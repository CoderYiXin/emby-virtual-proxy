import re
import json
import logging
import difflib
import datetime
import requests
from bs4 import BeautifulSoup
from .base_processor import BaseRssProcessor
from db_manager import DBManager, BANGUMI_CACHE_DB

logger = logging.getLogger(__name__)

class BangumiProcessor(BaseRssProcessor):
    def __init__(self, vlib):
        super().__init__(vlib)
        self.bangumi_db = DBManager(BANGUMI_CACHE_DB)
        
        # 定义去后缀的正则列表 (编译一次以提高效率)
        self.truncation_patterns = [
            re.compile(r'\s*第[一二三四五六七八九十\d]+[季期].*$', re.IGNORECASE),
            re.compile(r'\s*Season\s*\d+.*$', re.IGNORECASE),
            re.compile(r'\s*Part\s*\d+.*$', re.IGNORECASE),
            re.compile(r'\s*Cour\s*\d+.*$', re.IGNORECASE),
            re.compile(r'\s*-\s*season\s*\d+.*$', re.IGNORECASE),
        ]

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
        """
        根据 Bangumi ID 获取 TMDB 信息。
        流程: 查库 -> (未命中) -> Fetch Metadata -> Gen Strategies -> Search & Score -> Save -> Return
        """
        bangumi_id = source_info['id']
        
        # 1. 检查数据库映射
        existing = self.bangumi_db.fetchone(
            "SELECT tmdb_id, media_type, score FROM bangumi_tmdb_mapping WHERE bangumi_id = ?",
            (bangumi_id,)
        )
        if existing:
            logger.info(f"Bangumi ID {bangumi_id}: 命中缓存映射 -> TMDB ID {existing['tmdb_id']} ({existing['media_type']}), Score: {existing['score']}")
            return [(existing['tmdb_id'], existing['media_type'])]

        # 2. 执行匹配逻辑
        logger.info(f"Bangumi ID {bangumi_id}: 未找到缓存，开始智能匹配流程...")
        match_result = self._process_bangumi_match(bangumi_id)
        
        if match_result:
            tmdb_id, tmdb_type, score, method = match_result
            # 3. 保存结果
            self.bangumi_db.execute(
                "INSERT OR REPLACE INTO bangumi_tmdb_mapping (bangumi_id, tmdb_id, media_type, match_method, score) VALUES (?, ?, ?, ?, ?)",
                (bangumi_id, tmdb_id, tmdb_type, method, score),
                commit=True
            )
            logger.info(f"Bangumi ID {bangumi_id}: 匹配成功并保存 -> TMDB ID {tmdb_id} ({tmdb_type}) [Score: {score:.2f}]")
            return [(tmdb_id, tmdb_type)]
        else:
            logger.warning(f"Bangumi ID {bangumi_id}: 所有策略尝试完毕，未找到符合阈值的 TMDB 匹配。")
            return []

    def _process_bangumi_match(self, bangumi_id):
        """核心匹配流程控制器"""
        # Step 1: 获取 Bangumi 元数据
        metadata = self._fetch_bangumi_metadata(bangumi_id)
        if not metadata:
            return None

        # Step 2: 生成搜索策略
        strategies = self._generate_search_strategies(metadata)
        
        # Step 3: 执行搜索与打分
        best_match = None
        best_score = 0
        THRESHOLD = 7.5

        for priority, (query, year, strategy_name) in enumerate(strategies, 1):
            logger.info(f"  [策略 {priority}] {strategy_name}: 搜索 '{query}' (Year: {year})")
            
            candidates = self._search_tmdb_multi(query, year)
            if not candidates:
                logger.debug(f"    - 无结果，跳过。")
                continue

            for candidate in candidates:
                score = self._calculate_score(candidate, metadata, query)
                logger.debug(f"    - 候选 '{candidate.get('title') or candidate.get('name')}' ({candidate.get('id')}): {score:.2f}分")

                if score > best_score:
                    best_score = score
                    best_match = candidate
                    best_match['match_method'] = strategy_name

                # 如果超过阈值，直接锁定胜局 (Early Exit)
                if score >= THRESHOLD:
                    logger.info(f"    >>> 触发阈值 ({score:.2f} >= {THRESHOLD})，锁定匹配。")
                    return (str(best_match['id']), best_match['media_type'], score, strategy_name)

        # 如果循环结束还没有触发阈值，但有最高分结果（可选：根据需求决定是否要强制阈值。这里严格遵循“所有策略耗尽->匹配失败”如果不过阈值）
        # 但通常如果分数太低（比如<4），可能完全不对。
        # 逻辑描述说："如果所有策略尝试完都没有结果超过阈值，则判定为匹配失败。"
        return None

    def _fetch_bangumi_metadata(self, bangumi_id):
        """获取 Bangumi 条目详情 (带缓存)"""
        # 查缓存
        cached = self.bangumi_db.fetchone("SELECT api_response FROM bangumi_api_cache WHERE bangumi_id = ?", (bangumi_id,))
        if cached:
            return json.loads(cached['api_response'])

        # 调 API
        url = f"https://api.bgm.tv/v0/subjects/{bangumi_id}"
        headers = {"User-Agent": "emby-virtual-proxy/1.0 (https://github.com/orgs/bangumi/repositories)"}
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 404:
                logger.warning(f"Bangumi API 404: ID {bangumi_id} 不存在。")
                return None
            resp.raise_for_status()
            data = resp.json()
            
            # 存缓存
            self.bangumi_db.execute(
                "INSERT OR REPLACE INTO bangumi_api_cache (bangumi_id, api_response) VALUES (?, ?)",
                (bangumi_id, json.dumps(data, ensure_ascii=False)),
                commit=True
            )
            return data
        except Exception as e:
            logger.error(f"Bangumi API 请求失败 ({bangumi_id}): {e}")
            return None

    def _generate_search_strategies(self, metadata):
        """生成 5 种搜索策略"""
        name_cn = metadata.get('name_cn') or ""
        name_original = metadata.get('name') or ""
        date_str = metadata.get('date') or ""
        air_year = date_str.split('-')[0] if date_str else None
        
        strategies = []

        # Helper to clean suffixes
        def clean_suffix(text):
            if not text: return ""
            cleaned = text
            for pattern in self.truncation_patterns:
                cleaned = pattern.sub('', cleaned)
            return cleaned.strip()

        # 策略 1: 精确中文名 + 年份
        if name_cn and air_year:
            strategies.append((name_cn, air_year, "ExactCN_Year"))
        
        # 策略 2: 精确原名 + 年份
        if name_original and air_year:
            strategies.append((name_original, air_year, "ExactOrigin_Year"))

        # 策略 3: 基础中文名 (去后缀) + 年份
        base_cn = clean_suffix(name_cn)
        if base_cn and base_cn != name_cn and air_year:
            strategies.append((base_cn, air_year, "BaseCN_Year"))

        # 策略 4: 基础原名 (去后缀) + 年份
        base_origin = clean_suffix(name_original)
        if base_origin and base_origin != name_original and air_year:
            strategies.append((base_origin, air_year, "BaseOrigin_Year"))

        # 策略 5: 基础中文名 (无年份，作为保底)
        if base_cn:
            strategies.append((base_cn, None, "BaseCN_NoYear"))
        elif name_cn:
             strategies.append((name_cn, None, "ExactCN_NoYear"))

        return strategies

    def _search_tmdb_multi(self, query, year=None):
        """调用 TMDB /search/multi 接口"""
        if not self.config.tmdb_api_key:
            logger.error("未配置 TMDB API Key，无法搜索。")
            return []

        url = "https://api.themoviedb.org/3/search/multi"
        params = {
            "api_key": self.config.tmdb_api_key,
            "query": query,
            "language": "zh-CN",
            "include_adult": "false"
        }
        
        # TMDB API 对 multi search 的年份过滤参数稍微有点特殊
        # 对于 movie 是 release_year, 对于 tv 是 first_air_date_year
        # 但 search/multi 并不总是完美支持单一参数过滤两者，
        # 不过我们可以先搜出来，然后在代码里也可以二次验证。
        # 实际上 search/multi 并没有统一的 'year' 参数，通常不传，或者靠打分阶段的年份匹配来降权/加权。
        # 但为了遵循“策略”，我们可以在 API 调用层面不传 year (因为 multi 接口对混合类型的 year 支持一般)，
        # 或者尝试传 'year' (对 movie 有效) 和 'first_air_date_year' (对 tv 有效)。
        # 简单起见，这里不传 API 的 year 参数，依靠 query 召回，然后在 score 阶段验证年份？
        # 不，策略里明确说了 "+ 2023"，这通常意味着在 query 里不包含 2023，而是作为过滤条件。
        # 让我们检查 TMDB 文档。Multi search 只有 `query`, `page`, `include_adult`, `language`, `region`.
        # 它 *没有* year 参数。
        # 所以必须在收到结果后，在代码层面过滤或打分。
        # 更新：Specific search (search/movie, search/tv) 有 year 参数。
        # 既然逻辑要求 "Search Strategies" 里带年份，最好的办法是搜索后在内存里优先匹配该年份。
        # 或者，如果结果太多，我们可能无法全部获取。
        # 这里我们按 query 搜，然后在 _calculate_score 里如果不匹配年份则大幅扣分或不加分。
        
        proxies = {"http": self.config.tmdb_proxy, "https": self.config.tmdb_proxy} if self.config.tmdb_proxy else None
        
        try:
            resp = requests.get(url, params=params, proxies=proxies, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return data.get('results', [])
        except Exception as e:
            logger.error(f"TMDB Search Error (Query: {query}): {e}")
            return []

    def _calculate_score(self, tmdb_item, bgm_metadata, query_used):
        """
        智能打分系统
        @param tmdb_item: TMDB 返回的单个结果对象
        @param bgm_metadata: Bangumi 元数据
        @param query_used: 搜索使用的关键词 (用于计算文本相似度)
        """
        score = 0.0
        
        # 提取 TMDB 信息
        media_type = tmdb_item.get('media_type')
        if media_type not in ['tv', 'movie']:
            return 0 # 忽略 person 等其他类型

        title = tmdb_item.get('title') if media_type == 'movie' else tmdb_item.get('name')
        original_title = tmdb_item.get('original_title') if media_type == 'movie' else tmdb_item.get('original_name')
        
        date_str = tmdb_item.get('release_date') if media_type == 'movie' else tmdb_item.get('first_air_date')
        tmdb_year = date_str.split('-')[0] if date_str else None

        bgm_year = None
        if bgm_metadata.get('date'):
            bgm_year = bgm_metadata.get('date').split('-')[0]

        # 1. 基础分: 文本相似度 (0-10)
        # 比较 query 和 (title, original_title) 中相似度较高者
        sim_title = difflib.SequenceMatcher(None, query_used.lower(), (title or "").lower()).ratio()
        sim_orig = difflib.SequenceMatcher(None, query_used.lower(), (original_title or "").lower()).ratio()
        base_score = max(sim_title, sim_orig) * 10
        score += base_score

        # 2. 动画类型奖励 (+5)
        # TMDB Genre ID 16 = Animation
        genre_ids = tmdb_item.get('genre_ids', [])
        if 16 in genre_ids:
            score += 5.0

        # 3. 媒体格式奖励 (+3)
        # Bangumi type: 1=Book, 2=Anime, 3=Music, 4=Game, 6=Real (Three-dimension)
        # Platform 字段更详细: TV, Web, OVA, Movie, etc.
        bgm_platform = bgm_metadata.get('platform', '').lower()
        
        is_bgm_movie = bgm_platform in ['movie', 'theater', '剧场版']
        is_tmdb_movie = media_type == 'movie'
        
        # 简单判定：如果是 Movie 对 Movie -> 加分
        # 如果是 TV/Web/OVA 对 TV -> 加分
        if is_bgm_movie and is_tmdb_movie:
            score += 3.0
        elif (not is_bgm_movie) and (not is_tmdb_movie): # Assume TV
            score += 3.0

        # 4. (额外) 年份惩罚/过滤
        # 虽然逻辑说明里没明确写“年份不匹配扣分”，但“策略”里包含了年份。
        # 如果策略包含年份，而结果年份不匹配，理应降低相关性。
        # 简单的做法：如果年份差超过 1 年，扣 2 分；如果完全匹配，加 1 分。
        if tmdb_year and bgm_year:
            try:
                diff = abs(int(tmdb_year) - int(bgm_year))
                if diff == 0:
                    score += 1.0 # 年份完美匹配奖励
                elif diff > 1:
                    score -= 2.0 # 年份严重不符惩罚
            except:
                pass

        return score