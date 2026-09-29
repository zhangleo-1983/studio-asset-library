# balloon 行业包(完整示例)

气球派对布置图库:造型 / 配色 / 场景三个受词表约束的维度 + 主题 / 配色简称两个自由文本维度,
提示词、UI 文案(「接单响应神器」演示叙事)、程序绘制的演示素材生成器与本包专属测试。

```bash
export INDUSTRY_PACK=balloon
make demo-seed          # 建库 + 生成演示素材 + 只入合规库并断言计数(DEMO_MOCK=1 走确定性 provider,无需密钥)
make demo-web           # 起演示页 http://localhost:8100
make demo               # 打标闭环演示(mock provider)
INDUSTRY_PACK=balloon pytest -q packs/balloon/tests
```

- 演示素材:`demo/gen_demo_assets.py` 程序绘制,来源/许可见 [ASSETS.md](./ASSETS.md);不入库。
- 词表的 concept_key 已冻结(只改 `labels.zh`,不改键)。
- 提示词版本 `tagging_v3`:相对旧版只改了槽位写法(`{{VOCAB:…}}` / `{{SLOT:persona}}`),判别规则未变。
