"""
NAS 哨兵 (nas-sentinel) — MoviePilot 插件

通用哨兵:把「站点签到、考核进度、刷流/磁盘 IO 健康」三件需要人盯的事,
变成自动巡检 + 到点告警。

设计原则(为了将来能发布给其他人用):
  * 不写死任何本机路径/设备名/下载器名,全部可配置
  * 站点相关操作用「通用 NexusPHP 格式」解析,不针对单一站点硬编码
  * 失败隔离:任一模块异常不影响其它模块,全部输出到日志
"""

import html
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests
from apscheduler.triggers.cron import CronTrigger

from app.log import logger
from app.plugins import _PluginBase

# ---- 可选依赖:尽量不让插件因 mp 版本差异而加载失败 -------------------------
try:
    from app.schemas.types import MessageType
    _MSG_TYPE = getattr(MessageType, "Notification", None)
except Exception:  # pragma: no cover
    _MSG_TYPE = None

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
RE_SIGNED = re.compile(r"(已经签到|已签到|今日已签到|签到成功)")
RE_UNIT_NUM = re.compile(r"([\d.]+)\s*([KMGTP]?B)?", re.I)


class NasSentinel(_PluginBase):
    # ---- 插件元信息 ---------------------------------------------------------
    plugin_name = "NAS 哨兵"
    plugin_desc = "通用哨兵:站点签到补位、考核进度追踪、刷流与磁盘 IO 健康巡检,异常即报。"
    plugin_icon = "sentinel.png"
    plugin_version = "0.1.1"
    plugin_author = "Niven"
    author_url = "https://github.com/mao0824"
    plugin_config_prefix = "nassentinel_"
    plugin_order = 50
    auth_level = 1

    # ---- 运行时状态 ---------------------------------------------------------
    _enabled = False
    _notify = True
    _notify_daily = True
    _notify_issue = True
    _cron = "30 8 * * *"
    _signin_sites: List[int] = []
    _signin_path = "/attendance.php"
    _exam_sites: List[int] = []
    _io_enabled = True
    _io_interval = 5
    _io_devices = ""
    _load_threshold = 8.0
    _queue_threshold = 50
    _up_rate_min = 1.0
    _auto_downgrade = False
    _downgrade_cooldown = 30
    _downgrade_step = 1
    _qb_downloader = ""

    def init_plugin(self, config: dict = None):
        cfg = config or {}
        self._enabled = bool(cfg.get("enabled"))
        self._notify = cfg.get("notify", True)
        self._notify_daily = cfg.get("notify_daily", True)
        self._notify_issue = cfg.get("notify_issue", True)
        self._cron = (cfg.get("cron") or "30 8 * * *").strip()
        self._signin_sites = self.__as_int_list(cfg.get("signin_sites"))
        self._signin_path = (cfg.get("signin_path") or "/attendance.php").strip()
        self._exam_sites = self.__as_int_list(cfg.get("exam_sites"))
        self._io_enabled = cfg.get("io_enabled", True)
        try:
            self._io_interval = max(1, int(cfg.get("io_interval") or 5))
        except Exception:
            self._io_interval = 5
        self._io_devices = (cfg.get("io_devices") or "").strip()
        self._load_threshold = self.__as_float(cfg.get("load_threshold"), 8.0)
        self._queue_threshold = self.__as_float(cfg.get("queue_threshold"), 50)
        self._up_rate_min = self.__as_float(cfg.get("up_rate_min"), 1.0)
        self._auto_downgrade = bool(cfg.get("auto_downgrade"))  # 默认关闭
        try:
            self._downgrade_cooldown = max(1, int(cfg.get("downgrade_cooldown") or 30))
        except Exception:
            self._downgrade_cooldown = 30
        try:
            self._downgrade_step = max(1, int(cfg.get("downgrade_step") or 1))
        except Exception:
            self._downgrade_step = 1
        self._qb_downloader = (cfg.get("qb_downloader") or "").strip()

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
        # 1) 每日巡检:签到 + 考核进度 + 简报
        if self._cron and str(self._cron).count(" ") == 4:
            try:
                services.append({
                    "id": "NasSentinelDaily",
                    "name": "NAS哨兵-每日巡检",
                    "trigger": CronTrigger.from_crontab(self._cron),
                    "func": self.run_daily,
                    "kwargs": {},
                })
            except Exception as e:
                logger.error(f"【NAS哨兵】每日巡检 cron 解析失败:{e}")
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
        return [
            {"path": "/run", "endpoint": self.api_run, "methods": ["GET"],
             "summary": "立即执行一次完整巡检(签到+考核+IO)"},
            {"path": "/io", "endpoint": self.api_io, "methods": ["GET"],
             "summary": "立即执行一次 IO 巡检"},
            {"path": "/signin", "endpoint": self.api_signin, "methods": ["GET"],
             "summary": "立即执行一次站点签到"},
        ]

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        site_opts = []
        try:
            if SiteOper is not None:
                site_opts = [{"title": s.name, "value": s.id} for s in SiteOper().list_order_by_pri()]
        except Exception as e:
            logger.warn(f"【NAS哨兵】读取站点列表失败:{e}")

        return [
            {
                "component": "VForm",
                "content": [
                    self.__row([
                        self.__switch("enabled", "启用插件", 3),
                        self.__switch("notify", "启用通知", 3),
                        self.__switch("notify_daily", "每日简报", 3),
                        self.__switch("notify_issue", "异常即报", 3),
                    ]),
                    self.__row([
                        self.__text("cron", "每日巡检 cron(5 段)", 6, "30 8 * * *"),
                        self.__text("qb_downloader", "刷流下载器名(留空=自动)", 6, "如:刷流"),
                    ]),

                    {"component": "VDivider"},
                    {"component": "VSubheader", "props": {"class": "text-subtitle-2"}, "content": "站点签到(NexusPHP 通用)"},
                    self.__row([
                        self.__select("signin_sites", "需要签到的站点", 6, site_opts),
                        self.__text("signin_path", "签到相对路径", 6, "/attendance.php"),
                    ]),

                    {"component": "VDivider"},
                    {"component": "VSubheader", "props": {"class": "text-subtitle-2"}, "content": "考核进度追踪(NexusPHP 通用)"},
                    self.__row([self.__select("exam_sites", "需要追踪考核的站点", 12, site_opts)]),

                    {"component": "VDivider"},
                    {"component": "VSubheader", "props": {"class": "text-subtitle-2"}, "content": "IO 健康哨兵"},
                    self.__row([
                        self.__switch("io_enabled", "启用 IO 巡检", 4),
                        self.__text("io_interval", "采样间隔(分钟)", 4, "5"),
                        self.__text("io_devices", "监控设备(逗号分隔,留空=自动)", 4, "如:sda,sata1,nvme0n1"),
                    ]),
                    self.__row([
                        self.__text("load_threshold", "负载红线", 4, "8"),
                        self.__text("queue_threshold", "磁盘队列红线", 4, "50"),
                        self.__text("up_rate_min", "上传速率下限(MB/s)", 4, "1.0"),
                    ]),

                    {"component": "VDivider"},
                    {"component": "VSubheader", "props": {"class": "text-subtitle-2"}, "content": "自动降级(默认关闭)"},
                    self.__row([
                        self.__switch("auto_downgrade", "超红线自动降下载并发", 4),
                        self.__text("downgrade_step", "每次降低档数", 4, "1"),
                        self.__text("downgrade_cooldown", "冷却(分钟)", 4, "30"),
                    ]),
                    {"component": "VAlert", "props": {"type": "warning", "variant": "tonal", "class": "mb-3"},
                     "content": "自动降级会修改刷流下载器的并发上限。默认关闭,确认理解影响后再打开。"},
                ],
            },
            {
                "enabled": False,
                "notify": True,
                "notify_daily": True,
                "notify_issue": True,
                "cron": "30 8 * * *",
                "signin_sites": [],
                "signin_path": "/attendance.php",
                "exam_sites": [],
                "io_enabled": True,
                "io_interval": 5,
                "io_devices": "",
                "load_threshold": 8,
                "queue_threshold": 50,
                "up_rate_min": 1.0,
                "auto_downgrade": False,
                "downgrade_step": 1,
                "downgrade_cooldown": 30,
                "qb_downloader": "",
            },
        ]

    def get_page(self) -> Optional[List[dict]]:
        """展示最近一次巡检结果(只读)。"""
        last = self.get_data("last_result") or {}
        exam = last.get("exam") or []
        io = self.get_data("last_io") or last.get("io") or {}
        signin = last.get("signin") or []

        exam_text = "\n".join(exam) if exam else "尚未采集"
        sign_text = "\n".join(signin) if signin else "尚未采集"
        io_text = ("[%s]\n%s" % (io.get("time"), io.get("summary"))
                   if io.get("summary") else "尚未采集")

        return [
            {
                "component": "VForm",
                "content": [
                    self.__row([self.__alert("上次巡检:%s" % (last.get("time") or "从未运行"),
                                             "info", 12)]),
                    self.__row([self.__readonly("exam_view", "考核进度", 12, exam_text)]),
                    self.__row([self.__readonly("sign_view", "签到结果", 12, sign_text)]),
                    self.__row([self.__readonly("io_view", "IO 健康", 12, io_text)]),
                ],
            }
        ]

    def stop_service(self):
        pass

    # =====================================================================
    # API 端点
    # =====================================================================
    def api_run(self):
        return {"success": True, "message": self.run_daily(manual=True)}

    def api_io(self):
        return {"success": True, "message": self.run_io(manual=True)}

    def api_signin(self):
        return {"success": True, "message": "; ".join(self.__do_signin()) or "无站点需签到"}

    # =====================================================================
    # 巡检主体
    # =====================================================================
    def run_daily(self, manual: bool = False) -> str:
        logger.info("【NAS哨兵】开始每日巡检")
        signin, exam = [], []
        try:
            signin = self.__do_signin()
        except Exception as e:
            logger.error(f"【NAS哨兵】签到模块异常:{e}")
            signin = [f"签到模块异常:{e}"]
        try:
            exam = self.__do_exam()
        except Exception as e:
            logger.error(f"【NAS哨兵】考核模块异常:{e}")
            exam = [f"考核模块异常:{e}"]
        io = {}
        try:
            io = self.__sample_io(notify_issue=self._notify_issue and not manual)
        except Exception as e:
            logger.error(f"【NAS哨兵】IO 模块异常:{e}")
            io = {"summary": f"IO 模块异常:{e}", "breached": False}

        result = {"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                  "signin": signin, "exam": exam, "io": io}
        self.save_data("last_result", result)

        # 每日简报:仅在开启且非手动时发送
        if self._notify and self._notify_daily and not manual:
            body = self.__build_brief(result)
            self.__notify_send("NAS 哨兵·每日简报", body)
        if manual:
            return "巡检完成(签到 %d 项 / 考核 %d 项 / IO:%s)" % (
                len(signin), len(exam), io.get("level", "?"))
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
        cookie = getattr(site, "cookie", "") or ""
        ua = getattr(site, "ua", "") or DEFAULT_UA
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

        # 情况 A:页面已显示签到过
        if re.search(r"(已经签到|今日已签到|已签到)", text):
            return f"{name}: 今日已签到(跳过)"

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
        hint = "页面无表单/无签到链接/无已签到提示"
        return f"{name}: 未识别签到方式({hint})"

    # =====================================================================
    # 模块 2:通用 NexusPHP 考核进度
    # =====================================================================
    def __do_exam(self) -> List[str]:
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
                parsed = self.__exam_one(site)
                out.extend(parsed)
            except Exception as e:
                logger.error(f"【NAS哨兵】{name} 考核解析异常:{e}")
                out.append(f"{name}: 考核解析异常 {e}")
        return out

    def __exam_one(self, site) -> List[str]:
        name = getattr(site, "name", "?")
        base = (getattr(site, "url", "") or "").rstrip("/")
        cookie = getattr(site, "cookie", "") or ""
        ua = getattr(site, "ua", "") or DEFAULT_UA
        page = ""
        for path in ("/rules.php", "/"):
            r = self.__http(base + path, cookie=cookie, ua=ua)
            if r is not None and r.status_code == 200 and "考核" in (r.text or ""):
                page = r.text
                break
        if not page:
            return [f"{name}: 未找到考核信息"]
        text = self.__text_of(page)
        out: List[str] = []
        head = RE_EXAM_NAME.search(text)
        tm = RE_EXAM_TIME.search(text)
        if head or tm:
            seg = text[max(0, (head.start() if head else 0) - 5): (tm.end() if tm else 0) + 400]
            items = RE_EXAM_ITEM.findall(seg)
            title = head.group(1).strip() if head else "考核"
            out.append(f"【{name}】{title}")
            if tm:
                out.append(f"   期限:{tm.group(1)} ~ {tm.group(2)}")
            for idx, label, req, cur, res in items:
                flag = "✅" if ("通过" in res and "未" not in res) else "❌"
                out.append(f"   {flag} 指标{idx} {label.strip()}:要求 {req.strip()},当前 {cur.strip()},结果 {res.strip()}")
            # 进度外推(仅对有单位一致的两项做粗算,失败则跳过)
            try:
                out.extend(self.__exam_eta(tm, items))
            except Exception:
                pass
        return out or [f"{name}: 未解析到考核条目"]

    def __exam_eta(self, tm, items) -> List[str]:
        """基于当前值与已用时间,粗算剩余时间的达成可能性。"""
        if not tm or not items:
            return []
        try:
            start = datetime.strptime(tm.group(1), "%Y-%m-%d %H:%M:%S")
            end = datetime.strptime(tm.group(2), "%Y-%m-%d %H:%M:%S")
        except Exception:
            return []
        now = datetime.now()
        used = max((now - start).total_seconds(), 1)
        left = (end - now).total_seconds()
        if left <= 0:
            return ["   ⏰ 考核期已结束"]
        lines = []
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
                continue
            eta = need / rate
            ok = eta <= left
            lines.append("   ⏳ %s:按当前速率还需 %.1f 天,剩余 %.1f 天 → %s" % (
                label.strip(), eta / 86400, left / 86400, "来得及" if ok else "**有风险**"))
        return lines

    # =====================================================================
    # 模块 3:IO / 刷流健康哨兵
    # =====================================================================
    def __sample_io(self, notify_issue: bool = False) -> Dict[str, Any]:
        load1, load5, load15, iowait = self.__load()
        devs = self.__disk_rates()
        up_mbps, dl_mbps, qbt_state = self.__qbt_rate()

        breached, lines = [], []
        lines.append("负载 %.2f / %.2f / %.2f(1/5/15 分),IO 等待 %.2f" % (load1, load5, load15, iowait))
        if load1 > self._load_threshold:
            breached.append("负载 %.2f > 红线 %.2f" % (load1, self._load_threshold))

        if devs:
            worst = max(devs.values(), key=lambda d: d.get("queue", 0))
            for dev, d in sorted(devs.items(), key=lambda kv: -kv[1].get("queue", 0))[:4]:
                lines.append("  %s:读 %.2f MB/s 写 %.2f MB/s 队列 %d" % (
                    dev, d["read_mbps"], d["write_mbps"], d["queue"]))
            if worst.get("queue", 0) > self._queue_threshold:
                breached.append("设备 %s 队列 %d > 红线 %.0f" % (
                    worst["dev"], worst["queue"], self._queue_threshold))

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
                  "load1": load1, "up_mbps": up_mbps}

        # 落盘最近一次 IO 结果(供页面展示;与是否通知无关)
        self.save_data("last_io", result)

        # 超红线一律记日志(与通知开关解耦,保证可观测)
        if breached:
            logger.warn(f"【NAS哨兵】IO 超红线:{breached}")
        else:
            logger.debug(f"【NAS哨兵】IO 正常:负载 {load1:.2f},上传 {up_mbps}")

        # 异常即报(带冷却,避免刷屏)
        if breached and notify_issue and self._notify:
            last = self.get_data("last_issue_ts") or 0
            if time.time() - float(last) > max(self._downgrade_cooldown, 10) * 60:
                self.save_data("last_issue_ts", time.time())
                self.__notify_send("NAS 哨兵·异常告警", summary)
        # 自动降级(默认关闭)
        if breached and self._auto_downgrade and self._enabled:
            try:
                self.__auto_downgrade(breached)
            except Exception as e:
                logger.error(f"【NAS哨兵】自动降级失败:{e}")
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
                    out[p[2]] = {"rc": int(p[3]), "sr": int(p[5]), "wc": int(p[7]),
                                 "sw": int(p[9]), "q": int(p[11])}
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
            out[name] = {
                "dev": name,
                "read_mbps": (x["sr"] - y["sr"]) * 512 / seconds / 1048576,
                "write_mbps": (x["sw"] - y["sw"]) * 512 / seconds / 1048576,
                "queue": x["q"],
                "read_iops": drc / seconds,
                "write_iops": dwc / seconds,
            }
        return out

    # =====================================================================
    # 刷流下载器(qbt)查询 / 自动降级
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

    def __auto_downgrade(self, breached: List[str]):
        """超红线时把下载并发降一档(带冷却)。默认关闭,需用户在页面上显式开启。"""
        last = float(self.get_data("last_downgrade_ts") or 0)
        if time.time() - last < self._downgrade_cooldown * 60:
            return
        s, cfg = self.__qb_session()
        if not s:
            return
        host = cfg["host"]
        p = s.get(host + "/api/v2/app/preferences", timeout=30).json()
        cur = int(p.get("max_active_downloads") or 0)
        if cur <= 1:
            logger.info("【NAS哨兵】下载并发已为 %d,不再降级" % cur)
            return
        new = max(1, cur - self._downgrade_step)
        s.post(host + "/api/v2/app/setPreferences",
               data={"json": __import__("json").dumps({"max_active_downloads": new})}, timeout=30)
        self.save_data("last_downgrade_ts", time.time())
        msg = "超红线(%s),已将下载并发 %d → %d" % ("; ".join(breached), cur, new)
        logger.warn(f"【NAS哨兵】{msg}")
        if self._notify:
            self.__notify_send("NAS 哨兵·已自动降级", msg)

    # =====================================================================
    # 通知 / 工具
    # =====================================================================
    def __notify_send(self, title: str, text: str):
        try:
            self.post_message(mtype=_MSG_TYPE, title=title, text=text)
        except Exception as e:
            logger.warn(f"【NAS哨兵】通知发送失败:{e}")

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
    def __as_float(v, d: float) -> float:
        try:
            return float(v)
        except Exception:
            return d

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

    @staticmethod
    def __http(url: str, cookie: str = "", ua: str = DEFAULT_UA, method: str = "GET",
               data: Optional[Dict[str, str]] = None, timeout: int = 25):
        try:
            h = {"User-Agent": ua or DEFAULT_UA}
            if cookie:
                h["Cookie"] = cookie
            s = requests.Session()
            return s.request(method, url, headers=h, data=data, timeout=timeout,
                             allow_redirects=True)
        except Exception as e:
            logger.warn(f"【NAS哨兵】请求 {url} 失败:{e}")
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

    # ---- 表单小组件(减少重复)-------------------------------------------
    @staticmethod
    def __row(items: List[dict]) -> dict:
        return {"component": "VRow", "content": items}

    @staticmethod
    def __col(item: dict, md: int = 12) -> dict:
        return {"component": "VCol", "props": {"cols": 12, "md": md}, "content": [item]}

    def __switch(self, model: str, label: str, md: int = 3) -> dict:
        return self.__col({"component": "VSwitch", "props": {"model": model, "label": label}}, md)

    def __text(self, model: str, label: str, md: int = 6, hint: str = "") -> dict:
        return self.__col({"component": "VTextField",
                           "props": {"model": model, "label": label, "placeholder": hint}}, md)

    def __readonly(self, model: str, label: str, md: int, value: str) -> dict:
        return self.__col({"component": "VTextarea",
                           "props": {"model": model, "label": label, "rows": 8,
                                     "readonly": True, "model-value": value}}, md)

    def __select(self, model: str, label: str, md: int, options: List[dict]) -> dict:
        return self.__col({"component": "VSelect",
                           "props": {"model": model, "label": label, "multiple": True,
                                     "chips": True, "clearable": True,
                                     "items": options}}, md)

    def __alert(self, text: str, type_: str, md: int) -> dict:
        return self.__col({"component": "VAlert",
                           "props": {"type": type_, "variant": "tonal"}, "content": text}, md)
