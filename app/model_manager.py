from __future__ import annotations

import os
import base64
import json
import time
import logging
import folder_paths
import glob
import comfy.utils
import aiohttp
import hashlib
import uuid
import shutil
from aiohttp import web
from PIL import Image
from io import BytesIO
from folder_paths import map_legacy, filter_files_extensions, filter_files_content_types
from app.model_registry import get_registry


class ModelFileManager:
    def __init__(self) -> None:
        self.cache: dict[str, tuple[list[dict], dict[str, float], float]] = {}

    def get_cache(self, key: str, default=None) -> tuple[list[dict], dict[str, float], float] | None:
        return self.cache.get(key, default)

    def set_cache(self, key: str, value: tuple[list[dict], dict[str, float], float]):
        self.cache[key] = value

    def clear_cache(self):
        self.cache.clear()

    def add_routes(self, routes):
        # NOTE: This is an experiment to replace `/models`
        @routes.get("/experiment/models")
        async def get_model_folders(request):
            model_types = list(folder_paths.folder_names_and_paths.keys())
            folder_black_list = ["configs", "custom_nodes"]
            output_folders: list[dict] = []
            for folder in model_types:
                if folder in folder_black_list:
                    continue
                output_folders.append({"name": folder, "folders": folder_paths.get_folder_paths(folder)})
            return web.json_response(output_folders)

        # NOTE: This is an experiment to replace `/models/{folder}`
        @routes.get("/experiment/models/{folder}")
        async def get_all_models(request):
            folder = request.match_info.get("folder", None)
            if not folder in folder_paths.folder_names_and_paths:
                return web.Response(status=404)
            files = self.get_model_file_list(folder)
            return web.json_response(files)

        @routes.get("/experiment/models/preview/{folder}/{path_index}/{filename:.*}")
        async def get_model_preview(request):
            folder_name = request.match_info.get("folder", None)
            path_index = int(request.match_info.get("path_index", None))
            filename = request.match_info.get("filename", None)

            if not folder_name in folder_paths.folder_names_and_paths:
                return web.Response(status=404)

            folders = folder_paths.folder_names_and_paths[folder_name]
            folder = folders[0][path_index]
            full_filename = os.path.join(folder, filename)

            previews = self.get_model_previews(full_filename)
            default_preview = previews[0] if len(previews) > 0 else None
            if default_preview is None or (isinstance(default_preview, str) and not os.path.isfile(default_preview)):
                return web.Response(status=404)

            try:
                with Image.open(default_preview) as img:
                    img_bytes = BytesIO()
                    img.save(img_bytes, format="WEBP")
                    img_bytes.seek(0)
                    return web.Response(body=img_bytes.getvalue(), content_type="image/webp")
            except:
                return web.Response(status=404)

        @routes.post("/models/download")
        async def download_model(request):
            """Download model with hash verification and deduplication

            IMPORTANT: API keys (huggingface_token, civitai_api_key) are ephemeral
            and NEVER stored. They are used only for this request and immediately
            garbage collected.
            """
            body = await request.json()
            url = body.get("url")
            folder = body.get("folder")
            filename = body.get("filename")
            expected_sha256 = body.get("sha256")  # NEW: For deduplication and verification
            display_name = body.get("display_name")  # NEW: For registry metadata

            # Ephemeral API keys (NEVER logged or stored)
            huggingface_token = body.get("huggingface_token")
            civitai_api_key = body.get("civitai_api_key")

            path_index = body.get("path_index", 0)

            if not url or not folder:
                return web.json_response({"error": "Missing required fields 'url' and 'folder'"}, status=400)

            # Get registry for deduplication
            registry = get_registry()

            # Check if model already exists (deduplication)
            if expected_sha256:
                existing = registry.find_by_hash(expected_sha256)
                if existing:
                    logging.info(f"Model already exists with hash {expected_sha256[:16]}... at {existing['file_path']}")

                    # Determine if we need to create a symlink/alias
                    requested_path = os.path.join(folder, filename) if filename else None
                    if requested_path and requested_path != existing["file_path"]:
                        # Create alias in registry
                        registry.add_alias(expected_sha256, requested_path)

                        # Create symlink if file doesn't exist at requested location
                        target_folder = folder_paths.folder_names_and_paths[folder][0][path_index]
                        symlink_path = os.path.join(target_folder, filename)
                        existing_full_path = folder_paths.get_full_path_or_raise(folder, os.path.basename(existing["file_path"]))

                        if not os.path.exists(symlink_path):
                            folder_paths.create_symlink(existing_full_path, symlink_path)
                            logging.info(f"Created symlink: {symlink_path} -> {existing_full_path}")

                    return web.json_response({
                        "status": "already_exists",
                        "sha256": expected_sha256,
                        "path": existing["file_path"],
                        "size_bytes": existing["size_bytes"],
                        "message": "Model already downloaded"
                    })

            folder = map_legacy(folder)
            if folder not in folder_paths.folder_names_and_paths:
                return web.json_response({"error": f"Unknown folder '{folder}'"}, status=400)

            allowed_sources = ["https://civitai.com/", "https://huggingface.co/", "http://localhost:"]
            whitelisted_urls = {
                "https://huggingface.co/stabilityai/stable-zero123/resolve/main/stable_zero123.ckpt",
                "https://huggingface.co/TencentARC/T2I-Adapter/resolve/main/models/t2iadapter_depth_sd14v1.pth?download=true",
                "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
            }

            if url not in whitelisted_urls:
                if not any(url.startswith(source) for source in allowed_sources):
                    return web.json_response({"error": "Downloads are only allowed from civitai.com or huggingface.co."}, status=400)

            if filename:
                relative_name = filename
            else:
                relative_name = os.path.basename(url.split("?")[0])

            relative_name = relative_name.lstrip("/\\")
            normalized_relative = os.path.normpath(relative_name)
            if normalized_relative.startswith("..") or os.path.isabs(normalized_relative):
                return web.json_response({"error": "Invalid filename."}, status=400)

            sanitized_name = os.path.basename(normalized_relative)

            if url not in whitelisted_urls:
                allowed_extensions = {ext.lower() for ext in folder_paths.folder_names_and_paths[folder][1] if ext}
                if allowed_extensions and allowed_extensions != {"folder"}:
                    if not any(sanitized_name.lower().endswith(ext) for ext in allowed_extensions):
                        return web.json_response({"error": f"Only {', '.join(sorted(allowed_extensions))} downloads are allowed."}, status=400)

            available_paths = folder_paths.folder_names_and_paths[folder][0]
            try:
                path_index = int(path_index)
            except (TypeError, ValueError):
                path_index = 0
            target_folder = available_paths[path_index] if 0 <= path_index < len(available_paths) else available_paths[0]

            os.makedirs(target_folder, exist_ok=True)

            # Download to temp location first for hash verification
            temp_dir = os.path.join(folder_paths.base_path, "models", ".cache", "tmp")
            os.makedirs(temp_dir, exist_ok=True)
            temp_path = os.path.join(temp_dir, f"{uuid.uuid4()}.tmp")

            destination_path = os.path.abspath(os.path.join(target_folder, normalized_relative))

            if not destination_path.startswith(os.path.abspath(target_folder)):
                return web.json_response({"error": "Invalid filename."}, status=400)

            os.makedirs(os.path.dirname(destination_path), exist_ok=True)

            # Build headers with ephemeral authentication
            headers = {}
            download_url = url

            if huggingface_token and "huggingface.co" in url:
                headers["Authorization"] = f"Bearer {huggingface_token}"
                # Note: Token NOT logged

            if civitai_api_key and "civitai.com" in url:
                # Civitai uses API key in URL params
                if "?" in download_url:
                    download_url += f"&token={civitai_api_key}"
                else:
                    download_url += f"?token={civitai_api_key}"
                # Note: Token NOT logged

            # Log request without auth details
            logging.info(f"Download request: {filename} from {url[:50]}...")

            total_bytes = 0
            emitted_progress = 0
            last_emit_bytes = 0

            async def emit_progress(
                resp: web.StreamResponse,
                *,
                progress: float | None = None,
                error: str | None = None,
                message: str | None = None,
                bytes_written: int | None = None,
                total_length: int | None = None,
            ):
                payload = {}
                if progress is not None:
                    payload["progress"] = progress
                if error is not None:
                    payload["error"] = error
                if message is not None:
                    payload["message"] = message
                if bytes_written is not None:
                    payload["bytes"] = bytes_written
                if total_length is not None:
                    payload["total_bytes"] = total_length
                if not payload:
                    return
                await resp.write(json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n")
                await resp.drain()

            try:
                timeout = aiohttp.ClientTimeout(total=60 * 60)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    # Use download_url which may contain API key
                    async with session.get(download_url, headers=headers) as response:
                        # Handle auth errors
                        if response.status == 401:
                            return web.json_response({"error": "Authentication failed - invalid token"}, status=401)
                        elif response.status == 403:
                            return web.json_response({"error": "Access denied - check token permissions"}, status=403)
                        elif response.status != 200:
                            return web.json_response({"error": f"Download failed with status {response.status}"}, status=response.status)

                        content_length = response.headers.get("Content-Length")
                        total_length = int(content_length) if content_length and content_length.isdigit() else None

                        stream_response = web.StreamResponse(status=200)
                        stream_response.content_type = "application/x-ndjson"
                        await stream_response.prepare(request)

                        await emit_progress(
                            stream_response,
                            message=f"Downloading to {os.path.relpath(destination_path, target_folder)}",
                            total_length=total_length,
                            bytes_written=0,
                        )

                        try:
                            # Download to temp file and calculate hash
                            hasher = hashlib.sha256() if expected_sha256 else None

                            with open(temp_path, "wb") as outfile:
                                async for chunk in response.content.iter_chunked(1024 * 1024):
                                    outfile.write(chunk)
                                    total_bytes += len(chunk)

                                    # Update hash
                                    if hasher:
                                        hasher.update(chunk)

                                    if total_length:
                                        progress = min(total_bytes / total_length, 1.0)
                                        if progress - emitted_progress >= 0.01:
                                            emitted_progress = progress
                                            await emit_progress(
                                                stream_response,
                                                progress=progress,
                                                bytes_written=total_bytes,
                                                total_length=total_length,
                                            )
                                    elif total_bytes - last_emit_bytes >= 1 * 1024 * 1024:
                                        last_emit_bytes = total_bytes
                                        await emit_progress(
                                            stream_response,
                                            bytes_written=total_bytes,
                                        )

                            # Verify hash if expected
                            calculated_hash = hasher.hexdigest() if hasher else None

                            if expected_sha256 and calculated_hash != expected_sha256:
                                os.remove(temp_path)
                                await emit_progress(
                                    stream_response,
                                    error=f"Hash mismatch: expected {expected_sha256[:16]}..., got {calculated_hash[:16]}..."
                                )
                                return stream_response

                            # Check if another request downloaded this while we were downloading (race condition)
                            if calculated_hash:
                                existing = registry.find_by_hash(calculated_hash)
                                if existing:
                                    logging.info(f"Model downloaded by another request, using existing file")
                                    os.remove(temp_path)

                                    # Create symlink to existing file
                                    existing_full_path = folder_paths.get_full_path_or_raise(folder, os.path.basename(existing["file_path"]))
                                    if not os.path.exists(destination_path):
                                        folder_paths.create_symlink(existing_full_path, destination_path)
                                        registry.add_alias(calculated_hash, os.path.join(folder, normalized_relative))

                                    await emit_progress(
                                        stream_response,
                                        progress=1.0,
                                        bytes_written=total_bytes,
                                        total_length=total_length,
                                    )
                                    await stream_response.write(json.dumps({
                                        "message": "Download complete (deduplicated)",
                                        "path": destination_path,
                                        "folder": folder,
                                        "filename": normalized_relative,
                                        "sha256": calculated_hash,
                                        "deduplicated": True
                                    }, separators=(",", ":")).encode("utf-8") + b"\n")

                                    return stream_response

                            # Move from temp to final location
                            shutil.move(temp_path, destination_path)

                            # Register in database (WITHOUT any auth keys)
                            if calculated_hash:
                                # Strip query params from URL (may contain keys)
                                clean_url = url.split("?")[0]

                                registry.add_model(
                                    sha256=calculated_hash,
                                    file_path=os.path.join(folder, normalized_relative),
                                    size_bytes=total_bytes,
                                    source_url=clean_url,
                                    metadata={
                                        "filename": normalized_relative,
                                        "folder": folder,
                                        "display_name": display_name or normalized_relative
                                    }
                                )
                                logging.info(f"Registered model: {normalized_relative} (hash: {calculated_hash[:16]}...)")

                            await emit_progress(
                                stream_response,
                                progress=1.0,
                                bytes_written=total_bytes,
                                total_length=total_length,
                            )
                            await stream_response.write(json.dumps({
                                "message": "Download complete",
                                "path": destination_path,
                                "folder": folder,
                                "filename": normalized_relative,
                                "sha256": calculated_hash,
                                "size_bytes": total_bytes
                            }, separators=(",", ":")).encode("utf-8") + b"\n")
                        except Exception as e:
                            logging.exception("Failed to download model")
                            if os.path.exists(temp_path):
                                try:
                                    os.remove(temp_path)
                                except OSError:
                                    pass
                            if os.path.exists(destination_path):
                                try:
                                    os.remove(destination_path)
                                except OSError:
                                    pass
                            await emit_progress(stream_response, error=str(e))
                        finally:
                            await stream_response.write_eof()

                        return stream_response
            except Exception as e:
                logging.exception("Failed to download model")
                return web.json_response({"error": str(e)}, status=500)
            finally:
                # Ephemeral keys are garbage collected here (never stored)
                pass

        @routes.post("/models/check-dependencies")
        async def check_dependencies(request):
            """Check which models from workflow dependencies are missing

            Returns breakdown of existing vs missing models with deduplication info
            """
            body = await request.json()
            dependencies = body.get("dependencies", {})

            if not dependencies:
                return web.json_response({"error": "No dependencies provided"}, status=400)

            registry = get_registry()

            result = {
                "missing": [],
                "existing": [],
                "total_download_size": 0,
                "total_saved_size": 0
            }

            # Process all model types
            for model_type in ["checkpoints", "loras", "vae", "controlnet", "upscale_models",
                             "text_encoders", "diffusion_models", "clip_vision", "embeddings"]:
                models = dependencies.get(model_type, [])

                for model in models:
                    sha256 = model.get("sha256")
                    filename = model.get("filename")
                    size = model.get("size", 0)
                    urls = model.get("urls", [])
                    requires_auth = model.get("requires_auth", False)
                    auth_provider = model.get("auth_provider")

                    if not sha256 or not filename:
                        continue

                    # Check if model exists in registry
                    existing = registry.find_by_hash(sha256)

                    if existing:
                        result["existing"].append({
                            "filename": filename,
                            "exists_at": existing["file_path"],
                            "type": model_type,
                            "sha256": sha256,
                            "size": existing["size_bytes"],
                            "action": "symlink" if existing["file_path"] != os.path.join(model_type, filename) else "use_existing"
                        })
                        result["total_saved_size"] += existing["size_bytes"]
                    else:
                        result["missing"].append({
                            "filename": filename,
                            "type": model_type,
                            "sha256": sha256,
                            "size": size,
                            "urls": urls,
                            "requires_auth": requires_auth,
                            "auth_provider": auth_provider,
                            "display_name": model.get("display_name", filename)
                        })
                        result["total_download_size"] += size

            return web.json_response(result)

    def get_model_file_list(self, folder_name: str):
        folder_name = map_legacy(folder_name)
        folders = folder_paths.folder_names_and_paths[folder_name]
        output_list: list[dict] = []

        for index, folder in enumerate(folders[0]):
            if not os.path.isdir(folder):
                continue
            out = self.cache_model_file_list_(folder)
            if out is None:
                out = self.recursive_search_models_(folder, index)
                self.set_cache(folder, out)
            output_list.extend(out[0])

        return output_list

    def cache_model_file_list_(self, folder: str):
        model_file_list_cache = self.get_cache(folder)

        if model_file_list_cache is None:
            return None
        if not os.path.isdir(folder):
            return None
        if os.path.getmtime(folder) != model_file_list_cache[1]:
            return None
        for x in model_file_list_cache[1]:
            time_modified = model_file_list_cache[1][x]
            folder = x
            if os.path.getmtime(folder) != time_modified:
                return None

        return model_file_list_cache

    def recursive_search_models_(self, directory: str, pathIndex: int) -> tuple[list[str], dict[str, float], float]:
        if not os.path.isdir(directory):
            return [], {}, time.perf_counter()

        excluded_dir_names = [".git"]
        # TODO use settings
        include_hidden_files = False

        result: list[str] = []
        dirs: dict[str, float] = {}

        for dirpath, subdirs, filenames in os.walk(directory, followlinks=True, topdown=True):
            subdirs[:] = [d for d in subdirs if d not in excluded_dir_names]
            if not include_hidden_files:
                subdirs[:] = [d for d in subdirs if not d.startswith(".")]
                filenames = [f for f in filenames if not f.startswith(".")]

            filenames = filter_files_extensions(filenames, folder_paths.supported_pt_extensions)

            for file_name in filenames:
                try:
                    full_path = os.path.join(dirpath, file_name)
                    relative_path = os.path.relpath(full_path, directory)

                    # Get file metadata
                    file_info = {
                        "name": relative_path,
                        "pathIndex": pathIndex,
                        "modified": os.path.getmtime(full_path),  # Add modification time
                        "created": os.path.getctime(full_path),   # Add creation time
                        "size": os.path.getsize(full_path)        # Add file size
                    }
                    result.append(file_info)

                except Exception as e:
                    logging.warning(f"Warning: Unable to access {file_name}. Error: {e}. Skipping this file.")
                    continue

            for d in subdirs:
                path: str = os.path.join(dirpath, d)
                try:
                    dirs[path] = os.path.getmtime(path)
                except FileNotFoundError:
                    logging.warning(f"Warning: Unable to access {path}. Skipping this path.")
                    continue

        return result, dirs, time.perf_counter()

    def get_model_previews(self, filepath: str) -> list[str | BytesIO]:
        dirname = os.path.dirname(filepath)

        if not os.path.exists(dirname):
            return []

        basename = os.path.splitext(filepath)[0]
        match_files = glob.glob(f"{basename}.*", recursive=False)
        image_files = filter_files_content_types(match_files, "image")
        safetensors_file = next(filter(lambda x: x.endswith(".safetensors"), match_files), None)
        safetensors_metadata = {}

        result: list[str | BytesIO] = []

        for filename in image_files:
            _basename = os.path.splitext(filename)[0]
            if _basename == basename:
                result.append(filename)
            if _basename == f"{basename}.preview":
                result.append(filename)

        if safetensors_file:
            safetensors_filepath = os.path.join(dirname, safetensors_file)
            header = comfy.utils.safetensors_header(safetensors_filepath, max_size=8*1024*1024)
            if header:
                safetensors_metadata = json.loads(header)
        safetensors_images = safetensors_metadata.get("__metadata__", {}).get("ssmd_cover_images", None)
        if safetensors_images:
            safetensors_images = json.loads(safetensors_images)
            for image in safetensors_images:
                result.append(BytesIO(base64.b64decode(image)))

        return result

    def __exit__(self, exc_type, exc_value, traceback):
        self.clear_cache()
