"""Eight-signal-batch T+1 execution layer.

Selection remains owned by selection_engine_v45.  This module only freezes the
accepted close-of-day ranking and executes it from the next live session.
"""
from __future__ import annotations

from datetime import time


VERSION = "v6.0-eight-batch-t1-limit-execution"
MAX_BATCHES = 8
BATCH_FRACTION = 1 / MAX_BATCHES
SINGLE_LIMIT = .0225
SECTOR_LIMIT = .30
LIMIT_DISCOUNT = .98
MIN_ORDER_AMOUNT = 10_000.
MAX_RETRY_SESSIONS = 3
FALLBACK_START = time(14, 45)
ENTRY_END = time(14, 55)


def book(state):
    return state.setdefault("batchExecutionV6", {
        "version": VERSION, "activatedAt": None, "nextSequence": 1,
        "batches": [], "pendingOrders": [], "pendingExits": [],
        "lastSignalDate": None,
    })


def accepted_targets(engine, state, radar):
    """Re-run the unchanged selector against the immutable closing radar.

    Live quote freshness is an execution constraint.  At post-close signal
    freeze time the auditable same-day radar snapshot is the evidence, even if
    its final capture preceded the publishing cycle by several minutes.
    """
    now = engine.base.now_cn(); today = now.date().isoformat()
    captured = engine.rules.stamp(radar.get("capturedAt"))
    if radar.get("date") != today or captured is None or captured.date() != now.date():
        return []
    enriched = radar
    original_radar = engine.CONTEXT.get("radar")
    original_quotes = engine.CONTEXT.get("quotes")
    close_quotes = {}
    for code, stock in (radar.get("stocks") or {}).items():
        price = engine.rules.finite(stock.get("price"), 0)
        change = engine.rules.finite(stock.get("changePct"))
        if not price:
            continue
        denominator = 1 + change / 100 if change is not None else 0
        previous = price / denominator if denominator > 0 else price
        close_quotes[code] = {
            "price": price, "prevClose": previous, "changePct": change,
            "amount": engine.rules.finite(stock.get("amount")),
            "quoteTime": engine.base.iso(now), "sourceCapturedAt": radar.get("capturedAt"),
        }
    rows = []
    try:
        engine.CONTEXT["radar"] = enriched
        engine.CONTEXT["quotes"] = close_quotes
        for code in (radar.get("stocks") or {}):
            if code not in close_quotes:
                continue
            row = engine.build_candidate(
                state, engine.signal_stock(state, code, enriched), enriched, close_quotes)
            row["dataAt"] = radar.get("capturedAt")
            engine.apply_ranked_entry_policy(row, code in (state.get("positions") or {}))
            if not row.get("rejections"):
                rows.append(row)
    finally:
        if original_radar is None:
            engine.CONTEXT.pop("radar", None)
        else:
            engine.CONTEXT["radar"] = original_radar
        if original_quotes is None:
            engine.CONTEXT.pop("quotes", None)
        else:
            engine.CONTEXT["quotes"] = original_quotes
    rows.sort(key=lambda x: (-float(x.get("rankingScore") or 0),
                             -float(x.get("score") or 0), str(x.get("code") or "")))
    return rows


def freeze_signal(engine, state, radar, prices, targets=None):
    now = engine.base.now_cn(); today = now.date().isoformat(); b = book(state)
    if now.time() < time(15) or radar.get("date") != today or b.get("lastSignalDate") == today:
        return None
    if targets is not None:
        rows = [dict(x) for x in targets
                if not x.get("rejections") and str(x.get("dataAt") or "").startswith(today)]
        rows.sort(key=lambda x: (-float(x.get("rankingScore") or 0),
                                 -float(x.get("score") or 0), str(x.get("code") or "")))
    else:
        rows = []
    # Stored signals can be stale when the intraday worker was interrupted.
    # The current final radar is authoritative for the T-close freeze.
    if not rows:
        rows = accepted_targets(engine, state, radar)
    if not rows:
        return None
    nav, _ = engine.base.portfolio_nav(state, prices)
    seq = int(b.get("nextSequence") or 1)
    batch_id = f"B{seq:04d}-{today}"
    batch = {"id": batch_id, "sequence": seq, "signalDate": today,
             "budget": round(nav * BATCH_FRACTION, 2), "spent": 0.,
             "status": "PENDING_ENTRY", "lots": {}, "candidateCount": len(rows)}
    b["batches"].append(batch)
    b["nextSequence"] = seq + 1; b["lastSignalDate"] = today
    b["pendingOrders"].extend({
        "batchId": batch_id, "signalDate": today, "code": x["code"],
        "name": x.get("name") or x["code"], "sector": x.get("sector") or "未知",
        "score": x.get("score"), "rankingScore": x.get("rankingScore"),
        "rank": i + 1, "signalClose": float(x["referencePrice"]),
        "limitPrice": round(float(x["referencePrice"]) * LIMIT_DISCOUNT, 4),
        "attemptSessions": [], "status": "WAIT_T_PLUS_ONE",
        "reasonZh": "T日收盘候选已冻结，等待T+1低吸限价或收盘兜底",
    } for i, x in enumerate(rows))

    active = [x for x in b["batches"] if x.get("status") not in ("CLOSED", "CANCELLED")]
    if len(active) > MAX_BATCHES:
        oldest = min(active, key=lambda x: int(x.get("sequence") or 0))
        oldest["status"] = "PENDING_FIFO_EXIT"
        for code, qty in (oldest.get("lots") or {}).items():
            if int(qty or 0) > 0:
                b["pendingExits"].append({"batchId": oldest["id"], "code": code,
                    "qty": int(qty), "signalDate": today, "reasonCode": "FIFO_BATCH_EXPIRY",
                    "reasonZh": "第9个有效信号批次形成，T+1开盘轮出最老批次"})
        if not any(int(x or 0) for x in (oldest.get("lots") or {}).values()):
            oldest["status"] = "CLOSED"
    if not b.get("activatedAt"): b["activatedAt"] = engine.base.iso(now)
    return batch


def quote_ok(engine, code):
    return engine.own_quote_ok(code) and float((engine.CONTEXT.get("quotes") or {}).get(code, {}).get("price") or 0) > 0


def _sell_pending(engine, state, ledger, prices):
    now = engine.base.now_cn(); today = now.date().isoformat(); b = book(state); actions = []
    pending = []
    for order in b.get("pendingExits") or []:
        if str(order.get("signalDate") or "") >= today:
            pending.append(order); continue
        pos = (state.get("positions") or {}).get(order["code"])
        if not pos:
            continue
        qty = min(int(order.get("qty") or pos.get("qty") or 0), int(pos.get("qty") or 0))
        ref = prices.get(order["code"]) or float(pos.get("lastPrice") or 0)
        if qty <= 0 or ref <= 0 or not quote_ok(engine, order["code"]):
            pending.append(order); continue
        row = engine.execution.reduce_or_sell(state, ledger, pos, qty, ref, 0., order["reasonZh"])
        if not row:
            pending.append(order); continue
        actions.append(row)
        filled = int(row.get("qty") or row.get("filledQty") or 0)
        for batch in b.get("batches") or []:
            lot = int((batch.get("lots") or {}).get(order["code"]) or 0)
            take = min(lot, filled)
            if take:
                batch["lots"][order["code"]] = lot - take; filled -= take
            if filled <= 0: break
        if row.get("partialFill"):
            order["qty"] = max(0, qty - int(row.get("filledQty") or 0)); pending.append(order)
    b["pendingExits"] = pending
    for batch in b.get("batches") or []:
        if batch.get("status") == "PENDING_FIFO_EXIT" and not any(int(x or 0) for x in (batch.get("lots") or {}).values()):
            batch["status"] = "CLOSED"
    return actions


def evaluate_exits(engine, original, state, ledger, radar_stocks, quotes, prices):
    # Protective stops, drawdown controls, T+1 and capacity remain authoritative.
    actions = original(state, ledger, radar_stocks, quotes, prices)
    # A protective exit may close a position before its FIFO batch matures.
    # Reconcile batch lots so a later expiry can never sell the same shares.
    positions = state.get("positions") or {}
    for batch in book(state).get("batches") or []:
        for code in list((batch.get("lots") or {}).keys()):
            if code not in positions:
                batch["lots"][code] = 0
    if not engine.base.trading_session(engine.base.now_cn()):
        return actions
    actions.extend(_sell_pending(engine, state, ledger, prices))
    return actions


def _market_limit_up(engine, code):
    m = engine.base.EXECUTION_MARKET.get(code) or {}
    p, upper = float(m.get("price") or 0), float(m.get("upperLimit") or 0)
    opened = float(m.get("open") or p)
    low = float(m.get("low") or p)
    # Only a sealed one-price limit-up is automatically deferred.  A stock
    # that traded below the limit remains subject to the ordinary fill model.
    return upper > 0 and min(p, opened, low) >= upper * .995


def evaluate_entries(engine, state, ledger, radar, prices):
    now = engine.base.now_cn(); today = now.date().isoformat(); b = book(state); actions = []
    if not engine.base.trading_session(now) or now.time() > ENTRY_END:
        return actions
    risk = engine.risk_control(state, prices)
    if not risk.get("allowNew"):
        return actions
    batches = {x["id"]: x for x in b.get("batches") or []}
    pending = []
    for order in b.get("pendingOrders") or []:
        batch = batches.get(order.get("batchId"))
        if not batch or batch.get("status") in ("CLOSED", "CANCELLED"):
            continue
        if order.get("status") == "FILLED":
            continue
        if str(order.get("signalDate") or "") >= today:
            pending.append(order); continue
        if today not in order.setdefault("attemptSessions", []):
            order["attemptSessions"].append(today)
        if len(order["attemptSessions"]) > MAX_RETRY_SESSIONS:
            order.update(status="CANCELLED", reasonZh="连续3个有效交易日仍无法买入，订单放弃")
            continue
        code = order["code"]
        if not quote_ok(engine, code):
            order.update(status="WAIT_FRESH_QUOTE", reasonZh="等待T+1有效主行情")
            pending.append(order); continue
        if _market_limit_up(engine, code):
            order.update(status="WAIT_LIMIT_UP_RELEASE", reasonZh="涨停不可成交，顺延至下一有效交易日")
            pending.append(order); continue
        quote = (engine.CONTEXT.get("quotes") or {}).get(code) or {}
        ref = float(quote.get("price") or 0)
        intraday_low = float(quote.get("low") or ref)
        triggered = intraday_low <= float(order["limitPrice"])
        fallback = now.time() >= FALLBACK_START
        if not triggered and not fallback:
            order.update(status="WAIT_LIMIT_PRICE", reasonZh=f"等待触及低吸限价{order['limitPrice']:.2f}")
            pending.append(order); continue
        execution_ref = min(ref, float(order["limitPrice"])) if triggered else ref
        nav, mv = engine.base.portfolio_nav(state, prices)
        sector_value = sum(int(p.get("qty") or 0) * prices.get(c, p.get("lastPrice", p.get("avgCost", 0)))
                           for c, p in (state.get("positions") or {}).items()
                           if p.get("sector") == order["sector"])
        current = (state.get("positions") or {}).get(code) or {}
        current_value = int(current.get("qty") or 0) * execution_ref
        rooms = [float(batch["budget"]) - float(batch.get("spent") or 0),
                 nav * SINGLE_LIMIT - current_value,
                 nav * SECTOR_LIMIT - sector_value,
                 nav * float(risk.get("cap") or 0) - mv,
                 float(state.get("cash") or 0)]
        amount = max(0., min(rooms))
        if amount < MIN_ORDER_AMOUNT:
            order.update(status="WAIT_BUDGET", reasonZh="批次、个股、板块或总仓位剩余额度不足1万元")
            pending.append(order); continue
        qty = int(amount / (execution_ref * 1.01) / 100) * 100
        target = {"code": code, "name": order["name"], "sector": order["sector"],
                  "score": order.get("score") or 0, "rankingScore": order.get("rankingScore") or 0,
                  "referencePrice": execution_ref, "priceSource": "T+1实时行情/日内最低价触发",
                  "reasonZh": "T日候选；T+1低吸限价成交" if triggered else "T日候选；T+1收盘窗口兜底成交",
                  "targetWeight": min(SINGLE_LIMIT, amount / nav),
                  "targetWeightPct": min(SINGLE_LIMIT, amount / nav) * 100}
        row = engine.execution.add_or_buy(state, ledger, target, qty, prices, target["reasonZh"])
        if not row:
            order.update(status="WAIT_CAPACITY_OR_LIMIT", reasonZh="实时成交容量或价格限制未通过")
            pending.append(order); continue
        filled = int(row.get("qty") or row.get("filledQty") or 0)
        cost = float(row.get("amount") or 0) + float(row.get("fee") or 0)
        batch["spent"] = round(float(batch.get("spent") or 0) + cost, 2)
        batch.setdefault("lots", {})[code] = int(batch.get("lots", {}).get(code) or 0) + filled
        batch["status"] = "ACTIVE"
        order.update(status="FILLED", filledAt=engine.base.iso(now), filledQty=filled,
                     executionMode="LIMIT_98" if triggered else "CLOSE_FALLBACK")
        actions.append(row)
        if row.get("partialFill"):
            order.update(status="PARTIAL_WAIT", reasonZh="部分成交，剩余数量继续受容量约束")
            pending.append(order)
    b["pendingOrders"] = pending
    return actions


def mark_limit_up_exits(engine, state):
    now = engine.base.now_cn(); today = now.date().isoformat(); b = book(state)
    if now.time() < time(15): return
    existing = {(x.get("code"), x.get("signalDate"), x.get("reasonCode")) for x in b.get("pendingExits") or []}
    for code, pos in (state.get("positions") or {}).items():
        if _market_limit_up(engine, code) and (code, today, "LIMIT_UP_PROFIT") not in existing:
            b["pendingExits"].append({"code": code, "qty": int(pos.get("qty") or 0),
                "signalDate": today, "reasonCode": "LIMIT_UP_PROFIT",
                "reasonZh": "T日收盘涨停，T+1开盘优先兑现"})


def report(state):
    b = book(state)
    return {"version": VERSION, "activatedAt": b.get("activatedAt"),
            "batchCount": len(b.get("batches") or []),
            "activeBatchCount": sum(x.get("status") not in ("CLOSED", "CANCELLED") for x in b.get("batches") or []),
            "pendingOrderCount": len(b.get("pendingOrders") or []),
            "pendingExitCount": len(b.get("pendingExits") or []),
            "lastSignalDate": b.get("lastSignalDate"),
            "pendingOrders": [{k: x.get(k) for k in ("batchId", "signalDate", "code", "name", "rank",
                                                        "limitPrice", "status", "reasonZh")}
                              for x in (b.get("pendingOrders") or [])[:30]],
            "pendingExits": [{k: x.get(k) for k in ("batchId", "signalDate", "code", "qty",
                                                       "reasonCode", "reasonZh")}
                             for x in (b.get("pendingExits") or [])[:30]],
            "rulesZh": "T日收盘冻结当天候选；T+1按T收盘98%低吸，未触及则收盘窗口兜底；8批FIFO轮动；涨停后次日开盘卖出。"}
