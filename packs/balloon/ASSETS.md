# 本行业包的图片资产清单(来源/许可)

## 结论

**本仓库(含全部 git 历史)不包含任何图片二进制文件**(总览见仓库根 ASSETS.md)。 逐个 blob 校验:无 PNG/JPEG/GIF/WebP 等魔数,无 LFS 对象。
`.gitignore` 默认忽略位图;确需入库的图片(文档截图、logo 等)须在 `.gitignore` 用 `!路径` 显式放行,并在本文登记来源与许可。

## 已登记的可再生图片(不入库,由脚本程序绘制)

| 项 | 内容 |
|---|---|
| 生成器 | `packs/balloon/demo/gen_demo_assets.py`(一键:`INDUSTRY_PACK=balloon make demo-assets`;`make demo-seed` 已依赖它) |
| 来源 | 由代码用 Pillow **程序绘制**的示意插画,非 AI 模型生成,非任何第三方素材,无外部输入 |
| 许可 | 自有版权,与源码同许可(GNU AGPL-3.0,见 `LICENSE`);商业授权请联系 zhangliang@getbitbeats.com |
| 可复现性 | 离线运行,不依赖任何 API key 或网络;输出确定(同环境两次生成逐字节一致) |
| 输出位置 | `demo_assets/`(已 `.gitignore`);可用 `DEMO_ASSETS_DIR` 改目录 |

下表 sha256 为参考环境(macOS/arm64,`pyproject.toml` 解析出的 Pillow 版本)的生成结果;
不同 Pillow/平台版本可能产生像素级差异,此时以生成器脚本为准,哈希仅供核对。

| 文件(`demo_assets/` 下) | 字节数 | sha256 |
|---|---|---|
| fallback/sample.png | 53386 | `df81d3eff88db5ed1b5aa948eeaea45f606a08848caabc8fc567f70daf7827ff` |
| library/lib_拱门_多巴胺_商场美陈.png | 48970 | `25fca578abea3d70cd31c050520f11923bd2a6adb31547879a24070f46bf56d0` |
| library/lib_拱门_粉白_宝宝宴.png | 47576 | `5dbc48198f051c88357e6f108ab83a8653709930976c7a82576f28eef04af044` |
| library/lib_拱门_红金_婚礼.png | 47800 | `47e136212c28258d221e3828e8295d9071a445b52e3f876f46e39eaacc0fa6a8` |
| library/lib_拱门_蓝白_生日宴.png | 49089 | `f2f896b273aca8bf80c6d56530b7cbf4baba731e96512c4be3203d80416b1a96` |
| library/lib_立柱_多巴胺_商场美陈.png | 46983 | `fba4b59af2d4b13b40b2b172fe05a1a00f2a9fda2296908ca3a9968c2d7f0e12` |
| library/lib_立柱_粉白_宝宝宴.png | 44494 | `a2715443b315cbb1dd6f6ac3f389a15850d559ad02dad32779b478986c514688` |
| library/lib_立柱_红金_婚礼.png | 46507 | `edf6920fe7fd65758456daf3d0325036ed10771eab3cbbb74291c199b378b0af` |
| library/lib_立柱_蓝白_生日宴.png | 45887 | `f7a48878c3eb00a44cc1b52514697ab7a16e8d63fa9978bf04349e5108817365` |
| library/lib_花盒_多巴胺_商场美陈.png | 25770 | `f8153e09ce4eab2f6983cf88f793feb223590986e05a3012dfe918fe1cf561d9` |
| library/lib_花盒_粉白_宝宝宴.png | 24356 | `3e4e4b96e55cb29041783ae1d298e37ae4fab9039ba9f81dcdc9aa253c41b8b4` |
| library/lib_花盒_红金_婚礼.png | 25924 | `2f0c056b8d209ede0d3302e6fbc1cb220d096529e66a0ed8069a1a208f3557c5` |
| library/lib_花盒_蓝白_生日宴.png | 24748 | `85daf5d14a83a6fec973db5f85007566882a6f1ef1cbb8e270bdd6e42509f968` |

另有 `library/manifest.json`、`fallback/manifest.json`、`fallback/fallback_tags.json`:同一脚本产出的确定性打标数据,非图片。

## 其他

- 测试中使用的图片均为代码即时生成的纯色 PNG,不落盘入库。
- 使用者自备的图片应放在仓库之外或已被忽略的本地目录,并自行确保拥有相应权利。
