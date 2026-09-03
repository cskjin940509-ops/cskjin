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

import shadow_fund_v3 as fund

CN = ZoneInfo("Asia/Shanghai")
ROOT = Path(__file__).resolve().parents[1]
RADAR = ROOT / "astock_radar" / "latest.json"
OUT = ROOT / "astock_ai_portfolio"
STATE_PATH = OUT / "state.json"
LEDGER_PATH = OUT / "ledger.json"
LATEST_PATH = OUT / "latest.json"
AUTOMATION_PATH = OUT / "automation.json"
CYCLE_LOG_PATH = OUT / "cycle_log.json"
INITIAL_CAPITAL = float(os.environ.get("ASTOCK_SHADOW_CAPITAL", "20000000"))
STRATEGY_VERSION = "v1.0-ai-shadow-point-in-time"
RADAR_MAX_AGE_SECONDS = 15 * 60

# Portfolio constraints: this is a simulated shadow account, not broker execution.
MAX_POSITIONS = 5
MAX_GROSS_WEIGHT = 0.60
MAX_SINGLE_WEIGHT = 0.15
MAX_SECTOR_WEIGHT = 0.25
MAX_NEW_BUYS_PER_DAY = 3
MIN_BUY_SCORE = 64.0
BUY_SLIPPAGE_BPS = 5.0
SELL_SLIPPAGE_BPS = 5.0

# Conservative simulation fee model.
BROKER_COMMISSION_RATE = 0.0002
MIN_COMMISSION = 5.0
REGULATORY_FEE_RATE = 0.0000541
STAMP_DUTY_SELL_RATE = 0.0005

# Current point-in-time market data is registered once per cycle and consumed by
# the dynamic execution layer.  It is never persisted as an assumed future fill.
EXECUTION_MARKET: dict[str, dict] = {}


def now_cn() -> datetime:
    fixed = os.environ.get("ASTOCK_NOW")
    if fixed:
        parsed = datetime.fromisoformat(fixed)
        return parsed.replace(tzinfo=CN) if parsed.tzinfo is None else parsed.astimezone(CN)
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
    # Avoid initiating new positions during the final closing-auction minutes.
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
    if code.startswith(("8", "9")):
        return "bj" + code
    return ("sh" if code.startswith(("5", "6")) else "sz") + code


def fetch_tencent_quotes(codes: list[str]) -> dict[str, dict]:
    if os.environ.get("ASTOCK_DISABLE_QUOTE_FETCH") == "1":
        return {}
    codes = sorted({c for c in codes if re.fullmatch(r"\d{6}", c or "")})
    if not codes:
        return {}
    q = ",".join(symbol(c) for c in codes)
    req = urllib.request.Request(
        f"https://qt.gtimg.cn/q={q}",
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://gu.qq.com/",
            "Accept": "*/*",
        },
    )
    try:
        raw = urllib.request.urlopen(req, timeout=8).read().decode("gbk", errors="ignore")
    except Exception:
        return {}
    out: dict[str, dict] = {}
    for line in raw.split(";"):
        m = re.search(r'v_(sh|sz|bj)(\d{6})="([^"]*)"', line)
        if not m:
            continue
        code = m.group(2)
        f = m.group(3).split("~")
        try:
            price = float(f[3]) if len(f) > 3 and f[3] else None
            prev = float(f[4]) if len(f) > 4 and f[4] else None
            name = f[1] if len(f) > 1 else code
            quote_time = f[30] if len(f) > 30 else None
            amount = float(f[37]) * 10000.0 if len(f) > 37 and f[37] else None
            volume = float(f[6]) * 100.0 if len(f) > 6 and f[6] else None
            change_pct = ((price / prev - 1) * 100) if price and prev else None
            out[code] = {
                "code": code,
                "name": name,
                "price": price,
                "prevClose": prev,
                "changePct": change_pct,
                "quoteTime": quote_time,
                "quoteTimestamp": quote_time,
                "amount": amount,
                "volumeShares": volume,
                "source": "腾讯实时行情",
            }
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
    return {
        "schemaVersion": 3,
        "strategyVersion": STRATEGY_VERSION,
        "mode": "AI影子实盘",
        "simulated": True,
        "initialCapital": INITIAL_CAPITAL,
        "cash": INITIAL_CAPITAL,
        "realizedPnl": 0.0,
        "positions": {},
        "navHistory": [],
        "dailyControl": {},
        "createdAt": iso(),
        "updatedAt": iso(),
        "capitalEvents": [],
    }


def capital_base(state: dict) -> float:
    value = float(state.get("initialCapital") or INITIAL_CAPITAL)
    return value if value > 0 else INITIAL_CAPITAL


def migrate_capital_capacity(state: dict, dt: datetime | None = None) -> dict | None:
    """Increase capacity without rewriting fills or resetting the unit NAV."""
    dt = dt or now_cn()
    old = capital_base(state)
    target = float(INITIAL_CAPITAL)
    state.setdefault("capitalEvents", [])
    if math.isclose(old, target, rel_tol=0.0, abs_tol=0.01):
        state["initialCapital"] = target
        state["capitalCapacity"] = target
        fund.ensure_fund_accounting(state)
        return None

    delta = round(target - old, 2)
    if delta < 0 and float(state.get("cash") or 0.0) + delta < -0.01:
        raise RuntimeError("目标资金容量低于当前已占用资金，拒绝自动缩减")

    # Capture the pre-subscription account value before adding cash.  Existing
    # history and benchmark series remain intact.
    old_history = list(state.get("legacyNavHistory") or []) + list(state.get("navHistory") or [])
    pre_assets = float(old_history[-1].get("nav") or old) if old_history else old
    state["cash"] = round(float(state.get("cash") or 0.0) + delta, 2)
    state["initialCapital"] = target
    state["capitalCapacity"] = target
    state["capitalActivatedAt"] = iso(dt)
    event = {
        "eventId": f"capital-{dt.strftime('%Y%m%d-%H%M%S')}",
        "timestamp": iso(dt),
        "type": "CAPITAL_CAPACITY_ADJUSTMENT",
        "fromCapital": round(old, 2),
        "toCapital": round(target, 2),
        "cashContribution": delta,
        "preContributionAssets": round(pre_assets, 2),
        "retroactive": False,
        "noteZh": "资金容量按当前时点调整；保留此前成交审计，不倒改历史股数、价格或盈亏。",
    }
    state["capitalEvents"].append(event)
    fund.ensure_fund_accounting(state, pre_assets + delta)
    return event


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=CN) if parsed.tzinfo is None else parsed.astimezone(CN)
    except Exception:
        return None


def radar_freshness(radar: dict, dt: datetime) -> tuple[bool, float | None]:
    captured = parse_time(str(radar.get("capturedAt") or ""))
    if captured is None:
        return False, None
    raw_age = (dt - captured).total_seconds()
    if raw_age < -60:
        return False, raw_age
    age = max(0.0, raw_age)
    return age <= RADAR_MAX_AGE_SECONDS, age


def record_automation_cycle(
    status: str,
    reason_zh: str,
    dt: datetime | None = None,
    *,
    radar: dict | None = None,
    state: dict | None = None,
    ledger: list | None = None,
    actions: list | None = None,
    error: str | None = None,
) -> dict:
    dt = dt or now_cn()
    radar = radar or {}
    state = state or {}
    ledger = ledger or []
    actions = actions or []
    previous = read_json(AUTOMATION_PATH, {})
    fresh, age = radar_freshness(radar, dt)
    cycle_id = "-".join(filter(None, [
        os.environ.get("GITHUB_RUN_ID"),
        os.environ.get("GITHUB_RUN_ATTEMPT"),
    ])) or dt.strftime("%Y%m%d-%H%M%S")
    last_trade = next(
        (str(x.get("timestamp")) for x in reversed(ledger) if x.get("side") in {"BUY", "SELL"}),
        previous.get("lastTradeAt"),
    )
    successful = status != "ERROR"
    payload = {
        "schemaVersion": 1,
        "enabled": True,
        "executionMode": "SIMULATED_ONLY",
        "simulated": True,
        "brokerConnected": False,
        "appRequired": False,
        "engineLocation": "GitHub Actions云端定时任务",
        "scheduleZh": "A股交易时段约每5分钟检查一次；收盘后仅更新状态，不虚构成交",
        "cycleId": cycle_id,
        "lastRunAt": iso(dt),
        "lastSuccessAt": iso(dt) if successful else previous.get("lastSuccessAt"),
        "lastTradeAt": last_trade,
        "status": status,
        "statusZh": reason_zh,
        "runSource": os.environ.get("ASTOCK_RUN_SOURCE", "manual-or-integrated"),
        "sessionOpen": trading_session(dt),
        "radarCapturedAt": radar.get("capturedAt"),
        "radarFresh": fresh,
        "radarAgeSeconds": round(age, 1) if age is not None else None,
        "actionsThisCycle": len(actions),
        "buyActionsThisCycle": sum(1 for x in actions if x.get("side") == "BUY"),
        "sellActionsThisCycle": sum(1 for x in actions if x.get("side") == "SELL"),
        "ledgerDecisionCount": len(ledger),
        "positionCount": len(state.get("positions") or {}),
        "capitalCapacity": round(capital_base(state), 2),
        "error": error,
        "knownIncident": {
            "from": "2026-08-20T15:10:00+08:00",
            "to": "2026-09-03T10:27:19+08:00",
            "type": "MISSING_BACKEND_CYCLES",
            "backfilledTrades": False,
            "causeZh": "盘中雷达工作流的YAML脚本块缩进错误导致定时调度停摆；不能把该区间解释为策略主动不交易。",
        },
        "disclaimerZh": "仅为自动模拟影子交易，不连接券商、不发送真实订单。",
    }
    log = read_json(CYCLE_LOG_PATH, [])
    if not isinstance(log, list):
        log = []
    entry = {
        k: payload.get(k) for k in (
            "cycleId", "lastRunAt", "status", "statusZh", "runSource", "sessionOpen",
            "radarCapturedAt", "radarFresh", "radarAgeSeconds", "actionsThisCycle",
            "buyActionsThisCycle", "sellActionsThisCycle", "positionCount", "error",
        )
    }
    if not log or log[-1].get("cycleId") != cycle_id:
        log.append(entry)
    write_json(CYCLE_LOG_PATH, log[-2000:])
    write_json(AUTOMATION_PATH, payload)
    return payload


def get_daily_control(state: dict, date: str) -> dict:
    d = state.setdefault("dailyControl", {}).setdefault(
        date, {"newBuys": 0, "sells": 0, "lastDecisionAt": None}
    )
    return d


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
        score += 5
        reasons.append("主线确认中+5")
    elif stage == "EMERGING":
        score += 3
        reasons.append("主线潜在形成+3")
    elif stage == "ESTABLISHED":
        score -= 3
        reasons.append("已成主线-3")

    if formation >= 66:
        score += 4
        reasons.append("形成分强+4")
    elif formation >= 60:
        score += 2
        reasons.append("形成分改善+2")

    if flow_pct >= 12:
        score += 5
        reasons.append("资金强度高+5")
    elif flow_pct >= 6:
        score += 3
        reasons.append("资金正向+3")
    elif flow_pct < 0:
        score -= 6
        reasons.append("资金转负-6")

    if flow_score >= 70:
        score += 3
        reasons.append("资金评分高+3")

    if -0.8 <= change <= 3.5:
        score += 4
        reasons.append("价格尚未充分扩张+4")
    elif 3.5 < change <= 4.5:
        score += 1
        reasons.append("价格开始扩张+1")
    elif change > 4.5:
        rejects.append("当日涨幅已超过提前介入上限")
    elif change < -2.5:
        rejects.append("当日走势明显走弱")

    if amount < 50_000_000:
        rejects.append("成交额低于流动性门槛")

    if chase == "HIGH":
        rejects.append("追高风险高")
    elif chase == "MEDIUM":
        score -= 5
        reasons.append("追高风险中-5")
    elif chase == "LOW":
        score += 2
        reasons.append("追高风险低+2")

    if y.get("quoteOk") and stock.get("price") and y.get("price"):
        div = abs(float(y["price"]) / float(stock["price"]) - 1) * 100
        if div > 0.50:
            rejects.append(f"双源价格偏差{div:.2f}%")
    confirmation = y.get("confirmation")
    if confirmation == "POSITIVE_INDEPENDENT_FLOW":
        score += 5
        reasons.append("Yunai独立资金正确认+5")
    elif confirmation == "NEGATIVE_INDEPENDENT_FLOW":
        score -= 8
        reasons.append("Yunai独立资金负确认-8")

    return round(score, 2), reasons, rejects


def target_weight(score: float) -> float:
    if score >= 82:
        return 0.15
    if score >= 76:
        return 0.12
    if score >= 70:
        return 0.10
    return 0.08


def append_decision(ledger: list, **kwargs) -> dict:
    item = {
        "decisionId": f"{now_cn().strftime('%Y%m%d-%H%M%S')}-{len(ledger)+1:05d}",
        "timestamp": iso(),
        "strategyVersion": STRATEGY_VERSION,
        "mode": "AI影子实盘",
        "simulated": True,
        **kwargs,
    }
    ledger.append(item)
    return item


def buy_position(state: dict, ledger: list, stock: dict, score: float, reasons: list[str],
                 ref_price: float, ref_source: str, prices: dict[str, float]) -> dict | None:
    code = stock["code"]
    if code in state["positions"]:
        return None
    nav, _ = portfolio_nav(state, prices)
    _, sector_weights, gross = current_weights(state, prices)
    sector = stock.get("sector") or "未知"
    desired = min(target_weight(score), MAX_SINGLE_WEIGHT)
    desired = min(desired, MAX_GROSS_WEIGHT - gross)
    desired = min(desired, MAX_SECTOR_WEIGHT - sector_weights.get(sector, 0.0))
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
        amount = round(px * qty, 2)
        fee = fees(amount, "BUY")
    if qty < 100 or amount + fee > state["cash"]:
        return None

    state["cash"] = round(state["cash"] - amount - fee, 2)
    dt = now_cn()
    position = {
        "code": code,
        "name": stock.get("name") or code,
        "sector": sector,
        "qty": qty,
        "avgCost": round((amount + fee) / qty, 4),
        "costAmount": round(amount + fee, 2),
        "entryPrice": px,
        "entryReferencePrice": round(ref_price, 4),
        "entryPriceSource": ref_source,
        "entryTimestamp": iso(dt),
        "entryDate": dt.date().isoformat(),
        "initialWeightTarget": round(desired, 4),
        "lastPrice": ref_price,
        "lastPriceAt": iso(dt),
        "missingRadarCount": 0,
        "partialProfitTaken": False,
        "seenTradeDates": [dt.date().isoformat()],
        "buyScore": score,
        "buyReasonZh": "；".join(reasons),
        "invalidationZh": "主线连续退出雷达、资金显著转负，或相对持仓成本跌幅达到4%",
        "expectedHorizonZh": "次日优先验证，正常持有1-3个交易日，最长约5个交易日",
    }
    state["positions"][code] = position
    get_daily_control(state, dt.date().isoformat())["newBuys"] += 1
    decision = append_decision(
        ledger,
        side="BUY",
        sideZh="买入",
        code=code,
        name=position["name"],
        sector=sector,
        qty=qty,
        price=px,
        referencePrice=round(ref_price, 4),
        priceSource=ref_source,
        amount=amount,
        fee=fee,
        targetWeightPct=round(desired * 100, 2),
        decisionScore=score,
        reasonZh=position["buyReasonZh"],
        invalidationZh=position["invalidationZh"],
        expectedHorizonZh=position["expectedHorizonZh"],
    )
    return decision


def sell_position(state: dict, ledger: list, pos: dict, qty: int, ref_price: float,
                  reason: str, prices: dict[str, float], execution_plan: dict | None = None) -> dict | None:
    qty = min(int(qty), int(pos.get("qty", 0)))
    qty = (qty // 100) * 100
    if qty <= 0:
        return None
    px = float(execution_plan.get("executionPrice")) if execution_plan else exec_price(ref_price, "SELL")
    amount = round(px * qty, 2)
    fee = fees(amount, "SELL")
    avg_cost = float(pos.get("avgCost") or 0.0)
    basis = round(avg_cost * qty, 2)
    realized = round(amount - fee - basis, 2)
    state["cash"] = round(state["cash"] + amount - fee, 2)
    state["realizedPnl"] = round(float(state.get("realizedPnl", 0.0)) + realized, 2)
    old_qty = int(pos["qty"])
    remain = old_qty - qty

    decision = append_decision(
        ledger,
        side="SELL",
        sideZh="卖出",
        code=pos["code"],
        name=pos.get("name") or pos["code"],
        sector=pos.get("sector") or "未知",
        qty=qty,
        price=px,
        referencePrice=round(ref_price, 4),
        priceSource="腾讯实时行情/雷达行情",
        amount=amount,
        fee=fee,
        realizedPnl=realized,
        realizedReturnPct=round((px / avg_cost - 1) * 100, 2) if avg_cost else None,
        reasonZh=reason,
        remainingQty=remain,
        **({
            "executionModel": execution_plan.get("executionModel"),
            "capacityRequestedQty": execution_plan.get("requestedQty"),
            "filledQty": execution_plan.get("filledQty"),
            "slippageBps": execution_plan.get("slippageBps"),
            "marketImpactBps": execution_plan.get("marketImpactBps"),
            "participationPct": execution_plan.get("participationPct"),
            "intradayAmount": execution_plan.get("intradayAmount"),
            "adv20Amount": execution_plan.get("adv20Amount"),
            "advSampleDays": execution_plan.get("advSampleDays"),
            "capacityAmount": execution_plan.get("capacityAmount"),
            "dailyCapacityAmount": execution_plan.get("dailyCapacityAmount"),
            "liquidityBasisZh": execution_plan.get("liquidityBasisZh"),
            "priceLimitPct": execution_plan.get("limitPct"),
            "upperLimit": execution_plan.get("upperLimit"),
            "lowerLimit": execution_plan.get("lowerLimit"),
        } if execution_plan else {}),
    )

    if remain <= 0:
        state["positions"].pop(pos["code"], None)
    else:
        pos["qty"] = remain
        pos["costAmount"] = round(avg_cost * remain, 2)
        if "止盈" in reason:
            pos["partialProfitTaken"] = True
    if execution_plan:
        fund.commit_execution(state, pos["code"], now_cn().date().isoformat(), execution_plan)
    get_daily_control(state, now_cn().date().isoformat())["sells"] += 1
    return decision


def evaluate_exits(state: dict, ledger: list, radar_stocks: dict, quotes: dict[str, dict],
                   prices: dict[str, float]) -> list[dict]:
    actions: list[dict] = []
    today = now_cn().date().isoformat()
    for code in list(state.get("positions", {}).keys()):
        pos = state["positions"].get(code)
        if not pos:
            continue
        mark_seen_date(pos, today)
        q = quotes.get(code) or {}
        cur = q.get("price") or radar_stocks.get(code, {}).get("price") or pos.get("lastPrice")
        if not cur:
            continue
        cur = float(cur)
        prices[code] = cur
        pos["lastPrice"] = cur
        pos["lastPriceAt"] = iso()
        avg = float(pos.get("avgCost") or 0.0)
        ret = (cur / avg - 1) * 100 if avg else 0.0
        live = radar_stocks.get(code)
        if live:
            pos["missingRadarCount"] = 0
        else:
            pos["missingRadarCount"] = int(pos.get("missingRadarCount", 0)) + 1

        # Ordinary A shares are T+1: no same-day sell of today's new position.
        if pos.get("entryDate") >= today:
            continue

        reason = None
        qty = int(pos["qty"])
        if ret <= -4.0:
            reason = f"保护性止损：持仓收益{ret:.2f}%触及-4%风险边界"
        elif live and float(live.get("mainFlowPct") or 0.0) <= -6.0 and ret <= 2.0:
            reason = f"资金失效：主力资金强度{float(live.get('mainFlowPct') or 0.0):.1f}%且持仓收益{ret:.2f}%"
        elif ret >= 12.0:
            reason = f"强制锁定利润：累计浮盈{ret:.2f}%超过12%"
        elif ret >= 8.0 and not pos.get("partialProfitTaken"):
            qty = max(100, (int(pos["qty"]) // 2 // 100) * 100)
            reason = f"分批止盈：累计浮盈{ret:.2f}%超过8%，先减半仓"
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
            if d:
                actions.append(d)
    return actions


def evaluate_entries(state: dict, ledger: list, radar: dict, prices: dict[str, float]) -> list[dict]:
    dt = now_cn()
    if not can_open_new(dt):
        return []
    daily = get_daily_control(state, dt.date().isoformat())
    if int(daily.get("newBuys", 0)) >= MAX_NEW_BUYS_PER_DAY:
        return []
    if len(state.get("positions", {})) >= MAX_POSITIONS:
        return []

    candidates = []
    for code, st in (radar.get("stocks") or {}).items():
        st = dict(st)
        st.setdefault("code", code)
        if code in state.get("positions", {}):
            continue
        score, reasons, rejects = score_candidate(st)
        ref, src, divergence = candidate_reference_price(st)
        if ref is None:
            rejects.append(src)
        if rejects:
            continue
        if score < MIN_BUY_SCORE:
            continue
        candidates.append((score, st, reasons, float(ref), src))
    candidates.sort(key=lambda x: x[0], reverse=True)

    actions: list[dict] = []
    for score, st, reasons, ref, src in candidates:
        if len(state["positions"]) >= MAX_POSITIONS:
            break
        if get_daily_control(state, dt.date().isoformat())["newBuys"] >= MAX_NEW_BUYS_PER_DAY:
            break
        d = buy_position(state, ledger, st, score, reasons, ref, src, prices)
        if d:
            actions.append(d)
            prices[st["code"]] = ref
    return actions


def max_drawdown_pct(nav_history: list[dict]) -> float:
    peak = None
    mdd = 0.0
    for x in nav_history:
        nav = x.get("nav")
        if not nav:
            continue
        nav = float(nav)
        peak = nav if peak is None else max(peak, nav)
        if peak:
            dd = (nav / peak - 1) * 100
            mdd = min(mdd, dd)
    return round(mdd, 2)


def daily_series(nav_history: list[dict], initial_capital: float = INITIAL_CAPITAL) -> list[dict]:
    by_date: dict[str, list[dict]] = {}
    for x in nav_history:
        by_date.setdefault(x.get("date", ""), []).append(x)
    out = []
    prev_close = initial_capital
    for date in sorted(k for k in by_date if k):
        rows = by_date[date]
        close = float(rows[-1].get("nav") or prev_close)
        day_ret = (close / prev_close - 1) * 100 if prev_close else 0.0
        out.append({
            "date": date,
            "closeNav": round(close, 2),
            "dailyReturnPct": round(day_ret, 3),
            "cumulativeReturnPct": round((close / initial_capital - 1) * 100, 3),
        })
        prev_close = close
    return out


def closed_sell_stats(ledger: list[dict]) -> dict:
    sells = [x for x in ledger if x.get("side") == "SELL" and x.get("realizedPnl") is not None]
    wins = [x for x in sells if float(x.get("realizedPnl") or 0) > 0]
    losses = [x for x in sells if float(x.get("realizedPnl") or 0) < 0]
    avg_win = sum(float(x["realizedPnl"]) for x in wins) / len(wins) if wins else 0.0
    avg_loss = sum(float(x["realizedPnl"]) for x in losses) / len(losses) if losses else 0.0
    return {
        "sellDecisionCount": len(sells),
        "profitableSellCount": len(wins),
        "winRatePct": round(len(wins) / len(sells) * 100, 2) if sells else None,
        "avgWinPnl": round(avg_win, 2),
        "avgLossPnl": round(avg_loss, 2),
        "profitLossRatio": round(abs(avg_win / avg_loss), 2) if avg_loss else None,
    }


def build_latest(state: dict, ledger: list, prices: dict[str, float], radar: dict) -> dict:
    nav, mv = portfolio_nav(state, prices)
    initial_capital = capital_base(state)
    positions = []
    for code, p in state.get("positions", {}).items():
        cur = prices.get(code, p.get("lastPrice") or p.get("avgCost") or 0.0)
        qty = int(p.get("qty", 0))
        avg = float(p.get("avgCost") or 0.0)
        value = qty * float(cur or 0)
        pnl = value - qty * avg
        positions.append({
            **p,
            "currentPrice": round(float(cur or 0), 4),
            "marketValue": round(value, 2),
            "floatingPnl": round(pnl, 2),
            "floatingReturnPct": round((float(cur) / avg - 1) * 100, 2) if avg and cur else None,
            "currentWeightPct": round(value / nav * 100, 2) if nav else 0.0,
            "tradingDaysObserved": len(p.get("seenTradeDates", [])),
            "currentActionZh": (
                "次日优先观察，今日按T+1不可卖"
                if p.get("entryDate") == now_cn().date().isoformat()
                else "继续滚动评估持有/减仓/卖出条件"
            ),
        })
    positions.sort(key=lambda x: x.get("currentWeightPct", 0), reverse=True)

    performance = fund.fund_performance(state, ledger, nav)
    hist = performance["history"]
    day = performance["daily"]
    today = now_cn().date().isoformat()
    today_row = next((x for x in reversed(day) if x.get("date") == today), None)
    today_ret = today_row.get("dailyReturnPct") if today_row else None

    sector_exposure: dict[str, float] = {}
    for p in positions:
        sector = str(p.get("sector") or "未知")
        sector_exposure[sector] = sector_exposure.get(sector, 0.0) + float(p.get("currentWeightPct") or 0.0)
    sector_rows = [
        {"sector": key, "weightPct": round(value, 2)}
        for key, value in sorted(sector_exposure.items(), key=lambda x: x[1], reverse=True)
    ]
    top_weights = [float(x.get("currentWeightPct") or 0.0) for x in positions]
    fee_total = sum(float(x.get("fee") or 0.0) for x in ledger)
    buy_amount = sum(float(x.get("amount") or 0.0) for x in ledger if x.get("side") == "BUY")
    sell_amount = sum(float(x.get("amount") or 0.0) for x in ledger if x.get("side") == "SELL")
    execution = fund.execution_report(state, ledger, nav)
    accounting = performance["accounting"]

    summary = {
        "initialCapital": initial_capital,
        "capitalCapacity": initial_capital,
        "inceptionCapital": accounting.get("inceptionCapital"),
        "totalAssets": round(nav, 2),
        "fundUnits": accounting.get("fundUnits"),
        "unitNav": performance.get("currentUnitNav"),
        "cumulativeNav": performance.get("cumulativeNav"),
        "cash": round(float(state.get("cash", 0.0)), 2),
        "marketValue": round(mv, 2),
        "positionPct": round(mv / nav * 100, 2) if nav else 0.0,
        "cashPct": round(float(state.get("cash", 0.0)) / nav * 100, 2) if nav else 0.0,
        "todayReturnPct": round(today_ret, 3) if today_ret is not None else None,
        "cumulativeReturnPct": round(float(performance.get("cumulativeReturnPct") or 0.0), 3),
        "realizedPnl": round(float(state.get("realizedPnl", 0.0)), 2),
        "floatingPnl": round(sum(float(x.get("floatingPnl") or 0) for x in positions), 2),
        "maxDrawdownPct": performance.get("dailyCloseMaxDrawdownPct"),
        "maxDrawdownFrequency": "DAILY_CLOSE_UNIT_NAV",
        "intradayObservedMaxDrawdownPct": performance.get("intradayObservedMaxDrawdownPct"),
        "missingBackendBusinessDays": performance.get("missingBackendBusinessDays"),
        "positionCount": len(positions),
        **closed_sell_stats(ledger),
    }
    return {
        "schemaVersion": 3,
        "strategyVersion": STRATEGY_VERSION,
        "mode": "AI影子实盘",
        "simulated": True,
        "disclaimerZh": "这是按真实时点数据生成的模拟影子组合，不会向券商发送订单，也不代表收益保证。",
        "updatedAt": iso(),
        "radarCapturedAt": radar.get("capturedAt"),
        "radarStatus": radar.get("status"),
        "summary": summary,
        "positions": positions,
        "todayDecisions": [x for x in ledger if str(x.get("timestamp", "")).startswith(today)],
        "recentDecisions": ledger[-100:],
        "allDecisions": ledger,
        "capitalEvents": (state.get("capitalEvents") or [])[-10:],
        "capitalStages": accounting.get("unitEvents"),
        "dailyPerformance": day[-250:],
        "weeklyPerformance": performance.get("weekly", [])[-104:],
        "monthlyPerformance": performance.get("monthly", [])[-60:],
        "navHistory": hist[-1000:],
        "performanceReport": {
            "valuation": {
                "method": accounting.get("method"),
                "unitNav": performance.get("currentUnitNav"),
                "cumulativeNav": performance.get("cumulativeNav"),
                "fundUnits": accounting.get("fundUnits"),
                "netSubscriptions": performance.get("netSubscriptions"),
                "noteZh": accounting.get("noteZh"),
            },
            "returns": {
                "cumulativeReturnPct": performance.get("cumulativeReturnPct"),
                "daily": day[-250:],
                "weekly": performance.get("weekly", [])[-104:],
                "monthly": performance.get("monthly", [])[-60:],
            },
            "risk": {
                **performance.get("risk", {}),
                "dailyCloseMaxDrawdownPct": performance.get("dailyCloseMaxDrawdownPct"),
                "intradayObservedMaxDrawdownPct": performance.get("intradayObservedMaxDrawdownPct"),
                "drawdownFrequencyZh": performance.get("drawdownFrequencyZh"),
                "missingBackendBusinessDays": performance.get("missingBackendBusinessDays"),
            },
            "exposure": {
                "grossExposurePct": round(mv / nav * 100, 2) if nav else 0.0,
                "netExposurePct": round(mv / nav * 100, 2) if nav else 0.0,
                "cashPct": round(float(state.get("cash", 0.0)) / nav * 100, 2) if nav else 0.0,
                "top1ConcentrationPct": round(sum(top_weights[:1]), 2),
                "top5ConcentrationPct": round(sum(top_weights[:5]), 2),
                "sectorExposure": sector_rows,
            },
            "transactions": {
                "decisionCount": len(ledger),
                "buyDecisionCount": sum(1 for x in ledger if x.get("side") == "BUY"),
                "sellDecisionCount": sum(1 for x in ledger if x.get("side") == "SELL"),
                "grossBuyAmount": round(buy_amount, 2),
                "grossSellAmount": round(sell_amount, 2),
                "totalFees": round(fee_total, 2),
                **closed_sell_stats(ledger),
            },
            "liquidityAndCapacity": execution,
        },
        "rulesZh": {
            "newEntry": "只从全天提前雷达候选中择优，优先潜在形成/确认中、价格未充分扩张、资金正向且追高风险低的股票。",
            "position": "资金容量2000万元；单股最高15%、单板块最高25%，总仓位由机会质量决定，容量不足只部分成交。",
            "exit": "遵守A股T+1；涨停不假设能买入、跌停不假设能卖出，止损和目标调仓也受真实流动性容量约束。",
            "valuation": "采用基金份额净值法；增资按增资前单位净值发行份额，不重置历史收益。",
            "drawdown": "正式最大回撤按日终单位净值计算；盘中已观测最大回撤单独显示，周频和月频只用于收益归因。",
            "audit": "全部历史成交永久保留；旧版成交明确标记为固定滑点模型，不事后伪造容量字段。",
        },
    }


def _main_impl() -> int:
    global EXECUTION_MARKET
    OUT.mkdir(parents=True, exist_ok=True)
    dt = now_cn()
    if not RADAR.exists():
        record_automation_cycle("BLOCKED_NO_RADAR", "后台已运行，但没有可用雷达数据，拒绝交易", dt)
        print(json.dumps({"state": "no-radar", "time": iso(dt)}, ensure_ascii=False))
        return 0

    radar = read_json(RADAR, {})
    state = read_json(STATE_PATH, new_state())
    ledger = read_json(LEDGER_PATH, [])
    if not isinstance(ledger, list):
        ledger = []
    capital_event = migrate_capital_capacity(state, dt)
    radar_date = str(radar.get("date") or "")
    if radar_date != dt.date().isoformat():
        # A stale signal must never trade, but accounting, heartbeat and the
        # investor-style report still need to be persisted independently.
        prices = {
            code: float(pos.get("lastPrice") or pos.get("avgCost") or 0.0)
            for code, pos in (state.get("positions") or {}).items()
        }
        nav, _ = portfolio_nav(state, prices)
        fund.ensure_fund_accounting(state, nav)
        latest = build_latest(state, ledger, prices, radar)
        automation = record_automation_cycle(
            "BLOCKED_STALE_RADAR", "后台已运行并更新基金报表，但雷达不是当日数据，拒绝使用旧数据交易",
            dt, radar=radar, state=state, ledger=ledger
        )
        latest["automation"] = automation
        latest["capitalMigrationThisCycle"] = capital_event
        latest["dataFreshness"] = {
            "radarFresh": False,
            "radarAgeSeconds": None,
            "maxAllowedAgeSeconds": RADAR_MAX_AGE_SECONDS,
        }
        state["updatedAt"] = iso(dt)
        state["strategyVersion"] = STRATEGY_VERSION
        write_json(STATE_PATH, state)
        write_json(LEDGER_PATH, ledger)
        write_json(LATEST_PATH, latest)
        print(json.dumps({"state": "stale-radar", "radarDate": radar_date, "time": iso(dt)}, ensure_ascii=False))
        return 0

    codes = list(state.get("positions", {}).keys())
    codes += list((radar.get("stocks") or {}).keys())
    quotes = fetch_tencent_quotes(codes)
    prices: dict[str, float] = {}
    EXECUTION_MARKET = {}
    for code in set(codes):
        q = quotes.get(code) or {}
        st = (radar.get("stocks") or {}).get(code) or {}
        p = q.get("price") or st.get("price")
        if p:
            prices[code] = float(p)
        fallback = (state.get("positions") or {}).get(code, {}).get("lastPrice")
        EXECUTION_MARKET[code] = fund.market_data(st, q, fallback)
    fund.update_liquidity_profiles(state, radar, quotes, dt.date().isoformat())

    actions: list[dict] = []
    radar_fresh, radar_age = radar_freshness(radar, dt)
    # Buy/sell decisions are only allowed during actual exchange trading hours.
    # Post-close jobs may update NAV but must never invent a fill after the market closes.
    if trading_session(dt) and radar_fresh:
        # Exits are evaluated before entries, so freed cash can be reused only after an auditable sell.
        actions += evaluate_exits(state, ledger, radar.get("stocks") or {}, quotes, prices)
        actions += evaluate_entries(state, ledger, radar, prices)

    nav, mv = portfolio_nav(state, prices)
    accounting = fund.ensure_fund_accounting(state, nav)
    unit_nav = float(accounting.get("unitNav") or 1.0)
    nav_point = {
        "timestamp": iso(dt),
        "date": dt.date().isoformat(),
        "time": dt.strftime("%H:%M:%S"),
        "nav": round(nav, 2),
        "cash": round(float(state.get("cash", 0.0)), 2),
        "marketValue": round(mv, 2),
        "positionCount": len(state.get("positions", {})),
        "fundUnits": accounting.get("fundUnits"),
        "unitNav": round(unit_nav, 8),
        "cumulativeNav": round(unit_nav, 8),
        "cumulativeReturnPct": round((unit_nav - 1) * 100, 4),
        "radarCapturedAt": radar.get("capturedAt"),
    }
    hist = state.setdefault("navHistory", [])
    hist.append(nav_point)
    if len(hist) > 6000:
        state["navHistory"] = hist[-6000:]
    # Keep bounded operational controls while retaining all actual decisions.
    controls = state.get("executionControl") or {}
    state["executionControl"] = {k: controls[k] for k in sorted(controls)[-40:]}

    get_daily_control(state, dt.date().isoformat())["lastDecisionAt"] = iso(dt)
    state["updatedAt"] = iso(dt)
    state["strategyVersion"] = STRATEGY_VERSION
    latest = build_latest(state, ledger, prices, radar)

    if trading_session(dt) and not radar_fresh:
        cycle_status = "BLOCKED_STALE_RADAR"
        cycle_reason = f"后台已运行，但雷达超过{RADAR_MAX_AGE_SECONDS // 60}分钟，拒绝使用旧信号交易"
    elif not trading_session(dt):
        cycle_status = "OUTSIDE_SESSION"
        cycle_reason = "后台已运行；当前不在A股交易时段，仅更新净值与健康状态"
    elif actions:
        cycle_status = "TRADED"
        cycle_reason = f"后台自动模拟成交{len(actions)}笔"
    else:
        cycle_status = "NO_ACTION"
        cycle_reason = "后台已完成本轮检查，但目标权重变化未达到交易阈值"
    automation = record_automation_cycle(
        cycle_status, cycle_reason, dt, radar=radar, state=state, ledger=ledger, actions=actions
    )
    latest["automation"] = automation
    latest["capitalMigrationThisCycle"] = capital_event
    latest["dataFreshness"] = {
        "radarFresh": radar_fresh,
        "radarAgeSeconds": round(radar_age, 1) if radar_age is not None else None,
        "maxAllowedAgeSeconds": RADAR_MAX_AGE_SECONDS,
    }

    write_json(STATE_PATH, state)
    write_json(LEDGER_PATH, ledger)
    write_json(LATEST_PATH, latest)

    print(json.dumps({
        "state": "updated",
        "time": iso(dt),
        "session": trading_session(dt),
        "actions": len(actions),
        "buys": sum(1 for a in actions if a.get("side") == "BUY"),
        "sells": sum(1 for a in actions if a.get("side") == "SELL"),
        "positions": len(state.get("positions", {})),
        "nav": round(nav, 2),
        "cash": round(float(state.get("cash", 0.0)), 2),
    }, ensure_ascii=False))
    return 0


def main() -> int:
    try:
        return _main_impl()
    except Exception as exc:
        record_automation_cycle(
            "ERROR", "后台自动模拟交易引擎运行失败，已明确停止本轮交易", now_cn(), error=str(exc)[:300]
        )
        print(json.dumps({"state": "error", "error": str(exc), "time": iso()}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
