import re
import requests
import logging
from bs4 import BeautifulSoup
from .base_processor import BaseRssProcessor

logger = logging.getLogger(__name__)

class BangumiProcessor(BaseRssProcessor):
    def __init__(self, vlib):
        super().__init__(vlib)

    def _parse_source_ids(self, xml_content):
        """从 RSS XML 中解析出 Bangumi ID、标题和年份"""
        soup = BeautifulSoup(xml_content, 'xml')
        items_data = []
        for item in soup.find_all('item'):
            link = item.find('link').text
            title_text = item.find('title').text
            
            bangumi_id_match = re.search(r'bangumi\.tv/subject/(\d+)', link)
            if not bangumi_id_match:
                bangumi_id_match = re.search(r'bgm\.tv/subject/(\d+)', link)
            
            if bangumi_id_match:
                bangumi_id = bangumi_id_match.group(1)
                
                # Bangumi 的 RSS 通常不含年份，这里设为 None
                items_data.append({
                    "id": bangumi_id,
                    "title": title_text.strip(),
                    "year": None
                })
        logger.info(f"从 RSS 源中找到 {len(items_data)} 个 Bangumi 条目。")
        return items_data

    def _get_tmdb_info(self, source_info):
        """通过内部 API 将 Bangumi ID 转换为 TMDB 信息"""
        bangumi_id = source_info['id']
        # 注意：这个 API 地址是用户提供的，需要确保服务可用
        api_url = f"http://192.168.50.12:8180/api/matching/tmdb-matches/{bangumi_id}"
        try:
            response = requests.get(api_url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if not data:
                logger.warning(f"Bangumi ID {bangumi_id}: 未从 API 返回任何 TMDB 匹配结果。")
                return []

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

    def _find_items_in_emby(self, tmdb_ids_map):
        """重写此方法以专门查找 'Series' 类型"""
        return super()._find_items_in_emby(tmdb_ids_map, item_types="Series")
