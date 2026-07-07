"""词表查询原语(当期版本内的 concept_key / labels.zh / alias 反查)。

供归一化解析链(normalize.py)与提示词注入(prompt.py)复用。所有查询都限定
(tenant, dimension, vocab_version_id) + active=true —— "当期版本且在册"是 N12 的硬前提。
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

# 受词表约束的维度(存 concept_key);theme / color_scheme 为自由文本,不入本模块。
CONSTRAINED_DIMENSIONS = ("structure", "color", "scene")


def labels_zh(session: Session, tenant_id: int, dimension: str, vocab_version_id: int) -> list[str]:
    """当期版本内、active 的中文词形列表(注入提示词用)。"""
    rows = session.execute(
        text(
            """
            SELECT labels->>'zh' FROM vocabulary
            WHERE tenant_id=:t AND dimension=:d AND vocab_version_id=:v AND active=true
              AND labels ? 'zh'
            ORDER BY concept_key
            """
        ),
        {"t": tenant_id, "d": dimension, "v": vocab_version_id},
    ).scalars().all()
    return list(rows)


def concept_key_is_active(
    session: Session, tenant_id: int, dimension: str, vocab_version_id: int, concept_key: str
) -> bool:
    """concept_key 是否存在于当期版本且 active【N12 硬前提】。"""
    return session.execute(
        text(
            """
            SELECT 1 FROM vocabulary
            WHERE tenant_id=:t AND dimension=:d AND vocab_version_id=:v
              AND concept_key=:ck AND active=true
            """
        ),
        {"t": tenant_id, "d": dimension, "v": vocab_version_id, "ck": concept_key},
    ).first() is not None


def concept_key_by_zh(
    session: Session, tenant_id: int, dimension: str, vocab_version_id: int, zh: str
) -> Optional[str]:
    """当期版本内 labels.zh 词形 → concept_key(唯一,靠 vocabulary_zh_uq 保证)。"""
    row = session.execute(
        text(
            """
            SELECT concept_key FROM vocabulary
            WHERE tenant_id=:t AND dimension=:d AND vocab_version_id=:v
              AND active=true AND labels->>'zh'=:zh
            """
        ),
        {"t": tenant_id, "d": dimension, "v": vocab_version_id, "zh": zh},
    ).first()
    return None if row is None else row[0]


def concept_key_by_alias(
    session: Session, tenant_id: int, dimension: str, alias: str
) -> Optional[str]:
    """别名词形 → concept_key(alias_map 无版本维,命中后仍须校验当期在册 —— N12)。"""
    row = session.execute(
        text(
            "SELECT concept_key FROM alias_map WHERE tenant_id=:t AND dimension=:d AND alias=:a"
        ),
        {"t": tenant_id, "d": dimension, "a": alias},
    ).first()
    return None if row is None else row[0]
