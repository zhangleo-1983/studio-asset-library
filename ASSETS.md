# ASSETS —— 图片资产总览

**本仓库(含全部 git 历史)不包含任何图片二进制文件。** 逐个 blob 校验:无 PNG/JPEG/GIF/WebP 等魔数,无 LFS 对象。
`.gitignore` 默认忽略位图;确需入库的图片(文档截图、logo 等)须在 `.gitignore` 用 `!路径` 显式放行,
并在本文或对应行业包的 `ASSETS.md` 登记来源与许可。

## 行业包自带的演示素材

演示素材由各行业包的生成器**程序绘制**(离线、无 API key、输出确定),不入库;每个包在自己的目录里登记
来源、许可与参考哈希:

登记文件位于 `packs/<id>/ASSETS.md`(包列表见 [packs/README.md](packs/README.md));空骨架包无素材。
自绘素材与源码同许可:GNU AGPL-3.0,商业授权请联系 zhangliang@getbitbeats.com。

## 其他

- 测试中使用的图片均为代码即时生成的纯色 PNG,不落盘入库。
- 使用者自备的图片应放在仓库之外或已被忽略的本地目录,并自行确保拥有相应权利。
