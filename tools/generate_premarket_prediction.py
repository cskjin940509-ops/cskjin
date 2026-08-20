#!/usr/bin/env python3
"""Generate the next-session premarket prediction pool.

This layer is intentionally separate from:
- the immutable end-of-day Official cohort;
- the 09:30+ intraday mainline radar;
- the dynamic shadow portfolio.

It only consumes information that is already available before the target session:
previous Official cohort, prior-day main-flow facts, newly published T+1 margin/ETF
slow-money factors, previous final radar stage/chase state, and history-lab context.
It never consumes target-day auction or continuous-auction quotes.
"""
from __future__ import annotations

import json
import math
import os
from copy import deepcopy
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

import slow_money_factors as slow

CN = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
SNAPS = ROOT / "astock_snapshots" / "index.json"
FACTORS = ROOT / "astock_factors" / "latest.json"
RADAR = ROOT / "astock_radar" / "latest.json"
HISTORY = ROOT / "astock_history" / "latest.json"
OUT = ROOT / "astock_premarket"
LATEST = OUT / "latest.json"
HIST = OUT / "history"
VERSION = "v1.0-premarket-prediction-point-in-time"


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return deepcopy(default)


def finite(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, float(v)))


def rank_pct(values, v):
    xs = sorted(x for x in values if x is not None and math.isfinite(x))
    if v is None or not xs:
        return 50.0
    less = sum(x < v for x in xs)
    eq = sum(x == v for x in xs)
    return 100.0 * (less + 0.5 * eq) / len(xs)


def next_weekday(d):
    d = d + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def resolve_target_day(now: datetime) -> str:
    requested = os.getenv("TARGET_DATE", "").strip()
    if requested:
        return requested
    # Before the opening session, build today's pool. After the close, build a
    # preview for the next weekday; the scheduled 09:05/09:10/09:15 jobs will
    # refresh it again when the new T+1 slow-money data is available.
    if now.time() < time(9, 30):
        return now.date().isoformat()
    if now.time() >= time(15, 0):
        return next_weekday(now.date()).isoformat()
    return now.date().isoformat()


def previous_official(target_day: str):
    arr = read_json(SNAPS, [])
    rows = [x for x in arr if x.get("status") == "Official" and str(x.get("date") or "") < target_day]
    if not rows:
        return None
    return max(rows, key=lambda x: str(x.get("date") or ""))


def derive_chase(code: str, change):
    c = finite(change)
    if c is None:
        return "MEDIUM"
    limit = 30.0 if code.startswith(("8", "9")) else (20.0 if code.startswith(("30", "68")) else 10.0)
    ratio = max(c, 0.0) / limit
    if ratio >= 0.60:
        return "HIGH"
    if ratio >= 0.36:
        return "MEDIUM"
    return "LOW"


def history_context():
    h = read_json(HISTORY, {})
    live_j = ((h.get("edgeTrend") or {}).get("judgement") or {})
    rec = h.get("reconstruction") or {}
    vit = rec.get("vitals") or {}
    return {
        "updatedAt": h.get("updatedAt"),
        "liveSampleConfidenceZh": (h.get("overall") or {}).get("confidenceZh"),
        "liveEdgeStateZh": live_j.get("stateZh"),
        "liveEdgeReasonZh": live_j.get("reasonZh"),
        "reconstructionRecentTrendZh": vit.get("recentTrendZh"),
        "reconstructionAdviceZh": vit.get("currentAdviceZh"),
        "policyZh": "历史形态只作风险背景，不把历史重建收益直接写成买入概率或实盘权重。",
    }


def recompute_with_fresh_slow_money(official: dict, target_day: str, factor_payload: dict):
    stock_map = official.get("stocks") or {}
    rows = []
    flow_vals = [finite((m or {}).get("mainFlowPct")) for m in stock_map.values()]
    for code, raw in stock_map.items():
        x = deepcopy(raw or {})
        x["code"] = str(code)
        if finite(x.get("flowScore")) is None:
            x["flowScore"] = rank_pct(flow_vals, finite(x.get("mainFlowPct")))
        rows.append(x)
    pools0 = official.get("pools") or {}
    pools = {
        "B0": list(pools0.get("B0") or []),
        "B1": [],
        "B2": [],
        "B3": list(pools0.get("B3") or []),
        "B4": list(pools0.get("B4") or []),
    }
    out_rows, out_pools, _ = slow.apply_to_stock_candidates(rows, pools, target_day)
    return {str(x.get("code")): x for x in out_rows if x.get("code")}, out_pools


def pairwise(pools: dict):
    b1, b2, b3 = set(pools.get("B1") or []), set(pools.get("B2") or []), set(pools.get("B3") or [])
    pools = dict(pools)
    pools["B12"] = sorted(b1 & b2)
    pools["B13"] = sorted(b1 & b3)
    pools["B23"] = sorted(b2 & b3)
    return pools


def priority_row(code: str, meta: dict, pools: dict, radar_meta: dict, fresh_slow: bool):
    memberships = [k for k in ("B0", "B1", "B2", "B3", "B4", "B12", "B13", "B23") if code in (pools.get(k) or [])]
    base = finite(meta.get("slowCompositeScore")) if fresh_slow else None
    if base is None:
        base = finite(meta.get("score")) or 50.0
    score = float(base)
    # Membership points are confirmation bonuses, not calibrated probabilities.
    score += 2.0 if "B0" in memberships else 0.0
    score += 5.0 if "B1" in memberships else 0.0
    score += 5.0 if "B2" in memberships else 0.0
    score += 4.0 if "B3" in memberships else 0.0
    score += 2.0 if "B4" in memberships else 0.0
    score += 5.0 if "B12" in memberships else 0.0
    score += 4.0 if "B13" in memberships else 0.0
    score += 4.0 if "B23" in memberships else 0.0

    stage = str(radar_meta.get("mainlineStage") or meta.get("mainlineState") or "")
    stage_bonus = {"EMERGING": 4.0, "CONFIRMING": 5.0, "ESTABLISHED": 1.0, "OVERHEATED": -8.0, "FADING": -10.0}.get(stage, 0.0)
    score += stage_bonus
    chase = str(radar_meta.get("chaseRisk") or meta.get("chaseRisk") or derive_chase(code, meta.get("changePct"))).upper()
    score += {"LOW": 2.0, "MEDIUM": -3.0, "HIGH": -8.0}.get(chase, -1.0)

    change = finite(meta.get("changePct"))
    if change is not None and change > 7.0:
        score -= 5.0
    elif change is not None and change > 4.5:
        score -= 2.0
    priority = round(clamp(score), 2)

    pair_hits = [x for x in ("B12", "B13", "B23") if x in memberships]
    source_hits = [x for x in ("B1", "B2", "B3") if x in memberships]
    if fresh_slow and priority >= 74 and chase != "HIGH" and (pair_hits or len(source_hits) >= 2):
        tier = "一级优先"
    elif priority >= 66 and chase != "HIGH":
        tier = "二级观察"
    else:
        tier = "等竞价确认"

    reasons = []
    if pair_hits:
        reasons.append("/".join(pair_hits) + " 双因子确认")
    elif source_hits:
        reasons.append("+".join(source_hits) + " 单源/多源确认")
    reasons.append(f"基础/综合强度 {base:.1f}")
    if stage:
        reasons.append({"EMERGING":"主线潜在形成", "CONFIRMING":"主线确认中", "ESTABLISHED":"主线已形成", "OVERHEATED":"主线过热", "FADING":"主线衰退"}.get(stage, stage))
    if fresh_slow:
        ms, es = finite(meta.get("marginScore")), finite(meta.get("etfScore"))
        if ms is not None:
            reasons.append(f"两融评分 {ms:.0f}")
        if es is not None:
            reasons.append(f"ETF评分 {es:.0f}")
    else:
        reasons.append("B1/B2等待当日早间更新")

    risks = []
    if not fresh_slow:
        risks.append("慢资金尚未更新到上一交易日")
    if chase == "HIGH":
        risks.append("追高风险高")
    elif chase == "MEDIUM":
        risks.append("追高风险中")
    if change is not None and change > 4.5:
        risks.append(f"上一交易日已上涨{change:.2f}%")
    if not pair_hits:
        risks.append("暂无双因子交叉确认")
    if not risks:
        risks.append("仍需集合竞价与开盘后价格行为确认")

    if chase == "HIGH" or (change is not None and change > 4.5):
        auction = "9:15-9:25必须检查是否高开过度/虚假强势；不直接追价。"
    elif chase == "MEDIUM":
        auction = "等待9:25附近竞价方向与量能确认；弱于预期则降级。"
    else:
        auction = "竞价不明显转弱即可继续观察；9:30后交给盘中雷达和智能实盘重新评分。"

    return {
        "code": code,
        "name": meta.get("name") or code,
        "sector": meta.get("sector") or "未分类",
        "priorityScore": priority,
        "tierZh": tier,
        "memberships": memberships,
        "baseScore": finite(meta.get("score")),
        "slowCompositeScore": finite(meta.get("slowCompositeScore")) if fresh_slow else None,
        "marginScore": finite(meta.get("marginScore")) if fresh_slow else None,
        "etfScore": finite(meta.get("etfScore")) if fresh_slow else None,
        "mainFlowPct": finite(meta.get("mainFlowPct")),
        "mainlineStage": stage or None,
        "chaseRisk": chase,
        "previousChangePct": change,
        "reasonZh": "；".join(reasons),
        "riskZh": "；".join(risks),
        "auctionConfirmZh": auction,
    }


def main() -> int:
    now = datetime.now(CN)
    target = resolve_target_day(now)
    official = previous_official(target)
    if not official:
        raise RuntimeError("没有可用于开盘前预测的上一交易日Official")
    source_day = str(official.get("date") or "")

    factor_payload = read_json(FACTORS, {})
    factor_day = str(factor_payload.get("dataDate") or "")
    fresh_slow = factor_day == source_day

    if fresh_slow:
        stock_map, pools = recompute_with_fresh_slow_money(official, target, factor_payload)
    else:
        stock_map = {str(k): deepcopy(v or {}) for k, v in (official.get("stocks") or {}).items()}
        base_pools = official.get("pools") or {}
        pools = {
            "B0": list(base_pools.get("B0") or []),
            "B1": [],
            "B2": [],
            "B3": list(base_pools.get("B3") or []),
            "B4": list(base_pools.get("B4") or []),
        }
    pools = pairwise(pools)

    radar = read_json(RADAR, {})
    radar_stocks = (radar.get("stocks") or {}) if str(radar.get("date") or "") == source_day else {}
    candidate_codes = set()
    for k in ("B0", "B1", "B2", "B3", "B4", "B12", "B13", "B23"):
        candidate_codes.update(str(x) for x in (pools.get(k) or []) if x)
    if not candidate_codes:
        candidate_codes.update(stock_map.keys())

    rows = []
    for code in candidate_codes:
        meta = stock_map.get(code) or {}
        rows.append(priority_row(code, meta, pools, radar_stocks.get(code) or {}, fresh_slow))
    rows.sort(key=lambda x: (-float(x.get("priorityScore") or 0.0), x.get("code") or ""))
    rows = rows[:15]

    counts = {k: sum(1 for x in rows if x.get("tierZh") == k) for k in ("一级优先", "二级观察", "等竞价确认")}
    state = "ready" if fresh_slow else "waiting-slow-money"
    payload = {
        "schemaVersion": 1,
        "version": VERSION,
        "state": state,
        "targetDate": target,
        "generatedAt": now.isoformat(timespec="seconds"),
        "sourceOfficialDate": source_day,
        "factorDataDate": factor_day or None,
        "slowMoneyFresh": fresh_slow,
        "auctionDataUsed": False,
        "continuousMarketDataUsed": False,
        "pointInTimeCutoffZh": "只使用目标交易日开盘前已发布数据；不读取目标日09:15之后的集合竞价或连续竞价行情。",
        "roleZh": "开盘前提前预测池；不是正式买入池，也不会改写Official、盘中雷达或智能实盘账本。",
        "sourceAvailability": {
            "Official": f"可用：{source_day} Official",
            "B1两融": f"可用：数据日 {factor_day}" if fresh_slow else f"等待更新到 {source_day}；当前文件数据日 {factor_day or '—'}",
            "B2 ETF": f"可用：数据日 {factor_day}" if fresh_slow else f"等待更新到 {source_day}；当前文件数据日 {factor_day or '—'}",
            "B3主力": f"使用 {source_day} Official 冻结主力资金口径",
            "历史形态": "只作风险背景，不直接当作买入概率",
        },
        "pools": pools,
        "historyContext": history_context(),
        "summary": {
            "candidateCount": len(rows),
            "tierCounts": counts,
            "noteZh": "一级优先仍需竞价/开盘确认；若B1/B2尚未更新则不会给出一级优先。",
        },
        "candidates": rows,
    }

    OUT.mkdir(parents=True, exist_ok=True)
    HIST.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    LATEST.write_text(text, encoding="utf-8")
    (HIST / f"{target}.json").write_text(text, encoding="utf-8")
    print(json.dumps({
        "state": state,
        "targetDate": target,
        "sourceOfficialDate": source_day,
        "factorDataDate": factor_day or None,
        "slowMoneyFresh": fresh_slow,
        "candidates": len(rows),
        "tiers": counts,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
