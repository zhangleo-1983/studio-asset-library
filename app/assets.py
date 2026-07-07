"""资产上传入库(architecture §5,范围2)。【不变量三】

内容 hash 去重:
- 命中**已软删** asset(deleted_at 非空)→ 清空 deleted_at **恢复**该 asset(不新建、asset_id 不变)
  并落 upload 事件(restored=true)【Q3】;
- 命中**未软删** → 按普通去重跳过(不新建);
- 未命中 → 新建 asset + 落盘(StorageBackend)+ 落 upload 事件。

业务层只见 asset_id;storage_key 由 backend 按 {tenant}/{asset}/ 规则推导,是缓存不作依赖。
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text

from app.context import get_current_tenant
from app.db import tenant_session
from app.events import record_event
from app.storage import get_storage_backend


@dataclass(frozen=True)
class IngestResult:
    asset_id: int
    outcome: str          # 'created' | 'restored' | 'skipped_dup'
    content_hash: str


def _dims(content: bytes) -> tuple[Optional[int], Optional[int]]:
    try:
        from PIL import Image  # 延迟导入,mock 测试不必依赖真实图片

        with Image.open(io.BytesIO(content)) as im:
            return int(im.width), int(im.height)
    except Exception:
        return None, None


def ingest_asset(
    content: bytes,
    *,
    mime_type: str,
    original_ext: str,
    original_name: Optional[str] = None,
    uploaded_by: Optional[int] = None,
) -> IngestResult:
    tenant_id = get_current_tenant()
    content_hash = hashlib.sha256(content).hexdigest()
    actor_kind = "human" if uploaded_by is not None else "system"

    with tenant_session() as session:
        existing = session.execute(
            text(
                "SELECT asset_id, deleted_at FROM asset "
                "WHERE tenant_id=:t AND content_hash=:h"
            ),
            {"t": tenant_id, "h": content_hash},
        ).first()

        if existing is not None:
            asset_id, deleted_at = int(existing[0]), existing[1]
            if deleted_at is None:
                # 命中未删:普通去重跳过。
                return IngestResult(asset_id=asset_id, outcome="skipped_dup", content_hash=content_hash)
            # 命中已软删:恢复(asset_id 不变),落 upload 事件(restored)。
            session.execute(
                text("UPDATE asset SET deleted_at=NULL WHERE asset_id=:a AND tenant_id=:t"),
                {"a": asset_id, "t": tenant_id},
            )
            record_event(
                session, tenant_id=tenant_id, event_type="upload", actor_kind=actor_kind,
                actor_user_id=uploaded_by, subject_type="asset", subject_id=asset_id,
                payload={"content_hash": content_hash, "restored": True},
            )
            return IngestResult(asset_id=asset_id, outcome="restored", content_hash=content_hash)

        # 未命中:新建。storage_key NOT NULL,故先占位再回填(asset 非只增,可 UPDATE)。
        width, height = _dims(content)
        asset_id = int(
            session.execute(
                text(
                    """
                    INSERT INTO asset
                        (tenant_id, content_hash, byte_size, mime_type, width, height,
                         storage_key, original_name, uploaded_by)
                    VALUES (:t, :h, :sz, :mime, :w, :ht, :sk, :on, :by)
                    RETURNING asset_id
                    """
                ),
                {
                    "t": tenant_id, "h": content_hash, "sz": len(content), "mime": mime_type,
                    "w": width, "ht": height, "sk": "pending", "on": original_name, "by": uploaded_by,
                },
            ).scalar_one()
        )
        storage_key = get_storage_backend().put(
            tenant_id, asset_id, content, mime_type=mime_type, original_ext=original_ext
        )
        session.execute(
            text("UPDATE asset SET storage_key=:sk WHERE asset_id=:a AND tenant_id=:t"),
            {"sk": storage_key, "a": asset_id, "t": tenant_id},
        )
        record_event(
            session, tenant_id=tenant_id, event_type="upload", actor_kind=actor_kind,
            actor_user_id=uploaded_by, subject_type="asset", subject_id=asset_id,
            payload={"content_hash": content_hash, "restored": False},
        )
        return IngestResult(asset_id=asset_id, outcome="created", content_hash=content_hash)


def soft_delete_asset(asset_id: int, *, deleted_by: int) -> None:
    """软删资产(删除落 event)。补全 Q3 恢复路径的对侧;供 demo/测试构造已软删态。"""
    tenant_id = get_current_tenant()
    with tenant_session() as session:
        session.execute(
            text("UPDATE asset SET deleted_at=now() WHERE asset_id=:a AND tenant_id=:t"),
            {"a": asset_id, "t": tenant_id},
        )
        record_event(
            session, tenant_id=tenant_id, event_type="delete", actor_kind="human",
            actor_user_id=deleted_by, subject_type="asset", subject_id=asset_id,
            payload={"soft": True},
        )
