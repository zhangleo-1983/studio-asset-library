"""对象存储适配层。【不变量三】

业务层只见 asset_id + 内容 hash,永不见路径/文件名。换供应商只改本包的实现类。
"""
from app.storage.base import StorageBackend, StorageObject
from app.storage.oss import OSSStorageBackend

__all__ = ["StorageBackend", "StorageObject", "OSSStorageBackend"]
