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

app.registerExtension({
    name: "Comfy.ServerModelDownloader",
    setup() {
        document.addEventListener("click", async (event) => {
            const target = event.target;
            if (!(target instanceof HTMLElement)) return;
            if (target.tagName !== "BUTTON") return;
            if (!target.title) return;

            const container = target.closest(".comfy-missing-models");
            if (!container) return;

            const labelSpan = target.closest(".flex")?.querySelector("span");
            const labelText = labelSpan?.textContent?.trim();
            if (!labelText) return;

            const [folder, ...nameParts] = labelText.split("/").map((p) => p.trim());
            const filename = nameParts.join("/");
            if (!folder || !filename) return;

            const buttonText = target.textContent?.trim().toLowerCase() || "";
            if (!buttonText.startsWith("download")) return;

            event.preventDefault();
            event.stopPropagation();

            const url = target.title;
            const originalLabel = target.textContent;
            target.textContent = "Downloading...";
            target.disabled = true;

            try {
                let token = getStoredToken();
                let response = await requestDownload({ url, folder, filename, token });

                if (response.status === 401 || response.status === 403) {
                    token = promptForToken(token);
                    response = await requestDownload({ url, folder, filename, token });
                }

                const data = await response.json();
                if (!response.ok) {
                    throw new Error(data?.error || response.statusText);
                }
                target.textContent = "Downloaded";
                setTimeout(() => {
                    target.textContent = originalLabel;
                }, 1500);
            } catch (err) {
                const message = err?.message || err;
                alert(`Server download failed: ${message}`);
                target.textContent = originalLabel;
            } finally {
                target.disabled = false;
            }
        });
    }
});
