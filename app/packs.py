"""行业包(industry pack)加载与校验。

行业相关的一切(分类体系、提示词模板、UI 文案、演示数据集指向)都放在 packs/<id>/ 目录里,
核心代码只通过本模块读取。选用哪个包 = 环境变量/`.env` 里的 INDUSTRY_PACK(见 app/config.py)。
包的结构与字段说明见 docs/industry-packs.md 与 packs/template/FIELDS.md。

纪律:核心代码里不得出现任何具体行业词;新增行业 = 新增 packs/<id>/,不改本目录之外的代码。
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional, Sequence

from app.config import get_settings

PACK_FORMAT = 1

# 平台保留的维度键(库表 CHECK 约束按这些键设计,见 docs/industry-packs.md「已知限制」)。
# 包只能从中选用并配置显示名/词表,不能自定义新键。
RESERVED_DIMENSIONS = ("structure", "color", "scene", "theme", "color_scheme")
# 目前只有 color 维支持 role(库表 tag_role_shape 的口径)。
ROLE_DIMENSIONS = ("color",)
KINDS = ("constrained", "free_text")
COERCERS = ("str", "str_list", "scalar")

_VOCAB_SLOT = re.compile(r"\{\{VOCAB:([a-z_]+)(?:\|([^}]*))?\}\}")
_TEXT_SLOT = re.compile(r"\{\{SLOT:([a-z_]+)\}\}")


class PackError(Exception):
    """行业包缺失或不合法。"""


@dataclass(frozen=True)
class VocabEntry:
    concept_key: str
    labels: dict
    color_kind: Optional[str] = None


@dataclass(frozen=True)
class Dimension:
    key: str
    label: str
    kind: str
    multi: bool = False
    roles: tuple = ()
    vocabulary: tuple = ()          # tuple[VocabEntry]
    aliases: tuple = ()             # tuple[(alias, concept_key)]

    @property
    def constrained(self) -> bool:
        return self.kind == "constrained"


@dataclass(frozen=True)
class Extraction:
    dimension: str
    path: str
    coerce: str
    role: Optional[str] = None


@dataclass(frozen=True)
class Pack:
    id: str
    root: Path
    title: str
    industry: str
    prompt_version: str
    prompt_template: str
    prompt_slots: dict
    output_schema_version: str
    dimensions: tuple               # tuple[Dimension]
    extraction: tuple               # tuple[Extraction]
    ui: dict
    tagging_config: dict
    demo: dict = field(default_factory=dict)

    # ── 分类体系 ──────────────────────────────────────────
    def dimension(self, key: str) -> Optional[Dimension]:
        return next((d for d in self.dimensions if d.key == key), None)

    @property
    def constrained_dimensions(self) -> tuple:
        return tuple(d.key for d in self.dimensions if d.constrained)

    def roles_for(self, key: str) -> tuple:
        d = self.dimension(key)
        return d.roles if d else ()

    # ── 提示词 ────────────────────────────────────────────
    @property
    def prompt_sha256(self) -> str:
        """提示词模板本体(含槽位)的内容 hash——"在什么规则下打的"的内容锚。"""
        return hashlib.sha256(self.prompt_template.encode("utf-8")).hexdigest()

    @property
    def prompt_vocab_dimensions(self) -> tuple:
        """模板里出现 {{VOCAB:x}} 槽位的维度键(运行时需要注入当期词表的那些)。"""
        return tuple(dict.fromkeys(m.group(1) for m in _VOCAB_SLOT.finditer(self.prompt_template)))

    def render_prompt(self, vocab_labels: dict[str, Sequence[str]]) -> str:
        """把当期词表(各维度的展示词形)与包内静态槽位注入模板。"""

        def vocab(m: re.Match) -> str:
            sep = m.group(2) if m.group(2) is not None else "、"
            return sep.join(vocab_labels.get(m.group(1), ()))

        out = _VOCAB_SLOT.sub(vocab, self.prompt_template)
        return _TEXT_SLOT.sub(lambda m: str(self.prompt_slots.get(m.group(1), "")), out)

    # ── 演示数据集 ────────────────────────────────────────
    @property
    def demo_assets(self) -> Optional[dict]:
        return (self.demo or {}).get("assets")

    def demo_generator_path(self) -> Optional[Path]:
        a = self.demo_assets
        return (self.root / a["generator"]) if a and a.get("generator") else None


# ── 加载 ──────────────────────────────────────────────────
def packs_dir() -> Path:
    override = get_settings().packs_dir
    return Path(override) if override else Path(__file__).resolve().parents[1] / "packs"


def available_packs() -> list[str]:
    root = packs_dir()
    return sorted(p.name for p in root.iterdir() if (p / "pack.json").is_file()) if root.is_dir() else []


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise PackError(f"行业包缺少文件:{path}") from e
    except json.JSONDecodeError as e:
        raise PackError(f"行业包 JSON 不合法:{path}:{e}") from e


def _need(cond: bool, msg: str) -> None:
    if not cond:
        raise PackError(msg)


def _parse_dimension(raw: dict, where: str) -> Dimension:
    key = raw.get("key")
    _need(key in RESERVED_DIMENSIONS, f"{where}:维度键 {key!r} 不在平台保留键 {RESERVED_DIMENSIONS} 内")
    kind = raw.get("kind")
    _need(kind in KINDS, f"{where}:{key}.kind 必须是 {KINDS}")
    roles = tuple(raw.get("roles") or ())
    _need(not roles or key in ROLE_DIMENSIONS, f"{where}:{key} 不支持 roles(当前仅 {ROLE_DIMENSIONS} 维支持)")
    vocab, aliases = [], []
    if kind == "constrained":
        seen_ck, seen_zh = set(), set()
        for e in raw.get("vocabulary") or []:
            ck = e.get("concept_key", "")
            _need(ck.isascii() and ck.strip() != "", f"{where}:{key} 词条 concept_key 必须是非空 ASCII:{ck!r}")
            _need(ck not in seen_ck, f"{where}:{key} concept_key 重复:{ck}")
            zh = (e.get("labels") or {}).get("zh")
            _need(bool(zh), f"{where}:{key}.{ck} 缺少 labels.zh")
            _need(zh not in seen_zh, f"{where}:{key} 词形重复:{zh}")
            seen_ck.add(ck)
            seen_zh.add(zh)
            vocab.append(VocabEntry(ck, dict(e["labels"]), e.get("color_kind")))
        for a in raw.get("aliases") or []:
            _need(a.get("concept_key") in seen_ck, f"{where}:{key} 别名 {a.get('alias')!r} 指向不存在的 concept_key")
            aliases.append((a["alias"], a["concept_key"]))
    else:
        _need(not raw.get("vocabulary") and not raw.get("aliases"), f"{where}:自由文本维 {key} 不得带词表/别名")
    return Dimension(key=key, label=raw.get("label", key), kind=kind, multi=bool(raw.get("multi")),
                     roles=roles, vocabulary=tuple(vocab), aliases=tuple(aliases))


@lru_cache
def load_pack(name: str) -> Pack:
    root = packs_dir() / name
    _need(root.is_dir() and (root / "pack.json").is_file(),
          f"找不到行业包 {name!r}(在 {packs_dir()};可用:{available_packs()})")
    meta = _read_json(root / "pack.json")
    _need(meta.get("pack_format") == PACK_FORMAT, f"{name}:pack_format 必须为 {PACK_FORMAT}")
    _need(meta.get("id") == name, f"{name}:pack.json 的 id({meta.get('id')!r})必须等于目录名")

    tax = _read_json(root / meta["taxonomy"])
    dims = tuple(_parse_dimension(d, f"{name}/{meta['taxonomy']}") for d in tax.get("dimensions", []))
    _need(len({d.key for d in dims}) == len(dims), f"{name}:维度键重复")
    by_key = {d.key: d for d in dims}

    extraction = []
    for x in tax.get("extraction", []):
        d = by_key.get(x.get("dimension"))
        _need(d is not None, f"{name}:extraction 引用了未声明的维度 {x.get('dimension')!r}")
        _need(x.get("coerce") in COERCERS, f"{name}:extraction.coerce 必须是 {COERCERS}")
        role = x.get("role")
        _need((role in d.roles) if d.roles else role is None,
              f"{name}:extraction {d.key} 的 role {role!r} 与维度 roles {d.roles} 不符")
        extraction.append(Extraction(d.key, x["path"], x["coerce"], role))

    prompt_meta = meta["prompt"]
    template = (root / prompt_meta["file"]).read_text(encoding="utf-8")
    for m in _VOCAB_SLOT.finditer(template):
        d = by_key.get(m.group(1))
        _need(d is not None and d.constrained, f"{name}:提示词槽位 {m.group(0)} 必须指向受词表约束的维度")
    slots = dict(prompt_meta.get("slots") or {})
    for m in _TEXT_SLOT.finditer(template):
        _need(m.group(1) in slots, f"{name}:提示词槽位 {m.group(0)} 未在 pack.json prompt.slots 中给出")

    _read_json(root / meta["output_schema"]["file"])  # 仅校验存在且是合法 JSON
    demo = meta.get("demo") or {}
    for f in demo.get("view", []):
        _need(f.get("dimension") in by_key, f"{name}:demo.view 引用了未声明的维度 {f.get('dimension')!r}")
    for r in demo.get("recall", []):
        _need(r.get("dimension") in by_key, f"{name}:demo.recall 引用了未声明的维度 {r.get('dimension')!r}")
    assets = demo.get("assets")
    if assets:
        _need((root / assets["generator"]).is_file(), f"{name}:演示素材生成器不存在:{assets['generator']}")

    return Pack(
        id=name, root=root, title=meta.get("title", name), industry=meta["industry"],
        prompt_version=prompt_meta["version"], prompt_template=template, prompt_slots=slots,
        output_schema_version=meta["output_schema"]["version"],
        dimensions=dims, extraction=tuple(extraction),
        ui=_read_json(root / meta["ui"]), tagging_config=dict(meta.get("tagging_config") or {}), demo=demo,
    )


def get_pack() -> Pack:
    """当前选用的行业包(INDUSTRY_PACK)。进程内按包名缓存;测试切包用 get_settings.cache_clear()。"""
    return load_pack(get_settings().industry_pack)
