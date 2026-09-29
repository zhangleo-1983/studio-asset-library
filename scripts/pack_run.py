"""运行当前行业包(INDUSTRY_PACK)自带的演示脚本。

    python scripts/pack_run.py assets   # 生成演示素材(pack.json demo.assets.generator)
    python scripts/pack_run.py loop     # 打标闭环演示(pack.json demo.loop_script)

包没有提供对应脚本时打印说明并正常退出(空骨架包即如此)。脚本以子进程运行,继承环境变量。
"""
from __future__ import annotations

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.packs import get_pack  # noqa: E402


def main() -> int:
    kind = sys.argv[1] if len(sys.argv) > 1 else ""
    pack = get_pack()
    if kind == "assets":
        script = pack.demo_generator_path()
    elif kind == "loop":
        rel = (pack.demo or {}).get("loop_script")
        script = (pack.root / rel) if rel else None
    else:
        print(__doc__)
        return 2
    if script is None or not script.is_file():
        print(f"[pack:{pack.id}] 该行业包未提供 {kind} 脚本,跳过。")
        return 0
    print(f"[pack:{pack.id}] 运行 {script.relative_to(pack.root.parent.parent)}")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [os.getcwd(), os.environ.get("PYTHONPATH", "")]))}
    return subprocess.call([sys.executable, str(script)], env=env)


if __name__ == "__main__":
    sys.exit(main())
