# -*- coding: utf-8 -*-
"""Security-code and index-code mapping across the three code conventions the
project already uses:

- JoinQuant:  ``000001.XSHE`` / ``600000.XSHG`` / index ``000300.XSHG``
- Tushare:    ``000001.SZ``   / ``600000.SH``  / ``000300.SH`` (index ``.SH``)
- bare 6-char:``000001``

The backtest pipeline (``tools/update_strategy_backtest.py``) keys everything
by the bare 6-char code and infers the exchange from the leading digit, so the
bare code is the canonical join key inside this project.
"""
from __future__ import annotations

# JoinQuant -> Tushare exchange suffix
_JQ2TS = {"XSHE": "SZ", "XSHG": "SH", "XBJE": "BJ"}
_TS2JQ = {v: k for k, v in _JQ2TS.items()}

# Index set that resolves to tushare index asset; keep a stable lookup.
INDEX_BARE = {
    "000016": "000016.SH",  # SSE 50
    "000300": "000300.SH",  # CSI 300
    "000852": "000852.SH",  # CSI 1000
    "000905": "000905.SH",  # CSI 500
    "000906": "000906.SH",  # CSI 800
    "000985": "000985.SH",  # CSI All
    "399311": "399311.SZ",  # CN 1000
    "399303": "399303.SZ",  # CN 2000
}


def to_bare(code: str) -> str:
    """Any convention -> bare 6-char code."""
    code = str(code).strip().split(".")[0]
    return code


def exchange_of(bare: str) -> str:
    """Infer tushare exchange suffix from the leading digit (stock rule,
    matches tools/tushare_stock_api.ts_code). Indexes are resolved separately
    via to_tushare() through INDEX_BARE, so this only handles ordinary stocks."""
    bare = to_bare(bare)
    if bare.startswith(("5", "6")):
        return "SH"
    if bare.startswith(("8", "9")):
        return "BJ"
    return "SZ"


def to_tushare(code: str, exchange: str | None = None) -> str:
    """Any convention -> tushare code (``000001.SZ`` / ``600000.SH``)."""
    bare = to_bare(code)
    if bare in INDEX_BARE:
        return INDEX_BARE[bare]
    if exchange:
        return bare + "." + exchange.upper()
    return bare + "." + exchange_of(bare)


def to_joinquant(code: str) -> str:
    """Any convention -> JoinQuant code (``000001.XSHE``)."""
    ts = to_tushare(code)
    bare, suffix = ts.split(".")
    return bare + "." + _TS2JQ.get(suffix, suffix)


def index_to_jq(index_bare: str) -> str:
    """Index bare code -> JoinQuant index code (used for parquet lookups)."""
    bare = to_bare(index_bare)
    ts = INDEX_BARE.get(bare)
    if ts is None:
        raise KeyError(f"index {bare!r} not in known index set {sorted(INDEX_BARE)}")
    jq_code = to_joinquant(ts)
    return jq_code
