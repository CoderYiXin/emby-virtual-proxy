# src/models.py (Final Corrected Version)

from pydantic import BaseModel, Field, ConfigDict
from typing import List, Literal, Optional
import uuid

class AdvancedFilterRule(BaseModel):
    field: str
    operator: Literal[
        "equals", "not_equals",
        "contains", "not_contains",
        "greater_than", "less_than",
        "is_empty", "is_not_empty"
    ]
    value: Optional[str] = None

class AdvancedFilter(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    match_all: bool = Field(default=True)
    rules: List[AdvancedFilterRule] = Field(default_factory=list)

class VirtualLibrary(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    resource_type: Literal["collection", "tag", "genre", "studio", "person"]
    resource_id: str
    # image: Optional[str] = None  <-- 我们不再需要这个字段了，可以删除或注释掉
    image_tag: Optional[str] = None # <-- 【新增】用于存储图片的唯一标签
    advanced_filter_id: Optional[str] = None
    merge_by_tmdb_id: bool = Field(default=False)
    order: int = 0
    source_library: Optional[str] = None
    conditions: Optional[list] = None

class AppConfig(BaseModel):
    emby_url: str = Field(default="http://127.0.0.1:8096")
    emby_api_key: Optional[str] = Field(default="")
    log_level: Literal["debug", "info", "warn", "error"] = Field(default="info")
    display_order: List[str] = Field(default_factory=list)
    hide: List[str] = Field(default_factory=list)
    
    # 使用别名 'library' 来兼容旧的 config.json
    virtual_libraries: List[VirtualLibrary] = Field(
        default_factory=list, 
        alias="library",
        validation_alias="library" # <-- 【新增】确保加载时也优先用 'library'
    )
    
    # 明确定义 advanced_filters，不使用任何复杂的配置
    advanced_filters: List[AdvancedFilter] = Field(default_factory=list)

    # 新增：缓存开关
    enable_cache: bool = Field(default=True)

    class Config:
        # 允许从别名填充模型
        populate_by_name = True
