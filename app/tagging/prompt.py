"""打标提示词加载与注入。

- 提示词模板在行业包里(packs/<id>/prompt.txt),版本号在包的 pack.json;**按版本号命名、
  只增不改**(改内容 = 升版本号)【Q2】。
- prompt_sha256 = 提示词**本体模板**(含 {{...}} 槽位)的内容 hash,作为"在什么规则下打的"
  内容锚。槽位是模板,词表注入在运行时发生,故 hash 锚定模板而非注入后文本。
- 槽位:{{VOCAB:<维度键>}} / {{VOCAB:<维度键>| / }}(自定义分隔符)从当期 vocabulary 的
  labels.zh 填充;{{SLOT:<名>}} 取包内 pack.json 的 prompt.slots。所用 vocab_version_id
  写进标签溯源【不变量二】。
"""
from __future__ import annotations

from typing import Sequence

from app.packs import get_pack


def prompt_version() -> str:
    return get_pack().prompt_version


def prompt_sha256() -> str:
    """提示词本体(模板)内容 hash。"""
    return get_pack().prompt_sha256


def render_prompt(vocab_labels: dict[str, Sequence[str]]) -> str:
    """把当期词表(各维度的中文词形)注入模板槽位,得到发给模型的最终提示词。"""
    return get_pack().render_prompt(vocab_labels)
