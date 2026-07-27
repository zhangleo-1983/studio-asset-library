"""生成**自有版权**合规演示素材(占位图,程序绘制,非 AI 模型生成、非任何客户/示例客户素材)。

产出 demo_assets/:
  library/lib*.png + library/manifest.json  —— 演示图库(6 张)+ 各图 content_hash→模型输出
  fallback/sample.png + fallback/manifest.json + fallback/fallback_tags.json —— 断网兜底样本

正式演示前,把 library/ 换成真实合规图(即梦/MJ 生成 / 自有版权 / 客户自供),重跑本脚本更新 manifest 即可。
本占位素材仅用于机器链路验证与断网兜底演练;**永不冒充真实案例对外展示**(见 90 秒脚本诚实度纪律)。
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(os.environ.get("DEMO_ASSETS_DIR", "demo_assets"))

# 中文词形 → 绘制用 RGB
ZH_RGB = {
    "红": (219, 48, 60), "金": (223, 181, 74), "粉": (245, 160, 192), "白": (246, 246, 248),
    "蓝": (66, 118, 220), "绿": (72, 176, 118), "黄": (240, 205, 70), "紫": (150, 92, 205),
    "多巴胺": (240, 92, 150),
}


def _draw(structure: str, colors: list[str], size: int = 512) -> bytes:
    img = Image.new("RGB", (size, size), (250, 247, 251))
    d = ImageDraw.Draw(img)
    pal = [ZH_RGB.get(c, (200, 200, 210)) for c in colors] or [(200, 200, 210)]

    def ball(cx, cy, r, col):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col, outline=(255, 255, 255), width=3)

    if structure == "拱门":  # arch:两立柱 + 顶弧
        for i, x in enumerate((120, 392)):
            for j in range(6):
                ball(x, 430 - j * 62, 30, pal[(i + j) % len(pal)])
        for k in range(9):
            t = k / 8
            x = 120 + t * 272
            y = 150 - (0.5 - abs(t - 0.5)) * 120
            ball(int(x), int(y), 26, pal[k % len(pal)])
    elif structure == "立柱":  # column:单柱球串
        for j in range(8):
            ball(256, 450 - j * 55, 34, pal[j % len(pal)])
    else:  # 花盒 flowerbox:底盒 + 顶部球簇
        d.rounded_rectangle([176, 320, 336, 452], radius=16, fill=(196, 150, 110))
        for (dx, dy) in [(-60, -40), (0, -70), (60, -40), (-30, -100), (30, -100), (0, -20)]:
            ball(256 + dx, 300 + dy, 30, pal[(dx + dy) % len(pal)])
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _output(theme, primary, accent, scheme, structures, scene) -> dict:
    return {
        "image_id": "demo", "theme": theme,
        "theme_type": "通用元素" if theme else "无主题",
        "color_scheme": {"primary": primary, "accent": accent, "scheme_name": scheme},
        "structure_types": structures, "scene_guess": scene,
        "suggested_filename": "demo", "confidence": 0.95, "needs_review": False, "notes": "",
    }


# (文件名, 输出, 绘制结构, 绘制色)
LIBRARY = [
    ("lib1_arch_redgold_wedding", _output("爱心", ["红", "金"], ["白"], "红金", ["拱门"], "婚礼"), "拱门", ["红", "金"]),
    ("lib2_arch_pinkwhite_baby", _output(None, ["粉"], ["白"], "粉白", ["拱门"], "宝宝宴"), "拱门", ["粉", "白"]),
    ("lib3_column_redgold_opening", _output(None, ["红", "金"], [], "红金", ["立柱"], "开业"), "立柱", ["红", "金"]),
    ("lib4_column_bluewhite_birthday", _output(None, ["蓝"], ["白"], "蓝白", ["立柱"], "生日宴"), "立柱", ["蓝", "白"]),
    ("lib5_box_dopamine_mall", _output("多巴胺", ["多巴胺"], [], "多巴胺", ["花盒"], "商场美陈"), "花盒", ["多巴胺", "黄", "紫"]),
    ("lib6_box_pink_baby", _output(None, ["粉"], ["白"], "粉", ["花盒"], "宝宝宴"), "花盒", ["粉", "白"]),
]

# 兜底样本 = 拱门+红金+婚礼(与 lib1 强同款,但绘制含白点缀使字节/hash 与 lib1 不同,
# 模拟"客户新发的图":不撞库去重)。断网时展示它。
FALLBACK = ("fallback_arch_redgold_wedding",
            _output("爱心", ["红", "金"], ["白"], "红金", ["拱门"], "婚礼"), "拱门", ["红", "金", "白"])


def main() -> None:
    (OUT / "library").mkdir(parents=True, exist_ok=True)
    (OUT / "fallback").mkdir(parents=True, exist_ok=True)

    lib_manifest: dict[str, dict] = {}
    for name, output, structure, colors in LIBRARY:
        data = _draw(structure, colors)
        (OUT / "library" / f"{name}.png").write_bytes(data)
        lib_manifest[hashlib.sha256(data).hexdigest()] = output
    (OUT / "library" / "manifest.json").write_text(
        json.dumps(lib_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    name, output, structure, colors = FALLBACK
    data = _draw(structure, colors)
    (OUT / "fallback" / f"{name}.png").write_bytes(data)
    (OUT / "fallback" / "manifest.json").write_text(
        json.dumps({hashlib.sha256(data).hexdigest(): output}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    # 断网兜底标签(concept_key 形态,直接喂召回):拱门+红金主色+婚礼+爱心
    fb_tags = [
        {"dimension": "structure", "value": "arch", "role": None},
        {"dimension": "color", "value": "red", "role": "primary"},
        {"dimension": "color", "value": "gold", "role": "primary"},
        {"dimension": "color", "value": "white", "role": "accent"},
        {"dimension": "scene", "value": "wedding", "role": None},
        {"dimension": "theme", "value": "爱心", "role": None},
        {"dimension": "color_scheme", "value": "红金", "role": None},
    ]
    (OUT / "fallback" / "fallback_tags.json").write_text(
        json.dumps(fb_tags, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"生成 {len(LIBRARY)} 张演示库图 + 1 张兜底样本 → {OUT}/")


if __name__ == "__main__":
    main()
