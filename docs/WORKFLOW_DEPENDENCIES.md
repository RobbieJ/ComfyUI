# Workflow Dependencies System

This document describes the workflow dependency system for automatic model downloads with hash-based deduplication.

## Overview

The workflow dependency system allows workflows to specify required models (checkpoints, LoRAs, VAEs, etc.) that can be automatically downloaded when the workflow is loaded. Key features:

- **Hash-based deduplication**: Models are never downloaded twice, even if referenced with different filenames
- **Ephemeral API keys**: Authentication tokens are never stored, only used during download
- **Progress tracking**: Real-time download progress with detailed feedback
- **Multi-source support**: Download from HuggingFace, Civitai, and other sources
- **Automatic verification**: SHA256 hash verification ensures file integrity

## Workflow Format

### Basic Structure

Workflows can include a `dependencies` section that lists required models:

```json
{
  "workflow": {
    "nodes": {
      ... (existing workflow nodes)
    },
    "dependencies": {
      "checkpoints": [ ... ],
      "loras": [ ... ],
      "vae": [ ... ],
      "controlnet": [ ... ],
      "upscale_models": [ ... ]
    }
  }
}
```

### Model Specification

Each model is specified with the following fields:

```json
{
  "filename": "sd_xl_base_1.0.safetensors",
  "sha256": "31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b",
  "size": 6938078334,
  "urls": [
    "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors"
  ],
  "display_name": "Stable Diffusion XL Base 1.0",
  "required": true,
  "requires_auth": false,
  "auth_provider": null
}
```

#### Field Descriptions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `filename` | string | Yes | Filename to save as (without path) |
| `sha256` | string | Yes | SHA256 hash for deduplication and verification |
| `size` | integer | Yes | File size in bytes |
| `urls` | array | Yes | List of download URLs (tried in order) |
| `display_name` | string | No | Human-readable name for UI |
| `required` | boolean | No | Whether model is required (default: true) |
| `requires_auth` | boolean | No | Whether authentication is needed |
| `auth_provider` | string | No | Provider name ("huggingface" or "civitai") |

### Complete Example

```json
{
  "workflow": {
    "nodes": {
      "1": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {
          "ckpt_name": "sd_xl_base_1.0.safetensors"
        }
      },
      "2": {
        "class_type": "LoraLoader",
        "inputs": {
          "model": [1, 0],
          "clip": [1, 1],
          "lora_name": "detail-tweaker-xl.safetensors",
          "strength_model": 1.0,
          "strength_clip": 1.0
        }
      },
      "3": {
        "class_type": "VAELoader",
        "inputs": {
          "vae_name": "sdxl_vae.safetensors"
        }
      }
    },
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
      "loras": [
        {
          "filename": "detail-tweaker-xl.safetensors",
          "sha256": "9c5e9d66c7f5e1b2a3d4e5f6g7h8i9j0",
          "size": 143958118,
          "urls": [
            "https://civitai.com/api/download/models/135867"
          ],
          "display_name": "Detail Tweaker XL",
          "required": false,
          "requires_auth": false
        }
      ],
      "vae": [
        {
          "filename": "sdxl_vae.safetensors",
          "sha256": "235745af8d86bf4a4c1f7d4a7c8e5c64a1f2d3c4b5c6d7e8f9g0h1i2j3k4l5m6",
          "size": 334643018,
          "urls": [
            "https://huggingface.co/stabilityai/sdxl-vae/resolve/main/sdxl_vae.safetensors"
          ],
          "display_name": "SDXL VAE",
          "required": true,
          "requires_auth": false
        }
      ]
    }
  }
}
```

## Authentication

For models that require authentication (gated models on HuggingFace, Civitai premium models, etc.):

### HuggingFace Authentication

```json
{
  "filename": "private-model.safetensors",
  "sha256": "...",
  "size": 2000000000,
  "urls": [
    "https://huggingface.co/private-org/private-model/resolve/main/model.safetensors"
  ],
  "display_name": "Private Model",
  "required": true,
  "requires_auth": true,
  "auth_provider": "huggingface"
}
```

When this model is encountered, users will be prompted for their HuggingFace token. The token:
- Is stored in-memory only
- Is never written to disk or logs
- Is automatically cleared after download
- Can be obtained from https://huggingface.co/settings/tokens

### Civitai Authentication

```json
{
  "filename": "premium-model.safetensors",
  "sha256": "...",
  "size": 5000000000,
  "urls": [
    "https://civitai.com/api/download/models/12345"
  ],
  "display_name": "Premium Model",
  "required": true,
  "requires_auth": true,
  "auth_provider": "civitai"
}
```

Civitai API keys can be obtained from https://civitai.com/user/account

## Hash-Based Deduplication

The system uses SHA256 hashes to prevent duplicate downloads:

1. **Before download**: System checks if a model with the same hash already exists
2. **If exists**: Creates a symlink/alias instead of downloading
3. **If not exists**: Downloads and calculates hash during download
4. **After download**: Verifies hash matches expected value

### Example Scenario

1. User downloads workflow A that requires `sd_xl_base_1.0.safetensors` (hash: `31e35c80...`)
2. Model is downloaded and registered with hash
3. User downloads workflow B that requires `sdxl-base-v1.safetensors` (same hash: `31e35c80...`)
4. System detects hash already exists
5. Creates symlink from `sdxl-base-v1.safetensors` → `sd_xl_base_1.0.safetensors`
6. **Result**: 6.9 GB saved by not downloading twice

## API Endpoints

### Check Dependencies

Check which models from a workflow are missing:

```http
POST /models/check-dependencies
Content-Type: application/json

{
  "dependencies": {
    "checkpoints": [ ... ],
    "loras": [ ... ]
  }
}
```

**Response:**

```json
{
  "missing": [
    {
      "filename": "sd_xl_base_1.0.safetensors",
      "type": "checkpoints",
      "sha256": "31e35c80...",
      "size": 6938078334,
      "urls": ["https://..."],
      "requires_auth": false
    }
  ],
  "existing": [
    {
      "filename": "detail-tweaker.safetensors",
      "exists_at": "loras/detail-tweaker-v2.safetensors",
      "type": "loras",
      "sha256": "9c5e9d66...",
      "size": 143958118,
      "action": "symlink"
    }
  ],
  "total_download_size": 6938078334,
  "total_saved_size": 143958118
}
```

### Download Model

Download a single model with deduplication:

```http
POST /models/download
Content-Type: application/json

{
  "url": "https://huggingface.co/.../model.safetensors",
  "folder": "checkpoints",
  "filename": "model.safetensors",
  "sha256": "31e35c80...",
  "display_name": "My Model",
  "huggingface_token": "hf_..."  // Ephemeral, never stored
}
```

**Response:** NDJSON stream with progress updates:

```json
{"message":"Downloading to model.safetensors","bytes":0,"total_bytes":6938078334}
{"progress":0.01,"bytes":69380783,"total_bytes":6938078334}
{"progress":0.50,"bytes":3469039167,"total_bytes":6938078334}
{"progress":1.0,"bytes":6938078334,"total_bytes":6938078334}
{"message":"Download complete","path":"/path/to/model.safetensors","sha256":"31e35c80..."}
```

## Migration for Existing Models

For users with existing models, run the migration script to populate the registry:

```bash
# Dry run (preview only)
python scripts/migrate_models_to_registry.py --dry-run --verbose

# Migrate all models
python scripts/migrate_models_to_registry.py

# Migrate specific folder
python scripts/migrate_models_to_registry.py --folder checkpoints
```

This will:
1. Scan all model folders
2. Calculate SHA256 hash for each file
3. Register files in the database
4. Detect duplicates and create aliases

## Security Considerations

### API Key Handling

- **Never stored**: Keys are held in-memory only
- **Never logged**: Request logs exclude authentication headers
- **Auto-cleared**: Keys are cleared after download or after 1 hour timeout
- **User informed**: UI clearly states "will not be saved"

### Download Security

- **URL whitelist**: Only allowed sources (HuggingFace, Civitai, localhost)
- **Path traversal prevention**: Filenames are validated and normalized
- **Hash verification**: Files are verified against expected SHA256
- **Extension validation**: Only allowed file types can be downloaded

## Creating Shareable Workflows

To create a workflow with dependencies:

1. **Export your workflow** from ComfyUI
2. **Add dependencies section** with model metadata
3. **Calculate SHA256 hashes** for each model:
   ```bash
   sha256sum model.safetensors
   ```
4. **Test the workflow** by loading it on a clean install
5. **Share the JSON file**

### Best Practices

- Include `display_name` for better UX
- Mark optional models with `"required": false`
- Provide multiple URLs when possible (fallbacks)
- Use stable URLs (avoid temporary download links)
- Test with fresh installation to verify all dependencies are listed
- Document any special requirements in workflow description

## Troubleshooting

### Models not downloading

1. Check browser console for errors
2. Verify URLs are accessible
3. Check if authentication is required
4. Ensure sufficient disk space

### Hash mismatch errors

1. Model file may have been updated at source
2. Calculate new hash: `sha256sum model.safetensors`
3. Update workflow JSON with new hash

### Duplicate downloads despite deduplication

1. Run migration script to register existing models
2. Verify SHA256 hashes match exactly
3. Check registry database: `models/.registry/models.db`

## Technical Details

### Storage Structure

```
models/
  .registry/
    models.db              # SQLite database
  .cache/
    tmp/                   # Temporary downloads
  checkpoints/
    sd_xl_base_1.0.safetensors       # Actual file
    sdxl-base-v1.safetensors         # Symlink → sd_xl_base_1.0.safetensors
  loras/
    detail-tweaker.safetensors
```

### Database Schema

**model_files:**
- `sha256` (PRIMARY KEY): SHA256 hash
- `file_path`: Relative path to file
- `size_bytes`: File size
- `source_url`: Original download URL (without auth params)
- `metadata`: JSON metadata
- `date_added`: Timestamp

**model_aliases:**
- `id` (PRIMARY KEY)
- `sha256` (FOREIGN KEY): Reference to model_files
- `alias_path`: Alternative path/filename
- `created_at`: Timestamp

## Future Enhancements

Potential improvements for future versions:

- **Model registry server**: Central database of popular models with verified hashes
- **Torrent support**: P2P downloads for very large models (20GB+)
- **IPFS support**: Decentralized model distribution
- **Resume support**: Pause and resume large downloads
- **Batch downloads**: Parallel downloading of multiple models
- **Dependency resolution**: Automatic detection of workflow requirements
