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

    # ── 行业包 ─────────────────────────────────────────────────
    # 选用 packs/<id>/。切换整套分类体系/提示词/UI 文案/演示数据集只改这一项。
    industry_pack: str = Field(default="template", description="行业包 id(packs/ 下的目录名)")
    packs_dir: str = Field(default="", description="行业包根目录;空 = 仓库内 packs/")

    # ── 数据库 ────────────────────────────────────────────────
    # 应用运行时连接(理应用回收了 UPDATE/DELETE 的 app_role,见迁移 REVOKE)
    database_url: str = Field(
        default="postgresql+psycopg2://localhost:5432/asset_library",
        description="SQLAlchemy 连接串;compose 内指向 postgres 服务",
    )

    # ── 对象存储 ───────────────────────────────────────────────
    # backend: 'local'(开发/CI,字节落盘)| 'oss'(生产占位)。业务层只见 asset_id【不变量三】。
    storage_backend: str = Field(default="local", description="local|oss")
    local_storage_root: str = Field(
        default="/tmp/assetlib-storage",
        description="local backend 的落盘根目录;key 规则仍是 {tenant}/{asset}/...",
    )
    oss_endpoint: str = Field(default="", description="OSS endpoint,占位")
    oss_bucket: str = Field(default="", description="OSS bucket,占位")
    oss_access_key_id: str = Field(default="", description="占位")
    oss_access_key_secret: str = Field(default="", description="占位")

    # ── 打标引擎(Qwen-VL,OpenAI 兼容)。密钥只从环境变量取,不入库不入代码 ──
    dashscope_api_key: str = Field(default="", description="百炼 DASHSCOPE_API_KEY;CI 不设(全 mock)")
    qwen_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        description="OpenAI 兼容 endpoint",
    )

    # ── 打标复核阈值兜底(权威值在当期 config_version.payload.review_threshold)────
    review_confidence_threshold: float = Field(
        default=0.6,
        description="复核阈值兜底默认;正式取值经 active_config 读 payload.review_threshold",
    )


@lru_cache
def get_settings() -> Settings:
    """进程内单例;测试可通过 env 覆盖后 get_settings.cache_clear()。"""
    return Settings()
