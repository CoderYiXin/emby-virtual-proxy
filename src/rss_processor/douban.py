import re
import time
import requests
import json
from pathlib import Path
from bs4 import BeautifulSoup
from db_manager import DBManager, DOUBAN_CACHE_DB, RSS_CACHE_DB
import config_manager
import logging

logger = logging.getLogger(__name__)

# 定义数据库目录，以便在此文件中访问
DB_DIR = Path(__file__).parent.parent.parent / "config"

# 豆瓣 API 的速率限制
DOUBAN_API_RATE_LIMIT = 2  # 秒

class DoubanProcessor:
    def __init__(self, library_id, rsshub_url):
        self.library_id = library_id
        self.rsshub_url = rsshub_url
        self.douban_db = DBManager(DOUBAN_CACHE_DB)
        self.rss_db = DBManager(RSS_CACHE_DB)
        self.config = config_manager.load_config()
        self.last_api_call_time = 0

    def _fetch_rss_content(self):
        """获取并缓存 RSS 内容，缓存有效期为30分钟"""
        # 确保表结构正确
        self.rss_db.execute(
            "CREATE TABLE IF NOT EXISTS rss_cache (url TEXT PRIMARY KEY, content TEXT, timestamp REAL)",
            commit=True
        )

        cache_duration = 30 * 60  # 30分钟
        
        # 检查缓存
        cached = self.rss_db.fetchone("SELECT content, timestamp FROM rss_cache WHERE url = ?", (self.rsshub_url,))
        if cached:
            try:
                # 尝试将时间戳转换为浮点数并检查是否过期
                is_valid = (time.time() - float(cached['timestamp'])) < cache_duration
                if is_valid:
                    logger.info(f"RSS源 {self.rsshub_url} 命中缓存。")
                    return cached['content']
            except (ValueError, TypeError):
                # 如果时间戳是旧的字符串格式或无效，则视为过期
                logger.warning(f"RSS源 {self.rsshub_url} 的缓存时间戳格式无效，将强制刷新。")
                pass # 继续执行下面的代码以获取新内容

        # 获取新内容
        logger.info(f"RSS源 {self.rsshub_url} 缓存未命中或已过期，正在获取新内容...")
        response = requests.get(self.rsshub_url)
        response.raise_for_status()
        content = response.text
        
        # 存入缓存
        self.rss_db.execute(
            "INSERT OR REPLACE INTO rss_cache (url, content, timestamp) VALUES (?, ?, ?)",
            (self.rsshub_url, content, time.time()),
            commit=True
        )
        logger.info(f"RSS源 {self.rsshub_url} 的新内容已存入缓存。")
        return content

    def _parse_douban_ids(self, xml_content):
        """从 RSS XML 中解析出豆瓣 ID"""
        soup = BeautifulSoup(xml_content, 'xml')
        ids = []
        for item in soup.find_all('item'):
            link = item.find('link').text
            douban_id_match = re.search(r'douban.com/subject/(\d+)', link)
            if not douban_id_match:
                douban_id_match = re.search(r'douban.com/doubanapp/dispatch/movie/(\d+)', link)
            if douban_id_match:
                ids.append(douban_id_match.group(1))
        logger.info(f"从 RSS 源中找到 {len(ids)} 个豆瓣条目ID。")
        return ids

    def _get_imdb_id_from_douban_page(self, douban_id):
        """通过访问豆瓣页面抓取 IMDb ID"""
        # 检查缓存
        cached = self.douban_db.fetchone("SELECT api_response FROM douban_api_cache WHERE douban_id = ?", (f"douban_imdb_{douban_id}",))
        if cached and cached['api_response']:
            logger.info(f"豆瓣ID {douban_id}: 在缓存中找到 IMDb ID -> {cached['api_response']}")
            return cached['api_response']

        # 速率限制
        since_last_call = time.time() - self.last_api_call_time
        if since_last_call < DOUBAN_API_RATE_LIMIT:
            sleep_time = DOUBAN_API_RATE_LIMIT - since_last_call
            logger.info(f"豆瓣页面访问速率限制：休眠 {sleep_time:.2f} 秒。")
            time.sleep(sleep_time)
        self.last_api_call_time = time.time()

        url = f"https://movie.douban.com/subject/{douban_id}/"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'}
        
        logger.info(f"豆瓣ID {douban_id}: 正在抓取页面 {url} 以寻找 IMDb ID。")
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"抓取豆瓣页面失败 (ID: {douban_id}): {e}")
            return None
        
        imdb_id_match = re.search(r'IMDb:</span> (tt\d+)', response.text)
        imdb_id = imdb_id_match.group(1) if imdb_id_match else None
        
        if imdb_id:
            logger.info(f"豆瓣ID {douban_id}: 从页面中找到 IMDb ID {imdb_id}。")
        else:
            logger.warning(f"豆瓣ID {douban_id}: 在页面中未能找到 IMDb ID。")

        # 存入缓存，即使没找到也存入空值，避免重复抓取
        self.douban_db.execute(
            "INSERT OR REPLACE INTO douban_api_cache (douban_id, api_response) VALUES (?, ?)",
            (f"douban_imdb_{douban_id}", imdb_id or ''),
            commit=True
        )
        return imdb_id

    def _get_tmdb_info_from_imdb(self, imdb_id):
        """通过 IMDb ID 查询 TMDB"""
        logger.info(f"IMDb ID {imdb_id}: 正在查询 TMDB API...")
        tmdb_api_key = self.config.tmdb_api_key
        if not tmdb_api_key:
            raise ValueError("TMDB API Key not configured.")

        url = f"https://api.themoviedb.org/3/find/{imdb_id}?api_key={tmdb_api_key}&external_source=imdb_id"
        
        proxies = {"http": self.config.tmdb_proxy, "https": self.config.tmdb_proxy} if self.config.tmdb_proxy else None
        
        response = requests.get(url, proxies=proxies)
        response.raise_for_status()
        data = response.json()

        # 根据返回结果确定媒体类型
        if data.get('movie_results'):
            tmdb_id = data['movie_results'][0]['id']
            media_type = 'movie'
        elif data.get('tv_results'):
            tmdb_id = data['tv_results'][0]['id']
            media_type = 'tv'
        else:
            logger.warning(f"IMDb ID {imdb_id}: 在 TMDB 上未找到结果。")
            return None, None
        
        logger.info(f"IMDb ID {imdb_id}: 在 TMDB 上找到 -> TMDB ID: {tmdb_id}, 类型: {media_type}")
        return str(tmdb_id), media_type

    def process(self):
        """处理整个流程"""
        logger.info(f"开始处理 RSS 媒体库 {self.library_id} (URL: {self.rsshub_url})")
        xml_content = self._fetch_rss_content()
        douban_ids = self._parse_douban_ids(xml_content)
        
        rss_library_db = DBManager(DB_DIR / "rss_library_items.db")
        
        # 清理该库的旧项目，以确保完全同步
        logger.info(f"正在为媒体库 {self.library_id} 清理旧的项目...")
        rss_library_db.execute("DELETE FROM rss_library_items WHERE library_id = ?", (self.library_id,), commit=True)
        logger.info(f"媒体库 {self.library_id} 的旧项目已清理。")
        
        processed_count = 0
        total_items = len(douban_ids)
        for i, douban_id in enumerate(douban_ids):
            logger.info(f"正在处理豆瓣ID: {douban_id} ({i+1}/{total_items})")

            # 检查是否已存在 豆瓣ID -> TMDB ID 的映射
            existing_mapping = self.douban_db.fetchone(
                "SELECT tmdb_id, media_type FROM douban_tmdb_mapping WHERE douban_id = ?",
                (douban_id,)
            )
            if existing_mapping:
                tmdb_id = existing_mapping['tmdb_id']
                media_type = existing_mapping['media_type']
                logger.info(f"豆瓣ID {douban_id}: 在缓存中找到已存在的TMDB映射 -> {tmdb_id} ({media_type})，跳过。")
                # 确保该项目存在于库中
                rss_library_db.execute(
                    "INSERT OR IGNORE INTO rss_library_items (library_id, tmdb_id, media_type) VALUES (?, ?, ?)",
                    (self.library_id, tmdb_id, media_type),
                    commit=True
                )
                processed_count += 1
                continue

            # 如果没有映射，则走完整流程
            logger.info(f"豆瓣ID {douban_id}: 未找到TMDB映射，开始完整处理流程。")
            imdb_id = self._get_imdb_id_from_douban_page(douban_id)
            if not imdb_id:
                logger.warning(f"豆瓣ID {douban_id}: 因未能找到 IMDb ID 而跳过。")
                continue

            tmdb_id, media_type = self._get_tmdb_info_from_imdb(imdb_id)
            if not tmdb_id or not media_type:
                continue
            
            # 存入映射关系
            self.douban_db.execute(
                "INSERT OR REPLACE INTO douban_tmdb_mapping (douban_id, tmdb_id, media_type) VALUES (?, ?, ?)",
                (douban_id, tmdb_id, media_type),
                commit=True
            )
            
            # 存入虚拟库项目表，此时 emby_item_id 默认为 NULL
            rss_library_db.execute(
                "INSERT OR IGNORE INTO rss_library_items (library_id, tmdb_id, media_type, emby_item_id) VALUES (?, ?, ?, NULL)",
                (self.library_id, tmdb_id, media_type),
                commit=True
            )
            logger.info(f"豆瓣ID {douban_id}: 成功映射到 TMDB ID {tmdb_id} 并保存至媒体库 {self.library_id}。")
            processed_count += 1
        
        logger.info(f"RSS 媒体库 {self.library_id} TMDB 匹配完成。共处理 {processed_count}/{total_items} 个项目。")
        
        # --- 新增：在刷新流程的最后，匹配 Emby 库 ---
        self._match_items_in_emby(douban_ids)

    def _find_items_in_emby(self, tmdb_ids_map):
        """通过调用 Emby API 查找已存在的项目，返回 {tmdb_id: emby_item_id} 的映射"""
        if not tmdb_ids_map or not self.config.emby_url or not self.config.emby_api_key:
            return {}

        logger.info(f"将逐个查询 {len(tmdb_ids_map)} 个 TMDB ID 在 Emby 中的存在状态（此过程可能较慢）...")
        
        emby_id_map = {}
        url = f"{self.config.emby_url.rstrip('/')}/Items"
        headers = {"X-Emby-Token": self.config.emby_api_key}

        for tmdb_id in tmdb_ids_map.keys():
            params = {
                "Recursive": "true",
                "IncludeItemTypes": "Movie,Series",
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

    def _match_items_in_emby(self, douban_ids):
        """获取所有项目的 TMDB ID，查询 Emby，并更新数据库"""
        rss_library_db = DBManager(DB_DIR / "rss_library_items.db")
        
        # 1. 从 douban_tmdb_mapping 获取所有相关的 TMDB ID
        # 构建占位符 (?,?,...)
        placeholders = ','.join('?' for _ in douban_ids)
        query = f"SELECT tmdb_id, media_type FROM douban_tmdb_mapping WHERE douban_id IN ({placeholders})"
        
        all_tmdb_items = self.douban_db.fetchall(query, douban_ids)
        tmdb_ids_map = {item['tmdb_id']: item['media_type'] for item in all_tmdb_items}

        if not tmdb_ids_map:
            logger.info("没有需要与 Emby 库匹配的 TMDB ID。")
            return

        # 2. 调用 Emby API 查找这些 TMDB ID
        emby_id_map = self._find_items_in_emby(tmdb_ids_map)

        # 3. 更新 rss_library_items 数据库
        update_count = 0
        for tmdb_id, emby_item_id in emby_id_map.items():
            rss_library_db.execute(
                "UPDATE rss_library_items SET emby_item_id = ? WHERE library_id = ? AND tmdb_id = ?",
                (emby_item_id, self.library_id, tmdb_id),
                commit=True
            )
            update_count += 1
        
        logger.info(f"Emby 库匹配完成，已更新 {update_count} 个项目的存在状态。")
