"""本包测试:固定使用本行业包。测试库夹具在仓库根 conftest.py。"""
import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def _use_this_pack(monkeypatch):
    monkeypatch.setenv("INDUSTRY_PACK", "balloon")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
