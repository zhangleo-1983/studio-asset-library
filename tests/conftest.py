"""核心测试:与行业无关,固定使用默认行业包(空骨架 template),证明核心不依赖任何行业内容。

行业相关的测试在各包自己的 packs/<id>/tests 下,用该包运行(见 Makefile `test`)。
"""
import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def _core_uses_template_pack(monkeypatch):
    monkeypatch.setenv("INDUSTRY_PACK", "template")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
