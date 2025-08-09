# src/proxy_handlers/handler_images.py (确认此版本)

import logging
import re
from pathlib import Path
from fastapi import Request, Response
from fastapi.responses import FileResponse
import asyncio

from . import handler_autogen
import config_manager

logger = logging.getLogger(__name__)

# 只匹配UUID格式的ID
IMAGE_PATH_REGEX = re.compile(r"/Items/([a-f0-9\-]{36})/Images/(\w+)")
COVERS_DIR = Path("/app/config/images")
PLACEHOLDER_GENERATING_PATH = Path("/app/src/assets/images_placeholder/generating.jpg")

async def handle_virtual_library_image(request: Request, full_path: str) -> Response | None:
    match = IMAGE_PATH_REGEX.search(f"/{full_path}")
    if not match:
        return None

    item_id = match.group(1)
    image_type = match.group(2)

    if image_type != "Primary":
        return None

    config = config_manager.load_config()
    is_a_virtual_library = any(vlib.id == item_id for vlib in config.virtual_libraries)

    if not is_a_virtual_library:
        return None
    
    image_file = COVERS_DIR / f"{item_id}.jpg"

    if image_file.is_file():
        return FileResponse(str(image_file), media_type="image/jpeg")
    else:
        # 图片不存在，返回占位图。此时后台任务应该已经被 views_handler 触发了。
        if PLACEHOLDER_GENERATING_PATH.is_file():
            return FileResponse(str(PLACEHOLDER_GENERATING_PATH), media_type="image/jpeg")
        else:
            return Response(status_code=404)