# CLAUDE.md - AI Assistant Guide for ComfyUI

This document provides comprehensive guidance for AI assistants working with the ComfyUI codebase. It covers architecture, development workflows, conventions, and best practices.

## Table of Contents

1. [Project Overview](#project-overview)
2. [Repository Structure](#repository-structure)
3. [Architecture & Core Components](#architecture--core-components)
4. [Development Workflows](#development-workflows)
5. [Node System](#node-system)
6. [Testing Strategy](#testing-strategy)
7. [Configuration & Path Management](#configuration--path-management)
8. [API Structure](#api-structure)
9. [Key Conventions](#key-conventions)
10. [Common Patterns](#common-patterns)
11. [AI Assistant Guidelines](#ai-assistant-guidelines)

---

## Project Overview

**ComfyUI** is the most powerful and modular visual AI engine and application for stable diffusion and other generative AI models. It provides a graph/nodes/flowchart based interface for designing and executing advanced AI pipelines.

- **Language**: Python 3.9+ (3.13 recommended)
- **Version**: 0.3.68
- **License**: See LICENSE file
- **Homepage**: https://www.comfy.org/
- **Documentation**: https://docs.comfy.org/
- **Repository**: https://github.com/comfyanonymous/ComfyUI

### Key Features

- Node-based workflow system (visual programming)
- Support for 30+ AI model architectures (SD1.x, SDXL, SD3, Flux, video, audio, 3D)
- Smart memory management (runs on GPUs with as low as 1GB VRAM)
- Multi-platform GPU support (NVIDIA, AMD, Intel, Apple Silicon, Ascend, Cambricon, Iluvatar)
- Asynchronous execution with dependency resolution
- Multi-level caching for efficient re-execution
- WebSocket + REST API for real-time interaction
- Extensible plugin system (custom nodes)

---

## Repository Structure

```
ComfyUI/
├── comfy/                 # Core engine - model management, samplers, utilities
│   ├── model_management.py    # VRAM management, device handling
│   ├── model_detection.py     # Auto-detect model architectures
│   ├── model_patcher.py       # LoRA/weight patching system
│   ├── sd.py                  # Stable Diffusion implementations
│   ├── supported_models.py    # Model architecture definitions
│   ├── samplers.py            # Sampling algorithms
│   ├── controlnet.py          # ControlNet support
│   ├── clip_model.py          # Text encoders
│   ├── ops.py                 # Custom ops & quantization
│   └── ldm/                   # Latent Diffusion Model components
│
├── comfy_execution/       # Execution engine
│   ├── graph.py               # Workflow graph handling
│   ├── caching.py             # Multi-level cache strategies
│   └── executor.py            # Async execution coordinator
│
├── comfy_api/            # Versioned API system for custom nodes
│   ├── latest/                # Current development API (unstable)
│   ├── v0_0_2/                # Stable API v0.0.2
│   ├── v0_0_1/                # Stable API v0.0.1
│   └── internal/              # API registry and utilities
│
├── comfy_api_nodes/      # Cloud service integration nodes
│   ├── nodes_openai.py        # OpenAI integration
│   ├── nodes_stability.py     # Stability AI integration
│   └── ...                    # Other API-based nodes
│
├── comfy_extras/         # Built-in extra nodes
│   ├── nodes_*.py             # Various node collections
│   └── ...
│
├── comfy_config/         # Configuration management
│   ├── config_parser.py       # pyproject.toml parser
│   └── types.py               # Config types
│
├── api_server/           # Internal REST API routes
│   └── routes/internal/       # Additional server endpoints
│
├── app/                  # Application services
│   ├── user_manager.py        # User management
│   ├── model_manager.py       # Model installation/management
│   └── database/              # SQLAlchemy DB layer
│
├── web/                  # Frontend application
│   ├── index.html             # Main web interface
│   └── extensions/            # Frontend extensions
│
├── custom_nodes/         # User-installed custom nodes
├── models/               # Model storage (checkpoints, LoRAs, etc.)
├── input/                # Input files directory
├── output/               # Generated outputs directory
├── tests/                # Integration/inference tests
├── tests-unit/           # Fast unit tests
│
├── main.py               # Main entry point
├── server.py             # Web server & WebSocket handler
├── execution.py          # Workflow execution engine
├── nodes.py              # Core node definitions
├── folder_paths.py       # Path management system
├── requirements.txt      # Python dependencies
└── pyproject.toml        # Project metadata & linting config
```

### Important Files

| File | Purpose |
|------|---------|
| `main.py` | Application startup, initialization, custom node loading |
| `server.py` | aiohttp web server, WebSocket handler, REST API |
| `execution.py` | PromptExecutor, PromptQueue, workflow execution logic |
| `nodes.py` | Core built-in node definitions (LoadImage, SaveImage, etc.) |
| `folder_paths.py` | Central path management, model directory registry |
| `requirements.txt` | Production dependencies |
| `pyproject.toml` | Project metadata, linting rules (ruff, pylint) |
| `pytest.ini` | Test configuration and markers |

---

## Architecture & Core Components

### 1. Core Engine (`comfy/`)

The heart of ComfyUI - handles all model operations, memory management, and inference.

**Key Modules:**

- **`model_management.py`**:
  - GPU/CPU memory management
  - VRAM state detection (DISABLED, NO_VRAM, LOW_VRAM, NORMAL_VRAM, HIGH_VRAM, SHARED)
  - Smart model offloading strategies
  - Device abstraction (CUDA, ROCm, DirectML, MPS, XPU, NPU, MLU)

- **`model_detection.py`**:
  - Automatic model architecture detection from checkpoint files
  - Supports 30+ model types

- **`model_patcher.py`**:
  - Non-destructive model modification system
  - LoRA application, weight merging, parameter injection

- **`samplers.py`**:
  - Sampling algorithms (DPM++, DDIM, Euler, LMS, etc.)
  - Noise scheduling

- **`supported_models.py`**:
  - Architecture definitions for all supported models
  - Model-specific configurations

**Hardware Support Pattern:**
```python
# Device abstraction allows seamless multi-platform support
device = comfy.model_management.get_torch_device()
# Returns appropriate device: cuda, mps, cpu, xpu, etc.
```

### 2. Execution Engine (`comfy_execution/`, `execution.py`)

Handles workflow graph execution with dependency resolution and caching.

**Key Classes:**

- **`PromptExecutor`**:
  - Orchestrates workflow execution
  - Manages node dependencies
  - Handles async execution
  - Supports lazy evaluation

- **`PromptQueue`**:
  - Thread-safe queue with priority support
  - History management

- **`CacheSet`**:
  - Multi-level caching strategies:
    - `Classic`: Cache everything
    - `LRU`: Least recently used eviction
    - `RAM`: RAM pressure-based eviction
    - `None`: No caching

**Execution Flow:**
```
1. Validate workflow (type checking, dependency resolution)
2. Determine execution order (topological sort)
3. Check cache for unchanged nodes
4. Execute nodes in dependency order
5. Handle lazy inputs (execute only when needed)
6. Cache results for re-use
7. Send progress updates via WebSocket
```

### 3. Versioned API System (`comfy_api/`)

Provides stable APIs for custom node development with backwards compatibility.

**API Versions:**

- **`latest/`**: Development API (may have breaking changes)
- **`v0_0_2/`**: Stable API v0.0.2
- **`v0_0_1/`**: Stable API v0.0.1

**Why Versioning?**
- Allows core improvements without breaking custom nodes
- Custom nodes specify which API version they use
- Multiple versions can coexist

### 4. Web Server (`server.py`)

aiohttp-based server providing REST API and WebSocket communication.

**Key Features:**

- WebSocket at `/ws` for real-time updates
- REST endpoints for workflow submission, queue management
- File upload/download handling
- Middleware: CORS, compression, cache control, deprecation warnings
- Feature flag negotiation with clients

### 5. Node System (`nodes.py`, custom nodes)

Defines the visual programming interface - each node is a reusable operation.

**Two Node API Versions:**

1. **V1 (Legacy)**: Class-based with `INPUT_TYPES` classmethod
2. **V3 (Modern)**: Schema-based with type safety

See [Node System](#node-system) section for details.

### 6. Path Management (`folder_paths.py`)

Central registry for all file system operations.

**Features:**

- Global registry of model directories
- Multiple search paths per model type
- File extension filtering
- mtime-based cache invalidation
- Path annotation system: `[output]`, `[input]`, `[temp]`
- Security: Directory traversal prevention

**Model Types:**
```python
# Examples of model directories
models/checkpoints/     # Full SD checkpoints
models/unet/           # Diffusion models only
models/clip/           # Text encoders
models/vae/            # VAE models
models/loras/          # LoRA files
models/controlnet/     # ControlNet models
models/embeddings/     # Textual inversion
models/upscale_models/ # ESRGAN, RealESRGAN, etc.
# ... and 20+ more types
```

### 7. Application Services (`app/`)

Higher-level services built on top of the core.

- **`user_manager.py`**: User authentication and management
- **`model_manager.py`**: Model downloading and installation
- **`database/`**: SQLAlchemy models, migrations (Alembic)

---

## Development Workflows

### Entry Point Flow

**Startup Sequence (`main.py`):**

```
1. Parse CLI arguments (--cuda-device, --lowvram, --port, etc.)
2. Setup logging
3. Configure paths (models, input, output, custom_nodes)
4. Execute prestartup scripts from custom nodes
5. Initialize asyncio event loop
6. Load custom nodes via nodes.init_extra_nodes()
   - Load V1 nodes (NODE_CLASS_MAPPINGS)
   - Load V3 nodes (comfy_entrypoint)
   - Load web extensions
7. Setup database (if enabled)
8. Start prompt worker thread
9. Launch web server (server.py)
```

**Execution Flow:**

```
User submits workflow via /prompt
    ↓
Server adds to PromptQueue
    ↓
PromptExecutor picks up workflow
    ↓
Validate workflow (types, dependencies, inputs)
    ↓
Determine execution order (topological sort)
    ↓
For each node:
    - Check cache (skip if unchanged)
    - Check lazy status (defer if not needed)
    - Execute node function
    - Cache result
    - Send progress via WebSocket
    ↓
Return results (save images, etc.)
```

### Custom Node Development

**Location:** `custom_nodes/your_node/`

**V1 Node (Legacy but still supported):**

```python
# custom_nodes/my_nodes/__init__.py

class MyNode:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE",),
                "strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.01}),
            },
            "optional": {
                "text": ("STRING", {"multiline": True}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("processed_image",)
    FUNCTION = "process"
    CATEGORY = "image/processing"
    OUTPUT_NODE = False

    def process(self, image, strength, text=""):
        # Your processing logic here
        result = image * strength
        return (result,)

NODE_CLASS_MAPPINGS = {
    "MyNode": MyNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MyNode": "My Custom Node"
}
```

**V3 Node (Modern, recommended for new nodes):**

```python
# custom_nodes/my_nodes/__init__.py

from comfy_api.latest import io, ComfyExtension

class MyModernNode(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MyModernNode",
            display_name="My Modern Node",
            category="image/processing",
            inputs=[
                io.Image.Input("image"),
                io.Float.Input("strength", default=1.0, min=0.0, max=2.0, step=0.01),
                io.String.Input("text", multiline=True, optional=True),
            ],
            outputs=[
                io.Image.Output("processed_image")
            ]
        )

    @classmethod
    def execute(cls, image, strength, text=None) -> io.NodeOutput:
        result = image * strength
        return io.NodeOutput(result)

class MyExtension(ComfyExtension):
    async def get_node_list(self):
        return [MyModernNode]

async def comfy_entrypoint():
    return MyExtension()
```

**Adding Web Extensions:**

```python
# In your custom node __init__.py
WEB_DIRECTORY = "./web"  # Frontend files served from this directory
```

**Directory Structure for Custom Node:**
```
custom_nodes/my_nodes/
├── __init__.py          # Node definitions
├── requirements.txt     # Optional: node-specific dependencies
├── pyproject.toml       # Optional: node configuration
└── web/                 # Optional: frontend extensions
    └── my_extension.js
```

### Running the Application

**Basic:**
```bash
python main.py
```

**Common Options:**
```bash
# Specify GPU device
python main.py --cuda-device 0

# Low VRAM mode (aggressive offloading)
python main.py --lowvram

# High VRAM mode (keep models in VRAM)
python main.py --highvram

# CPU-only mode
python main.py --cpu

# Change port
python main.py --port 8080

# Listen on all interfaces
python main.py --listen 0.0.0.0

# Use different cache strategy
python main.py --cache-lru

# Use latest frontend
python main.py --front-end-version Comfy-Org/ComfyUI_frontend@latest

# Enable TLS/SSL
python main.py --tls-keyfile key.pem --tls-certfile cert.pem

# Custom model directories
python main.py --output-directory /path/to/outputs
```

**Environment Variables:**
```bash
# AMD ROCm optimizations
HSA_OVERRIDE_GFX_VERSION=10.3.0 python main.py  # For RDNA2
TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=1 python main.py --use-pytorch-cross-attention

# PyTorch tuning
PYTORCH_TUNABLEOP_ENABLED=1 python main.py
```

---

## Node System

### Node Anatomy

**Core Concepts:**

1. **Inputs**: Data coming into the node
2. **Outputs**: Data produced by the node
3. **Function**: The processing logic
4. **Category**: Organization in the UI
5. **Type System**: Ensures compatible connections

**Built-in Data Types:**

- `IMAGE`: Batch of images (tensor: [B, H, W, C])
- `LATENT`: Latent representation (dict with "samples" key)
- `MODEL`: Diffusion model
- `CONDITIONING`: Text conditioning
- `CLIP`: CLIP text encoder
- `VAE`: VAE encoder/decoder
- `CONTROL_NET`: ControlNet model
- `STRING`: Text string
- `INT`: Integer number
- `FLOAT`: Floating point number
- `BOOLEAN`: True/False
- Custom types defined by nodes

### V1 Node API (Legacy)

**Required Class Methods/Attributes:**

- `INPUT_TYPES(s)`: Defines node inputs (required and optional)
- `RETURN_TYPES`: Tuple of output type names
- `FUNCTION`: Name of the method to execute
- `CATEGORY`: UI category path (e.g., "image/processing")

**Optional Attributes:**

- `RETURN_NAMES`: Custom names for outputs
- `OUTPUT_NODE = True`: Mark as output node (workflow endpoint)
- `OUTPUT_IS_LIST = (True, False)`: Which outputs are lists
- `INPUT_IS_LIST`: Accept list inputs

**Optional Methods:**

- `IS_CHANGED(**kwargs)`: Return hash to determine if node should re-execute
- `VALIDATE_INPUTS(**kwargs)`: Custom input validation (return True or error string)
- `check_lazy_status(...)`: Control lazy evaluation

**Example with All Features:**

```python
class AdvancedNode:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE",),
                "mode": (["fast", "quality"],),
                "strength": ("FLOAT", {
                    "default": 1.0,
                    "min": 0.0,
                    "max": 2.0,
                    "step": 0.01,
                    "round": 0.001,
                }),
            },
            "optional": {
                "mask": ("MASK",),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
                "extra_pnginfo": "EXTRA_PNGINFO",
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("output", "info")
    FUNCTION = "process"
    CATEGORY = "advanced"
    OUTPUT_NODE = False

    @classmethod
    def IS_CHANGED(s, image, mode, strength, mask=None):
        # Return hash of inputs that affect output
        # If this changes, node will re-execute
        import hashlib
        m = hashlib.sha256()
        m.update(str(strength).encode())
        m.update(mode.encode())
        return m.hexdigest()

    @classmethod
    def VALIDATE_INPUTS(s, image, mode, strength, mask=None):
        # Custom validation
        if strength < 0:
            return "Strength must be positive"
        return True

    def process(self, image, mode, strength, mask=None, unique_id=None, extra_pnginfo=None):
        # Processing logic
        output = image * strength
        info = f"Processed with {mode} mode at strength {strength}"

        return (output, info)
```

### V3 Node API (Modern)

**Schema-Based Definition:**

```python
from comfy_api.latest import io, ComfyExtension

class ModernNode(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="ModernNode",
            display_name="Modern Processing Node",
            category="advanced",
            description="A modern node with type-safe inputs",
            inputs=[
                io.Image.Input("image", label="Input Image"),
                io.Enum.Input("mode", choices=["fast", "quality"], default="fast"),
                io.Float.Input("strength", default=1.0, min=0.0, max=2.0, step=0.01),
                io.Mask.Input("mask", optional=True),
            ],
            outputs=[
                io.Image.Output("output"),
                io.String.Output("info")
            ]
        )

    @classmethod
    def fingerprint_inputs(cls, image, mode, strength, mask=None) -> str:
        # Equivalent to IS_CHANGED
        import hashlib
        m = hashlib.sha256()
        m.update(str(strength).encode())
        m.update(mode.encode())
        return m.hexdigest()

    @classmethod
    def validate_inputs(cls, image, mode, strength, mask=None):
        # Custom validation
        if strength < 0:
            return io.ValidationResult.failure("Strength must be positive")
        return io.ValidationResult.success()

    @classmethod
    def execute(cls, image, mode, strength, mask=None) -> io.NodeOutput:
        output = image * strength
        info = f"Processed with {mode} mode at strength {strength}"
        return io.NodeOutput(output, info)
```

**Async Support:**

```python
class AsyncNode(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="AsyncNode",
            display_name="Async Processing Node",
            category="advanced",
            inputs=[io.String.Input("url")],
            outputs=[io.String.Output("content")]
        )

    @classmethod
    async def execute(cls, url) -> io.NodeOutput:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                content = await response.text()
        return io.NodeOutput(content)
```

### Node Registration

**V1 (Legacy):**
```python
NODE_CLASS_MAPPINGS = {
    "MyNode": MyNode,
    "AnotherNode": AnotherNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MyNode": "My Custom Node",
    "AnotherNode": "Another Custom Node",
}
```

**V3 (Modern):**
```python
class MyExtension(ComfyExtension):
    async def get_node_list(self):
        return [MyNode, AnotherNode, YetAnotherNode]

async def comfy_entrypoint():
    return MyExtension()
```

**You can mix both in the same file!**

### Special Node Types

**Output Node (saves to disk, shows in UI):**
```python
# V1
OUTPUT_NODE = True

# V3
io.Schema(..., is_output_node=True)
```

**Lazy Evaluation (defer execution until output is needed):**
```python
# V1
def check_lazy_status(self, input1, input2):
    # Return list of inputs that are needed
    # Others won't be executed yet
    return ["input1"]  # Only need input1 for now

# V3
@classmethod
def check_lazy_status(cls, input1, input2):
    return io.LazyStatus(needed_inputs=["input1"])
```

---

## Testing Strategy

ComfyUI has a two-tier testing approach: fast unit tests and comprehensive inference tests.

### Unit Tests (`tests-unit/`)

**Purpose:** Fast, isolated component testing without model loading.

**Location:** `tests-unit/`

**Structure:** Mirrors main codebase
```
tests-unit/
├── comfy_test/         # Tests for comfy/ modules
├── comfy_api_test/     # Tests for comfy_api/
├── server_test/        # Tests for server.py
├── execution_test/     # Tests for execution.py
└── ...
```

**Setup:**
```bash
pip install -r tests-unit/requirements.txt
pytest tests-unit/
```

**Example:**
```python
# tests-unit/comfy_test/test_model_detection.py
from comfy import model_detection

def test_detect_unet_config():
    state_dict = {...}  # Mock state dict
    config = model_detection.detect_unet_config(state_dict)
    assert config is not None
```

**Best Practices:**
- Mock external dependencies
- No actual model loading
- Fast execution (< 1 second per test)
- Test edge cases and error conditions

### Inference Tests (`tests/`)

**Purpose:** End-to-end workflow testing with actual model inference.

**Location:** `tests/`

**Markers:**
- `@pytest.mark.inference`: Full inference test (slow)
- `@pytest.mark.execution`: Workflow execution test

**Structure:**
```
tests/
├── inference/          # Full inference tests
│   ├── test_flux.py
│   ├── test_sd.py
│   └── ...
├── execution/          # Workflow execution tests
└── compare/            # Image quality regression
```

**Running:**
```bash
# All tests (slow)
pytest tests/

# Skip inference tests (faster)
pytest tests/ -m "not inference"

# Only inference tests
pytest tests/ -m inference

# Specific test file
pytest tests/inference/test_flux.py
```

**Example:**
```python
# tests/inference/test_basic.py
import pytest
from tests.inference.utils import run_workflow, compare_images

@pytest.mark.inference
def test_txt2img_workflow():
    workflow = load_workflow("txt2img.json")
    output = run_workflow(workflow)

    assert "images" in output
    assert len(output["images"]) > 0

    # Optional: Compare against baseline
    compare_images(output["images"][0], "baseline_txt2img.png", threshold=0.95)
```

**Image Quality Regression:**
```python
# tests/compare/
# Compare generated images against known good baselines
# Fails if similarity drops below threshold
```

### Test Utilities

**Inference Helpers (`tests/inference/utils.py`):**
- `run_workflow(workflow_dict)`: Execute workflow and return results
- `compare_images(img1, img2, threshold)`: Perceptual image comparison
- `load_test_model(model_type)`: Load models for testing

### CI/CD Considerations

**Fast Feedback Loop:**
```bash
# In CI, run unit tests on every commit
pytest tests-unit/

# Run inference tests only on release branches or manually
pytest tests/ -m inference
```

**Model Caching:**
- Inference tests require models to be downloaded
- Cache `models/` directory in CI to speed up tests

---

## Configuration & Path Management

### CLI Arguments (`comfy/cli_args.py`)

**Device Selection:**
- `--cpu`: Force CPU mode
- `--cuda-device 0`: Select CUDA device
- `--directml-device 0`: Use DirectML (Windows)

**Memory Management:**
- `--lowvram`: Aggressive offloading (4GB VRAM)
- `--normalvram`: Default behavior (6-8GB VRAM)
- `--highvram`: Keep models in VRAM (>8GB VRAM)
- `--novram`: CPU only, no GPU memory

**Cache Settings:**
- `--cache-classic`: Cache everything (default)
- `--cache-lru`: Least recently used eviction
- `--cache-ram`: RAM pressure-based eviction
- `--cache-none`: No caching

**Paths:**
- `--output-directory`: Where to save outputs
- `--input-directory`: Input files location
- `--temp-directory`: Temporary files
- `--user-directory`: User data (database, settings)

**Server:**
- `--listen ADDRESS`: Network interface (default: 127.0.0.1)
- `--port PORT`: Server port (default: 8188)
- `--tls-keyfile`, `--tls-certfile`: Enable HTTPS

**Frontend:**
- `--front-end-version Comfy-Org/ComfyUI_frontend@latest`: Use specific frontend version
- `--front-end-root /path`: Serve frontend from local directory

**Performance:**
- `--fast`: Disable some features for speed
- `--use-pytorch-cross-attention`: Use PyTorch's cross-attention
- `--disable-smart-memory`: Disable smart memory management
- `--fp16-vae`: Use FP16 for VAE (faster, less accurate)
- `--bf16-unet`: Use BF16 for UNet

**Development:**
- `--verbose`: Enable verbose logging
- `--dont-print-server`: Suppress server startup messages
- `--auto-launch`: Open browser on startup

### Folder Paths (`folder_paths.py`)

**Central Path Registry:**

```python
import folder_paths

# Get all checkpoints
checkpoints = folder_paths.get_filename_list("checkpoints")

# Get full path to a model
checkpoint_path = folder_paths.get_full_path("checkpoints", "model.safetensors")

# Add a custom search path
folder_paths.add_model_folder_path("checkpoints", "/my/models/checkpoints")

# Get annotated filename (with [output] suffix)
output_path = folder_paths.get_annotated_filepath("image.png")
# Returns: /path/to/output/image.png
```

**Model Directory Mapping:**

| Type | Directory | Purpose |
|------|-----------|---------|
| `checkpoints` | `models/checkpoints/` | Full SD checkpoints |
| `unet` | `models/unet/` | Diffusion models only |
| `clip` | `models/clip/` | Text encoders |
| `vae` | `models/vae/` | VAE models |
| `loras` | `models/loras/` | LoRA files |
| `controlnet` | `models/controlnet/` | ControlNet models |
| `clip_vision` | `models/clip_vision/` | CLIP vision encoders |
| `embeddings` | `models/embeddings/` | Textual inversion |
| `diffusers` | `models/diffusers/` | Diffusers format models |
| `vae_approx` | `models/vae_approx/` | TAESD preview VAEs |
| `upscale_models` | `models/upscale_models/` | ESRGAN, etc. |
| `photomaker` | `models/photomaker/` | PhotoMaker models |

**Annotations:**
```python
# Filename annotations indicate location
"image.png [output]"   # In output directory
"image.png [input]"    # In input directory
"image.png [temp]"     # In temp directory
```

### Extra Model Paths (`extra_model_paths.yaml`)

Share models between multiple ComfyUI installations:

```yaml
# extra_model_paths.yaml
base_path: /mnt/models/

checkpoints: checkpoints/
loras: loras/
vae: vae/

# Or absolute paths
another_install:
    checkpoints: /other/path/checkpoints/
```

**Usage:**
1. Copy `extra_model_paths.yaml.example` to `extra_model_paths.yaml`
2. Edit with your paths
3. Restart ComfyUI

### Custom Node Configuration (`pyproject.toml`)

Custom nodes can include a `pyproject.toml`:

```toml
[tool.comfy]
web_directory = "web"
# Other node-specific config
```

---

## API Structure

### WebSocket API (`/ws`)

**Real-time bidirectional communication for workflow execution.**

**Client → Server Messages:**

```javascript
// Feature flag negotiation
{
    "type": "client_features",
    "features": {
        "async_nodes": true,
        "preview_images": true
    }
}
```

**Server → Client Messages:**

```javascript
// Queue status update
{
    "type": "status",
    "data": {
        "status": {
            "exec_info": {
                "queue_remaining": 2
            }
        },
        "sid": "session_id"
    }
}

// Node execution started
{
    "type": "executing",
    "data": {
        "node": "3",  // Node ID
        "prompt_id": "uuid"
    }
}

// Progress update (with optional preview)
{
    "type": "progress",
    "data": {
        "value": 5,    // Current step
        "max": 20,     // Total steps
        "prompt_id": "uuid",
        "node": "3"
    }
}

// Node execution completed
{
    "type": "executed",
    "data": {
        "node": "3",
        "output": {
            "images": [
                {
                    "filename": "ComfyUI_00001_.png",
                    "subfolder": "",
                    "type": "output"
                }
            ]
        },
        "prompt_id": "uuid"
    }
}

// Execution error
{
    "type": "execution_error",
    "data": {
        "node_id": "3",
        "node_type": "KSampler",
        "exception_message": "Error message",
        "exception_type": "RuntimeError",
        "traceback": "...",
        "prompt_id": "uuid"
    }
}

// Nodes loaded from cache
{
    "type": "execution_cached",
    "data": {
        "nodes": ["1", "2"],  // Node IDs that were cached
        "prompt_id": "uuid"
    }
}
```

**Binary Messages (Preview Images):**

```
Event: "b" + PNG data
Metadata in first few bytes (node ID, etc.)
```

### REST API

**All endpoints available at both `/endpoint` and `/api/endpoint`**

#### Workflow Submission

**POST `/prompt`** - Submit workflow for execution

```json
Request:
{
    "prompt": {
        "1": {
            "class_type": "LoadImage",
            "inputs": {
                "image": "example.png"
            }
        },
        "2": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["1", 0]  // Output 0 from node 1
            }
        }
    },
    "client_id": "unique_client_id"
}

Response:
{
    "prompt_id": "uuid",
    "number": 1,  // Queue position
    "node_errors": {}  // Validation errors if any
}
```

**GET `/prompt`** - Get queue status

```json
Response:
{
    "exec_info": {
        "queue_remaining": 2
    }
}
```

#### Queue Management

**POST `/queue`** - Modify queue

```json
// Delete item from queue
{
    "delete": ["prompt_id_1", "prompt_id_2"]
}

// Clear queue
{
    "clear": true
}
```

**POST `/interrupt`** - Cancel current execution

**POST `/free`** - Free memory (unload models)

```json
{
    "unload_models": true,
    "free_memory": true
}
```

#### History

**GET `/history`** - Get execution history

```json
Response:
{
    "prompt_id_1": {
        "prompt": {...},
        "outputs": {
            "2": {
                "images": [
                    {
                        "filename": "ComfyUI_00001_.png",
                        "subfolder": "",
                        "type": "output"
                    }
                ]
            }
        },
        "status": {
            "status_str": "success",
            "completed": true,
            "messages": []
        }
    }
}
```

**GET `/history/{prompt_id}`** - Get specific execution

**POST `/history`** - Modify history

```json
// Delete from history
{
    "delete": ["prompt_id_1"]
}

// Clear history
{
    "clear": true
}
```

#### Node Information

**GET `/object_info`** - Get all node definitions

```json
Response:
{
    "LoadImage": {
        "input": {
            "required": {
                "image": ["IMAGE", {}]
            }
        },
        "output": ["IMAGE"],
        "output_is_list": [false],
        "output_name": ["IMAGE"],
        "name": "LoadImage",
        "display_name": "Load Image",
        "description": "...",
        "category": "image"
    },
    // ... all other nodes
}
```

**GET `/object_info/{node_class}`** - Get specific node definition

#### Model Listing

**GET `/models`** - List model types

```json
Response:
["checkpoints", "loras", "vae", "controlnet", ...]
```

**GET `/models/{type}`** - List models of specific type

```json
Response:
["model1.safetensors", "model2.ckpt", ...]
```

**GET `/embeddings`** - List embeddings

#### File Operations

**POST `/upload/image`** - Upload image

```
Multipart form data:
- image: file
- overwrite: "true" | "false"
- subfolder: "subfolder_name" (optional)
- type: "input" | "temp" (optional)
```

```json
Response:
{
    "name": "uploaded_image.png",
    "subfolder": "",
    "type": "input"
}
```

**GET `/view`** - View/download file

```
Query parameters:
- filename: "image.png"
- subfolder: "subfolder" (optional)
- type: "output" | "input" | "temp"
- preview: "true" (optional, for thumbnails)
- channel: "rgb" | "a" (optional, alpha channel)
```

**GET `/view_metadata/{folder}/{file}`** - Get model metadata

#### System Information

**GET `/system_stats`** - Get system information

```json
Response:
{
    "system": {
        "os": "linux",
        "python_version": "3.11.5",
        "embedded_python": false
    },
    "devices": [
        {
            "name": "NVIDIA GeForce RTX 3090",
            "type": "cuda",
            "index": 0,
            "vram_total": 25769803776,
            "vram_free": 12884901888,
            "torch_vram_total": 25769803776,
            "torch_vram_free": 12884901888
        }
    ]
}
```

**GET `/extensions`** - List frontend extensions

**GET `/features`** - Get server feature flags

```json
Response:
{
    "async_nodes": true,
    "preview_format": "jpeg",
    // ... other features
}
```

---

## Key Conventions

### Code Style

**Linting:** Configured in `pyproject.toml`

- **Ruff** for fast Python linting
  - Checks: N805, S307, S102, T, W, F (Pyflakes)
  - Excludes: `*.ipynb`, `generated/*.pyi`

- **Pylint** for detailed analysis
  - Python version: 3.9+
  - Many documentation checks disabled (pragmatic approach)
  - See `pyproject.toml` for full configuration

**Naming Conventions:**

| Element | Convention | Example |
|---------|-----------|---------|
| Files | `snake_case.py` | `model_management.py` |
| Classes | `PascalCase` | `PromptExecutor` |
| Functions/Methods | `snake_case` | `execute_workflow()` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_RESOLUTION` |
| Private | `_leading_underscore` | `_internal_function()` |
| Node categories | `lowercase/with/slashes` | `image/processing` |

**Type Hints:**

- Encouraged in new code
- Required for V3 API nodes
- Use `from __future__ import annotations` for forward references

**Docstrings:**

- Not strictly required (disabled in pylint)
- Encouraged for public APIs
- Use for complex algorithms

### Imports

**Standard Order:**

1. Standard library
2. Third-party libraries (torch, numpy, etc.)
3. Local modules (comfy, folder_paths, etc.)

**Example:**

```python
from __future__ import annotations

import os
import sys
import json
from typing import Optional

import torch
import numpy as np
from PIL import Image

import comfy.model_management
import folder_paths
from comfy.cli_args import args
```

### Error Handling

**Validation Before Execution:**

- Validate all inputs before starting workflow
- Return descriptive error messages
- Use `VALIDATE_INPUTS` for custom validation

**Graceful Degradation:**

- Don't crash if optional features unavailable
- Database, web extensions, etc. should degrade gracefully

**User-Friendly Errors:**

```python
# Good
raise ValueError(f"Image size {size} exceeds maximum {MAX_SIZE}")

# Bad
raise Exception("Invalid input")
```

### Memory Management

**Best Practices:**

1. **Unload models when not needed:**
   ```python
   comfy.model_management.soft_empty_cache()
   ```

2. **Respect VRAM states:**
   ```python
   vram_state = comfy.model_management.get_vram_state()
   if vram_state == comfy.model_management.VRAMState.LOW_VRAM:
       # Use more aggressive offloading
   ```

3. **Free intermediate tensors:**
   ```python
   del intermediate_result
   torch.cuda.empty_cache()  # If necessary
   ```

4. **Use appropriate dtypes:**
   - `torch.float16` for inference (most cases)
   - `torch.bfloat16` for training or if supported
   - `torch.float32` when precision required

### Path Handling

**Always use `folder_paths.py`:**

```python
# Good
checkpoint_path = folder_paths.get_full_path("checkpoints", "model.safetensors")

# Bad
checkpoint_path = os.path.join("models", "checkpoints", "model.safetensors")
```

**Security:**

- Never construct paths from user input directly
- Use `folder_paths` validation
- Prevent directory traversal attacks

### Progress Reporting

**For Long Operations:**

```python
from comfy.utils import ProgressBar

pbar = ProgressBar(total_steps)
for i in range(total_steps):
    # Do work
    pbar.update(1)
```

**This sends progress via WebSocket to the frontend.**

---

## Common Patterns

### 1. Loading Models

```python
import comfy.model_management
import comfy.sd
import folder_paths

def load_checkpoint(checkpoint_name):
    # Get full path
    checkpoint_path = folder_paths.get_full_path("checkpoints", checkpoint_name)

    # Load checkpoint
    checkpoint = comfy.sd.load_checkpoint_guess_config(
        checkpoint_path,
        output_vae=True,
        output_clip=True,
        embedding_directory=folder_paths.get_folder_paths("embeddings")
    )

    return checkpoint  # Returns dict with "model", "vae", "clip"
```

### 2. Applying LoRA

```python
def apply_lora(model, lora_name, strength_model, strength_clip):
    lora_path = folder_paths.get_full_path("loras", lora_name)

    lora = comfy.utils.load_torch_file(lora_path, safe_load=True)

    model_lora, clip_lora = comfy.sd.load_lora_for_models(
        model, clip, lora, strength_model, strength_clip
    )

    return (model_lora, clip_lora)
```

### 3. Image Processing

```python
import torch
from PIL import Image
import numpy as np

def pil_to_tensor(image: Image.Image) -> torch.Tensor:
    """Convert PIL Image to ComfyUI tensor format [1, H, W, C]"""
    image_np = np.array(image).astype(np.float32) / 255.0
    if len(image_np.shape) == 2:  # Grayscale
        image_np = np.expand_dims(image_np, axis=2)
    return torch.from_numpy(image_np).unsqueeze(0)

def tensor_to_pil(tensor: torch.Tensor) -> Image.Image:
    """Convert ComfyUI tensor [1, H, W, C] to PIL Image"""
    image_np = (tensor.squeeze(0).cpu().numpy() * 255).astype(np.uint8)
    return Image.fromarray(image_np)
```

### 4. Sampling

```python
import comfy.samplers

def sample(model, positive, negative, latent_image, seed, steps, cfg, sampler_name, scheduler):
    # Prepare noise
    noise = comfy.sample.prepare_noise(latent_image, seed)

    # Get sampler
    sampler = comfy.samplers.sampler_object(sampler_name)

    # Sample
    samples = comfy.sample.sample(
        model,
        noise,
        steps,
        cfg,
        sampler,
        scheduler,
        positive,
        negative,
        latent_image,
        denoise=1.0
    )

    return samples
```

### 5. VAE Encoding/Decoding

```python
def vae_encode(vae, image):
    """Encode image to latent"""
    latent = vae.encode(image[:,:,:,:3])  # RGB only
    return {"samples": latent}

def vae_decode(vae, latent):
    """Decode latent to image"""
    return vae.decode(latent["samples"])
```

### 6. CLIP Text Encoding

```python
def encode_text(clip, text):
    """Encode text prompt to conditioning"""
    tokens = clip.tokenize(text)
    cond, pooled = clip.encode_from_tokens(tokens, return_pooled=True)
    return [[cond, {"pooled_output": pooled}]]
```

### 7. Interrupt Checking

```python
from comfy.model_management import throw_exception_if_processing_interrupted

def long_operation():
    for i in range(1000):
        # Check for user interrupt
        throw_exception_if_processing_interrupted()

        # Do work
        process_step(i)
```

### 8. Custom Cache Key

```python
# V1 Node
@classmethod
def IS_CHANGED(s, **kwargs):
    import hashlib
    m = hashlib.sha256()

    # Hash relevant inputs
    for key, value in kwargs.items():
        if key not in ["unique_id", "extra_pnginfo"]:
            m.update(str(value).encode())

    return m.hexdigest()

# V3 Node
@classmethod
def fingerprint_inputs(cls, **kwargs) -> str:
    import hashlib
    m = hashlib.sha256()

    for key, value in kwargs.items():
        m.update(str(value).encode())

    return m.hexdigest()
```

### 9. Lazy Evaluation

```python
# Only execute expensive operations if output is needed

# V1
def check_lazy_status(self, input1, input2, expensive_input):
    # Check if we actually need expensive_input
    if self.mode == "simple":
        return ["input1"]  # Only need input1
    else:
        return ["input1", "expensive_input"]  # Need both

# V3
@classmethod
def check_lazy_status(cls, input1, input2, expensive_input):
    if cls.mode == "simple":
        return io.LazyStatus(needed_inputs=["input1"])
    else:
        return io.LazyStatus(needed_inputs=["input1", "expensive_input"])
```

### 10. Database Access (Optional)

```python
from app.database import session_scope
from app.database.models import User

def get_user(user_id):
    with session_scope() as session:
        user = session.query(User).filter_by(id=user_id).first()
        return user
```

---

## AI Assistant Guidelines

### When Working with ComfyUI Code

1. **Always use `folder_paths.py` for file operations**
   - Never hardcode paths like `models/checkpoints/`
   - Use `folder_paths.get_full_path()`, `get_filename_list()`, etc.

2. **Check both V1 and V3 node patterns**
   - When searching for node examples, look for both patterns
   - V1: `INPUT_TYPES`, `RETURN_TYPES`, `FUNCTION`
   - V3: `define_schema()`, `execute()`

3. **Understand the execution flow**
   - main.py → server.py → execution.py → nodes
   - Workflows are directed acyclic graphs (DAGs)
   - Nodes execute when all dependencies are ready

4. **Memory management is critical**
   - Users may have limited VRAM
   - Use `soft_empty_cache()` after heavy operations
   - Respect VRAM state settings

5. **Test both fast and slow paths**
   - Unit tests (`tests-unit/`) for logic
   - Inference tests (`tests/`) for actual model usage
   - Use markers: `@pytest.mark.inference`

6. **Handle interrupts gracefully**
   - Long operations should check for interrupts
   - Use `throw_exception_if_processing_interrupted()`

7. **Provide progress updates**
   - Use `ProgressBar` for user feedback
   - Especially important for slow operations

8. **Validate inputs before execution**
   - Implement `VALIDATE_INPUTS` or `validate_inputs`
   - Return clear error messages
   - Type checking is done automatically for V3

9. **Security considerations**
   - Never execute user-provided code
   - Validate file paths (no directory traversal)
   - Sanitize filenames

10. **Follow the release cycle**
    - Weekly releases (roughly Mondays)
    - Commits outside stable tags may be unstable
    - Frontend synced fortnightly from separate repo

### Common Tasks for AI Assistants

**Adding a new node:**

1. Decide between V1 (simple) or V3 (complex/modern)
2. Create class with appropriate structure
3. Implement processing logic
4. Add to `NODE_CLASS_MAPPINGS` (V1) or `comfy_entrypoint()` (V3)
5. Test with unit test and/or workflow test
6. Document input/output types

**Debugging execution issues:**

1. Check workflow validation errors first
2. Look at node type compatibility
3. Check for missing models/files
4. Review VRAM state and memory usage
5. Look for interrupt/cancel issues

**Optimizing performance:**

1. Profile to find bottlenecks
2. Consider caching strategies
3. Use appropriate dtypes (fp16 vs fp32)
4. Implement lazy evaluation if applicable
5. Offload to CPU when GPU memory tight

**Adding model support:**

1. Add model type to `folder_paths.py`
2. Implement loader in `comfy/sd.py` or new module
3. Add detection in `model_detection.py`
4. Create nodes for loading/using model
5. Add tests with actual model files

**Extending the API:**

1. Add route in `server.py` or `api_server/routes/`
2. Follow REST conventions
3. Add WebSocket events if real-time needed
4. Update feature flags if new capability
5. Document endpoint

### Understanding User Intent

**When users say...**

- "Add a node for X" → Create custom node (usually V1 for simplicity)
- "Optimize this workflow" → Look at caching, lazy eval, memory usage
- "Why is this slow?" → Check VRAM state, model offloading, cache misses
- "This workflow doesn't work" → Validate graph, check node compatibility
- "Add model support for X" → Implement loader, detector, nodes
- "How do I use X?" → Point to example workflows in docs

### Key Files for Different Tasks

| Task | Key Files |
|------|-----------|
| Add new node | `nodes.py`, `comfy_extras/nodes_*.py`, or `custom_nodes/` |
| Model loading | `comfy/sd.py`, `comfy/model_detection.py`, `folder_paths.py` |
| Execution logic | `execution.py`, `comfy_execution/` |
| API endpoints | `server.py`, `api_server/routes/` |
| Memory management | `comfy/model_management.py` |
| Testing | `tests/`, `tests-unit/` |
| Frontend | `web/`, separate frontend repo |
| Config | `comfy/cli_args.py`, `folder_paths.py` |

### Repository Navigation

**Finding node examples:**
```bash
# V1 nodes
grep -r "INPUT_TYPES" --include="*.py"

# V3 nodes
grep -r "define_schema" --include="*.py"

# Specific functionality
grep -r "LoadImage" nodes.py comfy_extras/
```

**Finding API usage:**
```bash
# REST endpoints
grep -r "@routes\." server.py api_server/

# WebSocket messages
grep -r "send_json" server.py
```

**Finding model code:**
```bash
# Model implementations
ls comfy/supported_models*.py

# Model loaders
grep -r "load_checkpoint" comfy/sd.py
```

### Documentation Resources

- **Official Docs**: https://docs.comfy.org/
- **Examples**: https://comfyanonymous.github.io/ComfyUI_examples/
- **Frontend Repo**: https://github.com/Comfy-Org/ComfyUI_frontend
- **Discord**: https://comfy.org/discord
- **Matrix**: https://app.element.io/#/room/#comfyui_space:matrix.org

---

## Quick Reference

### Essential Imports

```python
# Core
import comfy.model_management
import comfy.sd
import comfy.utils
import folder_paths

# Nodes
from comfy.comfy_types import IO, ComfyNodeABC
from comfy_api.latest import io, ComfyExtension

# Execution
from comfy.utils import ProgressBar
from comfy.model_management import throw_exception_if_processing_interrupted

# Image handling
import torch
from PIL import Image
import numpy as np
```

### Common CLI Commands

```bash
# Basic run
python main.py

# Low VRAM mode
python main.py --lowvram

# CPU only
python main.py --cpu

# Different port
python main.py --port 8080

# Latest frontend
python main.py --front-end-version Comfy-Org/ComfyUI_frontend@latest

# Verbose logging
python main.py --verbose

# Run tests
pytest tests-unit/                    # Fast unit tests
pytest tests/ -m "not inference"      # Skip slow tests
pytest tests/ -m inference            # Only inference tests
```

### Workflow JSON Structure

```json
{
    "1": {
        "class_type": "LoadImage",
        "inputs": {
            "image": "example.png"
        }
    },
    "2": {
        "class_type": "ImageScale",
        "inputs": {
            "image": ["1", 0],  // Output 0 from node 1
            "width": 512,
            "height": 512
        }
    },
    "3": {
        "class_type": "SaveImage",
        "inputs": {
            "images": ["2", 0]
        }
    }
}
```

### VRAM States

| State | VRAM | Behavior |
|-------|------|----------|
| `DISABLED` | N/A | No GPU |
| `NO_VRAM` | < 4GB | Most aggressive offloading |
| `LOW_VRAM` | 4-6GB | Aggressive offloading |
| `NORMAL_VRAM` | 6-8GB | Balanced (default) |
| `HIGH_VRAM` | > 8GB | Keep models in VRAM |
| `SHARED` | Shared | Unified memory (Apple Silicon, etc.) |

### Data Type Formats

```python
# Image: [Batch, Height, Width, Channels]
image = torch.randn(1, 512, 512, 3)  # RGB
image = torch.randn(1, 512, 512, 4)  # RGBA

# Latent: dict with "samples" key
latent = {
    "samples": torch.randn(1, 4, 64, 64)  # [B, C, H/8, W/8]
}

# Conditioning: list of [cond, pooled]
conditioning = [[
    torch.randn(1, 77, 768),  # Token embeddings
    {"pooled_output": torch.randn(1, 768)}  # Pooled
]]

# Mask: [Batch, Height, Width]
mask = torch.randn(1, 512, 512)
```

---

This document should provide a comprehensive foundation for AI assistants to effectively work with the ComfyUI codebase. For the most current information, always refer to the official documentation at https://docs.comfy.org/ and the repository itself.

**Last Updated:** 2025-11-16
**ComfyUI Version:** 0.3.68
