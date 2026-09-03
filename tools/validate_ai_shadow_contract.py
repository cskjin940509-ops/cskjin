#!/usr/bin/env python3
"""Validate the persisted cloud shadow-account payload before publication."""
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PORTFOLIO = ROOT / "astock_ai_portfolio"
EXPECTED_CAPITAL = 20_000_000.0


def load(name: str):
    return json.loads((PORTFOLIO / name).read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    try:
        state = load("state.json")
        latest = load("latest.json")
        ledger = load("ledger.json")
        automation = load("automation.json")
        cycles = load("cycle_log.json")
        summary = latest.get("summary") or {}

        require(isinstance(state, dict), "state.json must be an object")
        require(isinstance(latest, dict), "latest.json must be an object")
        require(isinstance(ledger, list), "ledger.json must be an array")
        require(isinstance(cycles, list) and cycles, "cycle_log.json must contain a heartbeat")
        require(float(state.get("initialCapital") or 0) == EXPECTED_CAPITAL, "state capital is not 20M")
        require(float(summary.get("capitalCapacity") or 0) == EXPECTED_CAPITAL, "summary capital is not 20M")
        require(float(automation.get("capitalCapacity") or 0) == EXPECTED_CAPITAL, "automation capital is not 20M")
        require(automation.get("enabled") is True, "background automation is disabled")
        require(automation.get("executionMode") == "SIMULATED_ONLY", "execution mode is not simulated-only")
        require(automation.get("brokerConnected") is False, "broker must remain disconnected")
        require(automation.get("appRequired") is False, "backend must not require the app")
        incident = automation.get("knownIncident") or {}
        require(incident.get("type") == "MISSING_BACKEND_CYCLES", "known execution gap is not disclosed")
        require(incident.get("backfilledTrades") is False, "historical gap must not contain invented fills")
        require(automation.get("status") in {
            "TRADED", "NO_ACTION", "OUTSIDE_SESSION", "BLOCKED_NO_RADAR", "BLOCKED_STALE_RADAR"
        }, "unexpected automation status")

        ids = [str(x.get("decisionId") or "") for x in ledger]
        require(all(ids), "ledger contains an empty decisionId")
        require(len(ids) == len(set(ids)), "ledger contains duplicate decisionIds")
        require(all(x.get("simulated") is True for x in ledger), "ledger contains a non-simulated fill")
        require(all(x.get("side") in {"BUY", "SELL"} for x in ledger), "ledger contains an invalid side")
        require(float(state.get("cash") or 0) >= -0.01, "cash is negative")

        positions = state.get("positions") or {}
        require(isinstance(positions, dict), "positions must be an object")
        require(all(int(x.get("qty") or 0) >= 0 for x in positions.values()), "negative position quantity")
        require(int(automation.get("ledgerDecisionCount") or 0) == len(ledger), "automation ledger count mismatch")
        require(int(automation.get("positionCount") or 0) == len(positions), "automation position count mismatch")

        print(json.dumps({
            "ok": True,
            "capitalCapacity": EXPECTED_CAPITAL,
            "ledgerDecisions": len(ledger),
            "positions": len(positions),
            "automationStatus": automation.get("status"),
            "lastRunAt": automation.get("lastRunAt"),
        }, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
