"""一键导出方案页:服务端渲染**单文件 HTML**(客户图 + 四维标签 + 召回案例图)。

浏览器直接打印即 PDF。模板 hardcode、内联样式、图片走 /image 端点。刻意绕开 export_job(冻结项)。
叙事:"接单/成交"口径——标题与文案一律钩住"给客户的方案、拿单",禁用内部作业类措辞(见 90 秒脚本诚实度纪律)。
"""
from __future__ import annotations

from html import escape


def _chip(text: str) -> str:
    return f'<span class="chip">{escape(text)}</span>'


def render_plan_page(*, uploaded_asset_id: int, view: dict, similar_asset_ids: list[int]) -> str:
    colors = "".join(
        _chip(f'{c["zh"]}·{"主色" if c["role"] == "primary" else "点缀"}') for c in view["colors"]
    )
    structure = "".join(_chip(s) for s in view["structure"])
    theme = escape(view["theme"]) if view["theme"] else "—"
    scene = escape(view["scene"]) if view["scene"] else "—"
    scheme = escape(view["scheme_name"]) if view["scheme_name"] else "—"
    cases = "".join(
        f'<div class="case"><img src="/image/{aid}" alt="参考案例"/></div>'
        for aid in similar_asset_ids
    )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>方案预览 · 为您匹配的参考</title>
<style>
  :root {{ --ink:#1a1a2e; --muted:#6b6b83; --line:#ececf3; --accent:#e84a7f; }}
  * {{ box-sizing:border-box; }}
  body {{ font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
         margin:0; color:var(--ink); background:#faf7fb; }}
  .wrap {{ max-width:900px; margin:0 auto; padding:32px 24px 64px; }}
  .head {{ text-align:center; margin-bottom:28px; }}
  .head h1 {{ font-size:24px; margin:0 0 6px; }}
  .head p {{ color:var(--muted); margin:0; font-size:14px; }}
  .card {{ background:#fff; border:1px solid var(--line); border-radius:16px;
           padding:20px; margin-bottom:20px; box-shadow:0 2px 12px rgba(30,10,40,.04); }}
  .hero img {{ width:100%; border-radius:12px; display:block; }}
  .dims {{ display:grid; grid-template-columns:repeat(2,1fr); gap:12px 20px; margin-top:14px; }}
  .dim label {{ display:block; font-size:12px; color:var(--muted); margin-bottom:4px; }}
  .chip {{ display:inline-block; background:#fde7ef; color:var(--accent); border-radius:999px;
           padding:3px 10px; font-size:13px; margin:2px 4px 2px 0; }}
  h2 {{ font-size:16px; margin:8px 0 14px; }}
  .cases {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }}
  .case img {{ width:100%; aspect-ratio:1/1; object-fit:cover; border-radius:10px; }}
  .foot {{ text-align:center; color:var(--muted); font-size:12px; margin-top:24px; }}
</style></head>
<body><div class="wrap">
  <div class="head">
    <h1>这是为您这套需求匹配的参考方案</h1>
    <p>客户发来的图 · AI 拆解 · 从我们的案例库为您选出同款参考</p>
  </div>
  <div class="card hero">
    <img src="/image/{uploaded_asset_id}" alt="客户需求图"/>
    <div class="dims">
      <div class="dim"><label>主题</label>{theme}</div>
      <div class="dim"><label>场景</label>{scene}</div>
      <div class="dim"><label>造型</label>{structure or "—"}</div>
      <div class="dim"><label>配色（{scheme}）</label>{colors or "—"}</div>
    </div>
  </div>
  <div class="card">
    <h2>同款 / 相似参考案例</h2>
    <div class="cases">{cases or "<p>暂无匹配案例</p>"}</div>
  </div>
  <p class="foot">演示用参考库 · 正式使用时跑的是您自己的作品图</p>
</div></body></html>"""
