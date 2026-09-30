"""归一化解析链(A-4 / A-6 / N12)。【不变量二 · 承重路径】

模型输出中文词形 → 落库 concept_key,规则(受约束维度,由行业包声明):

    1. 先查 alias_map(别名 → concept_key);
    2. 未命中再查当期 vocabulary.labels.zh(词形 → concept_key);
    3. 命中后**必须**校验该 concept_key 存在于当期 vocab_version 且 active=true【N12】;
    4. 通过 → (concept_key, 'active');
    5. 任一步失败(两处都查不到,或命中的 concept_key 不在当期在册)→ 走 A-6 失败路径:
       value 存**裸原词形**(concept_key 强制 ASCII,中文词形天然不冒充概念键,不加 raw: 前缀)、
       status='unresolved'、needs_review=true,进复核队列待人工归类。

自由文本维不入本链:value=原词形、status='active'。
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.tagging import vocab


@dataclass(frozen=True)
class Resolved:
    value: str          # 落 tag.value:concept_key(成功)或裸原词形(unresolved)
    status: str         # 'active' | 'unresolved'
    needs_review: bool


def resolve(
    session: Session,
    tenant_id: int,
    dimension: str,
    raw_word: str,
    vocab_version_id: int,
) -> Resolved:
    """把一个受约束维度的中文词形解析为落库形态。"""
    if dimension not in vocab.constrained_dimensions():
        raise ValueError(f"{dimension} 非受约束维度,不应走归一化链(自由文本维)")

    word = (raw_word or "").strip()
    if not word:
        # 空词形:视为反查失败,交人工(不静默丢)。
        return Resolved(value=raw_word, status="unresolved", needs_review=True)

    # 1) alias_map → concept_key
    candidate = vocab.concept_key_by_alias(session, tenant_id, dimension, word)
    # 2) 未命中再查当期 labels.zh → concept_key
    if candidate is None:
        candidate = vocab.concept_key_by_zh(session, tenant_id, dimension, vocab_version_id, word)

    # 3) N12:命中的 concept_key 必须在当期版本且 active
    if candidate is not None and vocab.concept_key_is_active(
        session, tenant_id, dimension, vocab_version_id, candidate
    ):
        return Resolved(value=candidate, status="active", needs_review=False)

    # 5) A-6 失败路径:裸原词形 + unresolved
    return Resolved(value=word, status="unresolved", needs_review=True)
