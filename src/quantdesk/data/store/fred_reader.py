# src/quantdesk/data/store/fred_reader.py
from __future__ import annotations

from pathlib import Path
from typing import Optional
import pandas as pd

from quantdesk.config import settings

def _single_path(series_id: str, base_dir: Optional[Path] = None) -> Path:
    base = (base_dir or settings.parquet_dir) / "macro" / "fred" / f"{series_id}.parquet"
    return base

def _partition_dir(series_id: str, base_dir: Optional[Path] = None) -> Path:
    return (base_dir or settings.parquet_dir) / "macro" / "fred" / series_id

def load_series(series_id: str, base_dir: Optional[Path] = None) -> pd.DataFrame:
    """
    Load a FRED series from either a single parquet file:
        <base>/macro/fred/<series_id>.parquet
    or partitioned directory:
        <base>/macro/fred/<series_id>/YYYY/MM/DD.parquet
    Returns a tidy df with ['series_id','date','value',...]
    """
    p_single = _single_path(series_id, base_dir)
    p_part = _partition_dir(series_id, base_dir)

    if p_single.exists():
        df = pd.read_parquet(p_single)
    else:
        # collect all parquets if partitioned
        if not p_part.exists():
            raise FileNotFoundError(f"FRED series not found: {series_id} under {p_part}")
        dfs = []
        for p in p_part.rglob("*.parquet"):
            dfs.append(pd.read_parquet(p))
        if not dfs:
            raise FileNotFoundError(f"No parquet files under {p_part}")
        df = pd.concat(dfs, ignore_index=True)

    if "date" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["date"]):
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    return df.sort_values("date").reset_index(drop=True)
