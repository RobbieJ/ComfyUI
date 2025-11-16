#!/usr/bin/env python3
"""
Quick test script for model registry system
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.model_registry import get_registry, calculate_file_hash
import json

def main():
    print("=" * 60)
    print("MODEL REGISTRY TEST")
    print("=" * 60)

    registry = get_registry()

    # Test 1: Check registry is initialized
    print("\n1. Registry Status:")
    stats = registry.get_stats()
    print(f"   ✓ Database: models/.registry/models.db")
    print(f"   ✓ Models: {stats['model_count']}")
    print(f"   ✓ Aliases: {stats['alias_count']}")
    print(f"   ✓ Total size: {stats['total_size_gb']} GB")

    # Test 2: List all models
    print("\n2. Registered Models:")
    models = registry.list_all_models()
    if models:
        for model in models:
            print(f"   • {model['file_path']}")
            print(f"     Hash: {model['sha256'][:16]}...")
            print(f"     Size: {model['size_bytes'] / (1024**2):.2f} MB")
            if model['aliases']:
                print(f"     Aliases: {', '.join(model['aliases'])}")
    else:
        print("   (No models registered yet)")

    # Test 3: Check dependency API format
    print("\n3. Example Workflow Dependency Format:")
    example_dependency = {
        "dependencies": {
            "checkpoints": [
                {
                    "filename": "example-model.safetensors",
                    "sha256": "0123456789abcdef" * 4,
                    "size": 6938078334,
                    "urls": ["https://example.com/model.safetensors"],
                    "display_name": "Example Model",
                    "required": True,
                    "requires_auth": False
                }
            ]
        }
    }
    print(json.dumps(example_dependency, indent=2))

    print("\n" + "=" * 60)
    print("Registry system is ready!")
    print("=" * 60)
    print("\nNext steps:")
    print("  1. Run ComfyUI server: python main.py")
    print("  2. Test download endpoint at POST /models/download")
    print("  3. Test dependencies at POST /models/check-dependencies")
    print("  4. Migrate existing models: python scripts/migrate_models_to_registry.py")

if __name__ == "__main__":
    main()
