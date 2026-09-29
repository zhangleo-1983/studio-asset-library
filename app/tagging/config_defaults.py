"""生产打标配置基线(平台默认值;行业包可在 pack.json 的 tagging_config 里覆盖/补充)。"""
from __future__ import annotations

import copy

from app.packs import get_pack

_BASE: dict = {
    "model": "qwen-vl-max",
    "few_shot": False,
    "temperature": 0,
    "image_max_edge": 1568,
    "max_retries": 3,
    "concurrency": 2,
    "resume": True,
    "provider": "aliyun_bailian",
    # vocab_versions 在 seed 运行时按本租户实际种子版本 id 填充【N3】
}


def tagging_config_base() -> dict:
    """平台默认 + 当前行业包覆盖。返回新副本,调用方可放心修改。"""
    return {**copy.deepcopy(_BASE), **copy.deepcopy(get_pack().tagging_config)}
