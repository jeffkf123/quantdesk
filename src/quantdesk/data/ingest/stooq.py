# src/quantdesk/data/ingest/stooq.py
from __future__ import annotations

import argparse
import datetime as dt
import io
import os
from typing import Iterable, List, Optional, Tuple, Dict

import httpx
import pandas as pd

# Stooq CSV daily endpoint: https://stooq.com/q/d/l/?s=<symbol>&i=d
STOOQ_DAILY_URL = "https://stooq.com/q/d/l/"

def _normalize_symbol(sym: str) -> str:
    """
    Stooq expects lowercase symbols, often with a market suffix for US stocks/ETFs:
      e.g., spy.us, aapl.us
    If user provides 'SPY' or 'AAPL', we'll map to 'spy.us'/'aapl.us'.
    If they pass 'spy.us' already, we keep it.
    """
    s = sym.strip().lower()
    if "." not in s:
        # assume US listing if not specified
        s = f"{s}.us"
    return s

def fetch_daily_csv(symbol: str, client: Optional[httpx.Client] = None) -> pd.DataFrame:
    """
    Download daily OHLCV CSV for a single symbol from Stooq.
    Returns tidy DataFrame with columns:
      ['symbol','date','open','high','low','close','volume','adjusted_close']
    Note: Stooq's 'Close' is already adjusted for splits/dividends in many cases;
          to be safe, we expose 'adjusted_close' equal to 'close' for now.
    """
    close_client = False
    if client is None:
        client = httpx.Client(timeout=20.0, headers={"user-agent": "quantdesk/0.1 stooq"})
        close_client = True
    try:
        sym = _normalize_symbol(symbol)
        params = {"s": sym, "i": "d"}
        r = client.get(STOOQ_DAILY_URL, params=params)
        r.raise_for_status()
        content = r.content.decode("utf-8", errors="ignore")
        if not content or "Date,Open,High,Low,Close,Volume" not in content:
            # stooq returns empty CSV for unknown symbols
            return pd.DataFrame(columns=["symbol","date","open","high","low","close","volume","adjusted_close"])
        df = pd.read_csv(io.StringIO(content))
        if df.empty:
            return pd.DataFrame(columns=["symbol","date","open","high","low","close","volume","adjusted_close"])
        # Normalize
        df.rename(columns={c: c.lower() for c in df.columns}, inplace=True)
        df["symbol"] = sym
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        df["adjusted_close"] = df["close"].astype("float64")
        cols = ["symbol","date","open","high","low","close","volume","adjusted_close"]
        df = df[cols].sort_values("date").reset_index(drop=True)
        return df
    finally:
        if close_client:
            client.close()

def fetch_many(symbols: Iterable[str]) -> pd.DataFrame:
    """
    Fetch a small batch of symbols sequentially (simple & robust).
    """
    rows = []
    with httpx.Client(timeout=20.0, headers={"user-agent": "quantdesk/0.1 stooq"}) as client:
        for s in symbols:
            df = fetch_daily_csv(s, client=client)
            if not df.empty:
                rows.append(df)
    if not rows:
        return pd.DataFrame(columns=["symbol","date","open","high","low","close","volume","adjusted_close"])
    return pd.concat(rows, ignore_index=True)

def write_parquet(df: pd.DataFrame, out: str) -> None:
    if df.empty:
        raise ValueError("No data to write.")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    df.to_parquet(out, index=False)

def write_partitioned(df: pd.DataFrame, out_dir: str) -> list[str]:
    """
    Partition by symbol/date: <out_dir>/<symbol>/YYYY/MM/DD.parquet
    """
    if df.empty:
        raise ValueError("No data to write.")
    paths: list[str] = []
    for sym, gsym in df.groupby("symbol"):
        base = os.path.join(out_dir, sym)
        for d, g in gsym.groupby("date"):
            p = os.path.join(base, f"{d.year:04d}", f"{d.month:02d}", f"{d.day:02d}.parquet")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            g.to_parquet(p, index=False)
            paths.append(p)
    return paths

def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ingest daily OHLCV from Stooq (free).")
    p.add_argument("--symbols", required=True, help="Comma-separated list, e.g. SPY,AAPL or spy.us,aapl.us")
    out = p.add_mutually_exclusive_group(required=True)
    out.add_argument("--out", help="Write single Parquet file")
    out.add_argument("--out-dir", help="Write partitioned Parquet under this directory")
    p.add_argument("--show-summary", action="store_true")
    return p.parse_args(argv)

def main(argv: Optional[List[str]] = None) -> None:
    ns = _parse_args(argv)
    syms = [s.strip() for s in ns.symbols.split(",") if s.strip()]
    df = fetch_many(syms)
    if df.empty:
        raise SystemExit("No data fetched.")
    if ns.out:
        write_parquet(df, ns.out)
    else:
        write_partitioned(df, ns.out_dir)
    if ns.show_summary:
        print(f"Fetched symbols: {sorted(set(df['symbol']))}")
        print(df.groupby('symbol').size().head())
        print(df.tail(5))
if __name__ == "__main__":
    main()
