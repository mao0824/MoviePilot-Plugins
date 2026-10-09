# MoviePilot Plugins (by mao0824)

自用的 MoviePilot 插件集合,持续更新。所有插件均**不绑定特定环境**:设备名、下载器名、站点、阈值都通过配置页设置。

## 插件列表

| 插件 | 版本 | 说明 |
|---|---|---|
| [NAS 哨兵](plugins/nassentinel) `NasSentinel` | v0.1.0 | 通用巡检哨兵:站点签到补位、NexusPHP 考核进度追踪、刷流与磁盘 IO 健康巡检,每日简报 + 异常即报 |

## 安装

MoviePilot → 设置 → 插件 → **添加插件仓库**,填入本仓库地址:

```
https://github.com/mao0824/MoviePilot-Plugins
```

然后在本仓库来源下安装所需插件即可。

## 仓库结构

```
package.json                    # 插件索引(MoviePilot 市场读取)
plugins/
└── <plugin_id>/__init__.py     # 插件本体(目录名 = 插件类名的小写)
```

新增插件时:放好 `plugins/<id>/__init__.py`,并在 `package.json` 里加一条同结构条目即可。

## 许可

MIT
