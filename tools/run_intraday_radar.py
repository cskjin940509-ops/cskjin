#!/usr/bin/env python3
"""A股全天主线提前雷达。

目标不是等板块已经大涨后再确认，而是在价格尚未充分扩张时识别
“潜在形成 -> 确认中 -> 已成主线”的状态演化。

约束：
- 只使用捕获时已经可获得的数据，不回写未来数据；
- 当日涨幅不作为形成分的正向奖励，而是进入价格延伸/追高惩罚；
- Yunai 由后置脚本作为独立确认层，不在这里偷换资金口径；
- B1/B2 缺失不参与本雷达，也不伪造。
"""
from __future__ import annotations

import json
import math
import os
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path

import run_daily_strategy_fast as base
import run_tail_decision as tail
import run_tail_rolling_reliable as reliable

CN = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "astock_radar"
LATEST = OUT / "latest.json"
INTRADAY = OUT / "intraday"
HISTORY = OUT / "history"
VERSION = "v2.6-early-mainline-radar-auditable"


def finite(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def pct_rank(values, value):
    xs = sorted(x for x in values if x is not None)
    if value is None or not xs:
        return 50.0
    return 100.0 * (sum(x < value for x in xs) + 0.5 * sum(x == value for x in xs)) / len(xs)


def clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, float(v)))


def slot_for(now):
    if now.time() >= dtime(15, 0):
        return "1500"
    minute = (now.minute // 5) * 5
    return f"{now.hour:02d}{minute:02d}"


def market_window(now):
    t = now.time()
    return (dtime(9, 25) <= t <= dtime(11, 35)) or (dtime(12, 55) <= t <= dtime(15, 30))


def load_previous(day):
    if not LATEST.exists():
        return {}
    try:
        obj = json.loads(LATEST.read_text(encoding="utf-8"))
        return obj if obj.get("date") == day else {}
    except Exception:
        return {}


def build_market(now):
    if now.time() >= dtime(15, 0):
        return reliable.build_payload_market_aware(now)
    return tail.build_payload(now)


def price_extension_penalty(change_pct):
    """形成雷达不奖励当日涨幅；涨得越充分，入场价值越低。"""
    c = finite(change_pct)
    if c is None:
        return 5.0, "MEDIUM"
    up = max(c, 0.0)
    if up >= 8.0:
        return 38.0, "HIGH"
    if up >= 6.0:
        return 30.0, "HIGH"
    if up >= 4.0:
        return 20.0, "HIGH"
    if up >= 2.5:
        return 10.0, "MEDIUM"
    if up >= 1.2:
        return 4.0, "LOW"
    return 0.0, "LOW"


def board_history(board, benchmark):
    try:
        return base.board_hist(board, benchmark)
    except Exception:
        return {"rs20": None, "rs60": None, "mta": "历史趋势未同步", "mtaScore": 50.0}


def stage_from(score, chase, previous_stage, breadth, flow_pct, breadth_delta, flow_delta):
    if previous_stage in ("EMERGING", "CONFIRMING", "ESTABLISHED"):
        if (breadth_delta is not None and breadth_delta <= -18.0) and (flow_delta is not None and flow_delta < -3.0):
            return "FADING"
    if chase == "HIGH" and score >= 70:
        return "OVERHEATED"
    if score >= 78 and breadth >= 58:
        return "ESTABLISHED"
    if score >= 68 and breadth >= 52:
        return "CONFIRMING"
    if score >= 58:
        return "EMERGING"
    return "RADAR"


def iso_minutes(a, b):
    try:
        da = datetime.fromisoformat(a)
        db = datetime.fromisoformat(b)
        return max(0, int((db - da).total_seconds() // 60))
    except Exception:
        return None


def score_boards(payload, previous, now):
    all_boards = []
    for kind in ("industry", "concept"):
        for b in ((payload.get("boardHeatmap") or {}).get(kind) or []):
            if not b.get("boardCode") or not b.get("name"):
                continue
            row = dict(b)
            row["kind"] = kind
            row["breadthPct"] = finite(row.get("breadthPct")) or 50.0
            all_boards.append(row)
    if not all_boards:
        return []

    flows = [finite(x.get("mainFlowPct")) for x in all_boards]
    amounts = [finite(x.get("amount")) for x in all_boards]
    # 预选完全不以当日涨幅作为正向奖励。
    for b in all_boards:
        flow_rank = pct_rank(flows, finite(b.get("mainFlowPct")))
        amount_rank = pct_rank(amounts, finite(b.get("amount")))
        ext_pen, _ = price_extension_penalty(b.get("changePct"))
        b["precursorScore"] = 0.48 * b["breadthPct"] + 0.34 * flow_rank + 0.18 * amount_rank - 0.55 * ext_pen
    preselected = sorted(all_boards, key=lambda x: x["precursorScore"], reverse=True)[:36]

    try:
        benchmark = base.trend(base.kline("1.000300"))
    except Exception:
        benchmark = {"r20": 0.0, "r60": 0.0}

    histories = {}
    with ThreadPoolExecutor(max_workers=12) as ex:
        futures = {ex.submit(board_history, b, benchmark): b["boardCode"] for b in preselected}
        for future in as_completed(futures):
            histories[futures[future]] = future.result()

    rs_values = [finite((histories.get(b["boardCode"]) or {}).get("rs20")) for b in preselected]
    prev_map = {str(x.get("boardCode")): x for x in (previous.get("mainlines") or []) if x.get("boardCode")}
    current_flow_values = [finite(x.get("mainFlowPct")) for x in preselected]
    current_amount_values = [finite(x.get("amount")) for x in preselected]
    rows = []
    stamp = now.isoformat(timespec="seconds")

    for b in preselected:
        h = histories.get(b["boardCode"]) or {}
        prev = prev_map.get(str(b["boardCode"])) or {}
        breadth = finite(b.get("breadthPct")) or 50.0
        flow_pct = finite(b.get("mainFlowPct"))
        amount = finite(b.get("amount"))
        rs20 = finite(h.get("rs20"))
        rs_rank = pct_rank(rs_values, rs20)
        flow_rank = pct_rank(current_flow_values, flow_pct)
        amount_rank = pct_rank(current_amount_values, amount)
        prev_breadth = finite(prev.get("breadthPct"))
        prev_flow = finite(prev.get("mainFlowPct"))
        breadth_delta = breadth - prev_breadth if prev_breadth is not None else None
        flow_delta = flow_pct - prev_flow if flow_pct is not None and prev_flow is not None else None

        breadth_improve = clamp(50.0 + (breadth_delta or 0.0) * 2.2)
        flow_improve = clamp(50.0 + (flow_delta or 0.0) * 5.0)
        low_extension = clamp(100.0 - max(finite(b.get("changePct")) or 0.0, 0.0) * 13.0)
        accumulation = 0.38 * breadth + 0.28 * flow_rank + 0.17 * breadth_improve + 0.10 * flow_improve + 0.07 * low_extension

        previous_stage = prev.get("stage") or "RADAR"
        persistence = 65.0 if previous_stage in ("EMERGING", "CONFIRMING", "ESTABLISHED") else 50.0
        if finite(prev.get("formationScore")) is not None and finite(prev.get("formationScore")) >= 58:
            persistence = 78.0
        mta_score = finite(h.get("mtaScore")) or 50.0
        ext_pen, chase = price_extension_penalty(b.get("changePct"))

        raw = (
            0.27 * rs_rank
            + 0.20 * breadth
            + 0.19 * flow_rank
            + 0.12 * mta_score
            + 0.10 * accumulation
            + 0.07 * persistence
            + 0.05 * amount_rank
        )
        formation = clamp(raw - ext_pen)
        stage = stage_from(formation, chase, previous_stage, breadth, flow_pct, breadth_delta, flow_delta)

        first_emerging = prev.get("firstEmergingAt")
        first_confirming = prev.get("firstConfirmingAt")
        first_established = prev.get("firstEstablishedAt")
        if stage in ("EMERGING", "CONFIRMING", "ESTABLISHED", "OVERHEATED") and not first_emerging:
            first_emerging = stamp
        if stage in ("CONFIRMING", "ESTABLISHED", "OVERHEATED") and not first_confirming:
            first_confirming = stamp
        if stage in ("ESTABLISHED", "OVERHEATED") and not first_established:
            first_established = stamp
        lead = None
        if first_emerging:
            lead = iso_minutes(first_emerging, first_established or stamp)

        rows.append({
            "boardCode": str(b.get("boardCode")),
            "name": b.get("name"),
            "type": "行业" if b.get("kind") == "industry" else "概念",
            "stage": stage,
            "formationScore": round(formation, 2),
            "accumulationScore": round(accumulation, 2),
            "priceExtensionPenalty": round(ext_pen, 2),
            "chaseRisk": chase,
            "changePct": finite(b.get("changePct")),
            "amount": amount,
            "mainNetFlow": finite(b.get("mainNetFlow")),
            "mainFlowPct": flow_pct,
            "breadthPct": round(breadth, 2),
            "breadthDelta5m": round(breadth_delta, 2) if breadth_delta is not None else None,
            "flowPctDelta5m": round(flow_delta, 2) if flow_delta is not None else None,
            "RS20": round(rs20 * 100.0, 2) if rs20 is not None else None,
            "RS60": round(finite(h.get("rs60")) * 100.0, 2) if finite(h.get("rs60")) is not None else None,
            "MTA": h.get("mta"),
            "firstEmergingAt": first_emerging,
            "firstConfirmingAt": first_confirming,
            "firstEstablishedAt": first_established,
            "leadTimeMin": lead,
            "reasonZh": f"形成分{formation:.0f}；吸筹{accumulation:.0f}；上涨扩散{breadth:.0f}%；资金强度{flow_pct if flow_pct is not None else 0:+.1f}%；价格延伸扣分{ext_pen:.0f}",
        })

    # 去重近似行业/概念名称，优先保留形成分高的。
    rows.sort(key=lambda x: (x["formationScore"], x["accumulationScore"]), reverse=True)
    selected = []
    for x in rows:
        base_name = str(x["name"]).replace("Ⅱ", "").replace("Ⅲ", "").replace("行业", "").replace("概念", "")
        if any(base_name in str(y["name"]) or str(y["name"]).replace("Ⅱ", "").replace("Ⅲ", "") in base_name for y in selected):
            continue
        selected.append(x)
        if len(selected) >= 10:
            break
    return selected


def stock_chase(code, change_pct):
    c = finite(change_pct)
    if c is None:
        return "MEDIUM", 8.0
    limit = 30.0 if str(code).startswith(("8", "9")) else (20.0 if str(code).startswith(("30", "68")) else 10.0)
    ratio = max(c, 0.0) / limit
    if ratio >= 0.60:
        return "HIGH", 32.0
    if ratio >= 0.36:
        return "MEDIUM", 14.0
    if ratio >= 0.18:
        return "LOW", 5.0
    return "LOW", 0.0


def score_stocks(mainlines):
    eligible = [x for x in mainlines if x.get("stage") in ("EMERGING", "CONFIRMING", "ESTABLISHED", "OVERHEATED")]
    if not eligible:
        return {}, {"EarlyWatch": [], "EarlyEntry": [], "Confirming": [], "EstablishedLowChase": [], "AvoidChase": []}
    board_inputs = [{
        "boardCode": x["boardCode"],
        "name": x["name"],
        "score": x["formationScore"],
        "status": "确认主线" if x["stage"] in ("ESTABLISHED", "OVERHEATED") else "候选主线",
    } for x in eligible[:6]]
    try:
        stocks, _ = base.choose_stocks(board_inputs)
    except Exception:
        return {}, {"EarlyWatch": [], "EarlyEntry": [], "Confirming": [], "EstablishedLowChase": [], "AvoidChase": []}

    sector_map = {x["name"]: x for x in mainlines}
    out = {}
    pools = {"EarlyWatch": [], "EarlyEntry": [], "Confirming": [], "EstablishedLowChase": [], "AvoidChase": []}
    for s in stocks[:60]:
        code = str(s.get("code") or "")
        if not code:
            continue
        sec = sector_map.get(s.get("sector")) or {}
        stage = sec.get("stage") or "RADAR"
        formation = finite(sec.get("formationScore")) or finite(s.get("sectorScore")) or 50.0
        base_score = finite(s.get("score")) or 50.0
        flow_score = finite(s.get("flowScore")) or 50.0
        chase, penalty = stock_chase(code, s.get("changePct"))
        early = clamp(0.42 * base_score + 0.30 * flow_score + 0.28 * formation - penalty)
        if chase == "HIGH":
            action = "等待回踩，禁止追高"
            pools["AvoidChase"].append(code)
        elif stage == "EMERGING" and early >= 62:
            action = "潜在主线，提前介入候选"
            pools["EarlyEntry"].append(code)
        elif stage == "CONFIRMING" and early >= 64:
            action = "主线确认中，等待触发介入"
            pools["Confirming"].append(code)
            pools["EarlyEntry"].append(code)
        elif stage == "ESTABLISHED" and chase == "LOW" and early >= 65:
            action = "主线已成，低追高风险观察"
            pools["EstablishedLowChase"].append(code)
        else:
            action = "提前观察"
            if early >= 55:
                pools["EarlyWatch"].append(code)

        out[code] = {
            "code": code,
            "name": s.get("name"),
            "sector": s.get("sector"),
            "mainlineStage": stage,
            "price": finite(s.get("price")),
            "changePct": finite(s.get("changePct")),
            "amount": finite(s.get("amount")),
            "turnover": finite(s.get("turnover")),
            "mainNetFlow": finite(s.get("mainNetFlow")),
            "mainFlowPct": finite(s.get("mainFlowPct")),
            "baseScore": round(base_score, 2),
            "flowScore": round(flow_score, 2),
            "mainlineFormationScore": round(formation, 2),
            "earlyEntryScore": round(early, 2),
            "chaseRisk": chase,
            "actionZh": action,
            "RS20": round(finite(s.get("rs20")) * 100.0, 2) if finite(s.get("rs20")) is not None else None,
            "MTA": s.get("mta"),
            "reasonZh": f"提前分{early:.0f}；主线形成{formation:.0f}；资金{flow_score:.0f}；追高风险{ {'LOW':'低','MEDIUM':'中','HIGH':'高'}.get(chase,'中') }",
        }

    for k in pools:
        pools[k] = sorted(set(pools[k]), key=lambda c: out.get(c, {}).get("earlyEntryScore", 0), reverse=True)[:15]
    return out, pools


def main():
    now = datetime.now(CN)
    day = now.strftime("%Y-%m-%d")
    allow_any = os.getenv("ALLOW_ANY_TIME", "0") == "1"
    if now.weekday() >= 5:
        print(json.dumps({"state": "skip", "reason": "周末", "date": day}, ensure_ascii=False))
        return
    if not allow_any and not market_window(now):
        print(json.dumps({"state": "skip", "reason": "非A股交易刷新窗口", "capturedAt": now.isoformat(timespec="seconds")}, ensure_ascii=False))
        return

    OUT.mkdir(parents=True, exist_ok=True)
    INTRADAY.mkdir(parents=True, exist_ok=True)
    HISTORY.mkdir(parents=True, exist_ok=True)
    previous = load_previous(day)
    is_final = now.time() >= dtime(15, 0)
    final_path = HISTORY / f"{day}.json"
    if is_final and final_path.exists() and os.getenv("FORCE_REBUILD", "0") != "1":
        existing = json.loads(final_path.read_text(encoding="utf-8"))
        if existing.get("status") == "RadarFinal":
            LATEST.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps({"state": "radar-final-immutable", "date": day}, ensure_ascii=False))
            return

    payload, quote_age = build_market(now)
    mainlines = score_boards(payload, previous, now)
    stocks, pools = score_stocks(mainlines)
    slot = slot_for(now)
    result = {
        "schemaVersion": 2,
        "date": day,
        "status": "RadarFinal" if is_final else "RadarLive",
        "strategyVersion": VERSION,
        "phaseZh": "收盘冻结" if is_final else "全天滚动",
        "capturedAt": now.isoformat(timespec="seconds"),
        "scheduledSlot": slot,
        "refreshIntervalMin": 5,
        "marketQuoteAgeSec": round(quote_age, 1),
        "dataSource": "腾讯指数行情 + 东方财富板块/个股 + 历史日线",
        "mainlines": mainlines,
        "stocks": stocks,
        "pools": pools,
        "marketSnapshot": payload.get("marketSnapshot"),
        "factorAvailability": {
            "价格/成交/板块广度": "可用",
            "东方财富主力资金": "可用时参与",
            "Yunai独立大单资金": "由后置独立确认层补充",
            "两融B1": "未接入真实专用数据，不伪造",
            "ETF一级申赎B2": "未接入真实专用数据，不伪造",
        },
        "scoreMeaningZh": "形成分是研究排序分，不代表上涨概率；当日涨幅只进入价格延伸惩罚，不作为形成分正向奖励。",
        "note": "从开盘起每5分钟滚动识别潜在主线和提前介入候选；14:30以后进入尾盘执行/确认阶段，15:00形成当日最终雷达快照。",
    }
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    LATEST.write_text(text, encoding="utf-8")
    if is_final:
        final_path.write_text(text, encoding="utf-8")
    else:
        d = INTRADAY / day
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{slot}.json").write_text(text, encoding="utf-8")

    print(json.dumps({
        "state": "radar-final-frozen" if is_final else "radar-live-updated",
        "date": day,
        "slot": slot,
        "mainlines": [{"name": x.get("name"), "stage": x.get("stage"), "score": x.get("formationScore")} for x in mainlines[:5]],
        "EarlyEntry": len(pools.get("EarlyEntry") or []),
        "EarlyWatch": len(pools.get("EarlyWatch") or []),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
