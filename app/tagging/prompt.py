"""打标提示词加载与注入(migration §1.1)。

- 提示词文件 prompts/tagging_v2.txt **按版本号命名、只增不改**(改内容 = 升版本号)【Q2】。
- prompt_sha256 = 提示词**本体模板**(含 {{...}} 占位符)的内容 hash,作为"在什么规则下打的"
  内容锚。占位符是模板,词表注入在运行时发生,故 hash 锚定模板而非注入后文本。
- 注入:{{COLOR_VOCAB}} / {{STRUCTURE_VOCAB}} 从当期 vocabulary 的 labels.zh 填充(旧项目从
  YAML 注入,新平台从库注入),所用 vocab_version_id 写进标签溯源【不变量二】。
"""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Sequence

PROMPT_VERSION = "tagging_v2"
_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "tagging_v2.txt"


@lru_cache
def load_prompt_template() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


@lru_cache
def prompt_sha256() -> str:
    """提示词本体(模板)内容 hash。"""
    return hashlib.sha256(_PROMPT_PATH.read_bytes()).hexdigest()


def render_prompt(color_vocab_zh: Sequence[str], structure_vocab_zh: Sequence[str]) -> str:
    """把当期词表(中文词形)注入模板占位符,得到发给模型的最终提示词。"""
    template = load_prompt_template()
    return (
        template
        .replace("{{COLOR_VOCAB}}", "、".join(color_vocab_zh))
        .replace("{{STRUCTURE_VOCAB}}", "、".join(structure_vocab_zh))
    )
