#!/usr/bin/env python3
from __future__ import annotations

from datetime import time
import json

import run_ai_shadow_portfolio as base

STRATEGY_VERSION = "v2.0-dynamic-rebalance-point-in-time"
MAX_GROSS_WEIGHT = 1.00
MAX_SINGLE_WEIGHT = 0.15
MAX_SECTOR_WEIGHT = 0.25
MIN_BUY_SCORE = 64.0
MIN_HOLD_SCORE = 57.0
MIN_REBALANCE_WEIGHT = 0.018
MIN_REBALANCE_AMOUNT = 5000.0

LAST_TARGETS: list[dict] = []
LAST_ACTIONS: list[dict] = []
ORIGINAL_BUILD_LATEST = base.build_latest


def sellable_qty(pos: dict, today: str) -> int:
    daily = pos.get("dailyBuyQty") or {}
    if not daily and str(pos.get("entryDate") or "") >= today:
        return 0
    return max(0, int(pos.get("qty", 0)) - int(daily.get(today, 0) or 0))


def target_budget(rows: list[dict]) -> float:
    fresh = [x for x in rows if float(x.get("score") or 0) >= MIN_BUY_SCORE]
    if not fresh:
        return 0.0
    n = len(fresh)
    top = float(fresh[0]["score"])
    avg = sum(float(x["score"]) for x in fresh[: min(n, 8)]) / min(n, 8)
    if top >= 82 and avg >= 72 and n >= 6:
        return 1.0
    if top >= 78 and avg >= 69:
        return min(1.0, 0.45 + 0.07 * n)
    if top >= 72:
        return min(0.85, 0.30 + 0.06 * n)
    return min(0.60, 0.18 + 0.05 * n)


def target_rows(radar: dict, state: dict) -> list[dict]:
    existing = set((state.get("positions") or {}).keys())
    rows: list[dict] = []
    for code, raw in (radar.get("stocks") or {}).items():
        st = dict(raw or {})
        st["code"] = code
        score, reasons, rejects = base.score_candidate(st)
        margin_score = st.get("marginScore")
        etf_score = st.get("etfScore")
        if margin_score is not None:
            ms = float(margin_score)
            if ms >= 75:
                score += 2; reasons.append("两融结构强+2")
            elif ms < 35:
                score -= 2; reasons.append("两融结构弱-2")
        if etf_score is not None:
            es = float(etf_score)
            if es >= 70:
                score += 2; reasons.append("ETF一级资金强+2")
            elif es < 35:
                score -= 2; reasons.append("ETF一级资金弱-2")
        ref, source, _ = base.candidate_reference_price(st)
        held = code in existing
        fatal = any(("走势明显走弱" in x or "双源价格偏差" in x or "流动性" in x) for x in rejects)
        new_ok = ref is not None and score >= MIN_BUY_SCORE and not rejects
        hold_ok = held and ref is not None and score >= MIN_HOLD_SCORE and not fatal
        if not (new_ok or hold_ok):
            continue
        rows.append({
            "code": code,
            "name": st.get("name") or code,
            "sector": st.get("sector") or "未知",
            "score": round(float(score), 2),
            "referencePrice": float(ref),
            "priceSource": source,
            "reasonZh": "；".join(reasons),
            "held": held,
        })
    rows.sort(key=lambda x: float(x["score"]), reverse=True)
    budget = target_budget(rows)
    if budget <= 0:
        return []

    weights = {x["code"]: 0.0 for x in rows}
    sector_used: dict[str, float] = {}
    alpha = {x["code"]: max(1.0, float(x["score"]) - 55.0) for x in rows}
    remaining = budget
    active = list(rows)
    for _ in range(20):
        if remaining < 0.002 or not active:
            break
        denom = sum(alpha[x["code"]] for x in active)
        if denom <= 0:
            break
        progressed = 0.0
        next_active = []
        for x in active:
            code, sec = x["code"], x["sector"]
            share = remaining * alpha[code] / denom
            room_single = MAX_SINGLE_WEIGHT - weights[code]
            room_sector = MAX_SECTOR_WEIGHT - sector_used.get(sec, 0.0)
            add = max(0.0, min(share, room_single, room_sector))
            if add > 0:
                weights[code] += add
                sector_used[sec] = sector_used.get(sec, 0.0) + add
                progressed += add
            if weights[code] < MAX_SINGLE_WEIGHT - 0.002 and sector_used.get(sec, 0.0) < MAX_SECTOR_WEIGHT - 0.002:
                next_active.append(x)
        if progressed < 0.001:
            break
        remaining -= progressed
        active = next_active

    out = []
    for x in rows:
        w = weights[x["code"]]
        if w < 0.02:
            continue
        y = dict(x)
        y["targetWeight"] = round(w, 6)
        y["targetWeightPct"] = round(w * 100.0, 2)
        out.append(y)
    out.sort(key=lambda x: float(x["targetWeight"]), reverse=True)
    return out


def add_or_buy(state: dict, ledger: list, t: dict, qty: int, prices: dict[str, float], reason: str):
    qty = int(qty // 100) * 100
    if qty < 100:
        return None
    code = t["code"]
    ref = float(t["referencePrice"])
    px = base.exec_price(ref, "BUY")
    amount = round(px * qty, 2)
    fee = base.fees(amount, "BUY")
    cash = float(state.get("cash", 0.0))
    if amount + fee > cash:
        qty = int(max(0.0, cash - base.MIN_COMMISSION) / px / 100) * 100
        if qty < 100:
            return None
        amount = round(px * qty, 2)
        fee = base.fees(amount, "BUY")
    if amount + fee > cash:
        return None

    dt = base.now_cn(); today = dt.date().isoformat()
    pos = (state.get("positions") or {}).get(code)
    side_zh = "加仓" if pos else "买入"
    if pos:
        old_qty = int(pos.get("qty", 0))
        old_cost = float(pos.get("costAmount") or (float(pos.get("avgCost") or 0.0) * old_qty))
        new_qty = old_qty + qty
        new_cost = old_cost + amount + fee
        pos["qty"] = new_qty
        pos["costAmount"] = round(new_cost, 2)
        pos["avgCost"] = round(new_cost / new_qty, 4)
        pos["lastPrice"] = ref
        pos["lastPriceAt"] = base.iso(dt)
        pos["buyScore"] = t["score"]
        pos["buyReasonZh"] = t["reasonZh"]
    else:
        pos = {
            "code": code, "name": t["name"], "sector": t["sector"], "qty": qty,
            "avgCost": round((amount + fee) / qty, 4), "costAmount": round(amount + fee, 2),
            "entryPrice": px, "entryReferencePrice": round(ref, 4), "entryPriceSource": t["priceSource"],
            "entryTimestamp": base.iso(dt), "entryDate": today, "initialWeightTarget": t["targetWeight"],
            "lastPrice": ref, "lastPriceAt": base.iso(dt), "missingRadarCount": 0, "partialProfitTaken": False,
            "seenTradeDates": [today], "buyScore": t["score"], "buyReasonZh": t["reasonZh"],
            "invalidationZh": "目标仓位降为0、主线/资金恶化或保护性止损触发",
            "expectedHorizonZh": "动态持有；每轮行情重新计算目标仓位，不设固定持有天数",
            "dailyBuyQty": {},
        }
        state["positions"][code] = pos
    daily = pos.setdefault("dailyBuyQty", {})
    daily[today] = int(daily.get(today, 0) or 0) + qty
    state["cash"] = round(cash - amount - fee, 2)
    return base.append_decision(
        ledger, side="BUY", sideZh=side_zh, code=code, name=t["name"], sector=t["sector"], qty=qty,
        price=px, referencePrice=round(ref, 4), priceSource=t["priceSource"], amount=amount, fee=fee,
        targetWeightPct=t["targetWeightPct"], decisionScore=t["score"], reasonZh=reason + "；" + t["reasonZh"],
        invalidationZh=pos["invalidationZh"], expectedHorizonZh=pos["expectedHorizonZh"],
    )


def reduce_or_sell(state: dict, ledger: list, pos: dict, qty: int, ref: float, target_pct: float, reason: str):
    today = base.now_cn().date().isoformat()
    qty = min(int(qty), sellable_qty(pos, today))
    qty = int(qty // 100) * 100
    if qty <= 0:
        return None
    d = base.sell_position(state, ledger, pos, qty, float(ref), reason, {})
    if d is not None:
        d["sideZh"] = "卖出" if int(d.get("remainingQty") or 0) <= 0 else "减仓"
        d["targetWeightPct"] = round(float(target_pct), 2)
    return d


def dynamic_exits(state: dict, ledger: list, radar_stocks: dict, quotes: dict[str, dict], prices: dict[str, float]) -> list[dict]:
    actions = []
    today = base.now_cn().date().isoformat()
    for code in list((state.get("positions") or {}).keys()):
        pos = state["positions"].get(code)
        if not pos:
            continue
        cur = (quotes.get(code) or {}).get("price") or (radar_stocks.get(code) or {}).get("price") or pos.get("lastPrice")
        if not cur:
            continue
        cur = float(cur); prices[code] = cur
        pos["lastPrice"] = cur; pos["lastPriceAt"] = base.iso()
        live = radar_stocks.get(code)
        pos["missingRadarCount"] = 0 if live else int(pos.get("missingRadarCount", 0)) + 1
        seen = pos.setdefault("seenTradeDates", [])
        if today not in seen:
            seen.append(today)
        avg = float(pos.get("avgCost") or 0.0)
        ret = (cur / avg - 1.0) * 100.0 if avg else 0.0
        reason = None
        if ret <= -4.0:
            reason = f"保护性止损：持仓收益{ret:.2f}%触及-4%"
        elif live and float(live.get("mainFlowPct") or 0.0) <= -8.0 and ret <= 1.0:
            reason = f"资金快速失效：主力资金强度{float(live.get('mainFlowPct') or 0.0):.1f}%"
        elif int(pos.get("missingRadarCount", 0)) >= 6:
            reason = f"持续离开候选：连续{pos.get('missingRadarCount')}轮未进入雷达"
        if reason:
            d = reduce_or_sell(state, ledger, pos, int(pos.get("qty", 0)), cur, 0.0, reason)
            if d:
                actions.append(d)
    return actions


def dynamic_entries(state: dict, ledger: list, radar: dict, prices: dict[str, float]) -> list[dict]:
    global LAST_TARGETS, LAST_ACTIONS
    targets = target_rows(radar, state)
    LAST_TARGETS = targets
    actions: list[dict] = []
    target_map = {x["code"]: x for x in targets}
    nav, _ = base.portfolio_nav(state, prices)
    if nav <= 0:
        return []
    current_w = base.current_weights(state, prices)[0]

    # 先减仓/清仓，再把现金分配给更强的新机会。
    sell_list = []
    for code, pos in list((state.get("positions") or {}).items()):
        cur = prices.get(code) or float(pos.get("lastPrice") or 0.0)
        if not cur:
            continue
        target = target_map.get(code)
        tw = float((target or {}).get("targetWeight") or 0.0)
        cw = float(current_w.get(code, 0.0))
        delta = cw - tw
        if tw == 0 or delta >= MIN_REBALANCE_WEIGHT:
            sell_list.append((delta, code, pos, cur, tw))
    sell_list.sort(key=lambda x: x[0], reverse=True)
    for delta, code, pos, cur, tw in sell_list:
        nav_now, _ = base.portfolio_nav(state, prices)
        target_value = nav_now * tw
        current_value = int(pos.get("qty", 0)) * cur
        qty = int(max(0.0, current_value - target_value) / cur / 100) * 100
        if tw == 0:
            qty = int(pos.get("qty", 0))
        if qty * cur < MIN_REBALANCE_AMOUNT and tw > 0:
            continue
        reason = "动态再平衡：目标仓位降为0" if tw == 0 else f"动态再平衡：当前仓位高于目标约{delta*100:.1f}个百分点"
        d = reduce_or_sell(state, ledger, pos, qty, cur, tw * 100.0, reason)
        if d:
            actions.append(d)

    dt = base.now_cn()
    if not base.trading_session(dt) or dt.time() > time(14, 55):
        LAST_ACTIONS = actions
        return actions

    for t in targets:
        code = t["code"]
        ref = float(t["referencePrice"])
        prices.setdefault(code, ref)
        nav_now, _ = base.portfolio_nav(state, prices)
        cw = float(base.current_weights(state, prices)[0].get(code, 0.0))
        tw = float(t["targetWeight"])
        delta = tw - cw
        if delta < MIN_REBALANCE_WEIGHT:
            continue
        amount = delta * nav_now
        if amount < MIN_REBALANCE_AMOUNT:
            continue
        qty = int(amount / base.exec_price(ref, "BUY") / 100) * 100
        if qty < 100:
            continue
        reason = "动态再平衡：新候选进入目标组合" if code not in (state.get("positions") or {}) else f"动态再平衡：目标仓位提高约{delta*100:.1f}个百分点"
        d = add_or_buy(state, ledger, t, qty, prices, reason)
        if d:
            actions.append(d)
    LAST_ACTIONS = actions
    return actions


def dynamic_build_latest(state: dict, ledger: list, prices: dict[str, float], radar: dict) -> dict:
    out = ORIGINAL_BUILD_LATEST(state, ledger, prices, radar)
    out["schemaVersion"] = 2
    out["strategyVersion"] = STRATEGY_VERSION
    out["mode"] = "智能影子实盘"
    out["targetPortfolio"] = [
        {k: x[k] for k in ("code", "name", "sector", "score", "targetWeightPct", "referencePrice", "priceSource", "reasonZh") if k in x}
        for x in LAST_TARGETS
    ]
    out["targetGrossPct"] = round(sum(float(x.get("targetWeightPct") or 0.0) for x in LAST_TARGETS), 2)
    out["decisionCycle"] = {
        "frequencyZh": "每次盘中雷达刷新重新评分与再平衡",
        "actionsThisCycle": len(LAST_ACTIONS),
        "positionCountLimit": None,
        "grossLimitPct": 100,
        "singleStockLimitPct": 15,
        "sectorLimitPct": 25,
    }
    rules = out.setdefault("rulesZh", {})
    rules["newEntry"] = "每轮行情把现有持仓和全部实时新候选统一重新评分；满足条件即可新买，不限制股票只数或每日买入次数。"
    rules["position"] = "允许0%到100%动态总仓位，不强制满仓；单股最高15%、单板块最高25%，总仓位由实时机会质量决定。"
    rules["rebalance"] = "目标组合每轮重算；新机会可买入/加仓，旧持仓相对变弱可减仓/卖出，并设置约1.8个百分点缓冲减少噪声交易。"
    rules["exit"] = "普通A股遵守T+1；保护性止损、资金快速失效和持续离开候选可优先退出。"
    rules["audit"] = "上午已经发生的成交永久保留；v2动态再平衡只影响启用后的新决策，不回写历史。"
    return out


def main() -> int:
    base.STRATEGY_VERSION = STRATEGY_VERSION
    base.MAX_POSITIONS = 10**9
    base.MAX_GROSS_WEIGHT = MAX_GROSS_WEIGHT
    base.MAX_SINGLE_WEIGHT = MAX_SINGLE_WEIGHT
    base.MAX_SECTOR_WEIGHT = MAX_SECTOR_WEIGHT
    base.MAX_NEW_BUYS_PER_DAY = 10**9
    base.evaluate_exits = dynamic_exits
    base.evaluate_entries = dynamic_entries
    base.build_latest = dynamic_build_latest
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
