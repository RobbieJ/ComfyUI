/**
 * Workflow Dependency Manager
 *
 * Handles automatic detection and download of required models for workflows.
 * Features:
 * - Hash-based deduplication (same model never downloaded twice)
 * - Ephemeral API key management (keys never stored)
 * - Progress tracking with detailed feedback
 * - Support for HuggingFace and Civitai authentication
 */

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

/**
 * Ephemeral Key Manager
 * Manages API keys in-memory only, never persisting them
 */
class EphemeralKeyManager {
    constructor() {
        // In-memory only, NEVER localStorage or any persistent storage
        this.sessionKeys = new Map(); // { "huggingface": "hf_xxxx", "civitai": "cvt_xxxx" }
        this.keyTimers = new Map(); // Auto-clear timers
    }

    /**
     * Set an API key for a provider
     * @param {string} provider - Provider name (e.g., "huggingface", "civitai")
     * @param {string} key - API key
     */
    setKey(provider, key) {
        this.sessionKeys.set(provider, key);

        // Clear existing timer
        if (this.keyTimers.has(provider)) {
            clearTimeout(this.keyTimers.get(provider));
        }

        // Auto-clear after 1 hour of inactivity
        const timer = setTimeout(() => {
            this.sessionKeys.delete(provider);
            this.keyTimers.delete(provider);
            console.log(`[DependencyManager] ${provider} key auto-cleared after timeout`);
        }, 60 * 60 * 1000);

        this.keyTimers.set(provider, timer);
    }

    /**
     * Get API key for a provider
     * @param {string} provider - Provider name
     * @returns {string|null} API key or null if not set
     */
    getKey(provider) {
        return this.sessionKeys.get(provider) || null;
    }

    /**
     * Clear all stored keys
     */
    clearAll() {
        this.sessionKeys.clear();

        // Clear all timers
        for (const timer of this.keyTimers.values()) {
            clearTimeout(timer);
        }
        this.keyTimers.clear();

        console.log("[DependencyManager] All API keys cleared");
    }

    /**
     * Check if key exists for provider
     * @param {string} provider - Provider name
     * @returns {boolean} True if key is set
     */
    hasKey(provider) {
        return this.sessionKeys.has(provider);
    }
}

/**
 * Format bytes to human-readable string
 * @param {number} bytes - Number of bytes
 * @returns {string} Formatted string (e.g., "1.5 GB")
 */
function formatBytes(bytes) {
    if (bytes === 0) return "0 B";

    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB", "TB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));

    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
}

/**
 * Workflow Dependency Manager
 */
class WorkflowDependencyManager {
    constructor() {
        this.keyManager = new EphemeralKeyManager();

        // Clear keys on page unload
        window.addEventListener("beforeunload", () => {
            this.keyManager.clearAll();
        });
    }

    /**
     * Parse workflow JSON to extract dependencies
     * @param {Object} workflow - Workflow JSON
     * @returns {Object|null} Dependencies object or null if not found
     */
    parseWorkflowDependencies(workflow) {
        // Check if workflow has dependencies section
        if (workflow.dependencies) {
            return workflow.dependencies;
        }

        // Check nested structure
        if (workflow.workflow && workflow.workflow.dependencies) {
            return workflow.workflow.dependencies;
        }

        return null;
    }

    /**
     * Check which dependencies are missing
     * @param {Object} dependencies - Dependencies object from workflow
     * @returns {Promise<Object>} Result with missing and existing models
     */
    async checkDependencies(dependencies) {
        try {
            const response = await api.fetchApi("/models/check-dependencies", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ dependencies })
            });

            if (!response.ok) {
                throw new Error(`Failed to check dependencies: ${response.statusText}`);
            }

            return await response.json();
        } catch (error) {
            console.error("[DependencyManager] Error checking dependencies:", error);
            throw error;
        }
    }

    /**
     * Prompt user for API key
     * @param {string} provider - Provider name ("huggingface" or "civitai")
     * @returns {Promise<string|null>} API key or null if cancelled
     */
    async promptForKey(provider) {
        const messages = {
            huggingface: {
                title: "HuggingFace Authentication",
                message: "Some models require a HuggingFace token to download.\n\nYour token will NOT be saved and will be cleared after download.",
                helpLink: "https://huggingface.co/settings/tokens",
                placeholder: "hf_..."
            },
            civitai: {
                title: "Civitai Authentication",
                message: "Some models require a Civitai API key to download.\n\nYour key will NOT be saved and will be cleared after download.",
                helpLink: "https://civitai.com/user/account",
                placeholder: "Enter Civitai API key..."
            }
        };

        const config = messages[provider];
        if (!config) {
            console.error(`[DependencyManager] Unknown provider: ${provider}`);
            return null;
        }

        return new Promise((resolve) => {
            // Create modal dialog
            const dialog = document.createElement("dialog");
            dialog.style.cssText = `
                padding: 0;
                border: none;
                border-radius: 8px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                max-width: 500px;
                width: 90%;
            `;

            dialog.innerHTML = `
                <div style="padding: 20px;">
                    <h3 style="margin-top: 0;">${config.title}</h3>
                    <p style="white-space: pre-line;">${config.message}</p>
                    <input
                        type="password"
                        id="api-key-input"
                        placeholder="${config.placeholder}"
                        style="width: 100%; padding: 8px; margin: 10px 0; box-sizing: border-box; font-family: monospace;"
                    />
                    <div style="margin: 10px 0;">
                        <a href="${config.helpLink}" target="_blank" style="color: #0066cc;">
                            Get ${provider} token
                        </a>
                    </div>
                    <div style="display: flex; gap: 10px; justify-content: flex-end; margin-top: 20px;">
                        <button id="cancel-btn" style="padding: 8px 16px;">Cancel</button>
                        <button id="ok-btn" style="padding: 8px 16px; background: #0066cc; color: white; border: none; border-radius: 4px; cursor: pointer;">
                            OK
                        </button>
                    </div>
                </div>
            `;

            document.body.appendChild(dialog);
            dialog.showModal();

            const input = dialog.querySelector("#api-key-input");
            const okBtn = dialog.querySelector("#ok-btn");
            const cancelBtn = dialog.querySelector("#cancel-btn");

            const cleanup = () => {
                dialog.close();
                document.body.removeChild(dialog);
            };

            okBtn.onclick = () => {
                const key = input.value.trim();
                cleanup();
                resolve(key || null);
            };

            cancelBtn.onclick = () => {
                cleanup();
                resolve(null);
            };

            // Enter key submits
            input.addEventListener("keypress", (e) => {
                if (e.key === "Enter") {
                    okBtn.click();
                }
            });

            input.focus();
        });
    }

    /**
     * Download a single model
     * @param {Object} model - Model info
     * @param {Function} onProgress - Progress callback
     * @returns {Promise<Object>} Download result
     */
    async downloadModel(model, onProgress) {
        const payload = {
            url: model.urls[0],
            folder: model.type,
            filename: model.filename,
            sha256: model.sha256,
            display_name: model.display_name
        };

        // Add ephemeral key if needed (NOT stored in payload permanently)
        if (model.requires_auth && model.auth_provider) {
            const key = this.keyManager.getKey(model.auth_provider);
            if (key) {
                if (model.auth_provider === "huggingface") {
                    payload.huggingface_token = key;
                } else if (model.auth_provider === "civitai") {
                    payload.civitai_api_key = key;
                }
            }
        }

        try {
            const response = await api.fetchApi("/models/download", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || `Download failed: ${response.statusText}`);
            }

            // Stream NDJSON progress updates
            const reader = response.body?.getReader();
            const decoder = new TextDecoder();
            let buffer = "";
            let lastProgress = {};

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n");
                buffer = lines.pop() ?? "";

                for (const line of lines) {
                    if (!line.trim()) continue;

                    const data = JSON.parse(line);

                    // Check for error
                    if (data.error) {
                        throw new Error(data.error);
                    }

                    // Update progress
                    if (data.progress !== undefined || data.bytes !== undefined) {
                        lastProgress = data;
                        if (onProgress) {
                            onProgress(data);
                        }
                    }

                    // Check for completion
                    if (data.message && data.message.includes("complete")) {
                        return {
                            success: true,
                            ...data
                        };
                    }
                }
            }

            return {
                success: true,
                ...lastProgress
            };
        } catch (error) {
            console.error(`[DependencyManager] Error downloading ${model.filename}:`, error);
            throw error;
        }
    }

    /**
     * Show download prompt and handle downloads
     * @param {Object} checkResult - Result from checkDependencies
     * @returns {Promise<boolean>} True if download completed, false if cancelled
     */
    async showDownloadPrompt(checkResult) {
        const { missing, existing, total_download_size, total_saved_size } = checkResult;

        if (missing.length === 0) {
            // All models available
            console.log("[DependencyManager] All required models already available");
            return true;
        }

        // Create download prompt dialog
        return new Promise((resolve) => {
            const dialog = document.createElement("dialog");
            dialog.style.cssText = `
                padding: 0;
                border: none;
                border-radius: 8px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                max-width: 600px;
                width: 90%;
            `;

            const existingHtml = existing.length > 0 ? `
                <div style="margin: 15px 0; padding: 10px; background: #e8f5e9; border-radius: 4px;">
                    <strong>✓ Already available (${existing.length} files, saved ${formatBytes(total_saved_size)}):</strong>
                    <ul style="margin: 5px 0; padding-left: 20px;">
                        ${existing.slice(0, 5).map(m => `<li>${m.filename}</li>`).join("")}
                        ${existing.length > 5 ? `<li><em>...and ${existing.length - 5} more</em></li>` : ""}
                    </ul>
                </div>
            ` : "";

            dialog.innerHTML = `
                <div style="padding: 20px;">
                    <h3 style="margin-top: 0;">Download Required Models?</h3>

                    <div style="margin: 15px 0; padding: 10px; background: #fff3cd; border-radius: 4px;">
                        <strong>Missing (${missing.length} files, ${formatBytes(total_download_size)}):</strong>
                        <ul style="margin: 5px 0; padding-left: 20px;">
                            ${missing.slice(0, 5).map(m =>
                                `<li>${m.display_name || m.filename} (${formatBytes(m.size)})${m.requires_auth ? ' 🔒' : ''}</li>`
                            ).join("")}
                            ${missing.length > 5 ? `<li><em>...and ${missing.length - 5} more</em></li>` : ""}
                        </ul>
                    </div>

                    ${existingHtml}

                    <div id="progress-container" style="display: none; margin: 15px 0;">
                        <div style="margin-bottom: 10px;">
                            <div id="progress-text">Preparing download...</div>
                            <div style="background: #e0e0e0; height: 20px; border-radius: 4px; overflow: hidden; margin-top: 5px;">
                                <div id="progress-bar" style="background: #4caf50; height: 100%; width: 0%; transition: width 0.3s;"></div>
                            </div>
                        </div>
                        <div id="progress-details" style="font-size: 12px; color: #666;"></div>
                    </div>

                    <div id="button-container" style="display: flex; gap: 10px; justify-content: flex-end; margin-top: 20px;">
                        <button id="cancel-btn" style="padding: 8px 16px;">Cancel</button>
                        <button id="download-btn" style="padding: 8px 16px; background: #0066cc; color: white; border: none; border-radius: 4px; cursor: pointer;">
                            Download ${formatBytes(total_download_size)}
                        </button>
                    </div>
                </div>
            `;

            document.body.appendChild(dialog);
            dialog.showModal();

            const cancelBtn = dialog.querySelector("#cancel-btn");
            const downloadBtn = dialog.querySelector("#download-btn");
            const progressContainer = dialog.querySelector("#progress-container");
            const progressBar = dialog.querySelector("#progress-bar");
            const progressText = dialog.querySelector("#progress-text");
            const progressDetails = dialog.querySelector("#progress-details");
            const buttonContainer = dialog.querySelector("#button-container");

            const cleanup = () => {
                dialog.close();
                document.body.removeChild(dialog);
            };

            cancelBtn.onclick = () => {
                cleanup();
                resolve(false);
            };

            downloadBtn.onclick = async () => {
                try {
                    // Hide buttons, show progress
                    buttonContainer.style.display = "none";
                    progressContainer.style.display = "block";

                    // Check which auth providers are needed
                    const authProviders = new Set();
                    for (const model of missing) {
                        if (model.requires_auth && model.auth_provider) {
                            authProviders.add(model.auth_provider);
                        }
                    }

                    // Prompt for missing keys
                    for (const provider of authProviders) {
                        if (!this.keyManager.hasKey(provider)) {
                            progressText.textContent = `Waiting for ${provider} authentication...`;

                            const key = await this.promptForKey(provider);
                            if (!key) {
                                cleanup();
                                resolve(false);
                                return;
                            }
                            this.keyManager.setKey(provider, key);
                        }
                    }

                    // Download models
                    let completedBytes = 0;
                    const totalBytes = total_download_size;

                    for (let i = 0; i < missing.length; i++) {
                        const model = missing[i];

                        progressText.textContent = `Downloading ${model.display_name || model.filename} (${i + 1}/${missing.length})`;

                        await this.downloadModel(model, (progress) => {
                            if (progress.bytes !== undefined && totalBytes > 0) {
                                const currentTotal = completedBytes + progress.bytes;
                                const percent = (currentTotal / totalBytes) * 100;
                                progressBar.style.width = `${percent}%`;
                                progressDetails.textContent = `${formatBytes(currentTotal)} / ${formatBytes(totalBytes)}`;
                            }
                        });

                        completedBytes += model.size;
                    }

                    // Clear keys after download
                    this.keyManager.clearAll();

                    progressText.textContent = "✓ Download complete!";
                    progressBar.style.width = "100%";
                    progressDetails.textContent = `Downloaded ${formatBytes(totalBytes)}`;

                    setTimeout(() => {
                        cleanup();
                        resolve(true);
                    }, 1500);
                } catch (error) {
                    console.error("[DependencyManager] Download error:", error);
                    progressText.textContent = `Error: ${error.message}`;
                    progressBar.style.background = "#f44336";

                    // Show close button
                    buttonContainer.style.display = "flex";
                    downloadBtn.style.display = "none";
                    cancelBtn.textContent = "Close";
                }
            };
        });
    }

    /**
     * Process workflow dependencies
     * @param {Object} workflow - Workflow JSON
     * @returns {Promise<boolean>} True if ready to run, false otherwise
     */
    async processWorkflow(workflow) {
        const dependencies = this.parseWorkflowDependencies(workflow);

        if (!dependencies) {
            // No dependencies section, workflow can run
            return true;
        }

        console.log("[DependencyManager] Checking workflow dependencies...");

        const checkResult = await this.checkDependencies(dependencies);

        if (checkResult.missing.length === 0) {
            console.log("[DependencyManager] All required models available");
            return true;
        }

        console.log(`[DependencyManager] Found ${checkResult.missing.length} missing models`);

        return await this.showDownloadPrompt(checkResult);
    }
}

// Global instance
const dependencyManager = new WorkflowDependencyManager();

// Export for use in other modules
window.workflowDependencyManager = dependencyManager;

// Hook into workflow load
app.registerExtension({
    name: "Comfy.WorkflowDependencyManager",

    async setup() {
        console.log("[DependencyManager] Extension loaded");

        // Note: Auto-checking on workflow load would require hooking into
        // the workflow loading mechanism. For now, this can be manually
        // triggered or called from a menu option.
    },

    // Expose API for manual checking
    async loadWorkflowFile(workflow) {
        // Called when loading a workflow file
        // Can check dependencies here if desired
        console.log("[DependencyManager] Workflow loaded, checking dependencies...");

        try {
            await dependencyManager.processWorkflow(workflow);
        } catch (error) {
            console.error("[DependencyManager] Error processing workflow:", error);
        }
    }
});

export { dependencyManager, formatBytes };
