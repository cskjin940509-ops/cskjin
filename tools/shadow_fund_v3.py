#!/usr/bin/env python3
"""Fund-accounting and realistic simulated-execution helpers.

The functions in this module are deliberately deterministic and dependency-free so
they can be exercised in CI without a market-data connection.  They do not place
orders.  They only constrain the quantities and prices recorded by the shadow book.
"""
from __future__ import annotations

import math
import statistics
from datetime import date, datetime


SCHEMA_VERSION = 3
BASE_UNIT_NAV = 1.0
MIN_RISK_SAMPLE_DAYS = 20
ORDER_PARTICIPATION_LIMIT = 0.008
DAY_PARTICIPATION_LIMIT = 0.015
ADV20_PARTICIPATION_LIMIT = 0.02
BASE_SPREAD_BPS = 3.0
IMPACT_COEFFICIENT_BPS = 80.0
MAX_IMPACT_BPS = 40.0


def finite(value, default=None):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip().replace("Z", "+00:00")
    if raw.isdigit() and len(raw) == 14:
        try:
            return datetime.strptime(raw, "%Y%m%d%H%M%S")
        except ValueError:
            return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _sorted_raw_history(state: dict) -> list[dict]:
    rows = list(state.get("legacyNavHistory") or []) + list(state.get("navHistory") or [])
    by_key: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get("timestamp") or f"{row.get('date')}T{row.get('time')}")
        if key and finite(row.get("nav")) is not None:
            by_key[key] = dict(row)
    return [by_key[k] for k in sorted(by_key)]


def _capital_event_rows(state: dict) -> list[dict]:
    rows = []
    for event in state.get("capitalEvents") or []:
        if not isinstance(event, dict):
            continue
        contribution = finite(event.get("cashContribution"), 0.0) or 0.0
        if abs(contribution) < 0.005:
            continue
        rows.append(event)
    rows.sort(key=lambda x: str(x.get("timestamp") or ""))
    return rows


def _nav_before_event(history: list[dict], event: dict, fallback: float) -> float:
    event_ts = str(event.get("timestamp") or "")
    before = [x for x in history if str(x.get("timestamp") or "") < event_ts]
    if before:
        return finite(before[-1].get("nav"), fallback) or fallback
    after = [x for x in history if str(x.get("timestamp") or "") >= event_ts]
    contribution = finite(event.get("cashContribution"), 0.0) or 0.0
    if after:
        candidate = (finite(after[0].get("nav"), fallback + contribution) or 0.0) - contribution
        if candidate > 0:
            return candidate
    return fallback


def ensure_fund_accounting(state: dict, current_assets: float | None = None) -> dict:
    """Create or repair a unit-NAV ledger without changing cash or positions.

    Cash contributions issue units at the pre-contribution unit NAV.  Therefore a
    capital-capacity change cannot dilute or reset the strategy return series.
    """
    history = _sorted_raw_history(state)
    events = _capital_event_rows(state)
    first_capital = None
    if events:
        first_capital = finite(events[0].get("fromCapital"))
    if not first_capital or first_capital <= 0:
        first_capital = finite((state.get("fundAccounting") or {}).get("inceptionCapital"))
    if not first_capital or first_capital <= 0:
        first_capital = finite(state.get("initialCapital"), 1.0) or 1.0

    units = first_capital / BASE_UNIT_NAV
    unit_events = [{
        "type": "INCEPTION",
        "timestamp": state.get("createdAt"),
        "cashFlow": round(first_capital, 2),
        "unitNav": BASE_UNIT_NAV,
        "unitsIssued": round(units, 8),
        "unitsAfter": round(units, 8),
    }]
    fallback_assets = first_capital
    for event in events:
        contribution = finite(event.get("cashContribution"), 0.0) or 0.0
        pre_assets = finite(event.get("preContributionAssets"))
        if pre_assets is None or pre_assets <= 0:
            pre_assets = _nav_before_event(history, event, fallback_assets)
        pre_unit_nav = pre_assets / units if units > 0 else BASE_UNIT_NAV
        issued = contribution / pre_unit_nav if pre_unit_nav > 0 else 0.0
        units += issued
        fallback_assets = pre_assets + contribution
        event["preContributionAssets"] = round(pre_assets, 2)
        event["preContributionUnitNav"] = round(pre_unit_nav, 8)
        event["unitsIssued"] = round(issued, 8)
        event["unitsAfter"] = round(units, 8)
        event["unitNavUnchanged"] = True
        unit_events.append({
            "type": "SUBSCRIPTION" if contribution > 0 else "REDEMPTION",
            "timestamp": event.get("timestamp"),
            "cashFlow": round(contribution, 2),
            "preCashFlowAssets": round(pre_assets, 2),
            "unitNav": round(pre_unit_nav, 8),
            "unitsIssued": round(issued, 8),
            "unitsAfter": round(units, 8),
            "capitalEventId": event.get("eventId"),
        })

    if current_assets is None:
        current_assets = finite(history[-1].get("nav")) if history else None
    if current_assets is None:
        current_assets = finite(state.get("cash"), 0.0) or 0.0
    unit_nav = current_assets / units if units > 0 else BASE_UNIT_NAV
    accounting = {
        "schemaVersion": SCHEMA_VERSION,
        "method": "UNIT_NAV_SUBSCRIPTION_REDEMPTION",
        "inceptionCapital": round(first_capital, 2),
        "inceptionUnitNav": BASE_UNIT_NAV,
        "fundUnits": round(units, 8),
        "unitNav": round(unit_nav, 8),
        "cumulativeNav": round(unit_nav / BASE_UNIT_NAV, 8),
        "currentAssets": round(current_assets, 2),
        "unitEvents": unit_events,
        "noteZh": "增资按增资前单位净值申购新增份额，单位净值和历史收益不重置。",
    }
    state["fundAccounting"] = accounting
    state["schemaVersion"] = max(int(state.get("schemaVersion") or 1), SCHEMA_VERSION)
    return accounting


def combined_unit_history(state: dict, current_assets: float | None = None) -> list[dict]:
    accounting = ensure_fund_accounting(state, current_assets)
    unit_events = accounting.get("unitEvents") or []
    inception_units = finite(unit_events[0].get("unitsAfter"), 1.0) or 1.0
    subscriptions = [x for x in unit_events[1:] if x.get("timestamp")]
    rows = []
    for raw in _sorted_raw_history(state):
        timestamp = str(raw.get("timestamp") or "")
        units = inception_units
        for event in subscriptions:
            if str(event.get("timestamp")) <= timestamp:
                units = finite(event.get("unitsAfter"), units) or units
        nav = finite(raw.get("nav"), 0.0) or 0.0
        unit_nav = nav / units if units > 0 else BASE_UNIT_NAV
        row = dict(raw)
        row["unitNav"] = round(unit_nav, 8)
        row["cumulativeNav"] = round(unit_nav / BASE_UNIT_NAV, 8)
        row["cumulativeReturnPct"] = round((unit_nav / BASE_UNIT_NAV - 1.0) * 100.0, 4)
        row["fundUnits"] = round(units, 8)
        rows.append(row)
    return rows


def business_days_between(start: str, end: str) -> int:
    try:
        a, b = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError:
        return 999
    if b <= a:
        return 0
    count = 0
    cursor = a
    while cursor < b:
        cursor = date.fromordinal(cursor.toordinal() + 1)
        if cursor.weekday() < 5:
            count += 1
    return count


def daily_unit_series(history: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for row in history:
        day = str(row.get("date") or "")
        if day:
            grouped.setdefault(day, []).append(row)
    result = []
    previous_day = None
    previous_close = BASE_UNIT_NAV
    for day in sorted(grouped):
        rows = sorted(grouped[day], key=lambda x: str(x.get("timestamp") or x.get("time") or ""))
        close = finite(rows[-1].get("unitNav"), previous_close) or previous_close
        period_return = (close / previous_close - 1.0) * 100.0 if previous_close else None
        distance = business_days_between(previous_day, day) if previous_day else 1
        complete = previous_day is None or distance <= 1
        result.append({
            "date": day,
            "closeUnitNav": round(close, 6),
            "closeCumulativeNav": round(close / BASE_UNIT_NAV, 6),
            "cumulativeReturnPct": round((close / BASE_UNIT_NAV - 1.0) * 100.0, 4),
            "dailyReturnPct": round(period_return, 4) if complete and period_return is not None else None,
            "periodReturnPct": round(period_return, 4) if period_return is not None else None,
            "observationGapBusinessDays": max(0, distance - 1),
            "coverageStatus": "COMPLETE" if complete else "MISSING_BACKEND_CYCLES",
            "pointCount": len(rows),
        })
        previous_day, previous_close = day, close
    return result


def max_drawdown(values: list[float], base: float = BASE_UNIT_NAV) -> float:
    peak = base
    worst = 0.0
    for value in values:
        if value <= 0:
            continue
        peak = max(peak, value)
        worst = min(worst, value / peak - 1.0)
    return round(worst * 100.0, 4)


def _period_series(daily: list[dict], period: str) -> list[dict]:
    grouped: dict[str, dict] = {}
    for row in daily:
        d = date.fromisoformat(row["date"])
        if period == "week":
            year, week, _ = d.isocalendar()
            key = f"{year}-W{week:02d}"
        else:
            key = f"{d.year}-{d.month:02d}"
        grouped[key] = row
    out = []
    previous = BASE_UNIT_NAV
    for key in sorted(grouped):
        close = finite(grouped[key].get("closeUnitNav"), previous) or previous
        out.append({
            "period": key,
            "closeUnitNav": round(close, 6),
            "returnPct": round((close / previous - 1.0) * 100.0, 4) if previous else None,
        })
        previous = close
    return out


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator and math.isfinite(denominator) else None


def risk_metrics(daily: list[dict]) -> dict:
    returns = [finite(x.get("dailyReturnPct")) / 100.0 for x in daily if finite(x.get("dailyReturnPct")) is not None]
    close_values = [finite(x.get("closeUnitNav")) for x in daily if finite(x.get("closeUnitNav")) is not None]
    enough = len(returns) >= MIN_RISK_SAMPLE_DAYS
    annualized_return = annualized_volatility = sharpe = sortino = calmar = None
    if enough and close_values:
        years = len(returns) / 252.0
        annualized_return = close_values[-1] ** (1.0 / years) - 1.0 if years > 0 else None
        annualized_volatility = statistics.stdev(returns) * math.sqrt(252.0) if len(returns) >= 2 else None
        sharpe = _safe_ratio(annualized_return or 0.0, annualized_volatility or 0.0)
        downside = [min(0.0, x) for x in returns]
        downside_dev = math.sqrt(sum(x * x for x in downside) / len(downside)) * math.sqrt(252.0)
        sortino = _safe_ratio(annualized_return or 0.0, downside_dev)
        mdd = abs(max_drawdown([x for x in close_values if x is not None]) / 100.0)
        calmar = _safe_ratio(annualized_return or 0.0, mdd)
    def pct_value(x):
        return round(x * 100.0, 4) if x is not None else None
    return {
        "validDailyReturnCount": len(returns),
        "minimumRequiredDailyReturns": MIN_RISK_SAMPLE_DAYS,
        "sampleSufficient": enough,
        "annualizedReturnPct": pct_value(annualized_return),
        "annualizedVolatilityPct": pct_value(annualized_volatility),
        "sharpeRatio": round(sharpe, 4) if sharpe is not None else None,
        "sortinoRatio": round(sortino, 4) if sortino is not None else None,
        "calmarRatio": round(calmar, 4) if calmar is not None else None,
        "noteZh": "至少20个有效日收益后才展示年化收益、波动率、夏普、索提诺和卡玛，样本不足不外推。",
    }


def fund_performance(state: dict, ledger: list[dict], current_assets: float) -> dict:
    accounting = ensure_fund_accounting(state, current_assets)
    history = combined_unit_history(state, current_assets)
    daily = daily_unit_series(history)
    daily_closes = [finite(x.get("closeUnitNav")) for x in daily]
    intraday = [finite(x.get("unitNav")) for x in history]
    gap_days = sum(int(x.get("observationGapBusinessDays") or 0) for x in daily)
    cash_flows = sum(finite(x.get("cashFlow"), 0.0) or 0.0 for x in accounting.get("unitEvents", [])[1:])
    current_unit_nav = finite(accounting.get("unitNav"), BASE_UNIT_NAV) or BASE_UNIT_NAV
    return {
        "accounting": accounting,
        "currentUnitNav": round(current_unit_nav, 6),
        "cumulativeNav": round(current_unit_nav / BASE_UNIT_NAV, 6),
        "cumulativeReturnPct": round((current_unit_nav / BASE_UNIT_NAV - 1.0) * 100.0, 4),
        "netSubscriptions": round(cash_flows, 2),
        "dailyCloseMaxDrawdownPct": max_drawdown([x for x in daily_closes if x is not None]),
        "intradayObservedMaxDrawdownPct": max_drawdown([x for x in intraday if x is not None]),
        "drawdownFrequencyZh": "正式最大回撤按日终单位净值；盘中已观测回撤单独列示",
        "missingBackendBusinessDays": gap_days,
        "daily": daily,
        "weekly": _period_series(daily, "week"),
        "monthly": _period_series(daily, "month"),
        "risk": risk_metrics(daily),
        "history": history,
    }


def board_limit_pct(code: str, name: str = "") -> float:
    code = str(code or "")
    upper_name = str(name or "").upper()
    if code.startswith(("30", "68")):
        return 20.0
    if code.startswith(("8", "9")):
        return 30.0
    if "ST" in upper_name:
        return 5.0
    return 10.0


def round_tick(price: float) -> float:
    return round(max(price, 0.01) + 1e-9, 2)


def price_band(code: str, name: str, prev_close: float | None) -> dict:
    limit_pct = board_limit_pct(code, name)
    prev = finite(prev_close)
    return {
        "limitPct": limit_pct,
        "upperLimit": round_tick(prev * (1.0 + limit_pct / 100.0)) if prev else None,
        "lowerLimit": round_tick(prev * (1.0 - limit_pct / 100.0)) if prev else None,
    }


def update_liquidity_profiles(state: dict, radar: dict, quotes: dict, day: str) -> None:
    profiles = state.setdefault("liquidityProfiles", {})
    rows: dict[str, dict] = {}
    for code, stock in (radar.get("stocks") or {}).items():
        rows[str(code)] = stock or {}
    for code, quote in quotes.items():
        rows.setdefault(str(code), {}).update({k: v for k, v in (quote or {}).items() if v is not None})
    for code, row in rows.items():
        amount = finite(row.get("amount"))
        if amount is None or amount <= 0:
            continue
        profile = profiles.setdefault(code, {"dailyAmounts": {}})
        daily = profile.setdefault("dailyAmounts", {})
        daily[day] = round(max(amount, finite(daily.get(day), 0.0) or 0.0), 2)
        keys = sorted(daily)[-60:]
        profile["dailyAmounts"] = {k: daily[k] for k in keys}
        completed = [finite(v) for k, v in profile["dailyAmounts"].items() if k < day and finite(v) is not None]
        recent = completed[-20:]
        profile["adv20Amount"] = round(statistics.mean(recent), 2) if recent else None
        profile["advSampleDays"] = len(recent)


def market_data(radar_stock: dict | None, quote: dict | None, fallback_price: float | None = None) -> dict:
    stock, quote = radar_stock or {}, quote or {}
    price = finite(quote.get("price")) or finite(stock.get("price")) or finite(fallback_price)
    change_pct = finite(quote.get("changePct"))
    if change_pct is None:
        change_pct = finite(stock.get("changePct"))
    prev_close = finite(quote.get("prevClose")) or finite(stock.get("prevClose"))
    if prev_close is None and price and change_pct is not None and change_pct > -99:
        prev_close = price / (1.0 + change_pct / 100.0)
    amount_candidates = [finite(stock.get("amount")), finite(quote.get("amount"))]
    amounts = [x for x in amount_candidates if x is not None and x > 0]
    return {
        "price": price,
        "prevClose": prev_close,
        "changePct": change_pct,
        "amount": min(amounts) if len(amounts) > 1 else (amounts[0] if amounts else None),
        "amountSource": "当时双源累计成交额较小值" if len(amounts) > 1 else "当时累计成交额",
        "quoteTime": quote.get("quoteTimestamp") or quote.get("quoteTime") or stock.get("quoteTime"),
    }


def _round_qty(qty: int, total_qty: int | None, side: str) -> int:
    qty = max(0, int(qty))
    if side == "SELL" and total_qty is not None and qty >= int(total_qty):
        return int(total_qty)
    return (qty // 100) * 100


def plan_execution(
    state: dict,
    *,
    side: str,
    code: str,
    name: str,
    requested_qty: int,
    reference_price: float,
    market: dict,
    day: str,
    total_position_qty: int | None = None,
) -> dict:
    side = str(side).upper()
    requested_qty = _round_qty(requested_qty, total_position_qty, side)
    ref = finite(reference_price)
    result = {
        "allowed": False,
        "side": side,
        "requestedQty": requested_qty,
        "filledQty": 0,
        "partialFill": False,
        "rejectCode": None,
        "rejectReasonZh": None,
        "executionModel": "v3-liquidity-capacity-point-in-time",
    }
    if requested_qty <= 0 or ref is None or ref <= 0:
        result.update(rejectCode="INVALID_ORDER", rejectReasonZh="委托股数或参考价格无效")
        return result

    amount = finite(market.get("amount"))
    prev_close = finite(market.get("prevClose"))
    band = price_band(code, name, prev_close)
    result.update(band)
    result["referencePrice"] = round(ref, 4)
    if prev_close is None:
        result.update(rejectCode="NO_PREV_CLOSE", rejectReasonZh="缺少昨收价，无法校验涨跌停价格")
        return result
    upper, lower = band["upperLimit"], band["lowerLimit"]
    if side == "BUY" and upper is not None and ref >= upper - 0.005:
        result.update(rejectCode="LIMIT_UP", rejectReasonZh="已到涨停价，模拟盘不假设可以买到")
        return result
    if side == "SELL" and lower is not None and ref <= lower + 0.005:
        result.update(rejectCode="LIMIT_DOWN", rejectReasonZh="已到跌停价，模拟盘不假设可以卖出")
        return result
    if amount is None or amount <= 0:
        result.update(rejectCode="NO_LIQUIDITY_DATA", rejectReasonZh="缺少当时累计成交额，拒绝假设成交")
        return result

    profile = (state.get("liquidityProfiles") or {}).get(code) or {}
    adv20 = finite(profile.get("adv20Amount"))
    sample_days = int(profile.get("advSampleDays") or 0)
    controls = state.setdefault("executionControl", {}).setdefault(day, {}).setdefault(code, {})
    traded_today = finite(controls.get("filledAmount"), 0.0) or 0.0
    per_order_cap = amount * ORDER_PARTICIPATION_LIMIT
    daily_cap = amount * DAY_PARTICIPATION_LIMIT
    if adv20 is not None and sample_days >= 5:
        daily_cap = min(daily_cap, adv20 * ADV20_PARTICIPATION_LIMIT)
        liquidity_basis = "当时累计成交额+历史ADV20"
    else:
        liquidity_basis = "当时累计成交额（ADV20样本不足，使用更保守日内上限）"
    remaining_daily_cap = max(0.0, daily_cap - traded_today)
    capacity_amount = min(per_order_cap, remaining_daily_cap)
    raw_qty = int(capacity_amount / ref)
    fill_qty = min(requested_qty, _round_qty(raw_qty, total_position_qty, side))
    if fill_qty <= 0:
        result.update(
            rejectCode="CAPACITY_EXHAUSTED",
            rejectReasonZh="当日流动性参与额度不足100股",
            intradayAmount=round(amount, 2),
            adv20Amount=round(adv20, 2) if adv20 is not None else None,
            advSampleDays=sample_days,
            capacityAmount=round(capacity_amount, 2),
            tradedAmountToday=round(traded_today, 2),
        )
        return result

    provisional_amount = fill_qty * ref
    participation = provisional_amount / amount
    impact_bps = min(MAX_IMPACT_BPS, BASE_SPREAD_BPS + IMPACT_COEFFICIENT_BPS * math.sqrt(max(0.0, participation)))
    signed_bps = impact_bps if side == "BUY" else -impact_bps
    execution_price = round_tick(ref * (1.0 + signed_bps / 10000.0))
    if side == "BUY" and upper is not None and execution_price >= upper:
        result.update(rejectCode="IMPACT_REACHES_LIMIT_UP", rejectReasonZh="考虑冲击成本后达到涨停价，拒绝假设成交")
        return result
    if side == "SELL" and lower is not None and execution_price <= lower:
        result.update(rejectCode="IMPACT_REACHES_LIMIT_DOWN", rejectReasonZh="考虑冲击成本后达到跌停价，拒绝假设成交")
        return result
    final_capacity_qty = _round_qty(int(capacity_amount / execution_price), total_position_qty, side)
    fill_qty = min(fill_qty, final_capacity_qty)
    if fill_qty <= 0:
        result.update(rejectCode="CAPACITY_EXHAUSTED", rejectReasonZh="冲击价格下容量不足100股")
        return result
    fill_amount = fill_qty * execution_price
    result.update({
        "allowed": True,
        "filledQty": fill_qty,
        "partialFill": fill_qty < requested_qty,
        "fillRatioPct": round(fill_qty / requested_qty * 100.0, 2),
        "executionPrice": execution_price,
        "filledAmount": round(fill_amount, 2),
        "slippageBps": round(impact_bps, 3),
        "marketImpactBps": round(max(0.0, impact_bps - BASE_SPREAD_BPS), 3),
        "participationPct": round(fill_amount / amount * 100.0, 4),
        "intradayAmount": round(amount, 2),
        "adv20Amount": round(adv20, 2) if adv20 is not None else None,
        "advSampleDays": sample_days,
        "capacityAmount": round(capacity_amount, 2),
        "dailyCapacityAmount": round(daily_cap, 2),
        "tradedAmountTodayBefore": round(traded_today, 2),
        "liquidityBasisZh": liquidity_basis,
        "amountSourceZh": market.get("amountSource"),
    })
    return result


def commit_execution(state: dict, code: str, day: str, plan: dict) -> None:
    if not plan.get("allowed"):
        return
    control = state.setdefault("executionControl", {}).setdefault(day, {}).setdefault(code, {})
    control["filledAmount"] = round(
        (finite(control.get("filledAmount"), 0.0) or 0.0) + (finite(plan.get("filledAmount"), 0.0) or 0.0), 2
    )
    control["filledQty"] = int(control.get("filledQty") or 0) + int(plan.get("filledQty") or 0)
    control["fillCount"] = int(control.get("fillCount") or 0) + 1
    control["lastParticipationPct"] = plan.get("participationPct")


def record_rejection(state: dict, *, code: str, name: str, side: str, plan: dict, timestamp: str) -> None:
    rows = state.setdefault("recentExecutionRejections", [])
    item = {
        "timestamp": timestamp,
        "code": code,
        "name": name,
        "side": side,
        "rejectCode": plan.get("rejectCode"),
        "reasonZh": plan.get("rejectReasonZh"),
        "requestedQty": plan.get("requestedQty"),
        "intradayAmount": plan.get("intradayAmount"),
        "capacityAmount": plan.get("capacityAmount"),
    }
    if not rows or any(rows[-1].get(k) != item.get(k) for k in ("code", "side", "rejectCode", "requestedQty")):
        rows.append(item)
    state["recentExecutionRejections"] = rows[-100:]


def execution_report(state: dict, ledger: list[dict], current_assets: float) -> dict:
    modeled = [x for x in ledger if x.get("executionModel") == "v3-liquidity-capacity-point-in-time"]
    legacy = [x for x in ledger if x.get("side") in {"BUY", "SELL"} and x not in modeled]
    partial = [x for x in modeled if x.get("partialFill")]
    slippages = [finite(x.get("slippageBps")) for x in modeled if finite(x.get("slippageBps")) is not None]
    amount = sum(finite(x.get("amount"), 0.0) or 0.0 for x in ledger if x.get("side") in {"BUY", "SELL"})
    return {
        "executionModel": "v3-liquidity-capacity-point-in-time",
        "capacityCapital": finite(state.get("capitalCapacity")) or finite(state.get("initialCapital")),
        "modeledFillCount": len(modeled),
        "legacyFixedSlippageFillCount": len(legacy),
        "partialFillCount": len(partial),
        "averageSlippageBps": round(statistics.mean(slippages), 3) if slippages else None,
        "grossTradedAmount": round(amount, 2),
        "turnoverPctOfCurrentAssets": round(amount / current_assets * 100.0, 3) if current_assets else None,
        "recentRejections": (state.get("recentExecutionRejections") or [])[-20:],
        "constraintsZh": [
            "买入按100股整手，卖出清仓允许处理剩余零股；普通A股T+1。",
            "单笔不超过当时累计成交额0.8%，当日累计不超过当时成交额1.5%。",
            "ADV20至少5个历史样本后，当日成交还受ADV20的2%约束。",
            "涨停不假设买得到、跌停不假设卖得出；缺少昨收或成交额时拒绝模拟成交。",
            "成交价含点差和随参与率上升的市场冲击；容量不足只部分成交。",
        ],
        "legacyNoteZh": "v3启用前成交永久保留，但仍标记为旧版固定滑点模型，不事后伪造容量字段。",
    }
