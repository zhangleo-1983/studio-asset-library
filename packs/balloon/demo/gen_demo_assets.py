"""生成**自有版权**合规演示素材(程序绘制的气球插画,非 AI 模型生成、非任何客户/示例客户素材)。

产出 demo_assets/:
  library/lib*.png + library/manifest.json      —— 演示图库(12 张:3 造型 × 4 配色)
  fallback/sample.png + fallback/*.json         —— 断网兜底样本

**这是自绘插画,不是真实作品照。** 正式演示前请把 library/ 换成真实合规图
(即梦/MJ 生成 / 自有版权 / 用户自有素材),重跑本脚本更新 manifest。插画仅供机器联调与排练,
方案页脚注已内置"正式使用跑你自己的图"声明,永不冒充真实案例。
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT = Path(os.environ.get("DEMO_ASSETS_DIR", "demo_assets"))
W = H = 640

ZH_RGB = {
    "红": (226, 58, 74), "金": (232, 190, 92), "粉": (247, 169, 197), "白": (250, 250, 252),
    "蓝": (96, 150, 232), "绿": (90, 190, 140), "黄": (245, 210, 90), "紫": (168, 110, 214),
    "多巴胺": (243, 102, 158),
}


def _bg(primary_rgb) -> Image.Image:
    """柔和竖向渐变背景,顶部近白、底部主色极淡。"""
    top = (252, 249, 252)
    r, g, b = primary_rgb
    bot = (int(245 - (245 - r) * .10), int(242 - (242 - g) * .10), int(246 - (246 - b) * .10))
    img = Image.new("RGB", (W, H), top)
    px = img.load()
    for y in range(H):
        t = y / H
        px_row = (int(top[0] + (bot[0] - top[0]) * t), int(top[1] + (bot[1] - top[1]) * t),
                  int(top[2] + (bot[2] - top[2]) * t))
        for x in range(W):
            px[x, y] = px_row
    return img


def _balloon(base: Image.Image, cx: int, cy: int, r: int, color) -> None:
    """一颗有高光、暗边、结与线的气球,带柔和投影。"""
    # 投影(单独图层高斯模糊)
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse([cx - r + 6, cy - r + 12, cx + r + 6, cy + r + 12], fill=(60, 30, 50, 60))
    base.paste(Image.alpha_composite(base.convert("RGBA"), sh.filter(ImageFilter.GaussianBlur(7))).convert("RGB"), (0, 0))
    d = ImageDraw.Draw(base)
    # 线
    d.line([cx, cy + r, cx + 6, cy + r + 46], fill=(180, 180, 190), width=2)
    # 结
    d.polygon([(cx - 5, cy + r - 2), (cx + 5, cy + r - 2), (cx, cy + r + 9)], fill=color)
    # 主体
    d.ellipse([cx - r, cy - int(r * 1.06), cx + r, cy + int(r * .96)], fill=color)
    # 暗边(底部弧)
    dark = tuple(int(c * .82) for c in color)
    d.arc([cx - r, cy - int(r * 1.06), cx + r, cy + int(r * .96)], 20, 160, fill=dark, width=max(2, r // 12))
    # 高光
    hl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(hl).ellipse([cx - int(r * .5), cy - int(r * .72), cx - int(r * .08), cy - int(r * .2)],
                               fill=(255, 255, 255, 150))
    base.paste(Image.alpha_composite(base.convert("RGBA"), hl.filter(ImageFilter.GaussianBlur(3))).convert("RGB"), (0, 0))


def _draw(structure: str, colors: list[str]) -> bytes:
    pal = [ZH_RGB.get(c, (200, 200, 210)) for c in colors] or [(200, 200, 210)]
    img = _bg(pal[0])
    if structure == "拱门":
        pts = []
        for k in range(11):
            t = k / 10
            x = 110 + t * 420
            y = 200 - (0.25 - (t - 0.5) ** 2) * 470
            pts.append((int(x), int(y)))
        for i, x in enumerate((110, 530)):
            for j in range(1, 4):
                pts.append((x, 200 + j * 66))
        for i, (x, y) in enumerate(pts):
            _balloon(img, x, y, 34, pal[i % len(pal)])
    elif structure == "立柱":
        for j in range(7):
            _balloon(img, 320, 470 - j * 62, 40, pal[j % len(pal)])
        for j in range(3):
            _balloon(img, 250, 250 - j * 40, 22, pal[(j + 1) % len(pal)])
            _balloon(img, 390, 250 - j * 40, 22, pal[(j + 2) % len(pal)])
    else:  # 花盒
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([210, 380, 430, 540], radius=22, fill=(206, 158, 116), outline=(150, 108, 72), width=3)
        d.line([210, 430, 430, 430], fill=(150, 108, 72), width=3)
        for i, (dx, dy) in enumerate([(-78, -30), (-30, -70), (30, -85), (78, -40), (0, -20), (-52, -95), (52, -95)]):
            _balloon(img, 320 + dx, 360 + dy, 32, pal[i % len(pal)])
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _out(theme, primary, accent, scheme, structures, scene) -> dict:
    return {"image_id": "demo", "theme": theme, "theme_type": "通用元素" if theme else "无主题",
            "color_scheme": {"primary": primary, "accent": accent, "scheme_name": scheme},
            "structure_types": structures, "scene_guess": scene,
            "suggested_filename": "demo", "confidence": 0.95, "needs_review": False, "notes": ""}


# 3 造型 × 4 配色 = 12;theme 只给部分,贴近真实分布
STRUCTS = ["拱门", "立柱", "花盒"]
SCHEMES = [
    ("红金", ["红", "金"], ["白"], "婚礼", "爱心", ["红", "金", "白"]),
    ("粉白", ["粉"], ["白"], "宝宝宴", None, ["粉", "白"]),
    ("多巴胺", ["多巴胺"], ["黄", "紫"], "商场美陈", "多巴胺", ["多巴胺", "黄", "紫"]),
    ("蓝白", ["蓝"], ["白"], "生日宴", None, ["蓝", "白"]),
]


def main() -> None:
    (OUT / "library").mkdir(parents=True, exist_ok=True)
    (OUT / "fallback").mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict] = {}
    for s in STRUCTS:
        for scheme, primary, accent, scene, theme, drawc in SCHEMES:
            data = _draw(s, drawc)
            name = f"lib_{s}_{scheme}_{scene}"
            (OUT / "library" / f"{name}.png").write_bytes(data)
            manifest[hashlib.sha256(data).hexdigest()] = _out(theme, primary, accent, scheme, [s], scene)
    (OUT / "library" / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # 兜底样本:拱门+红金+婚礼,绘制含白点缀使 hash 异于任何 lib(模拟客户新图)
    data = _draw("拱门", ["红", "金", "白", "金"])
    (OUT / "fallback" / "sample.png").write_bytes(data)
    (OUT / "fallback" / "manifest.json").write_text(
        json.dumps({hashlib.sha256(data).hexdigest(): _out("爱心", ["红", "金"], ["白"], "红金", ["拱门"], "婚礼")},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    fb = [{"dimension": "structure", "value": "arch", "role": None},
          {"dimension": "color", "value": "red", "role": "primary"},
          {"dimension": "color", "value": "gold", "role": "primary"},
          {"dimension": "color", "value": "white", "role": "accent"},
          {"dimension": "scene", "value": "wedding", "role": None},
          {"dimension": "theme", "value": "爱心", "role": None},
          {"dimension": "color_scheme", "value": "红金", "role": None}]
    (OUT / "fallback" / "fallback_tags.json").write_text(json.dumps(fb, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"生成 {len(manifest)} 张演示库插画 + 1 张兜底样本 → {OUT}/")


if __name__ == "__main__":
    main()
