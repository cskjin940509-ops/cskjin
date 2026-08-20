#!/usr/bin/env python3
"""动态历史形态实验室 v2.9。

只消费已经冻结并持续跟踪的 Official 样本，不改写原始成员名单。
实时冻结样本与未来历史重建样本始终分口径保存，避免回看污染样本外统计。

每天重新计算：
- 中短线 1/2/3/5/10/20 日与中长线 20/40/60/120/250 日收益、胜率、Alpha；
- 事件路径、收益分布、MFE / MAE、最大回撤；
- 最佳持有周期（没有正向 Edge 时明确返回“暂无正向历史优势”）；
- 全历史、近一年、近三个月、最近20/60样本的 Edge 演化；
- Market Regime、股票池、主线阶段、追高风险及阶段×追高风险条件表现；
- 成功/失败样本对比、典型案例、第一期路径分型；
- 样本数随时间的累计增长。
"""
from __future__ import annotations

import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

CN = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS = ROOT / "astock_snapshots" / "index.json"
OUT_DIR = ROOT / "astock_history"
OUT = OUT_DIR / "latest.json"
VERSION = "v2.9-dynamic-pattern-lab-2"

HORIZON_DAYS = {
    "1D": 1,
    "2D": 2,
    "3D": 3,
    "5D": 5,
    "10D": 10,
    "20D": 20,
    "40D": 40,
    "60D": 60,
    "120D": 120,
    "250D": 250,
}
HORIZONS = list(HORIZON_DAYS)
SHORT_HORIZONS = ["1D", "2D", "3D", "5D", "10D", "20D"]
LONG_HORIZONS = ["20D", "40D", "60D", "120D", "250D"]


def finite(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def r(v):
    return round(v, 8) if v is not None and math.isfinite(v) else None


def percentile(values, q):
    values = sorted(values)
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    pos = (len(values) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return values[lo]
    w = pos - lo
    return values[lo] * (1 - w) + values[hi] * w


def metric(perf, label, field="return"):
    x = (perf or {}).get(label)
    if isinstance(x, dict):
        return finite(x.get(field))
    return finite(x)


def daily_series(perf):
    rows = (perf or {}).get("dailySeries") or []
    return [x for x in rows if isinstance(x, dict)]


def horizon_metric(perf, label, field="return"):
    """优先使用已经冻结的 horizon 字段；缺失时从逐日路径派生。

    dailySeries 的第 1 行对应可执行入场日收盘，因此 1D 与原有
    次一交易日开盘→当日收盘口径一致。
    """
    direct = metric(perf, label, field)
    if direct is not None:
        return direct
    days = HORIZON_DAYS[label]
    rows = daily_series(perf)
    if len(rows) < days:
        return None
    row = rows[days - 1]
    if field == "return":
        return finite(row.get("cumulativeReturn"))
    if field == "alpha":
        return finite(row.get("cumulativeAlpha"))
    return None


def max_drawdown(perf):
    direct = finite((perf or {}).get("maxDrawdown"))
    if direct is not None:
        return direct
    vals = [finite(x.get("drawdown")) for x in daily_series(perf)]
    vals = [x for x in vals if x is not None]
    return min(vals) if vals else None


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
    for sample in samples:
        perf = sample["performance"]
        ret = horizon_metric(perf, horizon, "return")
        if ret is not None:
            returns.append(ret)
        alpha = horizon_metric(perf, horizon, "alpha")
        if alpha is not None:
            alphas.append(alpha)
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
        "p10": r(percentile(returns, 0.10)),
        "p25": r(percentile(returns, 0.25)),
        "p75": r(percentile(returns, 0.75)),
        "p90": r(percentile(returns, 0.90)),
    }


def summarize(samples):
    horizons = {h: summarize_values(samples, h) for h in HORIZONS}
    mfe = [metric(s["performance"], "MFE") for s in samples]
    mae = [metric(s["performance"], "MAE") for s in samples]
    dd = [max_drawdown(s["performance"]) for s in samples]
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


def best_horizon(horizons, labels):
    eligible = []
    mature_options = 0
    for label in labels:
        item = horizons.get(label) or {}
        n = int(item.get("members") or 0)
        if n < 5:
            continue
        mature_options += 1
        edge = finite(item.get("medianAlpha"))
        source = "中位超额收益"
        if edge is None:
            edge = finite(item.get("medianReturn"))
            source = "中位收益"
        if edge is not None and edge > 0:
            eligible.append((edge, HORIZON_DAYS[label], label, n, source))
    if not eligible:
        if mature_options:
            return {
                "horizon": None,
                "stateZh": "暂无正向历史优势",
                "reasonZh": "已有成熟周期，但目前没有一个周期呈现正向中位历史优势；不强行挑选所谓最佳持有期。",
            }
        return {
            "horizon": None,
            "stateZh": "样本不足",
            "reasonZh": "成熟样本不足，暂不判断最佳持有周期。",
        }
    eligible.sort(reverse=True)
    edge, days, label, n, source = eligible[0]
    return {
        "horizon": label,
        "days": days,
        "edge": r(edge),
        "members": n,
        "stateZh": "存在正向历史优势",
        "reasonZh": f"按成熟样本的{source}选择，当前最佳窗口为{days}个交易日。",
    }


def edge_window(samples, count):
    subset = sorted(samples, key=lambda x: (x["date"], x["code"]))[-count:]
    stat = summarize(subset)
    five = stat["horizons"].get("5D") or {}
    return {
        "requestedSamples": count,
        "actualSamples": len(subset),
        "fiveDayMedianAlpha": five.get("medianAlpha"),
        "fiveDayMedianReturn": five.get("medianReturn"),
        "fiveDayHitRate": five.get("hitRate"),
        "fiveDayMembers": five.get("members", 0),
    }


def edge_for_subset(samples):
    stat = summarize(samples)
    five = stat["horizons"].get("5D") or {}
    return {
        "sampleCount": len(samples),
        "fiveDayMembers": five.get("members", 0),
        "fiveDayMedianAlpha": five.get("medianAlpha"),
        "fiveDayMedianReturn": five.get("medianReturn"),
        "fiveDayHitRate": five.get("hitRate"),
    }


def trend_judgement(full, recent20, recent60):
    full_alpha = finite(full.get("fiveDayMedianAlpha"))
    a20 = finite(recent20.get("fiveDayMedianAlpha"))
    a60 = finite(recent60.get("fiveDayMedianAlpha"))
    n20 = int(recent20.get("fiveDayMembers") or 0)
    n60 = int(recent60.get("fiveDayMembers") or 0)
    if full_alpha is None or a20 is None or n20 < 8:
        return {"stateZh": "样本不足", "score": 0, "reasonZh": "5日成熟样本不足，暂不对历史优势强弱下结论。"}
    reference = a60 if a60 is not None and n60 >= 15 else full_alpha
    delta = a20 - reference
    if delta >= 0.01:
        return {"stateZh": "近期增强", "score": 1, "delta": r(delta), "reasonZh": "最近20个成熟样本的5日中位超额收益明显高于较长窗口。"}
    if delta <= -0.01:
        return {"stateZh": "近期弱化", "score": -1, "delta": r(delta), "reasonZh": "最近20个成熟样本的5日中位超额收益明显低于较长窗口。"}
    return {"stateZh": "相对稳定", "score": 0, "delta": r(delta), "reasonZh": "最近20个成熟样本与较长窗口的差异尚未达到1个百分点阈值。"}


def collect_samples(snapshots):
    samples = []
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
            samples.append({
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
    return samples


def group_stats(samples, key_fn, min_n=3):
    groups = defaultdict(list)
    for sample in samples:
        key = key_fn(sample)
        if key:
            groups[str(key)].append(sample)
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
    result.sort(key=lambda x: (
        finite(x.get("fiveDayMedianAlpha")) if finite(x.get("fiveDayMedianAlpha")) is not None else -999,
        x["sampleCount"],
    ), reverse=True)
    return result


def cross_condition_stats(samples):
    groups = defaultdict(list)
    for sample in samples:
        stage = sample.get("mainlineState")
        chase = sample.get("chaseRisk")
        if stage and chase:
            groups[(str(stage), str(chase))].append(sample)
    output = []
    for (stage, chase), members in groups.items():
        five = summarize_values(members, "5D")
        output.append({
            "mainlineState": stage,
            "chaseRisk": chase,
            "sampleCount": len(members),
            "fiveDayMembers": five.get("members", 0),
            "fiveDayMedianReturn": five.get("medianReturn"),
            "fiveDayMedianAlpha": five.get("medianAlpha"),
            "fiveDayHitRate": five.get("hitRate"),
        })
    return sorted(output, key=lambda x: (x["mainlineState"], x["chaseRisk"]))


def feature_summary(samples):
    scores = [finite(x.get("score")) for x in samples]
    accum = [finite(x.get("accumulationScore")) for x in samples]
    scores = [x for x in scores if x is not None]
    accum = [x for x in accum if x is not None]
    chase = [str(x.get("chaseRisk") or "") for x in samples if x.get("chaseRisk")]
    stages = [str(x.get("mainlineState") or "") for x in samples if x.get("mainlineState")]
    mfe = [metric(x["performance"], "MFE") for x in samples]
    mae = [metric(x["performance"], "MAE") for x in samples]
    mfe = [x for x in mfe if x is not None]
    mae = [x for x in mae if x is not None]
    high_tokens = {"高", "HIGH", "High", "high"}
    return {
        "sampleCount": len(samples),
        "averageScore": r(statistics.fmean(scores)) if scores else None,
        "averageAccumulation": r(statistics.fmean(accum)) if accum else None,
        "highChaseRatio": r(sum(x in high_tokens for x in chase) / len(chase)) if chase else None,
        "stageDistribution": dict(Counter(stages)),
        "chaseDistribution": dict(Counter(chase)),
        "medianMFE": r(statistics.median(mfe)) if mfe else None,
        "medianMAE": r(statistics.median(mae)) if mae else None,
    }


def success_failure(samples):
    mature = []
    for sample in samples:
        value = horizon_metric(sample["performance"], "5D", "return")
        if value is not None:
            mature.append((value, sample))
    success = [s for value, s in mature if value >= 0.03]
    failure = [s for value, s in mature if value <= -0.03]
    ranked = sorted(mature, key=lambda x: x[0], reverse=True)

    def example(pair):
        value, sample = pair
        return {
            "date": sample["date"],
            "code": sample["code"],
            "name": sample["name"],
            "sector": sample["sector"],
            "regime": sample["regime"],
            "fiveDayReturn": r(value),
            "fiveDayAlpha": r(horizon_metric(sample["performance"], "5D", "alpha")),
            "mfe": r(metric(sample["performance"], "MFE")),
            "mae": r(metric(sample["performance"], "MAE")),
        }

    return {
        "definitionZh": "成功：5日收益≥+3%；失败：5日收益≤-3%。中间样本不强行归类。",
        "matureFiveDaySamples": len(mature),
        "success": feature_summary(success),
        "failure": feature_summary(failure),
        "topExamples": [example(x) for x in ranked[:5]],
        "bottomExamples": [example(x) for x in ranked[-5:]],
    }


def path_clusters(samples):
    groups = defaultdict(list)
    for sample in samples:
        perf = sample["performance"]
        d1 = horizon_metric(perf, "1D")
        d3 = horizon_metric(perf, "3D")
        d5 = horizon_metric(perf, "5D")
        if d1 is None or d3 is None or d5 is None:
            continue
        if d5 <= -0.03:
            name = "失败下跌型"
        elif d1 < 0 and d5 >= 0.03:
            name = "回踩再涨型"
        elif d1 >= 0.015 and d3 >= 0.03 and d5 > 0:
            name = "快速启动型"
        elif abs(d5) < 0.02:
            name = "横盘蓄势型"
        else:
            name = "其他演化型"
        groups[name].append((d5, sample))
    total = sum(len(v) for v in groups.values())
    output = []
    for name, rows in groups.items():
        values = [x[0] for x in rows]
        output.append({
            "name": name,
            "sampleCount": len(rows),
            "share": r(len(rows) / total) if total else None,
            "medianFiveDayReturn": r(statistics.median(values)),
        })
    output.sort(key=lambda x: x["sampleCount"], reverse=True)
    return {
        "methodZh": "第一期使用透明规则分型；样本量充足后再升级为无监督路径聚类，并保留版本号避免事后改口径。",
        "matureSamples": total,
        "clusters": output,
    }


def distribution(samples, label):
    values = [horizon_metric(s["performance"], label) for s in samples]
    values = [x for x in values if x is not None]
    edges = [-math.inf, -0.05, -0.03, -0.01, 0.0, 0.01, 0.03, 0.05, 0.10, math.inf]
    names = ["<-5%", "-5~-3%", "-3~-1%", "-1~0%", "0~1%", "1~3%", "3~5%", "5~10%", ">10%"]
    counts = [0] * len(names)
    for value in values:
        for i in range(len(names)):
            if edges[i] <= value < edges[i + 1]:
                counts[i] += 1
                break
    return {
        "horizon": label,
        "members": len(values),
        "bins": [{"label": name, "count": count, "share": r(count / len(values)) if values else None} for name, count in zip(names, counts)],
    }


def sample_growth(samples):
    counts = Counter(s["date"] for s in samples if s.get("date"))
    total = 0
    output = []
    for day in sorted(counts):
        total += counts[day]
        output.append({"date": day, "newSamples": counts[day], "cumulativeSamples": total})
    return output


def rolling_edge(samples, window=20):
    mature = []
    for sample in sorted(samples, key=lambda x: (x["date"], x["code"])):
        alpha = horizon_metric(sample["performance"], "5D", "alpha")
        ret = horizon_metric(sample["performance"], "5D", "return")
        if ret is not None:
            mature.append((sample, alpha, ret))
    output = []
    for end in range(window, len(mature) + 1):
        rows = mature[end - window:end]
        alphas = [x[1] for x in rows if x[1] is not None]
        returns = [x[2] for x in rows]
        output.append({
            "date": rows[-1][0]["date"],
            "windowSamples": window,
            "medianAlpha": r(statistics.median(alphas)) if alphas else None,
            "medianReturn": r(statistics.median(returns)),
            "hitRate": r(sum(x > 0 for x in returns) / len(returns)),
        })
    return output[-120:]


def calendar_views(samples):
    dates = [s.get("date") for s in samples if s.get("date")]
    if not dates:
        return {"all": edge_for_subset(samples), "recentOneYear": edge_for_subset([]), "recentThreeMonths": edge_for_subset([])}
    anchor = datetime.strptime(max(dates), "%Y-%m-%d").date()
    one_year = anchor - timedelta(days=365)
    three_months = anchor - timedelta(days=90)
    y = [s for s in samples if datetime.strptime(s["date"], "%Y-%m-%d").date() >= one_year]
    q = [s for s in samples if datetime.strptime(s["date"], "%Y-%m-%d").date() >= three_months]
    return {
        "all": edge_for_subset(samples),
        "recentOneYear": edge_for_subset(y),
        "recentThreeMonths": edge_for_subset(q),
    }


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
    best_short = best_horizon(overall["horizons"], SHORT_HORIZONS)
    best_long = best_horizon(overall["horizons"], LONG_HORIZONS)

    event_path = [{"day": 0, "meanReturn": 0.0, "medianReturn": 0.0, "meanAlpha": 0.0}]
    for label in HORIZONS:
        item = overall["horizons"].get(label) or {}
        if item.get("mature"):
            event_path.append({
                "day": HORIZON_DAYS[label],
                "meanReturn": item.get("meanReturn"),
                "medianReturn": item.get("medianReturn"),
                "meanAlpha": item.get("meanAlpha"),
                "members": item.get("members"),
            })

    scatter = []
    for sample in sorted(samples, key=lambda x: (x["date"], x["code"]), reverse=True):
        mfe = metric(sample["performance"], "MFE")
        mae = metric(sample["performance"], "MAE")
        five = horizon_metric(sample["performance"], "5D")
        if mfe is None or mae is None:
            continue
        scatter.append({
            "id": sample["id"],
            "date": sample["date"],
            "code": sample["code"],
            "name": sample["name"],
            "mfe": r(mfe),
            "mae": r(mae),
            "fiveDayReturn": r(five),
        })
        if len(scatter) >= 200:
            break

    by_regime = group_stats(samples, lambda s: s.get("regime"), 3)
    by_pool = group_stats(samples, lambda s: "/".join(s.get("pools") or []), 3)
    by_stage = group_stats(samples, lambda s: s.get("mainlineState"), 5)
    by_chase = group_stats(samples, lambda s: s.get("chaseRisk"), 5)
    sf = success_failure(samples)
    clusters = path_clusters(samples)
    five_members = int((overall["horizons"].get("5D") or {}).get("members") or 0)
    five_alpha = finite((overall["horizons"].get("5D") or {}).get("medianAlpha"))

    if five_members < 30:
        long_validity = "待更多5日成熟样本"
    elif five_alpha is not None and five_alpha > 0:
        long_validity = "偏强"
    else:
        long_validity = "偏弱"

    short_label = f"{best_short.get('days')}个交易日" if best_short.get("days") else best_short.get("stateZh", "待样本")
    long_label = f"{best_long.get('days')}个交易日" if best_long.get("days") else best_long.get("stateZh", "待样本")
    updated = datetime.now(CN).isoformat(timespec="seconds")

    payload = {
        "schemaVersion": 2,
        "version": VERSION,
        "updatedAt": updated,
        "sourcePolicyZh": "当前统计只使用真实冻结 Official 样本；未来历史重建样本将以独立 sourceType 展示，不与样本外记录混算。",
        "overall": overall,
        "horizonGroups": {
            "shortTerm": SHORT_HORIZONS,
            "mediumLongTerm": LONG_HORIZONS,
        },
        "bestHolding": best_short,
        "bestHoldingShort": best_short,
        "bestHoldingLong": best_long,
        "edgeTrend": {
            "full": full_edge,
            "recent20": recent20,
            "recent60": recent60,
            "calendarViews": calendar_views(samples),
            "rolling20": rolling_edge(samples, 20),
            "judgement": trend,
        },
        "sampleGrowth": sample_growth(samples),
        "eventPath": event_path,
        "returnDistributions": {label: distribution(samples, label) for label in ["1D", "3D", "5D", "10D", "20D", "60D", "120D"]},
        "riskScatter": scatter,
        "pathClusters": clusters,
        "successFailure": sf,
        "conditions": {
            "byRegime": by_regime,
            "byPool": by_pool,
            "byMainlineState": by_stage,
            "byChaseRisk": by_chase,
            "stageByChase": cross_condition_stats(samples),
        },
        "vitals": {
            "longTermValidityZh": long_validity,
            "recentTrendZh": trend["stateZh"],
            "sampleConfidenceZh": overall["confidenceZh"],
            "bestHoldingZh": short_label,
            "bestShortHoldingZh": short_label,
            "bestLongHoldingZh": long_label,
            "currentAdviceZh": "继续积累成熟样本，不因早期少量结果提高策略权重" if five_members < 30 else ("维持历史优势权重并继续样本外验证" if trend["stateZh"] != "近期弱化" else "降低历史优势权重，等待重新增强"),
        },
        "limitationsZh": [
            "样本数量或目标周期未成熟时不输出高置信结论。",
            "没有正向历史优势时不从负收益周期中硬选所谓最佳持有期。",
            "主线阶段、追高风险只有在原始冻结快照真实记录时才参与条件统计，不做代理补造。",
            "路径分型第一期采用透明规则；未来若切换统计聚类，必须新版本并保留旧结果。",
            "历史重建与实时冻结样本必须分口径展示，避免把回看结果伪装成样本外。",
        ],
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "state": "updated",
        "samples": len(samples),
        "fiveDayMature": five_members,
        "trend": trend["stateZh"],
        "bestShort": best_short.get("horizon"),
        "bestLong": best_long.get("horizon"),
        "updatedAt": updated,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
