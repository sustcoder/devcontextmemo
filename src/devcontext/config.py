"""全局配置管理 — pydantic-settings。

从环境变量和配置文件加载应用配置。
"""

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """devContextMemo 全局配置。"""

    model_config = {"env_prefix": "DEVCONTEXT_", "env_file": ".env"}

    # 数据库
    db_path: str = ".devContextMemo/devcontextmemo.db"

    # LLM
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.minimax.chat/v1"
    llm_model: str = "MiniMax-Text-01"

    # 服务
    host: str = "127.0.0.1"
    port: int = 9020

    # 路径（三目录设计：staging/knowledge/deprecated + V5 quarantined）
    knowledge_dir: str = ".devContextMemo/knowledge"
    staging_dir: str = ".devContextMemo/staging"
    deprecated_dir: str = ".devContextMemo/deprecated"
    quarantined_dir: str = ".devContextMemo/quarantined"
    raw_dir: str = "~/.devcontext/raw"
    resources_dir: str = ".devContextMemo/resources"

    # V1.7 冲突仲裁阈值（可配置，V9 修补）
    arbitration_auto_adopt_threshold: float = 0.30
    arbitration_manual_review_threshold: float = 0.10
    arbitration_dual_discard_threshold: float = 0.40

    # 采集配置
    opencode_db_path: str = "~/.local/share/opencode/opencode.db"
    poll_interval_ms: int = 500
    buffer_max_messages: int = 200
    buffer_max_tokens: int = 6000

    # 攒批配置
    batch_token_threshold: int = 6000
    batch_max_age_minutes: int = 30

    # 文件系统采集配置
    filesystem_scan_paths: list[str] = Field(default_factory=list)
    filesystem_file_patterns: list[str] = Field(default_factory=lambda: ["*.jsonl", "*.md", "*.yaml"])

    # 通用 SQLite 数据源配置
    generic_sqlite_sources: list[dict] = Field(default_factory=list)


settings = Settings()
