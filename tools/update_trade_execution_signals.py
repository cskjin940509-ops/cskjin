#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path

import update_market_gateway as gw
import yunai_tail_overlay as yo

CN = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "astock_execution"
LATEST = OUT / "latest.json"
STATE = OUT / "state.json"
INTRADAY = OUT / "intraday"
HISTORY = OUT / "history"
TAIL = ROOT / "astock_tail" / "latest.json"
SNAPS = ROOT / "astock_snapshots" / "index.json"
VERSION = "v1.0-execution-assistant-5m"


def finite(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def pct(a, b):
    a, b = finite(a), finite(b)
    if a is None or b in (None, 0):
        return None
    return (a / b - 1.0) * 100.0


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def symbol(code: str) -> str:
    if code.startswith(("8", "9")):
        return "bj" + code
    return ("sh" if code.startswith(("5", "6")) else "sz") + code


def limit_pct(code: str) -> float:
    if code.startswith(("8", "9")):
        return 30.0
    if code.startswith(("30", "68")):
        return 20.0
    return 10.0


def phase(now: datetime) -> str:
    t = now.time()
    if t < dtime(9, 15): return "盘前"
    if t < dtime(9, 25): return "开盘集合竞价"
    if t < dtime(9, 30): return "开盘等待"
    if t < dtime(11, 30): return "上午连续竞价"
    if t < dtime(13, 0): return "午间休市"
    if t < dtime(14, 30): return "下午连续竞价"
    if t < dtime(14, 57): return "尾盘连续竞价"
    if t < dtime(15, 0): return "收盘集合竞价"
    return "已收盘"


def market_open(now: datetime) -> bool:
    t = now.time()
    return (dtime(9, 30) <= t < dtime(11, 30)) or (dtime(13, 0) <= t < dtime(15, 0))


def entry_window(now: datetime, source: str) -> bool:
    t = now.time()
    if source == "TailCore":
        return dtime(14, 30) <= t < dtime(14, 57)
    # Previous Official continuation: avoid the first five minutes and the closing rush.
    return (dtime(9, 35) <= t < dtime(10, 30)) or (dtime(13, 10) <= t < dtime(14, 20))


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def latest_prior_official(today: str):
    arr = read_json(SNAPS, [])
    rows = [x for x in arr if x.get("status") == "Official" and str(x.get("date") or "") < today]
    return max(rows, key=lambda x: x.get("date", "")) if rows else None


def same_day_tail(today: str):
    t = read_json(TAIL, {})
    return t if t.get("date") == today and t.get("status") in ("TailLive", "TailFinal", "TailDecision") else None


def build_universe(today: str):
    out = {}
    prior = latest_prior_official(today)
    if prior:
        pools = prior.get("pools") or {}
        preferred = pools.get("B4") or pools.get("B3") or pools.get("B0") or []
        for code in preferred[:20]:
            c = str(code)
            meta = (prior.get("stocks") or {}).get(c) or {}
            out[c] = {
                "source": "Official",
                "sourceDate": prior.get("date"),
                "name": meta.get("name"),
                "sector": meta.get("sector"),
                "score": finite(meta.get("score")),
                "mainFlowPct": finite(meta.get("mainFlowPct")),
                "referencePrice": finite(meta.get("selectionPrice")),
                "pools": meta.get("pools") or [p for p, vals in pools.items() if c in (vals or [])],
            }
    tail = same_day_tail(today)
    if tail:
        pools = tail.get("pools") or {}
        for code in (pools.get("TailCore") or [])[:10]:
            c = str(code)
            meta = (tail.get("stocks") or {}).get(c) or {}
            cur = out.setdefault(c, {})
            cur.update({
                "source": "TailCore",
                "sourceDate": today,
                "name": meta.get("name") or cur.get("name"),
                "sector": meta.get("sector") or cur.get("sector"),
                "score": finite(meta.get("tailScore")) or finite(meta.get("baseScore")) or cur.get("score"),
                "mainFlowPct": finite(meta.get("mainFlowPct")) if finite(meta.get("mainFlowPct")) is not None else cur.get("mainFlowPct"),
                "referencePrice": finite(meta.get("price")) or cur.get("referencePrice"),
                "pools": meta.get("pools") or ["TailCore"],
                "tailTradable": meta.get("tailTradable", True),
                "tailRisk": meta.get("risk"),
            })
    return out, prior, tail


def timeshare_rows(codes):
    supported = [c for c in codes if not c.startswith(("8", "9"))]
    if not supported:
        return {}
    result = {}
    for i in range(0, len(supported), 10):
        batch = supported[i:i+10]
        st, _, payload = yo.post(yo.PREFIX + "/time-share-quotes", {"symbols": batch})
        if not (200 <= st < 300):
            continue
        mp = yo.symbol_map(payload)
        for code in batch:
            raw = mp.get(code)
            if isinstance(raw, dict):
                rows = None
                for k in ("items", "quotes", "points", "timeShares", "list", "data", "rows"):
                    if isinstance(raw.get(k), list):
                        rows = raw.get(k); break
                if rows is None:
                    rows = [raw]
            elif isinstance(raw, list):
                rows = raw
            else:
                rows = []
            norm = []
            for x in rows:
                if not isinstance(x, dict):
                    continue
                pr = yo.scalar(x, ("price", "lastPrice", "close", "currentPrice", "latestPrice"))
                av = yo.scalar(x, ("avgPrice", "averagePrice", "vwap", "average"))
                tm = x.get("time") or x.get("tradeTime") or x.get("datetime") or x.get("dateTime") or x.get("timestamp")
                if pr is None and av is None:
                    continue
                norm.append({"price": pr, "avgPrice": av, "time": str(tm) if tm is not None else None})
            result[code] = norm
    return result


def time_key(v):
    if not v:
        return None
    s = str(v)
    # Accept HH:mm, HH:mm:ss, ISO, compact date-time.
    if "T" in s:
        s = s.split("T", 1)[1]
    if " " in s:
        s = s.split(" ")[-1]
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) >= 14:
        return digits[-6:]
    if len(digits) >= 6:
        return digits[:6]
    if len(digits) >= 4:
        return digits[:4] + "00"
    return None


def current_vwap(rows):
    for x in reversed(rows or []):
        v = finite(x.get("avgPrice"))
        if v is not None and v > 0:
            return v
    return None


def quote_map(codes):
    syms = [symbol(c) for c in codes]
    raw = gw.tencent_quotes(syms) if syms else {}
    return {c: raw.get(symbol(c)) for c in codes}


def load_state(today: str):
    s = read_json(STATE, {})
    if s.get("date") != today:
        return {"date": today, "stocks": {}}
    return s


def entry_score(code, meta, q, vwap, yunai):
    price = finite((q or {}).get("price"))
    high = finite((q or {}).get("high"))
    low = finite((q or {}).get("low"))
    chg = finite((q or {}).get("changePct"))
    if price is None or high is None or low is None or low <= 0 or high < low:
        return -999, []
    rng = max(high - low, 1e-9)
    pos = (price - low) / rng
    score = 0.0
    reasons = []
    if meta.get("source") == "TailCore":
        score += 30; reasons.append("尾盘核心池")
    elif "B4" in (meta.get("pools") or []):
        score += 22; reasons.append("昨日综合确认池")
    elif "B3" in (meta.get("pools") or []):
        score += 12; reasons.append("昨日主力资金池")
    flow = finite(meta.get("mainFlowPct"))
    if flow is not None:
        if flow >= 8: score += 15; reasons.append("主力资金强")
        elif flow >= 3: score += 9; reasons.append("主力资金正向")
        elif flow < 0: score -= 10; reasons.append("主力资金偏弱")
    large = finite((((yunai or {}).get("capital") or {}).get("largeNetInflow")))
    total = finite((((yunai or {}).get("capital") or {}).get("totalNetInflow")))
    if large is not None:
        if large > 0: score += 10; reasons.append("云AI大单净流入为正")
        elif large < 0: score -= 8; reasons.append("云AI大单净流入为负")
    elif total is not None and total > 0:
        score += 5; reasons.append("云AI总资金净流入为正")
    if vwap is not None:
        if price >= vwap * 0.998: score += 10; reasons.append("价格在分时均价附近或上方")
        elif price < vwap * 0.985: score -= 12; reasons.append("价格明显弱于分时均价")
    if 0.35 <= pos <= 0.72:
        score += 15; reasons.append("日内位置适中")
    elif 0.25 <= pos <= 0.82:
        score += 6
    elif pos > 0.9:
        score -= 14; reasons.append("接近日内高位")
    elif pos < 0.18:
        score -= 14; reasons.append("接近日内低位")
    lim = limit_pct(code)
    if chg is not None:
        if -1.5 <= chg <= min(5.0, lim * 0.45):
            score += 10; reasons.append("涨幅未过热")
        elif chg >= lim * 0.68:
            score -= 25; reasons.append("涨幅过大，追高风险")
        elif chg <= -4:
            score -= 20; reasons.append("当日走势偏弱")
    if meta.get("tailTradable") is False:
        score -= 100; reasons.append(str(meta.get("tailRisk") or "尾盘可交易性差"))
    return round(score, 2), reasons


def entry_zone(price, high, low, vwap):
    if None in (price, high, low) or low <= 0 or high < low:
        return None, None
    if vwap is not None and low <= vwap <= high:
        a = max(low, vwap * 0.995)
        b = min(high, vwap * 1.008)
        if a <= b:
            return round(a, 3), round(b, 3)
    rng = high - low
    return round(low + rng * 0.38, 3), round(low + rng * 0.62, 3)


def risk_levels(code, ref, high, low):
    if ref is None or ref <= 0:
        return None, None, None, None
    day_range = pct(high, low) if high is not None and low not in (None, 0) else None
    cap = 6.5 if limit_pct(code) >= 20 else 4.5
    risk = clamp((day_range or 3.5) * 0.55, 2.0, cap)
    stop = ref * (1.0 - risk / 100.0)
    t1 = ref * (1.0 + risk / 100.0)
    t2 = ref * (1.0 + 2.0 * risk / 100.0)
    return round(risk, 2), round(stop, 3), round(t1, 3), round(t2, 3)


def actionable_label(now, meta, score, q, vwap):
    if not market_open(now):
        return "非交易时段", "等待开市"
    if phase(now) == "收盘集合竞价":
        return "不新增追价", "14:57后进入收盘集合竞价，避免把连续竞价规则直接套用"
    if not entry_window(now, meta.get("source") or "Official"):
        return "非首选介入时段", "继续观察，等待策略介入窗口"
    price = finite((q or {}).get("price")); high = finite((q or {}).get("high")); low = finite((q or {}).get("low")); chg = finite((q or {}).get("changePct"))
    if None in (price, high, low):
        return "数据不足", "缺少可靠实时价格"
    pos = (price - low) / max(high - low, 1e-9)
    if chg is not None and chg >= limit_pct(str(meta.get("code") or "")) * 0.68:
        return "等待回踩", "涨幅较大，不追高"
    if pos > 0.86:
        return "等待回踩", "价格接近日内高位"
    if pos < 0.20 or (vwap is not None and price < vwap * 0.985):
        return "等待企稳", "价格结构偏弱"
    if score >= 70:
        return "介入候选", "价格、资金与池强度达到规则阈值"
    if score >= 55:
        return "观察确认", "部分条件满足，尚未达到介入阈值"
    return "暂不介入", "当前共振条件不足"


def main():
    now = datetime.now(CN)
    today = now.strftime("%Y-%m-%d")
    dry = os.getenv("DRY_RUN", "0") == "1"
    allow_any = os.getenv("ALLOW_ANY_TIME", "0") == "1" or dry
    if now.weekday() >= 5:
        print(json.dumps({"state":"skip","reason":"weekend"}, ensure_ascii=False)); return
    if not allow_any and not (dtime(9, 30) <= now.time() <= dtime(15, 5)):
        print(json.dumps({"state":"skip","reason":"outside-execution-window","time":now.isoformat(timespec="seconds")}, ensure_ascii=False)); return

    universe, prior, tail = build_universe(today)
    codes = list(universe.keys())
    if not codes:
        print(json.dumps({"state":"skip","reason":"no-candidate-universe","date":today}, ensure_ascii=False)); return
    for c in codes:
        universe[c]["code"] = c

    quotes = quote_map(codes)
    try:
        yunai = yo.fetch_stock_overlay(codes)
    except Exception:
        yunai = {}
    try:
        ts = timeshare_rows(codes)
    except Exception:
        ts = {}

    state = load_state(today)
    previous = read_json(LATEST, {}) if LATEST.exists() else {}
    rows = {}
    for code, meta in universe.items():
        q = quotes.get(code) or {}
        price = finite(q.get("price")); high = finite(q.get("high")); low = finite(q.get("low")); chg = finite(q.get("changePct"))
        vwap = current_vwap(ts.get(code) or [])
        score, reasons = entry_score(code, meta, q, vwap, yunai.get(code) or {})
        action, action_reason = actionable_label(now, meta, score, q, vwap)
        ez_lo, ez_hi = entry_zone(price, high, low, vwap)
        ref = price if action == "介入候选" else ((ez_lo + ez_hi) / 2.0 if ez_lo is not None and ez_hi is not None else price)
        risk_pct, stop, target1, target2 = risk_levels(code, ref, high, low)

        ss = state["stocks"].setdefault(code, {})
        if action == "介入候选" and price is not None and ss.get("signalPrice") is None:
            ss["signalAt"] = now.isoformat(timespec="seconds")
            ss["signalPrice"] = price
            ss["observedHigh"] = price
            ss["observedLow"] = price
        if ss.get("signalPrice") is not None and price is not None:
            ss["observedHigh"] = max(finite(ss.get("observedHigh")) or price, price)
            ss["observedLow"] = min(finite(ss.get("observedLow")) or price, price)

        signal_price = finite(ss.get("signalPrice"))
        signal_time = time_key(ss.get("signalAt"))
        best_time = worst_time = None
        precision = "5分钟采样"
        if signal_price is not None and signal_time and ts.get(code):
            after = [x for x in ts[code] if time_key(x.get("time")) and time_key(x.get("time")) >= signal_time and finite(x.get("price")) is not None]
            if after:
                hirow = max(after, key=lambda x: finite(x.get("price")) or -1)
                lorow = min(after, key=lambda x: finite(x.get("price")) or 1e99)
                ss["observedHigh"] = max(finite(ss.get("observedHigh")) or signal_price, finite(hirow.get("price")) or signal_price)
                ss["observedLow"] = min(finite(ss.get("observedLow")) or signal_price, finite(lorow.get("price")) or signal_price)
                best_time = hirow.get("time"); worst_time = lorow.get("time"); precision = "分时数据"
        mfe = pct(ss.get("observedHigh"), signal_price) if signal_price is not None else None
        mae = pct(ss.get("observedLow"), signal_price) if signal_price is not None else None

        range_pos = None
        if price is not None and high is not None and low is not None and high > low:
            range_pos = (price - low) / (high - low) * 100.0
        day_range = pct(high, low)
        prevrow = ((previous.get("stocks") or {}).get(code) or {})
        prior_flow = finite(prevrow.get("mainFlowPct"))
        flow_now = finite(meta.get("mainFlowPct"))
        flow_weakening = prior_flow is not None and flow_now is not None and flow_now < prior_flow - 3.0
        ytotal = finite((((yunai.get(code) or {}).get("capital") or {}).get("totalNetInflow")))
        below_vwap = vwap is not None and price is not None and price < vwap * 0.99
        holding = "持有观察"
        holding_reason = "未触发明确保护条件"
        if signal_price is not None and price is not None:
            _, sig_stop, sig_t1, sig_t2 = risk_levels(code, signal_price, high, low)
            if sig_stop is not None and price <= sig_stop:
                holding = "保护性离场"; holding_reason = "价格触及模型保护位"
            elif sig_t2 is not None and price >= sig_t2:
                holding = "分批止盈"; holding_reason = "达到约2R收益区"
            elif sig_t1 is not None and price >= sig_t1 and (range_pos or 0) >= 85:
                holding = "保护利润"; holding_reason = "达到约1R且接近日内高位"
            elif below_vwap and (range_pos or 100) < 30 and (flow_weakening or (ytotal is not None and ytotal < 0)):
                holding = "考虑减仓"; holding_reason = "价格弱于分时均价且资金走弱"

        rows[code] = {
            "code": code,
            "name": meta.get("name") or q.get("name") or code,
            "sector": meta.get("sector"),
            "source": meta.get("source"),
            "sourceDate": meta.get("sourceDate"),
            "pools": meta.get("pools") or [],
            "score": meta.get("score"),
            "entryScore": score,
            "entryAction": action,
            "entryReason": action_reason,
            "signalReasons": reasons,
            "holdingAction": holding,
            "holdingReason": holding_reason,
            "price": price,
            "changePct": chg,
            "dayHigh": high,
            "dayLow": low,
            "dayRangePct": round(day_range, 3) if day_range is not None else None,
            "rangePositionPct": round(range_pos, 2) if range_pos is not None else None,
            "vwap": round(vwap, 3) if vwap is not None else None,
            "entryZoneLow": ez_lo,
            "entryZoneHigh": ez_hi,
            "riskPct": risk_pct,
            "protectiveStop": stop,
            "target1R": target1,
            "target2R": target2,
            "mainFlowPct": flow_now,
            "yunaiLargeNetInflow": finite((((yunai.get(code) or {}).get("capital") or {}).get("largeNetInflow"))),
            "yunaiTotalNetInflow": ytotal,
            "firstActionableAt": ss.get("signalAt"),
            "firstActionablePrice": signal_price,
            "maxFavorablePctAfterSignal": round(mfe, 3) if mfe is not None else None,
            "maxAdversePctAfterSignal": round(mae, 3) if mae is not None else None,
            "bestObservedTimeAfterSignal": best_time,
            "worstObservedTimeAfterSignal": worst_time,
            "postSignalMetricPrecision": precision if signal_price is not None else None,
            "quoteTime": q.get("quoteTimeRaw") or q.get("quoteTime"),
            "newPositionSellableToday": False,
        }

    ranked = sorted(rows.values(), key=lambda x: (x.get("entryAction") == "介入候选", x.get("entryScore") or -999), reverse=True)
    result = {
        "schemaVersion": 1,
        "strategyVersion": VERSION,
        "date": today,
        "generatedAt": now.isoformat(timespec="seconds"),
        "phase": phase(now),
        "refreshIntervalMin": 5,
        "isMarketOpen": market_open(now),
        "candidateSources": {
            "priorOfficialDate": prior.get("date") if prior else None,
            "tailStatus": tail.get("status") if tail else None,
            "tailCapturedAt": tail.get("capturedAt") if tail else None,
        },
        "stocks": {x["code"]: x for x in ranked},
        "ranking": [x["code"] for x in ranked],
        "rules": {
            "newEntry": "昨日正式综合池用于次日延续观察；当日14:30后TailCore用于尾盘新仓。介入信号要求价格位置、资金和池强度共振，并避开明显追高。",
            "holding": "持仓提示依据模型保护位、1R/2R、分时均价和资金变化；未录入真实持仓时仅作结构参考。",
            "tPlusOne": "普通A股当日新买入仓位不可按本模型假设当日卖出；卖出提示仅适用于已有可卖持仓。",
            "closingAuction": "14:57-15:00为收盘集合竞价阶段，不生成连续竞价式追价信号。",
            "range": "日内最高/最低是事实区间；信号后最大浮盈/回撤只使用信号出现后可观察数据，不用事后全日高低倒推。",
        },
        "disclaimer": "规则化交易辅助，不是保证收益或自动下单系统。信号可能滞后、失效或因流动性/涨跌停/T+1无法成交。",
    }

    if dry:
        print(json.dumps({"state":"dry-run-ok","date":today,"phase":result["phase"],"stocks":len(rows),"entryCandidates":sum(x.get("entryAction")=="介入候选" for x in rows.values())}, ensure_ascii=False))
        return

    OUT.mkdir(parents=True, exist_ok=True)
    INTRADAY.joinpath(today).mkdir(parents=True, exist_ok=True)
    HISTORY.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    LATEST.write_text(text, encoding="utf-8")
    slot = now.strftime("%H%M")
    INTRADAY.joinpath(today, slot + ".json").write_text(text, encoding="utf-8")
    if now.time() >= dtime(15, 0):
        HISTORY.joinpath(today + ".json").write_text(text, encoding="utf-8")
    print(json.dumps({"state":"updated","date":today,"phase":result["phase"],"stocks":len(rows),"entryCandidates":sum(x.get("entryAction")=="介入候选" for x in rows.values())}, ensure_ascii=False))


if __name__ == "__main__":
    main()
