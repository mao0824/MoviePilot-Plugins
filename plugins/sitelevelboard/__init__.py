"""
站点等级看板 (SiteLevelBoard) — MoviePilot 插件

【做什么】把「绑定站点的当前等级 / 下一级条件 / 到达下一级的时间(ETA) / 全部等级阶梯 /
保号与封号条款」汇成一页看板,并给出**流量时间线**(上传/下载/分享率/魔力/做种 的历史曲线)。

【与其它插件的边界】
  * SiteStatistic  : 站点数据统计(只看现状)      → 本插件只做「等级与晋级」
  * SiteAssessment : 新手考核(有截止日期的临时任务) → 本插件看的是长期等级状态
  * BrushFlow      : 刷流抓种删种                 → 本插件不改任何种子

【独立性】本插件**不依赖任何其它插件**:数据全部来自 mp 自带的 `user.db`(siteuserdata)、
  站点页,以及自己落盘的 plugindata;也不会去读别的插件的库表或端点。

【数据来源与优先级(docs/07 §4.4 定稿)】
  L1 当前值 : **自己取** —— 直读 mp 自身库 `/config/user.db` 的 `siteuserdata`
              (该表按 `updated_day` 每天一行,是天然的历史快照 → 斜率不必自建)
  L2 等级规则: **站点页优先 → 内置快照兜底 → 手动规则**;不一致时用站点页但**告警**
              内置快照来自 PT-depiler(MIT,`pt-plugins/PT-depiler`,419 站定义)与站点页交叉核对;
              其中 3 个站(馒头/PTS/PT时间)经过人工核对,优先级高于外部规则库

【渲染契约(踩坑记录,MP v3 前端 renderer 的真实行为)】
  * 文本必须放 ``props.text``(VAlert)或顶层 ``text``(div);``content`` 只放子节点列表
  * ``VSubheader`` 在 Vuetify 3 已被移除 → 分节标题用 ``div`` + ``text``
  * 只读展示不能用 ``model-value``(表单渲染器会用 v-model 覆盖)→ 用 ``div`` + ``text-pre-wrap``
  * **配置页渲染器不绑定点击事件** → 所有按钮只能放**数据页**(``events.click.api``)
"""

import json
import os
import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

import requests
from apscheduler.triggers.cron import CronTrigger
from pydantic import BaseModel

from app import schemas
from app.log import logger
from app.plugins import _PluginBase

try:
    from app.schemas.types import MessageType
    # 注意:MessageType 没有 Notification 成员,插件消息要用 Plugin
    _MSG_TYPE = getattr(MessageType, "Plugin", None)
except Exception:  # pragma: no cover
    _MSG_TYPE = None

try:
    # 通知渠道是枚举(值=中文显示名),post_message(channel=…) 要传「枚举成员」
    from app.schemas.types import NotificationChannel
except Exception:  # pragma: no cover
    NotificationChannel = None

DB_PATH = "/config/user.db"          # mp 自身库(插件就跑在 mp 容器里,直接读)
SNAPSHOT_DATE = "2026-10-11"          # 内置等级规则快照的日期(UI 上必须显示)
GB = 1024 ** 3                        # 站点阈值按 GiB 口径对齐 NexusPHP

# live_history 的解析口径版本。解析器修了字段/单位/千分位后必须 +1,
# 否则历史里老口径写进去的样本会继续污染斜率(取中位数也救不回来:样本里
# 28 条坏值 vs 1 条好值,中位数必然落在坏值上)。
#   1 → 初始版本:做种积分遇逗号截断(59674 读成 59)、缺 upload/download/seeding
#   2 → 2026-11-10:千分位 + 补 upload/download/seeding/leeching
LIVE_SCHEMA_VERSION = 2

# 馒头 API 的 role → 等级名(与 mp 的 MTeam_sysRoleList 一致,取前 10 档)
MROLE_NAMES = {
    "1": "User", "2": "Power User", "3": "Elite User", "4": "Crazy User",
    "5": "Insane User", "6": "Veteran User", "7": "Extreme User",
    "8": "Ultimate User", "9": "Nexus Master", "10": "VIP",
}

# 体积单位 → 字节(站点页写的是 23G / 1.2T 这种)
SIZE_UNITS = {"G": GB, "T": 1024 * GB, "M": 1024 ** 2, "K": 1024}


# ===========================================================================
# 内置等级规则快照
#   来源:PT-depiler(MIT)的站点定义 + 站点页逐项交叉核对(见 docs/07 §4.0/§4.2)
#   ⚠️ 口径:``interval`` 是「注册时长」需求(周);``download``/``upload`` 是增量口径的
#      体量需求;``ratio`` 为分享率下限;降级线只作为**风险提示**,不参与晋级计算。
#   ⚠️ 保号标注以**站点页为准**(站点页与快照冲突时,站点页赢):
#      PTS  = Extreme User 及以上「永远保留」、Elite 及以上「封存后不被删」  ← /rules.php 原文
#      PT时间 = Veteran User 及以上「永远保留」、Elite 及以上「封存后不被删」 ← /rules.php 原文
#      馒头   = Extreme User 及以上「永远保留」(站点不公开,取自 PT-depiler 快照)
# ===========================================================================
LEVEL_SPECS: Dict[int, Dict[str, Any]] = {
    # ---------------------------------------------------------------- 馒头
    3: {
        "source": "ptd_snapshot", "snapshot_date": SNAPSHOT_DATE,
        "ladder": [
            {"order": 1, "name": "User", "requirements": [], "privilege": "默认等级"},
            {"order": 2, "name": "Power User",
             "requirements": [{"key": "interval", "target": 4, "unit": "周"},
                              {"key": "download", "target": 200, "unit": "GB"},
                              {"key": "ratio", "target": 2.0}],
             "privilege": "魔力值加成 +1%;可匿名发表候选种子;可上传字幕"},
            {"order": 3, "name": "Elite User",
             "requirements": [{"key": "interval", "target": 8, "unit": "周"},
                              {"key": "download", "target": 400, "unit": "GB"},
                              {"key": "ratio", "target": 3.0}],
             "privilege": "魔力值加成 +2%;可发邀请;可管理自己上传的字幕"},
            {"order": 4, "name": "Crazy User",
             "requirements": [{"key": "interval", "target": 12, "unit": "周"},
                              {"key": "download", "target": 500, "unit": "GB"},
                              {"key": "ratio", "target": 4.0}],
             "privilege": "魔力值加成 +3%"},
            {"order": 5, "name": "Insane User",
             "requirements": [{"key": "interval", "target": 16, "unit": "周"},
                              {"key": "download", "target": 800, "unit": "GB"},
                              {"key": "ratio", "target": 5.0}],
             "privilege": "魔力值加成 +4%;可查看排行榜"},
            {"order": 6, "name": "Veteran User", "is_parkable": True,
             "requirements": [{"key": "interval", "target": 20, "unit": "周"},
                              {"key": "download", "target": 1000, "unit": "GB"},
                              {"key": "ratio", "target": 6.0}],
             "privilege": "魔力值加成 +5%;封存账号后不会被删除"},
            {"order": 7, "name": "Extreme User", "is_permanent": True, "is_parkable": True,
             "requirements": [{"key": "interval", "target": 24, "unit": "周"},
                              {"key": "download", "target": 2000, "unit": "GB"},
                              {"key": "ratio", "target": 7.0}],
             "privilege": "魔力值加成 +6%;永远保留"},
            {"order": 8, "name": "Ultimate User", "is_permanent": True, "is_parkable": True,
             "requirements": [{"key": "interval", "target": 28, "unit": "周"},
                              {"key": "download", "target": 2500, "unit": "GB"},
                              {"key": "ratio", "target": 8.0}],
             "privilege": "魔力值加成 +7%"},
            {"order": 9, "name": "Nexus Master", "is_permanent": True, "is_parkable": True,
             "requirements": [{"key": "interval", "target": 32, "unit": "周"},
                              {"key": "download", "target": 3000, "unit": "GB"},
                              {"key": "ratio", "target": 9.0}],
             "privilege": "魔力值加成 +8%"},
        ],
        "keep_rules": [{"text": "Extreme User 及以上:永远保留账号(站点未公开,取自 PT-depiler 快照)"},
                       {"text": "Veteran User 及以上:封存账号后不会被删除"}],
        "ban_rules": [],
    },
    # ---------------------------------------------------------------- PTS
    4: {
        "source": "site_page", "snapshot_date": SNAPSHOT_DATE,
        "ladder": [
            {"order": 1, "name": "User", "requirements": [], "privilege": "新用户默认级别"},
            {"order": 2, "name": "Power User", "demote_ratio": 0.95,
             "requirements": [{"key": "interval", "target": 4, "unit": "周"},
                              {"key": "seeding_bonus", "target": 40000, "unit": "分"},
                              {"key": "download", "target": 50, "unit": "GB"},
                              {"key": "ratio", "target": 1.05}],
             "privilege": "可在每周六中午12点至周日23:59发布种子"},
            {"order": 3, "name": "Elite User", "demote_ratio": 1.45, "is_parkable": True,
             "requirements": [{"key": "interval", "target": 8, "unit": "周"},
                              {"key": "seeding_bonus", "target": 80000, "unit": "分"},
                              {"key": "download", "target": 120, "unit": "GB"},
                              {"key": "ratio", "target": 1.55}],
             "privilege": "Elite User 及以上:封存账号后不会被删除"},
            {"order": 4, "name": "Crazy User", "demote_ratio": 1.95, "is_parkable": True,
             "requirements": [{"key": "interval", "target": 15, "unit": "周"},
                              {"key": "seeding_bonus", "target": 150000, "unit": "分"},
                              {"key": "download", "target": 300, "unit": "GB"},
                              {"key": "ratio", "target": 2.05}],
             "privilege": "得到两个邀请名额;可选择匿名模式"},
            {"order": 5, "name": "Insane User", "demote_ratio": 2.45, "is_parkable": True,
             "requirements": [{"key": "interval", "target": 25, "unit": "周"},
                              {"key": "seeding_bonus", "target": 250000, "unit": "分"},
                              {"key": "download", "target": 500, "unit": "GB"},
                              {"key": "ratio", "target": 2.55}],
             "privilege": "可以查看普通日志"},
            {"order": 6, "name": "Veteran User", "demote_ratio": 2.95, "is_parkable": True,
             "requirements": [{"key": "interval", "target": 40, "unit": "周"},
                              {"key": "seeding_bonus", "target": 400000, "unit": "分"},
                              {"key": "download", "target": 750, "unit": "GB"},
                              {"key": "ratio", "target": 3.05}],
             "privilege": "得到三个邀请名额"},
            {"order": 7, "name": "Extreme User", "demote_ratio": 3.45,
             "is_permanent": True, "is_parkable": True,
             "requirements": [{"key": "interval", "target": 60, "unit": "周"},
                              {"key": "seeding_bonus", "target": 600000, "unit": "分"},
                              {"key": "download", "target": 1024, "unit": "GB"},
                              {"key": "ratio", "target": 3.55}],
             "privilege": "Extreme User 及以上:永远保留账号"},
            {"order": 8, "name": "Ultimate User", "demote_ratio": 3.95,
             "is_permanent": True, "is_parkable": True,
             "requirements": [{"key": "interval", "target": 80, "unit": "周"},
                              {"key": "seeding_bonus", "target": 800000, "unit": "分"},
                              {"key": "download", "target": 1536, "unit": "GB"},
                              {"key": "ratio", "target": 4.05}],
             "privilege": "得到五个邀请名额"},
            {"order": 9, "name": "Nexus Master", "demote_ratio": 4.45,
             "is_permanent": True, "is_parkable": True,
             "requirements": [{"key": "interval", "target": 100, "unit": "周"},
                              {"key": "seeding_bonus", "target": 1000000, "unit": "分"},
                              {"key": "download", "target": 3072, "unit": "GB"},
                              {"key": "ratio", "target": 4.55}],
             "privilege": "得到十个邀请名额"},
        ],
        "keep_rules": [{"text": "Extreme User 及以上等级用户会永远保留"},
                       {"text": "Elite User 及以上等级用户封存账号后不会被删除"}],
        "ban_rules": [{"text": "封存账号的用户连续 400 天不登录将被删除账号"},
                      {"text": "未封存账号的用户连续 30 天不登录将被删除账号"},
                      {"text": "没有流量的用户(上传/下载都为 0)连续 7 天不登录将被删除账号"},
                      {"text": "过低的分享率会导致严重后果,包括禁止账号(下一级降级线已标注)"}],
    },
    # ------------------------------------------------------------- PT时间
    5: {
        "source": "site_page", "snapshot_date": SNAPSHOT_DATE,
        "ladder": [
            {"order": 0, "name": "Peasant", "requirements": [], "privilege": "婴儿级(处罚档)"},
            {"order": 1, "name": "User", "requirements": [], "privilege": "幼儿园(注册默认)"},
            {"order": 2, "name": "Power User",
             "requirements": [{"key": "interval", "target": 4, "unit": "周"},
                              {"key": "download", "target": 512, "unit": "GB"},
                              {"key": "ratio", "target": 1.05}],
             "privilege": "小学"},
            {"order": 3, "name": "Elite User", "is_parkable": True,
             "requirements": [{"key": "interval", "target": 8, "unit": "周"},
                              {"key": "download", "target": 2048, "unit": "GB"},
                              {"key": "ratio", "target": 1.55}],
             "privilege": "初中;Elite User 及以上:封存账号后不会被删除"},
            {"order": 4, "name": "Crazy User", "is_parkable": True,
             "requirements": [{"key": "interval", "target": 15, "unit": "周"},
                              {"key": "download", "target": 4096, "unit": "GB"},
                              {"key": "ratio", "target": 2.05}],
             "privilege": "高中"},
            {"order": 5, "name": "Insane User", "is_parkable": True,
             "requirements": [{"key": "interval", "target": 25, "unit": "周"},
                              {"key": "download", "target": 8192, "unit": "GB"},
                              {"key": "ratio", "target": 2.55}],
             "privilege": "专科"},
            {"order": 6, "name": "Veteran User", "is_permanent": True, "is_parkable": True,
             "requirements": [{"key": "interval", "target": 52, "unit": "周"},
                              {"key": "download", "target": 16384, "unit": "GB"},
                              {"key": "ratio", "target": 3.05}],
             "privilege": "本科;Veteran User 及以上:永远保留账号"},
            {"order": 7, "name": "Extreme User", "is_permanent": True, "is_parkable": True,
             "requirements": [{"key": "interval", "target": 80, "unit": "周"},
                              {"key": "download", "target": 25000, "unit": "GB"},
                              {"key": "ratio", "target": 3.55}],
             "privilege": "研究生;该级起免限期登录要求"},
            {"order": 8, "name": "Ultimate User", "is_permanent": True, "is_parkable": True,
             "requirements": [{"key": "interval", "target": 104, "unit": "周"},
                              {"key": "download", "target": 45000, "unit": "GB"},
                              {"key": "ratio", "target": 4.05}],
             "privilege": "博士生"},
            {"order": 9, "name": "Nexus Master", "is_permanent": True, "is_parkable": True,
             "requirements": [{"key": "interval", "target": 130, "unit": "周"},
                              {"key": "download", "target": 90000, "unit": "GB"},
                              {"key": "ratio", "target": 4.55}],
             "privilege": "博士后"},
            {"order": 10, "name": "VIP", "requirements": [], "privilege": "捐赠/VIP 档"},
        ],
        "keep_rules": [{"text": "Veteran User 及以上等级用户会永远保留"},
                       {"text": "Elite User 及以上等级用户封存账号后不会被删除"}],
        "ban_rules": [{"text": "封存账号的用户连续 400 天不登录将被删除账号"},
                      {"text": "未封存账号的用户连续 150 天不登录将被删除账号"},
                      {"text": "没有流量的用户连续 100 天不登录将被删除账号"},
                      {"text": "0-6 级需 200 天内至少登录/访问一次(仅脚本签到无效)"},
                      {"text": "下载量小于 100G:不参与升级或降级,保持 User 级(晋级前必须先把下载量做上去)"}],
    },
}


# ===========================================================================
# 规则库索引(domain → spec)
#   * 内置 3 站(馒头/PTS/PT时间)经过人工与站点页核对 → 优先级高于外部规则库
#   * level_specs.json 由 scripts/import_depiler_rules.py 从 PT-depiler(MIT) 生成,
#     不覆盖内置站;规则日期通过 _meta.date 标注到 UI
#   * 查找顺序:手动规则 → 站点页解析 → 内置快照 → 外部规则库 → l1_only
# ===========================================================================
BUILTIN_DOMAIN_MAP = {3: "m-team.cc", 4: "ptskit.org", 5: "pttime.org"}
RULES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "level_specs.json")
RULES_DATE = SNAPSHOT_DATE
LEVEL_SPECS_BY_DOMAIN: Dict[str, Dict[str, Any]] = {}

for _sid, _dom in BUILTIN_DOMAIN_MAP.items():
    if _sid in LEVEL_SPECS:
        LEVEL_SPECS_BY_DOMAIN[_dom] = LEVEL_SPECS[_sid]


def _normalize_ladder(spec: Dict[str, Any]) -> None:
    """把外部规则库的档位编号统一成 1..N。

    PT-depiler 的 ``levelRequirements`` 有的从 0 编号、有的从 1 编号(实测 59 个从 0、
    114 个从 1、还有 1 个从 3 起)。编号只用于**相对比较**(下一级 = 第一个 order 更大的档),
    重排安全;不统一则「离可封存还差 N 级」会整体差一档。
    """
    ladder = spec.get("ladder")
    if not isinstance(ladder, list) or not ladder:
        return
    try:
        ladder.sort(key=lambda lv: (lv.get("order") is None, lv.get("order") or 0))
    except Exception:
        return
    for idx, level in enumerate(ladder, start=1):
        level["order"] = idx


def _load_external_rules() -> int:
    """加载 level_specs.json(外部规则库)。内置站不覆盖,返回新增条数。"""
    global RULES_DATE
    try:
        with open(RULES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return 0
    except Exception as e:  # 规则库坏了不能让整个插件起不来
        logger.warn(f"【站点等级看板】规则库加载失败:{e}")
        return 0
    if not isinstance(data, dict):
        return 0
    meta = data.pop("_meta", None)
    if isinstance(meta, dict) and meta.get("date"):
        RULES_DATE = str(meta["date"])
    added = 0
    for dom, spec in data.items():
        key = str(dom or "").lower().strip()
        # depiler 里有 ``www.ptskit.org`` 这种带 www 的键,而 mp 的 site.domain 是
        # ``ptskit.org`` —— 后缀候选只能往「更短」走,永远撞不上带 www 的键。
        if key.startswith("www."):
            key = key[4:]
        if not key or not isinstance(spec, dict) or key in LEVEL_SPECS_BY_DOMAIN:
            continue
        _normalize_ladder(spec)
        LEVEL_SPECS_BY_DOMAIN[key] = spec
        added += 1
    return added


def _domain_candidates(domain: str) -> List[str]:
    """域名后缀候选:``kp.m-team.cc`` → [``kp.m-team.cc``, ``m-team.cc``, ``cc``]。"""
    parts = str(domain or "").lower().strip().split(".")
    return [".".join(parts[i:]) for i in range(max(1, len(parts) - 1))]


_RULES_ADDED = _load_external_rules()


# ===========================================================================
# 等级名别名表(与域名无关的「等价组」)
#   为什么必须有:``siteuserdata.user_level`` 存的是**站点页上显示的名字**,不是标准名。
#   实测 PTS 的 user_level 出现过「贵宾」,而它的阶梯只有 User…Nexus Master ——
#   原样比对必然对不上,只能显示「未知」。别名表把「同一档的不同写法」收敛成一个键。
#
#   口径:**宁缺勿错**。错映射会把档位算错、ETA 跟着错,比老实显示「未知」更糟。
#   所以这里只收高置信度等价;同一组在一个阶梯里命中多档时,一律判歧义、不猜。
# ===========================================================================
ALIAS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "level_aliases.json")
ALIAS_DATE = ""
ALIAS_GROUPS: List[List[str]] = []      # 每组=一组等价写法(已归一化)
ALIAS_CANONICAL: List[str] = []         # 与 ALIAS_GROUPS 同下标:该组的规范名
ALIAS_INDEX: Dict[str, int] = {}        # 归一化写法 → 组下标

_PAREN_RE = re.compile(r"[（(][^）)]*[）)]")
_PAREN_INNER_RE = re.compile(r"[（(]([^）)]*)[）)]")
# 「Lv.3 霜降」「3级 Power User」这类序号前缀:去掉它才是等级名本身
_ORDINAL_RE = re.compile(r"^(?:lv\.?\s*\d+|\d+\s*[级等])\s*", re.I)


def _norm_name(text: Any) -> str:
    """归一化等级名:去括号注释、压空白、转小写 —— ``(幼儿园)User`` → ``user``。"""
    return re.sub(r"\s+", " ", _PAREN_RE.sub("", str(text or ""))).strip().lower()


def _ascii_name(text: Any) -> str:
    """只留 ASCII 字母数字 —— 用来穿透「憨头憨脑 User」「User 咖啡新人」这类中英混排。"""
    return re.sub(r"\s+", " ", re.sub(r"[^0-9A-Za-z]+", " ", str(text or ""))).strip().lower()


def _name_keys(text: Any) -> Set[str]:
    """一个等级名的全部可比较键:原文、括号内别名、纯 ASCII 投影、去空格投影。

    括号别名是白捡的:PT-depiler 的站定义里本来就写 ``凡人(Power User)``、
    ``黔首(Peasant)``、``冠军训练家(EU)`` —— 中英对照与缩写都在里面。
    """
    raw = str(text or "")
    keys: Set[str] = set()
    for part in [raw] + _PAREN_INNER_RE.findall(raw):
        for key in (_norm_name(part), _ascii_name(part), _ascii_name(part).replace(" ", "")):
            if key:
                keys.add(key)
    return keys


def _expand_groups(keys: Set[str]) -> Set[str]:
    """命中别名组的键展开成整组 —— 让「中级用户」与「Elite User」互相认得。"""
    out = set(keys)
    for key in keys:
        gid = ALIAS_INDEX.get(key)
        if gid is not None:
            out.update(ALIAS_GROUPS[gid])
    return out


def _load_aliases() -> int:
    """加载 level_aliases.json,返回等价组数。缺失/损坏只是少一层兜底,不能让插件起不来。"""
    global ALIAS_DATE
    try:
        with open(ALIAS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return 0
    except Exception as e:
        logger.warn(f"【站点等级看板】别名表加载失败:{e}")
        return 0
    if not isinstance(data, dict):
        return 0
    ALIAS_DATE = str((data.get("_meta") or {}).get("date") or "")
    for grp in (data.get("groups") or []):
        if not isinstance(grp, dict):
            continue
        canonical = str(grp.get("canonical") or "").strip()
        names: List[str] = []
        for raw in [canonical] + list(grp.get("names") or []):
            key = _norm_name(raw)
            # 一个写法只能属于一个组:重复登记会让「同组多档」的歧义判断失效
            if key and key not in ALIAS_INDEX:
                names.append(key)
        if len(names) < 2:
            continue
        gid = len(ALIAS_GROUPS)
        ALIAS_GROUPS.append(names)
        ALIAS_CANONICAL.append(canonical or names[0])
        for key in names:
            ALIAS_INDEX[key] = gid
    return len(ALIAS_GROUPS)


_ALIAS_GROUPS_LOADED = _load_aliases()


def _parse_alias_rules(text: str) -> Dict[str, Dict[str, str]]:
    """解析配置里的「域名|站点显示名|规则库等级名」,返回 ``{域名: {显示名: 标准名}}``。"""
    out: Dict[str, Dict[str, str]] = {}
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [x.strip() for x in re.split(r"[|｜]", line)]
        if len(parts) < 3:
            continue
        domain, shown, canonical = parts[0].lower().lstrip("*."), parts[1], parts[2]
        if not domain or not shown or not canonical:
            continue
        out.setdefault(domain, {})[_norm_name(shown)] = canonical
    return out


class TrackPayload(BaseModel):
    """「新增/删除站点」请求体。"""
    site_id: int = 0
    site_ids: Optional[List[int]] = None


class ReorderPayload(BaseModel):
    """「左侧列表拖拽排序」请求体:必须是看板站点集合的一个排列。"""
    site_ids: List[int] = []


class RefreshPayload(BaseModel):
    """刷新请求体:``site_id`` 有值=只刷该站(同步返回),否则全量(后台)。"""
    site_id: int = 0


class ConfigPayload(BaseModel):
    """配置保存请求体(与 get_form 的字段一一对应,缺省即不改)。"""
    enabled: Optional[bool] = None
    run_once: Optional[bool] = None
    notify: Optional[bool] = None
    notify_daily: Optional[bool] = None
    notify_level_change: Optional[bool] = None
    notify_risk: Optional[bool] = None
    notify_eta: Optional[bool] = None
    eta_threshold_days: Optional[int] = None
    notify_channel: Optional[str] = None
    quiet_start: Optional[str] = None
    quiet_end: Optional[str] = None
    cron: Optional[str] = None
    debug: Optional[bool] = None
    prefer_source: Optional[str] = None
    use_site_page: Optional[bool] = None
    timeout: Optional[int] = None
    manual_rules: Optional[str] = None
    manual_first: Optional[bool] = None
    level_aliases: Optional[str] = None


class SiteLevelBoard(_PluginBase):
    # ---- 元信息 -----------------------------------------------------------
    plugin_name = "站点等级看板"
    plugin_desc = "把绑定站点的等级、晋级条件、ETA(预计多久到下一级)、保号与封号风险汇成一页,附流量时间线。"
    # 裸文件名只会去 mp 内置 plugin_icon/ 里找(没有我们的图标),所以用本仓库的 raw 地址自带图标
    plugin_icon = "https://raw.githubusercontent.com/mao0824/MoviePilot-Plugins/main/icons/level-board.png"
    plugin_version = "0.3.0"
    plugin_author = "Niven"
    author_url = "https://github.com/mao0824"
    plugin_config_prefix = "sitelevelboard_"
    plugin_order = 55
    auth_level = 1

    # ---- 运行时状态:通用 ---------------------------------------------------
    _enabled = False
    _notify = True
    _notify_daily = True
    _cron = "45 8 * * *"          # 刻意错开常见插件早上 08:00 / 08:30 的签到与考核任务
    _notify_channel = ""
    _quiet_start = ""
    _quiet_end = ""
    _debug = False

    # ---- 通知开关(三个解耦,任意组合)--------------------------------------
    _notify_level_change = True    # 等级变化
    _notify_risk = True            # 风险
    _notify_eta = False            # ETA 阈值(默认关)
    _eta_threshold_days = 7

    # ---- 抓取 --------------------------------------------------------------
    _sites: List[int] = []
    _prefer_source = "site_page"   # site_page | snapshot
    _use_site_page = True
    _timeout = 20

    # ---- 手动规则 ----------------------------------------------------------
    _manual_rules = ""
    _manual_first = False
    _level_aliases = ""                     # 「域名|站点显示名|规则库等级名」每行一条
    _level_alias_map: Dict[str, Dict[str, str]] = {}

    _lock = threading.Lock()

    # ---- 「站点页实时值」的内存 TTL 缓存 -----------------------------------
    # 为什么需要:__live_values 会真的去抓馒头 API / PTS / PT时间 的站点页(走公网,
    # 实测 0.35~1.05s/站)。而它被每个 /detail 请求、每次后台刷新反复调用 ——
    # 看板的判定粒度是「日」,同一份实时值在几分钟内重复抓没有意义,只把首屏拖慢。
    # 命中此缓存时首屏从 ~1.5s 降到毫秒级;失败(空结果)只缓存 60s,避免坏网络反复重试。
    _live_cache: Dict[int, Any] = {}
    _live_lock = threading.Lock()
    _live_ttl = 300

    # ---- 「整站评估结果」的内存 TTL 缓存 -----------------------------------
    # 上面那个缓存解决的是「重抓站点页」的开销;这里解决的是「整站评估」本身的开销
    # (读 user.db 历史 + 合并 state + 落盘 live_history),实测 0.3~2.9s。
    # 前端每次点站点都会请求 /detail,没这个缓存就得重算一遍,翻站点时明显发顿。
    _detail_cache: Dict[int, Any] = {}
    _detail_lock = threading.Lock()
    _detail_ttl = 180

    # =====================================================================
    # 初始化
    # =====================================================================
    def init_plugin(self, config: dict = None):
        cfg = config or {}
        self._enabled = bool(cfg.get("enabled"))
        self._notify = cfg.get("notify", True)
        self._notify_daily = cfg.get("notify_daily", True)
        self._cron = (cfg.get("cron") or "45 8 * * *").strip()
        self._notify_channel = (cfg.get("notify_channel") or "").strip()
        self._quiet_start = (cfg.get("quiet_start") or "").strip()
        self._quiet_end = (cfg.get("quiet_end") or "").strip()
        self._debug = bool(cfg.get("debug"))

        self._notify_level_change = cfg.get("notify_level_change", True)
        self._notify_risk = cfg.get("notify_risk", True)
        self._notify_eta = cfg.get("notify_eta", False)
        self._eta_threshold_days = self.__as_int(cfg.get("eta_threshold_days"), 7, 1, 365)

        sites = cfg.get("sites") or []
        self._sites = [int(x) for x in sites if str(x).strip().isdigit()]
        self._prefer_source = cfg.get("prefer_source") or "site_page"
        self._use_site_page = cfg.get("use_site_page", True)
        self._timeout = self.__as_int(cfg.get("timeout"), 20, 5, 120)

        self._manual_rules = (cfg.get("manual_rules") or "").strip()
        self._manual_first = bool(cfg.get("manual_first"))
        self._level_aliases = (cfg.get("level_aliases") or "").strip()
        self._level_alias_map = _parse_alias_rules(self._level_aliases)

        if cfg.get("run_once"):
            logger.info("【站点等级看板】检测到「保存后立即运行一次」,后台刷新")
            threading.Thread(target=self.run_daily, kwargs={"manual": True}, daemon=True).start()

    # =====================================================================
    # 对外契约
    # =====================================================================
    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_render_mode() -> Tuple[str, str]:
        """声明使用 **Vue 联邦组件**渲染界面。

        与「站点刷流(BrushFlow)」同款机制:前端是独立打包的 Vue 应用(``src/`` → ``dist/``),
        通过 ``@originjs/vite-plugin-federation`` 暴露 ``./Page``/``./Config`` 组件,MP 运行时加载;
        组件内通过注入的 ``api`` 客户端(``props.api.get/post``)调用本插件的 API 取数。
        —— Vuetify 声明式渲染做不了「左侧列表 + 弹窗筛选 + 增删」这类交互。
        """
        return "vue", "dist/assets"

    def get_service(self) -> List[Dict[str, Any]]:
        services: List[Dict[str, Any]] = []
        if not self._enabled:
            return services
        if self.__cron_ok(self._cron):
            services.append({
                "id": "SiteLevelBoardDaily",
                "name": "站点等级看板-每日刷新",
                "trigger": CronTrigger.from_crontab(self._cron),
                "func": self.run_daily,
                "kwargs": {},
            })
        return services

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            # ---- 前端(Vue 组件)用 ----
            {"path": "/sites", "endpoint": self.api_sites, "methods": ["GET"],
             "auth": "bear", "summary": "看板站点列表(已纳入 + 可新增候选)"},
            {"path": "/detail", "endpoint": self.api_detail, "methods": ["GET"],
             "auth": "bear", "summary": "单个站点的等级详情(含阶梯与历史)"},
            {"path": "/track", "endpoint": self.api_track, "methods": ["POST"],
             "auth": "bear", "summary": "把站点加入看板"},
            {"path": "/untrack", "endpoint": self.api_untrack, "methods": ["POST"],
             "auth": "bear", "summary": "把站点移出看板(不影响 mp 站点管理)"},
            {"path": "/reorder", "endpoint": self.api_reorder, "methods": ["POST"],
             "auth": "bear", "summary": "保存看板站点的展示顺序(左侧列表拖拽)"},
            {"path": "/config", "endpoint": self.api_config, "methods": ["GET"],
             "auth": "bear", "summary": "读取插件配置"},
            {"path": "/config/save", "endpoint": self.api_config_save, "methods": ["POST"],
             "auth": "bear", "summary": "保存插件配置"},
            {"path": "/refresh", "endpoint": self.api_refresh, "methods": ["GET", "POST"],
             "auth": "bear", "summary": "立即刷新站点等级数据(可指定 site_id)"},
            {"path": "/report", "endpoint": self.api_report, "methods": ["GET", "POST"],
             "auth": "bear", "summary": "生成一份可复制的文字汇总"},
            {"path": "/enable", "endpoint": self.api_enable, "methods": ["GET", "POST"],
             "auth": "bear", "summary": "启用本插件(等效插件列表开关)"},
            {"path": "/disable", "endpoint": self.api_disable, "methods": ["GET", "POST"],
             "auth": "bear", "summary": "禁用本插件(等效插件列表开关)"},
            {"path": "/test_notify", "endpoint": self.api_test_notify, "methods": ["GET", "POST"],
             "auth": "bear", "summary": "发送一条测试通知(忽略免打扰时段)"},
        ]

    # =====================================================================
    # 配置表单(四组;按钮一律放数据页 —— 配置渲染器不绑定点击事件)
    # =====================================================================
    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        chan_opts = [{"title": "全部渠道(默认)", "value": ""}]
        if NotificationChannel is not None:
            try:
                for m in NotificationChannel:
                    chan_opts.append({"title": str(m.value), "value": m.name})
            except Exception:
                pass

        site_opts = []
        try:
            for s in self.__sites_all():
                site_opts.append({"title": "%s(%s)" % (s["name"], s["domain"]), "value": s["id"]})
        except Exception as e:
            logger.warn(f"【站点等级看板】读取站点列表失败:{e}")

        return [
            {
                "component": "VForm",
                "content": [
                    self.__row([
                        self.__switch("enabled", "启用插件", 3),
                        self.__switch("run_once", "保存后立即运行一次", 3),
                        self.__switch("notify", "启用通知", 3),
                        self.__switch("notify_daily", "每日汇总", 3),
                    ]),
                    self.__alert("本页是「配置」。可点按钮(启用/禁用插件、立即刷新、测试通知)在插件列表里"
                                 "本插件的「数据」页 —— 配置表单渲染器不绑定点击事件,放在这里点了没反应。",
                                 "info", 12),

                    # ========== ① 通用 ==========
                    self.__card("① 通用", "mdi-tune", [
                        self.__row([
                            self.__cron("cron", "刷新周期(cron)", 4, "45 8 * * *"),
                            self.__select("notify_channel", "通知渠道", 4, chan_opts, multiple=False),
                            self.__text("quiet_start", "免打扰开始(HH:MM)", 2, "23:30"),
                            self.__text("quiet_end", "免打扰结束(HH:MM)", 2, "07:00"),
                        ]),
                        self.__row([self.__switch("debug", "详细日志", 3)]),
                        self.__alert("默认每天刷新一次(避开 08:00 / 08:30 的其它插件),可自行改成更频繁。",
                                     "info", 12),
                    ]),

                    # ========== ② 通知(三者解耦) ==========
                    self.__card("② 通知(三个开关可任意组合)", "mdi-bell-ring-outline", [
                        self.__row([
                            self.__switch("notify_level_change", "等级变化时通知(默认开)", 4),
                            self.__switch("notify_risk", "风险通知(默认开)", 4),
                            self.__switch("notify_eta", "ETA 阈值通知(默认关)", 4),
                        ]),
                        self.__row([
                            self.__text("eta_threshold_days", "ETA 阈值(天)", 3, "7"),
                        ], show="notify_eta"),
                        self.__alert("「等级变化」= 升级/降级即报;「风险」= 命中保号/封号/降级条款;"
                                     "「ETA 阈值」= 预计 N 天内可升级时提醒。三者互不影响,可分别开关。",
                                     "info", 12),
                    ]),

                    # ========== ③ 数据源 ==========
                    self.__card("③ 数据源", "mdi-database-search-outline", [
                        self.__row([
                            self.__select("sites", "参与站点(留空=全部)", 6, site_opts, multiple=True),
                            self.__select("prefer_source", "等级规则优先来源", 6, [
                                {"title": "站点页优先(推荐)", "value": "site_page"},
                                {"title": "规则库优先", "value": "snapshot"},
                            ], multiple=False),
                        ]),
                        self.__row([
                            self.__switch("use_site_page", "允许抓站点页(当前值/规则)", 4),
                            self.__text("timeout", "请求超时(秒)", 4, "20"),
                        ]),
                        self.__alert("**当前值**一律自己取(直读 mp 的 siteuserdata,不依赖外部);"
                                     "**等级规则**按「站点页 → 内置规则库 → 手动规则」依次兜底。"
                                     "内置规则库:%d 站(人工核对) + %d 站(PT-depiler,MIT,快照 %s)。"
                                     % (len(BUILTIN_DOMAIN_MAP),
                                        max(0, len(LEVEL_SPECS_BY_DOMAIN) - len(BUILTIN_DOMAIN_MAP)),
                                        RULES_DATE),
                                     "info", 12),
                    ]),

                    # ========== ④ 规则 ==========
                    self.__card("④ 规则与兜底", "mdi-format-list-numbered", [
                        self.__row([self.__switch("manual_first", "手动规则优先于内置规则", 6)]),
                        self.__row([
                            self.__textarea("manual_rules", "手动等级规则(每行一条)", 12, 4,
                                            "域名|等级名|条件表达式,如:m-team.cc|Power User|下载>=200;"
                                            "也兼容旧的站点ID写法(2|Lv.4|经验>=20000)"),
                        ]),
                        self.__row([
                            self.__textarea("level_aliases", "等级名别名(每行一条)", 12, 3,
                                            "域名|站点显示名|规则库等级名,如:ptskit.org|贵宾|VIP;"
                                            "站点显示的等级名与规则库写法不一致时填这里(不必重抄整个阶梯)"),
                        ]),
                        self.__alert("站点不公开等级门槛时(如馒头)用内置规则库兜底,UI 会标注来源与快照日期;"
                                     "快照可能滞后,若你手上有更准的门槛,填在「手动等级规则」里覆盖。"
                                     "等级名对不上(如站点写「贵宾」、规则库写「VIP」)时,先用「等级名别名」补;"
                                     "内置别名表 %d 组(快照 %s),对不上会在站点详情里直接告诉你。"
                                     % (len(ALIAS_GROUPS), ALIAS_DATE or "-"),
                                     "info", 12),
                    ]),
                ],
            },
            {
                # ---- 默认配置 ----
                "enabled": False,
                "notify": True,
                "notify_daily": True,
                "cron": "45 8 * * *",
                "run_once": False,
                "notify_channel": "",
                "quiet_start": "",
                "quiet_end": "",
                "debug": False,
                "notify_level_change": True,
                "notify_risk": True,
                "notify_eta": False,
                "eta_threshold_days": 7,
                "sites": [],
                "prefer_source": "site_page",
                "use_site_page": True,
                "timeout": 20,
                "manual_rules": "",
                "manual_first": False,
                "level_aliases": "",
            },
        ]

    # =====================================================================
    # 数据页
    # =====================================================================
    def get_page(self) -> List[dict]:
        """Vue 详情组件自行通过插件 API 取页面数据(与 BrushFlow 一致)。"""
        return []

    def stop_service(self) -> None:
        """MP 的 ``_PluginBase`` 把 ``stop_service`` 声明为**抽象方法**,必须实现。

        ⚠️ 2026-10-11 踩过两次:①初次漏写导致安装失败(TypeError: Can't instantiate
        abstract class … 'stop_service');②改代码时又把它连同废弃段一起删掉 ——
        已在自检里加「6 个抽象方法必须齐全」的断言。本插件无常驻资源,无需清理。
        """
        pass

    # ---------------------------------------------------------------------
    # 以下为「声明式渲染」遗留的文本渲染器:现在只服务于 /report 与通知正文
    # ---------------------------------------------------------------------
    # =====================================================================
    # API
    # =====================================================================
    @staticmethod
    def __bg(func, **kwargs):
        threading.Thread(target=func, kwargs=kwargs, daemon=True).start()

    def api_refresh(self, payload: Optional[RefreshPayload] = None):
        site_id = int(getattr(payload, "site_id", 0) or 0)
        if site_id:
            # 单站同步刷新:前端等结果(通常 1~3 秒) → 直接返回该站详情
            # force_live=True:用户主动点「刷新本站」,要的就是重抓站点页,不吃 TTL 缓存
            try:
                site = self.__site_by_id(site_id)
                if not site:
                    return schemas.Response(success=False, message="站点不存在")
                res = self.__evaluate(site, force_live=True)
                self.__merge_state([res])
                return schemas.Response(success=True, message="已刷新", data=self.__detail_payload(res))
            except Exception as e:
                logger.error(f"【站点等级看板】单站刷新失败:{e}")
                return schemas.Response(success=False, message=f"刷新失败:{e}")
        if self._lock.locked():
            return schemas.Response(success=False, message="上一轮刷新仍在进行中")
        self.__bg(self.run_daily, manual=True, force_live=True)
        return schemas.Response(success=True, message="已开始全量刷新,约 10~60 秒后返回本页刷新列表")

    # ---------------------------------------------------------------------
    # 前端 API:站点列表 / 详情 / 增删 / 配置
    # ---------------------------------------------------------------------
    def api_sites(self):
        """返回:已纳入看板的站点(含最新等级摘要) + 尚未纳入的候选站点。

        看板部分**按 plugindata["tracked"] 里的顺序返回**(用户拖拽排的序就存在那里),
        不再跟 mp 站点列表的顺序走;mp 里已删掉的 tracked id 直接跳过。
        """
        tracked_ids = self.__tracked_ids()
        state = self.get_data("level_state") or {}
        cache = {int(x["site_id"]): x for x in (state.get("sites") or []) if x.get("site_id")}
        by_id = {int(site["id"]): site for site in self.__sites_all()}
        usernames = self.__usernames()
        tracked, candidates = [], []
        wanted = []
        for sid in tracked_ids:
            if sid not in wanted:
                wanted.append(sid)
        for sid in wanted:
            site = by_id.get(sid)
            if not site:
                continue
            c = cache.get(sid) or {}
            tight = self.__tightest_req(c.get("reqs")) if c else None
            risks = c.get("risks") or []
            worst = ([x for x in risks if x.get("level") == "danger"] or risks or [{}])[0]
            # 老缓存(本次升级前写的)没有 has_ladder/is_top,用 level_order 兜底:
            # 档位能匹配上 ⇒ 一定有阶梯;有阶梯且没有下一级 ⇒ 才是真的到顶。
            has_ladder = c.get("has_ladder")
            if has_ladder is None:
                has_ladder = c.get("level_order") is not None
            is_top = c.get("is_top")
            if is_top is None:
                is_top = bool(has_ladder and not c.get("next_level"))
            tracked.append({
                "id": sid, "name": site.get("name"), "domain": site.get("domain"),
                "username": usernames.get(site.get("domain") or ""),
                "active": bool(site.get("is_active")),
                "level": c.get("level"), "next_level": c.get("next_level"),
                # 等级名匹配的软硬程度:exact/alias/off_ladder/none… 前端据此标「别名匹配」
                "level_match": c.get("level_match"), "level_alias": c.get("level_alias"),
                "has_ladder": bool(has_ladder), "is_top": bool(is_top),
                "eta_days": c.get("eta_days"), "confidence": c.get("confidence"),
                "manual_blocked": c.get("manual_blocked"), "progress": c.get("progress"),
                # 卡点摘要:全站对比视图直接展示「卡在哪项、当前/目标」,不必进详情页
                "blocker": ({"key": tight.get("key"), "label": tight.get("label"),
                             "current": tight.get("current"),
                             "target": tight.get("target"), "unit": tight.get("unit") or "",
                             "eta_kind": tight.get("eta_kind"),
                             "eta_days": tight.get("eta_days"),
                             "rate_label": tight.get("rate_label")} if tight else None),
                # 没有阶梯的站风险无从判断,标 unknown 而不是 ok —— 一条规则都没读到,
                # 说「正常」是没有依据的断言。
                "risk": ("danger" if any(r.get("level") == "danger" for r in risks)
                         else "warn" if risks
                         else "ok" if has_ladder else "unknown"),
                "risk_text": worst.get("text"),
                "source": c.get("source"), "updated": c.get("l1_updated"),
                "evaluated": bool(c), "error": c.get("error"),
            })
        for sid, site in by_id.items():
            if sid not in wanted:
                candidates.append({"id": sid, "name": site.get("name"),
                                   "domain": site.get("domain"),
                                   "active": bool(site.get("is_active"))})
        return schemas.Response(success=True, data={
            "tracked": tracked, "candidates": candidates,
            "last_refresh": state.get("time"), "snapshot_date": RULES_DATE,
            # 别名表规模:让用户知道「等级名对不上」时插件到底做了多少努力
            "alias_groups": len(ALIAS_GROUPS), "alias_date": ALIAS_DATE})

    def api_detail(self, site_id: int = 0, live: int = 0):
        """单站详情:内存缓存 → level_state 缓存 → 现场评估(顺带回填缓存)。

        三级命中,为的是让「翻看各站点」这件事稳定地快:
        - 第 1 级 _detail_cache:整站评估结果的 TTL 缓存(180s),避免重复读库+落盘;
        - 第 2 级 level_state:上次全量刷新的落盘结果,直接转 payload;
        - 第 3 级 现场评估:只在上面都没有时发生(首次打开某站、或刚点过刷新)。
        live=1 时三级全跳过,强制重抓站点页(给「刷新本站」用)。
        """
        sid = int(site_id or 0)
        if not sid:
            return schemas.Response(success=False, message="缺少 site_id")
        if not live:
            now = time.time()
            with self._detail_lock:
                hit = self._detail_cache.get(sid)
            if hit and now - hit[0] < self._detail_ttl:
                return schemas.Response(success=True, data=hit[1])
            state = self.get_data("level_state") or {}
            for x in (state.get("sites") or []):
                if int(x.get("site_id") or 0) == sid:
                    payload = self.__detail_payload(x)
                    with self._detail_lock:
                        self._detail_cache[sid] = (now, payload)
                    return schemas.Response(success=True, data=payload)
        try:
            site = self.__site_by_id(sid)
            if not site:
                return schemas.Response(success=False, message="站点不存在")
            res = self.__evaluate(site, force_live=bool(live))
            self.__merge_state([res])
            payload = self.__detail_payload(res)
            with self._detail_lock:
                self._detail_cache[sid] = (time.time(), payload)
            return schemas.Response(success=True, data=payload)
        except Exception as e:
            logger.error(f"【站点等级看板】评估站点 {sid} 失败:{e}")
            return schemas.Response(success=False, message=f"评估失败:{e}")

    def api_track(self, payload: TrackPayload):
        """加入看板:新站点**追加到末尾**,已存在的保持原位(顺序由用户拖拽决定)。"""
        ids = self.__tracked_ids()
        add = payload.site_ids or ([payload.site_id] if payload.site_id else [])
        all_ids = {int(x["id"]) for x in self.__sites_all()}
        for x in add:
            if int(x) in all_ids and int(x) not in ids:
                ids.append(int(x))
        self.save_data("tracked", ids)
        return schemas.Response(success=True, message="已加入看板", data={"tracked": ids})

    def api_untrack(self, payload: TrackPayload):
        """移出看板:只摘掉目标站点,其余顺序不动。"""
        ids = self.__tracked_ids()
        drop = payload.site_ids or ([payload.site_id] if payload.site_id else [])
        ids = [x for x in ids if int(x) not in {int(y) for y in drop}]
        self.save_data("tracked", ids)
        return schemas.Response(success=True, message="已移出看板(不影响 mp 站点管理)",
                                data={"tracked": ids})

    def api_reorder(self, payload: ReorderPayload):
        """保存拖拽后的顺序。

        只接受「当前看板站点集合的一个排列」:集合对不上(比如列表已过期、前端拿到的是
        旧数据)就整体忽略并回错误,避免把站点排序写坏或误删。
        mp 里已被删除、但仍留在 tracked 里的 id 不参与排序,原样保留在末尾。
        """
        current = self.__tracked_ids()
        want = [int(x) for x in (payload.site_ids or [])]
        if len(want) != len(set(want)):
            return schemas.Response(success=False, message="排序结果里有重复站点,已忽略")
        known = {int(x["id"]) for x in self.__sites_all()}
        visible = [x for x in current if x in known]
        stale = [x for x in current if x not in known]
        if sorted(want) != sorted(visible):
            return schemas.Response(success=False, message="排序结果与看板站点不一致,已忽略(请刷新后重试)")
        order = want + stale
        self.save_data("tracked", order)
        return schemas.Response(success=True, message="顺序已保存", data={"tracked": order})

    def api_config(self):
        return schemas.Response(success=True, data=self.get_config() or {})

    def api_config_save(self, payload: ConfigPayload):
        """前端配置页保存:与声明式配置共用同一份 config,保存后重新初始化。"""
        try:
            cfg = dict(self.get_config() or {})
            for k, v in payload.model_dump(exclude_none=True).items():
                cfg[k] = v
            from app.api.dependencies.plugin import get_plugin_config_command
            res = get_plugin_config_command().update(self.__class__.__name__, cfg)
            if getattr(res, "success", False):
                return schemas.Response(success=True, message="配置已保存")
            return schemas.Response(success=False,
                                    message="保存失败:%s" % (getattr(res, "message", "") or "未知"))
        except Exception as e:
            logger.error(f"【站点等级看板】保存配置失败:{e}")
            return schemas.Response(success=False, message=f"保存失败:{e}")

    def api_report(self):
        state = self.get_data("level_state") or {}
        return {"success": True, "message": self.__text_overview(state.get("sites") or [])}

    def api_enable(self):
        return self.__set_enabled(True)

    def api_disable(self):
        return self.__set_enabled(False)

    def api_test_notify(self):
        self.__notify_send("站点等级看板·测试通知",
                           "这是一条测试消息,收到即表示通知链路正常。\n发送时间:%s"
                           % datetime.now().strftime("%Y-%m-%d %H:%M:%S"), force=True)
        return {"success": True, "message": "测试通知已发送(已忽略免打扰时段)"}

    def __set_enabled(self, on: bool) -> Dict[str, Any]:
        try:
            from app.api.dependencies.plugin import get_plugin_config_command
            cfg = dict(self.get_config() or {})
            cfg["enabled"] = bool(on)
            res = get_plugin_config_command().update(self.__class__.__name__, cfg)
            if getattr(res, "success", False):
                return {"success": True, "message": "已启用插件" if on else "已禁用插件"}
            return {"success": False, "message": "操作失败:%s" % (getattr(res, "message", "") or "未知")}
        except Exception as e:
            logger.error(f"【站点等级看板】启用/禁用失败:{e}")
            return {"success": False, "message": f"操作失败:{e}"}

    # =====================================================================
    # 主流程
    # =====================================================================
    def run_daily(self, manual: bool = False, force_live: bool = False) -> str:
        if not self._lock.acquire(blocking=False):
            return "上一轮仍在进行中"
        try:
            logger.info("【站点等级看板】开始刷新%s" % ("(强制重抓站点页)" if force_live else ""))
            tracked = set(self.__tracked_ids())
            sites = [s for s in self.__sites_all() if int(s["id"]) in tracked]
            out = []
            for s in sites:
                try:
                    out.append(self.__evaluate(s, force_live=force_live))
                except Exception as e:
                    logger.error(f"【站点等级看板】站点 {s.get('name')} 评估失败:{e}")
                    out.append({"site_id": s["id"], "site_name": s.get("name"), "domain": s.get("domain"),
                                "level": None, "error": str(e), "reqs": [], "risks": [], "source": "error"})
            state = {"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "sites": out}
            self.save_data("level_state", state)
            with self._detail_lock:
                self._detail_cache.clear()      # 全量刷新后详情要从新 state 重取,否则 180s 内看到旧详情
            self.__notify_changes(out, manual)
            logger.info("【站点等级看板】刷新完成:%d 个站点" % len(out))
            return "刷新完成(%d 个站点)" % len(out)
        finally:
            self._lock.release()

    # ---- 单站评估 ---------------------------------------------------------
    def __evaluate(self, site: Dict[str, Any], force_live: bool = False) -> Dict[str, Any]:
        domain, sid = site.get("domain"), int(site.get("id"))
        hist = self.__history(domain, 14)
        cur = hist[-1] if hist else {}
        spec = self.__spec_for(site)

        # 站点页 / 官方 API 的实时值优先:馒头与 PT时间 的**当前等级**以它们为准
        # (siteuserdata 只是 mp 的每日快照,可能落后)
        # force_live=True 时绕过 TTL 缓存(用户点「刷新本站」「刷新全部」时确实重抓)
        live = self.__live_values(site, spec, force=force_live) or {}
        if live:
            self.__record_live(sid, live)          # 站点页取到的值也落盘 → 供斜率用
        live_hist = self.__live_hist(sid)
        level_name = live.get("level") or cur.get("user_level") or ""

        ladder = spec.get("ladder") or []
        matched = self.__resolve_level(ladder, level_name, domain)
        order_now = matched["order"]
        next_level = None
        if order_now is not None:
            for lv in ladder:
                if lv["order"] > order_now:
                    next_level = lv
                    break

        reqs = []
        if next_level:
            reqs = self.__eval_level_reqs(next_level, cur, hist, spec, live, live_hist)

        eta_days, confidence = self.__site_eta(reqs, cur, hist)
        manual_blocked = any(r["eta_kind"] == "manual" and not r["met"] for r in reqs)
        progress = self.__progress(reqs)

        risks = self.__risks(spec, cur, reqs, order_now, ladder, domain, live)
        r = {
            "site_id": sid, "site_name": site.get("name"), "domain": domain,
            "level": level_name, "level_order": order_now,
            # 等级名是怎么对上的 —— 前端要能区分「原文一致」和「靠别名猜的」,
            # 后者要显式标出来让人复核(档位错一级,ETA 全错)
            "level_match": matched["how"],
            "level_alias": matched["matched"] if matched["how"] not in ("exact", "empty") else None,
            "next_level": (next_level or {}).get("name"),
            "next_order": (next_level or {}).get("order"),
            # 「没有下一级」有两种完全不同的原因,前端必须分开说,不能都写成「已最高」:
            #   has_ladder=False → 站点没公开阶梯,下一级**未知**(如 rousi.pro 只给经验值)
            #   is_top=True      → 有阶梯且当前已是最高档,这才是事实上的「已最高」
            "has_ladder": bool(ladder),
            "is_top": bool(ladder) and order_now is not None and next_level is None,
            "eta_days": eta_days, "confidence": confidence,
            "manual_blocked": manual_blocked, "progress": progress,
            "reqs": reqs, "risks": risks,
            "keep_rules": self.__rule_texts(spec.get("keep_rules")),
            "ban_rules": self.__rule_texts(spec.get("ban_rules")),
            "source": spec.get("source"), "snapshot_date": spec.get("snapshot_date"),
            "l1_updated": cur.get("updated_time"),
            "keep": self.__keep_status(ladder, order_now),
            "roadmap": self.__keep_roadmap(ladder, order_now, cur, hist, spec, live, live_hist),
            # 站点侧实时信息(馒头官方 API 给的:最后登录 / 封存 / 警告)—— 白名单,不外带凭据
            "live_extras": {k: live[k] for k in
                            ("parked", "warned", "leech_warn", "last_login", "joined")
                            if k in live},
        }
        return r

    def __eval_level_reqs(self, level: Optional[Dict[str, Any]], cur: Dict[str, Any],
                          hist: List[Dict[str, Any]], spec: Dict[str, Any],
                          live: Dict[str, Any],
                          live_hist: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """评估某一等级的全部晋级条件 —— 「下一级」与「保号路线图」共用同一套口径。"""
        reqs = []
        for r in ((level or {}).get("requirements") or []):
            cur_val = live.get(r["key"], cur.get(r["key"]))
            reqs.append(self.__eval_req(r, cur_val, cur, hist, spec, live_hist))
        return reqs

    def __keep_roadmap(self, ladder: List[Dict[str, Any]], order_now: Optional[int],
                       cur: Dict[str, Any], hist: List[Dict[str, Any]], spec: Dict[str, Any],
                       live: Dict[str, Any],
                       live_hist: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
        """保号路线图:到「可封存保号 / 永久保留」档还差几级、照当前增速要多久、卡在哪一项。

        口径与「下一级 ETA」完全一致(逐条评估目标档的条件 → 取最慢的一项);遇到
        「需人为推动」或数据不足的条件时,ETA 只是**可推算部分**的最快值,单独列出卡点。
        """
        out: Dict[str, Any] = {"parkable": None, "permanent": None}
        if order_now is None:
            return out
        for key, flag in (("parkable", "is_parkable"), ("permanent", "is_permanent")):
            above = next((lv for lv in ladder
                          if lv.get("order", 0) > order_now and lv.get(flag)), None)
            if above is None:
                here = next((lv for lv in ladder
                             if lv.get("order") == order_now and lv.get(flag)), None)
                if here is None:
                    continue          # 该站规则里没有这一档 → 前端不显示
                out[key] = {"reached": True, "order": order_now, "name": here.get("name"),
                            "levels_away": 0, "eta_days": 0.0, "confidence": "high",
                            "blockers": []}
                continue
            reqs = self.__eval_level_reqs(above, cur, hist, spec, live, live_hist)
            eta, conf = self.__site_eta(reqs, cur, hist)
            blockers = [{"label": r["label"], "kind": r["eta_kind"], "current": r.get("current"),
                         "target": r.get("target"), "unit": r.get("unit")}
                        for r in reqs if not r["met"]
                        and (r["eta_kind"] == "manual" or r["eta_days"] is None)]
            out[key] = {"reached": False, "order": above.get("order"), "name": above.get("name"),
                        "levels_away": max(0, int(above.get("order") or 0) - int(order_now)),
                        "eta_days": eta, "confidence": conf, "blockers": blockers}
        return out

    # ---- 单项条件评估 -----------------------------------------------------
    def __eval_req(self, r: Dict[str, Any], cur_val, cur_row: Dict[str, Any],
                   hist: List[Dict[str, Any]], spec: Dict[str, Any],
                   live_hist: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        key, target = r["key"], r["target"]
        unit = r.get("unit", "")
        kind = {"interval": "wait", "download": "manual"}.get(key, "auto")
        out = {"key": key, "target": target, "unit": unit, "label": self.__req_label(r),
               "eta_kind": kind, "current": None, "met": False, "eta_days": None,
               "rate_per_day": None, "rate_label": None}

        if key == "interval":      # 注册时长(周)
            weeks = None
            if isinstance(cur_val, (int, float)):
                weeks = float(cur_val)                 # 站点页直接给了注册周(如 PT时间)
            else:
                join = cur_row.get("join_at")
                if join:
                    try:
                        dt = datetime.strptime(str(join)[:19], "%Y-%m-%d %H:%M:%S")
                        weeks = (datetime.now() - dt).total_seconds() / 86400 / 7
                    except Exception:
                        weeks = None
            out["current"] = round(weeks, 1) if weeks is not None else None
            if weeks is not None:
                out["met"] = weeks >= float(target)
                if not out["met"]:
                    out["eta_days"] = round((float(target) - weeks) * 7, 1)
                    out["rate_label"] = "只等时间"
            return out

        if key in ("ratio",):
            out["current"] = round(float(cur_val), 3) if isinstance(cur_val, (int, float)) else None
        elif key in ("upload", "download", "seeding_size"):
            out["current"] = round(float(cur_val) / GB, 2) if isinstance(cur_val, (int, float)) else None
        else:   # bonus / seeding_bonus / seeding / …
            out["current"] = round(float(cur_val), 1) if isinstance(cur_val, (int, float)) else None

        if out["current"] is None:
            return out
        out["met"] = out["current"] >= float(target)
        if out["met"]:
            return out

        # 斜率(中位数,抗尖峰) → ETA
        # ⚠️ 有些字段(如 PTS 的「做种积分」)不在 siteuserdata 里,而是我们抓站点页得到的
        #    → 那些字段用本地攒的 live_history 算斜率(每次刷新存一条,攒够 3 条即可用)
        if kind == "auto":
            slope = self.__median_slope(hist, key)
            if slope is None and live_hist:
                slope = self.__median_slope(live_hist, key)
            if slope is not None and slope > 0:
                scaled = slope / GB if key in ("upload", "download", "seeding_size") else slope
                out["rate_per_day"] = round(scaled, 2)
                need = float(target) - out["current"]
                days = need / scaled if scaled > 0 else None
                if days is not None and days > 0:
                    out["eta_days"] = round(days, 1)
                    out["rate_label"] = "+%.2f/天" % scaled
            else:
                # slope 为 None = 样本不够;slope <= 0 = 有数据但没在涨(别再笼统写「趋势不足」)
                out["rate_label"] = ("无增长/在下降" if (slope is not None and slope <= 0)
                                     else "趋势不足")
        else:
            out["rate_label"] = "需人为推动"
        return out

    def __site_eta(self, reqs: List[Dict[str, Any]], cur_row, hist) -> Tuple[Optional[float], str]:
        """站点级 ETA:取未达成条件里最慢的一项。

        ⚠️ 只有「所有条件都达成」才返回 0.0;若存在未达成条件但一个都算不出 ETA
        (斜率不足 / 需人为推动),返回 None(未知)—— 早先这里返回 0.0,前端会显示成
        「已达成」,而站点其实还卡着条件(2026-10-11 实测馒头就是这种情况)。
        """
        if not reqs:
            return None, "none"
        unmet = [r for r in reqs if not r["met"]]
        if not unmet:
            return 0.0, ("high" if len(hist) >= 14 else ("mid" if len(hist) >= 3 else "low"))
        if len(hist) < 3:
            return None, "none"
        etas = [r["eta_days"] for r in unmet
                if r["eta_kind"] in ("auto", "wait") and r["eta_days"] is not None]
        if not etas:
            return None, "none"
        return max(etas), ("high" if len(hist) >= 14 else "mid")

    @staticmethod
    def __tightest_req(reqs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """未达成条件里「当前/目标」最小的那个 —— 与 ``__progress`` 同一口径。

        2026-11-22 新增:站点列表要支撑「全站对比」视图,得给每个站一句卡点摘要
        (卡在哪一项、当前/目标多少)。原来这些信息只在 /detail 里,想比较 4 个站
        就得进 4 次详情页,每次 0.3~3 秒。
        ⚠️ 选法必须与 ``__progress`` 一致:同一个站,进度条百分比和卡点文案
        指向的必须是同一项条件,否则用户会觉得数字自相矛盾。
        """
        unmet = [r for r in (reqs or []) if not r.get("met")]
        if not unmet:
            return None
        scored = []
        for r in unmet:
            t, c = r.get("target"), r.get("current")
            if t and isinstance(c, (int, float)):
                scored.append((min(1.0, float(c) / float(t)), r))
        if not scored:
            return unmet[0]
        return min(scored, key=lambda x: x[0])[1]

    @staticmethod
    def __progress(reqs: List[Dict[str, Any]]) -> Optional[float]:
        """按「最紧条件」计进度:取所有条件达成度的最小值。"""
        if not reqs:
            return None
        vals = []
        for r in reqs:
            t, c = r.get("target"), r.get("current")
            if t and isinstance(c, (int, float)):
                vals.append(min(1.0, float(c) / float(t)))
        return round(min(vals), 3) if vals else None

    # ---- 风险 -------------------------------------------------------------
    def __risks(self, spec, cur_row, reqs, order_now, ladder, domain,
                live: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
        risks: List[Dict[str, str]] = []
        live = live or {}
        ratio = cur_row.get("ratio")
        if isinstance(live.get("ratio"), (int, float)):
            ratio = live["ratio"]                      # 站点页/API 的值比每日快照新,优先
        # ① 降级线(下一级的 demote_ratio)
        nxt = None
        if order_now is not None:
            for lv in ladder:
                if lv["order"] > order_now:
                    nxt = lv
                    break
        if nxt and nxt.get("demote_ratio") and isinstance(ratio, (int, float)):
            if ratio < float(nxt["demote_ratio"]):
                risks.append({"level": "danger",
                              "text": "分享率 %.3f < %s 的降级线 %.2f" % (ratio, nxt["name"], nxt["demote_ratio"])})
        # ② 有人为条件挡路
        if any(r["eta_kind"] == "manual" and not r["met"] for r in reqs):
            risks.append({"level": "warn", "text": "有需主动推动的条件(如下载量),光等不会达成"})
        # ③ 站点官方 API 给的账号状态(馒头有:警告 / 吸血警告 / 封存)
        if live.get("warned"):
            risks.append({"level": "danger", "text": "站点已对该账号发出警告(warned),请尽快处理"})
        if live.get("leech_warn"):
            risks.append({"level": "warn", "text": "有下载/吸血相关警告(leechWarn)"})
        if live.get("parked"):
            risks.append({"level": "warn", "text": "账号处于封存(parked)状态,长期不登录仍会被清理"})
        # 注:站点条款原文不在这里堆(否则汇总区一节列 10 条),而是随站点卡单独展示
        return risks

    @staticmethod
    def __rule_texts(items: Any) -> List[str]:
        """规则条目可能是 ``{"text": ...}``(内置快照)或纯字符串(站点页解析 / 手动规则)→ 统一取文本。

        2026-10-12 踩坑:站点页解析返回字符串后,``__evaluate`` 仍按 ``x["text"]`` 取,直接 TypeError,
        整个刷新失败(馒头/PT时间 的「刷新失败:string indices must be integers」就是这个)。
        """
        out: List[str] = []
        for item in (items or []):
            text = item.get("text") if isinstance(item, dict) else item
            if text:
                out.append(str(text))
        return out

    @staticmethod
    def __keep_status(ladder, order_now) -> Dict[str, Any]:
        out = {"parkable_now": False, "levels_to_parkable": None,
               "permanent_now": False, "levels_to_permanent": None}
        if order_now is None:
            return out
        for lv in ladder:
            if lv.get("is_parkable") and out["levels_to_parkable"] is None:
                out["levels_to_parkable"] = max(0, lv["order"] - order_now)
            if lv.get("is_permanent") and out["levels_to_permanent"] is None:
                out["levels_to_permanent"] = max(0, lv["order"] - order_now)
        out["parkable_now"] = out["levels_to_parkable"] == 0
        out["permanent_now"] = out["levels_to_permanent"] == 0
        return out

    # =====================================================================
    # 等级规则:站点页 → 内置快照 → 手动规则
    # =====================================================================
    def __spec_for(self, site: Dict[str, Any]) -> Dict[str, Any]:
        domain = str(site.get("domain") or "").lower()
        sid = int(site.get("id") or 0)
        manual = self.__manual_spec(domain, sid)
        if self._manual_first and manual:
            manual["source"] = "manual"
            return manual

        spec = None
        if self._use_site_page and self._prefer_source == "site_page":
            spec = self.__site_page_spec(site)
        if not spec:
            spec = self.__rules_for(domain, sid)
        if not spec:
            spec = manual or {"source": "l1_only", "ladder": [], "keep_rules": [], "ban_rules": []}
        spec.setdefault("snapshot_date", RULES_DATE)
        return spec

    @staticmethod
    def __rules_for(domain: str, sid: int) -> Optional[Dict[str, Any]]:
        """按域名后缀查规则库;查不到再按 sid 兜底(兼容老配置的站点 ID)。"""
        for cand in _domain_candidates(domain):
            spec = LEVEL_SPECS_BY_DOMAIN.get(cand)
            if spec:
                return dict(spec)
        spec = LEVEL_SPECS.get(sid)
        if spec:
            spec = dict(spec)
            # 站点页拿不到时,快照的来源要如实标注
            if spec.get("source") == "site_page":
                spec["source"] = "ptd_snapshot"
            return spec
        return None

    def __site_page_spec(self, site: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """站点页解析:PTS 用 /faq.php 校验快照,PT时间 用等级校验页**整段重建**阶梯与条款。

        馒头门槛不公开(全站 SPA)→ 继续用内置快照,但当前值走官方 API(见 __live_values)。
        ⚠️ 只按域名判断:发布版不能依赖本地站点 ID(换个人/重建站点库就会错位)。
        """
        domain = str(site.get("domain") or "").lower()
        if "ptskit" in domain:
            return self.__pts_spec(site)
        if "pttime" in domain:
            return self.__pttime_spec(site)
        return None

    def __pts_spec(self, site: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            text = self.__http_get(site, str(site.get("url") or "").rstrip("/") + "/faq.php")
            if not text:
                return None
            # 只做「取到即用」的校验:必须能在同页找到 Power User 的阈值
            if "Power User" not in text or "40000" not in text:
                return None
            logger.info("【站点等级看板】PTS 站点页解析成功,使用站点页规则")
            spec = dict(LEVEL_SPECS[4])
            spec["source"] = "site_page_verified"
            return spec
        except Exception as e:
            logger.warn(f"【站点等级看板】PTS 站点页解析失败,回退内置快照:{e}")
            return None

    def __pttime_spec(self, site: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """PT时间:等级校验页的「等级规则」段逐级列出条件,所以整段重建阶梯(不再用快照)。"""
        try:
            base = str(site.get("url") or "").rstrip("/")
            flat = self.__flatten(self.__http_get(site, base + "/action.php?type=vertify_class"))
            if not flat or "级、" not in flat:
                return None
            ladder = self.__parse_pttime_ladder(flat)
            if len(ladder) < 3:
                logger.warn("【站点等级看板】PT时间等级规则解析到的档位太少,回退内置快照")
                return None
            keep_rules, ban_rules, permanent_name, parkable_name = self.__pttime_rules(site)
            for lv in ladder:
                norm = self.__norm_level(lv["name"])
                lv["is_parkable"] = bool(parkable_name) and norm == parkable_name
                lv["is_permanent"] = bool(permanent_name) and norm == permanent_name
            # 「X 及以上」→ 把标注铺到更高档位(保号档是「及以上」语义)
            for flag, name in (("is_parkable", parkable_name), ("is_permanent", permanent_name)):
                if not name:
                    continue
                hit = next((lv["order"] for lv in ladder if self.__norm_level(lv["name"]) == name), None)
                if hit is not None:
                    for lv in ladder:
                        lv[flag] = lv["order"] >= hit
            logger.info(f"【站点等级看板】PT时间站点页解析成功:{len(ladder)} 档 · "
                        f"可封存档 {parkable_name or '?'} · 永久档 {permanent_name or '?'}")
            return {"source": "site_page_verified", "ladder": ladder,
                    "keep_rules": keep_rules, "ban_rules": ban_rules}
        except Exception as e:
            logger.warn(f"【站点等级看板】PT时间站点页解析失败,回退内置快照:{e}")
            return None

    def __parse_pttime_ladder(self, flat: str) -> List[Dict[str, Any]]:
        """从 PT时间 等级校验页抽逐级条件:``2级、Power User(小学) 注册至少4周,且下载至少512G,且分享率大于1.05。``"""
        header = re.compile(r"(\d+)级、\s*([A-Za-z][A-Za-z ]*?)\s*[（(]([^）)]*)[）)]\s*[:：]?")
        hits = list(header.finditer(flat))
        segments: Dict[int, str] = {}
        for idx, hit in enumerate(hits):
            order = int(hit.group(1))
            end = hits[idx + 1].start() if idx + 1 < len(hits) else min(len(flat), hit.end() + 400)
            # 同一档可能出现在「升级提醒」与「等级规则」两处 → 取靠后的(等级规则段更全)
            segments[order] = flat[hit.end():end]
        ladder: List[Dict[str, Any]] = []
        for order, seg in sorted(segments.items()):
            if order < 1 or order > 9:          # 0 档是降级/封禁档,10 档是捐赠贵宾 → 不进阶梯
                continue
            label = next((h.group(2).strip() for h in hits if int(h.group(1)) == order), "")
            if order == 1:
                # 1 档是「注册默认等级」;页面上那串「下载超 X、分享率高于 Y」是**无流量保护**的分档说明,
                # 不是晋级条件 —— 收进备注,别拿它当 requirement(否则会误导进度与 ETA)
                note = "注册默认等级"
                if "下载量小于100G" in flat:
                    note += ";下载量 < 100G 不参与升降级"
                ladder.append({"order": order, "name": label or "User", "requirements": [],
                               "demote_ratio": None, "privilege": note,
                               "is_parkable": False, "is_permanent": False})
                continue
            requirements: List[Dict[str, Any]] = []
            m = re.search(r"注册至少\s*(\d+)\s*周", seg)
            if m:
                requirements.append({"key": "interval", "target": float(m.group(1)), "unit": "周"})
            m = re.search(r"下载(?:至少|超)\s*(\d+(?:\.\d+)?)\s*([KMGT])?", seg)
            if m:
                scale = SIZE_UNITS.get((m.group(2) or "G").upper(), GB)
                requirements.append({"key": "download",
                                     "target": round(float(m.group(1)) * scale / GB),
                                     "unit": "GB"})
            m = re.search(r"分享率(?:大于|高于)\s*([\d.]+)", seg)
            if m:
                requirements.append({"key": "ratio", "target": float(m.group(1)), "unit": ""})
            m = re.search(r"分享率低于\s*([\d.]+)\s*[,，]\s*将自动降级", seg)
            demote = float(m.group(1)) if m else None
            m = re.search(r"获得\s*(\d+)\s*个邀请名额", seg)
            ladder.append({
                "order": order, "name": label or f"等级 {order}",
                "requirements": requirements, "demote_ratio": demote,
                "privilege": (f"升级奖励 {m.group(1)} 个邀请名额" if m else None),
                "is_parkable": False, "is_permanent": False,
            })
        return ladder

    def __pttime_rules(self, site: Dict[str, Any]) -> Tuple[List[str], List[str], str, str]:
        """PT时间 /rules.php:账号保留规则(含「X 及以上」保号档)+ 封号条款。"""
        base = str(site.get("url") or "").rstrip("/")
        return self.__parse_pttime_rules(self.__flatten(self.__http_get(site, base + "/rules.php")))

    @staticmethod
    def __parse_pttime_rules(flat: str) -> Tuple[List[str], List[str], str, str]:
        """把 /rules.php 的纯文本切成:保号条款 / 封号条款 / 永久保留档 / 可封存档。"""
        keep_rules: List[str] = []
        ban_rules: List[str] = []
        permanent_name, parkable_name = "", ""
        if not flat:
            return keep_rules, ban_rules, permanent_name, parkable_name
        section = ""
        if "账号保留规则" in flat:
            start = flat.find("账号保留规则")
            section = flat[start:start + 900]
        for item in re.findall(r"\d+\.\s*([^;；。]{4,80})", section):
            text = re.sub(r"\s+", " ", item).strip()
            if not text or "保留规则" in text:
                continue
            keep_rules.append(text)
            m = re.search(r"([A-Za-z][A-Za-z ]*?)\s*及以上等级用户会永远保留", text)
            if m:
                permanent_name = SiteLevelBoard.__norm_level(m.group(1))
            m = re.search(r"([A-Za-z][A-Za-z ]*?)\s*及以上等级用户封存账号", text)
            if m:
                parkable_name = SiteLevelBoard.__norm_level(m.group(1))
        if "一切作弊" in flat:
            start = flat.find("一切作弊")
            tail = flat[start:start + 400]
            for sentence in re.split(r"[。!！]", tail):
                text = re.sub(r"\s+", " ", sentence).strip()
                if len(text) >= 4 and any(k in text for k in ("作弊", "禁止", "被封", "上传到其他")):
                    ban_rules.append(text)
        return keep_rules, ban_rules, permanent_name, parkable_name

    # ---- 手动规则解析 -----------------------------------------------------
    def __manual_spec(self, domain: str, sid: int) -> Optional[Dict[str, Any]]:
        """每行 ``域名或站点ID | 等级名 | 条件表达式``。

        推荐写域名(如 ``m-team.cc | Power User | 下载>=200``),发布版不再依赖本地
        站点 ID;纯数字的第一段仍按站点 ID 匹配,兼容老配置。
        """
        if not self._manual_rules:
            return None
        cands = set(_domain_candidates(domain))
        ladder = []
        for raw in self._manual_rules.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = [x.strip() for x in line.split("|")]
            if len(parts) < 3:
                continue
            head = parts[0]
            if head.isdigit():
                if int(head) != sid:
                    continue
            else:
                key = head.lower().lstrip("*.")     # 允许写 *.m-team.cc
                if key not in cands and key not in str(domain or "").lower():
                    continue
            _, name, expr = parts[0], parts[1], parts[2]
            reqs = []
            for m in re.finditer(r"([\u4e00-\u9fa5A-Za-z_]+)\s*(>=|>)\s*([\d.]+)", expr):
                key_cn, op, val = m.group(1), m.group(2), float(m.group(3))
                key = {"经验": "bonus", "上传": "upload", "下载": "download", "分享率": "ratio",
                       "魔力": "bonus", "积分": "seeding_bonus", "做种": "seeding"}.get(key_cn, key_cn)
                reqs.append({"key": key, "target": val, "unit": ""})
            if reqs:
                ladder.append({"order": len(ladder) + 1, "name": name, "requirements": reqs})
        if not ladder:
            return None
        return {"source": "manual", "ladder": ladder, "keep_rules": [], "ban_rules": []}

    # =====================================================================
    # 看板站点管理(前端左侧列表 + 增删)
    # =====================================================================
    def __tracked_ids(self) -> List[int]:
        """看板要展示的站点。未配置过 → 默认=全部 mp 绑定站点(开箱可用)。"""
        vals = self.get_data("tracked")
        if vals is None:
            return [int(x["id"]) for x in self.__sites_all()]
        try:
            return [int(x) for x in vals]
        except Exception:
            return []

    def __site_by_id(self, sid: int) -> Optional[Dict[str, Any]]:
        for x in self.__sites_all():
            if int(x["id"]) == int(sid):
                return x
        return None

    def __merge_state(self, results: List[Dict[str, Any]]):
        """把单站评估结果并回 level_state(保持其它站点不变)。"""
        state = self.get_data("level_state") or {"time": None, "sites": []}
        sites = [x for x in (state.get("sites") or []) if int(x.get("site_id") or 0) not in
                 {int(r.get("site_id") or 0) for r in results}]
        sites.extend(results)
        sites.sort(key=lambda x: int(x.get("site_id") or 0))
        state["sites"] = sites
        state["time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.save_data("level_state", state)

    def __detail_payload(self, r: Dict[str, Any]) -> Dict[str, Any]:
        """给前端的单站详情:评估结果 + 完整阶梯 + 最近历史(供画时间线)。"""
        sid = int(r.get("site_id") or 0)
        site = self.__site_by_id(sid) or {}
        spec = self.__spec_for(site)
        ladder = []
        for lv in (spec.get("ladder") or []):
            ladder.append({
                "order": lv.get("order"), "name": lv.get("name"),
                "is_permanent": bool(lv.get("is_permanent")),
                "is_parkable": bool(lv.get("is_parkable")),
                "privilege": lv.get("privilege"),
                "demote_ratio": lv.get("demote_ratio"),
                "requirements": [{"label": self.__req_label(x), "target": x.get("target"),
                                  "unit": x.get("unit", "")} for x in (lv.get("requirements") or [])],
            })
        hist = []
        for h in self.__history(r.get("domain") or "", 30):
            hist.append({
                "day": str(h.get("updated_day") or h.get("updated_time") or "")[:10],
                "upload_gb": round((h.get("upload") or 0) / GB, 2),
                "download_gb": round((h.get("download") or 0) / GB, 2),
                "ratio": h.get("ratio"), "bonus": h.get("bonus"),
                "seeding": h.get("seeding"),
                "seeding_size_gb": round((h.get("seeding_size") or 0) / GB, 2),
            })
        return {**r,
                # 老缓存没有这两个字段(本次升级前评估的结果):按 spec 现算一遍,
                # 免得「到顶了」在详情里退化成一概「未知」。
                "has_ladder": (r.get("has_ladder") if r.get("has_ladder") is not None
                               else bool(spec.get("ladder"))),
                "is_top": (r.get("is_top") if r.get("is_top") is not None
                           else bool(spec.get("ladder")) and r.get("level_order") is not None
                                and not r.get("next_level")),
                "ladder": ladder, "history": hist,
                # progress 为 None = 不知道(Rousi 这类没阶梯的站),不能兜成 0 ——
                # 0% 会被读成「一条都没达成」,是句假话。
                "progress_pct": (None if r.get("progress") is None
                                 else round(r.get("progress") * 100)),
                "site_url": site.get("url"), "domain": site.get("domain")}

    # =====================================================================
    # L1 数据(直读 mp 自身库;siteuserdata 是每日快照历史)
    # =====================================================================
    @staticmethod
    def __conn():
        con = sqlite3.connect("file:%s?mode=ro" % DB_PATH, uri=True)
        con.row_factory = sqlite3.Row
        return con

    def __sites_all(self) -> List[Dict[str, Any]]:
        try:
            con = self.__conn()
            rows = [dict(r) for r in con.execute(
                "select id,name,domain,url,is_active,proxy,apikey from site order by id")]
            con.close()
            return rows
        except Exception as e:
            logger.error(f"【站点等级看板】读取站点列表失败:{e}")
            return []

    def __usernames(self) -> Dict[str, str]:
        """各站点的**账号名**(mp 抓站点时记在 siteuserdata.username)。

        每一行都是 mp 在某天抓到的快照,故按 domain 取 id 最大(最新)的那行。
        取不到不报错 —— 只影响前端显示一个名字。
        """
        try:
            con = self.__conn()
            rows = con.execute(
                "select s.domain, s.username from siteuserdata s "
                "where s.username is not null and s.username != '' "
                "and s.id = (select max(s2.id) from siteuserdata s2 where s2.domain = s.domain)").fetchall()
            con.close()
            return {r["domain"]: r["username"] for r in rows}
        except Exception as e:
            logger.warn(f"【站点等级看板】读取站点账号名失败:{e}")
            return {}

    def __history(self, domain: str, limit: int = 14) -> List[Dict[str, Any]]:
        try:
            con = self.__conn()
            rows = [dict(r) for r in con.execute(
                "select * from siteuserdata where domain=? order by id desc limit ?",
                (domain, limit))]
            con.close()
            return list(reversed(rows))
        except Exception as e:
            logger.warn(f"【站点等级看板】读取站点数据失败({domain}):{e}")
            return []

    def __record_live(self, sid: int, live: Dict[str, Any]):
        """把站点页取到的当前值落盘成历史(供斜率/ETA 用 —— siteuserdata 没有这些字段)。

        ⚠️ 口径版本:每条样本都带 ``v``。读到 ``v`` 与当前 ``LIVE_SCHEMA_VERSION`` 不一致的
        站点时**整段丢弃**——老解析器写进去的坏值(做种积分被逗号截断成 59、缺
        upload/download)混在新样本里会把中位数斜率彻底带偏,留着比不留更糟。
        """
        try:
            all_live = self.get_data("live_history") or {}
            arr = list(all_live.get(str(sid)) or [])
            # 口径升级:老版本样本整段作废
            if arr and any(e.get("v") != LIVE_SCHEMA_VERSION for e in arr):
                dropped = len([e for e in arr if e.get("v") != LIVE_SCHEMA_VERSION])
                logger.info(f"【站点等级看板】站点 {sid} 的 live_history 口径升级"
                            f"(v→{LIVE_SCHEMA_VERSION}),丢弃 {dropped} 条旧样本重新积累")
                arr = []
            now = datetime.now()
            row = {"updated_day": now.strftime("%Y-%m-%d"),
                   "updated_time": now.strftime("%Y-%m-%d %H:%M:%S"),
                   "v": LIVE_SCHEMA_VERSION}
            row.update({k: v for k, v in live.items() if isinstance(v, (int, float))})
            if arr and arr[-1].get("updated_day") == row["updated_day"]:
                arr[-1] = row            # 同一天只留最后一条,避免日内样本淹没日粒度
            else:
                arr.append(row)
            all_live[str(sid)] = arr[-288:]
            self.save_data("live_history", all_live)
        except Exception as e:
            logger.warn(f"【站点等级看板】记录 live_history 失败:{e}")

    def __live_hist(self, sid: int) -> List[Dict[str, Any]]:
        """读 live_history;口径不符的旧样本一律不参与斜率计算。"""
        try:
            arr = list((self.get_data("live_history") or {}).get(str(sid)) or [])
        except Exception:
            return []
        return [e for e in arr if e.get("v") == LIVE_SCHEMA_VERSION]

    # ---- 站点页 / 官方 API 取当前值 ---------------------------------------
    def __live_values(self, site: Dict[str, Any], spec: Dict[str, Any], force: bool = False) -> Dict[str, Any]:
        """取「权威当前值」:PTS 顶栏、馒头官方 API、PT时间 等级校验页 —— 带内存 TTL 缓存。

        为什么缓存:这几步是**真的去抓公网站点页**(实测 0.35~1.05s/站),而 /detail
        与后台刷新会反复走到这里。看板判定粒度是「日」,几分钟内重复抓同一份实时值
        没有意义,只会把首屏拖慢(首屏 3 个站点实测合计 1.48s → 命中缓存后为毫秒级)。

        force=True 时绕过缓存(手动刷新/全量刷新用,保证「我要最新」时确实重抓)。
        取不到就返回 {},调用方一律回落到 mp 的 siteuserdata(站点改版也不会把看板搞崩)。
        """
        if not self._use_site_page:
            return {}
        sid = int(site.get("id") or 0)
        now = time.time()
        if not force and sid:
            with self._live_lock:
                hit = self._live_cache.get(sid)
            if hit:
                ts, ttl, val = hit
                if now - ts < ttl:
                    return dict(val)
        val = self.__fetch_live(site)
        if sid:
            ttl = self._live_ttl if val else 60      # 失败只短缓存,避免坏网络反复重试
            with self._live_lock:
                self._live_cache[sid] = (now, ttl, dict(val))
        return val

    def __fetch_live(self, site: Dict[str, Any]) -> Dict[str, Any]:
        """真正去抓站点页/官方 API(不查缓存)。"""
        domain = str(site.get("domain") or "").lower()
        try:
            if "ptskit" in domain:
                return self.__live_pts(site)
            if "m-team" in domain:
                return self.__live_mteam(site)
            if "pttime" in domain:
                return self.__live_pttime(site)
        except Exception as e:
            logger.warn(f"【站点等级看板】读取 {site.get('name')} 站点页/API 失败(回落 siteuserdata):{e}")
        return {}

    @staticmethod
    def __flatten(html: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "").replace("&nbsp;", " "))

    # ⚠️ 千分位:站点顶栏是 `做种积分 59,674`、`魔力值 [ 使用 ]: 139,569.1`,
    #    老正则 `([\d.]+)` 遇到逗号只吃到 `59` → 做种积分被读成 59 分,
    #    「下一级 ETA」算成还要 19971 天(2026-11-09 实测)。
    #    → 统一用 NUM 允许千分位,取值时再去逗号。
    _PTS_NUM = r"(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)"

    def __live_pts(self, site: Dict[str, Any]) -> Dict[str, Any]:
        """PTS(ptskit)顶栏一行给全部关键值:
        `分享率: 37.424 上传量: 1.828 TB 下载量: 50.02 GB 做种积分 59,674 当前活动: 394 0 ...`

        ⚠️ 老实现只解析了 ratio / seeding_bonus / bonus 三个,`upload` / `download` /
        `seeding` 全缺 → 走 `live.get(key, cur.get(key))` 回落到 siteuserdata 的陈旧值
        (download 停在 0.78GB,实际已 50.02GB),于是「下载量>50GB」永远判不达成、
        eta_kind=manual 直接把整站 ETA 打成未知。现在把这三个一并解析。
        """
        text = self.__http_get(site, str(site.get("url") or "").rstrip("/") + "/index.php")
        if not text:
            return {}
        flat = self.__flatten(text)
        out: Dict[str, Any] = {}
        num = self._PTS_NUM

        def grab(key: str, pat: str, scale: Optional[float] = None):
            m = re.search(pat, flat)
            if not m:
                return
            try:
                v = float(m.group(1).replace(",", ""))
            except (TypeError, ValueError):
                return
            out[key] = v * scale if scale else v

        # 顶栏:`上传量: 1.828 TB` / `下载量: 50.02 GB`(带单位,乘成字节)
        for key, label in (("upload", "上传量"), ("download", "下载量")):
            m = re.search(label + r"[:：]\s*" + num + r"\s*([KMGT])(?:B)?\b", flat)
            if m:
                try:
                    out[key] = float(m.group(1).replace(",", "")) * SIZE_UNITS.get(m.group(2).upper(), 1)
                except (TypeError, ValueError):
                    pass
        grab("seeding_bonus", r"做种积分\s*" + num)
        grab("ratio", r"分享率[:：]\s*" + num)
        grab("bonus", r"魔力值\s*\[\s*使用\s*\]\s*[:：]\s*" + num)
        # `当前活动: 394 0` = 做种数 / 下载数
        m = re.search(r"当前活动[:：]\s*(\d+)\s+(\d+)", flat)
        if m:
            out["seeding"] = float(m.group(1))
            out["leeching"] = float(m.group(2))
        return out

    def __live_mteam(self, site: Dict[str, Any]) -> Dict[str, Any]:
        """馒头官方 API(apikey 只能访问 profile;等级/门槛类端点要用户级 JWT,拿不到)。

        ⚠️ 必须发 JSON 体 `{}` —— 空 body 会回 `code:1 請求參數錯誤`(2026-10-11 实测)。
        """
        key = str(site.get("apikey") or "").strip()
        if not key:
            logger.warn("【站点等级看板】馒头未配置 apikey,跳过官方 API(回落 siteuserdata)")
            return {}
        payload = self.__http_post_json(site, "https://api.m-team.cc/api/member/profile", {},
                                       {"x-api-key": key})
        data = (payload or {}).get("data") or {}
        if not data:
            logger.warn(f"【站点等级看板】馒头 API 无 data:{(payload or {}).get('message')}")
            return {}
        out: Dict[str, Any] = {}
        role = str(data.get("role") or "")
        if role:
            out["level"] = MROLE_NAMES.get(role, f"角色 {role}")
        out["parked"] = bool(data.get("parked"))
        count = data.get("memberCount") or {}
        for src_key, dst_key in (("uploaded", "upload"), ("downloaded", "download")):
            raw = count.get(src_key)
            if raw not in (None, ""):
                out[dst_key] = float(raw)              # 字节
        if count.get("shareRate") not in (None, ""):
            out["ratio"] = float(count["shareRate"])
        if count.get("bonus") not in (None, ""):
            out["bonus"] = float(count["bonus"])
        if data.get("seedtime") not in (None, ""):
            out["seedtime_hours"] = round(float(data["seedtime"]) / 3600, 1)
        status = data.get("memberStatus") or {}
        for flag, dst in (("warned", "warned"), ("leechWarn", "leech_warn")):
            if status.get(flag):
                out[dst] = True
        if status.get("createdDate"):
            out["joined"] = status["createdDate"]
        if status.get("lastLogin"):
            out["last_login"] = status["lastLogin"]
        # 注:MT 的 seedtime(2791701187)单位不明(按秒算是 88 年),mp 自己也不换算 → 不展示、不参与判据
        logger.info(f"【站点等级看板】馒头 API 成功:等级 {out.get('level')}(role {role})"
                    f"{'、封存中' if out.get('parked') else ''}"
                    f"{'、有警告' if out.get('warned') else ''}")
        return out

    def __live_pttime(self, site: Dict[str, Any]) -> Dict[str, Any]:
        """PT时间等级校验页:同一页给出「目前等级应为」与 注册周/下载量/分享率/上传量。"""
        url = str(site.get("url") or "").rstrip("/") + "/action.php?type=vertify_class"
        html = self.__http_get(site, url)
        if not html:
            return {}
        flat = self.__flatten(html)
        out: Dict[str, Any] = {}
        m = re.search(r"目前等级应为[:：]\s*(?:[（(][^）)]*[）)]\s*)?([A-Za-z][A-Za-z ]*)", flat)
        if m:
            out["level"] = m.group(1).strip()
        m = re.search(r"注册周[:：]\s*([\d.]+)\s*周", flat)
        if m:
            out["interval"] = float(m.group(1))     # 与阶梯里 interval 条件的口径一致(周)
        m = re.search(r"注册于\s*(\d{4}-\d{2}-\d{2})", flat)
        if m:
            out["joined"] = m.group(1)
        for label, key in (("下载量", "download"), ("上传量", "upload")):
            m = re.search(label + r"[:：]\s*([\d.]+)\s*([KMGT])", flat)
            if m:
                out[key] = float(m.group(1)) * SIZE_UNITS.get(m.group(2).upper(), 1)
        m = re.search(r"分享率[:：]\s*([\d.]+)", flat)
        if m:
            out["ratio"] = float(m.group(1))
        if out:
            logger.info(f"【站点等级看板】PT时间等级校验页成功:等级 {out.get('level')}")
        return out

    def __http_get(self, site: Dict[str, Any], url: str) -> str:
        return self.__http_request(site, url, "GET")

    def __http_post_json(self, site: Dict[str, Any], url: str, payload: Dict[str, Any],
                         extra_headers: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
        text = self.__http_request(site, url, "POST", json_body=payload, extra_headers=extra_headers)
        if not text:
            return None
        try:
            return json.loads(text)
        except ValueError:
            logger.warn(f"【站点等级看板】{site.get('name')} 返回的不是 JSON:{text[:120]}")
            return None

    def __http_request(self, site: Dict[str, Any], url: str, method: str = "GET",
                       json_body: Optional[Dict[str, Any]] = None,
                       extra_headers: Optional[Dict[str, str]] = None) -> str:
        con = self.__conn()
        row = con.execute("select cookie,ua,proxy,render,timeout from site where id=?",
                          (int(site["id"]),)).fetchone()
        con.close()
        if not row:
            return ""
        headers = {"User-Agent": row["ua"] or "Mozilla/5.0"}
        if extra_headers:
            headers.update(extra_headers)
        ck = dict(x.split("=", 1) for x in str(row["cookie"]).split("; ") if "=" in x)
        # 带自定义头的调用 = 官方 API(靠 apikey 认证,域名也不同),不带站点 cookie
        if not ck and not extra_headers:
            return ""
        proxies = None
        if row["proxy"]:
            try:
                from app.core.config import settings
                proxies = settings.PROXY or None       # ⚠️ settings.PROXY 已是 dict
            except Exception:
                proxies = None
        kwargs: Dict[str, Any] = {"headers": headers, "proxies": proxies,
                                  "timeout": int(row["timeout"] or self._timeout)}
        if ck and not extra_headers:
            kwargs["cookies"] = ck
        if method == "POST":
            headers.setdefault("Content-Type", "application/json")
            response = requests.post(url, json=json_body if json_body is not None else {}, **kwargs)
        else:
            response = requests.get(url, **kwargs)
        return response.text if response.status_code == 200 else ""

    # =====================================================================
    # 等级匹配 / 斜率
    # =====================================================================
    @staticmethod
    def __norm_level(name: str) -> str:
        """等级名归一化(去括号注释 + 压空白 + 小写),与模块级 ``_norm_name`` 同一口径。"""
        return _norm_name(name)

    def __user_alias(self, domain: str, level_name: str) -> Optional[str]:
        """配置里「域名|站点显示名|规则库等级名」的映射优先于内置别名表。

        内置表只敢收「高置信度等价」;具体某个站的怪写法由用户自己补,这才是
        发布版该有的样子 —— 不能指望作者预判 290 个站的全部写法。
        """
        table = getattr(self, "_level_alias_map", None)
        if not table:
            return None
        key = _norm_name(level_name)
        for cand in _domain_candidates(domain):
            hit = table.get(cand)
            if hit and key in hit:
                return hit[key]
        return None

    def __resolve_level(self, ladder: List[Dict[str, Any]], level_name: str,
                        domain: str = "") -> Dict[str, Any]:
        """把「站点显示的等级名」解析成阶梯里的档位。

        返回 ``{"order", "how", "matched"}``,``how`` 说明这次匹配有多硬:
          exact       原文一致(最可信)
          compact     只差空格/大小写(PowerUser / POWER USER)
          alias       靠括号别名 / 中英混排 / 别名组对上(如「贵宾」→ VIP)
          user_alias  靠配置里的手动别名对上
          ambiguous   别名组在该站阶梯里命中多档 → **不猜**
          off_ladder  认得出是哪一档,但这站阶梯里没有这一档(如 PTS 的「贵宾」)
          none        完全对不上
          empty       站点没给等级名
        分阶段是刻意的:能精确就不猜,能靠别名就不做模糊包含 —— 档位错一级,ETA 全错。
        """
        name = str(level_name or "").strip()
        if not name:
            return {"order": None, "how": "empty", "matched": None}
        if not ladder:
            return {"order": None, "how": "none", "matched": None}

        override = self.__user_alias(domain, name)
        if override:
            name = override

        target = _norm_name(name)
        target_compact = target.replace(" ", "")
        target_ascii = _ascii_name(name).replace(" ", "")
        target_keys = _expand_groups(_name_keys(name))
        target_residual = _norm_name(_ORDINAL_RE.sub("", target)) or target
        entries = [(lv, _expand_groups(_name_keys(lv.get("name")))) for lv in ladder]

        def hit(lv: Dict[str, Any], how: str) -> Dict[str, Any]:
            return {"order": lv.get("order"),
                    "how": "user_alias" if override else how,
                    "matched": lv.get("name")}

        # 1) 原文一致
        for lv, _ in entries:
            if _norm_name(lv.get("name")) == target:
                return hit(lv, "exact")

        # 2) 只差空格/大小写(PowerUser / POWER USER)—— 这才是真正的「同一串字符」
        if target_compact:
            same = [lv for lv, _ in entries
                    if _norm_name(lv.get("name")).replace(" ", "") == target_compact]
            if len(same) == 1:
                return hit(same[0], "compact")

        # 3) 只留 ASCII 后一致 —— 穿透「憨头憨脑 User」「满面娇憨 Nexus Master」
        #    ⚠️ 与 2) 必须分开:这一档已经**丢掉了中文信息**,属于推断,不是同一串字符。
        if target_ascii:
            same = [lv for lv, _ in entries
                    if _ascii_name(lv.get("name")).replace(" ", "") == target_ascii]
            if len(same) == 1:
                return hit(same[0], "alias")

        # 4) 别名:括号别名 / 等价组(中文名、缩写)
        scored: List[Tuple[Dict[str, Any], int]] = []
        for lv, keys in entries:
            common = target_keys & keys
            if common:
                scored.append((lv, max(len(k) for k in common)))
        if scored:
            best = max(score for _, score in scored)
            top = [lv for lv, score in scored if score == best]
            if len(top) == 1:
                return hit(top[0], "alias")
            return {"order": None, "how": "ambiguous", "matched": None}

        # 5) 去掉「Lv.3」「3级」这类序号前缀后再比(节气/修仙主题站常见)。
        #    序号可能长在站点显示名上,也可能长在规则库的档位名上,两边都要剥。
        for lv, _ in entries:
            lv_norm = _norm_name(lv.get("name"))
            lv_residual = _norm_name(_ORDINAL_RE.sub("", lv_norm)) or lv_norm
            if not target_residual or target_residual != lv_residual:
                continue
            if target_residual == target and lv_residual == lv_norm:
                continue            # 两边都没剥掉东西 = 上面几级已经比过了
            return hit(lv, "alias")

        # 6) 认得出是哪一档,但这站阶梯里没这一档 —— 比「未知」多说一句实话
        for key in target_keys:
            gid = ALIAS_INDEX.get(key)
            if gid is not None:
                return {"order": None, "how": "off_ladder", "matched": ALIAS_CANONICAL[gid]}

        return {"order": None, "how": "none", "matched": None}

    @staticmethod
    def __median_slope(hist: List[Dict[str, Any]], key: str) -> Optional[float]:
        """用相邻样本的日增量的中位数当斜率(抗尖峰)。"""
        if len(hist) < 3:
            return None
        deltas = []
        for a, b in zip(hist, hist[1:]):
            va, vb = a.get(key), b.get(key)
            if not isinstance(va, (int, float)) or not isinstance(vb, (int, float)):
                continue
            try:
                ta = datetime.fromisoformat(str(a.get("updated_day") or a.get("updated_time")).replace(" ", "T"))
                tb = datetime.fromisoformat(str(b.get("updated_day") or b.get("updated_time")).replace(" ", "T"))
            except Exception:
                continue
            days = (tb - ta).total_seconds() / 86400
            if days > 0:
                deltas.append((vb - va) / days)
        if not deltas:
            return None
        deltas.sort()
        mid = deltas[len(deltas) // 2]
        return mid if mid > 0 else None

    # =====================================================================
    # 文本渲染(全部走 props.text / 顶层 text,已在真实页面验证过可渲染)
    # =====================================================================
    def __text_status(self, state: Dict[str, Any]) -> str:
        if not state:
            return "尚未刷新过 —— 点下方「立即刷新」开始(首次约 10~60 秒)"
        return "上次刷新:%s | 站点 %d 个 | 内置快照日期:%s" % (
            state.get("time") or "-", len(state.get("sites") or []), RULES_DATE)

    def __text_overview(self, sites: List[Dict[str, Any]]) -> str:
        if not sites:
            return "暂无数据,请先「立即刷新」。"
        rows = ["%-10s %-13s %-13s %-22s %-14s %s" % ("站点", "当前等级", "下一级", "最紧条件", "ETA", "红线")]
        rows.append("-" * 96)
        for s in sites:
            if s.get("error"):
                rows.append("%-10s %s" % (s.get("site_name", "?"), "评估失败:%s" % s["error"]))
                continue
            reqs = [r for r in (s.get("reqs") or []) if not r["met"]]
            if reqs:
                # 「最紧」= ETA 最大者;没有 ETA 的排后面
                reqs.sort(key=lambda r: (r["eta_days"] is None, -(r["eta_days"] or 0)))
                tight = "%s %s/%s" % (reqs[0]["label"], self.__fmt(reqs[0]["current"]), self.__fmt(reqs[0]["target"]))
            else:
                tight = "已全部达成" if s.get("next_level") else "—"
            eta = "未知"
            if s.get("manual_blocked"):
                eta = "受人为条件限制"
            elif s.get("eta_days") is not None:
                eta = "~%.0f 天(%s)" % (s["eta_days"], {"high": "高", "mid": "中", "low": "低"}.get(s["confidence"], "?"))
            elif s.get("next_level"):
                eta = "无法估算"
            risk = "⛔" if any(r["level"] == "danger" for r in (s.get("risks") or [])) else (
                "⚠️" if s.get("risks") else "✅")
            name = str(s.get("site_name") or "")[:9]
            rows.append("%-10s %-13s %-13s %-22s %-14s %s" % (
                name, str(s.get("level") or "?")[:12], str(s.get("next_level") or "—")[:12], tight[:22], eta, risk))
        rows.append("")
        rows.append("红线 = ⛔ 有硬风险 / ⚠️ 有提示 / ✅ 无;「受人为条件限制」= 有需主动推动的条件(如下载量)。")
        return "\n".join(rows)

    def __text_detail(self, s: Dict[str, Any]) -> str:
        if s.get("error"):
            return "评估失败:%s" % s["error"]
        lines = []
        lines.append("当前等级:%s   下一级:%s" % (s.get("level") or "?", s.get("next_level") or "已是最高/未知"))
        p = s.get("progress")
        if p is not None:
            bar = "▓" * int(round(p * 20)) + "░" * (20 - int(round(p * 20)))
            lines.append("晋级进度:%s %d%%(按最紧条件计)" % (bar, round(p * 100)))
        reqs = s.get("reqs") or []
        if reqs:
            lines.append("")
            lines.append("下一级条件(%d 项,已达成 %d 项):" % (len(reqs), sum(1 for r in reqs if r["met"])))
            for r in reqs:
                mark = "✅" if r["met"] else "❌"
                seg = "%s %-14s 要求 %s%s  当前 %s" % (
                    mark, r["label"], self.__fmt(r["target"]), (" " + r["unit"]) if r["unit"] else "",
                    self.__fmt(r["current"]) if r["current"] is not None else "取不到")
                if not r["met"]:
                    if r["eta_days"] is not None:
                        seg += "   (%s → 约 %.0f 天)" % (r.get("rate_label") or "", r["eta_days"])
                    elif r.get("rate_label"):
                        seg += "   (%s)" % r["rate_label"]
                lines.append("  " + seg)
        elif s.get("next_level"):
            lines.append("(该站等级规则不可得 —— 站点未公开门槛,可用手动规则补)")

        keep = s.get("keep") or {}
        lines.append("")
        lines.append("保号状态:")
        lines.append("  · 可封存保号:%s" % ("✅ 已达" if keep.get("parkable_now")
                                        else ("还差 %s 级" % keep.get("levels_to_parkable")
                                              if keep.get("levels_to_parkable") is not None else "未知")))
        lines.append("  · 永久保留:%s" % ("✅ 已达" if keep.get("permanent_now")
                                       else ("还差 %s 级" % keep.get("levels_to_permanent")
                                             if keep.get("levels_to_permanent") is not None else "未知")))
        kr, br = s.get("keep_rules") or [], s.get("ban_rules") or []
        if kr or br:
            lines.append("")
            lines.append("保号 / 封号条款(站点原文):")
            for t in kr:
                lines.append("  ✅ " + t)
            for t in br:
                lines.append("  ⛔ " + t)
        for r in (s.get("risks") or []):
            if r["level"] == "danger":
                lines.append("  🔴 当前已触发:" + r["text"])
        lines.append("  · 数据来源:%s%s | siteuserdata 更新于 %s" % (
            s.get("source") or "-",
            ("(快照 %s)" % s.get("snapshot_date")) if s.get("snapshot_date") else "",
            s.get("l1_updated") or "-"))
        return "\n".join(lines)

    def __text_timeline(self, state: Dict[str, Any]) -> str:
        sites = state.get("sites") or []
        if not sites:
            return "暂无数据。"
        lines = []
        for s in sites[:4]:
            hist = self.__history(s.get("domain", ""), 10)
            if not hist:
                lines.append("%s:无历史数据" % s.get("site_name"))
                continue
            lines.append("【%s】最近 %d 天(每天一行,来自 mp 的 siteuserdata 日快照)" % (s.get("site_name"), len(hist)))
            for h in hist:
                up = h.get("upload") or 0
                dl = h.get("download") or 0
                ratio = h.get("ratio")
                lines.append("  %s  上传 %8.2fG  下载 %8.2fG  分享率 %7s  魔力 %8s  做种 %4s" % (
                    str(h.get("updated_day") or h.get("updated_time") or "")[:10],
                    up / GB, dl / GB,
                    ("%.3f" % ratio) if isinstance(ratio, (int, float)) else "-",
                    self.__fmt(h.get("bonus")), h.get("seeding")))
            # 趋势行:区间首尾增量
            if len(hist) >= 2:
                a, b = hist[0], hist[-1]
                dup = ((b.get("upload") or 0) - (a.get("upload") or 0)) / GB
                ddl = ((b.get("download") or 0) - (a.get("download") or 0)) / GB
                lines.append("  ▸ %s → %s:上传 %+.1fG,下载 %+.1fG(日均 %+.1fG / %+.1fG)" % (
                    str(a.get("updated_day"))[:10], str(b.get("updated_day"))[:10],
                    dup, ddl, dup / max(1, len(hist) - 1), ddl / max(1, len(hist) - 1)))
            lines.append("")
        return "\n".join(lines)

    def __text_risk(self, sites: List[Dict[str, Any]]) -> str:
        if not sites:
            return "暂无数据。"
        danger, warn, ok = [], [], []
        for s in sites:
            for r in (s.get("risks") or []):
                item = "%s:%s" % (s.get("site_name"), r["text"])
                (danger if r["level"] == "danger" else warn).append(item)
            if not s.get("risks"):
                ok.append(s.get("site_name") or "?")
        lines = []
        lines.append("⛔ 已触发:%s" % ("; ".join(danger) if danger else "无"))
        lines.append("")
        lines.append("⚠️ 需关注(真实风险;各站保号/封号条款见对应站点卡):")
        if warn:
            for w in warn:
                lines.append("  · " + w)
        else:
            lines.append("  · 无")
        lines.append("")
        lines.append("✅ 未命中风险的站点:%s" % (", ".join(ok) if ok else "无"))
        return "\n".join(lines)

    @staticmethod
    def __req_label(r: Dict[str, Any]) -> str:
        cn = {"interval": "注册时长", "download": "下载量", "upload": "上传量", "ratio": "分享率",
              "bonus": "魔力值", "seeding_bonus": "做种积分", "seeding": "做种数",
              "seeding_size": "做种体积"}.get(r["key"], r["key"])
        unit = r.get("unit") or ""
        if r["key"] == "interval":
            return "%s ≥ %s%s" % (cn, r["target"], unit)
        return "%s ≥ %s%s" % (cn, r["target"], unit)

    @staticmethod
    def __fmt(v) -> str:
        if v is None:
            return "-"
        if isinstance(v, float):
            return ("%.3f" % v).rstrip("0").rstrip(".") if abs(v) < 10 else "%.2f" % v
        return str(v)

    # =====================================================================
    # 通知
    # =====================================================================
    def __notify_changes(self, sites: List[Dict[str, Any]], manual: bool):
        if not self._notify:
            return
        prev_map = self.get_data("notify_state") or {}
        now_map = dict(prev_map)
        msgs = []

        for s in sites:
            sid = str(s.get("site_id"))
            old = prev_map.get(sid) or {}
            # ① 等级变化
            if self._notify_level_change and s.get("level") and old.get("level") \
                    and old["level"] != s["level"]:
                old_order, new_order = old.get("order"), s.get("level_order")
                if isinstance(old_order, int) and isinstance(new_order, int):
                    arrow = "⬆️" if new_order > old_order else "⬇️"
                else:
                    arrow = "🔁"
                msgs.append("%s %s 等级变化:%s → %s" % (arrow, s.get("site_name"), old["level"], s["level"]))
            # ② 风险(仅新增或升级)
            if self._notify_risk:
                for r in (s.get("risks") or []):
                    if r["level"] == "danger":
                        msgs.append("⛔ %s:%s" % (s.get("site_name"), r["text"]))
            # ③ ETA 阈值
            if self._notify_eta and s.get("eta_days") is not None and not s.get("manual_blocked"):
                if s["eta_days"] <= self._eta_threshold_days:
                    key = "eta_notified_at"
                    last = old.get(key)
                    today = datetime.now().strftime("%Y-%m-%d")
                    if last != today:
                        msgs.append("🎯 %s 预计 %.0f 天内可升到 %s" % (
                            s.get("site_name"), s["eta_days"], s.get("next_level") or "下一级"))
                        now_map[sid] = {**old, key: today, "level": s.get("level"),
                                        "order": s.get("level_order")}
                        continue
            now_map[sid] = {"level": s.get("level"), "order": s.get("level_order"),
                            **(old if old.get("eta_notified_at") else {})}

        self.save_data("notify_state", now_map)
        if msgs and not manual:
            self.__notify_send("站点等级看板·变化与风险", "\n".join(msgs))
        elif msgs:
            logger.info("【站点等级看板】手动刷新,不推送通知:%s" % msgs)

        if self._notify_daily and not manual and self._notify:
            self.__notify_send("站点等级看板·每日汇总",
                               self.__text_overview(sites) + "\n\n" +
                               "\n".join("— %s —\n%s" % (s.get("site_name"), self.__text_detail(s))
                                         for s in sites[:6]))

    def __notify_send(self, title: str, text: str, force: bool = False):
        if not self._notify:
            return
        if not force and self.__in_quiet():
            logger.info(f"【站点等级看板】免打扰时段,跳过推送:{title}")
            return
        ch = None
        if self._notify_channel and NotificationChannel is not None:
            ch = getattr(NotificationChannel, self._notify_channel, None)
        try:
            self.post_message(mtype=_MSG_TYPE, title=title, text=text, channel=ch)
        except Exception as e:
            logger.warn(f"【站点等级看板】指定渠道失败({e}),改全渠道重试")
            try:
                self.post_message(mtype=_MSG_TYPE, title=title, text=text)
            except Exception as e2:
                logger.warn(f"【站点等级看板】通知失败:{e2}")

    def __in_quiet(self) -> bool:
        if not (self._quiet_start and self._quiet_end):
            return False
        try:
            def mins(x: str) -> int:
                h, m = x.split(":")[:2]
                return int(h) * 60 + int(m)
            a, b = mins(self._quiet_start), mins(self._quiet_end)
            now = datetime.now().hour * 60 + datetime.now().minute
            if a == b:
                return False
            return (a <= now < b) if a < b else (now >= a or now < b)
        except Exception:
            return False

    # =====================================================================
    # 工具
    # =====================================================================
    @staticmethod
    def __as_int(v, d: int, lo: int, hi: int) -> int:
        try:
            return max(lo, min(hi, int(str(v).strip())))
        except Exception:
            return d

    @staticmethod
    def __cron_ok(expr: str) -> bool:
        return len([x for x in (expr or "").split() if x]) == 5

    # ---- 渲染助手(声明式页面的通用写法,均已在真实页面验证)----------------
    @staticmethod
    def __row(items: List[dict], show: str = "") -> dict:
        node: Dict[str, Any] = {"component": "VRow", "content": items}
        if show:
            node["props"] = {"show": "{{ %s }}" % show}
        return node

    @staticmethod
    def __col(item: dict, md: int = 12) -> dict:
        return {"component": "VCol", "props": {"cols": 12, "md": md}, "content": [item]}

    @staticmethod
    def __card(title: str, icon: str, rows: List[dict]) -> dict:
        return {
            "component": "VCard",
            "props": {"variant": "outlined", "class": "mb-4"},
            "content": [
                {"component": "VCardTitle",
                 "props": {"class": "d-flex align-center text-subtitle-1"},
                 "content": [{"component": "VIcon", "props": {"icon": icon, "class": "mr-2",
                                                              "color": "primary"}},
                             {"component": "div", "text": title}]},
                {"component": "VCardText", "content": rows},
            ],
        }

    @staticmethod
    def __pane(text: str) -> dict:
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
        props: Dict[str, Any] = {"model": model, "label": label, "items": options, "clearable": True}
        if multiple:
            props.update({"multiple": True, "chips": True})
        return self.__col({"component": "VSelect", "props": props}, md)

    def __cron(self, model: str, label: str, md: int = 6, hint: str = "") -> dict:
        return self.__col({"component": "VCronField",
                           "props": {"model": model, "label": label, "placeholder": hint}}, md)

    def __textarea(self, model: str, label: str, md: int, rows: int, hint: str = "") -> dict:
        return self.__col({"component": "VTextarea",
                           "props": {"model": model, "label": label, "rows": rows,
                                     "placeholder": hint}}, md)

    def __btn(self, text: str, icon: str, path: str, md: int = 4) -> dict:
        return self.__col({
            "component": "VBtn",
            "props": {"class": "ma-1", "variant": "tonal", "prepend-icon": icon, "block": True},
            "text": text,
            "events": {"click": {"api": "plugin/%s%s" % (self.__class__.__name__, path),
                                 "method": "post"}},
        }, md)

    def __alert(self, text: str, type_: str, md: int, show: str = "") -> dict:
        props: Dict[str, Any] = {"type": type_, "variant": "tonal", "text": text}
        if show:
            props["show"] = "{{ %s }}" % show
        return self.__col({"component": "VAlert", "props": props}, md)
