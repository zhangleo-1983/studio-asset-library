"""词表对齐:给 demo 租户按目标用户的素材风格补词条(受约束维度,取自当前行业包)。

**这是填 seed 数据,不是改代码**。给某个用户做专属演示前,先把其常出现、但不在包内词表里的词补进来,
避免大面积 unresolved。

只增不改:向当期生效词表版本追加新 concept_key(不动任何已冻结概念键;裁决四只禁改、不禁增)。
用法:
  python scripts/demo_vocab_add.py --dim <维度键> --key <ASCII concept_key> --zh <中文词形>
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.active_config import current_config  # noqa: E402
from app.db import platform_session  # noqa: E402
from app.demo import DEMO_TENANT  # noqa: E402
from app.events import record_event  # noqa: E402
from app.packs import get_pack  # noqa: E402

CONSTRAINED = get_pack().constrained_dimensions


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dim", required=True, choices=CONSTRAINED or None)
    ap.add_argument("--key", required=True, help="ASCII concept_key")
    ap.add_argument("--zh", required=True, help="中文词形")
    ap.add_argument("--color-kind", default=None, choices=[None, "simple", "compound"])
    args = ap.parse_args()

    if not args.key.isascii():
        raise SystemExit("concept_key 必须 ASCII")

    with platform_session(reason=f"demo:vocab_add:{args.dim}:{args.key}") as s:
        cfg = current_config(s, DEMO_TENANT, "tagging")
        if not cfg:
            raise SystemExit("demo 租户无当期配置,请先 make demo-seed")
        vv = cfg["payload"]["vocab_versions"].get(args.dim)
        exists = s.execute(
            text("SELECT 1 FROM vocabulary WHERE tenant_id=:t AND dimension=:d AND vocab_version_id=:v "
                 "AND (concept_key=:k OR labels->>'zh'=:zh)"),
            {"t": DEMO_TENANT, "d": args.dim, "v": vv, "k": args.key, "zh": args.zh},
        ).first()
        if exists:
            print(f"已存在,跳过:{args.dim} {args.key}/{args.zh}")
            return
        s.execute(
            text("INSERT INTO vocabulary (tenant_id, dimension, concept_key, labels, color_kind, active, vocab_version_id) "
                 "VALUES (:t,:d,:k, CAST(:lab AS JSONB), :ck, true, :v)"),
            {"t": DEMO_TENANT, "d": args.dim, "k": args.key,
             "lab": json.dumps({"zh": args.zh}, ensure_ascii=False), "ck": args.color_kind, "v": vv},
        )
        record_event(s, tenant_id=DEMO_TENANT, event_type="config_change", actor_kind="system",
                     subject_type="vocabulary", subject_id=None,
                     payload={"action": "demo_vocab_add", "dimension": args.dim,
                              "concept_key": args.key, "zh": args.zh})
    print(f"✅ 已补词条:{args.dim} {args.key} = {args.zh}(当期版本 v_id={vv})")


if __name__ == "__main__":
    main()
