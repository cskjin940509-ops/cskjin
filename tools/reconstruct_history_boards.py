#!/usr/bin/env python3
"""A股行业板块历史重建层 v3.0。

目的：为动态历史形态实验室提供“研究用历史重建”样本，但绝不冒充真实样本外冻结记录。

硬约束：
- 只使用信号日当日及以前的板块/基准前复权日线；
- 每周最后一个交易日形成重建信号，下一交易日开盘作为可执行入场价；
- 未来收益只用于事后评估，不参与当期评分；
- 历史重建与实时冻结样本独立存储、独立统计；
- 第一期仅行业板块，不重建概念板块，避免概念分类随时间变化造成更严重的穿越；
- 当前行业板块列表仍存在“当前分类宇宙/幸存者偏差”，必须在结果中持续披露。

可重建特征（全部 point-in-time）：
Relative Strength / RS（相对强弱）20/60日、5/20日动量、成交额扩张、
Multi-Timeframe Alignment / MTA（多周期趋势共振）、价格延伸/追高风险、20日波动率。
历史主力资金、真实历史 breadth（上涨扩散度）目前无法可靠逐日重建，因此不伪造，权重重新分配。
"""
from __future__ import annotations

import json
import math
import statistics
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CN = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "astock_history" / "reconstruction"
OUT = OUT_DIR / "latest.json"
VERSION = "v3.0-weekly-board-reconstruction-1"
MAX_BARS = 1800
TOP_N = 5
MIN_LOOKBACK = 130
HORIZON_DAYS = {
    "1D": 1, "2D": 2, "3D": 3, "5D": 5, "10D": 10,
    "20D": 20, "40D": 40, "60D": 60, "120D": 120, "250D": 250,
}
HORIZONS = list(HORIZON_DAYS)
SHORT_HORIZONS = ["1D", "2D", "3D", "5D", "10D", "20D"]
LONG_HORIZONS = ["20D", "40D", "60D", "120D", "250D"]
UA = "Mozilla/5.0 AStockStrategy-History-Reconstruction/3.0"


def finite(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def rounded(v, digits=8):
    return round(v, digits) if v is not None and math.isfinite(v) else None


def get_json(url: str, timeout: int = 15):
    last = None
    for attempt in range(3):
        try:
            req = Request(url, headers={
                "User-Agent": UA,
                "Accept": "application/json",
                "Referer": "https://quote.eastmoney.com/",
                "Cache-Control": "no-cache",
            })
            with urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8", "replace"))
        except Exception as exc:
            last = exc
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(str(last or "request failed"))


def eastmoney_clist(fs: str, fields: str, pz: int = 500, fid: str = "f3"):
    params = {
        "pn": 1, "pz": pz, "po": 1, "np": 1, "fltt": 2, "invt": 2,
        "fid": fid, "fs": fs, "fields": fields,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
    }
    last = None
    for host in ("push2.eastmoney.com", "push2delay.eastmoney.com"):
        for attempt in range(3):
            try:
                url = f"https://{host}/api/qt/clist/get?" + urlencode({**params, "_": int(time.time() * 1000)})
                diff = ((get_json(url).get("data") or {}).get("diff") or [])
                if diff:
                    return diff
                last = RuntimeError(host + " empty")
            except Exception as exc:
                last = exc
                time.sleep(0.6 * (attempt + 1))
    raise RuntimeError(str(last or "board list unavailable"))


def industry_boards():
    rows = eastmoney_clist("m:90+t:2+f:!50", "f12,f14", 500, "f3")
    out = []
    seen = set()
    for row in rows:
        code = str(row.get("f12") or "")
        name = str(row.get("f14") or "")
        if not code.startswith("BK") or not name or code in seen:
            continue
        seen.add(code)
        out.append({"code": code, "name": name})
    if len(out) < 20:
        raise RuntimeError(f"industry board universe too small: {len(out)}")
    return out


def fetch_kline(secid: str, limit: int = MAX_BARS):
    params = {
        "secid": secid,
        "klt": 101,
        "fqt": 1,
        "lmt": limit,
        "end": "20500101",
        "iscca": 1,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
    }
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?" + urlencode(params)
    data = (get_json(url).get("data") or {})
    out = []
    for raw in data.get("klines") or []:
        f = raw.split(",")
        if len(f) < 7:
            continue
        opened, closed = finite(f[1]), finite(f[2])
        high, low, amount = finite(f[3]), finite(f[4]), finite(f[6])
        if not f[0] or opened is None or closed is None or opened <= 0 or closed <= 0:
            continue
        out.append({
            "date": f[0], "open": opened, "close": closed,
            "high": high if high is not None else max(opened, closed),
            "low": low if low is not None else min(opened, closed),
            "amount": amount,
        })
    out.sort(key=lambda x: x["date"])
    if len(out) < MIN_LOOKBACK + 20:
        raise RuntimeError(f"history too short: {secid} {len(out)}")
    return out


def mean(xs):
    vals = [x for x in xs if x is not None and math.isfinite(x)]
    return statistics.fmean(vals) if vals else None


def pct_rank(values, value, neutral=50.0):
    xs = sorted(x for x in values if x is not None and math.isfinite(x))
    if not xs or value is None:
        return neutral
    if len(xs) == 1:
        return 50.0
    below = sum(1 for x in xs if x < value)
    equal = sum(1 for x in xs if x == value)
    return 100.0 * (below + 0.5 * equal) / len(xs)


def ret(closes, n):
    if len(closes) <= n or closes[-n - 1] in (None, 0):
        return None
    return closes[-1] / closes[-n - 1] - 1.0


def ma(closes, n):
    if len(closes) < n:
        return None
    return mean(closes[-n:])


def volatility(closes, n=20):
    if len(closes) < n + 1:
        return None
    rs = []
    for a, b in zip(closes[-n - 1:-1], closes[-n:]):
        if a and b:
            rs.append(b / a - 1.0)
    return statistics.pstdev(rs) if len(rs) >= 10 else None


def raw_features(rows, idx, benchmark_rows, benchmark_idx):
    history = rows[: idx + 1]
    bench_hist = benchmark_rows[: benchmark_idx + 1]
    closes = [x["close"] for x in history]
    bench_closes = [x["close"] for x in bench_hist]
    if len(closes) < MIN_LOOKBACK or len(bench_closes) < MIN_LOOKBACK:
        return None
    r5, r20, r60 = ret(closes, 5), ret(closes, 20), ret(closes, 60)
    b20, b60 = ret(bench_closes, 20), ret(bench_closes, 60)
    rs20 = r20 - b20 if r20 is not None and b20 is not None else None
    rs60 = r60 - b60 if r60 is not None and b60 is not None else None
    m20, m60, m120 = ma(closes, 20), ma(closes, 60), ma(closes, 120)
    close = closes[-1]
    trend_count = 0
    if m20 is not None and close > m20:
        trend_count += 1
    if m20 is not None and m60 is not None and m20 > m60:
        trend_count += 1
    if m60 is not None and m120 is not None and m60 > m120:
        trend_count += 1
    amounts = [finite(x.get("amount")) for x in history]
    a5, a20 = mean(amounts[-5:]), mean(amounts[-20:])
    amount_expansion = a5 / a20 - 1.0 if a5 is not None and a20 not in (None, 0) else None
    extension = close / m20 - 1.0 if m20 not in (None, 0) else None
    high20 = max(x["high"] for x in history[-20:])
    room_to_high = high20 / close - 1.0 if close else None
    vol20 = volatility(closes, 20)
    return {
        "r5": r5, "r20": r20, "r60": r60,
        "rs20": rs20, "rs60": rs60,
        "trendCount": trend_count,
        "mtaScore": 100.0 * trend_count / 3.0,
        "amountExpansion": amount_expansion,
        "extension20": extension,
        "roomTo20High": room_to_high,
        "volatility20": vol20,
        "close": close,
    }


def score_cross_section(rows):
    rs20s = [x["f"].get("rs20") for x in rows]
    rs60s = [x["f"].get("rs60") for x in rows]
    r5s = [x["f"].get("r5") for x in rows]
    r20s = [x["f"].get("r20") for x in rows]
    amounts = [x["f"].get("amountExpansion") for x in rows]
    extensions = [x["f"].get("extension20") for x in rows]
    vols = [x["f"].get("volatility20") for x in rows]
    for item in rows:
        f = item["f"]
        rs = 0.60 * pct_rank(rs20s, f.get("rs20")) + 0.40 * pct_rank(rs60s, f.get("rs60"))
        momentum = 0.60 * pct_rank(r5s, f.get("r5")) + 0.40 * pct_rank(r20s, f.get("r20"))
        amount_score = pct_rank(amounts, f.get("amountExpansion"))
        # 延伸越高，追高风险越高。这里不是奖励“离均线越远越好”，而是保留合理上涨空间。
        ext_rank = pct_rank(extensions, f.get("extension20"))
        price_room = 100.0 - max(0.0, ext_rank - 35.0) / 65.0 * 100.0
        vol_score = 100.0 - pct_rank(vols, f.get("volatility20"))
        score = (
            0.32 * rs + 0.18 * momentum + 0.15 * amount_score +
            0.20 * f.get("mtaScore", 50.0) + 0.10 * price_room + 0.05 * vol_score
        )
        ext = f.get("extension20") or 0.0
        r5 = f.get("r5") or 0.0
        if ext > 0.10 or r5 > 0.12:
            stage = "过热"
        elif score >= 82 and f.get("trendCount", 0) >= 2 and (f.get("rs20") or -1) > 0:
            stage = "确认中"
        elif score >= 72 and (f.get("rs20") or -1) > 0:
            stage = "正在形成"
        elif score >= 62:
            stage = "潜在主线雷达"
        else:
            stage = "观察"
        if ext > 0.08 or r5 > 0.10:
            chase = "高"
        elif ext > 0.04 or r5 > 0.06:
            chase = "中"
        else:
            chase = "低"
        item.update({
            "score": rounded(score, 4),
            "mainlineState": stage,
            "chaseRisk": chase,
            "rsScore": rounded(rs, 4),
            "momentumScore": rounded(momentum, 4),
            "amountScore": rounded(amount_score, 4),
            "priceRoomScore": rounded(price_room, 4),
        })
    rows.sort(key=lambda x: x["score"], reverse=True)
    return rows


def benchmark_regime(bench, idx):
    closes = [x["close"] for x in bench[: idx + 1]]
    if len(closes) < 120:
        return "未知"
    close = closes[-1]
    m20, m60, m120 = ma(closes, 20), ma(closes, 60), ma(closes, 120)
    r20 = ret(closes, 20) or 0.0
    if m20 and m60 and m120 and close > m20 > m60 > m120 and r20 > 0:
        return "进攻"
    if m60 and m120 and close < m60 and m60 < m120:
        return "防御"
    return "中性"


def weekly_signal_dates(benchmark):
    groups = defaultdict(list)
    for row in benchmark:
        dt = datetime.strptime(row["date"], "%Y-%m-%d").date()
        iso = dt.isocalendar()
        groups[(iso.year, iso.week)].append(row["date"])
    return [max(v) for _, v in sorted(groups.items())]


def performance_for(board_rows, bench_rows, signal_date):
    bmap = {x["date"]: x for x in board_rows}
    future_bench = [x for x in bench_rows if x["date"] > signal_date]
    if not future_bench:
        return None
    entry_date = future_bench[0]["date"]
    entry_board = bmap.get(entry_date)
    entry_bench = future_bench[0]
    if not entry_board:
        return None
    entry_price = finite(entry_board.get("open"))
    bench_entry = finite(entry_bench.get("open"))
    if entry_price in (None, 0) or bench_entry in (None, 0):
        return None
    result = {
        "entryRule": "周频信号后一交易日开盘",
        "entryDate": entry_date,
        "entryPrice": rounded(entry_price, 6),
        "source": "东方财富前复权行业板块指数",
    }
    available = []
    for bench_bar in future_bench:
        board_bar = bmap.get(bench_bar["date"])
        if board_bar:
            available.append((bench_bar, board_bar))
    for label, sessions in HORIZON_DAYS.items():
        if len(future_bench) < sessions:
            continue
        target = future_bench[sessions - 1]
        board_target = bmap.get(target["date"])
        if not board_target:
            continue
        close = finite(board_target.get("close"))
        bench_close = finite(target.get("close"))
        if close is None or bench_close is None:
            continue
        retv = close / entry_price - 1.0
        bench_ret = bench_close / bench_entry - 1.0
        result[label] = {
            "return": rounded(retv), "benchmark": rounded(bench_ret),
            "alpha": rounded(retv - bench_ret), "asOf": target["date"], "mature": True,
        }
    risk_rows = available[:20]
    if risk_rows:
        highs = [finite(x[1].get("high")) for x in risk_rows]
        lows = [finite(x[1].get("low")) for x in risk_rows]
        highs = [x for x in highs if x is not None]
        lows = [x for x in lows if x is not None]
        result["MFE"] = {"return": rounded(max(highs) / entry_price - 1.0) if highs else None}
        result["MAE"] = {"return": rounded(min(lows) / entry_price - 1.0) if lows else None}
        navs = [finite(x[1].get("close")) / entry_price for x in risk_rows if finite(x[1].get("close")) is not None]
        peak = 1.0
        dd = 0.0
        for nav in navs:
            peak = max(peak, nav)
            dd = min(dd, nav / peak - 1.0)
        result["maxDrawdown"] = rounded(dd)
    return result


def metric(perf, label, field="return"):
    item = (perf or {}).get(label)
    if isinstance(item, dict):
        return finite(item.get(field))
    return finite(item)


def percentile(values, q):
    xs = sorted(values)
    if not xs:
        return None
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q
    lo, hi = int(math.floor(pos)), int(math.ceil(pos))
    if lo == hi:
        return xs[lo]
    w = pos - lo
    return xs[lo] * (1 - w) + xs[hi] * w


def confidence(n):
    if n >= 600:
        return "高"
    if n >= 250:
        return "中高"
    if n >= 100:
        return "中"
    if n >= 40:
        return "中低"
    return "低"


def summarize_values(samples, horizon):
    rets, alphas = [], []
    for s in samples:
        rv = metric(s["performance"], horizon, "return")
        av = metric(s["performance"], horizon, "alpha")
        if rv is not None:
            rets.append(rv)
        if av is not None:
            alphas.append(av)
    if not rets:
        return {"members": 0, "mature": False}
    return {
        "members": len(rets), "mature": True,
        "meanReturn": rounded(statistics.fmean(rets)),
        "medianReturn": rounded(statistics.median(rets)),
        "hitRate": rounded(sum(x > 0 for x in rets) / len(rets)),
        "meanAlpha": rounded(statistics.fmean(alphas)) if alphas else None,
        "medianAlpha": rounded(statistics.median(alphas)) if alphas else None,
        "p10": rounded(percentile(rets, 0.10)), "p25": rounded(percentile(rets, 0.25)),
        "p75": rounded(percentile(rets, 0.75)), "p90": rounded(percentile(rets, 0.90)),
    }


def summarize(samples):
    horizons = {h: summarize_values(samples, h) for h in HORIZONS}
    mfe = [metric(x["performance"], "MFE") for x in samples]
    mae = [metric(x["performance"], "MAE") for x in samples]
    dd = [finite((x["performance"] or {}).get("maxDrawdown")) for x in samples]
    mfe = [x for x in mfe if x is not None]
    mae = [x for x in mae if x is not None]
    dd = [x for x in dd if x is not None]
    return {
        "sampleCount": len(samples), "confidenceZh": confidence(len(samples)), "horizons": horizons,
        "medianMFE": rounded(statistics.median(mfe)) if mfe else None,
        "medianMAE": rounded(statistics.median(mae)) if mae else None,
        "medianMaxDrawdown": rounded(statistics.median(dd)) if dd else None,
    }


def best_horizon(horizons, labels):
    choices = []
    mature = 0
    for label in labels:
        item = horizons.get(label) or {}
        n = int(item.get("members") or 0)
        if n < 30:
            continue
        mature += 1
        edge = finite(item.get("medianAlpha"))
        source = "中位超额收益"
        if edge is None:
            edge = finite(item.get("medianReturn"))
            source = "中位收益"
        if edge is not None and edge > 0:
            choices.append((edge, -HORIZON_DAYS[label], label, n, source))
    if not choices:
        return {
            "horizon": None,
            "stateZh": "暂无正向历史优势" if mature else "样本不足",
            "reasonZh": "已有成熟重建周期，但没有正向中位历史优势；不强行挑最佳周期。" if mature else "成熟重建样本不足。",
        }
    choices.sort(reverse=True)
    edge, neg_days, label, n, source = choices[0]
    return {
        "horizon": label, "days": -neg_days, "edge": rounded(edge), "members": n,
        "stateZh": "存在正向历史优势", "reasonZh": f"按历史重建成熟样本的{source}选择。",
    }


def distribution(samples, label):
    vals = [metric(s["performance"], label) for s in samples]
    vals = [x for x in vals if x is not None]
    edges = [-math.inf, -0.05, -0.03, -0.01, 0.0, 0.01, 0.03, 0.05, 0.10, math.inf]
    names = ["<-5%", "-5~-3%", "-3~-1%", "-1~0%", "0~1%", "1~3%", "3~5%", "5~10%", ">10%"]
    counts = [0] * len(names)
    for v in vals:
        for i in range(len(names)):
            if edges[i] <= v < edges[i + 1]:
                counts[i] += 1
                break
    return {"horizon": label, "members": len(vals), "bins": [
        {"label": n, "count": c, "share": rounded(c / len(vals)) if vals else None}
        for n, c in zip(names, counts)
    ]}


def group_stats(samples, key_fn, min_n=20):
    groups = defaultdict(list)
    for s in samples:
        key = key_fn(s)
        if key:
            groups[str(key)].append(s)
    out = []
    for name, members in groups.items():
        if len(members) < min_n:
            continue
        five = summarize_values(members, "5D")
        out.append({
            "name": name, "sampleCount": len(members), "confidenceZh": confidence(len(members)),
            "fiveDayMedianReturn": five.get("medianReturn"), "fiveDayMedianAlpha": five.get("medianAlpha"),
            "fiveDayHitRate": five.get("hitRate"), "fiveDayMembers": five.get("members", 0),
        })
    return sorted(out, key=lambda x: ((finite(x.get("fiveDayMedianAlpha")) or -999), x["sampleCount"]), reverse=True)


def cross_condition_stats(samples):
    groups = defaultdict(list)
    for s in samples:
        groups[(s.get("mainlineState"), s.get("chaseRisk"))].append(s)
    out = []
    for (stage, chase), members in groups.items():
        if not stage or not chase or len(members) < 10:
            continue
        five = summarize_values(members, "5D")
        out.append({
            "mainlineState": stage, "chaseRisk": chase, "sampleCount": len(members),
            "fiveDayMembers": five.get("members", 0), "fiveDayMedianReturn": five.get("medianReturn"),
            "fiveDayMedianAlpha": five.get("medianAlpha"), "fiveDayHitRate": five.get("hitRate"),
        })
    return sorted(out, key=lambda x: (x["mainlineState"], x["chaseRisk"]))


def sample_growth(samples):
    counts = Counter(s["date"] for s in samples)
    total, out = 0, []
    for day in sorted(counts):
        total += counts[day]
        out.append({"date": day, "newSamples": counts[day], "cumulativeSamples": total})
    return out


def edge_window(samples, count):
    subset = sorted(samples, key=lambda x: (x["date"], x["code"]))[-count:]
    five = summarize_values(subset, "5D")
    return {
        "requestedSamples": count, "actualSamples": len(subset),
        "fiveDayMedianAlpha": five.get("medianAlpha"), "fiveDayMedianReturn": five.get("medianReturn"),
        "fiveDayHitRate": five.get("hitRate"), "fiveDayMembers": five.get("members", 0),
    }


def trend_judgement(full, recent60):
    fa, ra = finite(full.get("fiveDayMedianAlpha")), finite(recent60.get("fiveDayMedianAlpha"))
    n = int(recent60.get("fiveDayMembers") or 0)
    if fa is None or ra is None or n < 30:
        return {"stateZh": "样本不足", "score": 0, "reasonZh": "5日重建样本不足。"}
    delta = ra - fa
    if delta >= 0.01:
        return {"stateZh": "近期增强", "score": 1, "delta": rounded(delta), "reasonZh": "最近60个重建样本的5日中位超额收益高于全历史。"}
    if delta <= -0.01:
        return {"stateZh": "近期弱化", "score": -1, "delta": rounded(delta), "reasonZh": "最近60个重建样本的5日中位超额收益低于全历史。"}
    return {"stateZh": "相对稳定", "score": 0, "delta": rounded(delta), "reasonZh": "最近60个重建样本与全历史差异小于1个百分点。"}


def success_failure(samples):
    mature = [(metric(s["performance"], "5D"), s) for s in samples]
    mature = [(v, s) for v, s in mature if v is not None]
    good = [s for v, s in mature if v >= 0.03]
    bad = [s for v, s in mature if v <= -0.03]
    ranked = sorted(mature, key=lambda x: x[0], reverse=True)

    def feature(xs):
        scores = [finite(x.get("score")) for x in xs]
        scores = [x for x in scores if x is not None]
        high = sum(x.get("chaseRisk") == "高" for x in xs)
        maes = [metric(x["performance"], "MAE") for x in xs]
        maes = [x for x in maes if x is not None]
        return {
            "sampleCount": len(xs), "averageScore": rounded(mean(scores)), "averageAccumulation": None,
            "highChaseRatio": rounded(high / len(xs)) if xs else None,
            "medianMAE": rounded(statistics.median(maes)) if maes else None,
        }

    def ex(pair):
        v, s = pair
        return {
            "date": s["date"], "code": s["code"], "name": s["name"], "sector": "行业板块",
            "regime": s["regime"], "fiveDayReturn": rounded(v),
            "fiveDayAlpha": rounded(metric(s["performance"], "5D", "alpha")),
            "mfe": rounded(metric(s["performance"], "MFE")), "mae": rounded(metric(s["performance"], "MAE")),
        }
    return {
        "definitionZh": "历史重建成功：5日收益≥+3%；失败：5日收益≤-3%。",
        "matureFiveDaySamples": len(mature), "success": feature(good), "failure": feature(bad),
        "topExamples": [ex(x) for x in ranked[:5]], "bottomExamples": [ex(x) for x in ranked[-5:]],
    }


def path_clusters(samples):
    groups = defaultdict(list)
    for s in samples:
        d1, d3, d5 = [metric(s["performance"], x) for x in ("1D", "3D", "5D")]
        if d1 is None or d3 is None or d5 is None:
            continue
        if d5 <= -0.03:
            key = "失败下跌型"
        elif d1 < 0 and d5 >= 0.03:
            key = "回踩再涨型"
        elif d1 >= 0.015 and d3 >= 0.03 and d5 > 0:
            key = "快速启动型"
        elif abs(d5) < 0.02:
            key = "横盘蓄势型"
        else:
            key = "其他演化型"
        groups[key].append(d5)
    total = sum(len(x) for x in groups.values())
    return {
        "methodZh": "透明规则分型；历史重建和真实冻结使用相同路径定义，但不混合统计。",
        "matureSamples": total,
        "clusters": sorted([
            {"name": k, "sampleCount": len(v), "share": rounded(len(v) / total) if total else None,
             "medianFiveDayReturn": rounded(statistics.median(v))}
            for k, v in groups.items()
        ], key=lambda x: x["sampleCount"], reverse=True),
    }


def reconstruct():
    universe = industry_boards()
    histories = {}
    failures = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(fetch_kline, "90." + b["code"]): b for b in universe}
        futures[ex.submit(fetch_kline, "1.000300")] = {"code": "000300", "name": "沪深300"}
        for fut in as_completed(futures):
            item = futures[fut]
            try:
                histories[item["code"]] = fut.result()
            except Exception as exc:
                failures[item["code"]] = exc.__class__.__name__ + ":" + str(exc)[:80]
    benchmark = histories.get("000300")
    if not benchmark:
        raise RuntimeError("CSI300 history unavailable")
    board_meta = {b["code"]: b for b in universe if b["code"] in histories}
    bench_index = {x["date"]: i for i, x in enumerate(benchmark)}
    board_indices = {code: {x["date"]: i for i, x in enumerate(rows)} for code, rows in histories.items() if code != "000300"}
    signals = weekly_signal_dates(benchmark)
    # 只从具备至少120日历史之后开始。保留最近尚未成熟的样本，成熟状态由 horizon 字段自然体现。
    signals = [d for d in signals if bench_index.get(d, 0) >= MIN_LOOKBACK]
    samples = []
    cohorts = []
    for signal_date in signals:
        bi = bench_index.get(signal_date)
        if bi is None:
            continue
        candidates = []
        for code, meta in board_meta.items():
            idx = board_indices.get(code, {}).get(signal_date)
            if idx is None:
                continue
            f = raw_features(histories[code], idx, benchmark, bi)
            if f is None:
                continue
            candidates.append({"code": code, "name": meta["name"], "f": f})
        if len(candidates) < 20:
            continue
        scored = score_cross_section(candidates)
        selected = [x for x in scored if x["score"] >= 60][:TOP_N]
        if len(selected) < 3:
            selected = scored[:min(TOP_N, len(scored))]
        regime = benchmark_regime(benchmark, bi)
        cohort_members = []
        for rank, item in enumerate(selected, 1):
            perf = performance_for(histories[item["code"]], benchmark, signal_date)
            if perf is None:
                continue
            f = item["f"]
            sample = {
                "id": f"recon-{signal_date}-{item['code']}",
                "sourceType": "历史重建", "entityType": "行业板块",
                "date": signal_date, "code": item["code"], "name": item["name"],
                "sector": item["name"], "regime": regime, "rank": rank,
                "score": item["score"], "mainlineState": item["mainlineState"], "chaseRisk": item["chaseRisk"],
                "features": {
                    "rs20": rounded(f.get("rs20")), "rs60": rounded(f.get("rs60")),
                    "r5": rounded(f.get("r5")), "r20": rounded(f.get("r20")),
                    "amountExpansion": rounded(f.get("amountExpansion")), "mtaScore": rounded(f.get("mtaScore")),
                    "extension20": rounded(f.get("extension20")), "volatility20": rounded(f.get("volatility20")),
                },
                "performance": perf,
            }
            samples.append(sample)
            cohort_members.append({"code": item["code"], "name": item["name"], "rank": rank, "score": item["score"]})
        if cohort_members:
            cohorts.append({"date": signal_date, "regime": regime, "members": cohort_members})
    if len(samples) < 40:
        raise RuntimeError(f"reconstructed samples too small: {len(samples)}")

    overall = summarize(samples)
    best_short = best_horizon(overall["horizons"], SHORT_HORIZONS)
    best_long = best_horizon(overall["horizons"], LONG_HORIZONS)
    full = edge_window(samples, len(samples))
    recent20, recent60 = edge_window(samples, 20), edge_window(samples, 60)
    trend = trend_judgement(full, recent60)
    event_path = [{"day": 0, "meanReturn": 0.0, "medianReturn": 0.0, "meanAlpha": 0.0}]
    for label in HORIZONS:
        h = overall["horizons"].get(label) or {}
        if h.get("mature"):
            event_path.append({
                "day": HORIZON_DAYS[label], "meanReturn": h.get("meanReturn"),
                "medianReturn": h.get("medianReturn"), "meanAlpha": h.get("meanAlpha"),
                "members": h.get("members"),
            })
    scatter = []
    for s in sorted(samples, key=lambda x: (x["date"], x["code"]), reverse=True):
        mfe, mae = metric(s["performance"], "MFE"), metric(s["performance"], "MAE")
        if mfe is None or mae is None:
            continue
        scatter.append({
            "id": s["id"], "date": s["date"], "code": s["code"], "name": s["name"],
            "mfe": rounded(mfe), "mae": rounded(mae), "fiveDayReturn": rounded(metric(s["performance"], "5D")),
        })
        if len(scatter) >= 250:
            break
    sf = success_failure(samples)
    clusters = path_clusters(samples)
    five = overall["horizons"].get("5D") or {}
    five_alpha = finite(five.get("medianAlpha"))
    long_validity = "样本不足" if int(five.get("members") or 0) < 100 else ("偏强" if (five_alpha or 0) > 0 else "偏弱")
    short_label = f"{best_short.get('days')}个交易日" if best_short.get("days") else best_short.get("stateZh", "待样本")
    long_label = f"{best_long.get('days')}个交易日" if best_long.get("days") else best_long.get("stateZh", "待样本")
    dates = [s["date"] for s in samples]
    updated = datetime.now(CN).isoformat(timespec="seconds")
    payload = {
        "schemaVersion": 1,
        "version": VERSION,
        "updatedAt": updated,
        "sourceType": "历史重建",
        "sourcePolicyZh": "研究用历史重建：行业板块周频、信号后一交易日开盘、严格使用当时及以前K线。与真实冻结样本完全分开，不得冒充样本外记录。",
        "coverage": {
            "startDate": min(dates), "endDate": max(dates),
            "industryUniverseCurrent": len(universe), "boardsWithHistory": len(board_meta),
            "boardFailures": len(failures), "weeklyCohorts": len(cohorts), "samples": len(samples),
            "topNPerWeek": TOP_N, "benchmark": "沪深300", "priceSource": "东方财富前复权行业板块指数/沪深300",
        },
        "overall": overall,
        "horizonGroups": {"shortTerm": SHORT_HORIZONS, "mediumLongTerm": LONG_HORIZONS},
        "bestHolding": best_short, "bestHoldingShort": best_short, "bestHoldingLong": best_long,
        "edgeTrend": {
            "full": full, "recent20": recent20, "recent60": recent60,
            "calendarViews": {"all": full, "recentOneYear": edge_window([s for s in samples if s["date"] >= (datetime.strptime(max(dates), "%Y-%m-%d").date() - timedelta(days=365)).isoformat()], 100000),
                              "recentThreeMonths": edge_window([s for s in samples if s["date"] >= (datetime.strptime(max(dates), "%Y-%m-%d").date() - timedelta(days=90)).isoformat()], 100000)},
            "rolling20": [], "judgement": trend,
        },
        "sampleGrowth": sample_growth(samples),
        "eventPath": event_path,
        "returnDistributions": {h: distribution(samples, h) for h in ["1D", "3D", "5D", "10D", "20D", "60D", "120D", "250D"]},
        "riskScatter": scatter,
        "pathClusters": clusters,
        "successFailure": sf,
        "conditions": {
            "byRegime": group_stats(samples, lambda s: s.get("regime"), 20),
            "byPool": group_stats(samples, lambda s: "历史重建Top5", 20),
            "byMainlineState": group_stats(samples, lambda s: s.get("mainlineState"), 20),
            "byChaseRisk": group_stats(samples, lambda s: s.get("chaseRisk"), 20),
            "stageByChase": cross_condition_stats(samples),
        },
        "vitals": {
            "longTermValidityZh": long_validity, "recentTrendZh": trend["stateZh"],
            "sampleConfidenceZh": overall["confidenceZh"], "bestHoldingZh": short_label,
            "bestShortHoldingZh": short_label, "bestLongHoldingZh": long_label,
            "currentAdviceZh": "历史重建只用于研究/校准；真实交易权重仍以持续样本外验证为准。",
        },
        "limitationsZh": [
            "历史重建不是当时真实推荐，也不是样本外收益。",
            "行业宇宙来自当前东方财富行业分类，存在分类变迁与幸存者偏差。",
            "历史主力资金与真实历史上涨扩散度无法可靠逐日重建，因此未伪造这两个因子。",
            "概念板块第一期不纳入历史重建，避免使用今天的概念分类穿越到过去。",
            "周频样本仍存在相邻持有期重叠；样本量不能直接等同于完全独立事件数。",
        ],
        "cohorts": cohorts[-320:],
        "samples": samples[-2200:],
        "failures": failures,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "state": "updated", "version": VERSION, "boards": len(board_meta),
        "weeklyCohorts": len(cohorts), "samples": len(samples),
        "startDate": min(dates), "endDate": max(dates), "updatedAt": updated,
    }, ensure_ascii=False))
    return payload


if __name__ == "__main__":
    reconstruct()
