#!/usr/bin/env python3
"""从 PT-depiler(MIT) 的站点定义生成 SiteLevelBoard 的规则库 level_specs.json。

用法:
    python scripts/import_depiler_rules.py                 # 自动下载 depiler tarball
    python scripts/import_depiler_rules.py --src <目录>     # 用本地已解压的 definitions 目录
    python scripts/import_depiler_rules.py --out <文件>     # 指定输出(默认插件目录下 level_specs.json)

说明:
  * depiler 定义文件里的 ``urls`` 是 **ROT13 编码**的(防爬),这里解码后取域名;
  * 只抽取字面量数组形式的 ``levelRequirements``(引用变量/函数的站跳过);
  * 内置 3 站(m-team.cc / ptskit.org / pttime.org)由插件内人工核对快照提供,
    脚本默认不覆盖,避免丢掉 PTS 的「做种积分」这类 depiler 没有的条件。
"""

from __future__ import annotations

import argparse
import codecs
import json
import os
import re
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request
from datetime import date
from typing import Any, Dict, List, Optional

TARBALL_URL = "https://codeload.github.com/pt-plugins/PT-depiler/tar.gz/refs/heads/master"
BUILTIN_DOMAINS = {"m-team.cc", "ptskit.org", "pttime.org"}
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(HERE, "..", "plugins", "sitelevelboard", "level_specs.json")


def rot13(text: str) -> str:
    return codecs.encode(text, "rot_13")


def fetch_tarball(dst_dir: str) -> str:
    """下载 depiler 源码 tarball 并解压,返回 definitions 目录。"""
    tgz = os.path.join(dst_dir, "depiler.tar.gz")
    print(f"[1/3] 下载 {TARBALL_URL}")
    req = urllib.request.Request(TARBALL_URL, headers={"User-Agent": "SiteLevelBoard-rule-importer"})
    with urllib.request.urlopen(req, timeout=180) as resp, open(tgz, "wb") as f:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    print(f"      下载完成 {os.path.getsize(tgz) / 1024 / 1024:.1f} MB")
    print("[2/3] 解压")
    with tarfile.open(tgz, "r:gz") as tar:
        tar.extractall(dst_dir)
    for name in os.listdir(dst_dir):
        cand = os.path.join(dst_dir, name, "src", "packages", "site", "definitions")
        if os.path.isdir(cand):
            return cand
    raise RuntimeError("tarball 里没找到 definitions 目录")


def extract_block(text: str, key: str) -> Optional[str]:
    """取 ``key ... = [ ... ]`` 的方括号内容(括号配对,忽略字符串里的括号)。"""
    i = text.find(key)
    if i < 0:
        return None
    j = text.find("[", i)
    if j < 0:
        return None
    depth, in_str, quote = 0, False, ""
    k = j
    while k < len(text):
        c = text[k]
        if in_str:
            if c == "\\":
                k += 2
                continue
            if c == quote:
                in_str = False
        else:
            if c in "\"'`":
                in_str, quote = True, c
            elif c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    return text[j:k + 1]
        k += 1
    return None


def split_top_objects(block: str) -> List[str]:
    """把 ``[{...},{...}]`` 按顶层对象切开。"""
    out: List[str] = []
    depth, start = 0, None
    in_str, quote = False, ""
    i = 0
    while i < len(block):
        c = block[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                in_str = False
        else:
            if c in "\"'`":
                in_str, quote = True, c
            elif c == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0 and start is not None:
                    out.append(block[start:i + 1])
                    start = None
        i += 1
    return out


def _str_field(obj: str, key: str) -> Optional[str]:
    m = re.search(rf'\b{key}\s*:\s*"([^"]*)"', obj)
    return m.group(1) if m else None


def _num_field(obj: str, key: str) -> Optional[float]:
    m = re.search(rf'\b{key}\s*:\s*(-?[\d.]+)', obj)
    return float(m.group(1)) if m else None


def _bool_field(obj: str, key: str) -> Optional[bool]:
    m = re.search(rf'\b{key}\s*:\s*(true|false)', obj)
    return (m.group(1) == "true") if m else None


def parse_interval(value: Optional[str]) -> Optional[float]:
    """ISO-8601 duration → 周。``P4W``→4, ``P1M``→4.35, ``P1Y``→52。"""
    if not value:
        return None
    m = re.match(r"P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)W)?(?:(\d+)D)?", value)
    if not m:
        return None
    years, months, weeks, days = (int(x) if x else 0 for x in m.groups())
    total = years * 52 + months * 4.345 + weeks + days / 7
    return round(total, 1) if total > 0 else None


def parse_size_gb(value: Optional[str]) -> Optional[float]:
    """``200GB`` → 200, ``1TB`` → 1024。统一成 GB 口径。"""
    if not value:
        return None
    m = re.match(r"([\d.]+)\s*([KMGT]i?B?)", str(value), re.I)
    if not m:
        return None
    num = float(m.group(1))
    unit = m.group(2).upper()[0]
    scale = {"K": 1 / 1024 / 1024, "M": 1 / 1024, "G": 1, "T": 1024}
    return round(num * scale.get(unit, 1), 2)


def extract_domains(text: str) -> List[str]:
    m = re.search(r"\burls\s*:\s*\[(.*?)\]", text, re.S)
    if not m:
        return []
    domains: List[str] = []
    for raw in re.findall(r'"([^"]+)"', m.group(1)):
        decoded = rot13(raw)
        if not decoded.startswith("http"):
            continue
        host = urllib.parse.urlparse(decoded).hostname or ""
        host = host.lower().strip(".")
        if host and host not in domains:
            domains.append(host)
    return domains


def parse_file(path: str) -> Optional[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    domains = extract_domains(text)
    if not domains:
        return None
    block = extract_block(text, "levelRequirements")
    if not block:
        return None
    ladder: List[Dict[str, Any]] = []
    for obj in split_top_objects(block):
        level_id = _num_field(obj, "id")
        name = _str_field(obj, "name")
        if level_id is None or not name:
            continue
        if _str_field(obj, "groupType") or level_id >= 100:   # VIP / 捐赠档不进阶梯
            continue
        reqs: List[Dict[str, Any]] = []
        weeks = parse_interval(_str_field(obj, "interval"))
        if weeks:
            reqs.append({"key": "interval", "target": weeks, "unit": "周"})
        gb = parse_size_gb(_str_field(obj, "downloaded"))
        if gb:
            reqs.append({"key": "download", "target": gb, "unit": "GB"})
        ratio = _num_field(obj, "ratio")
        if ratio:
            reqs.append({"key": "ratio", "target": ratio, "unit": ""})
        ladder.append({
            "order": int(level_id),
            "name": name,
            "requirements": reqs,
            "privilege": _str_field(obj, "privilege"),
            "is_permanent": bool(_bool_field(obj, "isKept")),
            "is_parkable": bool(_bool_field(obj, "isKept")),
        })
    if len(ladder) < 2:
        return None
    ladder.sort(key=lambda x: x["order"])
    # 档位编号统一成 1..N:depiler 的 levelRequirements id 有的从 0 起、有的从 1 起
    # (实测 59 个从 0、114 个从 1、还有 1 个从 3 起)。编号只做相对比较,重排安全;
    # 不统一则「离可封存还差 N 级」会整体差一档。
    for idx, level in enumerate(ladder, start=1):
        level["order"] = idx
    return {"domains": domains, "ladder": ladder}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", help="本地 definitions 目录(跳过下载)")
    ap.add_argument("--out", default=DEFAULT_OUT, help="输出 JSON 路径")
    ap.add_argument("--keep-builtin", action="store_true", help="允许覆盖内置 3 站")
    args = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="depiler-")
    try:
        src = args.src or fetch_tarball(tmp)
        files = sorted(f for f in os.listdir(src) if f.endswith(".ts") and f != "index.ts")
        print(f"[3/3] 解析 {len(files)} 个站点定义")
        rules: Dict[str, Any] = {}
        with_rules, failed = 0, 0
        today = date.today().isoformat()
        for fn in files:
            try:
                parsed = parse_file(os.path.join(src, fn))
            except Exception as e:  # 单个文件坏掉不影响整体
                print(f"  ! {fn}: {e}")
                failed += 1
                continue
            if not parsed:
                continue
            with_rules += 1
            for dom in parsed["domains"]:
                if dom in BUILTIN_DOMAINS and not args.keep_builtin:
                    continue
                if dom in rules:
                    print(f"  ~ 域名重复,后者覆盖:{dom} ({fn})")
                rules[dom] = {
                    "source": "depiler_snapshot",
                    "snapshot_date": today,
                    "ladder": parsed["ladder"],
                    "keep_rules": [],
                    "ban_rules": [],
                }
        out = {
            "_meta": {
                "source": "PT-depiler (MIT) — https://github.com/pt-plugins/PT-depiler",
                "date": today,
                "definitions": len(files),
                "sites_with_rules": with_rules,
                "domains": len(rules),
                "failed": failed,
            }
        }
        out.update(rules)
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1, sort_keys=True)
        size_kb = os.path.getsize(args.out) / 1024
        print(f"\n完成:{with_rules} 个定义有等级规则 → {len(rules)} 个域名,"
              f"失败 {failed} 个;输出 {args.out} ({size_kb:.0f} KB)")
        return 0
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
