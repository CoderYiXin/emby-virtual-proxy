# src/proxy_handlers/handler_autogen.py (最终身份修正版)

import asyncio
import logging
import shutil
import random
import base64
import os
import hashlib
import time
from pathlib import Path
from io import BytesIO
from PIL import Image
import aiohttp
import importlib

import config_manager
# from cover_generator import style_multi_1 # 改为动态导入

logger = logging.getLogger(__name__)

GENERATION_IN_PROGRESS = set()

# 【【【 核心修正1：函数签名改变，接收用户ID和Token 】】】
async def generate_poster_in_background(library_id: str, user_id: str, api_key: str):
    """
    在后台异步生成海报。此版本使用触发时传入的身份信息来确保权限正确。
    """
    if library_id in GENERATION_IN_PROGRESS:
        return

    GENERATION_IN_PROGRESS.add(library_id)
    logger.info(f"✅ 已启动库 {library_id} (用户: {user_id}) 的封面自动生成后台任务。")
    
    config = None
    temp_dir = None
    
    try:
        config = config_manager.load_config()
        vlib = next((v for v in config.virtual_libraries if v.id == library_id), None)
        if not vlib:
            logger.error(f"后台任务：配置中未找到 vlib {library_id}。")
            return

        # --- 不再需要自己获取用户ID，直接使用传入的 ---
        
        # --- 2. 通过内部请求调用 proxy-core 自身来获取项目 ---
        internal_proxy_url = f"http://localhost:8999/emby/Users/{user_id}/Items"
        
        # 使用传入的、保证正确的 api_key
        params = {
            "ParentId": library_id,
            "Limit": 100,
            "Fields": "ImageTags,ProviderIds", # 添加ProviderIds以备不时之需
            "Recursive": "true",
            "IncludeItemTypes": "Movie,Series,Video",
            "X-Emby-Token": api_key,
            "X-Emby-Client": "Proxy (AutoGen)",
            "X-Emby-Device-Name": "ProxyAutoGen",
            "X-Emby-Device-Id": "proxy-autogen-device-id",
            "X-Emby-Client-Version": "4.8.11.0",
        }
        
        internal_headers = {
            'Accept': 'application/json',
            'X-Emby-Authorization': f'Emby UserId="{user_id}", Client="Proxy (AutoGen)", Device="ProxyAutoGen", DeviceId="proxy-autogen-device-id", Version="4.8.11.0", Token="{api_key}"'
        }
        
        items = []
        logger.info(f"后台任务：正在向内部代理 {internal_proxy_url} 请求项目...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(internal_proxy_url, params=params, headers=internal_headers, timeout=60) as response:
                    if response.status == 200:
                        items_dict = await response.json()
                        if isinstance(items_dict, dict): items = items_dict.get("Items", [])
                    else:
                        logger.error(f"后台任务：内部代理请求失败，状态码: {response.status}, 响应: {await response.text()}")
        except Exception as e:
            logger.error(f"后台任务连接内部代理时出错: {e}")

        if not items:
            logger.warning(f"后台任务：根据虚拟库 '{vlib.name}' 的规则，未从代理获取到任何项目。")
            return

        items_with_images = [item for item in items if item.get("ImageTags", {}).get("Primary")]
        if not items_with_images:
            logger.warning(f"后台任务：获取到的 {len(items)} 个项目中，没有带主图的项目，无法为库 '{vlib.name}' 生成封面。")
            return
            
        selected_items = random.sample(items_with_images, min(9, len(items_with_images)))
        
        # --- 3. 下载图片 ---
        output_dir = Path("/app/config/images/")
        output_dir.mkdir(exist_ok=True)
        temp_dir = output_dir / f"temp_autogen_{library_id}"
        temp_dir.mkdir(exist_ok=True)

        async def download_image(session, item, index):
            image_url = f"{config.emby_url.rstrip('/')}/emby/Items/{item['Id']}/Images/Primary"
            download_headers = {'X-Emby-Token': api_key} # 使用正确的api_key
            try:
                async with session.get(image_url, headers=download_headers, timeout=20) as response:
                    if response.status == 200:
                        with open(temp_dir / f"{index}.jpg", "wb") as f: f.write(await response.read())
                        return True
            except Exception: return False
            return False

        async with aiohttp.ClientSession() as session:
            tasks = [download_image(session, item, i + 1) for i, item in enumerate(selected_items)]
            results = await asyncio.gather(*tasks)

        if not any(results):
            logger.error(f"后台任务：为库 {library_id} 下载封面素材失败。")
            return

        # --- 动态调用所选的默认样式 ---
        style_name = config.default_cover_style
        logger.info(f"后台任务：使用默认样式 '{style_name}' 为 '{vlib.name}' 生成封面...")

        try:
            style_module = importlib.import_module(f"cover_generator.{style_name}")
            create_function = getattr(style_module, f"create_{style_name}")
        except (ImportError, AttributeError) as e:
            logger.error(f"后台任务：无法加载样式 '{style_name}': {e}")
            return

        # 检查自定义字体路径，如果未设置则使用默认值
        zh_font_path = config.custom_zh_font_path or "/app/src/assets/fonts/multi_1_zh.ttf"
        en_font_path = config.custom_en_font_path or "/app/src/assets/fonts/multi_1_en.otf"
        
        kwargs = {
            "title": (vlib.name, ""),
            "font_path": (zh_font_path, en_font_path)
        }

        if style_name == 'style_multi_1':
            kwargs['library_dir'] = str(temp_dir)
        elif style_name in ['style_single_1', 'style_single_2']:
            main_image_path = temp_dir / "1.jpg"
            if not main_image_path.is_file():
                logger.error(f"后台任务：无法找到用于单图模式的主素材图片 (1.jpg)。")
                return
            kwargs['image_path'] = str(main_image_path)
        else:
            logger.error(f"后台任务：未知的默认样式名称: {style_name}")
            return

        res_b64 = create_function(**kwargs)
        if not res_b64:
            logger.error(f"后台任务：为库 {library_id} 调用封面生成函数失败。")
            return

        image_data = base64.b64decode(res_b64)
        img = Image.open(BytesIO(image_data)).convert("RGB")
        final_path = output_dir / f"{library_id}.jpg"
        img.save(final_path, "JPEG", quality=90)
        
        new_image_tag = hashlib.md5(str(time.time()).encode()).hexdigest()
        current_config = config_manager.load_config()
        vlib_found_and_updated = False
        for vlib_in_config in current_config.virtual_libraries:
            if vlib_in_config.id == library_id:
                vlib_in_config.image_tag = new_image_tag
                vlib_found_and_updated = True
                break
        
        if vlib_found_and_updated:
            config_manager.save_config(current_config)
            logger.info(f"🎉 封面自动生成成功！已保存至 {final_path} 并更新了 config.json 的 ImageTag 为 {new_image_tag}")
        else:
            logger.error(f"自动生成封面后，无法在 config.json 中找到虚拟库 {library_id} 以更新 ImageTag。")

    except Exception as e:
        logger.error(f"封面自动生成后台任务发生未知错误: {e}", exc_info=True)
    finally:
        if temp_dir and temp_dir.exists():
            shutil.rmtree(temp_dir)
        GENERATION_IN_PROGRESS.remove(library_id)
        logger.info(f"后台任务结束，已释放库 {library_id} 的生成锁。")
