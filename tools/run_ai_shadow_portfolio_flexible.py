#!/usr/bin/env python3
"""Dynamic rolling allocator for the smart shadow portfolio.

Preserves the original v1 immutable ledger/state, but replaces one-shot entry
logic with a target-weight portfolio optimizer that runs on every radar refresh.
"""
from __future__ import annotations

from statistics import mean
import run_ai_shadow_portfolio as base

base.STRATEGY_VERSION = "v2.0-ai-shadow-dynamic-allocation"
base.MAX_POSITIONS = 10**9          # no holding-count limit
base.MAX_GROSS_WEIGHT = 1.00       # allow 100% gross exposure
base.MAX_NEW_BUYS_PER_DAY = 10**9  # no arbitrary daily buy-count cap

MAX_SINGLE = 0.15
MAX_SECTOR = 0.30
MIN_BUY = 64.0
MIN_HOLD = 54.0
MIN_GAP = 0.015
MIN_TRADE_RMB = 8_000.0

_TARGETS: dict[str, float] = {}
_META: dict[str, dict] = {}
_TARGET_GROSS = 0.0


def _daily(state: dict, date: str) -> dict:
    d = base.get_daily_control(state, date)
    d.setdefault("adds", 0)
    d.setdefault("reduces", 0)
    d.setdefault("blockedBuys", [])
    return d


def _reset_t1(pos: dict, today: str) -> None:
    if pos.get("todayBuyDate") != today:
        pos["todayBuyDate"] = today
        pos["todayBuyQty"] = 0


def _sellable(pos: dict, today: str) -> int:
    qty = int(pos.get("qty", 0))
    if str(pos.get("entryDate") or "") >= today:
        return 0
    _reset_t1(pos, today)
    return max(0, qty - int(pos.get("todayBuyQty", 0)))


def _gross_target(scores: list[float]) -> float:
    if not scores:
        return 0.0
    avg_top = mean(sorted(scores, reverse=True)[: min(8, len(scores))])
    gross = 0.25 + min(0.45, 0.055 * len(scores))
    gross += max(0.0, min(0.30, (avg_top - MIN_BUY) * 0.02))
    if avg_top < 68:
        gross = min(gross, 0.55)
    return min(1.0, max(0.0, gross))


def _allocate(items: list[dict], gross: float) -> dict[str, float]:
    if not items or gross <= 0:
        return {}
    w = {x["code"]: 0.0 for x in items}
    sec: dict[str, float] = {}
    active = {x["code"] for x in items}
    remaining = gross
    for _ in range(30):
        rows = [x for x in items if x["code"] in active]
        if not rows or remaining <= 1e-6:
            break
        total = sum(max(1.0, x["strength"]) for x in rows)
        added = 0.0
        saturated = set()
        for x in rows:
            code, sector = x["code"], x["sector"]
            want = remaining * max(1.0, x["strength"]) / total
            stock_room = MAX_SINGLE - w[code]
            sector_room = MAX_SECTOR - sec.get(sector, 0.0)
            add = max(0.0, min(want, stock_room, sector_room))
            w[code] += add
            sec[sector] = sec.get(sector, 0.0) + add
            added += add
            if stock_room - add <= 1e-6 or sector_room - add <= 1e-6:
                saturated.add(code)
        remaining -= added
        active -= saturated
        if added <= 1e-6:
            break
    return {k: round(v, 6) for k, v in w.items() if v >= 0.005}


def _observe(state: dict, radar_stocks: dict, quotes: dict, prices: dict[str, float]) -> None:
    today = base.now_cn().date().isoformat()
    for code, pos in list(state.get("positions", {}).items()):
        _reset_t1(pos, today)
        base.mark_seen_date(pos, today)
        if code in radar_stocks:
            pos["missingRadarCount"] = 0
        else:
            pos["missingRadarCount"] = int(pos.get("missingRadarCount", 0)) + 1
        q = quotes.get(code) or {}
        cur = q.get("price") or (radar_stocks.get(code) or {}).get("price") or pos.get("lastPrice")
        if cur:
            prices[code] = float(cur)
            pos["lastPrice"] = float(cur)
            pos["lastPriceAt"] = base.iso()


def _hard_exit(pos: dict, live: dict | None, cur: float | None) -> tuple[str | None, float | None]:
    if not cur:
        return None, None
    avg = float(pos.get("avgCost") or 0)
    ret = (cur / avg - 1) * 100 if avg else 0.0
    if ret <= -4:
        return f"保护性止损：持仓收益{ret:.2f}%触及-4%风险边界", 0.0
    if live and float(live.get("mainFlowPct") or 0) <= -6 and ret <= 2:
        return f"资金失效：主力资金强度{float(live.get('mainFlowPct') or 0):.1f}%且收益{ret:.2f}%", 0.0
    if ret >= 12:
        return f"强制锁定利润：累计浮盈{ret:.2f}%超过12%", 0.0
    if ret >= 8 and not pos.get("partialProfitTaken"):
        return f"分批止盈：累计浮盈{ret:.2f}%超过8%，目标减半", 0.5
    miss = int(pos.get("missingRadarCount", 0))
    if miss >= 6:
        return f"信号失效：连续{miss}个滚动时点未进入候选", 0.0
    if miss >= 3 and (ret >= 1.5 or ret <= -2.5):
        return f"动能退出：连续{miss}个时点离开候选，当前收益{ret:.2f}%", 0.0
    if len(pos.get("seenTradeDates", [])) >= 4 and ret >= 2:
        return f"时间止盈：跨{len(pos.get('seenTradeDates', []))}个交易日且收益{ret:.2f}%", 0.0
    if len(pos.get("seenTradeDates", [])) >= 6:
        return f"时间退出：已跨{len(pos.get('seenTradeDates', []))}个交易日", 0.0
    return None, None


def _score_targets(state: dict, radar: dict, prices: dict[str, float]):
    radar_stocks = radar.get("stocks") or {}
    held = state.get("positions", {})
    today = base.now_cn().date().isoformat()
    blocked = set(_daily(state, today).get("blockedBuys") or [])
    items, meta = [], {}
    for code, raw in radar_stocks.items():
        st = dict(raw)
        st.setdefault("code", code)
        score, reasons, rejects = base.score_candidate(st)
        entry_ok = not rejects and score >= MIN_BUY and code not in blocked
        hold_ok = code in held and score >= MIN_HOLD
        m = {
            "code": code, "name": st.get("name") or code,
            "sector": st.get("sector") or "未知", "score": score,
            "reasons": reasons, "rejects": rejects,
            "entryEligible": entry_ok, "holdEligible": hold_ok, "stock": st,
        }
        meta[code] = m
        if entry_ok or hold_ok:
            m["strength"] = max(1.0, score - 52) * (1.0 if entry_ok else 0.72)
            items.append(m)

    current_w = base.current_weights(state, prices)[0]
    grace = {}
    for code, pos in held.items():
        if code not in radar_stocks and int(pos.get("missingRadarCount", 0)) < 2:
            grace[code] = current_w.get(code, 0.0)
            meta[code] = {
                "code": code, "name": pos.get("name") or code,
                "sector": pos.get("sector") or "未知", "score": None,
                "reasons": ["暂离雷达，保留一个滚动周期观察"],
                "rejects": [], "entryEligible": False, "holdEligible": True,
            }

    fresh_scores = [float(x["score"]) for x in items if x["entryEligible"]]
    gross = _gross_target(fresh_scores)
    if not fresh_scores and items:
        gross = min(0.35, sum(current_w.get(x["code"], 0.0) for x in items))
    targets = _allocate(items, gross)

    room = max(0.0, 1.0 - sum(targets.values()))
    for code, w in sorted(grace.items(), key=lambda kv: kv[1], reverse=True):
        keep = min(w, room)
        if keep >= 0.005:
            targets[code] = keep
            room -= keep
    return targets, meta


def _append(ledger: list, **kw):
    item = {
        "decisionId": f"{base.now_cn().strftime('%Y%m%d-%H%M%S')}-{len(ledger)+1:05d}",
        "timestamp": base.iso(),
        "strategyVersion": base.STRATEGY_VERSION,
        "mode": "AI影子实盘", "simulated": True, **kw,
    }
    ledger.append(item)
    return item


def _sell_down(state, ledger, code, target, ref, reason, prices):
    pos = state.get("positions", {}).get(code)
    if not pos:
        return None
    today = base.now_cn().date().isoformat()
    sellable = _sellable(pos, today)
    if sellable < 100:
        return None
    nav, _ = base.portfolio_nav(state, prices)
    cw = base.current_weights(state, prices)[0].get(code, 0.0)
    if target > 0 and cw - target < MIN_GAP:
        return None
    target_qty = int((nav * max(0.0, target)) / max(ref, .01) / 100) * 100
    qty = min(sellable, max(0, int(pos.get("qty", 0)) - target_qty))
    qty = qty // 100 * 100
    if qty < 100:
        return None
    px = base.exec_price(ref, "SELL")
    amount = round(px * qty, 2)
    fee = base.fees(amount, "SELL")
    avg = float(pos.get("avgCost") or 0)
    realized = round(amount - fee - avg * qty, 2)
    state["cash"] = round(float(state.get("cash", 0)) + amount - fee, 2)
    state["realizedPnl"] = round(float(state.get("realizedPnl", 0)) + realized, 2)
    remain = int(pos["qty"]) - qty
    d = _append(
        ledger, side="SELL",
        sideZh="卖出" if target <= .001 and remain <= 0 else "减仓",
        actionType="EXIT" if target <= .001 and remain <= 0 else "REDUCE",
        code=code, name=pos.get("name") or code, sector=pos.get("sector") or "未知",
        qty=qty, price=px, referencePrice=round(ref, 4),
        priceSource="腾讯实时行情/雷达行情", amount=amount, fee=fee,
        realizedPnl=realized, realizedReturnPct=round((px / avg - 1) * 100, 2) if avg else None,
        targetWeightPct=round(target * 100, 2), beforeWeightPct=round(cw * 100, 2),
        reasonZh=reason, remainingQty=remain,
    )
    if remain <= 0:
        state["positions"].pop(code, None)
    else:
        pos["qty"] = remain
        pos["costAmount"] = round(avg * remain, 2)
        pos["latestTargetWeight"] = round(target, 6)
        if "止盈" in reason:
            pos["partialProfitTaken"] = True
    _daily(state, today)["sells"] += 1
    _daily(state, today)["reduces"] += 1
    return d


def _buy_or_add(state, ledger, code, m, target, ref, src, prices):
    nav, _ = base.portfolio_nav(state, prices)
    cw = base.current_weights(state, prices)[0].get(code, 0.0)
    gap = target - cw
    if gap < MIN_GAP or nav * gap < MIN_TRADE_RMB:
        return None
    px = base.exec_price(ref, "BUY")
    budget = min(float(state.get("cash", 0)) * .995, nav * gap)
    qty = int(budget / px / 100) * 100
    if qty < 100:
        return None
    amount = round(px * qty, 2)
    fee = base.fees(amount, "BUY")
    if amount + fee > float(state.get("cash", 0)):
        return None
    today = base.now_cn().date().isoformat()
    state["cash"] = round(float(state.get("cash", 0)) - amount - fee, 2)
    pos = state.setdefault("positions", {}).get(code)
    if pos:
        _reset_t1(pos, today)
        old_qty = int(pos["qty"])
        old_cost = float(pos.get("costAmount") or float(pos.get("avgCost") or 0) * old_qty)
        new_qty = old_qty + qty
        new_cost = old_cost + amount + fee
        pos.update({
            "qty": new_qty, "costAmount": round(new_cost, 2),
            "avgCost": round(new_cost / new_qty, 4),
            "lastPrice": ref, "lastPriceAt": base.iso(),
            "todayBuyDate": today, "todayBuyQty": int(pos.get("todayBuyQty", 0)) + qty,
            "buyScore": m["score"], "buyReasonZh": "；".join(m["reasons"]),
            "latestTargetWeight": round(target, 6),
        })
        side_zh, action = "加仓", "ADD"
        _daily(state, today)["adds"] += 1
    else:
        st = m["stock"]
        pos = {
            "code": code, "name": st.get("name") or code, "sector": st.get("sector") or "未知",
            "qty": qty, "avgCost": round((amount + fee) / qty, 4), "costAmount": round(amount + fee, 2),
            "entryPrice": px, "entryReferencePrice": round(ref, 4), "entryPriceSource": src,
            "entryTimestamp": base.iso(), "entryDate": today,
            "initialWeightTarget": round(target, 6), "latestTargetWeight": round(target, 6),
            "lastPrice": ref, "lastPriceAt": base.iso(), "missingRadarCount": 0,
            "partialProfitTaken": False, "seenTradeDates": [today],
            "todayBuyDate": today, "todayBuyQty": qty,
            "buyScore": m["score"], "buyReasonZh": "；".join(m["reasons"]),
            "invalidationZh": "实时目标权重降至0、主线/资金显著失效，或触发保护性止损",
            "expectedHorizonZh": "每轮行情重新评估，不预设固定持有天数",
        }
        state["positions"][code] = pos
        side_zh, action = "买入", "OPEN"
        _daily(state, today)["newBuys"] += 1
    return _append(
        ledger, side="BUY", sideZh=side_zh, actionType=action,
        code=code, name=pos.get("name") or code, sector=pos.get("sector") or "未知",
        qty=qty, price=px, referencePrice=round(ref, 4), priceSource=src,
        amount=amount, fee=fee, targetWeightPct=round(target * 100, 2),
        beforeWeightPct=round(cw * 100, 2), decisionScore=m["score"],
        reasonZh=f"动态组合再平衡：目标{target*100:.1f}%；" + "；".join(m["reasons"]),
        expectedHorizonZh="每个滚动时点重新计算目标权重",
    )


def evaluate_exits_dynamic(state, ledger, radar_stocks, quotes, prices):
    global _TARGETS, _META, _TARGET_GROSS
    _observe(state, radar_stocks, quotes, prices)
    today = base.now_cn().date().isoformat()
    actions = []

    for code in list(state.get("positions", {})):
        pos = state["positions"].get(code)
        if not pos:
            continue
        cur = prices.get(code) or pos.get("lastPrice")
        reason, cap = _hard_exit(pos, radar_stocks.get(code), float(cur) if cur else None)
        if reason is None or cap is None:
            continue
        cw = base.current_weights(state, prices)[0].get(code, 0.0)
        target = 0.0 if cap == 0 else cw * cap
        d = _sell_down(state, ledger, code, target, float(cur), reason, prices)
        if d:
            actions.append(d)
            if cap == 0:
                _daily(state, today)["blockedBuys"].append(code)

    radar = base.read_json(base.RADAR, {})
    _TARGETS, _META = _score_targets(state, radar, prices)
    for code in set(_daily(state, today).get("blockedBuys") or []):
        _TARGETS.pop(code, None)
    _TARGET_GROSS = sum(_TARGETS.values())

    current = base.current_weights(state, prices)[0]
    for code, cw in sorted(current.items(), key=lambda kv: kv[1] - _TARGETS.get(kv[0], 0), reverse=True):
        tw = _TARGETS.get(code, 0.0)
        if tw > 0 and cw - tw < MIN_GAP:
            continue
        pos = state.get("positions", {}).get(code)
        ref = prices.get(code) or (pos or {}).get("lastPrice")
        if not pos or not ref:
            continue
        score = (_META.get(code) or {}).get("score")
        why = f"动态组合再平衡：当前{cw*100:.1f}% → 目标{tw*100:.1f}%"
        if score is not None:
            why += f"，实时评分{float(score):.1f}"
        else:
            why += "，当前未进入有效目标集合"
        d = _sell_down(state, ledger, code, tw, float(ref), why, prices)
        if d:
            actions.append(d)
    return actions


def evaluate_entries_dynamic(state, ledger, radar, prices):
    global _TARGETS, _META
    if not base.can_open_new(base.now_cn()):
        return []
    current = base.current_weights(state, prices)[0]
    rows = []
    for code, tw in _TARGETS.items():
        m = _META.get(code) or {}
        gap = tw - current.get(code, 0.0)
        if gap >= MIN_GAP and m.get("entryEligible"):
            rows.append((gap, float(m.get("score") or 0), code, tw, m))
    rows.sort(reverse=True)
    actions = []
    for _, _, code, tw, m in rows:
        ref, src, _ = base.candidate_reference_price(m["stock"])
        if not ref:
            continue
        d = _buy_or_add(state, ledger, code, m, tw, float(ref), src, prices)
        if d:
            actions.append(d)
            prices[code] = float(ref)
    return actions


_original_build_latest = base.build_latest


def build_latest_dynamic(state, ledger, prices, radar):
    out = _original_build_latest(state, ledger, prices, radar)
    current, _, gross_now = base.current_weights(state, prices)
    members = []
    for code in set(_TARGETS) | set(current):
        m = _META.get(code) or {}
        tw, cw = float(_TARGETS.get(code, 0)), float(current.get(code, 0))
        gap = tw - cw
        action = "持有"
        if gap >= MIN_GAP:
            action = "加仓" if code in state.get("positions", {}) else "买入"
        elif gap <= -MIN_GAP:
            action = "卖出" if tw <= .001 else "减仓"
        members.append({
            "code": code,
            "name": m.get("name") or state.get("positions", {}).get(code, {}).get("name") or code,
            "sector": m.get("sector") or state.get("positions", {}).get(code, {}).get("sector") or "未知",
            "score": m.get("score"), "targetWeightPct": round(tw * 100, 2),
            "currentWeightPct": round(cw * 100, 2), "gapPct": round(gap * 100, 2),
            "actionZh": action, "entryEligible": bool(m.get("entryEligible")),
            "referencePrice": prices.get(code), "reasonZh": "；".join(m.get("reasons") or m.get("rejects") or []),
        })
    members.sort(key=lambda x: (x["targetWeightPct"], x.get("score") or -999), reverse=True)

    out["strategyVersion"] = base.STRATEGY_VERSION
    out["allocatorMode"] = "动态目标组合"
    out["referenceCapital"] = base.INITIAL_CAPITAL
    out["targetPortfolio"] = {
        "updatedAt": base.iso(),
        "rebalanceFrequencyZh": "每次盘中雷达刷新重新计算；当前生产频率约5分钟",
        "grossTargetPct": round(_TARGET_GROSS * 100, 2),
        "targetCashPct": round((1 - _TARGET_GROSS) * 100, 2),
        "currentGrossPct": round(gross_now * 100, 2),
        "holdingCountLimit": None, "singleStockCapPct": 15.0, "sectorCapPct": 30.0,
        "members": members,
    }
    out["rulesZh"] = {
        "newEntry": "每次盘中雷达刷新都重新扫描新候选与现有持仓；满足实时评分、流动性、价格和追高风险条件即可新买或加仓。",
        "position": "持仓股票数量不设硬上限；总仓位在0%-100%之间动态变化，允许满仓；单股最高15%、单板块最高30%。",
        "rebalance": "现有持仓与新候选统一按实时目标权重排序；目标上升可加仓，下降则减仓，降至0则退出；小于1.5个百分点的偏差不频繁交易。",
        "exit": "普通A股严格T+1；保护性止损、资金失效、信号失效、止盈和动态目标权重共同决定卖出。",
        "capital": "后台100万元参考账户用于保持历史成交不可回写；App可设置任意模拟资金额度，并按同一实时目标权重即时换算目标金额和股数。",
        "audit": "历史v1成交保持不变；v2开始的买入、加仓、减仓和卖出全部按真实时点永久记录。",
    }
    out["disclaimerZh"] = "这是按真实时点数据生成的模拟影子组合，不连接券商；允许满仓不等于强制满仓。"

    by_code = {x["code"]: x for x in members}
    for p in out.get("positions", []):
        x = by_code.get(p.get("code"))
        if x:
            p["targetWeightPct"] = x["targetWeightPct"]
            p["weightGapPct"] = x["gapPct"]
            p["currentActionZh"] = x["actionZh"]
            p["dynamicScore"] = x.get("score")
    return out


base.evaluate_exits = evaluate_exits_dynamic
base.evaluate_entries = evaluate_entries_dynamic
base.build_latest = build_latest_dynamic

if __name__ == "__main__":
    raise SystemExit(base.main())
