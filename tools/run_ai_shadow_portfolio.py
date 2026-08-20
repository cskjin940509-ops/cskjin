#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
import re
import sys
import urllib.request
from copy import deepcopy
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

CN = ZoneInfo("Asia/Shanghai")
ROOT = Path(__file__).resolve().parents[1]
RADAR = ROOT / "astock_radar" / "latest.json"
OUT = ROOT / "astock_ai_portfolio"
STATE_PATH = OUT / "state.json"
LEDGER_PATH = OUT / "ledger.json"
LATEST_PATH = OUT / "latest.json"
INITIAL_CAPITAL = 1_000_000.0
STRATEGY_VERSION = "v1.0-ai-shadow-point-in-time"

MAX_POSITIONS = 5
MAX_GROSS_WEIGHT = 0.60
MAX_SINGLE_WEIGHT = 0.15
MAX_SECTOR_WEIGHT = 0.25
MAX_NEW_BUYS_PER_DAY = 3
MIN_BUY_SCORE = 64.0
BUY_SLIPPAGE_BPS = 5.0
SELL_SLIPPAGE_BPS = 5.0

BROKER_COMMISSION_RATE = 0.0002
MIN_COMMISSION = 5.0
REGULATORY_FEE_RATE = 0.0000541
STAMP_DUTY_SELL_RATE = 0.0005


def now_cn() -> datetime:
    return datetime.now(CN)


def iso(dt: datetime | None = None) -> str:
    return (dt or now_cn()).isoformat(timespec="seconds")


def trading_session(dt: datetime) -> bool:
    if dt.weekday() >= 5:
        return False
    t = dt.time()
    return time(9, 30) <= t <= time(11, 30) or time(13, 0) <= t <= time(15, 0)


def can_open_new(dt: datetime) -> bool:
    if not trading_session(dt):
        return False
    return dt.time() <= time(14, 50)


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return deepcopy(default)


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def symbol(code: str) -> str:
    return ("sh" if code.startswith(("5", "6", "9")) else "sz") + code


def fetch_tencent_quotes(codes: list[str]) -> dict[str, dict]:
    codes = sorted({c for c in codes if re.fullmatch(r"\d{6}", c or "")})
    if not codes:
        return {}
    q = ",".join(symbol(c) for c in codes)
    req = urllib.request.Request(
        f"https://qt.gtimg.cn/q={q}",
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/", "Accept": "*/*"},
    )
    try:
        raw = urllib.request.urlopen(req, timeout=8).read().decode("gbk", errors="ignore")
    except Exception:
        return {}
    out: dict[str, dict] = {}
    for line in raw.split(";"):
        m = re.search(r'v_(sh|sz)(\d{6})="([^"]*)"', line)
        if not m:
            continue
        code = m.group(2)
        f = m.group(3).split("~")
        try:
            price = float(f[3]) if len(f) > 3 and f[3] else None
            prev = float(f[4]) if len(f) > 4 and f[4] else None
            name = f[1] if len(f) > 1 else code
            quote_time = f[30] if len(f) > 30 else None
            change_pct = ((price / prev - 1) * 100) if price and prev else None
            out[code] = {"code": code, "name": name, "price": price, "prevClose": prev, "changePct": change_pct, "quoteTime": quote_time, "source": "腾讯实时行情"}
        except Exception:
            continue
    return out


def round_tick(price: float) -> float:
    return round(max(price, 0.01) + 1e-9, 2)


def exec_price(reference: float, side: str) -> float:
    bps = BUY_SLIPPAGE_BPS if side == "BUY" else -SELL_SLIPPAGE_BPS
    return round_tick(reference * (1 + bps / 10000.0))


def fees(amount: float, side: str) -> float:
    commission = max(MIN_COMMISSION, amount * BROKER_COMMISSION_RATE)
    regulatory = amount * REGULATORY_FEE_RATE
    stamp = amount * STAMP_DUTY_SELL_RATE if side == "SELL" else 0.0
    return round(commission + regulatory + stamp, 2)


def new_state() -> dict:
    return {"schemaVersion": 1, "strategyVersion": STRATEGY_VERSION, "mode": "AI影子实盘", "simulated": True, "initialCapital": INITIAL_CAPITAL, "cash": INITIAL_CAPITAL, "realizedPnl": 0.0, "positions": {}, "navHistory": [], "dailyControl": {}, "createdAt": iso(), "updatedAt": iso()}


def get_daily_control(state: dict, date: str) -> dict:
    return state.setdefault("dailyControl", {}).setdefault(date, {"newBuys": 0, "sells": 0, "lastDecisionAt": None})


def mark_seen_date(pos: dict, date: str) -> None:
    seen = pos.setdefault("seenTradeDates", [])
    if date not in seen:
        seen.append(date)


def position_market_value(pos: dict, prices: dict[str, float]) -> float:
    p = prices.get(pos["code"], pos.get("lastPrice") or pos.get("avgCost") or 0.0)
    return float(pos.get("qty", 0)) * float(p or 0.0)


def portfolio_nav(state: dict, prices: dict[str, float]) -> tuple[float, float]:
    mv = sum(position_market_value(p, prices) for p in state.get("positions", {}).values())
    return float(state.get("cash", 0.0)) + mv, mv


def current_weights(state: dict, prices: dict[str, float]) -> tuple[dict[str, float], dict[str, float], float]:
    nav, _ = portfolio_nav(state, prices)
    nav = max(nav, 1.0)
    by_code: dict[str, float] = {}
    by_sector: dict[str, float] = {}
    for code, p in state.get("positions", {}).items():
        w = position_market_value(p, prices) / nav
        by_code[code] = w
        sector = p.get("sector") or "未知"
        by_sector[sector] = by_sector.get(sector, 0.0) + w
    return by_code, by_sector, sum(by_code.values())


def candidate_reference_price(stock: dict) -> tuple[float | None, str, float | None]:
    primary = stock.get("price")
    y = stock.get("yunai") or {}
    yp = y.get("price") if y.get("quoteOk") else None
    divergence = None
    if primary and yp:
        divergence = abs(float(yp) / float(primary) - 1.0) * 100
        if divergence <= 0.30:
            return (float(primary) + float(yp)) / 2.0, "东方财富+Yunai双源均价", divergence
        return None, "双源价格偏差过大", divergence
    if primary:
        return float(primary), "东方财富盘中行情", divergence
    if yp:
        return float(yp), "Yunai盘中行情", divergence
    return None, "无可用价格", divergence


def score_candidate(stock: dict) -> tuple[float, list[str], list[str]]:
    reasons: list[str] = []
    rejects: list[str] = []
    base = float(stock.get("earlyEntryScore") or 0.0)
    formation = float(stock.get("mainlineFormationScore") or 0.0)
    flow_score = float(stock.get("flowScore") or 0.0)
    flow_pct = float(stock.get("mainFlowPct") or 0.0)
    change = float(stock.get("changePct") or 0.0)
    amount = float(stock.get("amount") or 0.0)
    stage = str(stock.get("mainlineStage") or "")
    chase = str(stock.get("chaseRisk") or "").upper()
    y = stock.get("yunai") or {}

    score = base
    reasons.append(f"提前分{base:.0f}")
    if stage == "CONFIRMING":
        score += 5; reasons.append("主线确认中+5")
    elif stage == "EMERGING":
        score += 3; reasons.append("主线潜在形成+3")
    elif stage == "ESTABLISHED":
        score -= 3; reasons.append("已成主线-3")

    if formation >= 66:
        score += 4; reasons.append("形成分强+4")
    elif formation >= 60:
        score += 2; reasons.append("形成分改善+2")

    if flow_pct >= 12:
        score += 5; reasons.append("资金强度高+5")
    elif flow_pct >= 6:
        score += 3; reasons.append("资金正向+3")
    elif flow_pct < 0:
        score -= 6; reasons.append("资金转负-6")

    if flow_score >= 70:
        score += 3; reasons.append("资金评分高+3")

    if -0.8 <= change <= 3.5:
        score += 4; reasons.append("价格尚未充分扩张+4")
    elif 3.5 < change <= 4.5:
        score += 1; reasons.append("价格开始扩张+1")
    elif change > 4.5:
        rejects.append("当日涨幅已超过提前介入上限")
    elif change < -2.5:
        rejects.append("当日走势明显走弱")

    if amount < 50_000_000:
        rejects.append("成交额低于流动性门槛")

    if chase == "HIGH":
        rejects.append("追高风险高")
    elif chase == "MEDIUM":
        score -= 5; reasons.append("追高风险中-5")
    elif chase == "LOW":
        score += 2; reasons.append("追高风险低+2")

    if y.get("quoteOk") and stock.get("price") and y.get("price"):
        div = abs(float(y["price"]) / float(stock["price"]) - 1) * 100
        if div > 0.50:
            rejects.append(f"双源价格偏差{div:.2f}%")
    confirmation = y.get("confirmation")
    if confirmation == "POSITIVE_INDEPENDENT_FLOW":
        score += 5; reasons.append("Yunai独立资金正确认+5")
    elif confirmation == "NEGATIVE_INDEPENDENT_FLOW":
        score -= 8; reasons.append("Yunai独立资金负确认-8")

    return round(score, 2), reasons, rejects


def target_weight(score: float) -> float:
    if score >= 82: return 0.15
    if score >= 76: return 0.12
    if score >= 70: return 0.10
    return 0.08


def append_decision(ledger: list, **kwargs) -> dict:
    item = {"decisionId": f"{now_cn().strftime('%Y%m%d-%H%M%S')}-{len(ledger)+1:05d}", "timestamp": iso(), "strategyVersion": STRATEGY_VERSION, "mode": "AI影子实盘", "simulated": True, **kwargs}
    ledger.append(item)
    return item


def buy_position(state: dict, ledger: list, stock: dict, score: float, reasons: list[str], ref_price: float, ref_source: str, prices: dict[str, float]) -> dict | None:
    code = stock["code"]
    if code in state["positions"]:
        return None
    nav, _ = portfolio_nav(state, prices)
    _, sector_weights, gross = current_weights(state, prices)
    sector = stock.get("sector") or "未知"
    desired = min(target_weight(score), MAX_SINGLE_WEIGHT, MAX_GROSS_WEIGHT - gross, MAX_SECTOR_WEIGHT - sector_weights.get(sector, 0.0))
    if desired < 0.04:
        return None
    px = exec_price(ref_price, "BUY")
    budget = min(state["cash"] * 0.98, nav * desired)
    qty = int(budget / px / 100) * 100
    if qty < 100:
        return None
    amount = round(px * qty, 2)
    fee = fees(amount, "BUY")
    if amount + fee > state["cash"]:
        qty = int((state["cash"] - MIN_COMMISSION) / px / 100) * 100
        amount = round(px * qty, 2); fee = fees(amount, "BUY")
    if qty < 100 or amount + fee > state["cash"]:
        return None

    state["cash"] = round(state["cash"] - amount - fee, 2)
    dt = now_cn()
    position = {"code": code, "name": stock.get("name") or code, "sector": sector, "qty": qty, "avgCost": round((amount + fee) / qty, 4), "costAmount": round(amount + fee, 2), "entryPrice": px, "entryReferencePrice": round(ref_price, 4), "entryPriceSource": ref_source, "entryTimestamp": iso(dt), "entryDate": dt.date().isoformat(), "initialWeightTarget": round(desired, 4), "lastPrice": ref_price, "lastPriceAt": iso(dt), "missingRadarCount": 0, "partialProfitTaken": False, "seenTradeDates": [dt.date().isoformat()], "buyScore": score, "buyReasonZh": "；".join(reasons), "invalidationZh": "主线连续退出雷达、资金显著转负，或相对持仓成本跌幅达到4%", "expectedHorizonZh": "次日优先验证，正常持有1-3个交易日，最长约5个交易日"}
    state["positions"][code] = position
    get_daily_control(state, dt.date().isoformat())["newBuys"] += 1
    return append_decision(ledger, side="BUY", sideZh="买入", code=code, name=position["name"], sector=sector, qty=qty, price=px, referencePrice=round(ref_price, 4), priceSource=ref_source, amount=amount, fee=fee, targetWeightPct=round(desired * 100, 2), decisionScore=score, reasonZh=position["buyReasonZh"], invalidationZh=position["invalidationZh"], expectedHorizonZh=position["expectedHorizonZh"])


def sell_position(state: dict, ledger: list, pos: dict, qty: int, ref_price: float, reason: str, prices: dict[str, float]) -> dict | None:
    qty = min(int(qty), int(pos.get("qty", 0))); qty = (qty // 100) * 100
    if qty <= 0:
        return None
    px = exec_price(ref_price, "SELL")
    amount = round(px * qty, 2); fee = fees(amount, "SELL")
    avg_cost = float(pos.get("avgCost") or 0.0); basis = round(avg_cost * qty, 2)
    realized = round(amount - fee - basis, 2)
    state["cash"] = round(state["cash"] + amount - fee, 2)
    state["realizedPnl"] = round(float(state.get("realizedPnl", 0.0)) + realized, 2)
    remain = int(pos["qty"]) - qty
    decision = append_decision(ledger, side="SELL", sideZh="卖出", code=pos["code"], name=pos.get("name") or pos["code"], sector=pos.get("sector") or "未知", qty=qty, price=px, referencePrice=round(ref_price, 4), priceSource="腾讯实时行情/雷达行情", amount=amount, fee=fee, realizedPnl=realized, realizedReturnPct=round((px / avg_cost - 1) * 100, 2) if avg_cost else None, reasonZh=reason, remainingQty=remain)
    if remain <= 0:
        state["positions"].pop(pos["code"], None)
    else:
        pos["qty"] = remain; pos["costAmount"] = round(avg_cost * remain, 2)
        if "止盈" in reason: pos["partialProfitTaken"] = True
    get_daily_control(state, now_cn().date().isoformat())["sells"] += 1
    return decision


def evaluate_exits(state: dict, ledger: list, radar_stocks: dict, quotes: dict[str, dict], prices: dict[str, float]) -> list[dict]:
    actions: list[dict] = []
    today = now_cn().date().isoformat()
    for code in list(state.get("positions", {}).keys()):
        pos = state["positions"].get(code)
        if not pos: continue
        mark_seen_date(pos, today)
        q = quotes.get(code) or {}; cur = q.get("price") or radar_stocks.get(code, {}).get("price") or pos.get("lastPrice")
        if not cur: continue
        cur = float(cur); prices[code] = cur; pos["lastPrice"] = cur; pos["lastPriceAt"] = iso()
        avg = float(pos.get("avgCost") or 0.0); ret = (cur / avg - 1) * 100 if avg else 0.0
        live = radar_stocks.get(code)
        pos["missingRadarCount"] = 0 if live else int(pos.get("missingRadarCount", 0)) + 1
        if pos.get("entryDate") >= today:
            continue
        reason = None; qty = int(pos["qty"])
        if ret <= -4.0:
            reason = f"保护性止损：持仓收益{ret:.2f}%触及-4%风险边界"
        elif live and float(live.get("mainFlowPct") or 0.0) <= -6.0 and ret <= 2.0:
            reason = f"资金失效：主力资金强度{float(live.get('mainFlowPct') or 0.0):.1f}%且持仓收益{ret:.2f}%"
        elif ret >= 12.0:
            reason = f"强制锁定利润：累计浮盈{ret:.2f}%超过12%"
        elif ret >= 8.0 and not pos.get("partialProfitTaken"):
            qty = max(100, (int(pos["qty"]) // 2 // 100) * 100); reason = f"分批止盈：累计浮盈{ret:.2f}%超过8%，先减半仓"
        elif int(pos.get("missingRadarCount", 0)) >= 6:
            reason = f"信号失效：连续{pos['missingRadarCount']}个滚动时点未进入提前候选"
        elif int(pos.get("missingRadarCount", 0)) >= 3 and (ret >= 1.5 or ret <= -2.5):
            reason = f"主线/个股动能退出：连续{pos['missingRadarCount']}个时点离开候选，当前收益{ret:.2f}%"
        elif len(pos.get("seenTradeDates", [])) >= 4 and ret >= 2.0:
            reason = f"时间止盈：已跨{len(pos.get('seenTradeDates', []))}个交易日且收益{ret:.2f}%"
        elif len(pos.get("seenTradeDates", [])) >= 6:
            reason = f"时间退出：已跨{len(pos.get('seenTradeDates', []))}个交易日，结束本轮信号"
        if reason:
            d = sell_position(state, ledger, pos, qty, cur, reason, prices)
            if d: actions.append(d)
    return actions


def evaluate_entries(state: dict, ledger: list, radar: dict, prices: dict[str, float]) -> list[dict]:
    dt = now_cn()
    if not can_open_new(dt): return []
    daily = get_daily_control(state, dt.date().isoformat())
    if int(daily.get("newBuys", 0)) >= MAX_NEW_BUYS_PER_DAY or len(state.get("positions", {})) >= MAX_POSITIONS: return []
    candidates = []
    for code, st in (radar.get("stocks") or {}).items():
        st = dict(st); st.setdefault("code", code)
        if code in state.get("positions", {}): continue
        score, reasons, rejects = score_candidate(st)
        ref, src, _ = candidate_reference_price(st)
        if ref is None: rejects.append(src)
        if rejects or score < MIN_BUY_SCORE: continue
        candidates.append((score, st, reasons, float(ref), src))
    candidates.sort(key=lambda x: x[0], reverse=True)
    actions: list[dict] = []
    for score, st, reasons, ref, src in candidates:
        if len(state["positions"]) >= MAX_POSITIONS or get_daily_control(state, dt.date().isoformat())["newBuys"] >= MAX_NEW_BUYS_PER_DAY: break
        d = buy_position(state, ledger, st, score, reasons, ref, src, prices)
        if d: actions.append(d); prices[st["code"]] = ref
    return actions


def max_drawdown_pct(nav_history: list[dict]) -> float:
    peak = None; mdd = 0.0
    for x in nav_history:
        nav = x.get("nav")
        if not nav: continue
        nav = float(nav); peak = nav if peak is None else max(peak, nav)
        if peak: mdd = min(mdd, (nav / peak - 1) * 100)
    return round(mdd, 2)


def daily_series(nav_history: list[dict]) -> list[dict]:
    by_date: dict[str, list[dict]] = {}
    for x in nav_history: by_date.setdefault(x.get("date", ""), []).append(x)
    out = []; prev_close = INITIAL_CAPITAL
    for date in sorted(k for k in by_date if k):
        rows = by_date[date]; close = float(rows[-1].get("nav") or prev_close)
        day_ret = (close / prev_close - 1) * 100 if prev_close else 0.0
        out.append({"date": date, "closeNav": round(close, 2), "dailyReturnPct": round(day_ret, 3), "cumulativeReturnPct": round((close / INITIAL_CAPITAL - 1) * 100, 3)})
        prev_close = close
    return out


def closed_sell_stats(ledger: list[dict]) -> dict:
    sells = [x for x in ledger if x.get("side") == "SELL" and x.get("realizedPnl") is not None]
    wins = [x for x in sells if float(x.get("realizedPnl") or 0) > 0]; losses = [x for x in sells if float(x.get("realizedPnl") or 0) < 0]
    avg_win = sum(float(x["realizedPnl"]) for x in wins) / len(wins) if wins else 0.0
    avg_loss = sum(float(x["realizedPnl"]) for x in losses) / len(losses) if losses else 0.0
    return {"sellDecisionCount": len(sells), "profitableSellCount": len(wins), "winRatePct": round(len(wins) / len(sells) * 100, 2) if sells else None, "avgWinPnl": round(avg_win, 2), "avgLossPnl": round(avg_loss, 2), "profitLossRatio": round(abs(avg_win / avg_loss), 2) if avg_loss else None}


def build_latest(state: dict, ledger: list, prices: dict[str, float], radar: dict) -> dict:
    nav, mv = portfolio_nav(state, prices)
    positions = []
    for code, p in state.get("positions", {}).items():
        cur = prices.get(code, p.get("lastPrice") or p.get("avgCost") or 0.0); qty = int(p.get("qty", 0)); avg = float(p.get("avgCost") or 0.0)
        value = qty * float(cur or 0); pnl = value - qty * avg
        positions.append({**p, "currentPrice": round(float(cur or 0), 4), "marketValue": round(value, 2), "floatingPnl": round(pnl, 2), "floatingReturnPct": round((float(cur) / avg - 1) * 100, 2) if avg and cur else None, "currentWeightPct": round(value / nav * 100, 2) if nav else 0.0, "tradingDaysObserved": len(p.get("seenTradeDates", [])), "currentActionZh": ("次日优先观察，今日按T+1不可卖" if p.get("entryDate") == now_cn().date().isoformat() else "继续滚动评估持有/减仓/卖出条件")})
    positions.sort(key=lambda x: x.get("currentWeightPct", 0), reverse=True)
    hist = state.get("navHistory", []); day = daily_series(hist); today = now_cn().date().isoformat(); today_rows = [x for x in hist if x.get("date") == today]
    today_ret = None
    if today_rows:
        start = float(today_rows[0].get("nav") or nav); today_ret = (nav / start - 1) * 100 if start else None
    summary = {"initialCapital": INITIAL_CAPITAL, "totalAssets": round(nav, 2), "cash": round(float(state.get("cash", 0.0)), 2), "marketValue": round(mv, 2), "positionPct": round(mv / nav * 100, 2) if nav else 0.0, "cashPct": round(float(state.get("cash", 0.0)) / nav * 100, 2) if nav else 0.0, "todayReturnPct": round(today_ret, 3) if today_ret is not None else None, "cumulativeReturnPct": round((nav / INITIAL_CAPITAL - 1) * 100, 3), "realizedPnl": round(float(state.get("realizedPnl", 0.0)), 2), "floatingPnl": round(sum(float(x.get("floatingPnl") or 0) for x in positions), 2), "maxDrawdownPct": max_drawdown_pct(hist), "positionCount": len(positions), **closed_sell_stats(ledger)}
    return {"schemaVersion": 1, "strategyVersion": STRATEGY_VERSION, "mode": "AI影子实盘", "simulated": True, "disclaimerZh": "这是按真实时点数据生成的模拟影子组合，不会向券商发送订单，也不代表收益保证。", "updatedAt": iso(), "radarCapturedAt": radar.get("capturedAt"), "radarStatus": radar.get("status"), "summary": summary, "positions": positions, "todayDecisions": [x for x in ledger if str(x.get("timestamp", "")).startswith(today)], "recentDecisions": ledger[-30:], "dailyPerformance": day[-90:], "navHistory": hist[-300:], "rulesZh": {"newEntry": "只从全天提前雷达候选中择优，优先潜在形成/确认中、价格未充分扩张、资金正向且追高风险低的股票。", "position": "单股最高15%，单板块最高25%，总仓位最高60%，最多5只；没有合格机会允许100%现金。", "exit": "遵守普通A股T+1；止损、信号失效、资金转负、分批止盈和时间退出共同决定卖出。", "audit": "每笔决策按当时时间、价格、仓位和理由永久记录，后续行情不得回改历史决策。"}}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    dt = now_cn()
    if not RADAR.exists():
        print(json.dumps({"state": "no-radar", "time": iso(dt)}, ensure_ascii=False)); return 0
    radar = read_json(RADAR, {}); radar_date = str(radar.get("date") or "")
    if radar_date != dt.date().isoformat():
        print(json.dumps({"state": "stale-radar", "radarDate": radar_date, "time": iso(dt)}, ensure_ascii=False)); return 0
    state = read_json(STATE_PATH, new_state()); ledger = read_json(LEDGER_PATH, [])
    if not isinstance(ledger, list): ledger = []
    codes = list(state.get("positions", {}).keys()) + list((radar.get("stocks") or {}).keys())
    quotes = fetch_tencent_quotes(codes); prices: dict[str, float] = {}
    for code in set(codes):
        q = quotes.get(code) or {}; st = (radar.get("stocks") or {}).get(code) or {}; p = q.get("price") or st.get("price")
        if p: prices[code] = float(p)
    actions: list[dict] = []
    actions += evaluate_exits(state, ledger, radar.get("stocks") or {}, quotes, prices)
    actions += evaluate_entries(state, ledger, radar, prices)
    nav, mv = portfolio_nav(state, prices)
    nav_point = {"timestamp": iso(dt), "date": dt.date().isoformat(), "time": dt.strftime("%H:%M:%S"), "nav": round(nav, 2), "cash": round(float(state.get("cash", 0.0)), 2), "marketValue": round(mv, 2), "positionCount": len(state.get("positions", {})), "cumulativeReturnPct": round((nav / INITIAL_CAPITAL - 1) * 100, 4), "radarCapturedAt": radar.get("capturedAt")}
    hist = state.setdefault("navHistory", []); hist.append(nav_point)
    if len(hist) > 6000: state["navHistory"] = hist[-6000:]
    get_daily_control(state, dt.date().isoformat())["lastDecisionAt"] = iso(dt)
    state["updatedAt"] = iso(dt); state["strategyVersion"] = STRATEGY_VERSION
    latest = build_latest(state, ledger, prices, radar)
    write_json(STATE_PATH, state); write_json(LEDGER_PATH, ledger); write_json(LATEST_PATH, latest)
    print(json.dumps({"state": "updated", "time": iso(dt), "session": trading_session(dt), "actions": len(actions), "buys": sum(1 for a in actions if a.get("side") == "BUY"), "sells": sum(1 for a in actions if a.get("side") == "SELL"), "positions": len(state.get("positions", {})), "nav": round(nav, 2), "cash": round(float(state.get("cash", 0.0)), 2)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
