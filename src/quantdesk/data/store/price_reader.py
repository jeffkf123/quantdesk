# src/quantdesk/data/store/price_reader.py
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional, List, Dict
import pandas as pd

from quantdesk.config import settings

def _single_prices_path(base_dir: Optional[Path]) -> Path:
    return (base_dir or settings.parquet_dir) / "prices" / "stooq_daily.parquet"

def _partition_root(base_dir: Optional[Path]) -> Path:
    return (base_dir or settings.parquet_dir) / "prices" / "stooq_daily"

def load_price_series(symbol: str, base_dir: Optional[Path] = None) -> pd.DataFrame:
    """
    Load a single symbol from either:
      <base>/prices/stooq_daily.parquet (wide storage)
    or partitioned:
      <base>/prices/stooq_daily/<symbol>/YYYY/MM/DD.parquet
    Returns tidy: ['symbol','date','open','high','low','close','volume','adjusted_close']
    """
    sym = symbol.strip().lower() if "." in symbol else f"{symbol.strip().lower()}.us"
    p_single = _single_prices_path(base_dir)
    p_part = _partition_root(base_dir) / sym

    if p_single.exists():
        df = pd.read_parquet(p_single)
        df = df[df["symbol"] == sym]
    else:
        # walk partitions
        if not p_part.exists():
            raise FileNotFoundError(f"Price data not found for {sym} under {p_part}")
        dfs = [pd.read_parquet(p) for p in p_part.rglob("*.parquet")]
        df = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

    if df.empty:
        return df
    df = df.sort_values("date").reset_index(drop=True)
    return df

def compute_returns(df: pd.DataFrame, adjusted: bool = True) -> pd.DataFrame:
    """
    Adds 'ret_1d' (simple return) column.
    """
    if df.empty:
        return df
    px = df["adjusted_close"] if adjusted else df["close"]
    rets = px.astype("float64").pct_change()
    out = df.copy()
    out["ret_1d"] = rets
    return out
