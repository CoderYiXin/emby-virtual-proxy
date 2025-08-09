# src/proxy_handlers/handler_merger.py (无缓存的最终版)

import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

async def merge_items_by_tmdb(items: List[Dict]) -> List[Dict]:
    """
    根据 TMDB ID 合并项目列表。
    它会保留遇到的第一个具有特定 TMDB ID 的项目作为代表。
    
    Args:
        items: 从 Emby API 返回的原始项目列表。

    Returns:
        合并后的新项目列表。
    """
    if not items:
        return []

    logger.info(f"开始执行TMDB ID合并，原始项目数量: {len(items)}")
    
    tmdb_map: Dict[str, Dict] = {}
    final_items: List[Dict] = []
    
    for item in items:
        if not isinstance(item, dict):
            final_items.append(item)
            continue

        provider_ids = item.get("ProviderIds", {})
        item_type = item.get("Type")

        if item_type not in ("Movie", "Series"):
            final_items.append(item)
            continue
            
        tmdb_id = provider_ids.get("Tmdb")

        if tmdb_id:
            if tmdb_id not in tmdb_map:
                tmdb_map[tmdb_id] = item
                final_items.append(item)
            else:
                logger.debug(f"合并项目 '{item.get('Name')}' (ID: {item.get('Id')})，因为它与已有项目共享 TMDB ID: {tmdb_id}")
        else:
            final_items.append(item)
            
    merged_count = len(items) - len(final_items)
    if merged_count > 0:
        logger.info(f"TMDB ID 合并完成。{merged_count} 个项目被合并。最终项目数量: {len(final_items)}")
        
    return final_items