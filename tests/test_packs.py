"""行业包机制:每个包都能加载与自检、切包只改一项配置、空骨架包下系统可启动。"""
from __future__ import annotations

import importlib
import json
import re
import shutil
import sys

import pytest

from app import packs
from app.config import get_settings


def _use(monkeypatch, name: str):
    monkeypatch.setenv("INDUSTRY_PACK", name)
    get_settings.cache_clear()


@pytest.mark.parametrize("name", packs.available_packs())
def test_every_pack_loads_and_validates(name):
    p = packs.load_pack(name)
    assert p.id == name and p.prompt_sha256 and p.prompt_version
    # 提示词里的词表槽位都指向受约束维度(load_pack 已校验,这里断言渲染后无残留槽位)
    text = p.render_prompt({d: ["x"] for d in p.prompt_vocab_dimensions})
    assert re.search(r"\{\{(VOCAB|SLOT):[a-z_]+", text) is None


def test_switch_pack_by_single_setting(monkeypatch):
    names = packs.available_packs()
    assert "template" in names and len(names) >= 2
    _use(monkeypatch, "template")
    assert packs.get_pack().id == "template"
    other = next(n for n in names if n != "template")
    _use(monkeypatch, other)
    assert packs.get_pack().id == other
    assert packs.get_pack().prompt_sha256 != packs.load_pack("template").prompt_sha256


def test_template_pack_is_empty_skeleton():
    p = packs.load_pack("template")
    assert p.dimensions == () and p.extraction == () and p.demo_assets is None


def test_unknown_pack_gives_clear_error(monkeypatch):
    _use(monkeypatch, "no_such_pack")
    with pytest.raises(packs.PackError, match="找不到行业包"):
        packs.get_pack()


def test_invalid_pack_rejected(tmp_path, monkeypatch):
    root = tmp_path / "packs"
    shutil.copytree(packs.packs_dir() / "template", root / "bad")
    meta = json.loads((root / "bad" / "pack.json").read_text(encoding="utf-8"))
    meta["id"] = "bad"
    (root / "bad" / "pack.json").write_text(json.dumps(meta), encoding="utf-8")
    (root / "bad" / "taxonomy.json").write_text(
        json.dumps({"dimensions": [{"key": "custom_dim", "kind": "free_text"}], "extraction": []}), encoding="utf-8")
    monkeypatch.setenv("PACKS_DIR", str(root))
    get_settings.cache_clear()
    with pytest.raises(packs.PackError, match="保留键"):
        packs.load_pack("bad")


def test_system_starts_under_template_pack(monkeypatch):
    """空骨架包:主 API 与 demo 服务都能构建并响应,种子可跑通。"""
    from fastapi.testclient import TestClient

    from app.seed import seed_tenant

    _use(monkeypatch, "template")
    assert seed_tenant(71, "tpl_tenant", "tpl") is True

    from app.main import create_app
    assert TestClient(create_app()).get("/healthz").status_code == 200

    sys.modules.pop("app.demo.server", None)
    server = importlib.import_module("app.demo.server")
    client = TestClient(server.create_demo_app())
    ui = client.get("/ui.json").json()
    assert ui["app"]["page_title"]
    assert client.get("/").status_code == 200
