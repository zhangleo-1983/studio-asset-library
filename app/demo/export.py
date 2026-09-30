"""一键导出方案页:服务端渲染**单文件 HTML**(上传图 + 维度视图 + 召回案例图)。

浏览器直接打印即 PDF。模板 hardcode、内联样式、图片走 /image 端点。刻意绕开 export_job(冻结项)。
所有文案取自行业包 ui.json 的 plan 节与 role_labels。
"""
from __future__ import annotations

from html import escape

from app.packs import get_pack


def _chip(text: str) -> str:
    return f'<span class="chip">{escape(text)}</span>'


def render_plan_page(*, uploaded_asset_id: int, view: dict, similar_asset_ids: list[int]) -> str:
    ui = get_pack().ui
    plan, roles, empty = ui["plan"], ui.get("role_labels", {}), ui.get("empty_value", "—")

    dims_html = ""
    for f in view["fields"]:
        chips = "".join(
            _chip(i["text"] + (f'·{roles.get(i["role"], i["role"])}' if i["role"] else ""))
            for i in f["items"]
        )
        caption = f'（{escape(f["caption"])}）' if f["caption"] else ""
        dims_html += f'<div class="dim"><label>{escape(f["label"])}{caption}</label>{chips or empty}</div>\n      '
    cases = "".join(
        f'<div class="case"><img src="/image/{aid}" alt="{escape(plan["case_alt"])}"/></div>'
        for aid in similar_asset_ids
    )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{escape(plan["page_title"])}</title>
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
    <h1>{escape(plan["heading"])}</h1>
    <p>{escape(plan["subheading"])}</p>
  </div>
  <div class="card hero">
    <img src="/image/{uploaded_asset_id}" alt="{escape(plan["hero_alt"])}"/>
    <div class="dims">
      {dims_html}</div>
  </div>
  <div class="card">
    <h2>{escape(plan["cases_heading"])}</h2>
    <div class="cases">{cases or "<p>" + escape(plan["no_cases"]) + "</p>"}</div>
  </div>
  <p class="foot">{escape(plan["footer"])}</p>
</div></body></html>"""
