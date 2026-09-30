#!/usr/bin/env bash
# make smoke —— 真实 Qwen 冒烟测试(面向零基础用户,macOS)。说明见 docs/SMOKE.md。
#
# 做什么:预检 → 输入 key(仅本进程内存)→ 独立 docker compose 项目起全新数据库 → 示例包生成素材 →
#        通过 API 上传 3 张图并逐项断言 → 用错误 key 反向测试 → 收尾并扫描 key 是否落盘 → 中文汇总。
# 不碰:本机任何已有数据库、.env、任何文件里的 key。
#
# key 只能在终端里交互输入(read -s),不接受命令行参数/环境变量/管道传入。

export LC_ALL="${LC_ALL:-en_US.UTF-8}"
cd "$(cd "$(dirname "$0")/.." && pwd)" || exit 1
ROOT="$(pwd)"

PROJECT="assetlib-smoke"
PACK="${SMOKE_PACK:-}"   # 由 Makefile 传入(make smoke)
API_URL_BASE=""
KEY=""
TMP=""
RESULTS=()          # 元素:"✅|项目|说明"
FINISHED=0
STARTED=0          # 预检/输入 key 通过后才置 1;此前退出不打印汇总
COMPOSE_STARTED=0

# ── 输出工具 ────────────────────────────────────────────────
say()  { printf '%s\n' "$*"; }
hr()   { say "────────────────────────────────────────────────────────"; }
record() { RESULTS+=("$1|$2|$3"); if [ "$1" = "✅" ]; then say "  ✅ $2"; else say "  ❌ $2 —— $3"; fi; }

# 把输出里出现的 key 原文替换成 ***(key 通过环境变量传给 python,不出现在命令行)
redact() {
  if [ -n "$KEY" ]; then
    python3 -c 'import os,sys
k=os.environ.get("DASHSCOPE_API_KEY","")
s=sys.stdin.read()
sys.stdout.write(s.replace(k,"***") if k else s)'
  else
    cat
  fi
}

dc() { docker compose -p "$PROJECT" "$@"; }

# ── 1. 预检(缺什么就说明白怎么装,然后退出)────────────────────
precheck() {
  hr; say "第 1 步:检查运行环境"; hr
  local missing=0
  need() {  # need 命令 说明
    if command -v "$1" >/dev/null 2>&1; then say "  ✅ 已找到 $1"; else
      say "  ❌ 没有找到 $1 —— $2"; missing=1; fi
  }
  need git     "请在「终端」运行:xcode-select --install(会弹出安装窗口,点“安装”,等几分钟)"
  need make    "同上:xcode-select --install(git 和 make 是一起装的)"
  need python3 "同上:xcode-select --install(自带 python3)"
  need curl    "macOS 自带;若缺失请重装命令行工具:xcode-select --install"
  need docker  "请安装 Docker Desktop(https://www.docker.com/products/docker-desktop/ 下载安装,首次打开按提示完成设置),或 OrbStack(https://orbstack.dev)"
  if command -v docker >/dev/null 2>&1; then
    if docker info >/dev/null 2>&1; then say "  ✅ Docker 正在运行"; else
      say "  ❌ Docker 没有运行 —— 请打开「Docker Desktop」(或 OrbStack)应用,等菜单栏的鲸鱼图标停止转动后,重新运行 make smoke"; missing=1; fi
    if docker compose version >/dev/null 2>&1; then say "  ✅ 已找到 docker compose"; else
      say "  ❌ 没有 docker compose —— 请把 Docker Desktop 升级到最新版"; missing=1; fi
  fi
  if ! command -v git >/dev/null 2>&1; then :   # git 缺失已在上面提示,这里跳过 .env 检查
  elif git check-ignore -q .env 2>/dev/null; then say "  ✅ .env 已被 .gitignore 忽略(key 不会被误提交)"; else
    say "  ❌ .env 没有被 .gitignore 忽略 —— 请在仓库根目录的 .gitignore 里加一行 .env 再运行(防止 key 被误提交)"; missing=1; fi
  for v in DEMO_MOCK DEMO_FORCE_OFFLINE; do
    case "$(printf '%s' "${!v}" | tr 'A-Z' 'a-z')" in
      1|true|yes) say "  ❌ 检测到环境变量 $v 已开启(mock/离线模式),冒烟测试必须走真实调用 —— 请运行 unset $v 后重试"; missing=1;;
    esac
  done
  if [ "$missing" -ne 0 ]; then
    say ""; say "❌ 预检未通过,已退出。请按上面的提示处理后重新运行 make smoke。"; exit 1
  fi
  say "  ✅ 预检全部通过"
}

# ── 2. 输入 key ─────────────────────────────────────────────
ask_key() {
  hr; say "第 2 步:输入 DashScope(阿里云百炼)API key"; hr
  if [ ! -t 0 ]; then say "❌ 需要在终端里交互输入 key(不接受管道/重定向输入),请直接在终端运行 make smoke"; exit 1; fi
  say "请粘贴你的 key(输入时屏幕上不会显示任何字符,粘贴后按回车)。"
  say "key 只保存在本次运行的内存里,不写入任何文件,结束即消失。"
  IFS= read -r -s -p "DashScope key: " KEY; echo
  KEY="$(printf '%s' "$KEY" | tr -d '[:space:]"'"'")"
  if [ -z "$KEY" ]; then say "❌ 没有输入 key,已退出。"; exit 1; fi
  case "$KEY" in sk-*) ;; *) say "  ⚠️ 这个 key 不是以 sk- 开头,可能粘贴错了(继续尝试,失败会有明确提示)";; esac
  export DASHSCOPE_API_KEY="$KEY"
  say "  已收到 key:${KEY:0:3}****${KEY: -2}(已打码,共 ${#KEY} 位)"
}

# ── 收尾:down -v、清临时文件、扫描 key 有没有落盘、汇总 ────────────
cleanup_compose() {
  if [ "$COMPOSE_STARTED" -eq 1 ]; then
    dc down -v >/dev/null 2>&1
    COMPOSE_STARTED=0
  fi
}

finish() {
  [ "$STARTED" -eq 0 ] && return
  [ "$FINISHED" -eq 1 ] && return
  FINISHED=1
  hr; say "第 7 步:收尾与安全检查"; hr
  if [ -n "$PROJECT" ]; then
    if [ "$COMPOSE_STARTED" -eq 1 ]; then
      if dc down -v >/dev/null 2>&1; then COMPOSE_STARTED=0; record ✅ "已清理测试容器与数据库(docker compose down -v)" ""; else
        record ❌ "清理测试容器失败" "请手动运行:docker compose -p $PROJECT down -v"; fi
    else
      record ✅ "没有遗留的测试容器" ""
    fi
  fi
  [ -n "$TMP" ] && rm -rf "$TMP"
  if [ -n "$KEY" ]; then
    # grep -F 按 key 原文扫描整个工作区(pattern 经进程替换传入,不出现在命令行)
    local hits
    hits="$(grep -rlaF --exclude-dir=.venv -f <(printf '%s\n' "$KEY") "$ROOT" 2>/dev/null)"
    if [ -z "$hits" ]; then record ✅ "key 没有落进工作区的任何文件(grep -F 扫描)" ""; else
      record ❌ "在这些文件里发现了 key 原文" "$(printf '%s' "$hits" | tr '\n' ' ')—— 请立即删除其中的 key,并到百炼控制台重置该 key"; fi
  fi
  unset KEY DASHSCOPE_API_KEY

  hr; say "汇总"; hr
  local fail=0 r
  for r in "${RESULTS[@]}"; do
    local ok="${r%%|*}" rest="${r#*|}"
    local name="${rest%%|*}" det="${rest#*|}"
    if [ "$ok" = "✅" ]; then say "  ✅ $name"; else say "  ❌ $name —— $det"; fail=1; fi
  done
  hr
  if [ "$fail" -eq 0 ] && [ "${#RESULTS[@]}" -gt 0 ]; then say "总结论:✅ 通过"; else say "总结论:❌ 未通过"; fi
  hr
  [ "$fail" -eq 0 ] && [ "${#RESULTS[@]}" -gt 0 ] && exit 0
  exit 1
}
trap 'finish' EXIT
trap 'say ""; say "已中断,正在清理…"; record ❌ "测试被中断" "你按了 Ctrl+C"; exit 1' INT TERM

fatal() { record ❌ "$1" "$2"; exit 1; }

free_port() { python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1])'; }

# ── 主流程 ─────────────────────────────────────────────────
if [ -z "$PACK" ]; then echo "请用 make smoke 运行本脚本(由 Makefile 指定使用的行业包)。"; exit 1; fi
precheck
ask_key
STARTED=1

hr; say "第 3 步:启动全新的测试环境(独立 docker compose 项目 $PROJECT,不碰你本机已有的任何数据库)"; hr
TMP="$(mktemp -d)"
API_PORT="$(free_port)"; DEMO_PORT="$(free_port)"; PG_PORT="$(free_port)"
export INDUSTRY_PACK="$PACK" API_HOST_PORT="$API_PORT" DEMO_HOST_PORT="$DEMO_PORT" PG_HOST_PORT="$PG_PORT"
unset DEMO_MOCK DEMO_FORCE_OFFLINE DEMO_STRICT
record ✅ "已确认不是 mock 模式(mock/离线开关均未开启;服务将以严格模式运行,任何降级都会直接报错)" ""

dc down -v >/dev/null 2>&1   # 只清理本冒烟项目自己上次遗留的资源
say "  正在构建并启动(第一次需要下载镜像,可能要几分钟,请耐心等待)…"
COMPOSE_STARTED=1
if ! dc up -d --build >"$TMP/up.log" 2>&1; then
  redact <"$TMP/up.log" | tail -15
  if grep -q "docker-credential" "$TMP/up.log"; then
    fatal "启动测试环境失败" "Docker 的登录凭据助手找不到(常见于装过又卸载 Docker Desktop)。请先打开一次 Docker Desktop;或编辑 ~/.docker/config.json,删掉含 credsStore 的那一行,再重试"
  elif grep -q -i -E "pull access denied|TLS handshake|i/o timeout|no such host|connection refused|EOF" "$TMP/up.log"; then
    fatal "启动测试环境失败" "下载 Docker 镜像失败,请检查网络(需要能访问 Docker Hub),必要时开启/切换代理后重试"
  fi
  fatal "启动测试环境失败" "docker compose 报错(见上方最后几行)"
fi
ok=0
for i in $(seq 1 90); do
  if curl -fsS "http://127.0.0.1:$API_PORT/healthz" 2>/dev/null | grep -q '"status":"ok"'; then ok=1; break; fi
  sleep 2
done
[ "$ok" -eq 1 ] || fatal "测试环境没有在 3 分钟内就绪" "api 健康检查未通过"
record ✅ "全新数据库与服务已启动(示例包 $PACK)" ""

MODE_IN_CONTAINER="$(dc exec -T api sh -c 'printf "%s|%s|%s" "${INDUSTRY_PACK:-}" "${DEMO_MOCK:-}" "${DEMO_FORCE_OFFLINE:-}"' 2>/dev/null)"
[ "$MODE_IN_CONTAINER" = "$PACK||" ] || fatal "容器内运行模式不对" "期望 $PACK||,实际 $MODE_IN_CONTAINER"

say "  正在建立租户并生成演示素材(make demo-assets 的同一条命令,在容器内运行)…"
dc exec -T api python -c "
from app.seed import seed_tenant
from app.tagging.knowledge import register_tagging_config
seed_tenant(1, 'smoke_tenant', 'Smoke tenant'); register_tagging_config(1)" >"$TMP/seed.log" 2>&1 \
  || { redact <"$TMP/seed.log" | tail -8; fatal "初始化租户失败" "见上方输出"; }
dc exec -T api python scripts/pack_run.py assets >"$TMP/assets.log" 2>&1 \
  || { redact <"$TMP/assets.log" | tail -8; fatal "生成演示素材失败" "见上方输出"; }
dc cp api:/app/demo_assets/library "$TMP/lib" >/dev/null 2>&1 || fatal "取出演示素材失败" "docker compose cp 失败"
ls "$TMP/lib"/*.png >/dev/null 2>&1 || fatal "演示素材为空" "$TMP/lib 下没有 png"
record ✅ "演示素材已生成($(ls "$TMP/lib"/*.png | wc -l | tr -d ' ') 张程序绘制插画)" ""

PICKED=()
while IFS= read -r line; do PICKED+=("$line"); done < <(ls "$TMP/lib" | grep '\.png$' | python3 scripts/smoke_check.py pick)
[ "${#PICKED[@]}" -eq 4 ] || fatal "挑选测试图失败" "素材数量不足"

# 启动真实调用的 demo 服务(严格模式;key 经环境变量传入容器,不出现在命令行)
dc exec -T -d -e DASHSCOPE_API_KEY -e DEMO_STRICT=1 api uvicorn app.demo.server:app --host 0.0.0.0 --port 8100
ok=0
for i in $(seq 1 30); do
  curl -fsS "http://127.0.0.1:$DEMO_PORT/ui.json" >/dev/null 2>&1 && { ok=1; break; }; sleep 1
done
[ "$ok" -eq 1 ] || fatal "demo 服务没有起来" "8100 端口无响应"

hr; say "第 4 步:用你的真实 key 上传 3 张图,让真实 Qwen 打标(每张约几秒到十几秒)"; hr
ITEMS_JSON="$TMP/items.json"; echo "[]" >"$ITEMS_JSON"
UP_OK=1
for n in 0 1 2; do
  f="${PICKED[$n]}"
  code="$(curl -sS -m 180 -o "$TMP/resp$n.json" -w '%{http_code}' -F "file=@$TMP/lib/$f;type=image/png" "http://127.0.0.1:$DEMO_PORT/upload" 2>"$TMP/curl.err")"
  if [ "$code" != "200" ]; then
    say "  服务返回 HTTP $code:$(redact <"$TMP/resp$n.json" | head -c 300)"
    if grep -q -E "401|Incorrect API key|InvalidApiKey" "$TMP/resp$n.json"; then
      record ❌ "上传并打标 $f" "百炼提示 key 无效(401)——请检查是否复制完整、是否是「百炼」的 API key、是否已启用/未过期"
    else
      record ❌ "上传并打标 $f" "HTTP $code(见上)——最常见原因:额度用完、网络不通、模型服务暂时不可用"
    fi
    UP_OK=0; continue
  fi
  AID="$(python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print(d["asset_id"] if not d.get("degraded") else "DEGRADED")' "$TMP/resp$n.json")"
  if [ "$AID" = "DEGRADED" ]; then record ❌ "上传并打标 $f" "服务降级到了缓存(不是真实调用)"; UP_OK=0; continue; fi
  say "  已打标:$f → asset_id=$AID"
  SQL="SELECT COALESCE(json_agg(json_build_object('dimension',t.dimension,'value',t.value,'role',t.role,'status',t.status,'source',t.source,'model_id',t.model_id,'prompt_version',t.prompt_version,'provider',k.output->>'_provider') ORDER BY t.tag_id),'[]'::json) FROM tag t JOIN task k ON k.task_id=t.task_id WHERE t.tenant_id=1 AND t.asset_id=$AID"
  dc exec -T postgres psql -U assetlib -d asset_library -At -c "$SQL" >"$TMP/tags$n.json" 2>"$TMP/psql.err" \
    || { record ❌ "读取标签 $f" "$(head -c 200 "$TMP/psql.err")"; UP_OK=0; continue; }
  python3 - "$ITEMS_JSON" "$f" "$AID" "$TMP/tags$n.json" <<'PY'
import json, sys
path, f, aid, tp = sys.argv[1:5]
items = json.load(open(path))
items.append({"file": f, "asset_id": int(aid), "tags": json.load(open(tp))})
json.dump(items, open(path, "w"), ensure_ascii=False)
PY
done

hr; say "第 5 步:逐项检查标签(结果表格)"; hr
if [ "$(python3 -c 'import json,sys;print(len(json.load(open(sys.argv[1]))))' "$ITEMS_JSON")" -gt 0 ]; then
  python3 scripts/smoke_check.py check "packs/$PACK" <"$ITEMS_JSON" >"$TMP/check.out" 2>&1
  grep -v '^RESULT|' "$TMP/check.out"
  while IFS='|' read -r _ ok name det; do record "$ok" "$name" "$det"; done < <(grep '^RESULT|' "$TMP/check.out")
fi
if [ "$UP_OK" -eq 1 ]; then record ✅ "3 张图都通过 API 上传并由真实 Qwen 打标成功" ""; fi

hr; say "第 6 步:反向测试——故意用一个错误的 key,必须得到明确报错(不能悄悄退回 mock)"; hr
BAD_KEY="sk-smoke-wrong-key-000000000000"
dc exec -T -d -e DASHSCOPE_API_KEY="$BAD_KEY" -e DEMO_STRICT=1 api uvicorn app.demo.server:app --host 127.0.0.1 --port 8101
ok=0
for i in $(seq 1 40); do
  if dc exec -T api python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8101/ui.json',timeout=3)" >/dev/null 2>&1; then ok=1; break; fi
  sleep 1
done
[ "$ok" -eq 1 ] || fatal "反向测试用的服务没有起来" "8101 端口无响应"
REV_FILE="${PICKED[3]}"
dc exec -T api python - "$REV_FILE" >"$TMP/rev.out" 2>&1 <<'PY'
import json, sys, urllib.error, urllib.request, uuid
name = sys.argv[1]
data = open(f"demo_assets/library/{name}", "rb").read()
bd = uuid.uuid4().hex
body = (f'--{bd}\r\nContent-Disposition: form-data; name="file"; filename="{name.encode("ascii","ignore").decode() or "x.png"}"\r\n'
        f'Content-Type: image/png\r\n\r\n').encode() + data + f"\r\n--{bd}--\r\n".encode()
req = urllib.request.Request("http://127.0.0.1:8101/upload", body, {"Content-Type": "multipart/form-data; boundary=" + bd})
try:
    r = urllib.request.urlopen(req, timeout=120)
    print(json.dumps({"status": r.status, "body": r.read().decode()[:400]}, ensure_ascii=False))
except urllib.error.HTTPError as e:
    print(json.dumps({"status": e.code, "body": e.read().decode()[:400]}, ensure_ascii=False))
except Exception as e:
    print(json.dumps({"status": -1, "body": repr(e)[:300]}, ensure_ascii=False))
PY
REV="$(tail -1 "$TMP/rev.out")"
REV_STATUS="$(printf '%s' "$REV" | python3 -c 'import json,sys;print(json.load(sys.stdin)["status"])' 2>/dev/null)"
REV_BODY="$(printf '%s' "$REV" | python3 -c 'import json,sys;print(json.load(sys.stdin)["body"])' 2>/dev/null | redact)"
case "$REV_STATUS" in
  502|401|403|500|503)
    if printf '%s' "$REV_BODY" | grep -q "error"; then
      say "  错误 key 的返回:HTTP $REV_STATUS,$(printf '%s' "$REV_BODY" | head -c 200)"
      record ✅ "错误 key 得到明确报错(HTTP $REV_STATUS),没有悄悄退回 mock" ""
    else record ❌ "错误 key 的反向测试" "返回了 HTTP $REV_STATUS 但没有明确的错误信息:$REV_BODY"; fi;;
  200) record ❌ "错误 key 的反向测试" "用错误 key 居然返回成功——说明悄悄退回了 mock/缓存!";;
  *)   record ❌ "错误 key 的反向测试" "结果异常:status=$REV_STATUS $REV_BODY $(redact <"$TMP/rev.out" | tail -3 | tr '\n' ' ' | head -c 300)";;
esac

exit 0
