"""`make smoke` 的辅助脚本(仅标准库,宿主机 python3 即可运行)。

子命令:
  pick                  从 stdin 读图片文件名(每行一个),挑 3 张上传图 + 1 张反向测试图,按行输出
  check <pack_dir>      从 stdin 读 JSON([{file, asset_id, tags:[…]}]),逐项断言并用中文表格打印;
                        机器可读结果行以 `RESULT|✅|项目|说明` / `RESULT|❌|项目|说明` 输出

不读取、不打印任何密钥。
"""
from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path


def _w(s: str) -> int:
    """终端显示宽度(中文字符占 2 格)。"""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def _pad(s: str, n: int) -> str:
    return s + " " * max(0, n - _w(s))


def cmd_pick() -> int:
    names = sorted(l.strip() for l in sys.stdin if l.strip())
    if len(names) < 4:
        print(f"素材数量不足:只有 {len(names)} 张", file=sys.stderr)
        return 1
    # 均匀取 3 张上传 + 1 张(与上传的都不同)给反向测试
    idx = [0, len(names) // 2, len(names) - 1]
    rev = next(i for i in range(len(names)) if i not in idx and i != 0)
    for i in idx + [rev]:
        print(names[i])
    return 0


def cmd_check(pack_dir: str) -> int:
    root = Path(pack_dir)
    meta = json.loads((root / "pack.json").read_text(encoding="utf-8"))
    tax = json.loads((root / meta["taxonomy"]).read_text(encoding="utf-8"))
    want_pv = meta["prompt"]["version"]
    dims = {d["key"]: d for d in tax["dimensions"]}
    vocab = {k: {e["concept_key"]: e["labels"]["zh"] for e in d.get("vocabulary", [])}
             for k, d in dims.items() if d["kind"] == "constrained"}
    ui_roles = json.loads((root / meta["ui"]).read_text(encoding="utf-8")).get("role_labels", {})

    items = json.load(sys.stdin)
    header = ["图片", "维度", "标签", "角色", "状态", "来源", "提示词版本"]
    rows, bad_vocab, bad_src, bad_pv, empty = [], [], [], [], []
    for it in items:
        tags = it["tags"]
        if not tags:
            empty.append(it["file"])
        for t in tags:
            d = dims.get(t["dimension"])
            label = d["label"] if d else t["dimension"]
            shown = t["value"]
            if d and d["kind"] == "constrained":
                if t["status"] != "active" or t["value"] not in vocab[t["dimension"]]:
                    bad_vocab.append(f'{it["file"]}:{label}={t["value"]}(状态 {t["status"]})')
                else:
                    shown = vocab[t["dimension"]][t["value"]]
            elif d is None:
                bad_vocab.append(f'{it["file"]}:未知维度 {t["dimension"]}')
            if not (t["source"] == "model" and t.get("provider") == "qwen"
                    and str(t.get("model_id", "")).startswith("qwen")):
                bad_src.append(f'{it["file"]}:{label}(来源 {t["source"]}/{t.get("provider")}/{t.get("model_id")})')
            if t["prompt_version"] != want_pv:
                bad_pv.append(f'{it["file"]}:{label}({t["prompt_version"]})')
            rows.append([it["file"], label, shown, ui_roles.get(t["role"], t["role"] or "—"),
                         "在册" if t["status"] == "active" else t["status"],
                         "qwen" if t.get("provider") == "qwen" else str(t.get("provider")), t["prompt_version"]])

    # 表格(每张图一组;文件名只在组内首行显示)
    widths = [max(_w(str(r[i])) for r in [header] + rows) for i in range(len(header))]
    line = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    print(line)
    print("| " + " | ".join(_pad(h, widths[i]) for i, h in enumerate(header)) + " |")
    print(line)
    last = None
    for r in rows:
        r2 = list(r)
        if r2[0] == last:
            r2[0] = ""
        else:
            last = r2[0]
            if r is not rows[0]:
                print(line)
        print("| " + " | ".join(_pad(str(c), widths[i]) for i, c in enumerate(r2)) + " |")
    print(line)

    def res(ok: bool, name: str, ok_msg: str, bad: list[str]) -> None:
        detail = ok_msg if ok else "; ".join(bad[:6]) + ("…" if len(bad) > 6 else "")
        print(f"RESULT|{'✅' if ok else '❌'}|{name}|{detail}")

    res(not empty, "每张图都产出了标签", f"{len(items)} 张图均有标签", [f"{f} 无标签" for f in empty])
    res(not bad_vocab, "所有受词表约束的标签都在示例包词表内", f"{len(rows)} 条标签全部在册", bad_vocab)
    res(not bad_src, "标签来源是真实 Qwen(不是 mock)", "全部来自 qwen 调用", bad_src)
    res(not bad_pv, f"提示词版本是 {want_pv}", f"全部为 {want_pv}", bad_pv)
    return 0


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "pick":
        return cmd_pick()
    if len(sys.argv) >= 3 and sys.argv[1] == "check":
        return cmd_check(sys.argv[2])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
