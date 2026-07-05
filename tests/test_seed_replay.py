"""集成测试②:种子脚本以两个不同 tenant 参数重放,数据互不可见。

场景 3(第二租户接入)的代码级复现:同一参数化种子脚本对 tenant=1 与 tenant=2 各跑一遍,
两租户各得完整基线(28 条词表),且彼此数据在租户侧查询下互不可见;库内两套并存、
版本 id 独立。全程零业务代码改动。【不变量一】
"""
from __future__ import annotations

from sqlalchemy import text

from app import repository
from app.context import tenant_context
from app.db import platform_session
from app.seed import seed_tenant

BASELINE_VOCAB_COUNT = 3 + 17 + 8  # structure + color + scene


def test_two_tenant_replay_isolation():
    # 重放同一脚本:示例客户(首次)+ 第二租户
    assert seed_tenant(1, "demo_tenant", "示例客户") is True
    assert seed_tenant(2, "qqmgc", "气球梦工厂") is True

    # 幂等:同租户再跑一次不重复播种
    assert seed_tenant(1, "demo_tenant", "示例客户") is False

    # 各租户在自己上下文下看到完整基线,不多不少、不双计
    with tenant_context(1):
        assert repository.count_vocabulary() == BASELINE_VOCAB_COUNT
        s1 = repository.list_concept_keys("structure")
    with tenant_context(2):
        assert repository.count_vocabulary() == BASELINE_VOCAB_COUNT
        s2 = repository.list_concept_keys("structure")

    # concept_key 跨租户可复用(稳定键),内容一致
    assert s1 == s2 == ["arch", "column", "flowerbox"]

    # 互不可见 + 两套并存:库内共 2×28 行,两租户 structure 版本 id 相互独立
    with platform_session(reason="test:verify-isolation") as session:
        total = session.execute(
            text("SELECT count(*) FROM vocabulary WHERE tenant_id IN (1, 2)")
        ).scalar_one()
        assert total == 2 * BASELINE_VOCAB_COUNT

        vv1 = session.execute(
            text(
                "SELECT vocab_version_id FROM vocabulary_version "
                "WHERE tenant_id=1 AND dimension='structure'"
            )
        ).scalar_one()
        vv2 = session.execute(
            text(
                "SELECT vocab_version_id FROM vocabulary_version "
                "WHERE tenant_id=2 AND dimension='structure'"
            )
        ).scalar_one()
        assert vv1 != vv2  # 版本演化互不干扰

        # tenant 1 的词表行没有一条泄漏到 tenant 2 名下
        leaked = session.execute(
            text(
                "SELECT count(*) FROM vocabulary "
                "WHERE tenant_id=2 AND vocab_version_id=:vv1"
            ),
            {"vv1": vv1},
        ).scalar_one()
        assert leaked == 0


def test_seed_rejects_platform_reserved_tenant():
    import pytest

    with pytest.raises(ValueError):
        seed_tenant(0, "platform", "平台公共库")
