"""配置加载。

集中读取环境变量(12-factor),不散落 os.getenv 在业务代码里。
本期只放骨架必需项:数据库连接、对象存储占位、复核阈值(留位)。
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── 数据库 ────────────────────────────────────────────────
    # 应用运行时连接(理应用回收了 UPDATE/DELETE 的 app_role,见迁移 REVOKE)
    database_url: str = Field(
        default="postgresql+psycopg2://localhost:5432/balloon_platform",
        description="SQLAlchemy 连接串;compose 内指向 postgres 服务",
    )

    # ── 对象存储(OSS 占位;本期不实现真实上传)【不变量三】────────
    oss_endpoint: str = Field(default="", description="OSS endpoint,占位")
    oss_bucket: str = Field(default="", description="OSS bucket,占位")
    oss_access_key_id: str = Field(default="", description="占位")
    oss_access_key_secret: str = Field(default="", description="占位")

    # ── 打标复核阈值(留位;本期不跑打标)────────────────────────
    review_confidence_threshold: float = Field(
        default=0.6,
        description="低置信度进复核队列的阈值(租户级配置的默认值,留位)",
    )


@lru_cache
def get_settings() -> Settings:
    """进程内单例;测试可通过 env 覆盖后 get_settings.cache_clear()。"""
    return Settings()
