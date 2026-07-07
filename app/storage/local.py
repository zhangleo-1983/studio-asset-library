"""本地文件系统 StorageBackend(开发/CI/单机 demo)。【不变量三】

同样以 {tenant_id}/{asset_id}/original.ext 为 key、业务层只见 asset_id;只是把字节落到
本地磁盘而非 OSS。换回 OSS 只改工厂选择,业务代码零改动——这正是 StorageBackend 抽象的意义。
"""
from __future__ import annotations

from pathlib import Path

from app.config import get_settings
from app.storage.base import StorageBackend, StorageObject


class LocalStorageBackend(StorageBackend):
    def __init__(self, root: str | None = None) -> None:
        self.root = Path(root or get_settings().local_storage_root)

    def _path(self, tenant_id: int, asset_id: int, ext: str) -> Path:
        return self.root / str(tenant_id) / str(asset_id) / f"original.{ext.lstrip('.').lower()}"

    @staticmethod
    def _key(tenant_id: int, asset_id: int, ext: str) -> str:
        return f"{tenant_id}/{asset_id}/original.{ext.lstrip('.').lower()}"

    def put(
        self, tenant_id: int, asset_id: int, content: bytes, *, mime_type: str, original_ext: str
    ) -> str:
        p = self._path(tenant_id, asset_id, original_ext)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        return self._key(tenant_id, asset_id, original_ext)

    def get(self, tenant_id: int, asset_id: int, *, original_ext: str) -> StorageObject:
        p = self._path(tenant_id, asset_id, original_ext)
        data = p.read_bytes()
        return StorageObject(content=data, mime_type="application/octet-stream", byte_size=len(data))

    def presign(
        self, tenant_id: int, asset_id: int, *, original_ext: str, expires_s: int = 3600
    ) -> str:
        return self._path(tenant_id, asset_id, original_ext).as_uri()

    def thumbnail_url(
        self,
        tenant_id: int,
        asset_id: int,
        *,
        width: int = 400,
        thumb_key: str | None = None,
        original_ext: str = "jpg",
    ) -> str:
        # 本地后端不做实时图片处理,直接回原图 URI(缩略图墙属两端 UI,本期不做)。
        return self._path(tenant_id, asset_id, original_ext).as_uri()
