"""
Model Registry System for Content-Addressed Model Storage

This module provides hash-based deduplication for model files, ensuring that
the same model is never downloaded twice, even if referenced with different
filenames across multiple workflows.

Security Note: This registry NEVER stores authentication tokens or API keys.
Only cleaned URLs (without query parameters) are stored.
"""

import sqlite3
import json
import os
import hashlib
from datetime import datetime
from typing import Optional, Dict, List, Any
from pathlib import Path
import logging

import folder_paths


class ModelRegistry:
    """Content-addressed model file registry with hash-based deduplication"""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize the model registry

        Args:
            db_path: Path to SQLite database. Defaults to models/.registry/models.db
        """
        if db_path is None:
            base_path = folder_paths.base_path
            registry_dir = os.path.join(base_path, "models", ".registry")
            os.makedirs(registry_dir, exist_ok=True)
            db_path = os.path.join(registry_dir, "models.db")

        self.db_path = db_path
        self.db = None
        self._init_database()

    def _init_database(self):
        """Initialize database schema"""
        self.db = sqlite3.connect(self.db_path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row

        with self.db:
            # Main model files table - one entry per unique hash
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS model_files (
                    sha256 TEXT PRIMARY KEY,
                    file_path TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    source_url TEXT,
                    metadata TEXT,
                    date_added TEXT NOT NULL
                )
            """)

            # Aliases table - multiple filenames can point to same hash
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS model_aliases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sha256 TEXT NOT NULL,
                    alias_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (sha256) REFERENCES model_files(sha256),
                    UNIQUE(alias_path)
                )
            """)

            # Indexes for fast lookups
            self.db.execute("""
                CREATE INDEX IF NOT EXISTS idx_aliases_sha256
                ON model_aliases(sha256)
            """)

            self.db.execute("""
                CREATE INDEX IF NOT EXISTS idx_aliases_path
                ON model_aliases(alias_path)
            """)

            # Download queue for tracking in-progress downloads
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS download_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sha256 TEXT,
                    url TEXT NOT NULL,
                    dest_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    error TEXT
                )
            """)

    def find_by_hash(self, sha256: str) -> Optional[Dict[str, Any]]:
        """Find model by SHA256 hash

        Args:
            sha256: SHA256 hash of the model file

        Returns:
            Dict with model info if found, None otherwise
        """
        cursor = self.db.execute("""
            SELECT sha256, file_path, size_bytes, source_url, metadata, date_added
            FROM model_files
            WHERE sha256 = ?
        """, (sha256,))

        row = cursor.fetchone()
        if row:
            return {
                "sha256": row["sha256"],
                "file_path": row["file_path"],
                "size_bytes": row["size_bytes"],
                "source_url": row["source_url"],
                "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                "date_added": row["date_added"]
            }
        return None

    def find_by_path(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Find model by file path (checks both main files and aliases)

        Args:
            file_path: Relative path to model file

        Returns:
            Dict with model info if found, None otherwise
        """
        # Normalize path
        file_path = os.path.normpath(file_path)

        # Check main files
        cursor = self.db.execute("""
            SELECT sha256, file_path, size_bytes, source_url, metadata, date_added
            FROM model_files
            WHERE file_path = ?
        """, (file_path,))

        row = cursor.fetchone()
        if row:
            return {
                "sha256": row["sha256"],
                "file_path": row["file_path"],
                "size_bytes": row["size_bytes"],
                "source_url": row["source_url"],
                "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                "date_added": row["date_added"]
            }

        # Check aliases
        cursor = self.db.execute("""
            SELECT mf.sha256, mf.file_path, mf.size_bytes, mf.source_url,
                   mf.metadata, mf.date_added
            FROM model_aliases ma
            JOIN model_files mf ON ma.sha256 = mf.sha256
            WHERE ma.alias_path = ?
        """, (file_path,))

        row = cursor.fetchone()
        if row:
            return {
                "sha256": row["sha256"],
                "file_path": row["file_path"],
                "size_bytes": row["size_bytes"],
                "source_url": row["source_url"],
                "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                "date_added": row["date_added"],
                "is_alias": True
            }

        return None

    def add_model(self, sha256: str, file_path: str, size_bytes: int,
                  source_url: Optional[str] = None, metadata: Optional[Dict] = None) -> bool:
        """Register a downloaded model

        IMPORTANT: source_url should have auth tokens stripped before calling

        Args:
            sha256: SHA256 hash of the file
            file_path: Relative path where file is stored
            size_bytes: Size of file in bytes
            source_url: Clean URL (without auth tokens)
            metadata: Additional metadata (display_name, etc.)

        Returns:
            True if added, False if already exists
        """
        # Clean URL (remove query params that might contain keys)
        if source_url:
            source_url = source_url.split("?")[0]

        # Normalize path
        file_path = os.path.normpath(file_path)

        try:
            with self.db:
                self.db.execute("""
                    INSERT INTO model_files
                    (sha256, file_path, size_bytes, source_url, metadata, date_added)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    sha256,
                    file_path,
                    size_bytes,
                    source_url,
                    json.dumps(metadata or {}),
                    datetime.now().isoformat()
                ))
            logging.info(f"Registered model: {file_path} (hash: {sha256[:16]}...)")
            return True
        except sqlite3.IntegrityError:
            # Already exists
            logging.debug(f"Model already registered: {sha256[:16]}...")
            return False

    def add_alias(self, sha256: str, alias_path: str) -> bool:
        """Add an alias (symlink) to an existing model

        Args:
            sha256: SHA256 hash of the target model
            alias_path: New path/filename for the alias

        Returns:
            True if added, False if already exists or model not found
        """
        # Verify model exists
        if not self.find_by_hash(sha256):
            logging.error(f"Cannot create alias: model {sha256[:16]}... not found")
            return False

        # Normalize path
        alias_path = os.path.normpath(alias_path)

        try:
            with self.db:
                self.db.execute("""
                    INSERT INTO model_aliases (sha256, alias_path, created_at)
                    VALUES (?, ?, ?)
                """, (sha256, alias_path, datetime.now().isoformat()))
            logging.info(f"Created alias: {alias_path} -> {sha256[:16]}...")
            return True
        except sqlite3.IntegrityError:
            # Already exists
            logging.debug(f"Alias already exists: {alias_path}")
            return False

    def get_aliases(self, sha256: str) -> List[str]:
        """Get all aliases for a model

        Args:
            sha256: SHA256 hash of the model

        Returns:
            List of alias paths
        """
        cursor = self.db.execute("""
            SELECT alias_path FROM model_aliases WHERE sha256 = ?
        """, (sha256,))

        return [row["alias_path"] for row in cursor.fetchall()]

    def list_all_models(self) -> List[Dict[str, Any]]:
        """List all registered models

        Returns:
            List of model info dictionaries
        """
        cursor = self.db.execute("""
            SELECT sha256, file_path, size_bytes, source_url, metadata, date_added
            FROM model_files
            ORDER BY date_added DESC
        """)

        models = []
        for row in cursor.fetchall():
            models.append({
                "sha256": row["sha256"],
                "file_path": row["file_path"],
                "size_bytes": row["size_bytes"],
                "source_url": row["source_url"],
                "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                "date_added": row["date_added"],
                "aliases": self.get_aliases(row["sha256"])
            })

        return models

    def remove_model(self, sha256: str) -> bool:
        """Remove model from registry (does not delete file)

        Args:
            sha256: SHA256 hash of the model to remove

        Returns:
            True if removed, False if not found
        """
        try:
            with self.db:
                # Remove aliases first
                self.db.execute("DELETE FROM model_aliases WHERE sha256 = ?", (sha256,))

                # Remove main entry
                cursor = self.db.execute("DELETE FROM model_files WHERE sha256 = ?", (sha256,))

                if cursor.rowcount > 0:
                    logging.info(f"Removed model from registry: {sha256[:16]}...")
                    return True
        except Exception as e:
            logging.error(f"Error removing model: {e}")

        return False

    def get_total_size(self) -> int:
        """Get total size of all registered models in bytes

        Returns:
            Total size in bytes
        """
        cursor = self.db.execute("SELECT SUM(size_bytes) as total FROM model_files")
        row = cursor.fetchone()
        return row["total"] or 0

    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics

        Returns:
            Dictionary with stats (model_count, alias_count, total_size_bytes)
        """
        cursor = self.db.execute("SELECT COUNT(*) as count FROM model_files")
        model_count = cursor.fetchone()["count"]

        cursor = self.db.execute("SELECT COUNT(*) as count FROM model_aliases")
        alias_count = cursor.fetchone()["count"]

        total_size = self.get_total_size()

        return {
            "model_count": model_count,
            "alias_count": alias_count,
            "total_size_bytes": total_size,
            "total_size_gb": round(total_size / (1024**3), 2)
        }

    def close(self):
        """Close database connection"""
        if self.db:
            self.db.close()


# Global singleton instance
_registry_instance = None

def get_registry() -> ModelRegistry:
    """Get global model registry instance"""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = ModelRegistry()
    return _registry_instance


def calculate_file_hash(file_path: str, chunk_size: int = 1024 * 1024) -> str:
    """Calculate SHA256 hash of a file

    Args:
        file_path: Path to file
        chunk_size: Size of chunks to read (default 1MB)

    Returns:
        SHA256 hash as hex string
    """
    hasher = hashlib.sha256()

    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)

    return hasher.hexdigest()
