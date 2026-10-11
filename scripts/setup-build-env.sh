#!/usr/bin/env bash
# 准备前端构建环境(node_modules)。
#
# 本机(DSH 自带 Node)有个坑:rollup 的原生模块会因硬化运行时/库校验加载失败
# (ERR_DLOPEN_FAILED),此时用 `--wasm-rollup` 把 rollup 换成纯 WASM 版即可。
#
#   scripts/setup-build-env.sh                 只装依赖
#   scripts/setup-build-env.sh --wasm-rollup   装依赖 + 换 WASM rollup(推荐)
#
# 环境变量:NODE_BIN / PNPM_BIN 可指定 node / pnpm(默认走 PATH)。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLUGIN_DIR="$ROOT/plugins/sitelevelboard"
NODE_BIN="${NODE_BIN:-node}"
PNPM_BIN="${PNPM_BIN:-pnpm}"
USE_WASM="${1:-}"

command -v "${NODE_BIN%% *}" >/dev/null 2>&1 || { echo "✗ 找不到 node(可用 NODE_BIN=... 指定)"; exit 1; }
command -v "${PNPM_BIN%% *}" >/dev/null 2>&1 || { echo "✗ 找不到 pnpm(可用 PNPM_BIN=... 指定,允许带参数)"; exit 1; }

echo "==> 安装依赖"
# PNPM_BIN 允许带参数(如 "node /path/pnpm.mjs"),这里靠分词展开。
# 注:某些 pnpm 构建会在结尾报 ERR_PNPM_IGNORED_BUILDS(esbuild 的构建脚本被供应链策略拦下),
#     依赖其实已装好、构建照样能跑,所以这里不让它中断脚本。
( cd "$PLUGIN_DIR" && $PNPM_BIN install ) || echo "    ⚠ pnpm 返回非 0(常见:esbuild 构建脚本被策略拦下),继续"

if [ "$USE_WASM" = "--wasm-rollup" ]; then
  # rollup 是 vite 的传递依赖,pnpm 的严格 node_modules 里没有顶层入口 → 直接去 .pnpm 里找
  ROLLUP_DIR="$(ls -d "$PLUGIN_DIR"/node_modules/.pnpm/rollup@*/node_modules/rollup 2>/dev/null | head -1)"
  [ -n "$ROLLUP_DIR" ] || { echo "✗ 没找到 rollup 包目录(先装依赖)"; exit 1; }
  ROLLUP_VERSION="$(sed -n 's/.*"version": "\([^"]*\)".*/\1/p' "$ROLLUP_DIR/package.json" | head -1)"
  echo "==> 用 @rollup/wasm-node@$ROLLUP_VERSION 替换 $ROLLUP_DIR"
  TMP_DIR="$(mktemp -d)"
  trap 'rm -rf "$TMP_DIR"' EXIT
  curl -sSL "https://registry.npmjs.org/@rollup/wasm-node/-/wasm-node-${ROLLUP_VERSION}.tgz" \
    | tar xz -C "$TMP_DIR"
  rm -rf "$ROLLUP_DIR"
  mkdir -p "$ROLLUP_DIR"
  cp -R "$TMP_DIR/package/." "$ROLLUP_DIR/"
  echo "    替换完成"
fi

echo "==> 试构建"
( cd "$PLUGIN_DIR" && "$NODE_BIN" node_modules/vite/bin/vite.js build )
echo "==> 完成"
