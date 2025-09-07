import re
import time
import requests
import json
import logging
from pathlib import Path
from bs4 import BeautifulSoup
from db_manager import DBManager, RSS_CACHE_DB, TMDB_CACHE_DB
import config_manager

logger = logging.getLogger(__name__)

DB_DIR = Path(__file__).parent.parent.parent / "config"

class BaseRssProcessor:
    def __init__(self, vlib):
        self.vlib = vlib
        self.library_id = vlib.id
        self.rsshub_url = vlib.rsshub_url
        self.rss_db = DBManager(RSS_CACHE_DB)
        self.tmdb_cache_db = DBManager(TMDB_CACHE_DB)
        self.rss_library_db = DBManager(DB_DIR / "rss_library_items.db")
        self.config = config_manager.load_config()

    def _fetch_rss_content(self):
        """获取并缓存 RSS 内容，缓存有效期为30分钟"""
        self.rss_db.execute(
            "CREATE TABLE IF NOT EXISTS rss_cache (url TEXT PRIMARY KEY, content TEXT, timestamp REAL)",
            commit=True
        )
        cache_duration = 30 * 60
        cached = self.rss_db.fetchone("SELECT content, timestamp FROM rss_cache WHERE url = ?", (self.rsshub_url,))
        if cached:
            try:
                is_valid = (time.time() - float(cached['timestamp'])) < cache_duration
                if is_valid:
                    logger.info(f"RSS源 {self.rsshub_url} 命中缓存。")
                    return cached['content']
            except (ValueError, TypeError):
                logger.warning(f"RSS源 {self.rsshub_url} 的缓存时间戳格式无效，将强制刷新。")
                pass

        logger.info(f"RSS源 {self.rsshub_url} 缓存未命中或已过期，正在获取新内容...")
        response = requests.get(self.rsshub_url)
        response.raise_for_status()
        content = response.text
        
        self.rss_db.execute(
            "INSERT OR REPLACE INTO rss_cache (url, content, timestamp) VALUES (?, ?, ?)",
            (self.rsshub_url, content, time.time()),
            commit=True
        )
        logger.info(f"RSS源 {self.rsshub_url} 的新内容已存入缓存。")
        return content

    def _parse_source_ids(self, xml_content):
        """从 RSS XML 中解析出源 ID。必须由子类实现。"""
        raise NotImplementedError

    def _get_tmdb_info(self, source_info):
        """根据源 ID 获取 TMDB 信息。必须由子类实现。"""
        raise NotImplementedError

    def _search_tmdb_by_name(self, title, year=None):
        """通用的 TMDB 搜索方法，作为兜底方案。支持处理'|'分隔的多个标题。"""
        logger.info(f"正在使用通用搜索为 '{title}' (年份: {year or 'N/A'}) 查找 TMDB ID...")
        if not self.config.tmdb_api_key:
            logger.error("TMDB API Key 未配置，无法执行通用搜索。")
            return []

        # 替换全角'｜'为半角'|'，然后拆分为多个标题进行尝试
        normalized_title = title.replace('｜', '|')
        titles_to_try = [t.strip() for t in normalized_title.split('|')]
        
        proxies = {"http": self.config.tmdb_proxy, "https": self.config.tmdb_proxy} if self.config.tmdb_proxy else None

        for current_title in titles_to_try:
            if not current_title: # 跳过空的标题
                continue
            
            logger.info(f"正在尝试搜索标题: '{current_title}'...")
            url = f"https://api.themoviedb.org/3/search/multi?api_key={self.config.tmdb_api_key}&query={requests.utils.quote(current_title)}&language=zh-CN"
            if year:
                url += f"&year={year}"
            
            try:
                response = requests.get(url, proxies=proxies, timeout=10)
                response.raise_for_status()
                data = response.json()
                results = data.get("results", [])

                if not results:
                    # 这个标题没找到，继续尝试下一个
                    continue

                # 简单的匹配逻辑：选择第一个电影或电视剧结果
                for result in results:
                    media_type = result.get("media_type")
                    if media_type in ["movie", "tv"]:
                        tmdb_id = result.get("id")
                        logger.info(f"通用搜索成功: '{current_title}' -> TMDB ID {tmdb_id} ({media_type})")
                        # 找到一个就立刻返回
                        return [(str(tmdb_id), media_type)]
                
            except requests.RequestException as e:
                logger.error(f"通用 TMDB 搜索 API 请求失败 (标题: '{current_title}'): {e}")
                # 如果一个标题请求失败，继续尝试下一个
                continue
        
        # 所有标题都尝试过后，仍然没有找到结果
        logger.warning(f"通用搜索未能为任何备选标题 '{title}' 找到任何 TMDB 结果。")
        return []

    def process(self):
        """处理整个流程，包含专用匹配和通用兜底匹配"""
        logger.info(f"开始处理 RSS 媒体库 {self.library_id} (URL: {self.rsshub_url})")
        xml_content = self._fetch_rss_content()
        
        logger.info(f"正在为媒体库 {self.library_id} 清理旧的项目...")
        self.rss_library_db.execute("DELETE FROM rss_library_items WHERE library_id = ?", (self.library_id,), commit=True)
        
        source_items = self._parse_source_ids(xml_content)
        
        tmdb_ids_map = {}
        processed_count = 0
        total_items = len(source_items)

        for i, item_info in enumerate(source_items):
            source_id = item_info['id']
            title = item_info['title']
            year = item_info.get('year')
            
            logger.info(f"正在处理: {title} (ID: {source_id}) ({i+1}/{total_items})")
            
            # 1. 尝试专用方法匹配
            tmdb_results = self._get_tmdb_info(item_info)
            
            # 2. 如果专用方法失败，尝试通用兜底方法
            if not tmdb_results:
                logger.info(f"专用方法未能匹配 '{title}'，尝试通用搜索...")
                tmdb_results = self._search_tmdb_by_name(title, year)

            if not tmdb_results:
                logger.warning(f"所有方法都未能为 '{title}' (ID: {source_id}) 找到 TMDB 匹配，已跳过。")
                continue

            for tmdb_id, media_type in tmdb_results:
                self.rss_library_db.execute(
                    "INSERT OR IGNORE INTO rss_library_items (library_id, tmdb_id, media_type, emby_item_id) VALUES (?, ?, ?, NULL)",
                    (self.library_id, tmdb_id, media_type),
                    commit=True
                )
                logger.info(f"成功映射 '{title}' -> TMDB ID {tmdb_id} ({media_type}) 并保存至媒体库 {self.library_id}。")
                if tmdb_id not in tmdb_ids_map:
                    tmdb_ids_map[tmdb_id] = media_type
            
            processed_count += 1
        
        logger.info(f"RSS 媒体库 {self.library_id} TMDB 匹配完成。共处理 {processed_count}/{total_items} 个项目。")

        # 【核心修改】检查并追加手动指定的 TMDB ID
        if self.vlib.fallback_tmdb_id and self.vlib.fallback_tmdb_type:
            logger.info(f"正在为媒体库 {self.library_id} 追加手动指定的 TMDB ID: {self.vlib.fallback_tmdb_id}")
            tmdb_id = self.vlib.fallback_tmdb_id
            media_type = self.vlib.fallback_tmdb_type
            self.rss_library_db.execute(
                "INSERT OR IGNORE INTO rss_library_items (library_id, tmdb_id, media_type, emby_item_id) VALUES (?, ?, ?, NULL)",
                (self.library_id, tmdb_id, media_type),
                commit=True
            )
            if tmdb_id not in tmdb_ids_map:
                tmdb_ids_map[tmdb_id] = media_type
        
        if tmdb_ids_map:
            self._match_items_in_emby(tmdb_ids_map)
        
        self._precache_tmdb_info()

    def _find_items_in_emby(self, tmdb_ids_map):
        """通过调用 Emby API 查找已存在的项目，并根据每个项目的具体类型进行精确查询"""
        if not tmdb_ids_map or not self.config.emby_url or not self.config.emby_api_key:
            return {}

        logger.info(f"将逐个查询 {len(tmdb_ids_map)} 个 TMDB ID 在 Emby 中的存在状态...")
        
        emby_id_map = {}
        url = f"{self.config.emby_url.rstrip('/')}/Items"
        headers = {"X-Emby-Token": self.config.emby_api_key}

        # 【核心修复】遍历 tmdb_ids_map 的所有项，以同时获取 tmdb_id 和 media_type
        for tmdb_id, media_type in tmdb_ids_map.items():
            # 根据 media_type 确定要查询的 Emby 项目类型
            # 注意：我们前端保存的是 'Movie'/'TV'，而 TMDB API 返回的是 'movie'/'tv'
            if media_type.lower() == 'movie':
                item_types = "Movie"
            elif media_type.lower() == 'tv':
                item_types = "Series"
            else:
                # 对于未知类型，默认同时查找两者以保持兼容性
                item_types = "Movie,Series"
                logger.warning(f"TMDB ID {tmdb_id} 的媒体类型 '{media_type}' 未知，将同时搜索电影和剧集。")

            params = {
                "Recursive": "true",
                "IncludeItemTypes": item_types,
                "Fields": "ProviderIds",
                "TmdbId": tmdb_id
            }
            try:
                logger.info(f"  - 正在为 TMDB ID {tmdb_id} 查询 Emby 中的 '{item_types}'...")
                response = requests.get(url, headers=headers, params=params, timeout=10)
                response.raise_for_status()
                results = response.json().get("Items", [])
                
                for item in results:
                    item_tmdb_id = item.get("ProviderIds", {}).get("Tmdb")
                    if str(item_tmdb_id) == str(tmdb_id):
                        emby_id_map[tmdb_id] = item.get("Id")
                        logger.info(f"  - 匹配成功: TMDB ID {tmdb_id} -> Emby ID {item.get('Id')}")
                        break
            except requests.RequestException as e:
                logger.error(f"查询 Emby API 时发生错误 (TMDB ID: {tmdb_id}): {e}")
                continue
        
        logger.info(f"Emby API 查询完成，在您的库中找到了 {len(emby_id_map)} 个匹配的项目。")
        return emby_id_map

    def _match_items_in_emby(self, tmdb_ids_map):
        """获取所有项目的 TMDB ID，查询 Emby，并更新数据库"""
        # 【核心修复】移除子类中重写的 _find_items_in_emby 方法，因为现在基类方法已足够智能
        emby_id_map = self._find_items_in_emby(tmdb_ids_map)
        update_count = 0
        for tmdb_id, emby_item_id in emby_id_map.items():
            self.rss_library_db.execute(
                "UPDATE rss_library_items SET emby_item_id = ? WHERE library_id = ? AND tmdb_id = ?",
                (emby_item_id, self.library_id, tmdb_id),
                commit=True
            )
            update_count += 1
        logger.info(f"Emby 库匹配完成，已更新 {update_count} 个项目的存在状态。")

    def _format_tmdb_to_emby(self, tmdb_data, media_type, tmdb_id, server_id):
        """将从 TMDB API 获取的数据格式化为 Emby 项目所需的简化结构。"""
        is_movie = media_type == 'movie'
        item_type = 'Movie' if is_movie else 'Series'
        
        return {
            "Name": tmdb_data.get('title') if is_movie else tmdb_data.get('name'),
            "ProductionYear": int((tmdb_data.get('release_date') or '0').split('-')[0]) if is_movie else int((tmdb_data.get('first_air_date') or '0').split('-')[0]),
            "Id": f"tmdb-{tmdb_id}",
            "Type": item_type,
            "IsFolder": False,
            "MediaType": "Video" if is_movie else "Series",
            "ServerId": server_id,
            "ImageTags": {"Primary": "placeholder"},
            "HasPrimaryImage": True,
            "PrimaryImageAspectRatio": 0.6666666666666666,
            "ProviderIds": {"Tmdb": str(tmdb_id)},
            "UserData": {"Played": False, "PlayCount": 0, "IsFavorite": False, "PlaybackPositionTicks": 0},
            "Overview": tmdb_data.get("overview"),
            "PremiereDate": tmdb_data.get("release_date") if is_movie else tmdb_data.get("first_air_date"),
        }

    def _fetch_and_cache_tmdb_item(self, tmdb_id, media_type):
        """获取单个 TMDB 项目并将其存入缓存，如果缓存已存在则跳过。"""
        cached = self.tmdb_cache_db.fetchone("SELECT data FROM tmdb_cache WHERE tmdb_id = ? AND media_type = ?", (tmdb_id, media_type))
        if cached:
            return True

        if not self.config.tmdb_api_key: return False

        item_type_path = 'movie' if media_type == 'movie' else 'tv'
        url = f"https://api.themoviedb.org/3/{item_type_path}/{tmdb_id}?api_key={self.config.tmdb_api_key}&language=zh-CN"
        proxies = {"http": self.config.tmdb_proxy, "https": self.config.tmdb_proxy} if self.config.tmdb_proxy else None

        try:
            logger.info(f"正在为 TMDB ID {tmdb_id} ({media_type}) 获取信息并缓存...")
            response = requests.get(url, proxies=proxies, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            server_id = self.config.emby_server_id or "emby"
            emby_item = self._format_tmdb_to_emby(data, media_type, tmdb_id, server_id)
            
            self.tmdb_cache_db.execute(
                "INSERT OR REPLACE INTO tmdb_cache (tmdb_id, media_type, data) VALUES (?, ?, ?)",
                (tmdb_id, media_type, json.dumps(emby_item, ensure_ascii=False)),
                commit=True
            )
            return True
        except Exception as e:
            logger.error(f"从 TMDB 获取信息失败 (ID: {tmdb_id}): {e}")
            return False

    def _precache_tmdb_info(self):
        """为 RSS 库中不存在于 Emby 的项目预先缓存 TMDB 信息。"""
        logger.info(f"开始为媒体库 {self.library_id} 预缓存缺失项目的 TMDB 信息...")
        missing_items = self.rss_library_db.fetchall(
            "SELECT tmdb_id, media_type FROM rss_library_items WHERE library_id = ? AND emby_item_id IS NULL",
            (self.library_id,)
        )

        if not missing_items:
            logger.info("没有需要预缓存的 TMDB 项目。")
            return

        logger.info(f"发现 {len(missing_items)} 个需要预缓存信息的项目。")
        cached_count = 0
        for item in missing_items:
            cached = self._fetch_and_cache_tmdb_item(item['tmdb_id'], item['media_type'])
            if cached:
                cached_count += 1
        
        logger.info(f"TMDB 信息预缓存完成，成功缓存 {cached_count}/{len(missing_items)} 个项目。")
