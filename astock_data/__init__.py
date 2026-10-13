# -*- coding: utf-8 -*-
"""astock_data: offline point-in-time data foundation for the cskjin pipeline.

Expose the store and the ergonomic foundation wrapper at package level so
callers can just do:

    from astock_data import DataFoundation
    df = DataFoundation()
    df.get_kline("600000", 620)
"""
from .config import (ALL_DATASETS, DAILY_DATASETS, EXTENDED_DATASETS,
                     SINGLE_DATASETS, data_root, dataset_path)
from .mapping import (INDEX_BARE, exchange_of, index_to_jq, to_bare,
                      to_joinquant, to_tushare)
from .stock_margin import (available_dates, cross_source_reconciled,
                           day_audit, load_day)
from .store import DataFoundation, ParquetStore

__all__ = [
    "ParquetStore",
    "DataFoundation",
    "data_root",
    "dataset_path",
    "ALL_DATASETS",
    "DAILY_DATASETS",
    "EXTENDED_DATASETS",
    "SINGLE_DATASETS",
    "to_bare",
    "to_tushare",
    "to_joinquant",
    "index_to_jq",
    "exchange_of",
    "INDEX_BARE",
    "load_day",
    "available_dates",
    "day_audit",
    "cross_source_reconciled",
]
