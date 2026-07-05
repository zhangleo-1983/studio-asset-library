"""StorageBackend 接口。【不变量三:资产与标签分离,业务不依赖路径】

四个方法:put / get / presign / thumbnail_url。
关键约束:方法签名以 (tenant_id, asset_id) 为输入,storage_key 由 backend 内部按
`{tenant_id}/{asset_id}/...` 规则推导,**不向业务层暴露路径**。asset.storage_key 列只是
这条推导规则的缓存,不作业务依赖(见 data-model §3.2)。换 OSS/七牛/本地只换实现。
"""
from __future__ import annotations

import abc
from dataclasses import dataclass


@dataclass(frozen=True)
class StorageObject:
    """一次 get 的结果。不含任何"业务可依赖"的路径语义。"""

    content: bytes
    mime_type: str
    byte_size: int


class StorageBackend(abc.ABC):
    """存储供应商适配接口。业务层只通过 asset_id 访问资产。"""

    @abc.abstractmethod
    def put(
        self,
        tenant_id: int,
        asset_id: int,
        content: bytes,
        *,
        mime_type: str,
        original_ext: str,
    ) -> str:
        """上传原图,返回 storage_key(仅供落 asset.storage_key 缓存,业务勿依赖)。"""

    @abc.abstractmethod
    def get(self, tenant_id: int, asset_id: int, *, original_ext: str) -> StorageObject:
        """按 (tenant_id, asset_id) 取原图字节。"""

    @abc.abstractmethod
    def presign(
        self, tenant_id: int, asset_id: int, *, original_ext: str, expires_s: int = 3600
    ) -> str:
        """签发原图的临时可访问 URL。API 只吐这个,不吐 storage_key【A-5/Q8】。"""

    @abc.abstractmethod
    def thumbnail_url(
        self,
        tenant_id: int,
        asset_id: int,
        *,
        width: int = 400,
        thumb_key: str | None = None,
        original_ext: str = "jpg",
    ) -> str:
        """缩略图 URL。【Q4】默认由 OSS 图片处理参数实时生成;仅当源格式不支持、
        入库时预生成了派生物(thumb_key 非空)才走预生成对象。"""
