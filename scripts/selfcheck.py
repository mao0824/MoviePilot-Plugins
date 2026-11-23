#!/usr/bin/env python3
"""SiteLevelBoard 离线自检:不需要安装 MoviePilot,也不用联网。

覆盖:
  1. 插件基类的 6 个抽象方法是否都实现了(少一个就会装不上);
  2. 渲染模式与联邦产物是否齐(``get_render_mode()`` + ``dist/assets/remoteEntry.js``);
  3. 前端用到的端点是否都在 ``get_api()`` 里(12 个);
  4. 根 ``package.json`` 的版本与插件内 ``plugin_version`` 是否一致;
  5. 私有引用扫描(公开仓库里不该出现的内容);
  6. 拖拽排序的核心逻辑(排列落库 / 非法输入拒绝 / 陈旧 id 处理 / 增删不破坏顺序)。

用法:``python3 scripts/selfcheck.py``;全部通过退出码 0,否则 1。
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "plugins" / "sitelevelboard"
PLUGIN_FILE = PLUGIN_DIR / "__init__.py"

FAILED: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if ok else 'FAIL'} {label}{(' — ' + detail) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


def install_stubs() -> None:
    """插件 import 的 MoviePilot/三方依赖在本地并不存在,这里补最小桩。"""
    def module(name: str, **attrs: object) -> types.ModuleType:
        mod = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(mod, key, value)
        sys.modules[name] = mod
        return mod

    module("requests", get=None, post=None, Session=object)
    aps = module("apscheduler")
    aps_triggers = module("apscheduler.triggers")
    module("apscheduler.triggers.cron", CronTrigger=object)
    aps.triggers = aps_triggers
    aps_triggers.cron = sys.modules["apscheduler.triggers.cron"]

    class _Logger:
        def __getattr__(self, _name):  # noqa: ANN001
            return lambda *a, **k: None

    module("app", __path__=[])
    module("app.log", logger=_Logger())
    module("app.plugins", _PluginBase=type("_PluginBase", (), {}))
    module("app.schemas", __path__=[])

    class Response:
        def __init__(self, success: bool = True, message=None, data=None):
            self.success, self.message, self.data = success, message, data

    sys.modules["app.schemas"].Response = Response
    module("app.schemas.types", MessageType=type("MessageType", (), {"Plugin": "Plugin"}),
           NotificationChannel=None)

    try:
        import pydantic  # noqa: F401
    except Exception:  # 没有 pydantic 时用极简替代(只用到构造与 model_dump)
        class BaseModel:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

            def model_dump(self, exclude_none: bool = False):
                items = dict(self.__dict__)
                return {k: v for k, v in items.items() if v is not None} if exclude_none else items

        pyd = module("pydantic", BaseModel=BaseModel)
        pyd.Field = lambda *a, **k: None


def load_plugin():
    spec = importlib.util.spec_from_file_location("sitelevelboard", PLUGIN_FILE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_instance(mod, store: dict):
    """绕过 __init__ 造一个实例(不连数据库/不发网络请求),并注入内存存储。"""
    instance = object.__new__(mod.SiteLevelBoard)
    instance.save_data = lambda key, value=None, **kw: store.__setitem__(key, value)
    instance.get_data = lambda key, default=None: store.get(key, default)
    instance.update_config = lambda *a, **k: None
    instance.init_plugin({})
    sites = [{"id": 3, "name": "馒头", "domain": "m-team.cc", "is_active": 1},
             {"id": 4, "name": "PTS", "domain": "ptskit.org", "is_active": 1},
             {"id": 5, "name": "PT时间", "domain": "pttime.org", "is_active": 1},
             {"id": 6, "name": "Rousi Pro", "domain": "rousi.pro", "is_active": 1}]
    instance.__dict__["_SiteLevelBoard__sites_all"] = lambda: sites
    return instance, sites


def main() -> int:
    source = PLUGIN_FILE.read_text(encoding="utf-8")

    print("[1] 抽象方法(缺一个就装不上)")
    for name in ("init_plugin", "get_state", "get_api", "get_form", "get_page", "stop_service"):
        check(f"def {name}", bool(re.search(rf"^    def {name}\(", source, re.M)))

    install_stubs()
    mod = load_plugin()

    print("[2] 渲染模式与联邦产物")
    check('get_render_mode() == ("vue", "dist/assets")', mod.SiteLevelBoard.get_render_mode() == ("vue", "dist/assets"))
    check("dist/assets/remoteEntry.js 存在", (PLUGIN_DIR / "dist" / "assets" / "remoteEntry.js").is_file())

    print("[3] 端点(前端契约)")
    store: dict = {}
    instance, sites = make_instance(mod, store)
    paths = [api["path"] for api in instance.get_api()]
    expected = ["/sites", "/detail", "/track", "/untrack", "/reorder", "/config",
                "/config/save", "/refresh", "/report", "/enable", "/disable", "/test_notify"]
    for path in expected:
        check(path, path in paths)
    check(f"端点总数 {len(paths)} == 12", len(paths) == 12)

    print("[4] 版本一致性")
    manifest_version = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["SiteLevelBoard"]["version"]
    plugin_version = mod.SiteLevelBoard.plugin_version
    check(f"package.json({manifest_version}) == plugin_version({plugin_version})", manifest_version == plugin_version)

    print("[5] 私有引用扫描")
    denylist = ["NasSentinel", "哨兵", "192.168.", "m99m.synology", "/volume1", "nas-ops"]
    for path in sorted(PLUGIN_DIR.rglob("*")):
        if not path.is_file() or "node_modules" in path.parts or "__pycache__" in path.parts:
            continue
        if path.suffix not in {".py", ".md", ".js", ".vue", ".json", ".html"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for word in denylist:
            if word in text:
                check(f"{path.relative_to(ROOT)} 不含 {word!r}", False)

    print("[6] 拖拽排序逻辑")

    def order(resp) -> list[int]:
        return [item["id"] for item in resp.data["tracked"]]

    check("默认(未配置)= 全部站点", order(instance.api_sites()) == [3, 4, 5, 6])
    check("排列落库", instance.api_reorder(mod.ReorderPayload(site_ids=[5, 3, 4, 6])).success
          and store["tracked"] == [5, 3, 4, 6])
    check("/sites 按存储顺序返回", order(instance.api_sites()) == [5, 3, 4, 6])
    sites.append({"id": 7, "name": "新站", "domain": "new.example", "is_active": 1})
    instance.api_track(mod.TrackPayload(site_id=7))
    check("新增追加到末尾", store["tracked"] == [5, 3, 4, 6, 7])
    check("集合不符被拒绝", not instance.api_reorder(mod.ReorderPayload(site_ids=[5, 3, 4])).success
          and store["tracked"] == [5, 3, 4, 6, 7])
    check("含重复被拒绝", not instance.api_reorder(mod.ReorderPayload(site_ids=[5, 5, 3, 4, 6, 7])).success)
    store["tracked"] = [5, 3, 4, 6, 7, 999]          # 999 = mp 里已删、但仍留在 tracked
    check("陈旧 id 留末尾且不展示",
          instance.api_reorder(mod.ReorderPayload(site_ids=[7, 5, 3, 4, 6])).success
          and store["tracked"] == [7, 5, 3, 4, 6, 999]
          and order(instance.api_sites()) == [7, 5, 3, 4, 6])
    instance.api_untrack(mod.TrackPayload(site_id=3))
    check("移出不打乱顺序", store["tracked"] == [7, 5, 4, 6, 999])

    print("[7] ETA 口径(0.0 只代表「条件全达成」,算不出就必须给 None)")
    site_eta = instance._SiteLevelBoard__site_eta          # 私有方法,自检里直接调
    hist14 = [{}] * 14
    check("全部达成 → 0.0", site_eta([{"met": True, "eta_kind": "auto", "eta_days": None}], {}, hist14)[0] == 0.0)
    check("有未达成但算不出 → None",
          site_eta([{"met": False, "eta_kind": "auto", "eta_days": None}], {}, hist14)[0] is None)
    check("有未达成且算得出 → 取最慢的一项",
          site_eta([{"met": False, "eta_kind": "auto", "eta_days": 3},
                    {"met": False, "eta_kind": "wait", "eta_days": 11}], {}, hist14)[0] == 11)
    check("样本不足(<3) → None",
          site_eta([{"met": False, "eta_kind": "auto", "eta_days": 3}], {}, [{}] * 2)[0] is None)
    check("需人为推动不计入 ETA",
          site_eta([{"met": False, "eta_kind": "manual", "eta_days": 5}], {}, hist14)[0] is None)

    print("[8] 规则条目两种形态都能取到文本")
    rule_texts = instance._SiteLevelBoard__rule_texts       # 快照给 {"text": ...},站点页给字符串
    check("字符串直接取", rule_texts(["a", "b"]) == ["a", "b"])
    check("{text} 取字段", rule_texts([{"text": "x"}, {"text": "y"}]) == ["x", "y"])
    check("混合 + 脏值安全", rule_texts(["a", {"text": "b"}, {}, None]) == ["a", "b"])

    # ------------------------------------------------------------------
    # 等级名匹配:档位错一级,ETA 就全错 —— 这里逐级钉住行为
    # ------------------------------------------------------------------
    print("[9] 等级名别名匹配(宁缺勿错)")
    resolve = instance._SiteLevelBoard__resolve_level
    std = [{"order": i + 1, "name": n} for i, n in enumerate(
        ["User", "Power User", "Elite User", "Crazy User", "Insane User",
         "Veteran User", "Extreme User", "Ultimate User", "Nexus Master"])]

    r = resolve(std, "Power User")
    check("原文一致 → exact", (r["order"], r["how"]) == (2, "exact"))
    r = resolve(std, "PowerUser")
    check("只差空格 → compact", (r["order"], r["how"]) == (2, "compact"))
    r = resolve(std, "中级用户")
    check("中文名经别名组 → Elite User", (r["order"], r["how"]) == (3, "alias"))
    r = resolve(std, "EU")
    check("缩写 EU → Elite User", (r["order"], r["how"]) == (3, "alias"))
    r = resolve(std, "贵宾")
    check("贵宾认得出是 VIP、但阶梯里没有 → off_ladder",
          (r["order"], r["how"], r["matched"]) == (None, "off_ladder", "VIP"))
    r = resolve(std, "完全没见过的名字")
    check("对不上 → none", (r["order"], r["how"]) == (None, "none"))

    themed = [{"order": 1, "name": "黔首(Peasant)"}, {"order": 2, "name": "凡人(Power User)"},
              {"order": 3, "name": "渡劫一重·人劫(Elite User)"}]
    r = resolve(themed, "Power User")
    check("括号里的英文别名能反查 → 凡人", (r["order"], r["how"]) == (2, "alias"))
    r = resolve(themed, "凡人")
    check("主题中文名原文一致", (r["order"], r["how"]) == (2, "exact"))

    decorated = [{"order": 1, "name": "憨头憨脑 User"}, {"order": 2, "name": "满面娇憨 Nexus Master"}]
    r = resolve(decorated, "User")
    check("中英混排「憨头憨脑 User」认得 User", (r["order"], r["how"]) == (1, "alias"))
    r = resolve(decorated, "NEXUS MASTER")
    check("中英混排 + 大小写", (r["order"], r["how"]) == (2, "alias"))

    solar = [{"order": 1, "name": "Lv.1 白露"}, {"order": 3, "name": "Lv.3 霜降"}]
    r = resolve(solar, "霜降")
    check("去掉「Lv.3」前缀后对上", (r["order"], r["how"]) == (3, "alias"))

    both = [{"order": 2, "name": "Elite"}, {"order": 3, "name": "Elite User"}]
    r = resolve(both, "中级用户")
    check("同组命中多档 → ambiguous(不猜)", (r["order"], r["how"]) == (None, "ambiguous"))
    r = resolve(both, "Elite")
    check("原文一致优先于歧义", (r["order"], r["how"]) == (2, "exact"))

    instance._level_alias_map = mod._parse_alias_rules("example.com|初级|Power User")
    r = resolve(std, "初级", "example.com")
    check("配置别名 → user_alias", (r["order"], r["how"]) == (2, "user_alias"))
    r = resolve(std, "初级", "other.com")
    check("配置别名只对该域名生效", r["how"] == "none")
    instance._level_alias_map = {}

    print("[10] 别名表与规则库文件")
    check("level_aliases.json 已加载", len(mod.ALIAS_GROUPS) >= 10, f"groups={len(mod.ALIAS_GROUPS)}")
    check("规则库 174 个域名", len(mod.LEVEL_SPECS_BY_DOMAIN) >= 170,
          f"domains={len(mod.LEVEL_SPECS_BY_DOMAIN)}")
    check("规则库键不带 www.", not any(k.startswith("www.") for k in mod.LEVEL_SPECS_BY_DOMAIN))
    # 内置 3 站是人工核对的快照,编号口径保持原样(PT时间 的 Peasant=0 是有意的降级档);
    # 从 depiler 导入的部分必须统一成 1..N,否则「还差几级」会整体差一档。
    builtin = set(mod.BUILTIN_DOMAIN_MAP.values())
    external = {k: v for k, v in mod.LEVEL_SPECS_BY_DOMAIN.items() if k not in builtin}
    bad_order = [k for k, s in external.items()
                 if (s.get("ladder") or []) and s["ladder"][0].get("order") != 1]
    check("外部规则库档位从 1 起(depiler 有从 0 起的)", not bad_order, f"bad={bad_order[:3]}")
    strict = [k for k, s in external.items()
              if (s.get("ladder") or [])
              and [lv.get("order") for lv in s["ladder"]] != list(range(1, len(s["ladder"]) + 1))]
    check("外部规则库档位连续无空洞", not strict, f"bad={strict[:3]}")

    print()
    if FAILED:
        print(f"未通过 {len(FAILED)} 项:{FAILED}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
