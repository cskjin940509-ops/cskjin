#!/usr/bin/env python3
"""动态历史形态实验室。

只消费已经冻结并持续跟踪的 Official 样本，不改写原始成员名单。
每天随着 stockPerformance / dailySeries 成熟，重新计算：
- 1/5/10/20/60日收益、中位收益、胜率、Alpha；
- MFE / MAE / 最大回撤分布；
- 最佳持有周期；
- 全历史 vs 最近20/60样本 Edge 趋势；
- 不同 Market Regime、股票池的条件表现；
- 可用于 App 图表的事件路径与散点样本。

历史重建样本未来会使用独立 sourceType，不与实时冻结样本混淆。
"""
from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

CN = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS = ROOT / "astock_snapshots" / "index.json"
OUT_DIR = ROOT / "astock_history"
OUT = OUT_DIR / "latest.json"
VERSION = "v2.9-dynamic-pattern-lab-1"
HORIZONS = ["1D", "5D", "10D", "20D", "60D"]
HORIZON_DAYS = {"1D": 1, "5D": 5, "10D": 10, "20D": 20, "60D": 60}


def finite(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def r(v):
    return round(v, 8) if v is not None and math.isfinite(v) else None


def metric(perf, label, field="return"):
    x = (perf or {}).get(label)
    if isinstance(x, dict):
        return finite(x.get(field))
    return finite(x)


def confidence(n):
    if n >= 200:
        return "高"
    if n >= 80:
        return "中"
    if n >= 30:
        return "中低"
    return "低"


def summarize_values(samples, horizon):
    returns, alphas = [], []
    for s in samples:
        p = s["performance"]
        ret = metric(p, horizon, "return")
        if ret is not None:
            returns.append(ret)
        a = metric(p, horizon, "alpha")
        if a is not None:
            alphas.append(a)
    if not returns:
        return {"members": 0, "mature": False}
    return {
        "members": len(returns),
        "mature": True,
        "meanReturn": r(statistics.fmean(returns)),
        "medianReturn": r(statistics.median(returns)),
        "hitRate": r(sum(x > 0 for x in returns) / len(returns)),
        "meanAlpha": r(statistics.fmean(alphas)) if alphas else None,
        "medianAlpha": r(statistics.median(alphas)) if alphas else None,
        "p25": r(sorted(returns)[max(0, int((len(returns)-1)*0.25))]),
        "p75": r(sorted(returns)[max(0, int((len(returns)-1)*0.75))]),
    }


def summarize(samples):
    horizons = {h: summarize_values(samples, h) for h in HORIZONS}
    mfe = [metric(s["performance"], "MFE") for s in samples]
    mae = [metric(s["performance"], "MAE") for s in samples]
    dd = [finite((s["performance"] or {}).get("maxDrawdown")) for s in samples]
    mfe = [x for x in mfe if x is not None]
    mae = [x for x in mae if x is not None]
    dd = [x for x in dd if x is not None]
    return {
        "sampleCount": len(samples),
        "confidenceZh": confidence(len(samples)),
        "horizons": horizons,
        "medianMFE": r(statistics.median(mfe)) if mfe else None,
        "medianMAE": r(statistics.median(mae)) if mae else None,
        "medianMaxDrawdown": r(statistics.median(dd)) if dd else None,
    }


def best_horizon(horizons):
    eligible = []
    for h in HORIZONS:
        x = horizons.get(h) or {}
        n = int(x.get("members") or 0)
        edge = finite(x.get("medianAlpha"))
        if edge is None:
            edge = finite(x.get("medianReturn"))
        if edge is not None and n >= 5:
            eligible.append((edge, HORIZON_DAYS[h], h, n))
    if not eligible:
        return {"horizon": None, "reasonZh": "成熟样本不足，暂不判断最佳持有周期"}
    eligible.sort(reverse=True)
    edge, days, h, n = eligible[0]
    return {"horizon": h, "days": days, "edge": r(edge), "members": n, "reasonZh": f"按成熟样本的中位超额收益选择，当前最优为{days}个交易日"}


def edge_window(samples, count):
    subset = sorted(samples, key=lambda x: (x["date"], x["code"]))[-count:]
    s = summarize(subset)
    five = s["horizons"].get("5D") or {}
    return {
        "requestedSamples": count,
        "actualSamples": len(subset),
        "fiveDayMedianAlpha": five.get("medianAlpha"),
        "fiveDayMedianReturn": five.get("medianReturn"),
        "fiveDayHitRate": five.get("hitRate"),
        "fiveDayMembers": five.get("members", 0),
    }


def trend_judgement(full, recent20, recent60):
    fa = finite(full.get("fiveDayMedianAlpha"))
    r20 = finite(recent20.get("fiveDayMedianAlpha"))
    r60 = finite(recent60.get("fiveDayMedianAlpha"))
    n20 = int(recent20.get("fiveDayMembers") or 0)
    n60 = int(recent60.get("fiveDayMembers") or 0)
    if fa is None or r20 is None or n20 < 8:
        return {"stateZh": "样本不足", "score": 0, "reasonZh": "5日成熟样本不足，暂不对 Edge 强弱下结论"}
    reference = r60 if r60 is not None and n60 >= 15 else fa
    delta = r20 - reference
    if delta >= 0.01:
        return {"stateZh": "近期增强", "score": 1, "delta": r(delta), "reasonZh": "最近20个成熟样本的5日中位超额收益明显高于较长窗口"}
    if delta <= -0.01:
        return {"stateZh": "近期弱化", "score": -1, "delta": r(delta), "reasonZh": "最近20个成熟样本的5日中位超额收益明显低于较长窗口"}
    return {"stateZh": "相对稳定", "score": 0, "delta": r(delta), "reasonZh": "最近20个成熟样本与较长窗口差异暂未达到显著阈值"}


def collect_samples(snapshots):
    out = []
    for snap in snapshots:
        if snap.get("status") != "Official":
            continue
        day = str(snap.get("date") or "")
        stock_perf = snap.get("stockPerformance") or {}
        pools = snap.get("pools") or {}
        meta_map = snap.get("stocks") or {}
        codes = set(meta_map.keys())
        for members in pools.values():
            codes.update(str(x) for x in (members or []) if x)
        for code in sorted(codes):
            perf = stock_perf.get(code) or {}
            if not perf.get("entryDate"):
                continue
            meta = meta_map.get(code) or {}
            memberships = sorted(k for k, values in pools.items() if code in (values or []))
            out.append({
                "id": f"{day}-{code}",
                "sourceType": "实时冻结",
                "date": day,
                "code": code,
                "name": meta.get("name") or code,
                "sector": meta.get("sector") or "未分类",
                "regime": snap.get("regime") or "未知",
                "mainlines": snap.get("mainlines") or [],
                "pools": memberships,
                "score": finite(meta.get("score")),
                "mainlineState": meta.get("mainlineState") or meta.get("stageZh") or None,
                "chaseRisk": meta.get("chaseRisk") or meta.get("chaseRiskZh") or None,
                "accumulationScore": finite(meta.get("accumulationScore")),
                "performance": perf,
            })
    return out


def group_stats(samples, key_fn, min_n=3):
    groups = defaultdict(list)
    for s in samples:
        key = key_fn(s)
        if key:
            groups[str(key)].append(s)
    result = []
    for key, members in groups.items():
        stat = summarize(members)
        if stat["sampleCount"] < min_n:
            continue
        five = stat["horizons"].get("5D") or {}
        result.append({
            "name": key,
            "sampleCount": stat["sampleCount"],
            "confidenceZh": stat["confidenceZh"],
            "fiveDayMedianReturn": five.get("medianReturn"),
            "fiveDayMedianAlpha": five.get("medianAlpha"),
            "fiveDayHitRate": five.get("hitRate"),
            "fiveDayMembers": five.get("members", 0),
        })
    result.sort(key=lambda x: (finite(x.get("fiveDayMedianAlpha")) if finite(x.get("fiveDayMedianAlpha")) is not None else -999, x["sampleCount"]), reverse=True)
    return result


def main():
    if not SNAPSHOTS.exists():
        print(json.dumps({"state": "skip", "reason": "snapshot index missing"}, ensure_ascii=False))
        return
    snapshots = json.loads(SNAPSHOTS.read_text(encoding="utf-8"))
    samples = collect_samples(snapshots)
    overall = summarize(samples)
    full_edge = edge_window(samples, max(1, len(samples)))
    recent20 = edge_window(samples, 20)
    recent60 = edge_window(samples, 60)
    trend = trend_judgement(full_edge, recent20, recent60)
    best = best_horizon(overall["horizons"])

    event_path = [{"day": 0, "meanReturn": 0.0, "medianReturn": 0.0, "meanAlpha": 0.0}]
    for h in HORIZONS:
        x = overall["horizons"].get(h) or {}
        if x.get("mature"):
            event_path.append({
                "day": HORIZON_DAYS[h],
                "meanReturn": x.get("meanReturn"),
                "medianReturn": x.get("medianReturn"),
                "meanAlpha": x.get("meanAlpha"),
                "members": x.get("members"),
            })

    scatter = []
    for s in sorted(samples, key=lambda x: (x["date"], x["code"]), reverse=True):
        mfe = metric(s["performance"], "MFE")
        mae = metric(s["performance"], "MAE")
        five = metric(s["performance"], "5D")
        if mfe is None or mae is None:
            continue
        scatter.append({
            "id": s["id"], "date": s["date"], "code": s["code"], "name": s["name"],
            "mfe": r(mfe), "mae": r(mae), "fiveDayReturn": r(five),
        })
        if len(scatter) >= 160:
            break

    by_regime = group_stats(samples, lambda s: s.get("regime"), 3)
    by_pool = group_stats(samples, lambda s: "/".join(s.get("pools") or []), 3)
    by_stage = group_stats(samples, lambda s: s.get("mainlineState"), 5)
    by_chase = group_stats(samples, lambda s: s.get("chaseRisk"), 5)

    updated = datetime.now(CN).isoformat(timespec="seconds")
    payload = {
        "schemaVersion": 1,
        "version": VERSION,
        "updatedAt": updated,
        "sourcePolicyZh": "当前统计只使用真实冻结 Official 样本；未来历史重建样本将以独立 sourceType 展示，不与样本外记录混算。",
        "overall": overall,
        "bestHolding": best,
        "edgeTrend": {
            "full": full_edge,
            "recent20": recent20,
            "recent60": recent60,
            "judgement": trend,
        },
        "eventPath": event_path,
        "riskScatter": scatter,
        "conditions": {
            "byRegime": by_regime,
            "byPool": by_pool,
            "byMainlineState": by_stage,
            "byChaseRisk": by_chase,
        },
        "vitals": {
            "longTermValidityZh": "待更多成熟样本" if overall["sampleCount"] < 30 else ("偏强" if (finite(full_edge.get("fiveDayMedianAlpha")) or 0) > 0 else "偏弱"),
            "recentTrendZh": trend["stateZh"],
            "sampleConfidenceZh": overall["confidenceZh"],
            "bestHoldingZh": (f"{best.get('days')}个交易日" if best.get("days") else "待样本"),
            "currentAdviceZh": "继续积累样本，不提高策略权重" if overall["sampleCount"] < 30 else ("维持权重并继续样本外验证" if trend["stateZh"] != "近期弱化" else "降低历史 Edge 权重，等待重新增强"),
        },
        "limitationsZh": [
            "样本数量不足时不输出高置信结论。",
            "主线阶段、追高风险只有在原始冻结快照真实记录时才参与条件统计，不做代理补造。",
            "历史重建与实时冻结样本必须分口径展示，避免把回看结果伪装成样本外。",
        ],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"state": "updated", "samples": len(samples), "trend": trend["stateZh"], "bestHolding": best.get("horizon"), "updatedAt": updated}, ensure_ascii=False))


if __name__ == "__main__":
    main()
