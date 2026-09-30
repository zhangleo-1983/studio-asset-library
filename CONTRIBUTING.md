# 贡献指南

## 数据库迁移纪律(重要)

**已发布的迁移只能新增,不能修改。**(从首个公开版本起生效。)

- `app/migrations/versions/` 里已经合入默认分支并发布的迁移文件视为不可变:不改 DDL、不改默认值、不改角色名、不改文本。
  需要变更,新增一个 `NNNN_*.py` 迁移去 `ALTER`。
- 例外仅限**首个公开版本之前**:本仓库在公开前(没有任何生产库)为去除行业词,曾就地修改过 `0001`/`0002`
  的文本(角色 `platform_app`、`tenant.industry` 默认值)。此后不再有此类例外。
- 只增表(`event`、`tag_correction`、`vocabulary_version`、`config_version`)已 `REVOKE UPDATE, DELETE`,
  应用层不得绕过。

## 行业包

- 核心代码(`app/`、`scripts/`、迁移、核心测试)**不得出现具体行业词**;行业相关内容一律放进 `packs/<id>/`。
- 维度键限于平台保留的 5 个;自定义维度需要新迁移,见 [docs/industry-packs.md](docs/industry-packs.md)「已知限制」。
- 提示词内容改动 = 升 `pack.json` 里的 `prompt.version`(只增不改);词表 `concept_key` 上线后不改,只改 `labels`。
- 新增行业:复制 `packs/template/`,按 `FIELDS.md` 填写,并用 `INDUSTRY_PACK=<id> pytest tests/test_packs.py` 自检。

## 图片

仓库不携带图片二进制(`.gitignore` 默认忽略位图)。确需入库的图片须在 `.gitignore` 用 `!路径` 放行,
并在 `ASSETS.md`(或对应包的 `ASSETS.md`)登记来源与许可。

## 测试

```bash
make test    # 核心测试(默认包)+ 每个行业包自带的 packs/<id>/tests(用该包运行)
```

需要一个可连的 PostgreSQL 15(见 `tests/conftest.py`/根 `conftest.py`)。CI 会跑同样的测试。

## 提交前

- 不要提交密钥、`.env`、本地图库、个人路径或第三方客户信息。
- 破坏性的接口变更写进 [CHANGELOG.md](CHANGELOG.md)。
