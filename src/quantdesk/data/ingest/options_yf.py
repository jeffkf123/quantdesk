# src/quantdesk/data/ingest/options_yf.py
from __future__ import annotations

import argparse
import datetime as dt
import os
from typing import Iterable, List, Optional, Tuple

import pandas as pd

# We import yfinance lazily inside fetchers, so tests that import this module won't fail without yfinance.

DEFAULT_UNDERLYINGS = ["SPY", "QQQ", "AAPL", "MSFT", "^SPX", "TSLA"]

def _normalize_symbol(sym: str) -> str:
    s = sym.strip().upper()
    # yfinance uses '^SPX' for S&P 500 index, equities/ETFs are plain (no .US needed)
    return s

def _now_date_str() -> str:
    # As-of partition date (UTC)
    return dt.datetime.utcnow().date().isoformat()

def _fetch_one(symbol: str, max_expiries: int | None = 10) -> pd.DataFrame:
    import yfinance as yf  # local import
    ticker = yf.Ticker(_normalize_symbol(symbol))
    expirations = list(ticker.options or [])
    if not expirations:
        return pd.DataFrame()
    if max_expiries is not None:
        expirations = expirations[:max_expiries]
    rows: List[pd.DataFrame] = []
    # current spot (for convenience; can be NaN)
    spot = None
    try:
        info = ticker.fast_info or {}
        spot = info.get("last_price", None)
    except Exception:
        pass
    asof = _now_date_str()
    for expiry in expirations:
        try:
            ch = ticker.option_chain(expiry)
        except Exception:
            continue
        # ch.calls & ch.puts are dataframes
        for opt_df, opt_type in [(ch.calls, "call"), (ch.puts, "put")]:
            if opt_df is None or opt_df.empty:
                continue
            df = opt_df.copy()
            # Normalize common fields
            # yfinance typical columns: contractSymbol, lastTradeDate, strike, lastPrice, bid, ask, change, percentChange, volume, openInterest, impliedVolatility, inTheMoney
            keep = {
                "contractSymbol": "contract",
                "lastTradeDate": "last_trade",
                "strike": "strike",
                "lastPrice": "last",
                "bid": "bid",
                "ask": "ask",
                "volume": "volume",
                "openInterest": "open_interest",
                "impliedVolatility": "iv",
                "inTheMoney": "in_the_money",
            }
            for k in keep:
                if k not in df.columns:
                    df[k] = None
            slim = df[list(keep.keys())].rename(columns=keep)
            slim["symbol"] = _normalize_symbol(symbol)
            slim["asof"] = asof
            slim["expiration"] = expiry
            slim["type"] = opt_type
            # Mid
            slim["mid"] = (pd.to_numeric(slim["bid"], errors="coerce") + pd.to_numeric(slim["ask"], errors="coerce")) / 2.0
            # yfinance IV is in decimals (e.g., 0.20), ensure float
            slim["iv"] = pd.to_numeric(slim["iv"], errors="coerce")
            # coerce numerics
            for col in ["strike", "last", "bid", "ask", "mid", "volume", "open_interest"]:
                slim[col] = pd.to_numeric(slim[col], errors="coerce")
            # dates
            slim["last_trade"] = pd.to_datetime(slim["last_trade"], errors="coerce").dt.tz_localize(None)
            # add spot for convenience (nullable)
            slim["spot_hint"] = spot
            rows.append(slim)
    if not rows:
        return pd.DataFrame()
    out = pd.concat(rows, ignore_index=True)
    out = out.sort_values(["symbol", "expiration", "type", "strike"]).reset_index(drop=True)
    return out

def fetch_many(symbols: Iterable[str], max_expiries: int | None = 10) -> pd.DataFrame:
    rows = []
    for s in symbols:
        df = _fetch_one(s, max_expiries=max_expiries)
        if not df.empty:
            rows.append(df)
    if not rows:
        return pd.DataFrame(columns=[
            "symbol","asof","expiration","type","contract","last_trade",
            "strike","last","bid","ask","mid","volume","open_interest","iv","in_the_money","spot_hint"
        ])
    return pd.concat(rows, ignore_index=True)

def write_partitioned(df: pd.DataFrame, out_dir: str) -> list[str]:
    """
    Partition layout:
      <out_dir>/options/yahoo/<SYMBOL>/<ASOF>/<EXPIRATION>.parquet
    """
    if df.empty:
        raise ValueError("No options data to write.")
    paths: list[str] = []
    base = os.path.join(out_dir, "options", "yahoo")
    for (sym, asof, expiry), g in df.groupby(["symbol","asof","expiration"], dropna=False):
        p = os.path.join(base, sym, asof, f"{expiry}.parquet")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        g.to_parquet(p, index=False)
        paths.append(p)
    return paths

def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ingest options chains via yfinance.")
    p.add_argument("--symbols", default=",".join(DEFAULT_UNDERLYINGS), help="Comma-separated underlyings (e.g., SPY,QQQ,AAPL)")
    p.add_argument("--max-expiries", type=int, default=10, help="Limit number of expirations per underlying")
    p.add_argument("--out-dir", required=True, help="Root directory for partitioned Parquet")
    p.add_argument("--show-summary", action="store_true")
    return p.parse_args(argv)

def main(argv: Optional[List[str]] = None) -> None:
    ns = _parse_args(argv)
    symbols = [x.strip() for x in ns.symbols.split(",") if x.strip()]
    df = fetch_many(symbols, max_expiries=ns.max_expiries)
    if df.empty:
        raise SystemExit("No options data fetched.")
    write_partitioned(df, ns.out_dir)
    if ns.show_summary:
        print(f"Fetched symbols: {sorted(df['symbol'].unique())}")
        print(df.groupby(['symbol','expiration','type']).size().head())
        print(df.head(10).to_string(index=False))

if __name__ == "__main__":
    main()
