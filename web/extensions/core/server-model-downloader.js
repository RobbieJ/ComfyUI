import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";

const HF_TOKEN_KEY = "comfy.hf_token";

function getStoredToken() {
    return localStorage.getItem(HF_TOKEN_KEY) || "";
}

function promptForToken(existingToken) {
    const token = prompt("Enter your Hugging Face access token (leave blank to skip):", existingToken || "");
    if (token === null) {
        return existingToken;
    }
    const trimmed = token.trim();
    localStorage.setItem(HF_TOKEN_KEY, trimmed);
    return trimmed;
}

async function requestDownload({ url, folder, filename, token }) {
    const payload = { url, folder, filename };
    if (token) {
        payload.huggingface_token = token;
    }
    return api.fetchApi("/models/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    });
}

function ensureProgressElement(button) {
    const listItem = button.closest("li") || button.closest(".p-listbox-item") || button.closest(".flex");
    if (!listItem) return null;
    let progress = listItem.querySelector(".comfy-server-download-progress");
    if (!progress) {
        progress = document.createElement("div");
        progress.className = "comfy-server-download-progress text-xs text-secondary";
        progress.style.marginTop = "4px";
        listItem.appendChild(progress);
    }
    return progress;
}

function formatBytes(bytes, total) {
    const formatter = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 });
    const base = 1024;
    const units = ["B", "KB", "MB", "GB"];

    const format = (value) => {
        let size = value;
        let unit = units[0];
        for (let i = 1; i < units.length && size >= base; i++) {
            size /= base;
            unit = units[i];
        }
        return `${formatter.format(size)} ${unit}`;
    };

    const formattedCurrent = format(bytes);
    if (typeof total === "number" && total > 0) {
        return `${formattedCurrent} / ${format(total)}`;
    }
    return formattedCurrent;
}

async function streamProgress(response, onUpdate) {
    const reader = response.body?.getReader();
    if (!reader) {
        throw new Error("No response body to read progress from");
    }

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
            if (!line.trim()) continue;
            let data;
            try {
                data = JSON.parse(line);
            } catch (err) {
                console.warn("Failed to parse progress update", err);
                continue;
            }
            onUpdate(data);
        }
    }

    if (buffer.trim()) {
        try {
            onUpdate(JSON.parse(buffer));
        } catch (err) {
            console.warn("Failed to parse final progress update", err);
        }
    }
}

app.registerExtension({
    name: "Comfy.ServerModelDownloader",
    setup() {
        document.addEventListener("click", async (event) => {
            const target = event.target;
            if (!(target instanceof HTMLElement)) return;

            // Handle both <button> and <a> tags
            const button = target.closest("button") || target.closest("a");
            if (!button) return;

            // Get URL from title attribute or href
            const url = button.title || button.getAttribute("href");
            if (!url) return;

            const container = target.closest(".comfy-missing-models");
            if (!container) return;

            const labelSpan = button.closest("li")?.querySelector("span[title]") || button.closest(".flex")?.querySelector("span");
            const labelText = labelSpan?.textContent?.trim();
            if (!labelText) return;

            const [folder, ...nameParts] = labelText.split("/").map((p) => p.trim());
            const filename = nameParts.join("/");
            if (!folder || !filename) return;

            const buttonText = button.textContent?.trim().toLowerCase() || "";
            if (!buttonText.startsWith("download")) return;

            // Prevent default browser download
            event.preventDefault();
            event.stopPropagation();
            const originalLabel = button.textContent;
            const progressEl = ensureProgressElement(button);
            if (progressEl) progressEl.textContent = "Starting server download...";
            button.textContent = "Downloading...";

            // Disable button/link
            if (button.tagName === "BUTTON") {
                button.disabled = true;
            } else {
                button.style.pointerEvents = "none";
                button.style.opacity = "0.5";
            }

            try {
                let token = getStoredToken();
                let response = await requestDownload({ url, folder, filename, token });

                if (response.status === 401 || response.status === 403) {
                    token = promptForToken(token);
                    response = await requestDownload({ url, folder, filename, token });
                }

                if (!response.ok) {
                    let message = response.statusText;
                    try {
                        const data = await response.json();
                        message = data?.error || message;
                    } catch (_) {
                        // ignore parse errors and fallback to status text
                    }
                    throw new Error(message);
                }

                await streamProgress(response, (update) => {
                    if (update.error) {
                        throw new Error(update.error);
                    }
                    const hasPercent = typeof update.progress === "number";
                    if (typeof update.progress === "number") {
                        const pct = Math.floor(update.progress * 100);
                        button.textContent = `Downloading ${pct}%`;
                        if (progressEl) progressEl.textContent = `Server download ${pct}%`;
                    }
                    if (typeof update.bytes === "number" && !hasPercent) {
                        const total = typeof update.total_bytes === "number" ? update.total_bytes : undefined;
                        const text = formatBytes(update.bytes, total);
                        if (button.textContent?.startsWith("Downloading")) {
                            button.textContent = `Downloading ${text}`;
                        }
                        if (progressEl) progressEl.textContent = `Downloaded ${text}`;
                    }
                    if (update.message) {
                        if (progressEl) progressEl.textContent = update.message;
                    }
                });

                button.textContent = "Downloaded";
                setTimeout(() => {
                    button.textContent = originalLabel;
                    if (progressEl) progressEl.textContent = "";
                }, 1500);
            } catch (err) {
                const message = err?.message || err;
                alert(`Server download failed: ${message}`);
                button.textContent = originalLabel;
                if (progressEl) progressEl.textContent = "";
            } finally {
                // Re-enable button/link
                if (button.tagName === "BUTTON") {
                    button.disabled = false;
                } else {
                    button.style.pointerEvents = "";
                    button.style.opacity = "";
                }
            }
        });
    }
});
