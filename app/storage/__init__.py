"""对象存储适配层。【不变量三】

业务层只见 asset_id + 内容 hash,永不见路径/文件名。换供应商只改本包的实现类。
"""
from functools import lru_cache

from app.config import get_settings
from app.storage.base import StorageBackend, StorageObject
from app.storage.local import LocalStorageBackend
from app.storage.oss import OSSStorageBackend

__all__ = [
    "StorageBackend",
    "StorageObject",
    "OSSStorageBackend",
    "LocalStorageBackend",
    "get_storage_backend",
]


@lru_cache
def get_storage_backend() -> StorageBackend:
    """按配置选择存储后端。业务层调用它,不直接 new 具体实现。"""
    backend = get_settings().storage_backend.lower()
    if backend == "oss":
        return OSSStorageBackend()
    if backend == "local":
        return LocalStorageBackend()
    raise ValueError(f"未知 storage_backend={backend!r}(应为 local|oss)")
