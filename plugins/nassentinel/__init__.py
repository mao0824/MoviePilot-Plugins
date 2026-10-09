"""
NAS 哨兵 (nas-sentinel) — MoviePilot 插件

聚焦「刷流与磁盘 IO 健康」:把不需要人盯的事交给它,到点告警。

范围(2026-10-10 用户决定):站点签到交给 AutoSignIn(实测可签 PTS),
新手考核交给专门的考核插件 —— 本插件不再重复实现,只保留 IO 哨兵、
自动降级/恢复、刷流促销守护与简报。

设计原则(为了将来能发布给其他人用):
  * 不写死任何本机路径/设备名/下载器名,全部可配置
  * 失败隔离:任一模块异常不影响其它模块,全部输出到日志

渲染契约(踩坑记录,MP v3 前端 renderer 的真实行为):
  * 文本必须放 ``props.text``(如 VAlert: {"props": {"text": "..."}});
    顶层 ``content`` 只能是「子节点 dict 的列表」,塞字符串会渲染成空。
  * ``VSubheader`` 在 Vuetify 3 已被移除,前端 bundle 里零出现 -> 分节标题
    改用 ``div`` + ``text``。
  * 只读展示不能用 ``model-value``:表单渲染器用 v-model 绑定 model,
    会把静态值覆盖掉 -> 改用 ``div`` + ``props.text``(``text-pre-wrap`` 保换行)。
  * MP 自定义组件除 Vuetify 全量组件外还有:VCronField / VPathField /
    VDialogCloseBtn / VAceEditor / VApexChart / VPageContentTitle 等。
"""

import re
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests
from apscheduler.triggers.cron import CronTrigger

from app.log import logger
from app.plugins import _PluginBase

# ---- 可选依赖:尽量不让插件因 mp 版本差异而加载失败 -------------------------
try:
    from app.schemas.types import MessageType
    # 注意:MessageType 没有 Notification 成员(只有 Download/Organize/Subscribe/
    # SiteMessage/MediaServer/Manual/Plugin/Agent/Other),插件消息用 Plugin。
    # 传 None 会导致「邮箱通知」等渠道插件报 'NoneType' object has no attribute 'value'。
    _MSG_TYPE = getattr(MessageType, "Plugin", None)
except Exception:  # pragma: no cover
    _MSG_TYPE = None

try:
    # 通知渠道是枚举(值=中文显示名),post_message(channel=...) 要传「枚举成员」,
    # 所以配置里存成员名(如 Web / Telegram),用 getattr 还原。
    from app.schemas.types import NotificationChannel
except Exception:  # pragma: no cover
    NotificationChannel = None

class NasSentinel(_PluginBase):
    # ---- 插件元信息 ---------------------------------------------------------
    plugin_name = "NAS 哨兵"
    plugin_desc = "刷流与磁盘 IO 健康哨兵:积压/队列/上传速率巡检、超红线自动降级、刷流促销敞口守护。"
    plugin_icon = "sentinel.png"
    plugin_version = "0.4.0"
    plugin_author = "Niven"
    author_url = "https://github.com/mao0824"
    plugin_config_prefix = "nassentinel_"
    plugin_order = 50
    auth_level = 1

    # ---- 运行时状态:通用 ----------------------------------------------------
    _enabled = False
    _notify = True
    _notify_daily = True
    _notify_issue = True
    _notify_channel = ""
    _cron = "30 8 * * *"
    _debug = False
    _quiet_start = ""
    _quiet_end = ""

    # ---- IO ---------------------------------------------------------------
    _io_enabled = True
    _io_interval = 5
    _io_sample_seconds = 3
    _io_devices = ""
    _load_threshold = 8.0
    _load_check = False
    _queue_threshold = 50
    _iowait_threshold = 0.0
    _latency_threshold = 1500.0
    _up_rate_min = 1.0
    _io_check_qbt = True
    # 保留采样条数:288 ≈ 24h@5min(与配置页默认值保持一致)
    _io_keep = 288
    _io_notify_cooldown = 30

    # ---- 自动降级 / 恢复 ---------------------------------------------------
    _auto_downgrade = False
    _downgrade_step = 1
    _downgrade_min = 2
    _downgrade_cooldown = 30
    _auto_recover = False
    _recover_step = 1
    _recover_wait = 30

    _qb_downloader = ""

    def init_plugin(self, config: dict = None):
        cfg = config or {}
        # 通用
        self._enabled = bool(cfg.get("enabled"))
        self._notify = cfg.get("notify", True)
        self._notify_daily = cfg.get("notify_daily", True)
        self._notify_issue = cfg.get("notify_issue", True)
        self._notify_channel = (cfg.get("notify_channel") or "").strip()
        self._cron = (cfg.get("cron") or "30 8 * * *").strip()
        self._debug = bool(cfg.get("debug"))
        self._quiet_start = (cfg.get("quiet_start") or "").strip()
        self._quiet_end = (cfg.get("quiet_end") or "").strip()

        # IO
        self._io_enabled = cfg.get("io_enabled", True)
        self._io_interval = self.__as_int(cfg.get("io_interval"), 5, 1, 1440)
        self._io_sample_seconds = self.__as_int(cfg.get("io_sample_seconds"), 3, 1, 30)
        self._io_devices = (cfg.get("io_devices") or "").strip()
        self._load_threshold = self.__as_float(cfg.get("load_threshold"), 8.0)
        # 默认不拿负载当告警判据:实测本机负载常态 7.4~9.8(负载含 IO 等待),
        # 用它告警会持续误报;真正对应「上传被随机 IO 掐死」的是队列 + 上传下限。
        self._load_check = bool(cfg.get("load_check"))
        self._queue_threshold = self.__as_float(cfg.get("queue_threshold"), 50)
        self._iowait_threshold = self.__as_float(cfg.get("iowait_threshold"), 0.0)
        self._latency_threshold = self.__as_float(cfg.get("latency_threshold"), 1500.0)
        self._up_rate_min = self.__as_float(cfg.get("up_rate_min"), 1.0)
        self._io_check_qbt = cfg.get("io_check_qbt", True)
        self._io_keep = self.__as_int(cfg.get("io_keep"), 288, 1, 500)
        self._io_notify_cooldown = self.__as_int(cfg.get("io_notify_cooldown"), 30, 1, 1440)

        # 刷流促销守护:站点「免费」是限时的,排队久了会在免费期结束后才开跑 -> 计下载量
        self._promo_check = cfg.get("promo_check", True)
        self._promo_lead_hours = self.__as_float(cfg.get("promo_lead_hours"), 6.0)

        # 降级 / 恢复
        self._auto_downgrade = bool(cfg.get("auto_downgrade"))  # 默认关闭
        self._downgrade_step = self.__as_int(cfg.get("downgrade_step"), 1, 1, 50)
        self._downgrade_min = self.__as_int(cfg.get("downgrade_min"), 2, 1, 100)
        self._downgrade_cooldown = self.__as_int(cfg.get("downgrade_cooldown"), 30, 1, 1440)
        self._auto_recover = bool(cfg.get("auto_recover"))
        self._recover_step = self.__as_int(cfg.get("recover_step"), 1, 1, 50)
        self._recover_wait = self.__as_int(cfg.get("recover_wait"), 30, 1, 1440)

        self._qb_downloader = (cfg.get("qb_downloader") or "").strip()

        # 「立即运行一次」:保存配置后触发一次完整巡检(不改变开关状态)
        if cfg.get("run_once"):
            logger.info("【NAS哨兵】检测到「立即运行一次」,将后台执行一次完整巡检")
            threading.Thread(target=self.run_daily, kwargs={"manual": True}, daemon=True).start()

    # =====================================================================
    # 对外契约
    # =====================================================================
    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_render_mode() -> Tuple[str, Optional[str]]:
        return "vuetify", None

    def get_service(self) -> List[Dict[str, Any]]:
        services: List[Dict[str, Any]] = []
        if not self._enabled:
            return services

        # 1) 每日巡检:IO + 促销敞口 + 简报
        if self.__cron_ok(self._cron):
            services.append({
                "id": "NasSentinelDaily",
                "name": "NAS哨兵-每日巡检",
                "trigger": CronTrigger.from_crontab(self._cron),
                "func": self.run_daily,
                "kwargs": {},
            })
        # 2) IO 哨兵:按间隔采样,异常即报
        if self._io_enabled:
            services.append({
                "id": "NasSentinelIO",
                "name": "NAS哨兵-IO巡检",
                "trigger": "interval",
                "func": self.run_io,
                "kwargs": {"minutes": self._io_interval},
            })
        return services

    def get_api(self) -> List[Dict[str, Any]]:
        # 同时供「插件页面按钮」调用:events.click.api = plugin/<类名><path>
        return [
            {"path": "/run", "endpoint": self.api_run, "methods": ["GET", "POST"],
             "auth": "bear", "summary": "立即执行一次完整巡检(IO+促销敞口)"},
            {"path": "/io", "endpoint": self.api_io, "methods": ["GET", "POST"],
             "auth": "bear", "summary": "立即执行一次 IO 巡检"},
            {"path": "/promo", "endpoint": self.api_promo, "methods": ["GET", "POST"],
             "auth": "bear", "summary": "立即检查刷流种子的免费期敞口"},
            {"path": "/enable", "endpoint": self.api_enable, "methods": ["GET", "POST"],
             "auth": "bear", "summary": "启用本插件(等效于插件列表开关)"},
            {"path": "/disable", "endpoint": self.api_disable, "methods": ["GET", "POST"],
             "auth": "bear", "summary": "禁用本插件(等效于插件列表开关)"},
            {"path": "/test_notify", "endpoint": self.api_test_notify, "methods": ["GET", "POST"],
             "auth": "bear", "summary": "发送一条测试通知(忽略免打扰时段)"},
        ]

    # ---------------------------------------------------------------------
    # 配置表单
    # ---------------------------------------------------------------------
    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        chan_opts = [{"title": "全部渠道(默认)", "value": ""}]
        if NotificationChannel is not None:
            for m in NotificationChannel:
                chan_opts.append({"title": str(m.value), "value": m.name})

        return [
            {
                "component": "VForm",
                "content": [
                    # ========== 顶部快捷区(与 mp 其他插件的三连开关一致)==========
                    self.__row([
                        self.__switch("enabled", "启用插件", 3),
                        self.__switch("run_once", "保存后立即运行一次", 3),
                        self.__switch("notify", "启用通知", 3),
                        self.__switch("notify_daily", "每日简报", 3),
                    ]),
                    self.__alert("本页是「配置」。可点按钮(启用/禁用插件、立即巡检、测试通知)在"
                                 "插件列表里本插件的「数据」页 —— 配置表单渲染器不绑定点击事件,"
                                 "放在这里点了没反应,故统一放到数据页。", "info", 12),

                    # ========== ① 通用 ==========
                    self.__card("① 通用", "mdi-tune", [
                        self.__row([
                            self.__cron("cron", "每日巡检周期(cron)", 4, "30 8 * * *"),
                            self.__select("notify_channel", "通知渠道", 4, chan_opts, multiple=False),
                            self.__switch("notify_issue", "异常即报", 4),
                        ]),
                        self.__row([
                            self.__text("quiet_start", "免打扰开始(HH:MM)", 4, "如 23:30,留空=不启用"),
                            self.__text("quiet_end", "免打扰结束(HH:MM)", 4, "如 07:00"),
                            self.__switch("debug", "详细日志", 4),
                        ]),
                        self.__alert("下面各分组里,只有「已启用」的模块才会展开其详细参数"
                                     "(条件显隐由 MP 的 v-show 合并默认值机制保证安全)。",
                                     "info", 12),
                    ]),

                    # ========== ② IO 哨兵 ==========
                    self.__card("② 磁盘 / 刷流 IO 哨兵", "mdi-speedometer", [
                        self.__row([
                            self.__switch("io_enabled", "启用 IO 巡检", 3),
                            self.__text("io_interval", "采样间隔(分钟)", 3, "5"),
                            self.__text("io_sample_seconds", "采样窗口(秒)", 3, "3"),
                            self.__text("io_keep", "保留最近采样条数(288≈24h@5min)", 3, "288"),
                        ]),
                        self.__row([
                            self.__text("io_notify_cooldown", "告警冷却(分钟)", 3, "30"),
                            self.__switch("io_check_qbt", "检查刷流下载器速率", 3),
                            self.__text("qb_downloader", "刷流下载器名(留空=自动)", 3, "如:刷流"),
                            self.__text("io_devices", "监控设备(逗号分隔,留空=自动)", 3, "如:sda,sata1"),
                        ], show="io_enabled"),
                        self.__row([
                            self.__text("queue_threshold", "磁盘队列红线(告警判据)", 3, "50"),
                            self.__text("up_rate_min", "上传速率下限 MB/s(告警判据)", 3, "1.0"),
                            self.__text("load_threshold", "负载红线(仅记录)", 3, "8"),
                            self.__text("iowait_threshold", "IO 等待红线 %,0=不告警", 3, "0"),
                        ], show="io_enabled"),
                        self.__row([
                            self.__switch("load_check", "负载也参与告警(默认关)", 4),
                            self.__text("latency_threshold", "写延迟参考红线(ms,0=不检查)", 8, "1500"),
                        ], show="io_enabled"),
                        self.__alert("告警判据只保留「磁盘队列」与「上传速率下限」:本机负载含 IO 等待,"
                                     "实测常态就在 7.4~9.8,用负载判据会持续误报;而队列突发到 100+ 时"
                                     "上传会瞬间掉到 0 附近 —— 那才是「上传被随机 IO 掐死」的真信号。"
                                     "负载与 IO 等待仍会照常记录在结果里,需要时可打开上面的开关。",
                                     "info", 12, show="io_enabled"),
                        self.__alert("写延迟在写缓存 flush 突发时会飙到上千毫秒而队列仍很小,"
                                     "属于正常现象,因此默认阈值放得很宽(1500ms)或置 0 关闭。",
                                     "warning", 12, show="io_enabled"),
                    ]),

                    # ========== ③ 自动降级 / 恢复 ==========
                    self.__card("③ 自动降级 / 自动恢复(默认关闭)", "mdi-shield-alert-outline", [
                        self.__row([
                            self.__switch("auto_downgrade", "超红线自动降下载并发", 6),
                            self.__switch("auto_recover", "恢复后自动升回并发", 6),
                        ]),
                        self.__row([
                            self.__text("downgrade_step", "每次降低档数", 4, "1"),
                            self.__text("downgrade_min", "并发最低下限", 4, "2"),
                            self.__text("downgrade_cooldown", "降级冷却(分钟)", 4, "30"),
                        ], show="auto_downgrade"),
                        self.__row([
                            self.__text("recover_step", "每次升高档数", 6, "1"),
                            self.__text("recover_wait", "连续正常多久才升回(分钟)", 6, "30"),
                        ], show="auto_recover"),
                        self.__alert("会自动修改刷流下载器的并发上限。默认关闭;首次降级时记下当时并发"
                                     "作为升回基线。", "warning", 12),
                    ]),

                    # ========== ④ 刷流促销守护 ==========
                    self.__card("④ 刷流促销守护(免费期防漏)", "mdi-timer-alert-outline", [
                        self.__row([
                            self.__switch("promo_check", "启用促销敞口检查", 6),
                            self.__text("promo_lead_hours", "提前预警小时数", 6, "6"),
                        ]),
                        self.__alert("背景:站点的「免费」是限时的(馒头实测有 6h / 12h / 24h 档),"
                                     "而刷流插件抓种时只看「此刻是否免费」,不看「还剩多久」。"
                                     "两个刷流任务共用一个下载器时,任务级并发之和常超过下载器实际"
                                     "放行数 → 种子排队数小时,等它真开跑时免费期可能已结束,"
                                     "那部分下载量会被站点计费。本模块只读刷流插件逐种子记录的"
                                     "促销截止时间,每天巡检时报出「已过期却未下完」与「即将过期却"
                                     "未下完」的种子;发现前者会单独发一条告警。只读,不会改动任何种子。"
                                     "根治手段是在刷流任务里打开「促销过期即删未下完的种子」选项。",
                                     "info", 12, show="promo_check"),
                    ]),
                ],
            },
            {
                # ---- 默认配置 ----
                "enabled": False,
                "notify": True,
                "notify_daily": True,
                "notify_issue": True,
                "notify_channel": "",
                "cron": "30 8 * * *",
                "run_once": False,
                "debug": False,
                "quiet_start": "",
                "quiet_end": "",
                "io_enabled": True,
                "io_interval": 5,
                "io_sample_seconds": 3,
                "io_devices": "",
                "load_threshold": 8,
                "load_check": False,
                "queue_threshold": 50,
                "iowait_threshold": 0,
                "latency_threshold": 1500,
                "up_rate_min": 1.0,
                "io_check_qbt": True,
                "io_keep": 288,
                "io_notify_cooldown": 30,

                "promo_check": True,
                "promo_lead_hours": 6,

                "auto_downgrade": False,
                "downgrade_step": 1,
                "downgrade_min": 2,
                "downgrade_cooldown": 30,
                "auto_recover": False,
                "recover_step": 1,
                "recover_wait": 30,

                "qb_downloader": "",
            },
        ]

    # ---------------------------------------------------------------------
    # 插件页面(只读展示 + 手动按钮)
    # 注意:文本一律走 props.text,不能用 model-value/content 字符串
    # ---------------------------------------------------------------------
    def get_page(self) -> Optional[List[dict]]:
        last = self.get_data("last_result") or {}
        io = self.get_data("last_io") or last.get("io") or {}
        history = self.get_data("io_history") or []
        if io.get("summary"):
            io_text = "[%s] %s\n%s" % (io.get("time"), io.get("level"), io.get("summary"))
        else:
            io_text = "尚未采集,点上方「IO 检查」"

        hist_lines = []
        if io.get("trend"):
            hist_lines.append("【趋势】%s" % io.get("trend"))
            hist_lines.append("")
        for h in history[-self._io_keep:]:
            bl = h.get("backlog_gb")
            hist_lines.append("%s  上传 %-6s 下载 %-7s 负载 %-5s 队列 %-4s 积压 %-8s %s" % (
                str(h.get("time", ""))[5:16], h.get("up_mbps", "-"), h.get("dl_mbps", "-"),
                h.get("load1", "-"), h.get("queue", "-"),
                ("%.0fG" % bl) if isinstance(bl, (int, float)) else "-", h.get("level", "")))
        hist_text = "\n".join(hist_lines) if hist_lines else "暂无历史采样"

        promo = self.get_data("last_promo") or last.get("promo") or {}
        if promo.get("summary"):
            promo_text = "[%s] %s\n%s" % (
                promo.get("time"), promo.get("level"), promo.get("summary"))
        else:
            promo_text = "尚未采集,点上方「促销敞口」"

        state = "✅ 已启用" if self._enabled else "⛔ 已禁用"
        return [
            {
                "component": "VForm",
                "content": [
                    self.__alert("当前状态:%s | 上次巡检:%s" % (
                        state, last.get("time") or "从未运行"),
                        "success" if self._enabled else "warning", 12),
                    self.__card("快捷操作", "mdi-gesture-tap-button", [
                        self.__row([
                            self.__btn("启用插件", "mdi-power-plug", "/enable", 3),
                            self.__btn("禁用插件", "mdi-power-plug-off", "/disable", 3),
                            self.__btn("立即巡检", "mdi-radar", "/run", 3),
                            self.__btn("测试通知", "mdi-bell-ring", "/test_notify", 3),
                        ]),
                        self.__row([
                            self.__btn("IO 检查", "mdi-speedometer", "/io", 6),
                            self.__btn("促销敞口", "mdi-timer-alert-outline", "/promo", 6),
                        ]),
                        self.__alert("「立即巡检」= IO + 促销敞口一次跑完;"
                                     "「启用/禁用插件」走 mp 的插件配置用例(保存 + 重新初始化 + 刷新调度),"
                                     "与在插件列表里开关等效;「测试通知」会忽略免打扰时段。"
                                     "结果约 10~20 秒后刷新本页可见。", "info", 12),
                    ]),
                    self.__card("IO 健康", "mdi-speedometer", [self.__pane(io_text)]),
                    self.__card("刷流促销敞口(免费期防漏)", "mdi-timer-alert-outline",
                                [self.__pane(promo_text)]),
                    self.__card("IO 历史采样(最近 %d 次)" % self._io_keep, "mdi-chart-line",
                                [self.__pane(hist_text)]),
                ],
            }
        ]

    def stop_service(self):
        pass

    # =====================================================================
    # API 端点
    # =====================================================================
    @staticmethod
    def __bg(func, **kwargs):
        """后台执行:长任务不阻塞 HTTP 响应,避免页面按钮转圈超时。"""
        threading.Thread(target=func, kwargs=kwargs, daemon=True).start()

    def api_run(self):
        self.__bg(self.run_daily, manual=True)
        return {"success": True,
                "message": "已开始巡检(IO + 促销敞口),约 10~20 秒后刷新本页查看结果"}

    def api_io(self):
        self.__bg(self.run_io, manual=True)
        return {"success": True, "message": "已开始 IO 巡检,约 10 秒后刷新本页查看结果"}

    def api_promo(self):
        self.__bg(self.run_promo, manual=True)
        return {"success": True, "message": "已开始检查刷流促销敞口,约 5 秒后刷新本页查看结果"}

    def api_enable(self):
        return self.__set_enabled(True)

    def api_disable(self):
        return self.__set_enabled(False)

    def api_test_notify(self):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.__notify_send("NAS 哨兵·测试通知",
                           "这是一条测试消息,收到即表示通知链路正常。\n发送时间:%s" % now,
                           force=True)
        return {"success": True, "message": "测试通知已发送(已忽略免打扰时段)"}

    def __set_enabled(self, on: bool) -> Dict[str, Any]:
        """真正启用/禁用插件。

        复用 mp 的插件配置用例(``PluginConfigCommand.update``):保存配置 →
        重新初始化实例 → 刷新服务/命令/动态路由注册,与在插件列表里开关等效。
        自己直接写 DB 只会留下「界面说启用了、调度却没注册」的假状态。
        """
        pid = self.__class__.__name__
        try:
            from app.api.dependencies.plugin import get_plugin_config_command
            cfg = dict(self.get_config() or {})
            cfg["enabled"] = bool(on)
            res = get_plugin_config_command().update(pid, cfg)
            if bool(getattr(res, "success", False)):
                logger.info(f"【NAS哨兵】已{'启用' if on else '禁用'}插件")
                return {"success": True,
                        "message": "已启用插件(服务已注册)" if on else "已禁用插件(服务已注销)"}
            return {"success": False,
                    "message": "操作失败:%s" % (getattr(res, "message", "") or "未知原因")}
        except Exception as e:
            logger.error(f"【NAS哨兵】{'启用' if on else '禁用'}插件失败:{e}")
            return {"success": False, "message": f"操作失败:{e}"}

    # =====================================================================
    # 巡检主体
    # =====================================================================
    def run_daily(self, manual: bool = False) -> str:
        logger.info("【NAS哨兵】开始每日巡检")
        io = {}
        try:
            io = self.__sample_io(notify_issue=self._notify_issue and not manual)
        except Exception as e:
            logger.error(f"【NAS哨兵】IO 模块异常:{e}")
            io = {"summary": f"IO 模块异常:{e}", "level": "🔴 异常", "breached": False}
        promo = {}
        if self._promo_check:
            try:
                promo = self.__promo_exposure()
            except Exception as e:
                logger.error(f"【NAS哨兵】促销模块异常:{e}")
                promo = {"summary": f"促销模块异常:{e}", "level": "🔴 异常", "active": 0}

        result = {"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                  "io": io, "promo": promo}
        self.save_data("last_result", result)

        # 促销敞口:只在「已过期却仍在下载」时即时告警
        if promo.get("active") and self._notify_issue and not manual:
            self.__notify_send("NAS 哨兵·刷流促销敞口", promo.get("summary", ""))

        # 每日简报:仅在开启且非手动时发送
        if self._notify and self._notify_daily and not manual:
            self.__notify_send("NAS 哨兵·每日简报", self.__build_brief(result))
        if manual:
            return "巡检完成(IO:%s / 促销:%s)" % (
                io.get("level", "?"), promo.get("level", "未启用"))
        return "巡检完成"

    def run_io(self, manual: bool = False) -> str:
        try:
            io = self.__sample_io(notify_issue=self._notify_issue and not manual)
        except Exception as e:
            logger.error(f"【NAS哨兵】IO 巡检异常:{e}")
            return f"IO 巡检异常:{e}"
        if manual:
            return io.get("summary", "IO 巡检完成")
        return "IO 巡检完成"

    def run_promo(self, manual: bool = False) -> str:
        """检查刷流种子的免费期敞口(只读,不改任何种子)。"""
        if not self._promo_check:
            return "促销守护未启用"
        try:
            r = self.__promo_exposure()
        except Exception as e:
            logger.error(f"【NAS哨兵】促销敞口检查异常:{e}")
            return f"促销敞口检查异常:{e}"
        # 有「已过期却仍在下载」的才即时告警(每日简报里也会带一份)
        if r.get("active") and self._notify_issue and not manual:
            self.__notify_send("NAS 哨兵·刷流促销敞口", r.get("summary", ""))
        return r.get("summary", "促销敞口检查完成")

    # =====================================================================
    # 模块 1:IO / 刷流健康哨兵
    # =====================================================================
    def __sample_io(self, notify_issue: bool = False) -> Dict[str, Any]:
        load1, load5, load15, iowait = self.__load()
        devs = self.__disk_rates(float(self._io_sample_seconds))
        if self._io_check_qbt:
            up_mbps, dl_mbps, qbt_state, qbt_stats = self.__qbt_rate()
        else:
            up_mbps, dl_mbps, qbt_state, qbt_stats = None, None, "", {}

        breached, lines = [], []
        lines.append("负载 %.2f / %.2f / %.2f(1/5/15 分),IO 等待 %.1f%%" % (
            load1, load5, load15, iowait * 100))
        # 负载/IO 等待默认只记录不告警(见 init_plugin 说明):想启用就把开关打开
        if self._load_check and load1 > self._load_threshold:
            breached.append("负载 %.2f > 红线 %.2f" % (load1, self._load_threshold))
        if self._iowait_threshold > 0 and iowait * 100 > self._iowait_threshold:
            breached.append("IO 等待 %.1f%% > 红线 %.1f%%" % (iowait * 100, self._iowait_threshold))

        if devs:
            worst = max(devs.values(), key=lambda d: d.get("queue", 0))
            for dev, d in sorted(devs.items(), key=lambda kv: -kv[1].get("queue", 0))[:4]:
                lines.append("  %s:读 %.2f MB/s 写 %.2f MB/s 队列 %d 写延迟 %.0fms" % (
                    dev, d["read_mbps"], d["write_mbps"], d["queue"], d.get("write_latency", 0)))
            if worst.get("queue", 0) > self._queue_threshold:
                breached.append("设备 %s 队列 %d > 红线 %.0f" % (
                    worst["dev"], worst["queue"], self._queue_threshold))
            if self._latency_threshold > 0:
                slow = max(devs.values(), key=lambda d: d.get("write_latency", 0))
                if slow.get("write_latency", 0) > self._latency_threshold:
                    lines.append("  ⚠ %s 写延迟 %.0fms 超参考红线 %.0fms(flush 突发时属常见,仅供参考)" % (
                        slow["dev"], slow["write_latency"], self._latency_threshold))

        if up_mbps is not None:
            lines.append("  刷流下载器:上传 %.2f MB/s 下载 %.2f MB/s" % (up_mbps, dl_mbps))
            if up_mbps < self._up_rate_min:
                breached.append("上传 %.2f MB/s < 下限 %.2f MB/s" % (up_mbps, self._up_rate_min))
        if qbt_stats:
            lines.append("  未完成积压 %.1f GB(下载中 %d / 排队 %d / 做种 %d)" % (
                qbt_stats.get("backlog_gb", 0), qbt_stats.get("dl_count", 0),
                qbt_stats.get("queued", 0), qbt_stats.get("seeding", 0)))
        if qbt_state:
            lines.append("  种子状态:%s" % qbt_state)

        level = "🔴 超红线" if breached else "🟢 正常"
        summary = "%s\n%s" % ("; ".join(breached) if breached else "全部指标正常", "\n".join(lines))

        # 落盘历史采样:下载速率 / IO 等待 / 积压都要留,才能判断「换参数后有没有变好」
        hist = self.get_data("io_history") or []
        hist.append({"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "level": level,
                     "load1": load1, "up_mbps": up_mbps, "dl_mbps": dl_mbps,
                     "queue": max([d.get("queue", 0) for d in devs.values()] or [0]),
                     "iowait": round(iowait * 100, 1),
                     "backlog_gb": (qbt_stats or {}).get("backlog_gb")})
        hist = hist[-max(self._io_keep, 1):]
        self.save_data("io_history", hist)

        result = {"time": hist[-1]["time"], "level": level,
                  "breached": bool(breached), "summary": summary,
                  "load1": load1, "up_mbps": up_mbps, "dl_mbps": dl_mbps,
                  "iowait": round(iowait * 100, 1),
                  "queue": hist[-1]["queue"],
                  "backlog_gb": (qbt_stats or {}).get("backlog_gb"),
                  "trend": self.__io_trend(hist)}
        # 落盘最近一次 IO 结果(供页面展示;与是否通知无关)
        self.save_data("last_io", result)

        # 超红线一律记日志(与通知开关解耦,保证可观测)
        if breached:
            logger.warn(f"【NAS哨兵】IO 超红线:{breached}")
        else:
            logger.debug(f"【NAS哨兵】IO 正常:负载 {load1:.2f},上传 {up_mbps}")

        # 异常即报(带独立冷却,避免刷屏)
        if breached and notify_issue and self._notify:
            last = self.get_data("last_issue_ts") or 0
            if time.time() - float(last) > self._io_notify_cooldown * 60:
                self.save_data("last_issue_ts", time.time())
                self.__notify_send("NAS 哨兵·异常告警", summary)
        # 自动降级 / 恢复(默认关闭)
        if self._enabled:
            try:
                if breached and self._auto_downgrade:
                    self.__auto_downgrade(breached)
                elif not breached:
                    self.save_data("last_ok_ts", time.time())
                    if self._auto_recover:
                        self.__auto_recover()
            except Exception as e:
                logger.error(f"【NAS哨兵】自动降级/恢复失败:{e}")
        return result

    def __load(self) -> Tuple[float, float, float, float]:
        with open("/proc/loadavg") as f:
            parts = f.read().split()
        load1, load5, load15 = float(parts[0]), float(parts[1]), float(parts[2])
        iowait = 0.0
        try:
            def snap():
                with open("/proc/stat") as fh:
                    line = fh.readline().split()[1:]
                v = [int(x) for x in line]
                return v, sum(v)
            a, ta = snap()
            time.sleep(0.5)
            b, tb = snap()
            dt = tb - ta
            if dt > 0 and len(a) > 4 and len(b) > 4:
                iowait = (b[4] - a[4]) / dt
        except Exception:
            pass
        return load1, load5, load15, iowait

    @staticmethod
    def __disk_snapshot() -> Dict[str, Dict[str, int]]:
        out = {}
        with open("/proc/diskstats") as f:
            for ln in f:
                p = ln.split()
                if len(p) > 13:
                    out[p[2]] = {"rc": int(p[3]), "sr": int(p[5]), "msw": int(p[10]),
                                 "wc": int(p[7]), "sw": int(p[9]), "q": int(p[11])}
        return out

    def __disk_rates(self, seconds: float = 3.0) -> Dict[str, Dict[str, float]]:
        def wanted(name: str) -> bool:
            if self._io_devices:
                return name in [x.strip() for x in self._io_devices.split(",") if x.strip()]
            return bool(re.match(r"^(sd[a-z]+|sata\d+|nvme\d+n\d+|hd[a-z]+)$", name))

        a = self.__disk_snapshot()
        time.sleep(seconds)
        b = self.__disk_snapshot()
        out: Dict[str, Dict[str, float]] = {}
        for name, x in b.items():
            if name not in a or not wanted(name):
                continue
            y = a[name]
            drc, dwc = x["rc"] - y["rc"], x["wc"] - y["wc"]
            dmsw = x["msw"] - y["msw"]
            out[name] = {
                "dev": name,
                "read_mbps": (x["sr"] - y["sr"]) * 512 / seconds / 1048576,
                "write_mbps": (x["sw"] - y["sw"]) * 512 / seconds / 1048576,
                "queue": x["q"],
                "read_iops": drc / seconds,
                "write_iops": dwc / seconds,
                "write_latency": (dmsw / dwc) if dwc > 0 else 0.0,
            }
        return out

    # =====================================================================
    # 刷流下载器(qbt)查询 / 自动降级 / 自动恢复
    # =====================================================================
    def __qb_cfg(self) -> Optional[Dict[str, str]]:
        """从 mp 的下载器配置里取一个 qbittorrent 下载器(不落明文到本插件)。"""
        try:
            import sqlite3
            import os
            cfg_path = "/config/user.db"
            if not os.path.exists(cfg_path):
                return None
            conn = sqlite3.connect(cfg_path)
            row = conn.execute("SELECT value FROM systemconfig WHERE key='Downloaders'").fetchone()
            conn.close()
            if not row or not row[0]:
                return None
            import json as _json
            items = _json.loads(row[0])
            for it in items:
                if (it.get("type") or "").lower() != "qbittorrent":
                    continue
                if self._qb_downloader and it.get("name") != self._qb_downloader:
                    continue
                c = it.get("config") or {}
                if c.get("host") and c.get("username"):
                    return {"name": it.get("name", ""), "host": c["host"].rstrip("/"),
                            "username": c.get("username", ""), "password": c.get("password", "")}
            return None
        except Exception as e:
            logger.debug(f"【NAS哨兵】读取下载器配置失败:{e}")
            return None

    def __qb_session(self):
        cfg = self.__qb_cfg()
        if not cfg:
            return None, None
        s = requests.Session()
        try:
            s.post(cfg["host"] + "/api/v2/auth/login",
                   data={"username": cfg["username"], "password": cfg["password"]}, timeout=30)
            return s, cfg
        except Exception as e:
            logger.warn(f"【NAS哨兵】登录刷流下载器失败:{e}")
            return None, cfg

    def __qbt_rate(self):
        """返回 (上传 MB/s, 下载 MB/s, 状态分布字符串, 统计 dict)。

        统计 dict 含 backlog_gb(未完成种子的剩余字节合计,衡量积压)、
        dl_count / queued(并发与排队)、seeding(做种数)——用于「调参 → 比效果」。
        """
        try:
            s, cfg = self.__qb_session()
            if not s:
                return None, None, "", {}
            host = cfg["host"]
            ti = s.get(host + "/api/v2/transfer/info", timeout=30).json()
            up = ti.get("up_info_speed", 0) / 1048576
            dl = ti.get("dl_info_speed", 0) / 1048576
            t = s.get(host + "/api/v2/torrents/info", timeout=60).json()
            from collections import Counter
            st = dict(Counter(x.get("state") for x in t))
            backlog = 0
            for x in t:
                if (x.get("progress") or 0) < 1 and x.get("state") in (
                        "downloading", "forcedDL", "stalledDL", "metaDL", "queuedDL"):
                    backlog += (x.get("amount_left") or 0)
            stats = {"backlog_gb": round(backlog / 1073741824, 1),
                     "dl_count": st.get("downloading", 0) + st.get("forcedDL", 0),
                     "queued": st.get("queuedDL", 0),
                     "seeding": st.get("uploading", 0) + st.get("stalledUP", 0)}
            return up, dl, str(st), stats
        except Exception as e:
            logger.warn(f"【NAS哨兵】查询刷流下载器失败:{e}")
            return None, None, "", {}

    def __io_trend(self, hist: List[dict]) -> str:
        """把留存窗口内的采样压成一行趋势。

        目的是回答「哪个参数组合最有利于拿上传量」:上传均值/最大、下载均值/最大、
        队列峰值、积压从多少降到多少 —— 换参数后用这行对比即可。
        """
        ups = [h.get("up_mbps") for h in hist if isinstance(h.get("up_mbps"), (int, float))]
        dls = [h.get("dl_mbps") for h in hist if isinstance(h.get("dl_mbps"), (int, float))]
        qs = [h.get("queue") for h in hist if isinstance(h.get("queue"), (int, float))]
        bl = [h.get("backlog_gb") for h in hist if isinstance(h.get("backlog_gb"), (int, float))]
        if not ups:
            return "样本不足"
        out = "近 %d 次(约 %.1fh):上传 均值 %.2f / 最大 %.2f MB/s" % (
            len(hist), len(hist) * self._io_interval / 60.0, sum(ups) / len(ups), max(ups))
        if dls:
            out += ";下载 均值 %.1f / 最大 %.1f MB/s" % (sum(dls) / len(dls), max(dls))
        if qs:
            out += ";队列峰值 %d" % max(qs)
        if bl:
            out += ";积压 %.0f → %.0f GB" % (bl[0], bl[-1])
        return out

    def __qb_set_concurrency(self, new: int) -> bool:
        """把刷流下载器的 max_active_downloads 设为 new。"""
        s, cfg = self.__qb_session()
        if not s:
            return False
        try:
            import json as _json
            s.post(cfg["host"] + "/api/v2/app/setPreferences",
                   data={"json": _json.dumps({"max_active_downloads": int(new)})}, timeout=30)
            return True
        except Exception as e:
            logger.error(f"【NAS哨兵】设置下载并发失败:{e}")
            return False

    def __qb_concurrency(self) -> Optional[int]:
        s, cfg = self.__qb_session()
        if not s:
            return None
        try:
            p = s.get(cfg["host"] + "/api/v2/app/preferences", timeout=30).json()
            return int(p.get("max_active_downloads") or 0)
        except Exception:
            return None

    # =====================================================================
    # 刷流促销守护:找出「免费期已过 / 即将过期,却还没下完」的刷流种子
    #
    # 背景(2026-10-10 实测):馒头等站点的「免费」是限时的,实测有 6h / 12h / 24h
    # 三档;而 BrushFlow 抓种时只看「此刻是否免费」,不看「还剩多久」。两个刷流任务
    # 共用一个下载器时,任务级并发之和会超过下载器实际放行数 -> 种子排队几小时,
    # 等它真正开跑时免费期可能已经结束,那部分下载量就会被站点计费。
    #
    # 数据来源:BrushFlow 把每个种子的 freedate(站点促销截止)记在 mp 自己的
    # /config/user.db 的 plugindata 表(key 形如 task.<任务id>.torrents)。本模块
    # 只读它,不依赖 BrushFlow 的私有方法;读不到就降级为「无数据」,不影响其它模块。
    # =====================================================================
    @staticmethod
    def __parse_site_dt(v) -> Optional[datetime]:
        """解析站点返回的时间字符串(形如 2026-10-10 11:07:59)。"""
        try:
            return datetime.strptime(str(v).strip().replace("T", " ")[:19], "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None

    def __brushflow_records(self) -> List[Tuple[str, dict]]:
        """读取 BrushFlow 逐种子记录(含 freedate / size / downloaded / deleted)。"""
        out: List[Tuple[str, dict]] = []
        try:
            import json as _json
            import sqlite3
            conn = sqlite3.connect("/config/user.db")
            try:
                rows = conn.execute(
                    "SELECT value FROM plugindata "
                    "WHERE plugin_id='BrushFlow' AND key LIKE 'task.%.torrents'").fetchall()
            finally:
                conn.close()
            for row in rows:
                try:
                    data = _json.loads(row[0] or "{}")
                except Exception:
                    continue
                if not isinstance(data, dict):
                    continue
                for h, v in data.items():
                    if isinstance(v, dict):
                        out.append((h, v))
        except Exception as e:
            logger.warn(f"【NAS哨兵】读取刷流促销数据失败(将跳过本模块):{e}")
        return out

    def __promo_exposure(self) -> Dict[str, Any]:
        """统计刷流种子的促销敞口:已过期未下完 / 临近过期未下完。"""
        now = datetime.now()
        expired: List[dict] = []
        soon: List[dict] = []
        no_date = 0
        for h, v in self.__brushflow_records():
            if v.get("deleted"):
                continue
            try:
                size = float(v.get("size") or 0)
                done = float(v.get("downloaded") or 0)
            except (TypeError, ValueError):
                continue
            # 已下完的只做种,不再产生下载量 -> 不是敞口
            if size <= 0 or done >= size:
                continue
            exp = self.__parse_site_dt(v.get("freedate"))
            if not exp:
                no_date += 1
                continue
            left = (exp - now).total_seconds() / 3600.0
            item = {"hash": h, "title": str(v.get("title") or "")[:58],
                    "size_gb": round(size / 1073741824, 1),
                    "done_gb": round(done / 1073741824, 1),
                    "expire": exp.strftime("%m-%d %H:%M"), "left_h": round(left, 1)}
            if left <= 0:
                expired.append(item)
            elif left <= self._promo_lead_hours:
                soon.append(item)

        # 与下载器对账:区分「还在下载组(真在计费)」与「已停止 / 已不在下载器」
        states: Dict[str, dict] = {}
        if expired or soon:
            s, cfg = self.__qb_session()
            if s:
                try:
                    for x in s.get(cfg["host"] + "/api/v2/torrents/info", timeout=60).json():
                        states[x.get("hash")] = x
                except Exception as e:
                    logger.debug(f"【NAS哨兵】促销敞口对账下载器失败:{e}")
        LIVE = ("downloading", "forcedDL", "stalledDL", "metaDL", "queuedDL", "checkingDL")
        for it in expired + soon:
            t = states.get(it["hash"])
            it["state"] = (t or {}).get("state") or "已不在下载器"
            it["active"] = it["state"] in LIVE

        expired.sort(key=lambda x: -x["size_gb"])
        soon.sort(key=lambda x: x["left_h"])
        danger = [x for x in expired if x["active"]]

        lines: List[str] = []
        if expired:
            lines.append("⚠ 免费期已过但未下完:%d 个(其中仍在下载组 %d 个 <- 这部分正在被计下载量)"
                         % (len(expired), len(danger)))
            for x in expired[:6]:
                lines.append("   [过期 %s] %s %.1fG(已下 %.1fG)%s" % (
                    x["expire"], x["title"], x["size_gb"], x["done_gb"],
                    " ← 仍在下载" if x["active"] else " (已停止/已不在下载器)"))
        if soon:
            lines.append("⏳ %.0f 小时内到期但未下完:%d 个" % (self._promo_lead_hours, len(soon)))
            for x in soon[:6]:
                lines.append("   [剩 %.1fh] %s %.1fG(已下 %.1fG)%s" % (
                    x["left_h"], x["title"], x["size_gb"], x["done_gb"],
                    " ← 在下载组(可能来不及)" if x["active"] else ""))
        if not expired and not soon:
            lines.append("✅ 没有「已过期/临近过期却未下完」的刷流种子")
        if no_date:
            lines.append("(另有 %d 个未下完种子没有 freedate 记录,无法判断,已跳过)" % no_date)

        level = ("🔴 有敞口" if danger else
                 ("🟠 已过期(未在跑)" if expired else ("🟡 临近到期" if soon else "🟢 正常")))
        result = {"time": now.strftime("%Y-%m-%d %H:%M:%S"), "level": level,
                  "expired": len(expired), "active": len(danger), "soon": len(soon),
                  "no_date": no_date, "summary": "\n".join(lines)}
        self.save_data("last_promo", result)
        if danger:
            logger.warn(f"【NAS哨兵】刷流促销敞口:{len(danger)} 个免费期已过却仍在下载")
        else:
            logger.debug(f"【NAS哨兵】促销敞口:{level},过期 {len(expired)} / 临近 {len(soon)}")
        return result

    def __auto_downgrade(self, breached: List[str]):
        """超红线时把下载并发降一档(带冷却)。默认关闭,需用户在页面上显式开启。"""
        last = float(self.get_data("last_downgrade_ts") or 0)
        if time.time() - last < self._downgrade_cooldown * 60:
            return
        cur = self.__qb_concurrency()
        if cur is None:
            return
        if cur <= self._downgrade_min:
            logger.info("【NAS哨兵】下载并发已到下限 %d,不再降级" % cur)
            return
        new = max(self._downgrade_min, cur - self._downgrade_step)
        if not self.__qb_set_concurrency(new):
            return
        # 首次降级时记录原始并发,作为「自动恢复」的上限
        if not self.get_data("downgrade_baseline"):
            self.save_data("downgrade_baseline", cur)
        self.save_data("last_downgrade_ts", time.time())
        msg = "超红线(%s),已将下载并发 %d → %d" % ("; ".join(breached), cur, new)
        logger.warn(f"【NAS哨兵】{msg}")
        if self._notify:
            self.__notify_send("NAS 哨兵·已自动降级", msg)

    def __auto_recover(self):
        """持续正常一段时间后,把并发逐步升回降级前的基线。"""
        base = self.get_data("downgrade_baseline")
        if not base:
            return
        ok_since = float(self.get_data("last_ok_ts") or 0)
        if not ok_since or time.time() - ok_since < self._recover_wait * 60:
            return
        cur = self.__qb_concurrency()
        if cur is None or cur >= int(base):
            return
        last = float(self.get_data("last_recover_ts") or 0)
        if time.time() - last < self._recover_wait * 60:
            return
        new = min(int(base), cur + self._recover_step)
        if not self.__qb_set_concurrency(new):
            return
        self.save_data("last_recover_ts", time.time())
        msg = "连续正常超过 %d 分钟,已将下载并发 %d → %d(基线 %d)" % (
            self._recover_wait, cur, new, int(base))
        logger.info(f"【NAS哨兵】{msg}")
        if self._notify:
            self.__notify_send("NAS 哨兵·已自动恢复", msg)

    # =====================================================================
    # 通知 / 工具
    # =====================================================================
    def __notify_send(self, title: str, text: str, force: bool = False):
        if not self._notify:
            return
        if not force and self.__in_quiet():
            logger.info(f"【NAS哨兵】处于免打扰时段,跳过推送:{title}")
            return
        ch = None
        if self._notify_channel and NotificationChannel is not None:
            ch = getattr(NotificationChannel, self._notify_channel, None)
        try:
            self.post_message(mtype=_MSG_TYPE, title=title, text=text, channel=ch)
        except Exception as e:
            logger.warn(f"【NAS哨兵】指定渠道推送失败({e}),改为全渠道重试")
            try:
                self.post_message(mtype=_MSG_TYPE, title=title, text=text)
            except Exception as e2:
                logger.warn(f"【NAS哨兵】通知发送失败:{e2}")

    def __in_quiet(self) -> bool:
        """免打扰时段判断,支持跨零点(如 23:30 ~ 07:00)。"""
        if not (self._quiet_start and self._quiet_end):
            return False
        try:
            def mins(s: str) -> int:
                h, m = s.split(":")[:2]
                return int(h) * 60 + int(m)
            start, end = mins(self._quiet_start), mins(self._quiet_end)
            now = datetime.now().hour * 60 + datetime.now().minute
            if start == end:
                return False
            if start < end:
                return start <= now < end
            return now >= start or now < end
        except Exception:
            return False

    def __build_brief(self, result: Dict[str, Any]) -> str:
        lines = ["巡检时间:%s" % result.get("time", "")]
        io = result.get("io") or {}
        if io:
            lines.append("— IO —")
            lines.append(io.get("summary", ""))
        promo = result.get("promo") or {}
        if promo:
            lines.append("— 刷流促销 —")
            lines.append(promo.get("summary", ""))
        return "\n".join(lines)

    # ---- 解析工具 ---------------------------------------------------------
    @staticmethod
    def __cron_ok(expr: str) -> bool:
        return bool(expr) and str(expr).count(" ") == 4

    @staticmethod
    def __as_int(v, d: int, lo: int, hi: int) -> int:
        try:
            return max(lo, min(hi, int(float(v))))
        except Exception:
            return d

    @staticmethod
    def __as_float(v, d: float) -> float:
        try:
            return float(v)
        except Exception:
            return d

    # ---- 表单小组件(减少重复)-------------------------------------------
    @staticmethod
    def __row(items: List[dict], show: str = "") -> dict:
        """一行配置。``show`` 传一个配置键名:该键为假则整行隐藏。

        MP 的表单接口会把默认配置合并进 model(注释原文:so all keys exist for
        v-show evaluation),因此表达式的键一定存在,不会因未定义而抛错。
        """
        node: Dict[str, Any] = {"component": "VRow", "content": items}
        if show:
            node["props"] = {"show": "{{ %s }}" % show}
        return node

    @staticmethod
    def __col(item: dict, md: int = 12) -> dict:
        return {"component": "VCol", "props": {"cols": 12, "md": md}, "content": [item]}

    @staticmethod
    def __card(title: str, icon: str, rows: List[dict]) -> dict:
        """分节卡片:标题带图标 + 内容区。文本一律走 text/node 或 props.text。"""
        return {
            "component": "VCard",
            "props": {"variant": "outlined", "class": "mb-4"},
            "content": [
                {"component": "VCardTitle",
                 "props": {"class": "d-flex align-center text-subtitle-1"},
                 "content": [
                     {"component": "VIcon",
                      "props": {"icon": icon, "class": "mr-2", "color": "primary"}},
                     {"component": "div", "text": title},
                 ]},
                {"component": "VCardText", "content": rows},
            ],
        }

    @staticmethod
    def __section(title: str) -> dict:
        """分节标题。注意:VSubheader 在 Vuetify 3 已被移除,这里用 div + text。"""
        return {"component": "div",
                "props": {"class": "text-subtitle-1 font-weight-bold mt-4 mb-2"},
                "text": title}

    @staticmethod
    def __pane(text: str) -> dict:
        """只读文本块。文本必须走 props.text;用 text-pre-wrap 保留换行。"""
        return {"component": "div",
                "props": {"class": "text-body-2 text-pre-wrap pa-3 mb-2",
                          "style": "border:1px solid rgba(128,128,128,.3);border-radius:6px;"},
                "text": text or "-"}

    def __switch(self, model: str, label: str, md: int = 3) -> dict:
        return self.__col({"component": "VSwitch", "props": {"model": model, "label": label}}, md)

    def __text(self, model: str, label: str, md: int = 6, hint: str = "") -> dict:
        return self.__col({"component": "VTextField",
                           "props": {"model": model, "label": label, "placeholder": hint}}, md)

    def __select(self, model: str, label: str, md: int, options: List[dict],
                 multiple: bool = True) -> dict:
        props: Dict[str, Any] = {"model": model, "label": label, "items": options,
                                 "clearable": True}
        if multiple:
            props.update({"multiple": True, "chips": True})
        return self.__col({"component": "VSelect", "props": props}, md)

    def __cron(self, model: str, label: str, md: int = 6, hint: str = "") -> dict:
        """VCronField 是 MP 前端注册的自定义组件(5 段 cron 选择器)。"""
        return self.__col({"component": "VCronField",
                           "props": {"model": model, "label": label, "placeholder": hint}}, md)

    def __textarea(self, model: str, label: str, md: int, rows: int, hint: str = "") -> dict:
        return self.__col({"component": "VTextarea",
                           "props": {"model": model, "label": label, "rows": rows,
                                     "placeholder": hint}}, md)

    def __btn(self, text: str, icon: str, path: str, md: int = 4) -> dict:
        """鼠标可点的操作按钮:click 事件映射到本插件 API。"""
        return self.__col({
            "component": "VBtn",
            "props": {"class": "ma-1", "variant": "tonal", "prepend-icon": icon, "block": True},
            "text": text,
            "events": {"click": {"api": "plugin/%s%s" % (self.__class__.__name__, path),
                                 "method": "post"}},
        }, md)

    def __alert(self, text: str, type_: str, md: int, show: str = "") -> dict:
        """VAlert 的文本必须写在 props.text(放顶层 content 会渲染成空)。"""
        props: Dict[str, Any] = {"type": type_, "variant": "tonal", "text": text}
        if show:
            props["show"] = "{{ %s }}" % show
        return self.__col({"component": "VAlert", "props": props}, md)
