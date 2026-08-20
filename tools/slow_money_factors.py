#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FACTOR_DIR = ROOT / "astock_factors"

THEME_RULES = [
    ("黄金", ["黄金", "贵金属"]),
    ("有色金属", ["有色", "铜", "铝", "锌", "铅", "镍", "钴", "锂", "稀土", "资源"]),
    ("半导体", ["半导体", "芯片", "集成电路", "科创芯"]),
    ("通信", ["通信", "光通信", "CPO", "5G", "算力", "数据中心"]),
    ("传媒", ["传媒", "媒体", "影视", "游戏", "动漫", "短剧", "视频"]),
    ("计算机", ["计算机", "软件", "云计算", "信创", "网络安全", "数据要素"]),
    ("人工智能", ["人工智能", "AI", "机器人", "智能驾驶"]),
    ("电力设备", ["电力设备", "电网", "输配电", "配电", "电气", "特高压"]),
    ("新能源", ["新能源", "光伏", "储能", "风电", "电池", "锂电"]),
    ("医药", ["医药", "医疗", "创新药", "生物", "中药"]),
    ("消费", ["消费", "食品", "饮料", "白酒", "家电", "零售", "旅游"]),
    ("农业", ["农业", "农林牧渔", "种植", "养殖", "粮食", "种子"]),
    ("军工", ["军工", "国防", "航天", "航空"]),
    ("银行", ["银行"]),
    ("证券", ["证券", "券商"]),
    ("保险", ["保险"]),
    ("房地产", ["房地产", "地产"]),
    ("煤炭", ["煤炭", "煤"]),
    ("钢铁", ["钢铁"]),
    ("化工", ["化工", "化学", "材料"]),
    ("汽车", ["汽车", "新能源车", "智能车"]),
]


def finite(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def rank_pct(values, v):
    xs = sorted(x for x in values if x is not None and math.isfinite(x))
    if v is None or not xs:
        return None
    less = sum(x < v for x in xs)
    eq = sum(x == v for x in xs)
    return 100.0 * (less + 0.5 * eq) / len(xs)


def themes_for_text(text: str | None):
    s = (text or "").upper().replace(" ", "")
    out = []
    for theme, keys in THEME_RULES:
        if any(k.upper() in s for k in keys):
            out.append(theme)
    return out


def _parse_day(s):
    try:
        y, m, d = map(int, str(s).split("-")[:3])
        return date(y, m, d)
    except Exception:
        return None


def load_for_signal_date(signal_day: str | None = None):
    candidates = []
    latest = FACTOR_DIR / "latest.json"
    if latest.exists():
        try:
            candidates.append(json.loads(latest.read_text(encoding="utf-8")))
        except Exception:
            pass
    hist = FACTOR_DIR / "history"
    if hist.exists():
        for p in hist.glob("*.json"):
            try:
                candidates.append(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                continue
    if not candidates:
        return None
    cutoff = _parse_day(signal_day) if signal_day else None
    usable = []
    for x in candidates:
        d = _parse_day(x.get("dataDate"))
        if d is None:
            continue
        if cutoff is None or d < cutoff:
            usable.append((d, x))
    if not usable:
        return None
    usable.sort(key=lambda z: z[0])
    return usable[-1][1]


def _theme_stats_for_sector(factors: dict, sector: str | None):
    themes = themes_for_text(sector)
    stats = ((factors.get("etf") or {}).get("themes") or {})
    matches = []
    for theme in themes:
        row = stats.get(theme)
        if isinstance(row, dict):
            matches.append((theme, row))
    return matches


def apply_to_stock_candidates(stocks: list[dict], pools: dict, signal_day: str | None = None):
    factors = load_for_signal_date(signal_day)
    pools = dict(pools or {})
    pools.setdefault("B1", [])
    pools.setdefault("B2", [])
    if not factors:
        return stocks, pools, None

    margin_map = ((factors.get("margin") or {}).get("stocks") or {})
    theme_map = ((factors.get("etf") or {}).get("themes") or {})

    m1_values, m5_values, buy_values = [], [], []
    for s in stocks:
        m = margin_map.get(str(s.get("code"))) or {}
        m1_values.append(finite(m.get("balanceChangePct1d")))
        m5_values.append(finite(m.get("balanceChangePct5d")))
        buy_values.append(finite(m.get("buyToBalancePct")))

    theme1 = [finite(x.get("shareChangePct1d")) for x in theme_map.values() if isinstance(x, dict)]
    theme5 = [finite(x.get("shareChangePct5d")) for x in theme_map.values() if isinstance(x, dict)]
    theme_pos = [finite(x.get("positiveRatio1d")) for x in theme_map.values() if isinstance(x, dict)]

    b1_ranked, b2_ranked = [], []
    for s in stocks:
        code = str(s.get("code") or "")
        m = margin_map.get(code) or {}
        m1 = finite(m.get("balanceChangePct1d"))
        m5 = finite(m.get("balanceChangePct5d"))
        buy = finite(m.get("buyToBalancePct"))
        mranks = [rank_pct(m1_values, m1), rank_pct(m5_values, m5), rank_pct(buy_values, buy)]
        weights = [0.50, 0.30, 0.20]
        used = [(r, w) for r, w in zip(mranks, weights) if r is not None]
        margin_score = (sum(r * w for r, w in used) / sum(w for _, w in used)) if used else None
        if margin_score is not None:
            s["marginScore"] = round(margin_score, 2)
            s["marginFactorScore"] = round(margin_score, 2)
            s["marginData"] = {
                "dataDate": (factors.get("margin") or {}).get("dataDate"),
                "balance": finite(m.get("balance")),
                "buyAmount": finite(m.get("buyAmount")),
                "balanceChange1d": finite(m.get("balanceChange1d")),
                "balanceChangePct1d": m1,
                "balanceChangePct5d": m5,
                "source": m.get("source"),
            }
            if (m1 or 0) > 0 and (m5 is None or m5 >= 0) and margin_score >= 55:
                b1_ranked.append((margin_score, code))

        matches = _theme_stats_for_sector(factors, s.get("sector"))
        best = None
        for theme, row in matches:
            r1 = rank_pct(theme1, finite(row.get("shareChangePct1d")))
            r5 = rank_pct(theme5, finite(row.get("shareChangePct5d")))
            rp = rank_pct(theme_pos, finite(row.get("positiveRatio1d")))
            vals = [(r1, 0.50), (r5, 0.30), (rp, 0.20)]
            vals = [(r, w) for r, w in vals if r is not None]
            score = (sum(r * w for r, w in vals) / sum(w for _, w in vals)) if vals else None
            if score is not None and (best is None or score > best[0]):
                best = (score, theme, row)
        if best:
            etf_score, theme, row = best
            s["etfScore"] = round(etf_score, 2)
            s["etfFlowScore"] = round(etf_score, 2)
            s["etfData"] = {
                "dataDate": (factors.get("etf") or {}).get("dataDate"),
                "theme": theme,
                "shareChangePct1d": finite(row.get("shareChangePct1d")),
                "shareChangePct5d": finite(row.get("shareChangePct5d")),
                "shareChangePct20d": finite(row.get("shareChangePct20d")),
                "positiveRatio1d": finite(row.get("positiveRatio1d")),
                "netCreationAmountEstimate1d": finite(row.get("netCreationAmountEstimate1d")),
            }
            if (finite(row.get("shareChangePct1d")) or 0) > 0 and (finite(row.get("shareChangePct5d")) is None or finite(row.get("shareChangePct5d")) >= 0) and etf_score >= 55:
                b2_ranked.append((etf_score, code))

        base = finite(s.get("score"))
        if base is None:
            base = finite(s.get("earlyEntryScore")) or finite(s.get("baseScore")) or 50.0
        flow = finite(s.get("flowScore")) or 50.0
        ms = finite(s.get("marginScore")) or 50.0
        es = finite(s.get("etfScore")) or 50.0
        composite = 0.50 * base + 0.20 * flow + 0.15 * ms + 0.15 * es
        s["slowCompositeScore"] = round(composite, 2)
        s["slowFactorDataDate"] = factors.get("dataDate")

    b1_ranked.sort(key=lambda x: (-x[0], x[1]))
    b2_ranked.sort(key=lambda x: (-x[0], x[1]))
    pools["B1"] = [c for _, c in b1_ranked[:10]]
    pools["B2"] = [c for _, c in b2_ranked[:10]]

    ranked_b4 = sorted(stocks, key=lambda s: (-(finite(s.get("slowCompositeScore")) or -1), str(s.get("code"))))
    pools["B4"] = [str(s.get("code")) for s in ranked_b4[:10] if s.get("code")]
    return stocks, pools, factors


def availability_strings(factors: dict | None):
    if not factors:
        return {
            "B1": "两融T+1日频数据暂未取得，保持为空",
            "B2": "ETF份额T+1日频数据暂未取得，保持为空",
        }
    m = factors.get("margin") or {}
    e = factors.get("etf") or {}
    return {
        "B1": f"可用：交易所两融T+1日频，数据日 {m.get('dataDate') or '—'}，覆盖 {m.get('stockCount') or 0} 只股票",
        "B2": f"可用：交易所ETF份额T+1日频，数据日 {e.get('dataDate') or '—'}，覆盖 {e.get('etfCount') or 0} 只ETF；净申赎金额为份额变化×价格的估算",
    }
