#!/usr/bin/env bash
# 发版:版本校验 → 离线自检 → 构建 dist → 打 zip → 提交推送 → 建 GitHub Release
#
#   scripts/release.sh SiteLevelBoard 0.1.3            完整发版(需 gh 或 GITHUB_TOKEN)
#   scripts/release.sh SiteLevelBoard 0.1.3 --dry-run  只校验 + 打 zip,不提交不发 Release
#
# MoviePilot 的硬要求(写错装不上):tag = <PluginId>_v<版本>,
# 资产名 = tag 全小写 + .zip,zip 根目录就是插件文件。
set -euo pipefail

PLUGIN_ID="${1:?用法: scripts/release.sh <PluginId> <version> [--dry-run]}"
VERSION="${2:?缺少版本号}"
MODE="${3:-}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PLUGIN_DIR="plugins/$(echo "$PLUGIN_ID" | tr '[:upper:]' '[:lower:]')"
[ -d "$PLUGIN_DIR" ] || { echo "✗ 找不到插件目录:$PLUGIN_DIR"; exit 1; }

TAG="${PLUGIN_ID}_v${VERSION}"
ASSET="$(echo "$TAG" | tr '[:upper:]' '[:lower:]').zip"

echo "==> 版本校验"
MANIFEST_VERSION="$(python3 -c "import json;print(json.load(open('package.json'))['${PLUGIN_ID}']['version'])")"
PLUGIN_VERSION="$(grep -m1 'plugin_version =' "$PLUGIN_DIR/__init__.py" | sed 's/.*"\(.*\)".*/\1/')"
[ "$MANIFEST_VERSION" = "$VERSION" ] || { echo "✗ package.json 是 $MANIFEST_VERSION,与 $VERSION 不一致"; exit 1; }
[ "$PLUGIN_VERSION" = "$VERSION" ] || { echo "✗ __init__.py 里 plugin_version 是 $PLUGIN_VERSION,与 $VERSION 不一致"; exit 1; }
echo "    package.json / plugin_version 都是 $VERSION"

echo "==> 离线自检"
python3 scripts/selfcheck.py

echo "==> 前端产物"
if [ -d "$PLUGIN_DIR/node_modules" ] && command -v node >/dev/null 2>&1; then
  ( cd "$PLUGIN_DIR" && node node_modules/vite/bin/vite.js build )
else
  echo "    ⚠ 没有 node_modules 或 node,直接用已提交的 dist/ —— 请确认它就是当前源码构建出来的"
fi

echo "==> 打 zip:$ASSET"
rm -f "$ASSET"
( cd "$PLUGIN_DIR" && zip -r -X -q "$ROOT/$ASSET" . \
    -x 'node_modules/*' '*/node_modules/*' '__pycache__/*' '*/__pycache__/*' '*.pyc' '.DS_Store' '._*' )
ls -l "$ASSET" | awk '{print "    " $5 " bytes  " $9}'

if [ "$MODE" = "--dry-run" ]; then
  echo "==> --dry-run:跳过提交与 Release,产物在 $ROOT/$ASSET"
  exit 0
fi

echo "==> 提交推送"
git add -A
git diff --cached --quiet || git commit -m "release(${PLUGIN_ID}): v${VERSION}"
git push origin main

echo "==> 建 GitHub Release"
REMOTE_URL="$(git remote get-url origin)"
USER_REPO="$(echo "$REMOTE_URL" | sed -E 's#.*[:/]([^/]+/[^/]+?)(\.git)?$#\1#')"

if command -v gh >/dev/null 2>&1; then
  gh release create "$TAG" "$ASSET" --title "$TAG" --notes "详见 package.json 的 history.v${VERSION}"
elif [ -n "${GITHUB_TOKEN:-}" ]; then
  RELEASE_ID="$(python3 - "$USER_REPO" "$TAG" "$VERSION" <<'PY'
import json, os, sys, urllib.request
user_repo, tag, version = sys.argv[1], sys.argv[2], sys.argv[3]
body = json.dumps({"tag_name": tag, "name": tag,
                   "body": f"详见 package.json 的 history.v{version}"}).encode()
req = urllib.request.Request(
    f"https://api.github.com/repos/{user_repo}/releases", data=body,
    headers={"Authorization": "token " + os.environ["GITHUB_TOKEN"],
             "Accept": "application/vnd.github+json", "Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=60) as resp:
    print(json.load(resp)["id"])
PY
)"
  curl -sS -X POST \
    -H "Authorization: token ${GITHUB_TOKEN}" \
    -H "Content-Type: application/zip" \
    --data-binary @"$ASSET" \
    "https://uploads.github.com/repos/${USER_REPO}/releases/${RELEASE_ID}/assets?name=${ASSET}" >/dev/null
  echo "    Release $TAG 已创建,资产 $ASSET 已上传"
else
  echo "✗ 既没有 gh 也没有 GITHUB_TOKEN:zip 已生成,请手动建 Release"
  echo "    tag   = $TAG"
  echo "    asset = $ASSET"
  exit 1
fi

echo "==> 完成。MoviePilot 侧验证:GET /api/v1/plugin/releases/${PLUGIN_ID}"
