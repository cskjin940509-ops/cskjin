# -*- coding: utf-8 -*-
"""Data-foundation configuration.

Points every other module at the Alpha Rank parquet export and exposes the
dataset manifest. The root is resolved from the environment so the module
stays portable across machines; nothing hard-codes an absolute path here.
"""
from __future__ import annotations

import os
from pathlib import Path

# Default location of the export on this workstation. Override with
# ALPHA_RANK_DATA_ROOT when the archive lives elsewhere.
_DEFAULT_ROOT = "E:/天翼云盘/天翼云盘下载/量化数据/alpha_rank_export"

# Daily-frequency datasets: one parquet per trading day, hive partition `date`.
DAILY_DATASETS = (
    "jq_daily",
    "jq_valuation",
    "jq_indicator",
    "jq_balance",
    "jq_cash_flow",
    "jq_income",
)

# 2020-onward datasets (minute bars, extra funds/industry, indices).
EXTENDED_DATASETS = (
    "jq_minute",
    "jq_extra",
    "jq_index_daily",
    "jq_index_comp",
)

# Single-file / special datasets.
SINGLE_DATASETS = ("stock_list",)

ALL_DATASETS = DAILY_DATASETS + EXTENDED_DATASETS + SINGLE_DATASETS


def data_root() -> Path:
    """Resolve the export root directory."""
    override = os.getenv("ALPHA_RANK_DATA_ROOT", "").strip()
    root = Path(override) if override else Path(_DEFAULT_ROOT)
    if not root.is_dir():
        raise FileNotFoundError(
            f"alpha_rank_export not found at {root}; set ALPHA_RANK_DATA_ROOT "
            "to the export directory"
        )
    return root


def dataset_path(name: str) -> Path:
    """Directory (or single file for trade_dates) backing a dataset."""
    root = data_root()
    if name == "trade_dates":
        return root / "trade_dates.parquet"
    if name not in ALL_DATASETS:
        raise KeyError(f"unknown dataset {name!r}; expected one of {ALL_DATASETS}")
    return root / name
