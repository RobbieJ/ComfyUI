import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";

// Known model URLs mapping - users can extend this
const KNOWN_MODEL_URLS = {
    // Qwen models
    "qwen_image_vae.safetensors": "https://huggingface.co/Comfy-Org/Qwen2.5-VL-7B-Instruct-fp8/resolve/main/qwen_image_vae.safetensors",
    "qwen_image_fp8_e4m3fn.safetensors": "https://huggingface.co/Comfy-Org/Qwen2.5-VL-7B-Instruct-fp8/resolve/main/qwen_image_fp8_e4m3fn.safetensors",
    "qwen_2.5_vl_7b_fp8_scaled.safetensors": "https://huggingface.co/Comfy-Org/Qwen2.5-VL-7B-Instruct-fp8/resolve/main/qwen_2.5_vl_7b_fp8_scaled.safetensors",
    "Qwen-Image-Lightning-4steps-V1.0.safetensors": "https://huggingface.co/Comfy-Org/Qwen-Lightning-Lora-fp8/resolve/main/Qwen-Image-Lightning-4steps-V1.0.safetensors",
};

// Map node types to folder types
const NODE_TYPE_TO_FOLDER = {
    "VAELoader": "vae",
    "UNETLoader": "diffusion_models",
    "LoraLoaderModelOnly": "loras",
    "LoraLoader": "loras",
    "CLIPLoader": "text_encoders",
    "CheckpointLoaderSimple": "checkpoints",
    "CheckpointLoader": "checkpoints",
};

// Map input names to folder types as fallback
const INPUT_NAME_TO_FOLDER = {
    "vae_name": "vae",
    "unet_name": "diffusion_models",
    "lora_name": "loras",
    "clip_name": "text_encoders",
    "ckpt_name": "checkpoints",
    "model_name": "checkpoints",
};

function getFolderForModel(nodeType, inputName) {
    return NODE_TYPE_TO_FOLDER[nodeType] || INPUT_NAME_TO_FOLDER[inputName] || "checkpoints";
}

function createMissingModelsDialog(missingModels) {
    const dialog = document.createElement("div");
    dialog.className = "comfy-modal comfy-missing-models-dialog";
    dialog.style.cssText = `
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        background: var(--bg-color, #202020);
        border: 2px solid var(--border-color, #4a4a4a);
        border-radius: 8px;
        padding: 20px;
        max-width: 600px;
        max-height: 80vh;
        overflow-y: auto;
        z-index: 10000;
        box-shadow: 0 4px 20px rgba(0,0,0,0.5);
    `;

    const title = document.createElement("h3");
    title.textContent = "Missing Models";
    title.style.cssText = "margin: 0 0 16px 0; color: var(--fg-color, #fff); font-size: 18px;";
    dialog.appendChild(title);

    const description = document.createElement("p");
    description.textContent = "The following models are required but not found on the server. You can download them automatically:";
    description.style.cssText = "margin: 0 0 16px 0; color: var(--fg-color, #ccc); font-size: 14px;";
    dialog.appendChild(description);

    const modelsList = document.createElement("div");
    modelsList.className = "comfy-missing-models";
    modelsList.style.cssText = "margin: 0 0 16px 0;";

    for (const model of missingModels) {
        const modelItem = document.createElement("div");
        modelItem.className = "flex";
        modelItem.style.cssText = `
            display: flex;
            flex-direction: column;
            padding: 12px;
            margin-bottom: 8px;
            background: var(--comfy-input-bg, #1a1a1a);
            border: 1px solid var(--border-color, #3a3a3a);
            border-radius: 4px;
        `;

        const modelHeader = document.createElement("div");
        modelHeader.style.cssText = "display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;";

        const modelLabel = document.createElement("span");
        modelLabel.textContent = `${model.folder}/${model.filename}`;
        modelLabel.title = `${model.folder}/${model.filename}`;
        modelLabel.style.cssText = "color: var(--fg-color, #fff); font-size: 14px; font-weight: 500;";

        const downloadButton = document.createElement("button");
        downloadButton.textContent = model.url ? "Download" : "Enter URL";
        downloadButton.title = model.url || "";
        downloadButton.style.cssText = `
            padding: 6px 12px;
            background: ${model.url ? "var(--comfy-menu-bg, #3a3a3a)" : "#666"};
            color: var(--fg-color, #fff);
            border: 1px solid var(--border-color, #555);
            border-radius: 4px;
            cursor: ${model.url ? "pointer" : "default"};
            font-size: 13px;
            transition: background 0.2s;
        `;

        if (!model.url) {
            downloadButton.onclick = (e) => {
                e.preventDefault();
                e.stopPropagation();
                const url = prompt(`Enter download URL for ${model.filename}:`, "https://huggingface.co/...");
                if (url && url.trim()) {
                    model.url = url.trim();
                    downloadButton.title = model.url;
                    downloadButton.textContent = "Download";
                    downloadButton.style.background = "var(--comfy-menu-bg, #3a3a3a)";
                    downloadButton.style.cursor = "pointer";
                }
            };
        }

        const nodeInfo = document.createElement("div");
        nodeInfo.textContent = `Required by: ${model.nodeType} (${model.inputName})`;
        nodeInfo.style.cssText = "color: var(--fg-color, #888); font-size: 12px; margin-top: 4px;";

        modelHeader.appendChild(modelLabel);
        modelHeader.appendChild(downloadButton);
        modelItem.appendChild(modelHeader);
        modelItem.appendChild(nodeInfo);
        modelsList.appendChild(modelItem);
    }

    dialog.appendChild(modelsList);

    const buttonContainer = document.createElement("div");
    buttonContainer.style.cssText = "display: flex; justify-content: flex-end; gap: 8px;";

    const closeButton = document.createElement("button");
    closeButton.textContent = "Close";
    closeButton.style.cssText = `
        padding: 8px 16px;
        background: var(--comfy-menu-bg, #3a3a3a);
        color: var(--fg-color, #fff);
        border: 1px solid var(--border-color, #555);
        border-radius: 4px;
        cursor: pointer;
        font-size: 14px;
    `;
    closeButton.onclick = () => {
        document.body.removeChild(overlay);
    };

    buttonContainer.appendChild(closeButton);
    dialog.appendChild(buttonContainer);

    const overlay = document.createElement("div");
    overlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.7);
        z-index: 9999;
    `;
    overlay.onclick = () => {
        document.body.removeChild(overlay);
    };

    dialog.onclick = (e) => e.stopPropagation();
    overlay.appendChild(dialog);
    document.body.appendChild(overlay);
}

function extractMissingModels(nodeErrors) {
    const missingModels = [];

    for (const [nodeId, errors] of Object.entries(nodeErrors)) {
        const errorArray = Array.isArray(errors) ? errors : errors.errors || [];

        for (const error of errorArray) {
            if (error.type === "value_not_in_list") {
                const inputName = error.extra_info?.input_name;
                const filename = error.extra_info?.received_value;

                // Check if this is a model-related input
                if (inputName && filename && typeof filename === "string") {
                    // Get node info from the prompt to determine node type
                    const nodeType = error.node_type || "Unknown";
                    const folder = getFolderForModel(nodeType, inputName);

                    // Look up URL in known models
                    const url = KNOWN_MODEL_URLS[filename];

                    missingModels.push({
                        nodeId,
                        nodeType,
                        inputName,
                        filename,
                        folder,
                        url: url || null
                    });
                }
            }
        }
    }

    return missingModels;
}

// Store the original queuePrompt function
let originalQueuePrompt = null;

app.registerExtension({
    name: "Comfy.MissingModelsUI",
    async setup() {
        // Intercept API calls to detect validation errors
        const originalFetchApi = api.fetchApi;
        api.fetchApi = async function(route, options) {
            const response = await originalFetchApi.call(this, route, options);

            // Check if this is a prompt submission
            if (route === "/prompt" && options?.method === "POST") {
                // Clone response so we can read it
                const clonedResponse = response.clone();
                try {
                    const data = await clonedResponse.json();

                    if (data.node_errors && Object.keys(data.node_errors).length > 0) {
                        // Extract node type info from the prompt
                        const body = JSON.parse(options.body);
                        const prompt = body.prompt;

                        // Enhance errors with node type information
                        for (const [nodeId, errors] of Object.entries(data.node_errors)) {
                            const nodeData = prompt?.[nodeId];
                            if (nodeData && nodeData.class_type) {
                                const errorArray = Array.isArray(errors) ? errors : errors.errors || [];
                                for (const error of errorArray) {
                                    error.node_type = nodeData.class_type;
                                }
                            }
                        }

                        const missingModels = extractMissingModels(data.node_errors);

                        if (missingModels.length > 0) {
                            // Show dialog after a short delay to ensure UI is ready
                            setTimeout(() => {
                                createMissingModelsDialog(missingModels);
                            }, 100);
                        }
                    }
                } catch (e) {
                    // Not JSON or error parsing - ignore
                    console.warn("Failed to parse prompt response:", e);
                }
            }

            return response;
        };
    }
});
