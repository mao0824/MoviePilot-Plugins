"""
NAS 哨兵 (nas-sentinel) — MoviePilot 插件

通用哨兵:把「站点签到、考核进度、刷流/磁盘 IO 健康」三件需要人盯的事,
变成自动巡检 + 到点告警。

设计原则(为了将来能发布给其他人用):
  * 不写死任何本机路径/设备名/下载器名,全部可配置
  * 站点相关操作用「通用 NexusPHP 格式」解析,不针对单一站点硬编码
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

import html
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

try:
    from app.db.site_oper import SiteOper
except Exception:  # pragma: no cover
    SiteOper = None


DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")

# NexusPHP 考核公告的标准格式:
#   名称：新手考核 时间：2026-10-09 11:37:10 ~ 2026-11-08 11:37:10
#   指标1：上传增量, 要求：30 GB, 当前：614.59 MB, 结果： 未通过！
RE_EXAM_TIME = re.compile(r"时间：\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*~\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
RE_EXAM_ITEM = re.compile(
    r"指标\s*(\d+)\s*：\s*([^,，]{1,24})\s*[,，]\s*要求\s*：\s*([^,，]{1,24})\s*[,，]\s*"
    r"当前\s*：\s*([^,，]{1,24})\s*[,，]\s*结果\s*：\s*([^！!]{1,12})[！!]?"
)
RE_EXAM_NAME = re.compile(r"名称\s*：\s*([^时]{1,40}?)\s*时间\s*：")
RE_SIGNED = re.compile(
    r"(已经签到|今日已签到|已签到|签到成功|已连续签到|签到已得|本次签到获得|补签卡)")
RE_UNIT_NUM = re.compile(r"([\d.]+)\s*([KMGTP]?B)?", re.I)

UNIT_FACTOR = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3, "TB": 1024 ** 4}


class NasSentinel(_PluginBase):
    # ---- 插件元信息 ---------------------------------------------------------
    plugin_name = "NAS 哨兵"
    plugin_desc = "通用哨兵:站点签到补位、考核进度追踪、刷流与磁盘 IO 健康巡检,异常即报。"
    plugin_icon = "sentinel.png"
    plugin_version = "0.3.1"
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

    # ---- 签到 --------------------------------------------------------------
    _signin_enabled = True
    _signin_sites: List[int] = []
    _signin_path = "/attendance.php"
    _signin_cron = ""
    _signin_retry = 1
    _signin_notify = True
    _signin_skip_signed = True
    _signin_ua = ""
    _signin_cookie = ""
    _signin_extra_form = ""

    # ---- 考核 --------------------------------------------------------------
    _exam_enabled = True
    _exam_sites: List[int] = []
    _exam_paths: List[str] = ["/rules.php", "/"]
    _exam_keyword = "考核"
    _exam_cron = ""
    _exam_warn_days = 5
    _exam_notify_risk = True
    _exam_metrics = ""
    _exam_site_config = ""

    # ---- IO ---------------------------------------------------------------
    _io_enabled = True
    _io_interval = 5
    _io_sample_seconds = 3
    _io_devices = ""
    _load_threshold = 8.0
    _queue_threshold = 50
    _iowait_threshold = 30.0
    _latency_threshold = 1500.0
    _up_rate_min = 1.0
    _io_check_qbt = True
    _io_keep = 20
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
    _http_timeout = 25

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

        # 签到
        self._signin_enabled = cfg.get("signin_enabled", True)
        self._signin_sites = self.__as_int_list(cfg.get("signin_sites"))
        self._signin_path = (cfg.get("signin_path") or "/attendance.php").strip()
        self._signin_cron = (cfg.get("signin_cron") or "").strip()
        self._signin_retry = self.__as_int(cfg.get("signin_retry"), 1, 0, 5)
        self._signin_notify = cfg.get("signin_notify", True)
        self._signin_skip_signed = cfg.get("signin_skip_signed", True)
        self._signin_ua = (cfg.get("signin_ua") or "").strip()
        self._signin_cookie = (cfg.get("signin_cookie") or "").strip()
        self._signin_extra_form = (cfg.get("signin_extra_form") or "").strip()

        # 考核
        self._exam_enabled = cfg.get("exam_enabled", True)
        self._exam_sites = self.__as_int_list(cfg.get("exam_sites"))
        self._exam_paths = self.__as_str_list(cfg.get("exam_paths")) or ["/rules.php", "/"]
        self._exam_keyword = (cfg.get("exam_keyword") or "考核").strip()
        self._exam_cron = (cfg.get("exam_cron") or "").strip()
        self._exam_warn_days = self.__as_int(cfg.get("exam_warn_days"), 5, 0, 60)
        self._exam_notify_risk = cfg.get("exam_notify_risk", True)
        self._exam_metrics = (cfg.get("exam_metrics") or "").strip()
        self._exam_site_config = (cfg.get("exam_site_config") or "").strip()

        # IO
        self._io_enabled = cfg.get("io_enabled", True)
        self._io_interval = self.__as_int(cfg.get("io_interval"), 5, 1, 1440)
        self._io_sample_seconds = self.__as_int(cfg.get("io_sample_seconds"), 3, 1, 30)
        self._io_devices = (cfg.get("io_devices") or "").strip()
        self._load_threshold = self.__as_float(cfg.get("load_threshold"), 8.0)
        self._queue_threshold = self.__as_float(cfg.get("queue_threshold"), 50)
        self._iowait_threshold = self.__as_float(cfg.get("iowait_threshold"), 30.0)
        self._latency_threshold = self.__as_float(cfg.get("latency_threshold"), 1500.0)
        self._up_rate_min = self.__as_float(cfg.get("up_rate_min"), 1.0)
        self._io_check_qbt = cfg.get("io_check_qbt", True)
        self._io_keep = self.__as_int(cfg.get("io_keep"), 20, 1, 500)
        self._io_notify_cooldown = self.__as_int(cfg.get("io_notify_cooldown"), 30, 1, 1440)

        # 降级 / 恢复
        self._auto_downgrade = bool(cfg.get("auto_downgrade"))  # 默认关闭
        self._downgrade_step = self.__as_int(cfg.get("downgrade_step"), 1, 1, 50)
        self._downgrade_min = self.__as_int(cfg.get("downgrade_min"), 2, 1, 100)
        self._downgrade_cooldown = self.__as_int(cfg.get("downgrade_cooldown"), 30, 1, 1440)
        self._auto_recover = bool(cfg.get("auto_recover"))
        self._recover_step = self.__as_int(cfg.get("recover_step"), 1, 1, 50)
        self._recover_wait = self.__as_int(cfg.get("recover_wait"), 30, 1, 1440)

        self._qb_downloader = (cfg.get("qb_downloader") or "").strip()
        self._http_timeout = self.__as_int(cfg.get("http_timeout"), 25, 5, 120)

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

        # 1) 每日巡检:签到 + 考核 + IO + 简报
        if self.__cron_ok(self._cron):
            services.append({
                "id": "NasSentinelDaily",
                "name": "NAS哨兵-每日巡检",
                "trigger": CronTrigger.from_crontab(self._cron),
                "func": self.run_daily,
                "kwargs": {},
            })
        # 2) 独立签到周期(留空则并入侵检)
        if self._signin_enabled and self.__cron_ok(self._signin_cron):
            services.append({
                "id": "NasSentinelSignin",
                "name": "NAS哨兵-站点签到",
                "trigger": CronTrigger.from_crontab(self._signin_cron),
                "func": self.run_signin,
                "kwargs": {},
            })
        # 3) 独立考核检查周期(留空则并入侵检)
        if self._exam_enabled and self.__cron_ok(self._exam_cron):
            services.append({
                "id": "NasSentinelExam",
                "name": "NAS哨兵-考核追踪",
                "trigger": CronTrigger.from_crontab(self._exam_cron),
                "func": self.run_exam,
                "kwargs": {},
            })
        # 4) IO 哨兵:按间隔采样,异常即报
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
             "auth": "bear", "summary": "立即执行一次完整巡检(签到+考核+IO)"},
            {"path": "/io", "endpoint": self.api_io, "methods": ["GET", "POST"],
             "auth": "bear", "summary": "立即执行一次 IO 巡检"},
            {"path": "/signin", "endpoint": self.api_signin, "methods": ["GET", "POST"],
             "auth": "bear", "summary": "立即执行一次站点签到"},
            {"path": "/exam", "endpoint": self.api_exam, "methods": ["GET", "POST"],
             "auth": "bear", "summary": "立即执行一次考核进度检查"},
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
        site_opts = []
        try:
            if SiteOper is not None:
                site_opts = [{"title": s.name, "value": s.id} for s in SiteOper().list_order_by_pri()]
        except Exception as e:
            logger.warn(f"【NAS哨兵】读取站点列表失败:{e}")

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
                            self.__text("quiet_start", "免打扰开始(HH:MM)", 3, "如 23:30,留空=不启用"),
                            self.__text("quiet_end", "免打扰结束(HH:MM)", 3, "如 07:00"),
                            self.__text("http_timeout", "请求超时(秒)", 3, "25"),
                            self.__switch("debug", "详细日志", 3),
                        ]),
                        self.__alert("合上这两个开关看效果:下面各分组里,只有「已启用」的模块才会"
                                     "展开其详细参数(条件显隐由 MP 的 v-show 合并默认值机制保证安全)。",
                                     "info", 12),
                    ]),

                    # ========== ② 站点签到 ==========
                    self.__card("② 站点签到(NexusPHP 通用)", "mdi-calendar-check", [
                        self.__row([
                            self.__switch("signin_enabled", "启用签到", 3),
                            self.__switch("signin_notify", "签到结果通知", 3),
                            self.__switch("signin_skip_signed", "已签到则跳过", 3),
                            self.__text("signin_retry", "失败重试次数", 3, "1"),
                        ]),
                        self.__row([
                            self.__select("signin_sites", "需要签到的站点", 8, site_opts),
                            self.__text("signin_path", "签到相对路径", 4, "/attendance.php"),
                        ], show="signin_enabled"),
                        self.__row([
                            self.__cron("signin_cron", "独立签到周期(留空=并入侵检)", 4, "0 9 * * *"),
                            self.__text("signin_ua", "自定义 UA(留空=用站点 UA)", 4, ""),
                            self.__text("signin_cookie", "自定义 Cookie(留空=用站点 Cookie)", 4, ""),
                        ], show="signin_enabled"),
                        self.__row([
                            self.__textarea("signin_extra_form", "附加表单字段", 12, 4,
                                            "每行一个 k=v,POST 时并入表单(个别站点需要固定附加参数时用)\n"
                                            "例:type=signin"),
                        ], show="signin_enabled"),
                    ]),

                    # ========== ③ 考核追踪 ==========
                    self.__card("③ 考核进度追踪(NexusPHP 通用)", "mdi-clipboard-check", [
                        self.__row([
                            self.__switch("exam_enabled", "启用考核追踪", 3),
                            self.__switch("exam_notify_risk", "有风险立即通知", 3),
                            self.__text("exam_warn_days", "剩余天数告警阈值", 3, "5"),
                            self.__text("exam_metrics", "重点关注指标(逗号分隔,留空=全部)", 3, "上传,积分"),
                        ]),
                        self.__row([
                            self.__select("exam_sites", "需要追踪考核的站点", 6, site_opts),
                            self.__text("exam_paths", "考核页面路径(逗号分隔)", 3, "/rules.php,/"),
                            self.__text("exam_keyword", "识别关键词", 3, "考核"),
                        ], show="exam_enabled"),
                        self.__row([
                            self.__cron("exam_cron", "独立考核检查周期(留空=并入侵检)", 12, "35 8 * * *"),
                        ], show="exam_enabled"),
                        self.__row([
                            self.__textarea("exam_site_config", "考核单点配置(按站覆盖)", 12, 6,
                                            "每行一条,字段用 | 分隔:# 开头为注释\n"
                                            "站点ID | 考核页面 | 上传目标 | 做种积分目标 | 分享率目标 | 备注\n"
                                            "目标也支持 关键词=目标 写法,如:上传=83.2GB;积分=1200;分享率=1.05\n"
                                            "示例:\n4 | /rules.php | 83.2GB | 0 | 0 | PTS 新手考核\n"
                                            "3 | | 300GB | | 1.2 | 填写空白字段表示用页面上的要求"),
                        ], show="exam_enabled"),
                        self.__alert("考核单点配置用来解决「同一站点无法单独配置」的问题:"
                                     "可为每个站点分别指定考核页面与各项指标目标值,"
                                     "插件会用你填的目标替代页面上的要求参与达成度与风险推算。",
                                     "info", 12, show="exam_enabled"),
                    ]),

                    # ========== ④ IO 哨兵 ==========
                    self.__card("④ 磁盘 / 刷流 IO 哨兵", "mdi-speedometer", [
                        self.__row([
                            self.__switch("io_enabled", "启用 IO 巡检", 3),
                            self.__text("io_interval", "采样间隔(分钟)", 3, "5"),
                            self.__text("io_sample_seconds", "采样窗口(秒)", 3, "3"),
                            self.__text("io_keep", "保留最近采样条数", 3, "20"),
                        ]),
                        self.__row([
                            self.__text("io_notify_cooldown", "告警冷却(分钟)", 3, "30"),
                            self.__switch("io_check_qbt", "检查刷流下载器速率", 3),
                            self.__text("qb_downloader", "刷流下载器名(留空=自动)", 3, "如:刷流"),
                            self.__text("io_devices", "监控设备(逗号分隔,留空=自动)", 3, "如:sda,sata1"),
                        ], show="io_enabled"),
                        self.__row([
                            self.__text("load_threshold", "负载红线", 3, "8"),
                            self.__text("queue_threshold", "磁盘队列红线", 3, "50"),
                            self.__text("iowait_threshold", "IO 等待红线(%)", 3, "30"),
                            self.__text("up_rate_min", "上传速率下限(MB/s)", 3, "1.0"),
                        ], show="io_enabled"),
                        self.__row([
                            self.__text("latency_threshold", "写延迟参考红线(ms,0=不检查)", 12, "1500"),
                        ], show="io_enabled"),
                        self.__alert("写延迟在写缓存 flush 突发时会飙到上千毫秒而队列仍很小,"
                                     "属于正常现象,因此默认阈值放得很宽(1500ms)或置 0 关闭;"
                                     "判据以「磁盘队列 + 负载」为主。", "warning", 12, show="io_enabled"),
                    ]),

                    # ========== ⑤ 自动降级 / 恢复 ==========
                    self.__card("⑤ 自动降级 / 自动恢复(默认关闭)", "mdi-shield-alert-outline", [
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
                "http_timeout": 25,

                "signin_enabled": True,
                "signin_sites": [],
                "signin_path": "/attendance.php",
                "signin_cron": "",
                "signin_retry": 1,
                "signin_notify": True,
                "signin_skip_signed": True,
                "signin_ua": "",
                "signin_cookie": "",
                "signin_extra_form": "",

                "exam_enabled": True,
                "exam_sites": [],
                "exam_paths": "/rules.php,/",
                "exam_keyword": "考核",
                "exam_cron": "",
                "exam_warn_days": 5,
                "exam_notify_risk": True,
                "exam_metrics": "",
                "exam_site_config": "",

                "io_enabled": True,
                "io_interval": 5,
                "io_sample_seconds": 3,
                "io_devices": "",
                "load_threshold": 8,
                "queue_threshold": 50,
                "iowait_threshold": 30,
                "latency_threshold": 1500,
                "up_rate_min": 1.0,
                "io_check_qbt": True,
                "io_keep": 20,
                "io_notify_cooldown": 30,

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
        exam = last.get("exam") or []
        signin = last.get("signin") or []
        io = self.get_data("last_io") or last.get("io") or {}
        history = self.get_data("io_history") or []

        exam_text = "\n".join(exam) if exam else "尚未采集,点上方「考核检查」"
        sign_text = "\n".join(signin) if signin else "尚未采集,点上方「立即签到」"
        if io.get("summary"):
            io_text = "[%s] %s\n%s" % (io.get("time"), io.get("level"), io.get("summary"))
        else:
            io_text = "尚未采集,点上方「IO 检查」"

        hist_lines = []
        for h in history[-self._io_keep:]:
            hist_lines.append("%s  负载 %-5s 上传 %-6s %s" % (
                h.get("time", ""), h.get("load1", "-"), h.get("up_mbps", "-"), h.get("level", "")))
        hist_text = "\n".join(hist_lines) if hist_lines else "暂无历史采样"

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
                            self.__btn("立即签到", "mdi-calendar-check", "/signin", 4),
                            self.__btn("考核检查", "mdi-clipboard-check", "/exam", 4),
                            self.__btn("IO 检查", "mdi-speedometer", "/io", 4),
                        ]),
                        self.__alert("「立即巡检」= 签到 + 考核 + IO 一次跑完;"
                                     "「启用/禁用插件」走 mp 的插件配置用例(保存 + 重新初始化 + 刷新调度),"
                                     "与在插件列表里开关等效;「测试通知」会忽略免打扰时段。"
                                     "结果约 10~20 秒后刷新本页可见。", "info", 12),
                    ]),
                    self.__card("考核进度", "mdi-clipboard-check", [self.__pane(exam_text)]),
                    self.__card("签到结果", "mdi-calendar-check", [self.__pane(sign_text)]),
                    self.__card("IO 健康", "mdi-speedometer", [self.__pane(io_text)]),
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
                "message": "已开始巡检(签到 + 考核 + IO),约 10~20 秒后刷新本页查看结果"}

    def api_io(self):
        self.__bg(self.run_io, manual=True)
        return {"success": True, "message": "已开始 IO 巡检,约 10 秒后刷新本页查看结果"}

    def api_signin(self):
        self.__bg(self.run_signin, manual=True)
        return {"success": True, "message": "已开始站点签到,约 10 秒后刷新本页查看结果"}

    def api_exam(self):
        self.__bg(self.run_exam, manual=True)
        return {"success": True, "message": "已开始考核检查,约 10 秒后刷新本页查看结果"}

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
        signin, exam = [], []
        if self._signin_enabled:
            try:
                signin = self.__do_signin()
            except Exception as e:
                logger.error(f"【NAS哨兵】签到模块异常:{e}")
                signin = [f"签到模块异常:{e}"]
        risks: List[str] = []
        if self._exam_enabled:
            try:
                exam = self.__do_exam(risks)
            except Exception as e:
                logger.error(f"【NAS哨兵】考核模块异常:{e}")
                exam = [f"考核模块异常:{e}"]
        io = {}
        try:
            io = self.__sample_io(notify_issue=self._notify_issue and not manual)
        except Exception as e:
            logger.error(f"【NAS哨兵】IO 模块异常:{e}")
            io = {"summary": f"IO 模块异常:{e}", "level": "🔴 异常", "breached": False}

        result = {"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                  "signin": signin, "exam": exam, "io": io}
        self.save_data("last_result", result)

        # 考核风险:独立告警(与简报解耦)
        if risks and self._exam_notify_risk:
            self.__notify_send("NAS 哨兵·考核风险", "\n".join(risks))

        # 每日简报:仅在开启且非手动时发送
        if self._notify and self._notify_daily and not manual:
            self.__notify_send("NAS 哨兵·每日简报", self.__build_brief(result))
        if manual:
            return "巡检完成(签到 %d 项 / 考核 %d 项 / IO:%s)" % (
                len(signin), len(exam), io.get("level", "?"))
        return "巡检完成"

    def run_signin(self, manual: bool = False) -> str:
        if not self._signin_enabled:
            return "签到模块未启用"
        try:
            lines = self.__do_signin()
        except Exception as e:
            logger.error(f"【NAS哨兵】签到异常:{e}")
            return f"签到异常:{e}"
        if lines:
            self.save_data("last_signin_only", {"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                                "lines": lines})
        if self._signin_notify and not manual:
            self.__notify_send("NAS 哨兵·签到结果", "\n".join(lines) or "无站点需要签到")
        return "\n".join(lines) if manual else "签到完成"

    def run_exam(self, manual: bool = False) -> str:
        if not self._exam_enabled:
            return "考核模块未启用"
        risks: List[str] = []
        try:
            lines = self.__do_exam(risks)
        except Exception as e:
            logger.error(f"【NAS哨兵】考核检查异常:{e}")
            return f"考核检查异常:{e}"
        if risks and self._exam_notify_risk and not manual:
            self.__notify_send("NAS 哨兵·考核风险", "\n".join(risks))
        return "\n".join(lines) if manual else "考核检查完成"

    def run_io(self, manual: bool = False) -> str:
        try:
            io = self.__sample_io(notify_issue=self._notify_issue and not manual)
        except Exception as e:
            logger.error(f"【NAS哨兵】IO 巡检异常:{e}")
            return f"IO 巡检异常:{e}"
        if manual:
            return io.get("summary", "IO 巡检完成")
        return "IO 巡检完成"

    # =====================================================================
    # 模块 1:通用 NexusPHP 签到
    # =====================================================================
    def __do_signin(self) -> List[str]:
        out: List[str] = []
        if not self._signin_sites:
            return out
        for sid in self._signin_sites:
            site = self.__get_site(sid)
            if not site:
                out.append(f"[{sid}] 站点不存在")
                continue
            name = getattr(site, "name", str(sid))
            try:
                out.append(self.__signin_one(site))
            except Exception as e:
                logger.error(f"【NAS哨兵】{name} 签到异常:{e}")
                out.append(f"{name}: 异常 {e}")
        return out

    def __signin_one(self, site) -> str:
        name = getattr(site, "name", "?")
        base = (getattr(site, "url", "") or "").rstrip("/")
        cookie = self._signin_cookie or (getattr(site, "cookie", "") or "")
        ua = self._signin_ua or (getattr(site, "ua", "") or DEFAULT_UA)
        if not base:
            return f"{name}: 站点 URL 为空"
        if not cookie:
            return f"{name}: 未配置 Cookie,跳过(本插件用 Cookie 签到,不走用户名密码)"
        url = base + self._signin_path
        r = self.__http(url, cookie=cookie, ua=ua)
        if r is None:
            return f"{name}: 请求失败"
        if r.status_code != 200:
            return f"{name}: HTTP {r.status_code}"
        page = r.text or ""
        text = self.__text_of(page)

        # 情况 A:页面已显示签到过(覆盖站点多种措辞:签到成功/已连续签到/签到已得 等)
        if RE_SIGNED.search(text):
            if self._signin_skip_signed:
                return f"{name}: 今日已签到(跳过)"
            return f"{name}: 今日已签到"

        extra = self.__parse_kv(self._signin_extra_form)

        # 情况 B:存在签到表单 -> 按表单提交(POST)
        form = re.search(r"(?is)<form[^>]*>(.*?)</form>", page)
        if form:
            fm = re.search(r'(?is)<form[^>]*action=["\']?([^"\'>\s]+)', page)
            action = fm.group(1) if fm else self._signin_path
            inputs = re.findall(r'(?is)<input[^>]*>', form.group(1))
            data: Dict[str, str] = {}
            for tag in inputs:
                n = re.search(r'name=["\']([^"\']+)["\']', tag, re.I)
                if not n:
                    continue
                v = re.search(r'value=["\']([^"\']*)["\']', tag, re.I)
                data[n.group(1)] = v.group(1) if v else ""
            data.update(extra)
            target = action if action.lower().startswith("http") else base + "/" + action.lstrip("/")
            r2 = self.__http(target, cookie=cookie, ua=ua, method="POST", data=data)
            if r2 is None:
                return f"{name}: 表单已提交但无响应(字段:{','.join(data) or '无'})"
            t2 = self.__text_of(r2.text or "")
            if re.search(r"(签到成功|成功|已经签到|已签到)", t2):
                return f"{name}: 签到成功(POST 表单)"
            return f"{name}: 已提交表单,未见成功字样(HTTP {r2.status_code})"

        # 情况 C:签到链接(GET)
        link = re.search(r'(?is)<a[^>]+href=["\']([^"\']*?(?:attendance|sign|checkin)[^"\']*)["\'][^>]*>',
                         page)
        if link and "attendance.php" not in link.group(1):
            target = link.group(1)
            if not target.lower().startswith("http"):
                target = base + "/" + target.lstrip("/")
            r3 = self.__http(target, cookie=cookie, ua=ua)
            t3 = self.__text_of((r3.text if r3 else "") or "")
            if re.search(r"(签到成功|成功|已签到)", t3):
                return f"{name}: 签到成功(GET 链接)"
            return f"{name}: 已请求签到链接,未见成功字样"

        # 情况 D:无法判定 -> 把探测结果报告出来(便于人工确认机制)
        if extra:
            # 配了附加表单字段,尝试直接 POST 到签到路径
            r4 = self.__http(url, cookie=cookie, ua=ua, method="POST", data=extra)
            t4 = self.__text_of((r4.text if r4 else "") or "")
            if re.search(r"(签到成功|成功|已经签到|已签到)", t4):
                return f"{name}: 签到成功(附加字段 POST)"
            return f"{name}: 已按附加字段 POST,未见成功字样"
        hint = "页面无表单/无签到链接/无已签到提示"
        return f"{name}: 未识别签到方式({hint})"

    # =====================================================================
    # 模块 2:通用 NexusPHP 考核进度
    # =====================================================================
    def __do_exam(self, risks: Optional[List[str]] = None) -> List[str]:
        out: List[str] = []
        if not self._exam_sites:
            return out
        for sid in self._exam_sites:
            site = self.__get_site(sid)
            if not site:
                out.append(f"[{sid}] 站点不存在")
                continue
            name = getattr(site, "name", str(sid))
            try:
                out.extend(self.__exam_one(site, risks))
            except Exception as e:
                logger.error(f"【NAS哨兵】{name} 考核解析异常:{e}")
                out.append(f"{name}: 考核解析异常 {e}")
        return out

    def __exam_one(self, site, risks: Optional[List[str]] = None) -> List[str]:
        name = getattr(site, "name", "?")
        sid = int(getattr(site, "id", -1))
        base = (getattr(site, "url", "") or "").rstrip("/")
        cookie = getattr(site, "cookie", "") or ""
        ua = getattr(site, "ua", "") or DEFAULT_UA

        # 单点配置:按站点覆盖考核页面与指标目标
        per = self.__exam_sites_cfg().get(sid) or {}
        paths = per.get("paths") or self._exam_paths

        page = ""
        hit_path = ""
        for path in paths:
            if not path:
                continue
            r = self.__http(base + path, cookie=cookie, ua=ua)
            if r is not None and r.status_code == 200 and self._exam_keyword in (r.text or ""):
                page = r.text
                hit_path = path
                break
        if not page:
            return [f"{name}: 未找到考核信息(试过 {','.join(paths)})"]
        text = self.__text_of(page)
        out: List[str] = []
        head = RE_EXAM_NAME.search(text)
        tm = RE_EXAM_TIME.search(text)
        if head or tm:
            seg = text[max(0, (head.start() if head else 0) - 5): (tm.end() if tm else 0) + 400]
            items = RE_EXAM_ITEM.findall(seg)
            title = head.group(1).strip() if head else "考核"
            out.append(f"【{name}】{title}(来源 {hit_path})")
            if tm:
                out.append(f"   期限:{tm.group(1)} ~ {tm.group(2)}")
            if self._exam_metrics:
                want = [x.strip() for x in re.split(r"[,、;]", self._exam_metrics) if x.strip()]
                items = [it for it in items if any(w in it[1] for w in want)] or items
            for idx, label, req, cur, res in items:
                flag = "✅" if ("通过" in res and "未" not in res) else "❌"
                # 单点配置里的目标值优先于页面要求
                ov = self.__target_for(label, per.get("targets") or {})
                if ov:
                    req = ov
                out.append(f"   {flag} 指标{idx} {label.strip()}:要求 {req.strip()},"
                           f"当前 {cur.strip()},结果 {res.strip()}")
            # 进度外推(仅对有单位一致的两项做粗算,失败则跳过)
            try:
                eta_lines, risk_lines = self.__exam_eta(tm, items, name)
                out.extend(eta_lines)
                if risks is not None:
                    risks.extend(risk_lines)
            except Exception as e:
                logger.debug(f"【NAS哨兵】考核外推失败:{e}")
            # 单点配置里填了目标但页面没给出对应指标 -> 明确提示
            for k, v in (per.get("targets") or {}).items():
                if not any(k in it[1] for it in items):
                    out.append(f"   🎯 目标 {k} = {v}(该站点页面未提供此指标当前值)")
            if tm:
                try:
                    end = datetime.strptime(tm.group(2), "%Y-%m-%d %H:%M:%S")
                    left_days = (end - datetime.now()).total_seconds() / 86400
                    if 0 < left_days <= self._exam_warn_days and not all(
                            ("通过" in it[4] and "未" not in it[4]) for it in items):
                        msg = f"【{name}】考核剩余 {left_days:.1f} 天(阈值 {self._exam_warn_days} 天),仍未全部通过"
                        out.append(f"   ⏰ {msg}")
                        if risks is not None:
                            risks.append(msg)
                except Exception:
                    pass
        return out or [f"{name}: 未解析到考核条目"]

    def __exam_eta(self, tm, items, site_name: str = "") -> Tuple[List[str], List[str]]:
        """基于当前值与已用时间,粗算剩余时间的达成可能性。返回(展示行, 风险行)。"""
        if not tm or not items:
            return [], []
        try:
            start = datetime.strptime(tm.group(1), "%Y-%m-%d %H:%M:%S")
            end = datetime.strptime(tm.group(2), "%Y-%m-%d %H:%M:%S")
        except Exception:
            return [], []
        now = datetime.now()
        used = max((now - start).total_seconds(), 1)
        left = (end - now).total_seconds()
        if left <= 0:
            return ["   ⏰ 考核期已结束"], []
        lines: List[str] = []
        risks: List[str] = []
        for _idx, label, req, cur, _res in items:
            rv, ru = self.__num(req)
            cv, cu = self.__num(cur)
            if rv is None or cv is None:
                continue
            # 只处理同量纲或可换算的(此处按原值比较,避免误算)
            if ru and cu and ru.lower() != cu.lower():
                continue
            need = rv - cv
            if need <= 0:
                lines.append(f"   ⏳ {label.strip()}:已达标")
                continue
            rate = cv / used
            if rate <= 0:
                lines.append(f"   ⏳ {label.strip()}:进度为 0,当前速率无法预计")
                risks.append(f"【{site_name}】{label.strip()}:进度为 0")
                continue
            eta = need / rate
            ok = eta <= left
            lines.append("   ⏳ %s:按当前速率还需 %.1f 天,剩余 %.1f 天 → %s" % (
                label.strip(), eta / 86400, left / 86400, "来得及" if ok else "**有风险**"))
            if not ok:
                risks.append("【%s】%s:按当前速率还需 %.1f 天 > 剩余 %.1f 天" % (
                    site_name, label.strip(), eta / 86400, left / 86400))
        return lines, risks

    # =====================================================================
    # 模块 3:IO / 刷流健康哨兵
    # =====================================================================
    def __sample_io(self, notify_issue: bool = False) -> Dict[str, Any]:
        load1, load5, load15, iowait = self.__load()
        devs = self.__disk_rates(float(self._io_sample_seconds))
        if self._io_check_qbt:
            up_mbps, dl_mbps, qbt_state = self.__qbt_rate()
        else:
            up_mbps, dl_mbps, qbt_state = None, None, ""

        breached, lines = [], []
        lines.append("负载 %.2f / %.2f / %.2f(1/5/15 分),IO 等待 %.1f%%" % (
            load1, load5, load15, iowait * 100))
        if load1 > self._load_threshold:
            breached.append("负载 %.2f > 红线 %.2f" % (load1, self._load_threshold))
        if iowait * 100 > self._iowait_threshold:
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
        if qbt_state:
            lines.append("  种子状态:%s" % qbt_state)

        level = "🔴 超红线" if breached else "🟢 正常"
        summary = "%s\n%s" % ("; ".join(breached) if breached else "全部指标正常", "\n".join(lines))
        result = {"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "level": level,
                  "breached": bool(breached), "summary": summary,
                  "load1": load1, "up_mbps": up_mbps, "iowait": round(iowait * 100, 1),
                  "queue": max([d.get("queue", 0) for d in devs.values()] or [0])}

        # 落盘最近一次 IO 结果 + 历史采样(供页面展示;与是否通知无关)
        self.save_data("last_io", result)
        hist = self.get_data("io_history") or []
        hist.append({"time": result["time"], "level": level, "load1": load1,
                     "up_mbps": up_mbps, "queue": result["queue"]})
        self.save_data("io_history", hist[-max(self._io_keep, 1):])

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
        try:
            s, cfg = self.__qb_session()
            if not s:
                return None, None, ""
            host = cfg["host"]
            ti = s.get(host + "/api/v2/transfer/info", timeout=30).json()
            up = ti.get("up_info_speed", 0) / 1048576
            dl = ti.get("dl_info_speed", 0) / 1048576
            t = s.get(host + "/api/v2/torrents/info", timeout=60).json()
            from collections import Counter
            st = dict(Counter(x.get("state") for x in t))
            return up, dl, str(st)
        except Exception as e:
            logger.warn(f"【NAS哨兵】查询刷流下载器失败:{e}")
            return None, None, ""

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
        if result.get("signin"):
            lines.append("— 签到 —")
            lines.extend(result["signin"])
        if result.get("exam"):
            lines.append("— 考核 —")
            lines.extend(result["exam"])
        io = result.get("io") or {}
        if io:
            lines.append("— IO —")
            lines.append(io.get("summary", ""))
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
    def __as_int_list(v) -> List[int]:
        out = []
        for x in (v or []):
            try:
                out.append(int(x))
            except Exception:
                continue
        return out

    @staticmethod
    def __as_str_list(v) -> List[str]:
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        return [x.strip() for x in re.split(r"[,，]", str(v or "")) if x.strip()]

    @staticmethod
    def __as_float(v, d: float) -> float:
        try:
            return float(v)
        except Exception:
            return d

    @staticmethod
    def __parse_kv(text: str) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for ln in str(text or "").splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#") or "=" not in ln:
                continue
            k, _, v = ln.partition("=")
            if k.strip():
                out[k.strip()] = v.strip()
        return out

    @staticmethod
    def __to_bytes(v: float, unit: str) -> Optional[float]:
        f = UNIT_FACTOR.get((unit or "").upper())
        return v * f if f else None

    @staticmethod
    def __num(s: str) -> Tuple[Optional[float], Optional[str]]:
        m = RE_UNIT_NUM.search(s or "")
        if not m:
            return None, None
        return float(m.group(1)), (m.group(2) or "").upper()

    @staticmethod
    def __text_of(page: str) -> str:
        t = re.sub(r"(?is)<(script|style).*?</\1>", " ", page or "")
        t = re.sub(r"(?s)<[^>]+>", " ", t)
        t = html.unescape(t)
        return re.sub(r"\s+", " ", t)

    def __http(self, url: str, cookie: str = "", ua: str = DEFAULT_UA, method: str = "GET",
               data: Optional[Dict[str, str]] = None, timeout: Optional[int] = None):
        """带重试的请求。重试次数由 signin_retry 控制(0~5)。"""
        attempts = max(1, int(self._signin_retry) + 1)
        h = {"User-Agent": ua or DEFAULT_UA}
        if cookie:
            h["Cookie"] = cookie
        for i in range(attempts):
            try:
                s = requests.Session()
                return s.request(method, url, headers=h, data=data,
                                 timeout=timeout or self._http_timeout, allow_redirects=True)
            except Exception as e:
                if i == attempts - 1:
                    logger.warn(f"【NAS哨兵】请求 {url} 失败(重试 {i} 次):{e}")
                else:
                    time.sleep(1.5)
        return None

    def __get_site(self, site_id: int):
        try:
            if SiteOper is None:
                return None
            for s in SiteOper().list_order_by_pri():
                if int(getattr(s, "id", -1)) == int(site_id):
                    return s
        except Exception as e:
            logger.warn(f"【NAS哨兵】查询站点 {site_id} 失败:{e}")
        return None

    def __exam_sites_cfg(self) -> Dict[int, Dict[str, Any]]:
        """解析「考核单点配置」。

        每行:`站点ID | 考核页面 | 上传目标 | 做种积分目标 | 分享率目标 | 备注`
        目标字段支持两种写法:
          * 位置式(第 3/4/5 个字段):依次对应 上传 / 做种积分 / 分享率
          * 关键词式(任一字段):`关键词=目标`,如 `上传=83.2GB`、`积分=1200`
        空字段表示沿用页面上的要求。
        """
        POSITIONAL = ["上传", "积分", "分享率"]
        out: Dict[int, Dict[str, Any]] = {}
        for raw in str(self._exam_site_config or "").splitlines():
            ln = raw.strip()
            if not ln or ln.startswith("#"):
                continue
            seg = [x.strip() for x in ln.split("|")]
            if not seg or not seg[0].isdigit():
                continue
            sid = int(seg[0])
            paths = []
            if len(seg) > 1 and seg[1]:
                paths = [x.strip() for x in re.split(r"[,，\s]+", seg[1]) if x.strip()]
            targets: Dict[str, str] = {}
            for i, fld in enumerate(seg[2:]):
                if not fld:
                    continue
                if "=" in fld:
                    k, _, v = fld.partition("=")
                    if k.strip() and v.strip():
                        targets[k.strip()] = v.strip()
                elif i < len(POSITIONAL) and fld:
                    targets[POSITIONAL[i]] = fld
            out[sid] = {"paths": paths, "targets": targets}
        return out

    @staticmethod
    def __target_for(label: str, targets: Dict[str, str]) -> str:
        for k, v in (targets or {}).items():
            if k and k in (label or ""):
                return v
        return ""

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
