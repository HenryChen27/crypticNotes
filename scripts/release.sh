#!/usr/bin/env bash
# 一条命令走完发版：打包 → 整理分享仓库 → 推源码 → 推分发分支 → 建 Release。
#
# 用法：
#   scripts/release.sh                  # 全流程。真正推送之前会停下来问你一次
#   scripts/release.sh --local          # 只在本机做完（打包 + 提交），不推送、不发 Release
#   scripts/release.sh --yes            # 不问，直接推
#   scripts/release.sh --no-build       # 跳过 PyInstaller，复用现有 dist/
#   scripts/release.sh --no-share       # 不整理也不推分享仓库的源码
#   scripts/release.sh --no-release     # 推完就停，不建 GitHub Release
#   scripts/release.sh -m "提交信息"     # 两个仓库共用的提交信息
#
# 为什么要有这个脚本：这几步之间是**有顺序的**，而且顺序已经错过一次 ——
# zip 由打包脚本从 `dist/` 压出来，而协作者双击的 `更新.cmd` 是分发脚本才拷进
# `dist/` 的，谁先谁后都会漏东西（上一版 zip 就这么少了更新入口）。串成一串之后
# 这个顺序就没法再记错。
#
# 主仓库 c:\jysj 故意不配远端，本脚本也不会碰它。源码推送走 `release/crypticNotes`
# 这个独立 clone，分发包走 `out/dist_repo`，两者互不相干。

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SHARE="$ROOT/release/crypticNotes"
DIST_GIT="$ROOT/out/dist_repo/.git"
DIST_TREE="$ROOT/dist/IdentityVMapAssistant"
REMOTE=origin
SHARE_BRANCH=main
DIST_BRANCH=dist

DO_BUILD=1
DO_SHARE=1
DO_RELEASE=1
DO_PUSH=1
ASSUME_YES=0
MESSAGE=""
NOTE=""

usage() {
  cat <<'USAGE'
一条命令走完发版：打包 → 整理分享仓库 → 推源码 → 推分发分支 → 建 Release。

  scripts/release.sh                  全流程。真正推送之前会停下来问你一次
  scripts/release.sh --local          只在本机做完（打包 + 提交），不推送、不发 Release
  scripts/release.sh --yes            不问，直接推
  scripts/release.sh --no-build       跳过 PyInstaller，复用现有 dist/
  scripts/release.sh --no-share       不整理也不推分享仓库的源码
  scripts/release.sh --no-release     推完就停，不建 GitHub Release
  scripts/release.sh -m "提交信息"     两个仓库共用的提交信息
  scripts/release.sh --note "本次更新"  Release 正文里「本次更新」一节的内容

不给 --note 时，那一节由「上个 Release 以来的提交标题」自动生成。但分享仓库的提交
标题基本都是 `release: 更新源码与地图库`（真正的工作在开发仓库里，每次发版压成一条），
所以自动生成的结果通常很单薄 —— 想让人看到什么，就用 --note 写一句。
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --local)      DO_PUSH=0; DO_RELEASE=0 ;;
    --yes|-y)     ASSUME_YES=1 ;;
    --no-build)   DO_BUILD=0 ;;
    --no-share)   DO_SHARE=0 ;;
    --no-release) DO_RELEASE=0 ;;
    -m)           shift; MESSAGE="${1:-}" ;;
    --note)       shift; NOTE="${1:-}" ;;
    -h|--help)    usage; exit 0 ;;
    *)            echo "未知参数: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

step() { printf '\n=== %s ===\n' "$1"; }

# 打包脚本要 PyInstaller 和 PySide6，走 .venv 最稳；其余脚本只用标准库。
PYTHON_BIN="${PYTHON:-}"
if [ -z "$PYTHON_BIN" ]; then
  for candidate in "$ROOT/.venv/Scripts/python.exe" python py python3; do
    if [ -x "$candidate" ] || command -v "$candidate" >/dev/null 2>&1; then PYTHON_BIN="$candidate"; break; fi
  done
fi
[ -n "$PYTHON_BIN" ] || { echo "找不到 python。" >&2; exit 1; }
export PYTHON="$PYTHON_BIN"   # publish_dist.sh 会用它来注入更新入口
# 本脚本的中文是 UTF-8 字节直出；Python 默认按控制台代码页写。不统一的话，
# 同一条输出流里总有一边是乱码。
export PYTHONIOENCODING=utf-8

# ---- 1. 打包 ----
# build_windows.py 在 PyInstaller 之后会调 finalize_release.finalize()：
# 补 README/third-party → **注入更新入口** → 压 zip → 写 SHA256SUMS。
# 注入必须在压缩之前，这就是原来那个顺序坑。
if [ "$DO_BUILD" = 1 ]; then
  step "1/5 打包（地图索引 → PyInstaller → 注入更新入口 → 压 zip）"
  "$PYTHON_BIN" "$ROOT/scripts/build_windows.py"
else
  step "1/5 打包（--no-build，复用现有 dist/）"
fi

# ---- 2. 整理分享仓库 ----
if [ "$DO_SHARE" = 1 ]; then
  step "2/5 整理分享仓库（按白名单导出源码，不含缓存与本机状态）"
  "$PYTHON_BIN" "$ROOT/scripts/prepare_share.py"
  git -C "$SHARE" add -A
  if git -C "$SHARE" diff --cached --quiet; then
    echo "  与上一次逐字节相同，没有新的源码提交。"
  else
    [ -n "$MESSAGE" ] || MESSAGE="release: 更新源码与地图库"
    git -C "$SHARE" commit -q -m "$MESSAGE"
    echo "  已提交： $(git -C "$SHARE" --no-pager log --oneline -1)"
  fi
else
  step "2/5 整理分享仓库（--no-share，跳过）"
fi

# ---- 3. 组装分发目录 ----
# `--local` 让它只提交不推送：所有东西先在本机备好，等一下一次性确认。
step "3/5 组装分发目录并提交 $DIST_BRANCH 分支"
dist_args=(--local)
if [ -n "$MESSAGE" ]; then dist_args+=(-m "$MESSAGE"); fi
"$ROOT/scripts/publish_dist.sh" "${dist_args[@]}"

SHARE_SHA="$(git -C "$SHARE" rev-parse --short HEAD)"
SHARE_STAMP="$(git -C "$SHARE" log -1 --format=%cd --date=format:%Y%m%d)"
TAG="desktop-update-${SHARE_STAMP}-${SHARE_SHA}"

# ---- 4. 确认 ----
if [ "$DO_PUSH" = 0 ]; then
  step "4/5 收工（--local）"
  echo "  本机已经全部备好，一个字节都没有推出去："
  echo "    dist/IdentityVMapAssistant  成品目录（含更新入口）"
  echo "    release/*.zip + SHA256SUMS  便携包"
  echo "    release/crypticNotes        源码分享树，已提交"
  echo "    out/dist_repo               $DIST_BRANCH 分支，已提交"
  echo
  echo "  去掉 --local 重跑一次即可推送（会再问你一次）。"
  exit 0
fi

step "4/5 即将推送"
echo "  源码    ： $SHARE → $REMOTE/$SHARE_BRANCH"
echo "            $(git -C "$SHARE" --no-pager log --oneline -1)"
echo "  分发包  ： dist/IdentityVMapAssistant → $REMOTE/$DIST_BRANCH"
if [ "$DO_RELEASE" = 1 ]; then
  echo "  Release ： $TAG"
else
  echo "  Release ： 跳过（--no-release）"
fi
echo
echo "  推送是外向且不可逆的：这一步会把源码和分发包都公开更新，"
echo "  协作者下次双击 更新.cmd 就会拿到这一版。"
if [ "$ASSUME_YES" = 1 ]; then
  echo "  --yes：直接推送。"
else
  answer=""
  read -r -p "  确认推送？[y/N] " answer || true
  case "$answer" in
    [yY]*) ;;
    *) echo "  已取消。本机的打包和提交都还在，随时重跑本脚本即可。"; exit 1 ;;
  esac
fi

# ---- 5. 推送并发布 ----
step "5/5 推送并发布"
if [ "$DO_SHARE" = 1 ]; then
  git -C "$SHARE" push "$REMOTE" "$SHARE_BRANCH"
else
  echo "  源码： --no-share，跳过"
fi
GIT_DIR="$DIST_GIT" GIT_WORK_TREE="$DIST_TREE" git push "$REMOTE" "$DIST_BRANCH"

if [ "$DO_RELEASE" = 1 ]; then
  release_args=(-Tag "$TAG")
  if [ -n "$NOTE" ]; then release_args+=(-Note "$NOTE"); fi
  powershell -NoProfile -ExecutionPolicy Bypass -File "$ROOT/scripts/publish_release.ps1" "${release_args[@]}"
else
  echo "  Release： --no-release，跳过"
fi

echo
echo "完成。"
