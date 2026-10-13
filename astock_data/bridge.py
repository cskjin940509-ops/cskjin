# -*- coding: utf-8 -*-
"""Drop-in offline replacement for the online kline fetch used by the cskjin
backtest pipeline.

tools/update_strategy_backtest.py currently pulls per-symbol daily bars from
Tencent/Eastmoney over the network. This module reproduces the exact contract
that pipeline expects -- a list of ``{date, open, close, high, low, amount}``
ascending, forward-adjusted, most-recent-``limit`` bars -- but serves it from
the local Alpha Rank parquet with no network dependency.

Usage (zero change to existing scripts):

    from astock_data.bridge import patch_module
    import update_strategy_backtest as usb
    patch_module(usb)          # usb.fetch_kline now reads locally

Or, to keep the online path but add a point-in-time knob:

    from astock_data.bridge import local_fetch_kline
    rows = local_fetch_kline("600519", 620, end="2026-09-30")

Rules of thumb:
- Code ``000300`` (and any known index in INDEX_BARE) resolves to
  ``jq_index_daily``; every other 6-char code resolves to ``jq_daily``.
- ``adjust`` defaults to ``qfq`` to match the Tencent qfq feed; pass ``hfq``
  or ``none`` to get post-adjusted / raw prices.
- ``end`` is optional; omit it to read up to the latest partition.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:  # pragma: no cover
    import astock_data.store as _store

from .mapping import INDEX_BARE, to_bare
from .store import DataFoundation, ParquetStore

DEFAULT_LIMIT = 620


def _store_for(store: Optional[ParquetStore]) -> ParquetStore:
    return store if store is not None else DataFoundation().store


def local_fetch_kline(
    code: str,
    limit: int = DEFAULT_LIMIT,
    end: Optional[str] = None,
    adjust: str = "qfq",
    store: Optional[ParquetStore] = None,
) -> list[dict]:
    """Local replacement for tools/update_strategy_backtest.fetch_kline.

    Returns ascending ``[{date, open, close, high, low, amount}]`` for a stock
    or index. Index codes are routed to ``jq_index_daily``; ordinary codes to
    ``jq_daily`` with the requested adjustment.
    """
    s = _store_for(store)
    bare = to_bare(code)
    if bare in INDEX_BARE:
        return s.get_index_kline(bare, limit=limit, end=end)
    return s.get_kline(bare, limit=limit, end=end, adjust=adjust)


def make_provider(
    store: Optional[ParquetStore] = None,
    default_end: Optional[str] = None,
    adjust: str = "qfq",
) -> Callable[..., list[dict]]:
    """Factory returning a fetch_kline-compatible callable.

    The returned function accepts ``(code, limit=620)`` -- the exact signature
    of the online fetch_kline -- and always bounds its read to ``default_end``
    when given, giving you a point-in-time view without touching the script.
    """

    def _provider(code: str, limit: int = DEFAULT_LIMIT) -> list[dict]:
        return local_fetch_kline(code, limit, end=default_end,
                                 adjust=adjust, store=store)

    return _provider


def patch_module(module, default_end: Optional[str] = None,
                adjust: str = "qfq") -> Callable[..., list[dict]]:
    """Monkeypatch ``module.fetch_kline`` to the local provider. Returns the
    provider so it can be restored later. Existing scripts only need to add:

        from astock_data.bridge import patch_module
        patch_module(update_strategy_backtest)
    """
    provider = make_provider(default_end=default_end, adjust=adjust)
    original = getattr(module, "fetch_kline", None)
    module.fetch_kline = provider
    if hasattr(module, "_original_fetch_kline"):
        delattr(module, "_original_fetch_kline")
    module._original_fetch_kline = original
    return provider


def restore_module(module) -> Optional[Callable[..., list[dict]]]:
    """Undo patch_module(). Returns the original fetch_kline (or None)."""
    original = getattr(module, "_original_fetch_kline", None)
    if original is not None:
        module.fetch_kline = original
        delattr(module, "_original_fetch_kline")
    return original


if __name__ == "__main__":  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser(description="Offline kline provider demo")
    parser.add_argument("code", help="6-char code or known index")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--end", default=None)
    args = parser.parse_args()

    rows = local_fetch_kline(args.code, limit=args.limit + 5, end=args.end)
    print(f"{args.code}: last {min(args.limit, len(rows))} of {len(rows)} bars "
          f"({rows[-1]['date'] if rows else 'NA'})")
    for r in rows[-args.limit:]:
        print("  ", r)
