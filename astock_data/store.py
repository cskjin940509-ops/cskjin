# -*- coding: utf-8 -*-
"""ParquetStore: the offline, point-in-time data base for the cskjin pipeline.

Design goals:
- No online fetch, no future-function. Every read is a slice of the exported
  hive partitioned parquet (one file per trading day, `date=YYYY-MM-DD`).
- Date range = glob over filenames; column pruning and row filters = pyarrow
  dataset; a small process-wide LRU keeps hot cross-sections resident.
- Output shapes are chosen to drop-in replace the online kline fetch used by
  tools/update_strategy_backtest.py (list of {date, open, close, high, low,
  amount}, ascending, forward-adjusted).
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds

from . import config
from .mapping import INDEX_BARE, to_bare, to_joinquant

_PRICE_COLS = ("open", "high", "low", "close", "volume", "money", "avg")


def _norm_date(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    s = str(value).strip()
    return s[:10] if len(s) >= 10 else s


def _to_pandas(table: pa.Table | None) -> "object":
    import pandas as pd

    if table is None or table.num_rows == 0:
        return pd.DataFrame()
    return table.to_pandas()


class ParquetStore:
    """Read-only slice over the Alpha Rank export."""

    def __init__(self, root: str | Path | None = None, lru_size: int = 64):
        self._root = Path(root) if root else config.data_root()
        if not self._root.is_dir():
            raise FileNotFoundError(f"alpha_rank_export root missing: {self._root}")
        self._lru_size = lru_size
        self._lru: "OrderedDict[str, object]" = OrderedDict()
        self._file_cache: dict[str, list[str]] = {}

    # ------------------------------------------------------------------ files
    def _files_for(self, dataset: str, start: str | None, end: str | None) -> list[str]:
        """Absolute paths of in-range partitions for a hive dataset."""
        key = (dataset, _norm_date(start), _norm_date(end))
        hit = self._file_cache.get((dataset,))
        if hit is None:
            base = self._root / dataset
            hit = sorted(str(p) for p in base.glob("date=*.parquet"))
            self._file_cache[dataset] = hit
        lo, hi = _norm_date(start), _norm_date(end)
        out = []
        for path in hit:
            d = Path(path).stem[5:]  # 'date=2024-06-19' -> '2024-06-19'
            if lo and d < lo:
                continue
            if hi and d > hi:
                continue
            out.append(path)
        return out

    def _scan(
        self,
        dataset: str,
        start: str | None,
        end: str | None,
        columns: Sequence[str] | None,
        code_filter: Iterable[str] | None,
    ) -> "object":
        files = self._files_for(dataset, start, end)
        if not files:
            import pandas as pd

            return pd.DataFrame(columns=list(columns) if columns else None)
        dset = ds.dataset(files, format="parquet")
        expr = None
        if code_filter:
            jq = [to_joinquant(c) for c in code_filter]
            expr = pc.field("code").isin(jq)
        table = dset.to_table(columns=list(columns) if columns else None, filter=expr)
        return _to_pandas(table)

    # ------------------------------------------------------------ date helpers
    def _cache_get(self, key: str):
        return self._lru.get(key)

    def _cache_put(self, key: str, value) -> None:
        self._lru[key] = value
        self._lru.move_to_end(key)
        while len(self._lru) > self._lru_size:
            self._lru.popitem(last=False)

    def calendar(self, start: str | None = None, end: str | None = None) -> list[str]:
        """Trading dates (YYYY-MM-DD) within range, from the single calendar file."""
        import pandas as pd

        cal = _to_pandas(
            ds.dataset(str(config.dataset_path("trade_dates")), format="parquet").to_table()
        )
        col = "trade_date"
        dates = [str(d)[:10] for d in cal[col]]
        lo, hi = _norm_date(start), _norm_date(end)
        return [d for d in dates if (not lo or d >= lo) and (not hi or d <= hi)]

    def dates_of(self, dataset: str) -> list[str]:
        """All partition dates present for a dataset (ascending)."""
        return [Path(p).stem[5:] for p in self._files_for(dataset, None, None)]

    # ---------------------------------------------------------- single cross
    def cross_section(
        self,
        dataset: str,
        date: str,
        columns: Sequence[str] | None = None,
        codes: Iterable[str] | None = None,
    ) -> "object":
        """One trading-day snapshot (rows = stocks) for a daily dataset."""
        key = f"cs:{dataset}:{_norm_date(date)}:{tuple(columns) if columns else None}:{tuple(codes) if codes else None}"
        hit = self._cache_get(key)
        if hit is not None:
            return hit
        cols = list(columns) if columns else None
        if cols:
            for anchor in ("code", "time"):
                if anchor not in cols:
                    cols.append(anchor)
        out = self._scan(dataset, _norm_date(date), _norm_date(date), cols, codes)
        if not out.empty:
            self._cache_put(key, out)
        return out

    def daily_panel(
        self,
        dataset: str,
        start: str,
        end: str,
        columns: Sequence[str] | None = None,
        codes: Iterable[str] | None = None,
    ) -> "object":
        """Long panel (rows = stock-day) across a date range."""
        cols = list(columns) if columns else None
        if cols:
            for anchor in ("code", "time"):
                if anchor not in cols:
                    cols.append(anchor)
        return self._scan(dataset, start, end, cols, codes)

    # ------------------------------------------------------------------ daily
    def get_daily(
        self,
        codes: Sequence[str],
        start: str,
        end: str,
        adjust: str = "hfq",
        fields: Sequence[str] | None = None,
    ) -> "object":
        """Daily OHLCV panel keyed by (time, code).

        adjust: 'hfq' (default, post-adjusted close_post series), 'none' raw, or
        'qfq' forward-adjusted. fields selects the output columns; defaults to
        OHLCV. Returns rows sorted by (time, code).
        """
        codes = list(dict.fromkeys(codes))
        base = ("open", "high", "low", "close", "volume", "money", "avg")
        requested = list(fields) if fields else list(base)
        need = list(dict.fromkeys(requested + ["factor"]))
        if adjust == "hfq":
            for c in ("open", "high", "low", "close", "avg"):
                need.append(f"{c}_post")
            need.append("volume_post")
        need = list(dict.fromkeys(need))
        df = self.daily_panel("jq_daily", start, end, columns=need, codes=codes)
        if df.empty:
            import pandas as pd

            return pd.DataFrame()

        if adjust == "hfq":
            for c in ("open", "high", "low", "close", "avg"):
                if c in df.columns:
                    df[c] = df.get(f"{c}_post")
            if "volume" in df.columns:
                df["volume"] = df.get("volume_post")
        elif adjust == "qfq":
            # forward-adjust: divide by the last post-adjust factor per code so
            # the most recent bar equals the raw close, matching qfq online feeds.
            last_factor = df.groupby("code")["factor"].transform("last")
            for c in ("open", "high", "low", "close", "avg"):
                if c in df.columns:
                    df[c] = df[c] * df["factor"] / last_factor
        # adjust == 'none' -> leave raw

        out_cols = [c for c in (fields or base) if c in df.columns]
        out_cols += [c for c in ("time", "code") if c in df.columns and c not in out_cols]
        out = df[out_cols].copy()
        out["time"] = out["time"].dt.strftime("%Y-%m-%d")
        out = out.sort_values(["time", "code"])
        return out.reset_index(drop=True)

    # ------------------------------------------------------------------- kline
    def get_kline(
        self,
        code: str,
        limit: int = 620,
        end: str | None = None,
        adjust: str = "qfq",
    ) -> list[dict]:
        """Drop-in replacement for tools/update_strategy_backtest.fetch_kline.

        Returns ascending [{date, open, close, high, low, amount}] where prices
        honour `adjust` ('qfq' default, 'hfq', 'none') and `amount` is raw
        turnover in yuan (money). `limit` keeps the most recent N bars.
        """
        import pandas as pd

        all_dates = self.dates_of("jq_daily")
        if not all_dates:
            return []
        hi = _norm_date(end) or all_dates[-1]
        lo = all_dates[0]
        panel = self.get_daily([code], lo, hi, adjust=adjust,
                               fields=("open", "high", "low", "close", "money"))
        if panel.empty:
            return []
        panel = panel.tail(limit)
        rows = []
        for rec in panel.itertuples(index=False):
            o, c, h, low = rec.open, rec.close, rec.high, rec.low
            if o is None or c is None or pd.isna(o) or pd.isna(c):
                continue
            h = h if (h is not None and not pd.isna(h)) else max(o, c)
            low = low if (low is not None and not pd.isna(low)) else min(o, c)
            amount = rec.money
            if amount is not None and pd.isna(amount):
                amount = None
            rows.append({"date": str(rec.time), "open": float(o), "close": float(c),
                         "high": float(h), "low": float(low),
                         "amount": None if amount is None else float(amount)})
        rows.sort(key=lambda r: r["date"])
        return rows

    # ------------------------------------------------------------------ index
    def get_index_kline(self, index_bare: str, limit: int = 620,
                       start: str | None = None, end: str | None = None) -> list[dict]:
        """Index daily bars from jq_index_daily (forward-adjusted source)."""
        import pandas as pd

        jq = to_joinquant(index_bare if index_bare in INDEX_BARE else to_bare(index_bare))
        panel = self._scan("jq_index_daily", start, end,
                           columns=("date", "index_code", "open", "close", "high", "low",
                                    "volume", "money"),
                           code_filter=None)
        if panel.empty:
            return []
        panel = panel[panel["index_code"] == jq]
        panel = panel.sort_values("date").tail(limit)
        rows = [{"date": str(r.date), "open": float(r.open), "close": float(r.close),
                 "high": float(r.high), "low": float(r.low),
                 "amount": None if pd.isna(r.money) else float(r.money)}
                for r in panel.itertuples(index=False)]
        return rows

    def index_constituents(self, index_bare: str, date: str) -> list[str]:
        """Bare codes of an index's constituents on a given day (latest monthly
        snapshot available on or before `date`)."""
        import pandas as pd

        jq = to_joinquant(index_bare if index_bare in INDEX_BARE else to_bare(index_bare))
        df = self._scan("jq_index_comp", None, _norm_date(date),
                        columns=("date", "index_code", "code", "weight"), code_filter=None)
        if df.empty:
            return []
        df = df[df["index_code"] == jq]
        df = df.sort_values("date")
        day = df[df["date"] <= _norm_date(date)]
        if day.empty:
            return []
        last = day["date"].max()
        return [to_bare(c) for c in day[day["date"] == last]["code"]]

    # ------------------------------------------------------------- stock list
    def stock_list(self, date: str) -> list[str]:
        """All bare A-share codes listed that trading day (incl. suspended,
        not delisted)."""
        import pandas as pd

        df = self._scan("stock_list", _norm_date(date), _norm_date(date),
                        columns=("code",), code_filter=None)
        if df.empty:
            return []
        return [to_bare(c) for c in df["code"]]

    # -------------------------------------------------------------- industries
    def industries(self, codes: Sequence[str], date: str) -> "object":
        """Industry tags (SW/JoinQuant/CSRC levels) for a set of codes on a day.
        Codes not in that day's jq_extra (e.g. not a two-financing target) still
        appear, with null tags."""
        panel = self.cross_section(
            "jq_extra", date,
            columns=("industry_sw_l1", "industry_sw_l2", "industry_sw_l3",
                     "industry_jq_l1", "industry_jq_l2", "industry_zjw"),
            codes=list(codes),
        )
        if panel.empty:
            import pandas as pd

            return pd.DataFrame()
        return panel.set_index("code")

    # ------------------------------------------------------------- two-financing
    def margin(self, codes: Sequence[str], date: str) -> "object":
        """Per-stock two-financing (mtss_*) snapshot for a date. Nulls mean the
        stock had no two-financing data that day, NOT zero."""
        return self.cross_section("jq_extra", date,
                                  columns=("mtss_fin_value", "mtss_sec_value",
                                           "mtss_fin_sec_value"),
                                  codes=list(codes))

    def stock_margin(self, date: str, codes: Sequence[str] | None = None) -> dict:
        """Exchange-published per-stock detail (financing balance/buy/repay,
        BSE included) from the Tushare-proxy supplement. Day-scoped dict
        keyed by bare code; absent codes mean no two-financing record that
        day. Prefer this over jq_extra mtss when BSE or exact repay matters."""
        from . import stock_margin as _sm

        day = _sm.load_day(date)
        if codes:
            from .mapping import to_bare

            day = {to_bare(c): day[to_bare(c)] for c in codes if to_bare(c) in day}
        return day


@dataclass
class DataFoundation:
    """Thin ergonomic wrapper: builds one ParquetStore and re-exposes its API."""

    root: str | None = None
    lru_size: int = 64
    _store: "ParquetStore | None" = None

    def __post_init__(self) -> None:
        self._store = ParquetStore(root=self.root, lru_size=self.lru_size)

    @property
    def store(self) -> ParquetStore:
        return self._store

    def __getattr__(self, item):
        return getattr(self._store, item)
