"""词表对齐(演示前置 SOP):给 demo 租户按目标工作室的作品风格补词条。

**这是填 seed 数据,不是改代码**(零级验证不解冻开发)。杀手锏(给某工作室做专属选款页)前,
先把它常出现、但不在 28 词表里的造型/场景/配色补进来,避免大面积 unresolved 砸场。

只增不改:向当期生效词表版本追加新 concept_key(不动任何已冻结概念键;裁决四只禁改、不禁增)。
用法:
  python scripts/demo_vocab_add.py --dim structure --key backdrop --zh 背景墙
  python scripts/demo_vocab_add.py --dim structure --key table_arrangement --zh 桌花
  python scripts/demo_vocab_add.py --dim scene --key opening_ceremony --zh 开工大吉
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

CONSTRAINED = ("structure", "color", "scene")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dim", required=True, choices=CONSTRAINED)
    ap.add_argument("--key", required=True, help="ASCII concept_key,如 backdrop")
    ap.add_argument("--zh", required=True, help="中文词形,如 背景墙")
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
