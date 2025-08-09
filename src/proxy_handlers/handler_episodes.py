# src/proxy_handlers/handler_episodes.py (修改后)

import asyncio
import json
import logging
import re
from fastapi import Request, Response
from aiohttp import ClientSession
from ._find_helper import find_all_series_by_tmdb_id, is_item_in_a_merge_enabled_vlib # <-- 导入新函数

logger = logging.getLogger(__name__)

EPISODES_PATH_REGEX = re.compile(r"/Shows/([a-f0-9\-]+)/Episodes")

async def handle_episodes_merge(request: Request, full_path: str, session: ClientSession, real_emby_url: str) -> Response | None:
    match = EPISODES_PATH_REGEX.search(f"/{full_path}")
    season_id = request.query_params.get("SeasonId")
    if not match or not season_id: return None

    series_id_from_path = match.group(1)
    logger.info(f"EPISODES_HANDLER: 拦截到对剧集 {series_id_from_path} 下，季 {season_id} 的“集”请求。")

    params = request.query_params
    user_id = params.get("UserId")
    if not user_id: return Response(content="UserId not found", status_code=400)

    headers = {k: v for k, v in request.headers.items() if k.lower() != 'host'}
    auth_token_param = {'X-Emby-Token': params.get('X-Emby-Token')} if 'X-Emby-Token' in params else {}
    
    # --- 【【【 新增的资格检查 】】】 ---
    should_merge = await is_item_in_a_merge_enabled_vlib(
        session, real_emby_url, user_id, series_id_from_path, headers, auth_token_param
    )
    if not should_merge:
        return None
    # --- 资格检查结束 ---

    try:
        item_url = f"{real_emby_url}/emby/Users/{user_id}/Items/{series_id_from_path}"
        item_params = {'Fields': 'ProviderIds', **auth_token_param}
        async with session.get(item_url, params=item_params, headers=headers) as resp:
            tmdb_id = (await resp.json()).get("ProviderIds", {}).get("Tmdb")
            
        season_url = f"{real_emby_url}/emby/Users/{user_id}/Items/{season_id}"
        season_params = {'Fields': 'IndexNumber', **auth_token_param}
        async with session.get(season_url, params=season_params, headers=headers) as resp:
            target_season_number = (await resp.json()).get("IndexNumber")

    except Exception as e:
        logger.error(f"EPISODES_HANDLER: 获取TMDB ID或季号失败: {e}"); return None

    if not tmdb_id or target_season_number is None: return None
    logger.info(f"EPISODES_HANDLER: 找到TMDB ID: {tmdb_id}，目标季号: {target_season_number}。")

    original_series_ids = await find_all_series_by_tmdb_id(session, real_emby_url, user_id, tmdb_id, headers, auth_token_param)
    if len(original_series_ids) < 2: return None
    logger.info(f"EPISODES_HANDLER: ✅ 找到 {len(original_series_ids)} 个关联剧集: {original_series_ids}。")

    async def fetch_episodes(series_id: str):
        seasons_url = f"{real_emby_url}/emby/Shows/{series_id}/Seasons"
        try:
            async with session.get(seasons_url, params=auth_token_param, headers=headers) as resp:
                seasons = (await resp.json()).get("Items", [])
            
            # 找到这个剧集里，与我们目标季号相同的那个季的ID
            matching_season = next((s for s in seasons if s.get("IndexNumber") == target_season_number), None)
            if not matching_season: return []

            episodes_url = f"{real_emby_url}/emby/Shows/{series_id}/Episodes"
            episode_params = dict(params)
            episode_params["SeasonId"] = matching_season.get("Id") # 使用正确的季ID
            
            async with session.get(episodes_url, params=episode_params, headers=headers) as resp:
                return (await resp.json()).get("Items", []) if resp.status == 200 else []
        except Exception: return []

    tasks = [fetch_episodes(sid) for sid in original_series_ids]
    all_episodes = [ep for sublist in await asyncio.gather(*tasks) for ep in sublist]

    merged_episodes = {}
    for episode in all_episodes:
        key = episode.get("IndexNumber")
        if key is not None and key not in merged_episodes:
            merged_episodes[key] = episode
    
    final_items = sorted(merged_episodes.values(), key=lambda x: x.get("IndexNumber", 0))
    logger.info(f"EPISODES_HANDLER: 合并完成。合并前总数: {len(all_episodes)}, 合并后最终数量: {len(final_items)}")

    return Response(content=json.dumps({"Items": final_items, "TotalRecordCount": len(final_items)}), status_code=200, media_type="application/json")