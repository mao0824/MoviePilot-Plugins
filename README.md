# MoviePilot Plugins (by mao0824)

MoviePilot **v3** 插件市场仓库。

## 插件列表

| 插件 | 版本 | 说明 |
|---|---|---|
| [站点等级看板](plugins/sitelevelboard) `SiteLevelBoard` | v0.1.3 | 把绑定站点的等级 / 下一级条件 / ETA / 全部阶梯 / 保号与封号风险汇成一页，附流量时间线 |

## 安装

MoviePilot → 设置 → 插件 → **添加插件仓库**，填入本仓库地址：

```
https://github.com/mao0824/MoviePilot-Plugins
```

然后在本仓库来源下安装 `SiteLevelBoard` 即可。

## 设计约定

- **不绑定任何特定环境**：站点、阈值、通知渠道全部走配置页；
- **不依赖其它插件**：数据只来自 MoviePilot 自带的 `user.db`（`siteuserdata` 每日快照）、站点页，
  以及插件自己落盘的数据；
- **等级规则**：站点页优先 → 内置快照（来源 [PT-depiler](https://github.com/pt-plugins/PT-depiler)，MIT）兜底 → 可手动覆盖。

## 仓库结构

```
package.json                    # 插件索引（MoviePilot 市场读取，只列公开插件）
icons/                          # 插件图标（plugin_icon 用本仓库的 raw 地址）
plugins/<plugin_id>/            # 插件本体（目录名 = 插件类名小写）
scripts/release.sh              # 发版：自检 → 构建 dist → 打 zip → 推 tag/Release
scripts/selfcheck.py            # 离线自检（不需要装 MoviePilot）
```

## 发版

```bash
scripts/release.sh SiteLevelBoard 0.1.3
```

MoviePilot 对 Release 的命名有硬要求，写错就装不上：

- tag = `<PluginId>_v<版本>`，例如 `SiteLevelBoard_v0.1.3`；
- 资产名 = **tag 全小写** + `.zip`，例如 `sitelevelboard_v0.1.3.zip`；
- **zip 根目录就是插件文件**（`__init__.py`、`dist/`、`README.md` …），不要多套一层目录名。

## 改前端（本地构建）

`dist/` 是提交进仓库的，只改 Python 时不需要构建。要动 `src/` 时：

```bash
scripts/setup-build-env.sh --wasm-rollup
```

`--wasm-rollup` 用来绕开一个环境坑：部分 Node 发行版（硬化运行时 + 库校验）加载 rollup 原生模块会
报 `ERR_DLOPEN_FAILED`，换成纯 WASM 版即可；依赖安装末尾若出现
`ERR_PNPM_IGNORED_BUILDS: esbuild`，忽略它，构建照常能跑。`NODE_BIN` / `PNPM_BIN` 可指定 node / pnpm。

## 许可

MIT。等级规则与字段口径参考 **PT-depiler / PT-Plugin-Plus**（均为 MIT）。
