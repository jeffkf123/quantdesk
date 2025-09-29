# src/quantdesk/data/ingest/fred.py
from __future__ import annotations
from .base import Ingestor
import argparse
import datetime as dt
import json
import math
import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import httpx
import pandas as pd


FRED_BASE = "https://api.stlouisfed.org/fred"
# We’ll use the Observations endpoint:
# /fred/series/observations?series_id=ID&observation_start=YYYY-MM-DD&observation_end=YYYY-MM-DD&api_key=...&file_type=json

def _get_api_key() -> str:
    k = os.getenv("FRED_API_KEY") or os.getenv("FRED_API_TOKEN") or ""
    if not k:
        raise RuntimeError("FRED_API_KEY not set in environment.")
    return k

def _coerce_float(x: str | None) -> Optional[float]:
    if x is None:
        return None
    s = str(x).strip()
    if s == "." or s == "":
        return None
    try:
        return float(s)
    except Exception:
        return None

def _compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Assumes a tidy frame with columns: ['date', 'value'] (value as float).
    Adds:
      - value_yoy: 12m pct change (for monthly series).
      - value_3m_ann: 3m annualized pct change (compound).
    We compute only when the frequency looks >= monthly; daily series get NaNs for YoY.
    """
    if df.empty:
        df["value_yoy"] = pd.Series(dtype="float64")
        df["value_3m_ann"] = pd.Series(dtype="float64")
        return df

    out = df.copy()
    out = out.sort_values("date").reset_index(drop=True)

    # Infer frequency by median delta
    if len(out) >= 2:
        deltas = (out["date"].diff().dropna().dt.days).abs()
        med = deltas.median() if not deltas.empty else None
    else:
        med = None

    # Treat <=10 days as "high frequency" (skip YoY), around 30 days as monthly, ~90 days as quarterly
    value = out["value"].astype("float64")
    out["value_yoy"] = pd.Series([math.nan] * len(out))
    out["value_3m_ann"] = pd.Series([math.nan] * len(out))

    if med is not None and med >= 20:  # monthly or lower freq
        # YoY 12-month change, if enough history
        out["value_yoy"] = (value / value.shift(12) - 1.0) * 100.0

        # 3m annualized (%): ((v/v[-3])^(12/3) - 1)*100
        ratio_3m = value / value.shift(3)
        out["value_3m_ann"] = (ratio_3m ** (12.0 / 3.0) - 1.0) * 100.0

    return out

def fetch_series(series_id: str, start: dt.date, end: dt.date, client: Optional[httpx.Client] = None) -> pd.DataFrame:
    """
    Fetch a single FRED series' observations into a tidy DataFrame with:
    ['series_id','date','value'] where date is datetime64[ns] (normalized to date).
    """
    key = _get_api_key()
    close_client = False
    if client is None:
        client = httpx.Client(timeout=30.0, headers={"user-agent": "quantdesk/0.1 fred ingestor"})
        close_client = True
    try:
        url = f"{FRED_BASE}/series/observations"
        params = {
            "series_id": series_id,
            "observation_start": start.isoformat(),
            "observation_end": end.isoformat(),
            "api_key": key,
            "file_type": "json",
        }
        r = client.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        obs = data.get("observations", [])
        rows = []
        for o in obs:
            ds = o.get("date")
            v = _coerce_float(o.get("value"))
            if ds is None:
                continue
            # Normalize 'date' to date
            try:
                d = pd.to_datetime(ds).date()
            except Exception:
                continue
            rows.append({"series_id": series_id, "date": pd.Timestamp(d), "value": v})
        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.sort_values("date").reset_index(drop=True)
        return df
    finally:
        if close_client:
            client.close()

def write_parquet(df: pd.DataFrame, out: str) -> None:
    if df.empty:
        raise ValueError("No data to write.")
    out_dir = os.path.dirname(out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    df.to_parquet(out, index=False)

def write_partitioned(df: pd.DataFrame, out_dir: str, series_id: str) -> list[str]:
    """
    Partition structure:
      <out_dir>/<series_id>/YYYY/MM/DD.parquet  (one row per observation)
    """
    if df.empty:
        raise ValueError("No data to write.")
    paths: list[str] = []
    base = os.path.join(out_dir, series_id)
    for d, g in df.groupby("date"):
        p = os.path.join(base, f"{d.year:04d}", f"{d.month:02d}", f"{d.day:02d}.parquet")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        g.to_parquet(p, index=False)
        paths.append(p)
    return paths

def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ingest a FRED series into Parquet.")
    p.add_argument("--series", required=True, help="FRED series_id (e.g., CPIAUCSL, PCE, UNRATE, DFF)")
    p.add_argument("--start", required=True, help="YYYY-MM-DD")
    p.add_argument("--end", required=True, help="YYYY-MM-DD")
    out = p.add_mutually_exclusive_group(required=True)
    out.add_argument("--out", help="Single Parquet output path")
    out.add_argument("--out-dir", help="Directory for partitioned parquet (/<series_id>/YYYY/MM/DD.parquet)")
    p.add_argument("--with-features", action="store_true", help="Add YoY and 3m annualized features to the stored file(s)")
    p.add_argument("--show-summary", action="store_true", help="Print a short summary")
    return p.parse_args(argv)

def main(argv: Optional[List[str]] = None) -> None:
    ns = _parse_args(argv)
    start = dt.date.fromisoformat(ns.start)
    end = dt.date.fromisoformat(ns.end)
    df = fetch_series(ns.series, start, end)
    if df.empty:
        raise SystemExit("No observations returned.")

    if ns.with_features:
        df = _compute_features(df)

    if ns.out:
        write_parquet(df, ns.out)
    else:
        write_partitioned(df, ns.out_dir, ns.series)

    if ns.show_summary:
        print(f"Series {ns.series} rows: {len(df):,}")
        print(df.head(8).to_string(index=False))

if __name__ == "__main__":
    main()
