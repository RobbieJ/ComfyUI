# Model Download System - Quick Start Guide

## Overview

ComfyUI now includes an advanced model download system with hash-based deduplication that prevents downloading the same model twice, even if it has different filenames in different workflows.

## Key Features

✅ **Never download the same model twice** - Models are identified by SHA256 hash
✅ **Ephemeral API key support** - HuggingFace and Civitai tokens are never stored
✅ **Automatic verification** - Files are verified against expected hashes
✅ **Space efficient** - Uses symlinks to share models across workflows
✅ **Progress tracking** - Real-time download progress with detailed feedback

## For Users

### Loading Workflows with Dependencies

When you load a workflow that includes dependency metadata:

1. System automatically checks which models you already have
2. Shows download prompt with:
   - Missing models (need to download)
   - Existing models (already have, saved space)
   - Total download size
3. If authentication needed, prompts for API key (not saved)
4. Downloads missing models with progress tracking
5. Automatically creates symlinks for duplicate models

### Using Private Models

For gated HuggingFace models or Civitai premium content:

1. Get your API key:
   - **HuggingFace**: https://huggingface.co/settings/tokens
   - **Civitai**: https://civitai.com/user/account

2. When prompted, enter your key
3. Key is used only for download, then immediately cleared
4. Never stored to disk or logs

### Migrating Existing Models

If you already have models downloaded:

```bash
# Preview what will be migrated
python scripts/migrate_models_to_registry.py --dry-run

# Migrate all models
python scripts/migrate_models_to_registry.py

# Migrate specific folder only
python scripts/migrate_models_to_registry.py --folder checkpoints
```

This registers your existing models in the deduplication database.

## For Workflow Creators

### Adding Dependencies to Workflows

1. **Calculate SHA256 hash** for each model:
   ```bash
   sha256sum model.safetensors
   ```

2. **Add dependencies section** to workflow JSON:
   ```json
   {
     "workflow": {
       "nodes": { ... },
       "dependencies": {
         "checkpoints": [
           {
             "filename": "sd_xl_base_1.0.safetensors",
             "sha256": "31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b",
             "size": 6938078334,
             "urls": [
               "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors"
             ],
             "display_name": "Stable Diffusion XL Base 1.0",
             "required": true,
             "requires_auth": false
           }
         ],
         "loras": [ ... ],
         "vae": [ ... ]
       }
     }
   }
   ```

3. **Test workflow** on clean install to verify all dependencies are listed

See [WORKFLOW_DEPENDENCIES.md](./WORKFLOW_DEPENDENCIES.md) for complete format specification.

## How Deduplication Works

### Example Scenario

1. Download Workflow A that uses `sd_xl_base_1.0.safetensors`
   - File downloaded: 6.9 GB
   - Registered with hash: `31e35c80...`

2. Download Workflow B that uses `sdxl-base-v1.safetensors` (same file, different name)
   - System detects hash `31e35c80...` already exists
   - Creates symlink instead of downloading
   - **Saved: 6.9 GB**

3. Result:
   ```
   models/checkpoints/
     sd_xl_base_1.0.safetensors      (6.9 GB actual file)
     sdxl-base-v1.safetensors        (symlink → sd_xl_base_1.0.safetensors)
   ```

## Storage Structure

```
models/
  .registry/
    models.db              # SQLite database tracking all models by hash
  .cache/
    tmp/                   # Temporary download location
  checkpoints/
    model1.safetensors     # Actual file
    model2.safetensors     # Could be symlink to model1 if same hash
  loras/
    lora1.safetensors
  vae/
    vae1.safetensors
```

## API Endpoints

### Check Dependencies
```bash
POST /models/check-dependencies
```
Returns which models are missing vs already available

### Download Model
```bash
POST /models/download
```
Downloads model with hash verification and deduplication

See [WORKFLOW_DEPENDENCIES.md](./WORKFLOW_DEPENDENCIES.md) for API documentation.

## Security

### API Key Handling
- Keys stored **in-memory only** (never on disk)
- Automatically cleared after download or 1-hour timeout
- Never logged or included in error messages
- UI clearly states "will not be saved"

### Download Security
- URL whitelist (HuggingFace, Civitai, localhost only)
- Path traversal prevention
- SHA256 verification
- File extension validation

## Troubleshooting

### "Model already exists" but I don't see it

Run the migration script to register existing models:
```bash
python scripts/migrate_models_to_registry.py
```

### Hash mismatch error

Model file was likely updated at source. Calculate new hash:
```bash
sha256sum path/to/model.safetensors
```
Update workflow JSON with new hash.

### Download fails with auth error

1. Verify API key is correct
2. Check token has required permissions (HuggingFace: read access)
3. Verify model is accessible with that token

## Advanced Usage

### View Registry Statistics

```python
from app.model_registry import get_registry

registry = get_registry()
stats = registry.get_stats()

print(f"Total models: {stats['model_count']}")
print(f"Total aliases: {stats['alias_count']}")
print(f"Total size: {stats['total_size_gb']} GB")
```

### List All Registered Models

```python
from app.model_registry import get_registry

registry = get_registry()
models = registry.list_all_models()

for model in models:
    print(f"{model['file_path']}: {model['sha256'][:16]}...")
    if model['aliases']:
        print(f"  Aliases: {', '.join(model['aliases'])}")
```

## Support

For detailed documentation, see:
- [WORKFLOW_DEPENDENCIES.md](./WORKFLOW_DEPENDENCIES.md) - Complete format specification
- API documentation in source code

For issues:
- Check browser console for errors
- Check server logs for download errors
- Verify disk space available
- Ensure URLs are accessible
