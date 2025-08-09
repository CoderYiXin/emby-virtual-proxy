# src/proxy_cache.py

from cachetools import TTLCache, Cache

# 创建一个全局的、线程安全的缓存实例
# - maxsize=500: 最多缓存 500 个不同的 API 响应
# - ttl=300:     每个缓存项的存活时间为 300 秒 (5 分钟)
api_cache = TTLCache(maxsize=500, ttl=300)

# 【【【 新增 】】】
# 虚拟库项目列表缓存 (用于封面生成)
# - maxsize=100: 最多缓存100个虚拟库的项目列表
# 这个缓存不需要时间过期，因为它只在用户浏览时更新
vlib_items_cache = Cache(maxsize=100)