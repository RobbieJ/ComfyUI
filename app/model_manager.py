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
from aiohttp import web
from PIL import Image
from io import BytesIO
from folder_paths import map_legacy, filter_files_extensions, filter_files_content_types


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
            body = await request.json()
            url = body.get("url")
            folder = body.get("folder")
            filename = body.get("filename")
            huggingface_token = body.get("huggingface_token")
            path_index = body.get("path_index", 0)

            if not url or not folder:
                return web.json_response({"error": "Missing required fields 'url' and 'folder'"}, status=400)

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
            destination_path = os.path.abspath(os.path.join(target_folder, normalized_relative))

            if not destination_path.startswith(os.path.abspath(target_folder)):
                return web.json_response({"error": "Invalid filename."}, status=400)

            os.makedirs(os.path.dirname(destination_path), exist_ok=True)

            headers = {}
            if huggingface_token:
                headers["Authorization"] = f"Bearer {huggingface_token}"

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers) as response:
                        if response.status != 200:
                            return web.json_response({"error": f"Download failed with status {response.status}"}, status=response.status)

                        with open(destination_path, "wb") as outfile:
                            async for chunk in response.content.iter_chunked(1024 * 1024):
                                outfile.write(chunk)
            except Exception as e:
                logging.exception("Failed to download model")
                return web.json_response({"error": str(e)}, status=500)

            return web.json_response({
                "message": "Download complete",
                "path": destination_path,
                "folder": folder,
                "filename": normalized_relative,
            })

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
