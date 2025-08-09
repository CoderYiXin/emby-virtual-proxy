# src/proxy_handlers/handler_latest.py (最终修正版)

import logging
import json
from fastapi import Request, Response
from aiohttp import ClientSession
from models import AppConfig
from typing import List, Dict
import asyncio
from pathlib import Path

from . import handler_merger
# 【新增】导入后台生成处理器
from . import handler_autogen
from ._filter_translator import translate_rules
from .handler_items import _apply_post_filter

logger = logging.getLogger(__name__)

# 【新增】定义封面存储路径
COVERS_DIR = Path("/app/config/images")

async def handle_home_latest_items(
    request: Request,
    full_path: str,
    method: str,
    real_emby_url: str,
    session: ClientSession,
    config: AppConfig
) -> Response | None:
    if "/Items/Latest" not in full_path or method != "GET":
        return None

    params = request.query_params
    parent_id = params.get("ParentId")
    if not parent_id: return None

    found_vlib = next((vlib for vlib in config.virtual_libraries if vlib.id == parent_id), None)
    if not found_vlib: return None

    logger.info(f"HOME_LATEST_HANDLER: Intercepting request for latest items in vlib '{found_vlib.name}'.")

    # --- 【【【 核心修正：在这里也添加封面自动生成触发器 】】】 ---
    image_file = COVERS_DIR / f"{found_vlib.id}.jpg"
    if not image_file.is_file():
        logger.info(f"首页最新项目：发现虚拟库 '{found_vlib.name}' ({found_vlib.id}) 缺少封面，触发自动生成。")
        if found_vlib.id not in handler_autogen.GENERATION_IN_PROGRESS:
            # 从当前请求中提取必要信息
            user_id = params.get("UserId")
            api_key = params.get("X-Emby-Token") or config.emby_api_key

            if user_id and api_key:
                 asyncio.create_task(handler_autogen.generate_poster_in_background(found_vlib.id, user_id, api_key))
            else:
                logger.warning(f"无法为库 {found_vlib.id} 触发后台任务，因为缺少 UserId 或 ApiKey。")
    # --- 【【【 修正结束 】】】 ---

    # user_id 的获取逻辑后面已经有了，这里不需要重复
    user_id = params.get("UserId")
    if not user_id:
        path_parts_for_user = full_path.split('/')
        if 'Users' in path_parts_for_user:
            try:
                user_id_index = path_parts_for_user.index('Users') + 1
                if user_id_index < len(path_parts_for_user): user_id = path_parts_for_user[user_id_index]
            except (ValueError, IndexError): pass
    if not user_id: return None

    new_params = {}
    safe_params_to_inherit = ["Fields", "IncludeItemTypes", "EnableImageTypes", "ImageTypeLimit", "X-Emby-Token", "EnableUserData", "Limit"]
    for key in safe_params_to_inherit:
        if key in params: new_params[key] = params[key]

    new_params["SortBy"] = "DateCreated"
    new_params["SortOrder"] = "Descending"
    new_params["Recursive"] = "true"
    
    post_filter_rules = []
    if found_vlib.advanced_filter_id:
        adv_filter = next((f for f in config.advanced_filters if f.id == found_vlib.advanced_filter_id), None)
        if adv_filter:
            emby_native_params, post_filter_rules = translate_rules(adv_filter.rules)
            new_params.update(emby_native_params)
            logger.info(f"HOME_LATEST_HANDLER: 应用了 {len(emby_native_params)} 条原生筛选规则。")
    
    if post_filter_rules or found_vlib.merge_by_tmdb_id:
        fetch_limit = 200
        client_limit = int(params.get("Limit", 20))
        try: fetch_limit = min(max(client_limit * 10, 50), 200)
        except (ValueError, TypeError): pass
        new_params["Limit"] = fetch_limit
        logger.info(f"HOME_LATEST_HANDLER: 后筛选或合并需要，已将获取限制提高到 {fetch_limit}。")

    required_fields = set(["ProviderIds"])
    if post_filter_rules:
        for rule in post_filter_rules: required_fields.add(rule.field.split('.')[0])
    if required_fields:
        current_fields = set(new_params.get("Fields", "").split(','))
        current_fields.discard('')
        current_fields.update(required_fields)
        new_params["Fields"] = ",".join(sorted(list(current_fields)))

    resource_map = {"collection": "CollectionIds", "tag": "TagIds", "person": "PersonIds", "genre": "GenreIds", "studio": "StudioIds"}
    if found_vlib.resource_type in resource_map:
        new_params[resource_map[found_vlib.resource_type]] = found_vlib.resource_id

    # 采用白名单策略转发所有必要的请求头，确保认证信息不丢失
    headers_to_forward = {
        k: v for k, v in request.headers.items() 
        if k.lower() in [
            'accept', 'accept-language', 'user-agent',
            'x-emby-authorization', 'x-emby-client', 'x-emby-device-name',
            'x-emby-device-id', 'x-emby-client-version', 'x-emby-language',
            'x-emby-token'
        ]
    }
    
    target_url = f"{real_emby_url}/emby/Users/{user_id}/Items"
    logger.debug(f"HOME_LATEST_HANDLER: Forwarding to URL={target_url}, Params={new_params}")

    async with session.get(target_url, params=new_params, headers=headers_to_forward) as resp:
        if resp.status != 200 or "application/json" not in resp.headers.get("Content-Type", ""):
            content = await resp.read(); return Response(content=content, status_code=resp.status, headers={"Content-Type": resp.headers.get("Content-Type")})

        data = await resp.json()
        items_list = data.get("Items", [])

        if post_filter_rules:
            items_list = _apply_post_filter(items_list, post_filter_rules)

        if found_vlib.merge_by_tmdb_id:
            items_list = await handler_merger.merge_items_by_tmdb(items_list)

        client_limit_str = params.get("Limit")
        if client_limit_str:
            try:
                final_limit = int(client_limit_str)
                items_list = items_list[:final_limit]
            except (ValueError, TypeError): pass
        
        # 关键修复：/Items/Latest 端点需要直接返回一个 JSON 数组，而不是一个包含 "Items" 键的对象。
        # 这与 Go 版本的实现保持一致。
        content = json.dumps(items_list).encode('utf-8')
        return Response(content=content, status_code=200, headers={"Content-Type": "application/json"})

    return None
