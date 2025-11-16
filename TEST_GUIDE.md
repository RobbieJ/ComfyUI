# Testing the Model Download & Deduplication System

## ✅ System Status

Run this to verify everything is working:

```bash
python3 scripts/test_registry.py
```

## 🧪 Test Scenarios

### **Test 1: Basic Registry Functions**

```python
python3 << 'EOF'
import sys
sys.path.insert(0, "/home/user/ComfyUI")
from app.model_registry import get_registry

registry = get_registry()

# Check stats
stats = registry.get_stats()
print(f"Models: {stats['model_count']}")
print(f"Aliases: {stats['alias_count']}")
print(f"Size: {stats['total_size_gb']} GB")
EOF
```

### **Test 2: API Endpoint - Check Dependencies**

Start ComfyUI server first: `python main.py`

Then test the dependency checker:

```bash
curl -X POST http://localhost:8188/models/check-dependencies \
  -H "Content-Type: application/json" \
  -d '{
    "dependencies": {
      "checkpoints": [
        {
          "filename": "test-model.safetensors",
          "sha256": "abc123def456",
          "size": 1000000,
          "urls": ["https://example.com/model.safetensors"],
          "display_name": "Test Model",
          "required": true,
          "requires_auth": false
        }
      ]
    }
  }'
```

Expected response:
```json
{
  "missing": [...],
  "existing": [],
  "total_download_size": 1000000,
  "total_saved_size": 0
}
```

### **Test 3: Download Endpoint (with deduplication)**

Download a whitelisted model:

```bash
curl -X POST http://localhost:8188/models/download \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://huggingface.co/stabilityai/stable-zero123/resolve/main/stable_zero123.ckpt",
    "folder": "checkpoints",
    "filename": "stable_zero123.ckpt",
    "sha256": "your_calculated_hash_here"
  }'
```

### **Test 4: Deduplication Test**

1. Download a model with filename "model-v1.safetensors"
2. Try to download again with filename "model-v2.safetensors" but SAME sha256
3. System should:
   - Detect hash already exists
   - Create symlink instead of downloading
   - Return `"status": "already_exists"`

### **Test 5: Migration Script**

If you have existing models:

```bash
# Dry run first
python scripts/migrate_models_to_registry.py --dry-run --verbose

# Actually migrate
python scripts/migrate_models_to_registry.py

# Migrate specific folder only
python scripts/migrate_models_to_registry.py --folder checkpoints
```

### **Test 6: Frontend Extension**

1. Start ComfyUI: `python main.py`
2. Open browser to http://localhost:8188
3. Open browser console (F12)
4. Look for: `[DependencyManager] Extension loaded`

### **Test 7: Workflow with Dependencies**

Create a test workflow file:

```json
{
  "workflow": {
    "nodes": {
      "1": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {
          "ckpt_name": "test-model.safetensors"
        }
      }
    },
    "dependencies": {
      "checkpoints": [
        {
          "filename": "test-model.safetensors",
          "sha256": "31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b",
          "size": 6938078334,
          "urls": [
            "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors"
          ],
          "display_name": "SDXL Base 1.0",
          "required": true,
          "requires_auth": false
        }
      ]
    }
  }
}
```

Load this workflow in ComfyUI and the system should:
1. Parse dependencies
2. Check which models exist
3. Show download prompt if needed
4. Download missing models
5. Register in database

## 🔍 Verification Commands

### Check registry database:
```bash
ls -lh models/.registry/models.db
```

### Check temp directory:
```bash
ls -la models/.cache/tmp/
```

### List registered models:
```python
python3 << 'EOF'
import sys
sys.path.insert(0, "/home/user/ComfyUI")
from app.model_registry import get_registry

registry = get_registry()
models = registry.list_all_models()

for model in models:
    print(f"{model['file_path']}: {model['sha256'][:16]}...")
    if model['aliases']:
        print(f"  Aliases: {', '.join(model['aliases'])}")
EOF
```

### Check for symlinks:
```bash
find models/checkpoints -type l -ls
```

## 🔐 Testing Ephemeral Keys

1. Create a workflow with a gated HuggingFace model:
   ```json
   {
     "filename": "gated-model.safetensors",
     "sha256": "...",
     "urls": ["https://huggingface.co/gated/model/..."],
     "requires_auth": true,
     "auth_provider": "huggingface"
   }
   ```

2. Load workflow
3. System prompts for HF token
4. Enter token (get from https://huggingface.co/settings/tokens)
5. Download proceeds
6. Verify key NOT in logs:
   ```bash
   # Should NOT contain token
   grep -i "hf_" logs/*.log
   ```

## 📊 Expected Results

### ✅ Success Indicators:
- [x] Registry database created at `models/.registry/models.db`
- [x] Temp directory exists at `models/.cache/tmp/`
- [x] Download endpoint returns NDJSON stream
- [x] Duplicate downloads create symlinks
- [x] Hash verification works
- [x] API keys not logged
- [x] Frontend extension loads

### 🐛 Common Issues:

**Import errors:**
- Make sure to run from ComfyUI directory
- Use `sys.path.insert(0, os.getcwd())` in scripts

**Permission errors (Windows):**
- Symlinks require Developer Mode
- System falls back to hardlinks automatically

**Path issues:**
- Check `folder_paths.base_path` is correct
- Verify model folders exist

## 🎯 Quick Verification

Run this one-liner to check everything:

```bash
python3 scripts/test_registry.py && \
echo "✓ Registry OK" && \
ls -lh models/.registry/models.db && \
echo "✓ Database OK" && \
ls -ld models/.cache/tmp/ && \
echo "✓ Temp dir OK" && \
echo "✓ System ready!"
```

## 📝 Next Steps

1. **Start ComfyUI**: `python main.py`
2. **Test download**: Use curl or frontend
3. **Test deduplication**: Download same model with different name
4. **Migrate existing models**: `python scripts/migrate_models_to_registry.py`
5. **Create workflows**: Add dependency sections
6. **Share workflows**: Include model metadata

## 🆘 Debugging

**Check server logs:**
```bash
# Look for registry-related messages
grep -i "registry\|dedup\|symlink" server.log
```

**Inspect database:**
```python
import sqlite3
conn = sqlite3.connect('models/.registry/models.db')
cursor = conn.cursor()

# Count models
cursor.execute("SELECT COUNT(*) FROM model_files")
print(f"Models: {cursor.fetchone()[0]}")

# Count aliases
cursor.execute("SELECT COUNT(*) FROM model_aliases")
print(f"Aliases: {cursor.fetchone()[0]}")
```

**Test hash calculation:**
```python
import sys
sys.path.insert(0, "/home/user/ComfyUI")
from app.model_registry import calculate_file_hash

# Replace with actual model file
hash = calculate_file_hash("models/checkpoints/your-model.safetensors")
print(f"SHA256: {hash}")
```
