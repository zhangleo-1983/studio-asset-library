# 行业包(industry pack)

核心代码与行业无关。一切行业相关的东西——**分类体系(维度 + 词表)、带槽位的提示词模板、UI 文案、演示数据集指向**——
都放在 `packs/<id>/` 里。选用哪个包只改一项配置:

```bash
export INDUSTRY_PACK=<id>        # 或写进 .env;默认 template(空骨架)
```

切换后,种子(词表/配置)、打标提示词、demo 页面文案与维度视图、召回权重、演示素材全部随之切换,不改任何代码。

## 随仓库提供的两个包

- **[`packs/balloon`](../packs/balloon/README.md)(完整示例包)**:四维标签体系、提示词、UI 文案、程序绘制的演示素材生成器、本包专属测试。包名与用法见 [packs/README.md](../packs/README.md)。
- **`packs/template`**:空骨架:结构齐全但无词表、无演示素材;复制它开始写新行业。字段逐项说明见 [packs/template/FIELDS.md](../packs/template/FIELDS.md)。

## 目录结构

```
packs/<id>/
├── pack.json          # 包元数据 + 引用下面各文件 + 演示配置
├── taxonomy.json      # 分类体系:维度、词表、别名、模型输出取值规则
├── prompt.txt         # 提示词模板(带 {{VOCAB:…}} / {{SLOT:…}} 槽位)
├── output_schema.json # 模型输出的 JSON Schema(留档,并随任务记录其版本号)
├── ui.json            # UI 文案(demo 页面 + 导出方案页)
├── demo/              # (可选)演示素材生成器、闭环演示脚本
└── tests/             # (可选)本包专属测试,用本包运行
```

## 加载与校验

`app/packs.py` 在启动/首次使用时加载并校验当前包,错误会给出明确信息(缺文件、维度键非法、词条重复、
概念键非 ASCII、提示词槽位指向不存在的维度等)。`tests/test_packs.py` 对 `packs/` 下**每个包**做加载自检。

## 分类体系(taxonomy.json)

- `dimensions[]`:本包启用的维度。`key` 必须取自平台保留键 `structure / color / scene / theme / color_scheme`
  (见下「已知限制」);`label` 是展示名;`kind`:`constrained`(受词表约束,标签存 concept_key)或
  `free_text`(自由文本,标签存原词形);`roles`(仅 `color` 支持)声明角色集合;`vocabulary[]` / `aliases[]`
  仅 constrained 维度可有。
- 词表条目:`concept_key`(**ASCII、稳定、上线后不改**)+ `labels.zh`(展示词形,可改)+ 可选 `color_kind`。
- `extraction[]`:模型输出 JSON 里哪个路径对应哪个维度(`path` 用 `a.b.c`;`coerce`:`str` / `str_list` / `scalar`
  对应三种兜底函数;带 role 的维度须写 `role`)。
- 词表进库靠种子脚本(`assetlib-seed`)。已有租户的词表演进走词表版本机制,不是改这个文件。

> **注意:自由文本维度的标签不受词表约束。** 只有 `kind: constrained` 的维度,标签才保证是词表里的 `concept_key`
> (词表外的词会记为「待归类」并进复核队列);`kind: free_text` 的维度(如示例包的主题、配色简称)按模型原词形落库,
> 不做词表校验。对使用者:检索/统计时不要假设这些维度的取值是有限集合。

## 提示词模板(prompt.txt)

- `{{VOCAB:<维度键>}}`:运行时注入当期词表(该维度当前版本内 active 词条的中文词形),分隔符默认「、」,
  可写 `{{VOCAB:<维度键>| / }}` 自定义。所用词表版本写进标签溯源。
- `{{SLOT:<名>}}`:取 `pack.json` 的 `prompt.slots.<名>`(纯文本,如角色设定)。
- **版本纪律**:提示词内容改动 = 升 `pack.json` 里 `prompt.version`(只增不改);系统按模板内容算 `prompt_sha256`
  存入配置版本,标签可追溯到确切的提示词内容。

## UI 文案(ui.json)

`app.*`:demo 页面各处文案;`plan.*`:导出方案页文案;`role_labels`:role 键 → 展示名;`empty_value`。
静态页面不含任何文案,由 `/ui.json` 提供。

## 演示数据集指向(pack.json 的 demo)

- `tenant_slug` / `tenant_name`:demo 租户。
- `assets`:`null` = 无演示素材;否则 `{generator, library_subdir, fallback_subdir}`——`make demo-assets` 运行
  `generator` 生成素材到 `DEMO_ASSETS_DIR/<library_subdir>` 等目录,`make demo-seed` 只入这个库并断言计数。
- `view[]`:演示页/方案页展示哪些维度、顺序、显示名、是否翻译词形、是否显示 role、标题旁的说明维度。
- `recall[]`:召回计分权重(维度 + 可选 role + 权重)。
- `loop_script`:打标闭环演示脚本(`make demo` 运行)。

## 教程:以 `packs/balloon` 为例逐字段看一遍

示例包是气球派对布置图库。下面的片段都取自它的真实文件,可对照 `packs/balloon/` 阅读。

**1. 维度与词表**(`taxonomy.json`)——造型维度受词表约束,词表 3 条、别名 1 条:

```json
{
  "key": "structure",
  "label": "造型",
  "kind": "constrained",
  "multi": true,
  "vocabulary": [
    {
      "concept_key": "column",
      "labels": {
        "zh": "立柱"
      }
    },
    {
      "concept_key": "arch",
      "labels": {
        "zh": "拱门"
      }
    },
    {
      "...": "共 3 条"
    }
  ],
  "aliases": [
    {
      "alias": "气球花盒",
      "concept_key": "flowerbox"
    }
  ]
}
```

- 配色维度(`color`)另带 `"roles": ["primary", "accent"]`(主色/点缀),词表 17 条,`color_kind` 区分单色 `simple` 与复合色 `compound`(如「多巴胺」「珠光粉」)。
- 场景维度(`scene`)8 条,含兜底项「其他」(`other`)。
- 主题(`theme`)、配色简称(`color_scheme`)是自由文本维度:模型写什么就存什么,**不受词表约束**。

**2. 模型输出如何变成标签**(`taxonomy.json` 的 `extraction`)——例如模型输出 `{"structure_types": ["立柱","气球花盒"], "color_scheme": {"primary": ["红","金"], "scheme_name": "红金"}, "scene_guess": "婚礼"}`:

| 输出路径 | 落到维度 | 处理 |
|---|---|---|
| `structure_types`(列表) | `structure` | "立柱" → 词表命中 `column`;"气球花盒" → 别名命中 `flowerbox`;词表外的词记为「待归类」 |
| `color_scheme.primary` | `color`(role=`primary`) | "红"→`red`,"金"→`gold` |
| `scene_guess` | `scene` | "婚礼" → `wedding` |
| `color_scheme.scheme_name` | `color_scheme`(自由文本) | 原样存"红金" |

**3. 提示词**(`prompt.txt`)——开头 `你是{{SLOT:persona}},…`(角色设定来自 `pack.json` 的 `prompt.slots.persona`);造型/配色词表用 `{{VOCAB:structure}}`、`{{VOCAB:color}}` 注入,场景枚举用 `{{VOCAB:scene| / }}`(自定义分隔符)。版本号在 `pack.json`:`prompt.version = "tagging_v3"`。

**4. UI 文案与演示**(`ui.json`、`pack.json` 的 `demo`)——`ui.json` 的 `app.hero_title` 等是演示页文案;`demo.view` 决定演示页展示「主题 / 场景 / 造型 / 配色」四块;`demo.recall` 决定召回权重(造型 3、主色 2、其余 1);`demo.assets.generator` 指向程序绘制插画的脚本 `demo/gen_demo_assets.py`。

**5. 跑起来**

```bash
export INDUSTRY_PACK=balloon
DEMO_MOCK=1 make demo-seed && make demo-web     # 无需密钥的演示
make smoke                                     # 用你自己的百炼 key 做真实模型冒烟(见 SMOKE.md)
```

## 新增一个行业

1. `cp -r packs/template packs/<你的行业>`,把 `pack.json` 的 `id` 改成目录名;
2. 按 FIELDS.md 填 `taxonomy.json` / `prompt.txt` / `output_schema.json` / `ui.json`;
3. `INDUSTRY_PACK=<你的行业> pytest tests/test_packs.py` 自检;
4. (可选)加 `demo/` 与 `tests/`,`make test` 会自动逐包运行 `packs/*/tests`。

## 已知限制(诚实标注)

1. **维度键是平台保留的 5 个**:库表 CHECK 约束(`tag_role_shape`、`tag_provenance_by_source`)按这 5 个键设计,
   自定义新键会被数据库拒绝。包能决定启用哪些、词表与展示名是什么,但暂不能发明新维度键;role 目前只支持 `color`。
   要支持自定义维度,需要新的迁移(例如把维度定义落成表)并改这两条 CHECK——尚未做,登记为后续项。
2. 词表语言键固定为 `zh`(`labels.zh`);多语言是留位,未实现。
3. 提示词里的输出 JSON 结构由各包自己在 `prompt.txt` / `output_schema.json` 写明,平台只按 `extraction` 取值,
   不校验模型输出是否符合 `output_schema.json`(刻意宽松,靠兜底函数)。
