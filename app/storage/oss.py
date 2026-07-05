"""阿里云 OSS 实现(占位)。

本期只落 key 推导规则与接口契约,不接真实 OSS SDK(打标/上传闭环属后续阶段)。
key 规则集中在此:`{tenant_id}/{asset_id}/{original|thumb}.ext`(architecture §3.1 存储层)。
真实实现时把 `oss2` 客户端塞进各方法体,签名与 key 规则不变。
"""
from __future__ import annotations

from app.config import get_settings
from app.storage.base import StorageBackend, StorageObject


class OSSStorageBackend(StorageBackend):
    def __init__(self, bucket: str | None = None, endpoint: str | None = None) -> None:
        settings = get_settings()
        self.bucket = bucket or settings.oss_bucket
        self.endpoint = endpoint or settings.oss_endpoint

    # ── key 规则(唯一推导点)────────────────────────────────
    @staticmethod
    def _original_key(tenant_id: int, asset_id: int, original_ext: str) -> str:
        ext = original_ext.lstrip(".").lower()
        return f"{tenant_id}/{asset_id}/original.{ext}"

    @staticmethod
    def _thumb_key(tenant_id: int, asset_id: int) -> str:
        return f"{tenant_id}/{asset_id}/thumb.jpg"

    # ── 接口实现(占位;抛 NotImplementedError,签名与契约已定)──
    def put(
        self,
        tenant_id: int,
        asset_id: int,
        content: bytes,
        *,
        mime_type: str,
        original_ext: str,
    ) -> str:
        key = self._original_key(tenant_id, asset_id, original_ext)
        raise NotImplementedError(
            f"OSS 上传未接入(骨架期):将写入 key={key}(len={len(content)}, {mime_type})"
        )

    def get(self, tenant_id: int, asset_id: int, *, original_ext: str) -> StorageObject:
        key = self._original_key(tenant_id, asset_id, original_ext)
        raise NotImplementedError(f"OSS 读取未接入(骨架期):key={key}")

    def presign(
        self, tenant_id: int, asset_id: int, *, original_ext: str, expires_s: int = 3600
    ) -> str:
        key = self._original_key(tenant_id, asset_id, original_ext)
        raise NotImplementedError(f"OSS 签名 URL 未接入(骨架期):key={key}, ttl={expires_s}")

    def thumbnail_url(
        self,
        tenant_id: int,
        asset_id: int,
        *,
        width: int = 400,
        thumb_key: str | None = None,
        original_ext: str = "jpg",
    ) -> str:
        # 【Q4】thumb_key 非空 = 预生成派生物;否则对 original 挂 OSS 图片处理参数实时缩放。
        key = thumb_key or self._original_key(tenant_id, asset_id, original_ext)
        raise NotImplementedError(
            f"OSS 缩略图 URL 未接入(骨架期):key={key}, w={width}, 预生成={thumb_key is not None}"
        )
