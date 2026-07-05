"""种子常量:concept_key 命名(migration.md §1.2【A-3 定稿冻结】)。

自裁决四(2026-07-05)批准即冻结:concept_key 稳定、ASCII、上线后不改。
后续改中文词形只动 labels.zh,不动 concept_key 与历史 tag.value。
"""
from __future__ import annotations

# structure(3 条)
STRUCTURE: list[tuple[str, str]] = [
    ("column", "立柱"),
    ("arch", "拱门"),
    ("flowerbox", "花盒"),
]

# color(17 条 = 10 单色 + 7 复合色);第三元为 color_kind
COLOR: list[tuple[str, str, str]] = [
    ("pink", "粉", "simple"),
    ("white", "白", "simple"),
    ("red", "红", "simple"),
    ("blue", "蓝", "simple"),
    ("green", "绿", "simple"),
    ("yellow", "黄", "simple"),
    ("purple", "紫", "simple"),
    ("black", "黑", "simple"),
    ("silver", "银", "simple"),
    ("gold", "金", "simple"),
    ("dopamine", "多巴胺", "compound"),
    ("pearl_white", "珠光白", "compound"),
    ("pearl_pink", "珠光粉", "compound"),
    ("chrome_rose_gold", "铬玫瑰金", "compound"),
    ("chrome_champagne_gold", "铬香槟金", "compound"),
    ("papaya_yellow", "木瓜黄", "compound"),
    ("chrome_gold", "铬金", "compound"),
]

# scene(8 条);裁决四改名 2 处已落地:baby_banquet、grand_opening
SCENE: list[tuple[str, str]] = [
    ("birthday", "生日宴"),
    ("longevity_feast", "寿宴"),
    ("baby_banquet", "宝宝宴"),
    ("mall_display", "商场美陈"),
    ("campus_event", "校园活动"),
    ("grand_opening", "开业"),
    ("wedding", "婚礼"),
    ("other", "其他"),
]

# alias_map 基线(migration.md §1.3【A-2】):别名词形 → concept_key
# 存量唯一一条,source='human'。dimension=structure。
ALIAS_BASELINE: list[tuple[str, str, str]] = [
    # (dimension, alias, concept_key)
    ("structure", "气球花盒", "flowerbox"),
]

# 生产打标配置基线(migration.md §1.4):锁定的评测结论
CONFIG_PAYLOAD_BASE: dict = {
    "model": "qwen-vl-max",
    "few_shot": False,
    "temperature": 0,
    "image_max_edge": 1568,
    "max_retries": 3,
    "concurrency": 2,
    "resume": True,
    "provider": "aliyun_bailian",
    "note": (
        "锁定于 2026-07-03:83 张全量评测 structure 判错率 3.6%,优于 gemini 4.8% 且更快更省;"
        "few-shot 三轮实验判错率反涨至 10.8–13.3% 已关闭"
    ),
    # vocab_versions 在 seed 运行时按本租户实际种子版本 id 填充【N3】
}
