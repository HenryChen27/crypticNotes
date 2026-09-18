#!/usr/bin/env bash
# 把 dist/IdentityVMapAssistant 的当前内容发布到 crypticNotes 仓库的 dist 分支，
# 让协作者用 git 增量更新，不必每次重下 223 MB 的 zip。
#
# 为什么 git 目录不放在 dist 里：
#   打包脚本每次会先删掉整个 dist/，.git 放里面会被一起删掉。
#   这里用「独立 GIT_DIR + 指向 dist 的工作树」，打包删了 dist 也不影响仓库。
#
# 用法：
#   scripts/publish_dist.sh                 # 提交并推送
#   scripts/publish_dist.sh --local         # 只提交，不推送（先看看要传多少）
#   scripts/publish_dist.sh -m "提交信息"    # 自定义提交信息

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_TREE="$ROOT/dist/IdentityVMapAssistant"
export GIT_DIR="$ROOT/out/dist_repo/.git"
export GIT_WORK_TREE="$WORK_TREE"
BRANCH=dist
REMOTE=origin
PUSH=1
MESSAGE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --local) PUSH=0 ;;
    -m) shift; MESSAGE="${1:-}" ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
  shift
done

[ -d "$WORK_TREE" ] || { echo "找不到 $WORK_TREE —— 先跑一次打包。" >&2; exit 1; }
[ -d "$GIT_DIR" ] || { echo "找不到 $GIT_DIR —— 分发仓库还没建过。" >&2; exit 1; }

# ---- 1. 注入分发型文件 ----
# 打包会清空 dist/，所以这两个文件每次发布都重新生成，保证内容只有一个来源。
cat > "$WORK_TREE/.gitignore" <<'GITIGNORE'
# 这个文件随仓库分发。它划定「哪些文件不属于发布内容」：让协作者那边的
# `git status` 保持干净，也让发布脚本的 `git add -A` 不会把各台机器自己的
# 运行时状态误当成新版内容提交上来。
# 要改规则请改 scripts/publish_dist.sh 里的这一段，别手改安装目录里的副本。

# —— 每台机器各自的运行时状态 ——
# 「管理地图」里移除过哪些图。文件不存在时程序按「全部启用」处理，
# 所以不跟踪它是安全的。
maps/disabled.json

# 「放进来但还没登记」的临时堆放区。协作者往这里丢的原图不会被更新动到。
maps/_unindexed/

# —— 打包/运行残留 ——
__pycache__/
*.pyc
out/
*.log
ui.lock
GITIGNORE

# 分发目录里只有这两个文件对「行尾」敏感，所以强制按二进制原样存取。
# 它们到了协作者机器上必须是 CRLF：`更新.cmd` 是 cmd.exe 的批处理（按字节偏移
# 定位下一行，行尾不对会从行中间开始执行），`update-client.ps1` 还额外要求
# UTF-8 BOM。各人机器的 core.autocrlf 三档（true / false / input）都常见，
# 这里要保证的是「无论对方怎么配，拿到的字节都跟发布时一模一样」——
# 光靠本机实测「这次没坏」是不够的，对方那台机器的设置我们看不到。
cat > "$WORK_TREE/.gitattributes" <<'GITATTR'
# 这个文件随仓库分发。要改规则请改 scripts/publish_dist.sh 里的这一段，
# 别手改安装目录里的副本。
更新.cmd                   -text
scripts/update-client.ps1  -text
GITATTR

# `更新.cmd` / `update-client.ps1` 是协作者双击更新的入口，必须随包发出去。
# 拷贝和编码校验（.cmd 纯 ASCII、.ps1 带 UTF-8 BOM）都在 scripts/dist_extras.py 里，
# 打包脚本 finalize_release.py 走的是同一个函数 —— 两边各写一份迟早会漂移，
# 而漂移的后果是协作者那边双击没反应、本地却看不出来。
PYTHON_BIN="${PYTHON:-}"
if [ -z "$PYTHON_BIN" ]; then
  for candidate in python py python3 "$ROOT/.venv/Scripts/python.exe"; do
    if command -v "$candidate" >/dev/null 2>&1; then PYTHON_BIN="$candidate"; break; fi
  done
fi
[ -n "$PYTHON_BIN" ] || { echo "找不到 python，无法注入更新入口。" >&2; exit 1; }
# 本脚本自己的中文是 UTF-8 字节直出；Python 默认按控制台代码页写，两边混在一条
# 输出流里会有一边乱码。统一成 UTF-8。
PYTHONIOENCODING=utf-8 "$PYTHON_BIN" "$ROOT/scripts/dist_extras.py" "$WORK_TREE"

# ---- 2. 暂存并汇总 ----
git add -A

if git diff --cached --quiet; then
  echo "dist/ 与上一次发布逐字节相同，没有需要提交的变化。"
  exit 0
fi

echo "本次变化的文件："
git -c core.quotepath=false diff --cached --name-only | sed 's/^/  /'

size=$(git diff --cached --name-only -z \
  | while IFS= read -r -d '' f; do
      [ -f "$WORK_TREE/$f" ] && stat -c %s "$WORK_TREE/$f"
    done | awk '{s+=$1} END{printf "%.1f", s/1048576}')
echo
echo "变化内容合计约 ${size} MiB（原始大小）。"
echo "推送时 git 只传内容真的变了的文件，与上次相同的部分不会重传，"
echo "所以实际传输量通常明显小于这个数。"

# ---- 3. 提交 ----
[ -n "$MESSAGE" ] || MESSAGE="release: 更新分发内容"
git commit -q -m "$MESSAGE"
echo
echo "已提交： $(git --no-pager log --oneline -1)"

# ---- 4. 推送 ----
if [ "$PUSH" = "1" ]; then
  echo "正在推送到 $REMOTE/$BRANCH ..."
  git push "$REMOTE" "$BRANCH"
else
  echo "（--local：已跳过推送）"
fi
