#!/usr/bin/env python3
"""历史行业板块重建 v3.0 的基准行情可靠性包装层。

行业板块仍使用原脚本的东方财富前复权板块指数；沪深300基准先尝试原东方财富路径，
失败时改用腾讯前复权日线。只修数据获取可靠性，不改变信号、评分、入场或收益口径。
"""
from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import reconstruct_history_boards as base


_original_fetch_kline = base.fetch_kline


def fetch_tencent_csi300(limit: int = base.MAX_BARS):
    symbol = "sh000300"
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?" + urlencode({
        "param": f"{symbol},day,,,{limit},qfq"
    })
    req = Request(url, headers={
        "User-Agent": base.UA,
        "Accept": "application/json",
        "Referer": "https://gu.qq.com/",
        "Cache-Control": "no-cache",
    })
    with urlopen(req, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8", "replace"))
    root = ((payload.get("data") or {}).get(symbol) or {})
    raw_rows = root.get("qfqday") or root.get("day") or []
    out = []
    for fields in raw_rows:
        if not isinstance(fields, list) or len(fields) < 5:
            continue
        opened = base.finite(fields[1])
        closed = base.finite(fields[2])
        high = base.finite(fields[3])
        low = base.finite(fields[4])
        amount = base.finite(fields[6]) if len(fields) > 6 else None
        if not fields[0] or opened is None or closed is None or opened <= 0 or closed <= 0:
            continue
        out.append({
            "date": fields[0],
            "open": opened,
            "close": closed,
            "high": high if high is not None else max(opened, closed),
            "low": low if low is not None else min(opened, closed),
            "amount": amount,
        })
    out.sort(key=lambda x: x["date"])
    if len(out) < base.MIN_LOOKBACK + 20:
        raise RuntimeError(f"腾讯沪深300历史过短: {len(out)}")
    return out


def robust_fetch_kline(secid: str, limit: int = base.MAX_BARS):
    if secid != "1.000300":
        return _original_fetch_kline(secid, limit)
    eastmoney_error = None
    try:
        return _original_fetch_kline(secid, limit)
    except Exception as exc:
        eastmoney_error = exc
    try:
        rows = fetch_tencent_csi300(limit)
        print(json.dumps({
            "benchmarkFallback": "腾讯前复权日线",
            "bars": len(rows),
            "eastmoneyError": eastmoney_error.__class__.__name__ if eastmoney_error else None,
        }, ensure_ascii=False))
        return rows
    except Exception as tencent_error:
        raise RuntimeError(
            "沪深300双源历史均不可用："
            f"东方财富={eastmoney_error}; 腾讯={tencent_error}"
        ) from tencent_error


base.fetch_kline = robust_fetch_kline

if __name__ == "__main__":
    base.reconstruct()
