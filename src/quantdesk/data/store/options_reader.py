# src/quantdesk/data/store/options_reader.py
from __future__ import annotations

from pathlib import Path
from typing import Optional
import pandas as pd

from quantdesk.config import settings

def _root(base_dir: Optional[Path] = None) -> Path:
    return (base_dir or settings.parquet_dir) / "options" / "yahoo"

def list_asofs(symbol: str, base_dir: Optional[Path] = None) -> list[str]:
    r = _root(base_dir) / symbol.upper()
    if not r.exists():
        return []
    return sorted([p.name for p in r.iterdir() if p.is_dir()])

def list_expirations(symbol: str, asof: str, base_dir: Optional[Path] = None) -> list[str]:
    d = _root(base_dir) / symbol.upper() / asof
    if not d.exists():
        return []
    return sorted([p.stem for p in d.glob("*.parquet")])

def load_chain(symbol: str, expiration: str, asof: Optional[str] = None, base_dir: Optional[Path] = None) -> pd.DataFrame:
    sym = symbol.upper()
    root = _root(base_dir) / sym
    if asof is None:
        asofs = list_asofs(sym, base_dir=base_dir)
        if not asofs:
            raise FileNotFoundError(f"No as-of partitions for {sym} under {root}")
        asof = asofs[-1]  # latest
    p = root / asof / f"{expiration}.parquet"
    if not p.exists():
        raise FileNotFoundError(f"Chain not found: {p}")
    df = pd.read_parquet(p)
    # Ensure schema
    expected = {"symbol","asof","expiration","type","contract","last_trade","strike","last","bid","ask","mid","volume","open_interest","iv","in_the_money","spot_hint"}
    missing = expected - set(df.columns)
    for m in missing:
        df[m] = None
    # sort
    df = df.sort_values(["type","strike"]).reset_index(drop=True)
    return df
