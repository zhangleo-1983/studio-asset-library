"""单张打标执行 + 落 tag(完整溯源)。【不变量二 · 承重路径】

流程(architecture §3.3):
  取当期配置(经 active_config,禁止取最新/硬编码【裁决七】)→ 取图 → 注入当期词表调 provider →
  模型原始输出**原样**落 task.output → coerce 兜底 → 归一化解析 → 落 tag(六项溯源,裁决八按维度)。

批量取任务用 PG FOR UPDATE SKIP LOCKED(见 run_batch)。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.active_config import current_config
from app.context import get_current_tenant
from app.db import tenant_session
from app.events import record_event
from app.schemas import TAGGING_OUTPUT_SCHEMA_VERSION, TaggingOutput
from app.storage import get_storage_backend
from app.tagging import normalize
from app.tagging.parse import ParseError, extract_json_obj, to_tagging_output
from app.tagging.prompt import PROMPT_VERSION, render_prompt
from app.tagging.provider import TaggingProvider
from app.tagging.vocab import CONSTRAINED_DIMENSIONS, labels_zh

logger = logging.getLogger("balloon.tagging")


class TaggingFailure(Exception):
    """打标失败(provider 或解析)。携带需持久化到 task 的碎片,由批量层在独立事务落库。

    不在 process_task 的会话里写 failed —— 那会随 raise 一起回滚。
    """

    def __init__(
        self,
        reason: str,
        *,
        raw_text: Optional[str] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: int = 0,
        model_id: Optional[str] = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.raw_text = raw_text
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.latency_ms = latency_ms
        self.model_id = model_id


@dataclass(frozen=True)
class TagWrite:
    dimension: str
    value: str
    role: Optional[str]
    status: str
    needs_review: bool


def enqueue_tagging_task(asset_id: int, run_id: str) -> int:
    """建一条 pending 打标任务。返回 task_id。"""
    tenant_id = get_current_tenant()
    with tenant_session() as session:
        return int(
            session.execute(
                text(
                    """
                    INSERT INTO task (tenant_id, task_type, asset_id, run_id, status)
                    VALUES (:t, 'tagging', :a, :r, 'pending')
                    RETURNING task_id
                    """
                ),
                {"t": tenant_id, "a": asset_id, "r": run_id},
            ).scalar_one()
        )


def claim_next_task(session: Session, tenant_id: int) -> Optional[int]:
    """PG 队列:取一条 pending tagging 任务并置 running。FOR UPDATE SKIP LOCKED 支持多 worker 并发。"""
    row = session.execute(
        text(
            """
            SELECT task_id FROM task
            WHERE tenant_id = :t AND task_type = 'tagging' AND status = 'pending'
            ORDER BY task_id
            FOR UPDATE SKIP LOCKED
            LIMIT 1
            """
        ),
        {"t": tenant_id},
    ).first()
    if row is None:
        return None
    task_id = int(row[0])
    session.execute(
        text("UPDATE task SET status='running' WHERE task_id=:id AND tenant_id=:t"),
        {"id": task_id, "t": tenant_id},
    )
    return task_id


def _plan_tags(out: TaggingOutput) -> list[tuple[str, str, Optional[str]]]:
    """把 TaggingOutput 摊平成 (dimension, raw_word, role) 列表。role 仅 color 维有值。"""
    plan: list[tuple[str, str, Optional[str]]] = []
    for w in out.structure_types:
        plan.append(("structure", w, None))
    for w in out.color_scheme.primary:
        plan.append(("color", w, "primary"))
    for w in out.color_scheme.accent:
        plan.append(("color", w, "accent"))
    if out.scene_guess:
        plan.append(("scene", out.scene_guess, None))
    if out.theme:  # 自由文本;theme=null 则不落标签
        plan.append(("theme", out.theme, None))
    if out.color_scheme.scheme_name:
        plan.append(("color_scheme", out.color_scheme.scheme_name, None))
    return plan


def _insert_model_tag(
    session: Session,
    *,
    tenant_id: int,
    asset_id: int,
    task_id: int,
    tw: TagWrite,
    model_id: str,
    config_version_id: int,
    run_id: str,
    input_hash: str,
    vocab_version_id: Optional[int],
    confidence: Optional[float],
    input_tokens: Optional[int],
    output_tokens: Optional[int],
) -> None:
    session.execute(
        text(
            """
            INSERT INTO tag
                (tenant_id, asset_id, task_id, dimension, value, role, status,
                 source, model_id, prompt_version, vocab_version_id, config_version_id,
                 run_id, input_hash, input_tokens, output_tokens, confidence, needs_review)
            VALUES
                (:t, :a, :task, :dim, :val, :role, :status,
                 'model', :model, :pv, :vv, :cv,
                 :run, :ih, :itok, :otok, :conf, :nr)
            """
        ),
        {
            "t": tenant_id, "a": asset_id, "task": task_id, "dim": tw.dimension,
            "val": tw.value, "role": tw.role, "status": tw.status,
            "model": model_id, "pv": PROMPT_VERSION, "vv": vocab_version_id, "cv": config_version_id,
            "run": run_id, "ih": input_hash, "itok": input_tokens, "otok": output_tokens,
            "conf": confidence, "nr": tw.needs_review,
        },
    )


def process_task(session: Session, task_id: int, provider: TaggingProvider) -> int:
    """处理一条已 claim 的任务:调 provider、落 output、落 tag、落 event。返回落库 tag 数。

    在传入的 session/事务内完成(调用方负责 commit)。失败时置 task.failed 并抛出。
    """
    tenant_id = get_current_tenant()

    # 1) 当期配置(唯一入口;禁止取最新 created_at)【裁决七】
    cfg = current_config(session, tenant_id, "tagging")
    if cfg is None:
        raise RuntimeError(f"租户 {tenant_id} 无当期 tagging 配置")
    payload = cfg["payload"]
    model_id = payload["model"]
    vocab_versions = payload["vocab_versions"]  # {structure,color,scene}
    config_version_id = cfg["config_version_id"]

    # 2) 任务与资产
    trow = session.execute(
        text("SELECT asset_id, run_id FROM task WHERE task_id=:id AND tenant_id=:t"),
        {"id": task_id, "t": tenant_id},
    ).first()
    asset_id, run_id = int(trow[0]), trow[1]
    arow = session.execute(
        text("SELECT content_hash, storage_key FROM asset WHERE asset_id=:a AND tenant_id=:t"),
        {"a": asset_id, "t": tenant_id},
    ).first()
    content_hash, storage_key = arow[0], arow[1]
    original_ext = storage_key.rsplit(".", 1)[-1] if "." in storage_key else "jpg"
    image_bytes = get_storage_backend().get(tenant_id, asset_id, original_ext=original_ext).content

    # 3) 注入当期词表调模型
    color_zh = labels_zh(session, tenant_id, "color", vocab_versions["color"])
    structure_zh = labels_zh(session, tenant_id, "structure", vocab_versions["structure"])
    prompt = render_prompt(color_zh, structure_zh)

    try:
        result = provider.call(image_bytes, prompt)
    except Exception as e:
        # 失败落库交批量层(独立事务),避免与本会话 raise 一起回滚。
        raise TaggingFailure(str(e)[:2000], model_id=model_id) from e

    # 4) 原始输出原样落 output;解析经 coerce 兜底
    try:
        raw_obj = extract_json_obj(result.text)
    except ParseError as e:
        # 连 JSON 都不是:原文交批量层保留(不静默丢原始输出)。
        raise TaggingFailure(
            f"parse:{e}", raw_text=result.text, input_tokens=result.input_tokens,
            output_tokens=result.output_tokens, latency_ms=result.latency_ms, model_id=model_id,
        ) from e

    out = to_tagging_output(raw_obj)

    # 5) task 收尾:output = {_raw_text(模型全文原样), parsed(提取后对象)},token 累计【N7】
    #    【P2-3】成功/失败两条路径统一结构,原始全文一律保全(不丢代码围栏外文字)。
    session.execute(
        text(
            """
            UPDATE task SET status='done', finished_at=now(),
                output = CAST(:raw AS JSONB), output_schema_version=:osv, model_id=:m,
                input_tokens = COALESCE(input_tokens,0) + :it,
                output_tokens = COALESCE(output_tokens,0) + :ot,
                latency_ms=:lat, retry_count = retry_count + :ret
            WHERE task_id=:id AND tenant_id=:t
            """
        ),
        {"raw": json.dumps({"_raw_text": result.text, "parsed": raw_obj}, ensure_ascii=False),
         "osv": TAGGING_OUTPUT_SCHEMA_VERSION,
         "m": model_id, "it": result.input_tokens, "ot": result.output_tokens,
         "lat": result.latency_ms, "ret": result.retries, "id": task_id, "t": tenant_id},
    )

    # 6) 落 tag:归一化 + 六项溯源(裁决八:受约束维记 vocab_version_id,自由文本维置 NULL)
    n = 0
    for dimension, raw_word, role in _plan_tags(out):
        if dimension in CONSTRAINED_DIMENSIONS:
            vv = vocab_versions[dimension]
            r = normalize.resolve(session, tenant_id, dimension, raw_word, vv)
            tw = TagWrite(dimension=dimension, value=r.value, role=role,
                          status=r.status, needs_review=r.needs_review or bool(out.needs_review))
            vocab_version_id: Optional[int] = vv
        else:
            # 自由文本维(theme/color_scheme):value=原词形,active,vocab_version_id 必为空【裁决八】
            tw = TagWrite(dimension=dimension, value=raw_word, role=role,
                          status="active", needs_review=bool(out.needs_review))
            vocab_version_id = None
        _insert_model_tag(
            session, tenant_id=tenant_id, asset_id=asset_id, task_id=task_id, tw=tw,
            model_id=model_id, config_version_id=config_version_id, run_id=run_id,
            input_hash=content_hash, vocab_version_id=vocab_version_id,
            confidence=out.confidence, input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )
        n += 1

    # 7) 打标完成事件(system;非敏感)
    record_event(
        session, tenant_id=tenant_id, event_type="tagging_done", actor_kind="system",
        subject_type="task", subject_id=task_id,
        payload={"run_id": run_id, "asset_id": asset_id, "n_tags": n},
    )
    return n


def _persist_failure(tenant_id: int, task_id: int, f: "TaggingFailure") -> None:
    """在独立事务里把失败落到 task(含原始输出碎片),不受处理事务回滚影响。"""
    output_sql = "output = CAST(:raw AS JSONB)," if f.raw_text is not None else ""
    with tenant_session() as session:
        session.execute(
            text(
                f"""
                UPDATE task SET status='failed', error=:err, finished_at=now(),
                    retry_count = retry_count + 1, {output_sql}
                    output_schema_version=:osv, model_id=:m,
                    input_tokens = COALESCE(input_tokens,0) + :it,
                    output_tokens = COALESCE(output_tokens,0) + :ot, latency_ms=:lat
                WHERE task_id=:id AND tenant_id=:t
                """
            ),
            {
                "err": f.reason[:2000],
                "raw": json.dumps({"_raw_text": f.raw_text}, ensure_ascii=False),
                "osv": TAGGING_OUTPUT_SCHEMA_VERSION, "m": f.model_id,
                "it": f.input_tokens, "ot": f.output_tokens, "lat": f.latency_ms,
                "id": task_id, "t": tenant_id,
            },
        )


def run_once(provider: TaggingProvider) -> Optional[int]:
    """认领并处理一条任务。返回处理的 task_id;无 pending 返回 None。"""
    tenant_id = get_current_tenant()
    with tenant_session() as session:
        task_id = claim_next_task(session, tenant_id)  # claim 提交后该行不再 pending(resume 天然跳过)
    if task_id is None:
        return None
    try:
        with tenant_session() as session:
            process_task(session, task_id, provider)
    except TaggingFailure as f:
        logger.warning("task %s 打标失败:%s", task_id, f.reason)
        _persist_failure(tenant_id, task_id, f)
    return task_id


def run_batch(provider: TaggingProvider, *, max_tasks: Optional[int] = None) -> int:
    """连续认领处理直到无 pending(或达到 max_tasks)。返回处理条数。

    并发:多 worker 各调 run_batch,claim_next_task 的 FOR UPDATE SKIP LOCKED 保证不撞单。
    重试:provider 内部指数退避;任务级失败置 failed(retry_count+1),重排由上层策略决定。
    resume:已 done/running/failed 的任务不在 pending 集合,天然跳过已完成。
    """
    processed = 0
    while max_tasks is None or processed < max_tasks:
        task_id = run_once(provider)
        if task_id is None:
            break
        processed += 1
    return processed
