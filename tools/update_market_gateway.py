#!/usr/bin/env python3
import json, re, statistics, sys, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CN = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
GATEWAY = ROOT / "astock_gateway"
SNAPS = ROOT / "astock_snapshots" / "index.json"
UA = "Mozilla/5.0 AStockStrategy-Gateway/1.0"


def error_detail(exc):
    """Keep provider diagnostics useful without ever leaking the configured token."""
    detail = f"{type(exc).__name__}: {exc}"
    try:
        from tushare_stock_api import _token
        token = _token()
        if token:
            detail = detail.replace(token, "[redacted]")
    except Exception:
        pass
    return detail[:240]


def market_completeness(verified_today, index_count, industry_count, concept_count, breadth_count):
    return bool(verified_today and index_count >= 5 and industry_count >= 30
                and concept_count >= 100 and breadth_count >= 4000)


def get_bytes(url, timeout=15):
    req = Request(url, headers={
        "User-Agent": UA,
        "Accept": "*/*",
        "Cache-Control": "no-cache",
        "Referer": "https://quote.eastmoney.com/"
    })
    with urlopen(req, timeout=timeout) as r:
        if r.status < 200 or r.status >= 300:
            raise RuntimeError(f"HTTP {r.status}")
        return r.read()


def get_json(url):
    return json.loads(get_bytes(url).decode("utf-8", errors="replace"))


def num(v):
    try:
        if v in (None, "", "-"):
            return None
        return float(v)
    except Exception:
        return None


def tencent_quotes(symbols):
    url = "https://qt.gtimg.cn/q=" + ",".join(symbols)
    text = get_bytes(url).decode("gbk", errors="replace")
    out = {}
    for sym, payload in re.findall(r'v_([A-Za-z0-9]+)="([^"]*)"', text):
        f = payload.split("~")
        if len(f) <= 37:
            continue
        qt = f[30] if len(f) > 30 else None
        qtime = None
        if qt and len(qt) >= 14 and qt[-6:].isdigit():
            hh, mm, ss = int(qt[-6:-4]), int(qt[-4:-2]), int(qt[-2:])
            if 0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59:
                qtime = f"{hh:02d}:{mm:02d}:{ss:02d}"
        out[sym] = {
            "symbol": sym,
            "name": f[1] if len(f) > 1 else "",
            "code": f[2] if len(f) > 2 else "",
            "price": num(f[3] if len(f) > 3 else None),
            "prevClose": num(f[4] if len(f) > 4 else None),
            "changePct": num(f[32] if len(f) > 32 else None),
            "high": num(f[33] if len(f) > 33 else None),
            "low": num(f[34] if len(f) > 34 else None),
            "amount": (num(f[37]) * 10000.0) if len(f) > 37 and num(f[37]) is not None else None,
            "quoteTimeRaw": qt,
            "quoteDate": qt[:8] if qt and len(qt) >= 8 and qt[:8].isdigit() else None,
            "quoteTime": qtime,
            "source": "腾讯行情"
        }
    if not out:
        raise RuntimeError("腾讯行情返回为空")
    return out


def eastmoney_clist(fs, fields, pz=500, fid="f3"):
    params = {
        "pn": 1, "pz": pz, "po": 1, "np": 1, "fltt": 2, "invt": 2,
        "fid": fid, "fs": fs, "fields": fields,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281"
    }
    last = None
    # 实时域名在部分云机房会 502；延迟域名作为独立网络路径兜底。
    for host in ("push2.eastmoney.com", "push2delay.eastmoney.com"):
        for attempt in range(3):
            try:
                url = f"https://{host}/api/qt/clist/get?" + urlencode({**params, "_": int(time.time() * 1000)})
                data = get_json(url).get("data") or {}
                diff = data.get("diff") or []
                if diff:
                    return diff
                last = RuntimeError(f"{host} 返回空数据")
            except Exception as e:
                last = e
                time.sleep(0.8 * (attempt + 1))
    raise RuntimeError(str(last or "东方财富列表接口不可用"))


def boards(kind):
    fs = "m:90+t:2+f:!50" if kind == "industry" else "m:90+t:3+f:!50"
    rows = eastmoney_clist(fs, "f3,f6,f12,f14,f62,f184,f104,f105,f106", 500, "f3")
    out = []
    for x in rows:
        up, down, flat = int(x.get("f104") or 0), int(x.get("f105") or 0), int(x.get("f106") or 0)
        total = up + down + flat
        out.append({
            "boardCode": str(x.get("f12") or ""),
            "name": x.get("f14") or "",
            "changePct": num(x.get("f3")),
            "amount": num(x.get("f6")),
            "mainNetFlow": num(x.get("f62")),
            "mainFlowPct": num(x.get("f184")),
            "up": up, "down": down, "flat": flat,
            "breadthPct": (up / total * 100.0) if total else None,
            "source": "东方财富板块"
        })
    minimum = 30 if kind == "industry" else 100
    if len(out) < minimum:
        raise RuntimeError(f"东方财富{kind}板块样本不完整: {len(out)} < {minimum}")
    return out


def boards_with_failover(kind, trade_date):
    """Prefer Eastmoney, then use the independent Tushare/THS API for that date."""
    try:
        return boards(kind)
    except Exception as primary_error:
        try:
            from tushare_stock_api import ths_board_flows
            rows = ths_board_flows(kind, trade_date)
            for row in rows:
                row["source"] = "Tushare兼容stock_api/同花顺"
            return rows
        except Exception as secondary_error:
            raise RuntimeError(
                f"东方财富失败({error_detail(primary_error)}); "
                f"Tushare/同花顺失败({error_detail(secondary_error)})"
            ) from secondary_error


def all_a_breadth():
    fs = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
    # Providers cap pz silently. Use actual page length and verify all unique codes.
    def collect(host):
        def page(n):
            q = dict(pn=n, pz=100, po=1, np=1, fltt=2, invt=2, fid='f12', fs=fs,
                     fields='f3,f6,f12,f13,f14', ut='bd1d9ddb04089700cf9c27f6f7426281')
            data = get_json(f'https://{host}/api/qt/clist/get?' + urlencode(q)).get('data') or {}
            part = data.get('diff') or []
            if isinstance(part, dict): part = list(part.values())
            return int(data.get('total') or 0), part
        total, first = page(1)
        if total < 2000 or not first: raise RuntimeError('Incomplete full-market universe')
        size = len(first)
        if (total + size - 1) // size > 100: raise RuntimeError('Unexpected market page size')
        rows = list(first)
        with ThreadPoolExecutor(max_workers=6) as pool:
            for count, part in pool.map(page, range(2, (total + size - 1) // size + 1)):
                if count != total: raise RuntimeError('Market universe changed during pagination')
                rows.extend(part)
        unique = {(x.get('f13'), x.get('f12')): x for x in rows if x.get('f12')}
        if len(unique) != total: raise RuntimeError('Missing or duplicated market pages')
        return list(unique.values())
    failures = []
    for host in ('push2.eastmoney.com', 'push2delay.eastmoney.com'):
        try:
            rows = collect(host)
            break
        except Exception as exc:
            failures.append(type(exc).__name__)
    else:
        raise RuntimeError('Full-market pagination failed: ' + ','.join(failures))

    changes, amounts = [], []
    up = down = flat = 0
    for x in rows:
        ch = num(x.get("f3")); amt = num(x.get("f6"))
        if ch is not None:
            changes.append(ch)
            if ch > 0: up += 1
            elif ch < 0: down += 1
            else: flat += 1
        if amt is not None and amt > 0:
            amounts.append(amt)
    if not changes:
        raise RuntimeError("全A截面返回为空")
    return {
        "up": up, "down": down, "flat": flat,
        "medianChangePct": statistics.median(changes),
        "totalAmount": sum(amounts),
        "sampleCount": len(changes),
        "source": "东方财富全A截面"
    }


def breadth_with_failover(trade_date):
    try:
        return all_a_breadth()
    except Exception as primary_error:
        try:
            from tushare_stock_api import daily_market_breadth
            return daily_market_breadth(trade_date)
        except Exception as secondary_error:
            raise RuntimeError(
                f"东方财富失败({error_detail(primary_error)}); "
                f"Tushare全市场日线失败({error_detail(secondary_error)})"
            ) from secondary_error


def stock_api_quotes(symbols):
    """Best-effort quote failover for equity codes; index freshness stays Tencent-gated."""
    from tushare_stock_api import realtime_quotes
    index_symbols = {"sh000001", "sz399006", "sh000688", "sh000300", "sh000852"}
    codes = sorted({symbol[2:] for symbol in symbols
                    if symbol not in index_symbols and symbol[:2] in ("sh", "sz", "bj")
                    and symbol[2:].isdigit()})
    if not codes:
        return {}
    raw = realtime_quotes(codes)
    out = {}
    for symbol in symbols:
        if symbol in index_symbols:
            continue
        code = symbol[2:] if symbol[:2] in ("sh", "sz", "bj") else ""
        row = raw.get(code) or {}
        if not row.get("quoteOk") or not row.get("price"):
            continue
        stamp = str(row.get("quoteTime") or "")
        digits = re.sub(r"\D", "", stamp)
        out[symbol] = {
            "symbol": symbol, "name": row.get("name") or code, "code": code,
            "price": row.get("price"), "prevClose": row.get("prevClose"),
            "changePct": row.get("changePct"), "high": row.get("high"), "low": row.get("low"),
            "amount": row.get("amount"), "quoteTimeRaw": digits,
            "quoteDate": digits[:8] if len(digits) >= 8 else None,
            "quoteTime": digits[-6:] if len(digits) >= 14 else None,
            "source": "Tushare兼容stock_api实时行情",
        }
    return out


def index_snapshot(quotes):
    names = {
        "sh000001": "上证指数", "sz399006": "创业板指", "sh000688": "科创50",
        "sh000300": "沪深300", "sh000852": "中证1000"
    }
    out = {}
    for sym, name in names.items():
        q = quotes.get(sym)
        if not q: continue
        out[sym] = {
            "name": name, "close": q.get("price"), "changePct": q.get("changePct"),
            "amount": q.get("amount"), "quoteTime": q.get("quoteTime"),
            "quoteDate": q.get("quoteDate"), "source": q.get("source")
        }
    return out


def merge_snapshot(day, market, heat):
    if not SNAPS.exists(): return False
    arr = json.loads(SNAPS.read_text(encoding="utf-8"))
    changed = False
    for item in arr:
        if item.get("date") != day: continue
        item["marketSnapshot"] = market
        item["boardHeatmap"] = heat
        sync = item.setdefault("syncStatus", {})
        sync.update({"marketSnapshot": "ready", "boardHeatmap": "ready", "marketUpdatedAt": market.get("availableAt")})
        changed = True
        break
    if changed:
        SNAPS.write_text(json.dumps(arr, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


def active_pool_symbols():
    if not SNAPS.exists():
        return [], None
    try:
        snapshots = json.loads(SNAPS.read_text(encoding="utf-8"))
        official = [item for item in snapshots if item.get("status") == "Official"]
        latest = max(official, key=lambda item: item.get("date", "")) if official else None
        if not latest:
            return [], None
        codes = sorted({
            str(code)
            for members in (latest.get("pools") or {}).values()
            for code in (members or [])
            if str(code).isdigit()
        })
        symbols = []
        for code in codes:
            prefix = "bj" if code.startswith(("8", "9")) else ("sh" if code.startswith(("5", "6")) else "sz")
            symbols.append(prefix + code)
        return symbols, latest.get("date")
    except Exception:
        return [], None


def main():
    now = datetime.now(CN)
    day = now.strftime("%Y-%m-%d")
    day_compact = now.strftime("%Y%m%d")
    generated = now.isoformat(timespec="seconds")
    errors = []
    index_symbols = ["sh000001", "sz399006", "sh000688", "sh000300", "sh000852"]
    pool_symbols, active_cohort_date = active_pool_symbols()
    symbols = list(dict.fromkeys(index_symbols + pool_symbols))

    try:
        quotes = tencent_quotes(symbols)
    except Exception as e:
        quotes = {}
        errors.append("腾讯行情：" + str(e))

    # Complete only missing stock quotes. The second provider is never allowed
    # to invent an index quote timestamp, which is required by the close gate.
    if len(quotes) < len(symbols):
        missing_symbols = [symbol for symbol in pool_symbols if symbol not in quotes]
        if missing_symbols:
            try:
                secondary = stock_api_quotes(missing_symbols)
                quotes.update(secondary)
            except Exception as e:
                errors.append("Tushare兼容个股行情：" + str(e))

    try:
        industry = boards_with_failover("industry", day_compact)
    except Exception as e:
        industry = []
        errors.append("行业板块：" + str(e))

    try:
        concept = boards_with_failover("concept", day_compact)
    except Exception as e:
        concept = []
        errors.append("概念板块：" + str(e))

    try:
        breadth = breadth_with_failover(day_compact)
    except Exception as e:
        breadth = {}
        errors.append("全A截面：" + str(e))

    index_quotes = [quotes.get(symbol) or {} for symbol in index_symbols]
    provider_dates = sorted({q.get("quoteDate") for q in index_quotes if q.get("quoteDate")})
    latest_provider_date = provider_dates[-1] if provider_dates else None
    verified_today = latest_provider_date == day_compact
    complete = market_completeness(
        verified_today, len(index_snapshot(quotes)), len(industry), len(concept),
        breadth.get("sampleCount") or 0,
    )
    market = {
        "sourceDate": day if verified_today else (f"{latest_provider_date[:4]}-{latest_provider_date[4:6]}-{latest_provider_date[6:8]}" if latest_provider_date and len(latest_provider_date)==8 else None),
        "availableAt": generated,
        "confidence": "高" if complete else ("中" if verified_today and (quotes or industry) else "低"),
        "completeness": "完整" if complete else "部分",
        "verifiedToday": verified_today,
        "dataSource": ", ".join(sorted({q.get("source") for q in quotes.values() if q.get("source")}
                                         | {x.get("source") for x in industry + concept if x.get("source")}
                                         | ({breadth.get("source")} if breadth.get("source") else set()))),
        "indices": index_snapshot(quotes),
        "totalAmount": breadth.get("totalAmount"),
        "up": breadth.get("up"), "down": breadth.get("down"), "flat": breadth.get("flat"),
        "medianChangePct": breadth.get("medianChangePct"),
        "sampleCount": breadth.get("sampleCount")
    }
    heat = {"industry": industry, "concept": concept, "sourceDate": market.get("sourceDate"), "availableAt": generated}
    payload = {
        "schemaVersion": 1,
        "generatedAt": generated,
        "state": "可用" if complete else ("部分可用" if (quotes or industry or concept) else "不可用"),
        "verifiedToday": verified_today,
        "providerDate": latest_provider_date,
        "activeCohortDate": active_cohort_date,
        "activePoolQuoteCount": sum(1 for symbol in pool_symbols if symbol in quotes),
        "marketSnapshot": market,
        "boardHeatmap": heat,
        "quotes": quotes,
        "errors": errors,
        "dataSources": sorted({q.get("source") for q in quotes.values() if q.get("source")}
                              | {x.get("source") for x in industry + concept if x.get("source")}
                              | ({breadth.get("source")} if breadth.get("source") else set()))
    }

    GATEWAY.mkdir(parents=True, exist_ok=True)
    (GATEWAY / "latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 只有数据源明确返回当天日期，才允许冻结当天市场事实，避免陈旧行情污染历史。
    if verified_today and now.weekday() < 5 and now.time().hour >= 15:
        hist = GATEWAY / "history"
        hist.mkdir(parents=True, exist_ok=True)
        (hist / f"{day}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        merge_snapshot(day, market, heat)

    print(json.dumps({
        "generatedAt": generated, "verifiedToday": verified_today, "providerDate": latest_provider_date,
        "indices": len(market["indices"]), "activeCohortDate": active_cohort_date,
        "poolQuotes": sum(1 for symbol in pool_symbols if symbol in quotes),
        "industry": len(industry), "concept": len(concept),
        "breadth": breadth.get("sampleCount"), "errors": errors
    }, ensure_ascii=False))
    if not quotes and not industry and not concept:
        sys.exit(2)


if __name__ == "__main__":
    main()
