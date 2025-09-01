# src/proxy_handlers/_filter_translator.py (新文件)

import logging
from typing import List, Dict, Any, Tuple
from models import AdvancedFilterRule

logger = logging.getLogger(__name__)

# 映射我们的操作符到 Emby API 的过滤器名称后缀
# 例如： 'equals' -> 'Is', 'contains' -> 'Contains' (虽然不常用), 'greater_than' -> 'GreaterThan'
# 注意：Emby 对参数名的大小写敏感。
OPERATOR_MAP = {
    "equals": "Is",
    "not_equals": "IsNot",
    "contains": "Contains",
    "greater_than": "GreaterThan",
    "less_than": "LessThan",
}

# 映射我们的字段到 Emby API 的查询参数
# Key 是我们在前端定义的 field, Value 是对应的 Emby API 参数 (或元组)
# 对于 'greater_than'/'less_than'，我们使用 (Min-Param, Max-Param) 的元组
FIELD_MAP = {
    "CommunityRating": ("MinCommunityRating", "MaxCommunityRating"),
    "CriticRating": ("MinCriticRating", "MaxCriticRating"),
    "OfficialRating": "OfficialRatings",
    "ProductionYear": ("MinPremiereDate", "MaxPremiereDate"), # 将年份转换为日期
    "Genres": "Genres",
    "Tags": "Tags",
    "Studios": "Studios",
    "VideoRange": "VideoTypes", # 例如 'HDR', 'SDR'
    "Container": "Containers",
    "NameStartsWith": "NameStartsWith",
    "SeriesStatus": "SeriesStatus",
    # 布尔类型的特殊字段
    "IsMovie": "IsMovie",
    "IsSeries": "IsSeries",
    "IsPlayed": "IsPlayed",
    "IsUnplayed": "IsUnplayed",
    "HasSubtitles": "HasSubtitles",
    "HasOfficialRating": "HasOfficialRating",
    # 存在性检查
    "ProviderIds.Tmdb": "HasTmdbId",
    "ProviderIds.Imdb": "HasImdbId",
}

def translate_rules(rules: List[AdvancedFilterRule]) -> Tuple[Dict[str, Any], List[AdvancedFilterRule]]:
    """
    将高级筛选规则列表翻译成 Emby 原生 API 参数和需要后筛选的规则。

    Args:
        rules: 从前端传来的高级筛选规则列表。

    Returns:
        一个元组，包含:
        - emby_native_params: 一个可以直接用于 aiohttp 请求的字典。
        - post_filter_rules: 一个无法被翻译，需要代理端进行后筛选的规则列表。
    """
    emby_native_params = {}
    post_filter_rules = []

    for rule in rules:
        field = rule.field
        operator = rule.operator
        value = rule.value
        translated = False

        if operator == "is_not_empty":
            if field in FIELD_MAP and isinstance(FIELD_MAP[field], str) and FIELD_MAP[field].startswith("Has"):
                emby_native_params[FIELD_MAP[field]] = "true"
                translated = True
        
        elif operator == "is_empty":
             if field in FIELD_MAP and isinstance(FIELD_MAP[field], str) and FIELD_MAP[field].startswith("Has"):
                emby_native_params[FIELD_MAP[field]] = "false"
                translated = True

        elif field in FIELD_MAP:
            param_template = FIELD_MAP[field]
            
            # 处理范围查询 (Min/Max)
            if isinstance(param_template, tuple):
                min_param, max_param = param_template
                if operator == "greater_than":
                    param_name = min_param
                elif operator == "less_than":
                    param_name = max_param
                elif operator == "equals":
                    # 对于年份的精确匹配，需要设置Min和Max为同一年
                    if field == "ProductionYear":
                        emby_native_params[min_param] = f"{value}-01-01T00:00:00.000Z"
                        emby_native_params[max_param] = f"{value}-12-31T23:59:59.999Z"
                        translated = True
                    else: # 其他字段的 equals
                        param_name = f"{param_template[0].replace('Min','')}" # 假设是 CommunityRating
                else:
                    param_name = None
                
                if not translated and param_name:
                    # 对年份特殊处理，转换为完整的日期时间格式
                    if field == "ProductionYear":
                        # aiohttp 会自动编码，这里不需要手动处理
                        emby_native_params[param_name] = f"{value}-01-01T00:00:00.000Z" if operator == "greater_than" else f"{value}-12-31T23:59:59.999Z"
                    else:
                        emby_native_params[param_name] = value
                    translated = True
            
            # 处理直接映射的字段
            elif isinstance(param_template, str):
                emby_native_params[param_template] = value
                translated = True

        if not translated:
            logger.info(f"高级筛选规则无法翻译，将进行后筛选: {rule.field} {rule.operator} {rule.value}")
            post_filter_rules.append(rule)
        else:
            logger.info(f"高级筛选规则已成功翻译为原生参数: {rule.field} -> {emby_native_params}")

    return emby_native_params, post_filter_rules
