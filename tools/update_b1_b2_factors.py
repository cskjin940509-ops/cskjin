#!/usr/bin/env python3
"""Build T+1 B1/B2 funding factors from exchange-public data via AKShare.

B1: SSE/SZSE per-security margin-financing detail.
B2: SSE/SZSE daily ETF shares; primary-market net creation/redemption is inferred
    from changes in units outstanding. No intraday claim is made.

The output is a separate immutable-by-date factor snapshot. Trading workflows use
only the latest factor date strictly earlier than the current trading decision day.
"""
from __future__ import annotations

import json
import math
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import akshare as ak
import pandas as pd

CN = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "astock_factors"
HIST = OUT / "history"
OUT.mkdir(exist_ok=True)
HIST.mkdir(exist_ok=True)
VERSION = "v1.0-exchange-public-tplus1"


def fnum(v):
    try:
        if pd.isna(v):
            return None
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def code6(v):
    s = str(v).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s.zfill(6) if s.isdigit() else s


def pct_rank(values, value):
    xs = sorted(x for x in values if x is not None and math.isfinite(x))
    if value is None or not xs:
        return None
    lt = sum(x < value for x in xs)
    eq = sum(x == value for x in xs)
    return 100.0 * (lt + 0.5 * eq) / len(xs)


def date_candidates(days=45):
    today = datetime.now(CN).date()
    return [(today - timedelta(days=i)).strftime("%Y%m%d") for i in range(days + 1)
            if (today - timedelta(days=i)).weekday() < 5]


def df_records(df):
    if df is None or getattr(df, "empty", True):
        return []
    return df.to_dict("records")


def fetch_margin_one(day8):
    out = {}
    errors = []
    for market, fn in (("SSE", ak.stock_margin_detail_sse), ("SZSE", ak.stock_margin_detail_szse)):
        try:
            rows = df_records(fn(date=day8))
        except Exception as e:
            errors.append(f"{market}:{e.__class__.__name__}")
            rows = []
        norm = {}
        for r in rows:
            code = code6(r.get("标的证券代码") if market == "SSE" else r.get("证券代码"))
            if not code or not code[:1].isdigit():
                continue
            balance = fnum(r.get("融资余额"))
            buy = fnum(r.get("融资买入额"))
            repay = fnum(r.get("融资偿还额")) if market == "SSE" else None
            if balance is None:
                continue
            norm[code] = {
                "code": code,
                "name": str(r.get("标的证券简称") if market == "SSE" else r.get("证券简称") or ""),
                "market": market,
                "financingBalance": balance,
                "financingBuy": buy,
                "financingRepay": repay,
                "shortBalance": fnum(r.get("融券余额")),
                "shortVolume": fnum(r.get("融券余量")),
                "shortSellVolume": fnum(r.get("融券卖出量")),
            }
        if norm:
            out[market] = norm
    return day8, out, errors


def load_margin_history():
    # 12 successful trading dates are enough for 1D/5D plus holiday tolerance.
    candidates = date_candidates(24)
    results = {}
    errors = {}
    with ThreadPoolExecutor(max_workers=5) as ex:
        fut = {ex.submit(fetch_margin_one, d): d for d in candidates[:18]}
        for f in as_completed(fut):
            d, markets, errs = f.result()
            if markets:
                results[d] = markets
            if errs:
                errors[d] = errs
    # Keep dates with meaningful combined coverage.
    dates = []
    for d in sorted(results, reverse=True):
        n = sum(len(x) for x in results[d].values())
        if n >= 500:
            dates.append(d)
        if len(dates) >= 8:
            break
    dates = sorted(dates)
    if len(dates) < 2:
        raise RuntimeError("两融明细不足两个有效交易日")
    latest = dates[-1]
    current = {}
    for market, rows in results[latest].items():
        current.update(rows)
    merged_by_date = {}
    for d in dates:
        m = {}
        for rows in results[d].values():
            m.update(rows)
        merged_by_date[d] = m

    all_1d, all_5d, all_buy_ratio, all_net_ratio = [], [], [], []
    metrics = {}
    for code, row in current.items():
        prev = merged_by_date[dates[-2]].get(code)
        p5 = merged_by_date[dates[-6]].get(code) if len(dates) >= 6 else None
        bal = row.get("financingBalance")
        prev_bal = prev.get("financingBalance") if prev else None
        p5_bal = p5.get("financingBalance") if p5 else None
        one = (bal / prev_bal - 1.0) if bal is not None and prev_bal and prev_bal > 0 else None
        five = (bal / p5_bal - 1.0) if bal is not None and p5_bal and p5_bal > 0 else None
        net = (bal - prev_bal) if bal is not None and prev_bal is not None else None
        # SSE has direct repayment; SZSE net increase is exactly balance change under the exchange identity.
        direct_net = None
        if row.get("financingBuy") is not None and row.get("financingRepay") is not None:
            direct_net = row["financingBuy"] - row["financingRepay"]
        net = direct_net if direct_net is not None else net
        buy_ratio = (row.get("financingBuy") / prev_bal) if row.get("financingBuy") is not None and prev_bal and prev_bal > 0 else None
        net_ratio = (net / prev_bal) if net is not None and prev_bal and prev_bal > 0 else None
        metrics[code] = {**row,
            "factorDate": f"{latest[:4]}-{latest[4:6]}-{latest[6:]}",
            "previousFactorDate": f"{dates[-2][:4]}-{dates[-2][4:6]}-{dates[-2][6:]}",
            "financingNetIncrease": net,
            "financingBalance1dPct": one,
            "financingBalance5dPct": five,
            "financingBuyToPrevBalance": buy_ratio,
            "financingNetIncreaseToPrevBalance": net_ratio,
        }
        all_1d.append(one); all_5d.append(five); all_buy_ratio.append(buy_ratio); all_net_ratio.append(net_ratio)
    for x in metrics.values():
        parts = []
        for weight, vals, key in ((0.40, all_net_ratio, "financingNetIncreaseToPrevBalance"),
                                  (0.30, all_1d, "financingBalance1dPct"),
                                  (0.20, all_5d, "financingBalance5dPct"),
                                  (0.10, all_buy_ratio, "financingBuyToPrevBalance")):
            r = pct_rank(vals, x.get(key))
            if r is not None:
                parts.append((weight, r))
        x["marginScore"] = round(sum(w*r for w,r in parts) / sum(w for w,_ in parts), 2) if parts else None
    return {
        "tradeDate": metrics[next(iter(metrics))]["factorDate"] if metrics else None,
        "historyDates": [f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in dates],
        "stockCount": len(metrics),
        "stocks": metrics,
        "topPositive": sorted(metrics.values(), key=lambda x: (x.get("marginScore") is not None, x.get("marginScore") or -1), reverse=True)[:30],
        "source": "上交所/深交所融资融券逐证券明细（AKShare公开接口适配）",
        "errors": errors,
    }


def fetch_sse_etf_one(day8):
    try:
        rows = df_records(ak.fund_etf_scale_sse(date=day8))
    except Exception:
        return day8, {}
    out = {}
    for r in rows:
        code = code6(r.get("基金代码"))
        share_raw = fnum(r.get("基金份额"))
        if not code or share_raw is None:
            continue
        # SSE public table is in 万份; normalize to actual shares.
        out[code] = {
            "code": code,
            "name": str(r.get("基金简称") or ""),
            "market": "SSE",
            "shares": share_raw * 10000.0,
        }
    return day8, out


def load_etf_history():
    candidates = date_candidates(48)
    sse = {}
    with ThreadPoolExecutor(max_workers=5) as ex:
        fut = {ex.submit(fetch_sse_etf_one, d): d for d in candidates}
        for f in as_completed(fut):
            d, rows = f.result()
            if len(rows) >= 100:
                sse[d] = rows
    # SZSE offers a date-range daily ETF scale endpoint.
    start = (datetime.now(CN).date() - timedelta(days=48)).strftime("%Y%m%d")
    end = datetime.now(CN).date().strftime("%Y%m%d")
    sz_rows = df_records(ak.fund_scale_daily_szse(start_date=start, end_date=end, symbol="ETF"))
    sz = {}
    for r in sz_rows:
        dval = r.get("日期")
        if hasattr(dval, "strftime"):
            day8 = dval.strftime("%Y%m%d")
        else:
            day8 = str(dval).replace("-", "")[:8]
        code = code6(r.get("基金代码"))
        shares = fnum(r.get("基金份额"))
        if len(day8) != 8 or not code or shares is None:
            continue
        sz.setdefault(day8, {})[code] = {
            "code": code,
            "name": str(r.get("基金简称") or ""),
            "market": "SZSE",
            "shares": shares,
        }
    dates = sorted({*sse.keys(), *sz.keys()})
    # Require at least 2 dates; prefer dates where both exchanges have data.
    good = [d for d in dates if len(sse.get(d, {})) + len(sz.get(d, {})) >= 300]
    if len(good) < 2:
        raise RuntimeError("ETF份额不足两个有效交易日")
    latest = good[-1]
    history = good[-25:]
    by_date = {}
    for d in history:
        x = {}
        x.update(sse.get(d, {})); x.update(sz.get(d, {}))
        by_date[d] = x

    # Previous-close prices are used only to estimate RMB creation amount.
    spot = {}
    try:
        for r in df_records(ak.fund_etf_spot_em()):
            c = code6(r.get("代码"))
            spot[c] = {
                "prevClose": fnum(r.get("昨收")),
                "latestPrice": fnum(r.get("最新价")),
                "amount": fnum(r.get("成交额")),
            }
    except Exception:
        pass

    cur = by_date[latest]
    prev_date = history[-2]
    d5 = history[-6] if len(history) >= 6 else None
    d20 = history[-21] if len(history) >= 21 else None
    vals_amt, vals_1d, vals_5d, vals_20d = [], [], [], []
    metrics = {}
    for code, row in cur.items():
        prev = by_date.get(prev_date, {}).get(code)
        p5 = by_date.get(d5, {}).get(code) if d5 else None
        p20 = by_date.get(d20, {}).get(code) if d20 else None
        sh = row.get("shares")
        psh = prev.get("shares") if prev else None
        sh5 = p5.get("shares") if p5 else None
        sh20 = p20.get("shares") if p20 else None
        delta = sh - psh if sh is not None and psh is not None else None
        one = sh / psh - 1.0 if sh is not None and psh and psh > 0 else None
        five = sh / sh5 - 1.0 if sh is not None and sh5 and sh5 > 0 else None
        twenty = sh / sh20 - 1.0 if sh is not None and sh20 and sh20 > 0 else None
        px = (spot.get(code) or {}).get("prevClose") or (spot.get(code) or {}).get("latestPrice")
        est = delta * px if delta is not None and px is not None else None
        metrics[code] = {**row,
            "factorDate": f"{latest[:4]}-{latest[4:6]}-{latest[6:]}",
            "previousFactorDate": f"{prev_date[:4]}-{prev_date[4:6]}-{prev_date[6:]}",
            "shareChange1d": delta,
            "shareChange1dPct": one,
            "shareChange5dPct": five,
            "shareChange20dPct": twenty,
            "estimatedNetCreationAmount": est,
            "priceForEstimate": px,
            "secondaryMarketAmount": (spot.get(code) or {}).get("amount"),
        }
        vals_amt.append(est); vals_1d.append(one); vals_5d.append(five); vals_20d.append(twenty)
    for x in metrics.values():
        parts = []
        for weight, vals, key in ((0.40, vals_amt, "estimatedNetCreationAmount"),
                                  (0.30, vals_1d, "shareChange1dPct"),
                                  (0.20, vals_5d, "shareChange5dPct"),
                                  (0.10, vals_20d, "shareChange20dPct")):
            r = pct_rank(vals, x.get(key))
            if r is not None:
                parts.append((weight, r))
        x["etfFlowScore"] = round(sum(w*r for w,r in parts) / sum(w for w,_ in parts), 2) if parts else None
    return {
        "tradeDate": f"{latest[:4]}-{latest[4:6]}-{latest[6:]}",
        "historyDates": [f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in history],
        "fundCount": len(metrics),
        "funds": metrics,
        "topCreations": sorted(metrics.values(), key=lambda x: x.get("estimatedNetCreationAmount") or -1e99, reverse=True)[:40],
        "topRedemptions": sorted(metrics.values(), key=lambda x: x.get("estimatedNetCreationAmount") or 1e99)[:40],
        "source": "上交所ETF基金份额 + 深交所ETF基金规模日频（AKShare公开接口适配）",
        "method": "一级净申赎代理=当日基金份额-前一交易日基金份额；金额=份额变化×匹配到的ETF前收/最新价，仅为估算",
    }


def main():
    margin = load_margin_history()
    etf = load_etf_history()
    generated = datetime.now(CN).isoformat(timespec="seconds")
    payload = {
        "schemaVersion": VERSION,
        "generatedAt": generated,
        "timing": "T+1日频；不得标记为盘中实时",
        "margin": margin,
        "etf": etf,
        "quality": {
            "marginReady": margin.get("stockCount", 0) >= 500,
            "etfReady": etf.get("fundCount", 0) >= 300,
            "notes": [
                "两融使用交易所公开逐证券日频明细。",
                "ETF使用交易所公开基金份额变化推断一级净申购/赎回；估算金额不是二级市场主力净流入。",
                "B2映射到行业/个股时必须保留ETF名称匹配方法与置信度，不冒充精确持仓穿透。",
            ],
        },
    }
    latest_date = min(x for x in (margin.get("tradeDate"), etf.get("tradeDate")) if x)
    path = HIST / f"{latest_date}.json"
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")
    (OUT / "latest.json").write_text(text, encoding="utf-8")
    print(json.dumps({
        "state": "updated",
        "marginDate": margin.get("tradeDate"),
        "marginStocks": margin.get("stockCount"),
        "etfDate": etf.get("tradeDate"),
        "etfFunds": etf.get("fundCount"),
        "historyFile": str(path.relative_to(ROOT)),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
