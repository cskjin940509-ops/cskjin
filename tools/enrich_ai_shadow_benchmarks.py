#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import urllib.request
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

CN = ZoneInfo("Asia/Shanghai")
ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT / "astock_ai_portfolio"
STATE_PATH = PORT / "state.json"
LATEST_PATH = PORT / "latest.json"
RADAR_PATH = ROOT / "astock_radar" / "latest.json"

INDEXES = {
    "沪深300": "sh000300",
    "中证A500": "sh000510",
    "创业板指": "sz399006",
}


def iso() -> str:
    return datetime.now(CN).isoformat(timespec="seconds")


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return deepcopy(default)


def write_json(path: Path, obj) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def stock_symbol(code: str) -> str:
    if code.startswith(("8", "9")):
        return "bj" + code
    return ("sh" if code.startswith(("5", "6")) else "sz") + code


def fetch_symbols(symbols: list[str]) -> dict[str, dict]:
    symbols = [s for s in dict.fromkeys(symbols) if re.fullmatch(r"(?:sh|sz|bj)\d{6}", s or "")]
    if not symbols:
        return {}
    req = urllib.request.Request(
        "https://qt.gtimg.cn/q=" + ",".join(symbols),
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/", "Accept": "*/*"},
    )
    try:
        raw = urllib.request.urlopen(req, timeout=8).read().decode("gbk", errors="ignore")
    except Exception:
        return {}
    out: dict[str, dict] = {}
    for line in raw.split(";"):
        m = re.search(r'v_((?:sh|sz|bj)\d{6})="([^"]*)"', line)
        if not m:
            continue
        sym = m.group(1)
        f = m.group(2).split("~")
        try:
            price = float(f[3]) if len(f) > 3 and f[3] else None
            name = f[1] if len(f) > 1 else sym
            if price and price > 0:
                out[sym] = {"name": name, "price": price}
        except Exception:
            continue
    return out


def pct(current: float | None, base: float | None) -> float | None:
    if not current or not base:
        return None
    return round((float(current) / float(base) - 1.0) * 100.0, 3)


def unit_nav_at(latest: dict, timestamp: str | None) -> float | None:
    rows = [
        x for x in latest.get("navHistory") or []
        if x.get("unitNav") is not None and (not timestamp or str(x.get("timestamp") or "") <= timestamp)
    ]
    return float(rows[-1]["unitNav"]) if rows else None


def main() -> int:
    state = read_json(STATE_PATH, None)
    latest = read_json(LATEST_PATH, None)
    radar = read_json(RADAR_PATH, {})
    if not isinstance(state, dict) or not isinstance(latest, dict):
        print(json.dumps({"state": "no-ai-shadow-state"}, ensure_ascii=False))
        return 0

    tracking = state.get("benchmarkTracking")
    radar_stocks = radar.get("stocks") or {}

    if not isinstance(tracking, dict):
        # Benchmark comparison deliberately starts when this module is first enabled.
        # We do NOT backfill index prices to the earlier 11:14 account creation time.
        ranked = sorted(
            ((code, st) for code, st in radar_stocks.items() if re.fullmatch(r"\d{6}", code or "")),
            key=lambda kv: float((kv[1] or {}).get("earlyEntryScore") or 0.0),
            reverse=True,
        )[:30]
        symbols = list(INDEXES.values()) + [stock_symbol(code) for code, _ in ranked]
        quotes = fetch_symbols(symbols)
        items = {}
        for name, sym in INDEXES.items():
            q = quotes.get(sym)
            if q:
                items[name] = {"symbol": sym, "basePrice": q["price"], "lastPrice": q["price"]}
        members = {}
        for code, st in ranked:
            sym = stock_symbol(code)
            q = quotes.get(sym)
            fallback = (st or {}).get("price")
            base = q.get("price") if q else fallback
            if base:
                members[code] = {
                    "code": code,
                    "name": (st or {}).get("name") or code,
                    "basePrice": float(base),
                    "lastPrice": float(base),
                }
        tracking = {
            "startedAt": iso(),
            "portfolioBaseNav": float((latest.get("summary") or {}).get("totalAssets") or state.get("initialCapital") or 1_000_000.0),
            "portfolioBaseUnitNav": float((latest.get("summary") or {}).get("unitNav") or 1.0),
            "indexes": items,
            "candidatePool": {
                "definitionZh": "基准起始时点提前主线雷达中的前30只候选固定等权，不随后续入池/出池回改成员",
                "members": members,
            },
        }
        state["benchmarkTracking"] = tracking
    else:
        index_symbols = [x.get("symbol") for x in (tracking.get("indexes") or {}).values() if x.get("symbol")]
        member_codes = list(((tracking.get("candidatePool") or {}).get("members") or {}).keys())
        quotes = fetch_symbols(index_symbols + [stock_symbol(c) for c in member_codes])
        for item in (tracking.get("indexes") or {}).values():
            q = quotes.get(item.get("symbol"))
            if q:
                item["lastPrice"] = q["price"]
        for code, item in (((tracking.get("candidatePool") or {}).get("members") or {}).items()):
            q = quotes.get(stock_symbol(code))
            if q:
                item["lastPrice"] = q["price"]

    summary = latest.get("summary") or {}
    current_nav = float(summary.get("unitNav") or 0.0)
    base_nav = tracking.get("portfolioBaseUnitNav")
    if base_nav is None:
        base_nav = unit_nav_at(latest, tracking.get("startedAt")) or current_nav
        tracking["portfolioBaseUnitNav"] = float(base_nav)
        tracking["unitNavMigrationZh"] = "原资金净值基准已迁移为同一时点单位净值，避免增资扭曲收益。"
    port_ret = pct(current_nav, float(base_nav or 0.0))

    index_result = []
    for name, item in (tracking.get("indexes") or {}).items():
        r = pct(item.get("lastPrice"), item.get("basePrice"))
        index_result.append({
            "name": name,
            "returnPct": r,
            "alphaPct": round(port_ret - r, 3) if port_ret is not None and r is not None else None,
        })

    member_returns = []
    for item in (((tracking.get("candidatePool") or {}).get("members") or {}).values()):
        r = pct(item.get("lastPrice"), item.get("basePrice"))
        if r is not None:
            member_returns.append(r)
    pool_ret = round(sum(member_returns) / len(member_returns), 3) if member_returns else None

    latest["benchmarkComparison"] = {
        "startedAt": tracking.get("startedAt"),
        "noteZh": "基准从该同步时点开始，不回填影子账户更早的11:14买入时点，避免事后选择基准价格。",
        "portfolioMetric": "UNIT_NAV_RETURN",
        "portfolioReturnPct": port_ret,
        "indexes": index_result,
        "candidatePool": {
            "name": "原始候选池固定等权",
            "memberCount": len(((tracking.get("candidatePool") or {}).get("members") or {})),
            "returnPct": pool_ret,
            "alphaPct": round(port_ret - pool_ret, 3) if port_ret is not None and pool_ret is not None else None,
            "definitionZh": (tracking.get("candidatePool") or {}).get("definitionZh"),
        },
    }
    latest["updatedAt"] = iso()
    state["updatedAt"] = latest["updatedAt"]
    write_json(STATE_PATH, state)
    write_json(LATEST_PATH, latest)
    print(json.dumps({
        "state": "benchmark-updated",
        "startedAt": tracking.get("startedAt"),
        "portfolioReturnPct": port_ret,
        "candidatePoolReturnPct": pool_ret,
        "indexCount": len(index_result),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
