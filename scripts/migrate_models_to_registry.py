#!/usr/bin/env python3
"""
Model Registry Migration Script

This script scans existing model files and populates the registry database
with their SHA256 hashes. This enables deduplication for models that were
downloaded before the registry system was implemented.

Usage:
    python scripts/migrate_models_to_registry.py [--dry-run] [--folder FOLDER]

Options:
    --dry-run       Show what would be done without making changes
    --folder FOLDER Only process specific folder (e.g., checkpoints, loras)
    --verbose       Show detailed progress
"""

import sys
import os
import argparse
import logging
from pathlib import Path

# Add parent directory to path to import ComfyUI modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import folder_paths
from app.model_registry import get_registry, calculate_file_hash


def setup_logging(verbose=False):
    """Setup logging configuration"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def format_bytes(bytes_value):
    """Format bytes to human-readable string"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.2f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.2f} PB"


def scan_folder(folder_name, registry, dry_run=False, verbose=False):
    """Scan a folder and register all model files

    Args:
        folder_name: Name of folder to scan (e.g., "checkpoints", "loras")
        registry: ModelRegistry instance
        dry_run: If True, don't actually register files
        verbose: If True, show detailed progress

    Returns:
        Dictionary with statistics
    """
    stats = {
        "total_files": 0,
        "already_registered": 0,
        "newly_registered": 0,
        "errors": 0,
        "total_size": 0
    }

    folder_name = folder_paths.map_legacy(folder_name)

    if folder_name not in folder_paths.folder_names_and_paths:
        logging.error(f"Unknown folder: {folder_name}")
        return stats

    folders = folder_paths.folder_names_and_paths[folder_name]
    allowed_extensions = folders[1]

    logging.info(f"Scanning folder: {folder_name}")

    for folder_index, folder_path in enumerate(folders[0]):
        if not os.path.isdir(folder_path):
            logging.debug(f"Skipping non-existent folder: {folder_path}")
            continue

        logging.info(f"  Scanning: {folder_path}")

        # Walk directory tree
        for dirpath, _, filenames in os.walk(folder_path, followlinks=True):
            # Skip hidden directories
            if any(part.startswith('.') for part in Path(dirpath).parts):
                continue

            # Filter by allowed extensions
            filtered_files = folder_paths.filter_files_extensions(filenames, allowed_extensions)

            for filename in filtered_files:
                full_path = os.path.join(dirpath, filename)
                relative_path = os.path.relpath(full_path, folder_paths.base_path)

                # Normalize to use forward slashes
                relative_path = relative_path.replace(os.sep, '/')

                # Skip if symlink or hardlink (already registered)
                if folder_paths.is_symlink_or_hardlink(full_path):
                    if verbose:
                        logging.debug(f"    Skipping link: {relative_path}")
                    continue

                stats["total_files"] += 1

                try:
                    file_size = os.path.getsize(full_path)
                    stats["total_size"] += file_size

                    if verbose:
                        logging.debug(f"    Processing: {relative_path} ({format_bytes(file_size)})")
                    else:
                        # Show progress for large scans
                        if stats["total_files"] % 10 == 0:
                            print(".", end="", flush=True)

                    # Check if already registered by path
                    existing = registry.find_by_path(relative_path)
                    if existing:
                        stats["already_registered"] += 1
                        if verbose:
                            logging.debug(f"      Already registered: {existing['sha256'][:16]}...")
                        continue

                    # Calculate hash
                    logging.info(f"    Hashing: {relative_path}")
                    sha256 = calculate_file_hash(full_path)

                    # Check if hash already exists (duplicate file)
                    existing_hash = registry.find_by_hash(sha256)
                    if existing_hash:
                        logging.info(f"      Duplicate of: {existing_hash['file_path']}")

                        if not dry_run:
                            # Add as alias
                            registry.add_alias(sha256, relative_path)
                            logging.info(f"      Added as alias")

                        stats["already_registered"] += 1
                        continue

                    # Register new model
                    if not dry_run:
                        registry.add_model(
                            sha256=sha256,
                            file_path=relative_path,
                            size_bytes=file_size,
                            source_url=None,  # Unknown for existing files
                            metadata={
                                "filename": filename,
                                "folder": folder_name,
                                "migrated": True
                            }
                        )
                        logging.info(f"      Registered: {sha256[:16]}...")
                    else:
                        logging.info(f"      [DRY RUN] Would register: {sha256[:16]}...")

                    stats["newly_registered"] += 1

                except Exception as e:
                    logging.error(f"    Error processing {relative_path}: {e}")
                    stats["errors"] += 1

        if not verbose and stats["total_files"] > 0:
            print()  # New line after progress dots

    return stats


def main():
    """Main migration function"""
    parser = argparse.ArgumentParser(description="Migrate existing models to registry")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be done without making changes")
    parser.add_argument("--folder", type=str,
                       help="Only process specific folder (e.g., checkpoints, loras)")
    parser.add_argument("--verbose", action="store_true",
                       help="Show detailed progress")

    args = parser.parse_args()

    setup_logging(args.verbose)

    if args.dry_run:
        logging.info("=== DRY RUN MODE - No changes will be made ===")

    # Get registry
    registry = get_registry()

    # Determine which folders to scan
    if args.folder:
        folders_to_scan = [args.folder]
    else:
        # Scan common model folders
        folders_to_scan = [
            "checkpoints",
            "loras",
            "vae",
            "controlnet",
            "upscale_models",
            "text_encoders",
            "diffusion_models",
            "clip_vision",
            "embeddings",
            "hypernetworks"
        ]

    logging.info("Starting model registry migration...")
    logging.info(f"Scanning folders: {', '.join(folders_to_scan)}")
    print()

    total_stats = {
        "total_files": 0,
        "already_registered": 0,
        "newly_registered": 0,
        "errors": 0,
        "total_size": 0
    }

    # Scan each folder
    for folder_name in folders_to_scan:
        stats = scan_folder(folder_name, registry, dry_run=args.dry_run, verbose=args.verbose)

        total_stats["total_files"] += stats["total_files"]
        total_stats["already_registered"] += stats["already_registered"]
        total_stats["newly_registered"] += stats["newly_registered"]
        total_stats["errors"] += stats["errors"]
        total_stats["total_size"] += stats["total_size"]

    # Print summary
    print()
    print("=" * 60)
    print("MIGRATION SUMMARY")
    print("=" * 60)
    print(f"Total files scanned:     {total_stats['total_files']}")
    print(f"Already registered:      {total_stats['already_registered']}")
    print(f"Newly registered:        {total_stats['newly_registered']}")
    print(f"Errors:                  {total_stats['errors']}")
    print(f"Total size:              {format_bytes(total_stats['total_size'])}")
    print("=" * 60)

    if args.dry_run:
        print("\n[DRY RUN] No changes were made. Run without --dry-run to apply changes.")
    else:
        print("\nMigration complete!")

        # Show registry stats
        registry_stats = registry.get_stats()
        print(f"\nRegistry statistics:")
        print(f"  Total models:   {registry_stats['model_count']}")
        print(f"  Total aliases:  {registry_stats['alias_count']}")
        print(f"  Total size:     {registry_stats['total_size_gb']} GB")

    return 0 if total_stats["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
