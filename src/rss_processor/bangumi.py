import re
import time
import requests
import json
from pathlib import Path
from bs4 import BeautifulSoup
from db_manager import DBManager, RSS_CACHE_DB
import config_manager
import logging

logger = logging.getLogger(__name__)

# 定义数据库目录
DB_DIR = Path(__file__).parent.parent.parent / "config"

class BangumiProcessor:
    def __init__(self, library_id, rsshub_url):
        self.library_id = library_id
        self.rsshub_url = rsshub_url
        self.rss_db = DBManager(RSS_CACHE_DB)
        self.config = config_manager.load_config()

    def _fetch_rss_content(self):
        """获取并缓存 RSS 内容，缓存有效期为30分钟"""
        self.rss_db.execute(
            "CREATE TABLE IF NOT EXISTS rss_cache (url TEXT PRIMARY KEY, content TEXT, timestamp REAL)",
            commit=True
        )
        cache_duration = 30 * 60
        cached = self.rss_db.fetchone("SELECT content, timestamp FROM rss_cache WHERE url = ?", (self.rsshub_url,))
        if cached and cached['timestamp'] and (time.time() - float(cached['timestamp'])) < cache_duration:
            logger.info(f"RSS源 {self.rsshub_url} 命中缓存。")
            return cached['content']
        
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

    def _parse_bangumi_ids(self, xml_content):
        """从 RSS XML 中解析出 Bangumi ID"""
        soup = BeautifulSoup(xml_content, 'xml')
        
        # 清理该库的旧项目，以确保完全同步
        rss_library_db = DBManager(DB_DIR / "rss_library_items.db")
        logger.info(f"正在为媒体库 {self.library_id} 清理旧的项目...")
        rss_library_db.execute("DELETE FROM rss_library_items WHERE library_id = ?", (self.library_id,), commit=True)
        logger.info(f"媒体库 {self.library_id} 的旧项目已清理。")
        
        items = []
        for item in soup.find_all('item'):
            link = item.find('link').text
            # 匹配如 https://bgm.tv/subject/544967 或 https://bangumi.tv/subject/544967
            bangumi_id_match = re.search(r'bangumi\.tv/subject/(\d+)', link)
            if not bangumi_id_match:
                bangumi_id_match = re.search(r'bgm\.tv/subject/(\d+)', link)
            
            if bangumi_id_match:
                items.append(bangumi_id_match.group(1))
        logger.info(f"从 RSS 源中找到 {len(items)} 个 Bangumi 条目ID。")
        return items

    def _get_tmdb_info_from_bangumi(self, bangumi_id):
        """通过内部 API 将 Bangumi ID 转换为 TMDB 信息"""
        # 注意：这个 API 地址是用户提供的，需要确保服务可用
        api_url = f"http://192.168.50.12:8180/api/matching/tmdb-matches/{bangumi_id}"
        try:
            response = requests.get(api_url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if not data:
                logger.warning(f"Bangumi ID {bangumi_id}: 未从 API 返回任何 TMDB 匹配结果。")
                return []

            # API 可能返回多个匹配项
            results = []
            for match in data:
                tmdb_id = match.get("tmdb_id")
                tmdb_type = match.get("tmdb_type")
                if tmdb_id and tmdb_type:
                    results.append((str(tmdb_id), tmdb_type))
            
            logger.info(f"Bangumi ID {bangumi_id}: 找到 {len(results)} 个 TMDB 匹配项。")
            return results
            
        except requests.RequestException as e:
            logger.error(f"调用 Bangumi 到 TMDB 匹配 API 失败 (ID: {bangumi_id}): {e}")
            return []

    def process(self):
        """处理整个流程"""
        logger.info(f"开始处理 RSS 媒体库 {self.library_id} (URL: {self.rsshub_url})")
        xml_content = self._fetch_rss_content()
        bangumi_ids = self._parse_bangumi_ids(xml_content)
        
        rss_library_db = DBManager(DB_DIR / "rss_library_items.db")
        
        newly_added_tmdb_ids = {} # 使用字典来存储 tmdb_id -> media_type，避免重复
        processed_count = 0
        total_items = len(bangumi_ids)

        for i, bangumi_id in enumerate(bangumi_ids):
            logger.info(f"正在处理 Bangumi ID: {bangumi_id} ({i+1}/{total_items})")

            tmdb_results = self._get_tmdb_info_from_bangumi(bangumi_id)
            if not tmdb_results:
                logger.warning(f"Bangumi ID {bangumi_id}: 未找到任何 TMDB 匹配，已跳过。")
                continue

            for tmdb_id, media_type in tmdb_results:
                # 存入虚拟库项目表
                rss_library_db.execute(
                    "INSERT OR IGNORE INTO rss_library_items (library_id, tmdb_id, media_type, emby_item_id) VALUES (?, ?, ?, NULL)",
                    (self.library_id, tmdb_id, media_type),
                    commit=True
                )
                logger.info(f"Bangumi ID {bangumi_id}: 成功映射到 TMDB ID {tmdb_id} ({media_type}) 并保存至媒体库 {self.library_id}。")
                if tmdb_id not in newly_added_tmdb_ids:
                    newly_added_tmdb_ids[tmdb_id] = media_type
            
            processed_count += 1
        
        logger.info(f"RSS 媒体库 {self.library_id} TMDB 匹配完成。共处理 {processed_count}/{total_items} 个项目。")
        
        if newly_added_tmdb_ids:
            self._match_items_in_emby(newly_added_tmdb_ids)

    def _find_items_in_emby(self, tmdb_ids_map):
        """通过调用 Emby API 查找已存在的项目"""
        if not tmdb_ids_map or not self.config.emby_url or not self.config.emby_api_key:
            return {}

        logger.info(f"将逐个查询 {len(tmdb_ids_map)} 个 TMDB ID 在 Emby 中的存在状态...")
        
        emby_id_map = {}
        url = f"{self.config.emby_url.rstrip('/')}/Items"
        headers = {"X-Emby-Token": self.config.emby_api_key}

        for tmdb_id in tmdb_ids_map.keys():
            params = {
                "Recursive": "true",
                "IncludeItemTypes": "Series", # Bangumi 主要处理电视剧
                "Fields": "ProviderIds",
                "TmdbId": tmdb_id
            }
            try:
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
        rss_library_db = DBManager(DB_DIR / "rss_library_items.db")
        
        # 调用通用的 Emby 查找函数
        emby_id_map = self._find_items_in_emby(tmdb_ids_map)

        # 更新 rss_library_items 数据库
        update_count = 0
        for tmdb_id, emby_item_id in emby_id_map.items():
            rss_library_db.execute(
                "UPDATE rss_library_items SET emby_item_id = ? WHERE library_id = ? AND tmdb_id = ?",
                (emby_item_id, self.library_id, tmdb_id),
                commit=True
            )
            update_count += 1
        
        logger.info(f"Emby 库匹配完成，已更新 {update_count} 个项目的存在状态。")
