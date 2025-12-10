import sqlite3
import threading
from pathlib import Path

# 数据库文件都存放在 config 目录下
DB_DIR = Path(__file__).parent.parent / "config"
DB_DIR.mkdir(exist_ok=True)

# 为每个功能定义独立的数据库文件
RSS_CACHE_DB = DB_DIR / "rss_cache.db"
DOUBAN_CACHE_DB = DB_DIR / "douban_cache.db"
BANGUMI_CACHE_DB = DB_DIR / "bangumi_cache.db"
TMDB_CACHE_DB = DB_DIR / "tmdb_cache.db"

class DBManager:
    _instances = {}
    _locks = {}

    def __new__(cls, db_path):
        if db_path not in cls._instances:
            cls._instances[db_path] = super(DBManager, cls).__new__(cls)
            cls._locks[db_path] = threading.Lock()
        return cls._instances[db_path]

    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = None

    def get_conn(self):
        # 每个线程使用自己的连接
        local = threading.local()
        if not hasattr(local, 'conn') or local.conn.is_closed():
            local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            local.conn.row_factory = sqlite3.Row
        return local.conn

    def execute(self, query, params=(), commit=False):
        with self._locks[self.db_path]:
            conn = self.get_conn()
            cursor = conn.cursor()
            cursor.execute(query, params)
            if commit:
                conn.commit()
            return cursor

    def fetchall(self, query, params=()):
        cursor = self.execute(query, params)
        return cursor.fetchall()

    def fetchone(self, query, params=()):
        cursor = self.execute(query, params)
        return cursor.fetchone()

    def close(self):
        conn = self.get_conn()
        if conn:
            conn.close()

def init_databases():
    # 初始化 RSS 缓存数据库
    rss_db = DBManager(RSS_CACHE_DB)
    rss_db.execute("""
    CREATE TABLE IF NOT EXISTS rss_cache (
        url TEXT PRIMARY KEY,
        content TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """, commit=True)

    # 初始化豆瓣缓存和映射数据库
    douban_db = DBManager(DOUBAN_CACHE_DB)
    douban_db.execute("""
    CREATE TABLE IF NOT EXISTS douban_api_cache (
        douban_id TEXT PRIMARY KEY,
        api_response TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """, commit=True)
    douban_db.execute("""
    CREATE TABLE IF NOT EXISTS douban_tmdb_mapping (
        douban_id TEXT PRIMARY KEY,
        tmdb_id TEXT,
        media_type TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """, commit=True)

    # 初始化 Bangumi 缓存和映射数据库
    bangumi_db = DBManager(BANGUMI_CACHE_DB)
    bangumi_db.execute("""
    CREATE TABLE IF NOT EXISTS bangumi_api_cache (
        bangumi_id TEXT PRIMARY KEY,
        api_response TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """, commit=True)
    bangumi_db.execute("""
    CREATE TABLE IF NOT EXISTS bangumi_tmdb_mapping (
        bangumi_id TEXT PRIMARY KEY,
        tmdb_id TEXT,
        media_type TEXT,
        match_method TEXT,
        score REAL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """, commit=True)

    # 初始化 TMDB 缓存数据库
    tmdb_db = DBManager(TMDB_CACHE_DB)
    tmdb_db.execute("""
    CREATE TABLE IF NOT EXISTS tmdb_cache (
        tmdb_id TEXT PRIMARY KEY,
        media_type TEXT,
        data TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """, commit=True)
    
    # 初始化 RSS 虚拟库项目数据库
    rss_library_db = DBManager(DB_DIR / "rss_library_items.db")
    rss_library_db.execute("""
    CREATE TABLE IF NOT EXISTS rss_library_items (
        library_id TEXT,
        tmdb_id TEXT,
        media_type TEXT,
        emby_item_id TEXT, -- 新增：用于存储在 Emby 中匹配到的 Item ID
        PRIMARY KEY (library_id, tmdb_id)
    )
    """, commit=True)

    # --- 安全地为旧表添加新列 ---
    try:
        cursor = rss_library_db.execute("PRAGMA table_info(rss_library_items)")
        columns = [row['name'] for row in cursor.fetchall()]
        if 'emby_item_id' not in columns:
            print("Adding 'emby_item_id' column to 'rss_library_items' table.")
            rss_library_db.execute("ALTER TABLE rss_library_items ADD COLUMN emby_item_id TEXT", commit=True)
    except Exception as e:
        print(f"Error updating rss_library_items table schema: {e}")

# 在模块加载时执行初始化
init_databases()
