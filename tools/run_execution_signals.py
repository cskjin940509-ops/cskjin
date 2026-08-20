#!/usr/bin/env python3
"""Point-in-time execution guidance for frozen A-share cohorts.

This layer never changes strategy membership. It translates a frozen Official/Tail
candidate set into observable execution states using only data available at each run.
It also keeps a deterministic paper-execution state for later MFE/MAE evaluation.

Important market rule: ordinary A-share stock buys are treated as T+1. A position
opened today cannot emit a sell recommendation until a later trading date.
"""
from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime, timedelta, timezone, time as dtime
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SNAPS = ROOT / "astock_snapshots" / "index.json"
TAIL = ROOT / "astock_tail" / "latest.json"
OUT_DIR = ROOT / "astock_execution"
LATEST = OUT_DIR / "latest.json"
STATE = OUT_DIR / "state.json"
CN = timezone(timedelta(hours=8))


def finite(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def r6(v):
    return round(v, 6) if v is not None and math.isfinite(v) else None


def symbol(code: str) -> str:
    if code.startswith(("8", "9")):
        return "bj" + code
    return ("sh" if code.startswith(("5", "6")) else "sz") + code


def tencent_quotes(codes: list[str]) -> dict[str, dict]:
    syms = [symbol(c) for c in codes]
    if not syms:
        return {}
    req = Request(
        "https://qt.gtimg.cn/q=" + ",".join(syms),
        headers={"User-Agent": "Mozilla/5.0 AStock-Execution/1.0", "Referer": "https://gu.qq.com/", "Cache-Control": "no-cache"},
    )
    with urlopen(req, timeout=12) as r:
        text = r.read().decode("gbk", "replace")
    out = {}
    for sym, raw in re.findall(r'v_([A-Za-z0-9]+)="([^"]*)"', text):
        f = raw.split("~")
        if len(f) <= 37:
            continue
        code = f[2] if len(f) > 2 else sym[-6:]
        stamp = f[30] if len(f) > 30 else ""
        out[code] = {
            "name": f[1] if len(f) > 1 else code,
            "price": finite(f[3] if len(f) > 3 else None),
            "prevClose": finite(f[4] if len(f) > 4 else None),
            "open": finite(f[5] if len(f) > 5 else None),
            "changePct": finite(f[32] if len(f) > 32 else None),
            "high": finite(f[33] if len(f) > 33 else None),
            "low": finite(f[34] if len(f) > 34 else None),
            "amount": (finite(f[37]) * 10000.0) if finite(f[37]) is not None else None,
            "quoteTimeRaw": stamp,
            "quoteDate": stamp[:8] if len(stamp) >= 8 else None,
            "quoteTime": (stamp[-6:-4] + ":" + stamp[-4:-2] + ":" + stamp[-2:]) if len(stamp) >= 14 else None,
            "source": "腾讯行情",
        }
    return out


def latest_official_before(day: str) -> dict | None:
    if not SNAPS.exists():
        return None
    arr = json.loads(SNAPS.read_text(encoding="utf-8"))
    xs = [x for x in arr if x.get("status") == "Official" and x.get("date") and x.get("date") < day]
    return max(xs, key=lambda x: x.get("date", "")) if xs else None


def latest_official(day: str) -> dict | None:
    if not SNAPS.exists():
        return None
    arr = json.loads(SNAPS.read_text(encoding="utf-8"))
    xs = [x for x in arr if x.get("status") == "Official" and x.get("date")]
    return max(xs, key=lambda x: x.get("date", "")) if xs else None


def candidate_codes(snap: dict | None) -> list[str]:
    if not snap:
        return []
    pools = snap.get("pools") or {}
    for p in ("B4", "B3", "B0"):
        vals = [str(x) for x in pools.get(p) or []]
        if vals:
            return vals[:12]
    return []


def load_tail_today(day: str) -> dict | None:
    if not TAIL.exists():
        return None
    try:
        x = json.loads(TAIL.read_text(encoding="utf-8"))
        return x if x.get("date") == day and not x.get("noTrade") else None
    except Exception:
        return None


def load_state() -> dict:
    if not STATE.exists():
        return {"positions": {}, "closed": {}}
    try:
        x = json.loads(STATE.read_text(encoding="utf-8"))
        if not isinstance(x, dict):
            raise ValueError
        x.setdefault("positions", {})
        x.setdefault("closed", {})
        return x
    except Exception:
        return {"positions": {}, "closed": {}}


def safe_yunai_overlay(codes: list[str]) -> dict:
    if not os.getenv("YUNAI_TOKEN", "").strip() or not codes:
        return {}
    try:
        import yunai_tail_overlay as yo
        return yo.fetch_stock_overlay(codes)
    except Exception:
        return {}


def extract_series_node(node, code: str, found: list[dict]):
    if isinstance(node, dict):
        price = None
        for k in ("price", "lastPrice", "latestPrice", "currentPrice", "close", "closePrice"):
            price = finite(node.get(k))
            if price is not None:
                break
        tm = None
        for k in ("time", "tradeTime", "dateTime", "datetime", "timestamp", "ts"):
            if node.get(k) not in (None, ""):
                tm = node.get(k)
                break
        if price is not None and tm is not None:
            found.append({"time": str(tm), "price": price})
        for k, v in node.items():
            if k == code or isinstance(v, (dict, list)):
                extract_series_node(v, code, found)
    elif isinstance(node, list):
        for x in node:
            extract_series_node(x, code, found)


def yunai_timeshare(codes: list[str]) -> dict[str, list[dict]]:
    if not os.getenv("YUNAI_TOKEN", "").strip() or not codes:
        return {}
    supported = [c for c in codes if not c.startswith(("8", "9"))]
    if not supported:
        return {}
    try:
        import yunai_tail_overlay as yo
        st, _, payload = yo.post(yo.PREFIX + "/time-share-quotes", {"symbols": supported})
        if not (200 <= st < 300):
            st, _, payload = yo.post(yo.PREFIX + "/time-share-quotes", {"symbols": supported, "tradeSession": "Regular"})
        if not (200 <= st < 300):
            return {}
        out = {}
        for c in supported:
            pts = []
            root = payload.get(c) if isinstance(payload, dict) and c in payload else payload
            extract_series_node(root, c, pts)
            # Deduplicate in API order. We intentionally do not sort opaque timestamps;
            # vendor arrays are expected to be chronological and ordering is part of the evidence.
            dedup = []
            seen = set()
            for p in pts:
                key = (p["time"], p["price"])
                if key not in seen:
                    seen.add(key); dedup.append(p)
            if dedup:
                out[c] = dedup
        return out
    except Exception:
        return {}


def max_ordered_profit(points: list[dict]) -> dict | None:
    if len(points) < 2:
        return None
    min_p = finite(points[0].get("price")); min_t = points[0].get("time")
    if min_p is None or min_p <= 0:
        return None
    best = None
    for p in points[1:]:
        px = finite(p.get("price"))
        if px is None or px <= 0:
            continue
        ret = px / min_p - 1.0
        if best is None or ret > best["return"]:
            best = {"buyTime": min_t, "buyPrice": min_p, "sellTime": p.get("time"), "sellPrice": px, "return": ret}
        if px < min_p:
            min_p, min_t = px, p.get("time")
    if not best:
        return None
    return {"buyTime": best["buyTime"], "buyPrice": r6(best["buyPrice"]), "sellTime": best["sellTime"], "sellPrice": r6(best["sellPrice"]), "return": r6(best["return"]), "source": "Yunai分时·先低后高时序"}


def phase(now: datetime) -> str:
    t = now.time()
    if t < dtime(9, 25): return "PREOPEN"
    if t < dtime(9, 40): return "OPEN_OBSERVE"
    if t <= dtime(11, 30): return "LIVE"
    if t < dtime(13, 0): return "LUNCH"
    if t <= dtime(15, 0): return "LIVE"
    return "CLOSED"


def entry_signal(meta: dict, q: dict, now: datetime, yunai: dict | None) -> dict:
    p, prev, opn, hi, lo = [finite(q.get(k)) for k in ("price", "prevClose", "open", "high", "low")]
    if not all(v is not None and v > 0 for v in (p, prev, opn)):
        return {"state": "NO_QUOTE", "label": "行情不足", "actionable": False, "reason": "缺少当天实时价/昨收/开盘价"}
    ph = phase(now)
    lower = max(opn * 0.985, prev * 0.98)
    upper = min(opn * 1.025, prev * 1.04)
    gap = opn / prev - 1.0
    from_open = p / opn - 1.0
    change = p / prev - 1.0
    near_high = hi is not None and hi > 0 and p / hi >= 0.985
    main_flow_pct = finite(meta.get("mainFlowPct"))
    ycap = ((yunai or {}).get("capital") or {}) if isinstance(yunai, dict) else {}
    ylarge = finite(ycap.get("largeNetInflow"))
    flow_ok = (main_flow_pct is not None and main_flow_pct > 0) or (ylarge is not None and ylarge > 0)
    reason_bits = [f"开盘跳空{gap*100:+.2f}%", f"较开盘{from_open*100:+.2f}%"]
    if ph == "PREOPEN":
        state, label, actionable = "WAIT_OPEN", "等待开盘", False
    elif ph == "OPEN_OBSERVE":
        state, label, actionable = "OBSERVE_OPEN", "开盘观察", False
        reason_bits.append("09:40前不追首轮波动")
    elif ph in ("LUNCH", "CLOSED"):
        state, label, actionable = "MARKET_CLOSED", "非交易时段", False
    elif change <= -0.05 or from_open <= -0.035:
        state, label, actionable = "AVOID_BREAKDOWN", "暂不买·弱势", False
        reason_bits.append("价格结构破弱")
    elif change >= 0.07 or (near_high and from_open >= 0.03):
        state, label, actionable = "WAIT_PULLBACK", "等回踩·不追高", False
        reason_bits.append("当前过度扩张/接近日高")
    elif lower <= p <= upper and flow_ok:
        state, label, actionable = "BUY_ZONE", "可分批观察买入", True
        reason_bits.append("价格进入计划区间且资金确认非负")
    elif p > upper:
        state, label, actionable = "WAIT_PULLBACK", "等回踩", False
        reason_bits.append("高于计划买入上沿")
    else:
        state, label, actionable = "WAIT_CONFIRM", "等企稳确认", False
        reason_bits.append("低于计划区间或资金未确认")
    return {
        "state": state, "label": label, "actionable": actionable,
        "zoneLow": r6(lower), "zoneHigh": r6(upper),
        "gapPct": r6(gap), "fromOpenPct": r6(from_open), "fromPrevClosePct": r6(change),
        "reason": "；".join(reason_bits),
        "rules": {"noChaseChangePct": 0.07, "openObserveUntil": "09:40", "flowConfirmation": True},
    }


def position_signal(pos: dict, q: dict, now: datetime) -> dict:
    p = finite(q.get("price")); opn = finite(q.get("open")); entry = finite(pos.get("entryPrice")); peak = finite(pos.get("maxPrice"))
    if p is None or entry is None or entry <= 0:
        return {"state": "NO_QUOTE", "label": "行情不足", "actionable": False}
    ret = p / entry - 1.0
    peak_ret = (peak / entry - 1.0) if peak else ret
    drawdown = (p / peak - 1.0) if peak else 0.0
    if pos.get("entryDate") == now.strftime("%Y-%m-%d"):
        return {"state": "HOLD_T1", "label": "持有·T+1不可当日卖", "actionable": False, "return": r6(ret), "reason": "普通A股买入当日不发卖出指令"}
    if ret <= -0.035:
        st, lb, rs = "SELL_STOP", "卖出·止损", "跌破-3.5%风险线"
    elif ret >= 0.10:
        st, lb, rs = "SELL_TAKE_PROFIT", "卖出/至少止盈一部分", "达到+10%二级止盈"
    elif peak_ret >= 0.06 and drawdown <= -0.025:
        st, lb, rs = "SELL_TRAIL", "卖出·移动止盈", "峰值收益>=6%后回撤>=2.5%"
    elif now.time() >= dtime(14, 45) and opn and p < opn and ret < 0.01:
        st, lb, rs = "SELL_WEAK_CLOSE", "尾盘减仓/退出", "14:45后弱于开盘且持仓收益<1%"
    else:
        st, lb, rs = "HOLD", "继续持有", "未触发止损/止盈/尾盘弱势条件"
    return {"state": st, "label": lb, "actionable": st.startswith("SELL"), "return": r6(ret), "peakReturn": r6(peak_ret), "drawdownFromPeak": r6(drawdown), "reason": rs}


def main():
    now = datetime.now(CN)
    day = now.strftime("%Y-%m-%d")
    ph = phase(now)
    prev_official = latest_official_before(day)
    newest_official = latest_official(day)
    source = prev_official if ph != "CLOSED" else newest_official
    source_mode = "OfficialNextDayExecution" if source and source.get("date") < day else "OfficialNextSessionPlan"
    codes = candidate_codes(source)

    # Tail is a separate same-day channel after 14:30. Never merge its membership into Official.
    tail = load_tail_today(day) if now.time() >= dtime(14, 30) else None
    tail_codes = [str(x) for x in ((tail or {}).get("pools") or {}).get("TailCore") or []][:8]
    all_codes = list(dict.fromkeys(codes + tail_codes))
    quotes = tencent_quotes(all_codes) if all_codes else {}
    yoverlay = safe_yunai_overlay(all_codes)
    timeshares = yunai_timeshare(all_codes) if ph in ("LIVE", "LUNCH", "CLOSED") else {}
    state = load_state()
    positions = state["positions"]
    closed = state["closed"]

    meta_map = (source or {}).get("stocks") or {}
    ranked = []
    for idx, code in enumerate(codes):
        meta = dict(meta_map.get(code) or {})
        q = quotes.get(code) or {}
        trade_id = f"{(source or {}).get('date','')}-{code}"
        pos = positions.get(trade_id)
        if pos:
            px = finite(q.get("price"))
            if px is not None:
                pos["maxPrice"] = max(finite(pos.get("maxPrice")) or px, px)
                pos["minPrice"] = min(finite(pos.get("minPrice")) or px, px)
                pos["lastPrice"] = px
                pos["lastUpdatedAt"] = now.isoformat(timespec="seconds")
            sig = position_signal(pos, q, now)
            if sig.get("actionable") and ph == "LIVE":
                pos["exitSignalAt"] = now.isoformat(timespec="seconds")
                pos["exitSignalPrice"] = finite(q.get("price"))
        else:
            sig = entry_signal(meta, q, now, yoverlay.get(code))
            # Deterministic paper entry: only top-3 actionable Official candidates.
            if sig.get("state") == "BUY_ZONE" and idx < 3 and ph == "LIVE" and trade_id not in closed:
                px = finite(q.get("price"))
                if px:
                    pos = {
                        "tradeId": trade_id, "code": code, "sourceDate": (source or {}).get("date"),
                        "entryDate": day, "entryTime": q.get("quoteTime") or now.strftime("%H:%M:%S"),
                        "entryPrice": r6(px * 1.001), "observedPrice": px, "slippageBps": 10,
                        "maxPrice": px, "minPrice": px, "status": "OPEN",
                        "fillModel": "信号时点行情+10bp不利滑点；仅用于策略跟踪，不代表用户真实成交",
                    }
                    positions[trade_id] = pos
                    sig = position_signal(pos, q, now)
        day_hi, day_lo = finite(q.get("high")), finite(q.get("low"))
        opportunity = max_ordered_profit(timeshares.get(code) or [])
        paper = None
        if pos:
            ep = finite(pos.get("entryPrice")); mx = finite(pos.get("maxPrice")); mn = finite(pos.get("minPrice"))
            if ep:
                paper = {
                    "entryDate": pos.get("entryDate"), "entryTime": pos.get("entryTime"), "entryPrice": ep,
                    "currentReturn": r6((finite(q.get("price")) / ep - 1.0) if finite(q.get("price")) else None),
                    "MFE": r6(mx / ep - 1.0) if mx else None,
                    "MAE": r6(mn / ep - 1.0) if mn else None,
                    "sellEligible": pos.get("entryDate") != day,
                }
        ranked.append({
            "rank": idx + 1, "code": code, "name": meta.get("name") or q.get("name") or code,
            "sector": meta.get("sector"), "score": finite(meta.get("score")),
            "pools": meta.get("pools") or [p for p, vals in ((source or {}).get("pools") or {}).items() if code in (vals or [])],
            "selectionPrice": finite(meta.get("selectionPrice")), "mainFlowPct": finite(meta.get("mainFlowPct")),
            "quote": q,
            "dayStats": {
                "high": day_hi, "low": day_lo,
                "rangePct": r6(day_hi / day_lo - 1.0) if day_hi and day_lo and day_lo > 0 else None,
                "changePct": finite(q.get("changePct")),
            },
            "signal": sig,
            "paperPosition": paper,
            "maxRealizableIntradayInterval": opportunity,
            "yunai": yoverlay.get(code),
        })

    tail_items = []
    if tail:
        tmeta = tail.get("stocks") or {}
        for idx, code in enumerate(tail_codes):
            q = quotes.get(code) or {}; meta = tmeta.get(code) or {}
            sig = entry_signal(meta, q, now, yoverlay.get(code))
            tail_items.append({
                "rank": idx + 1, "code": code, "name": meta.get("name") or q.get("name") or code,
                "sector": meta.get("sector"), "quote": q, "signal": sig,
                "dayStats": {"high": finite(q.get("high")), "low": finite(q.get("low")), "changePct": finite(q.get("changePct"))},
                "maxRealizableIntradayInterval": max_ordered_profit(timeshares.get(code) or []),
            })

    payload = {
        "schemaVersion": 1,
        "generatedAt": now.isoformat(timespec="seconds"),
        "marketDate": day,
        "phase": ph,
        "refreshIntervalMin": 5,
        "sourceMode": source_mode,
        "officialSourceDate": (source or {}).get("date"),
        "officialStrategyVersion": (source or {}).get("strategyVersion"),
        "executionRules": {
            "entry": "09:40后才允许BUY_ZONE；过度高开/接近日高不追；要求价格区间+资金确认",
            "paperFill": "首次进入BUY_ZONE的Top3按观察价+10bp不利滑点模拟",
            "sell": "普通A股T+1；之后按-3.5%止损、+10%止盈、峰值>=6%后回撤2.5%移动止盈、14:45弱势退出",
            "intradayInterval": "Yunai分时按时序计算先低后高最大区间；不是事后简单日高/日低相除",
            "note": "这是规则化交易决策支持/模拟跟踪，不会自动下单，也不保证成交或收益。",
        },
        "officialCandidates": ranked,
        "tailChannel": {"date": tail.get("date"), "status": tail.get("status"), "candidates": tail_items} if tail else None,
        "summary": {
            "candidates": len(ranked),
            "buyZone": sum(1 for x in ranked if (x.get("signal") or {}).get("state") == "BUY_ZONE"),
            "holding": sum(1 for x in ranked if (x.get("signal") or {}).get("state") in ("HOLD", "HOLD_T1")),
            "sellSignals": sum(1 for x in ranked if str((x.get("signal") or {}).get("state", "")).startswith("SELL")),
            "paperOpenPositions": len(positions),
        },
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    intraday = OUT_DIR / "intraday" / day
    intraday.mkdir(parents=True, exist_ok=True)
    slot = now.strftime("%H%M")
    (intraday / f"{slot}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if ph == "CLOSED":
        hist = OUT_DIR / "history"
        hist.mkdir(parents=True, exist_ok=True)
        (hist / f"{day}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"date": day, "phase": ph, **payload["summary"], "officialSourceDate": payload["officialSourceDate"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
