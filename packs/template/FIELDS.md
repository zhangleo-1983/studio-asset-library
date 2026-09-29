# 行业包字段说明(template)

复制本目录为 `packs/<你的行业>/` 开始写新行业;完整机制见 [docs/industry-packs.md](../../docs/industry-packs.md)。
本目录的 JSON 文件是**能通过校验的空骨架**:填内容时保持 JSON 合法即可。

## pack.json

| 字段 | 必填 | 说明 |
|---|---|---|
| `pack_format` | ✔ | 固定 `1` |
| `id` | ✔ | 必须等于目录名 |
| `title` / `description` | | 给人看的说明 |
| `industry` | ✔ | 写入租户表 `tenant.industry` 的标识 |
| `prompt.file` / `prompt.version` | ✔ | 提示词文件名与版本号(内容改动必须升版本) |
| `prompt.slots` | | 键值对,供 `prompt.txt` 里 `{{SLOT:<名>}}` 使用(如 `persona`) |
| `output_schema.file` / `.version` | ✔ | 输出 JSON Schema 文件与版本号(落 `task.output_schema_version`) |
| `taxonomy` / `ui` | ✔ | 分类体系、UI 文案的文件名 |
| `tagging_config` | | 覆盖平台默认打标配置(模型、温度…)的键值 |
| `demo.tenant_slug` / `tenant_name` | ✔ | demo 租户 |
| `demo.assets` | | `null` 或 `{"generator":"demo/xxx.py","library_subdir":"library","fallback_subdir":"fallback"}` |
| `demo.view[]` | | `{label, dimension, translate, show_role?, caption_dimension?}`:demo 页展示的字段 |
| `demo.recall[]` | | `{dimension, role?, weight}`:召回计分 |
| `demo.loop_script` | | 打标闭环演示脚本相对路径 |

## taxonomy.json

```jsonc
{
  "dimensions": [
    {
      "key": "structure",          // 只能取 structure|color|scene|theme|color_scheme
      "label": "展示名",
      "kind": "constrained",       // constrained(受词表约束)| free_text(自由文本)
      "multi": true,               // 是否多值(展示用)
      "vocabulary": [              // 仅 constrained
        {"concept_key": "ascii_key", "labels": {"zh": "词形"}}   // color 维可加 "color_kind"
      ],
      "aliases": [                 // 仅 constrained:变体词 → concept_key
        {"alias": "变体词形", "concept_key": "ascii_key"}
      ]
    }
    // color 维另可写 "roles": ["primary", "accent"](目前仅 color 支持 roles)
  ],
  "extraction": [                  // 模型输出 → 维度
    {"dimension": "structure", "path": "structure_types", "coerce": "str_list"}
    // path 用 a.b.c;coerce: str | str_list | scalar;带 roles 的维度须写 "role"
  ]
}
```

`concept_key` 必须是 ASCII、维度内唯一、**上线后不再改**;`labels.zh` 在维度内唯一,之后可改。

## prompt.txt

自由文本。槽位:`{{VOCAB:<维度键>}}`(注入当期词表,可写 `{{VOCAB:<维度键>| / }}` 改分隔符)、
`{{SLOT:<名>}}`(取 `pack.json` 的 `prompt.slots`)。`{{VOCAB:x}}` 的 `x` 必须是本包已声明的 constrained 维度。

## output_schema.json

模型输出的 JSON Schema(留档;平台不强校验)。字段需与 `taxonomy.json` 的 `extraction[].path` 对应。

## ui.json

`app.*`(demo 页面文案)、`plan.*`(导出方案页文案)、`role_labels`(role 键→展示名)、`empty_value`。键集合以本目录 `ui.json` 为准,不可删。

## 可选:demo/ 与 tests/

- `demo/`:演示素材生成器(须离线、无 API key、输出确定)等,由 `pack.json` 的 `demo.*` 指向。
- `tests/`:本包专属测试;`make test` 会用 `INDUSTRY_PACK=<id>` 逐包运行。
