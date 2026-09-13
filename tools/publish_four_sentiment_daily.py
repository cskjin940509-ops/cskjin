#!/usr/bin/env python3
"""Publish the four-item original sentiment daily without fabricating scores."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "astock_sentiment"
HISTORY = OUT / "history"
CN = timezone(timedelta(hours=8))


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def latest_snapshot(payload, on_or_before=None):
    rows = payload if isinstance(payload, list) else (
        payload.get("snapshots") or payload.get("history") or payload.get("items") or [])
    rows = [x for x in rows if isinstance(x, dict) and x.get("date")]
    if on_or_before:
        rows = [x for x in rows if x.get("date") <= on_or_before]
    official = [x for x in rows if x.get("status") == "Official"]
    return max(official or rows, key=lambda x: x["date"], default=None)


def finite(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def prior_item(name, before_date):
    candidates = []
    for path in HISTORY.glob("*.json"):
        row = read_json(path, {})
        if row.get("reportDate", "") >= before_date:
            continue
        item = next((x for x in row.get("indices", []) if x.get("name") == name), None)
        if item:
            candidates.append((row.get("reportDate"), item))
    return max(candidates, default=(None, None))[1]


def proxy_margin_window(source_date):
    payload = read_json(ROOT / "astock_factors" / "proxy_backfill" / "margin.json", {})
    body = payload.get("data") or {}
    fields, items = body.get("fields") or [], body.get("items") or []
    required = ("trade_date", "exchange_id", "rzye")
    if not all(x in fields for x in required):
        return None
    ix = {x: fields.index(x) for x in required}; by_day = {}
    cutoff = source_date.replace("-", "")
    for row in items:
        day, exchange = str(row[ix["trade_date"]]), str(row[ix["exchange_id"]])
        if day > cutoff or exchange not in ("SSE", "SZSE"):
            continue
        value = finite(row[ix["rzye"]])
        if value is not None:
            by_day.setdefault(day, {})[exchange] = value
    balances = [(day, sum(parts.values())) for day, parts in sorted(by_day.items())
                if set(parts) == {"SSE", "SZSE"}]
    if len(balances) < 2 or balances[-1][0] != cutoff:
        return None
    deltas = [(balances[i][0], balances[i][1] - balances[i-1][1])
              for i in range(1, len(balances))]
    window = deltas[-485:]
    change = deltas[-1][1]
    score = (100 * sum(x[1] < change for x in window) / (len(window)-1)
             if len(window) == 485 else None)
    return {"balance": balances[-1][1], "change": change, "score": score,
            "observations": len(window)}


def publish(now=None, report_date=None, source_date=None, write_latest=True):
    now = now or datetime.now(CN)
    report_date = report_date or now.date().isoformat()
    snapshots = read_json(ROOT / "astock_snapshots" / "index.json", {})
    factor_path = ROOT / "astock_factors" / "history" / f"{source_date}.json" if source_date else None
    factors = read_json(factor_path, None) if factor_path else None
    factors = factors or read_json(ROOT / "astock_factors" / "latest.json", {})
    snap = latest_snapshot(snapshots, source_date)
    market = (snap or {}).get("marketSnapshot") or {}
    source_date = market.get("sourceDate") or (snap or {}).get("date")
    up, down = finite(market.get("up")), finite(market.get("down"))
    sample = finite(market.get("sampleCount"))
    profit_raw = None
    if up is not None and down is not None and up + down >= 2000:
        profit_raw = math.log((up + .5) / (down + .5))

    margin = factors.get("margin") or {}
    summary = margin.get("marketSummary") or {}
    margin_balance = finite(summary.get("financingBalance")) if summary.get("complete") else None
    previous_margin = prior_item("两融情绪", source_date or "9999-99-99")
    previous_balance = finite((previous_margin or {}).get("raw", {}).get("financingBalance"))
    margin_delta = (margin_balance - previous_balance
                    if margin_balance is not None and previous_balance is not None else None)
    proxy_margin = proxy_margin_window(source_date or source_date)
    margin_score = None
    if proxy_margin:
        margin_balance = proxy_margin["balance"]
        margin_delta = proxy_margin["change"]
        margin_score = proxy_margin["score"]

    etf = factors.get("etf") or {}
    etfs = list((etf.get("etfs") or {}).values())
    changes = [finite(x.get("shareChange1d")) for x in etfs]
    changes = [x for x in changes if x is not None]
    estimates = [finite(x.get("netCreationAmountEstimate1d")) for x in etfs]
    estimates = [x for x in estimates if x is not None]
    etf_raw = {
        "etfCount": len(etfs), "validChangeCount": len(changes),
        "netShareChange1d": sum(changes) if changes else None,
        "netCreationAmountEstimate1d": sum(estimates) if estimates else None,
        "historyObservations": len(etf.get("tradingDates") or []),
    }

    indices = [
        {"name": "市场赚钱效应", "score": None, "scoreScale": "0-100",
         "raw": {"logUpDownRatio": profit_raw, "up": up, "down": down,
                 "flat": finite(market.get("flat")), "sampleCount": sample},
         "dataDate": source_date, "availableAt": market.get("availableAt"),
         "classification": "研究原始值",
         "status": "INSUFFICIENT_485_HISTORY" if profit_raw is not None else "MISSING_INPUT",
         "blocker": "尚无485个固定股票宇宙、同口径、可得时间可审计的交易日观测",
         "positionEligible": False},
        {"name": "两融情绪", "score": margin_score, "scoreScale": "0-100",
         "raw": {"financingBalance": margin_balance, "change1d": margin_delta,
                 "exchangeCoverage": ["SSE", "SZSE"] if proxy_margin else summary.get("exchangeCoverage", []),
                 "errors": summary.get("errors", {}),
                 "historyObservations": (proxy_margin or {}).get("observations")},
         "dataDate": source_date or summary.get("dataDate") or margin.get("dataDate"),
         "availableAt": factors.get("collectedAt"), "classification": "反向工程估算",
         "status": "ESTIMATED" if margin_score is not None else ("INSUFFICIENT_485_HISTORY" if margin_delta is not None else "MISSING_INPUT"),
         "blocker": None if margin_score is not None else (summary.get("scoreBlocker") or "缺完整沪深余额或相邻交易日基数"),
         "positionEligible": margin_score is not None},
        {"name": "ETF资金强弱", "score": None, "scoreScale": "0-100",
         "raw": etf_raw, "dataDate": etf.get("dataDate"),
         "availableAt": factors.get("collectedAt"), "classification": "研究观察值",
         "status": "FORMULA_UNVERIFIED",
         "blocker": "原版ETF池、窗口、原始因子与标准化顺序未冻结；历史不足485日",
         "positionEligible": False},
        {"name": "综合市场资金情绪", "score": None, "scoreScale": "0-100",
         "raw": None, "dataDate": source_date, "availableAt": now.isoformat(),
         "classification": "不可计算", "status": "DEPENDENCIES_INCOMPLETE",
         "blocker": "前三项未全部形成正式分位，且综合权重版本未冻结",
         "positionEligible": False},
    ]
    result = {
        "schemaVersion": 1, "reportDate": report_date,
        "generatedAt": now.isoformat(), "cutoffZh": "截至生成时实际可得数据",
        "referenceReplication": "NOT_VERIFIED", "indices": indices,
        "allFourScoresAvailable": all(x["score"] is not None for x in indices),
        "positionControlEnabled": False,
        "noteZh": "缺失不补0；研究原始值不冒充原版0-100指数；不修改模拟仓位。",
    }
    OUT.mkdir(exist_ok=True); HISTORY.mkdir(exist_ok=True)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if write_latest:
        (OUT / "latest.json").write_text(text, encoding="utf-8")
    (HISTORY / f"{result['reportDate']}.json").write_text(text, encoding="utf-8")
    return result


if __name__ == "__main__":
    out = publish()
    print(json.dumps({"reportDate": out["reportDate"],
                      "available": out["allFourScoresAvailable"]}, ensure_ascii=False))
