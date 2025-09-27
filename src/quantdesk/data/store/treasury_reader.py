from __future__ import annotations

from pathlib import Path
from typing import Optional
import pandas as pd

from quantdesk.config import settings


def _partition_path(date_str: str, base_dir: Optional[Path] = None) -> Path:
    """Return partition path for a given date.

    Tries both:
      <base>/treasury/par_yield/YYYY/MM/DD.parquet
      <base>/curated/treasury/par_yield/YYYY/MM/DD.parquet

    This accommodates tests or environments that store under a 'curated' subdir.
    """
    base = (base_dir or settings.parquet_dir)
    y, m, d = date_str.split("-")
    p1 = (base / "treasury" / "par_yield" / y / m / f"{d}.parquet")
    if p1.exists():
        return p1
    p2 = (base / "curated" / "treasury" / "par_yield" / y / m / f"{d}.parquet")
    return p2


def load_curve(date_str: str, base_dir: Optional[Path] = None) -> pd.DataFrame:
    """Load a day's Treasury par yield curve (partitioned parquet).

    Returns a DataFrame with columns: date, bc_code, tenor_years, par_yield_pct, cc_rate_approx, source
    Raises FileNotFoundError if the partition is missing.

    """
    p = _partition_path(date_str, base_dir)
    if not p.exists():
        raise FileNotFoundError(f"Treasury curve file not found for {date_str}: {p}")
    df = pd.read_parquet(p)
    # Ensure sorting by tenor for convenience
    if not df.empty and "tenor_years" in df.columns:
        df = df.sort_values(["tenor_years"]).reset_index(drop=True)
    return df
 

from datetime import date, timedelta

def iter_dates(start: str, end: str):
    """Yield date strings YYYY-MM-DD from start..end inclusive."""
    d0 = date.fromisoformat(start)
    d1 = date.fromisoformat(end)
    if d1 < d0:
        raise ValueError("end < start")
    d = d0
    one = timedelta(days=1)
    while d <= d1:
        yield d.isoformat()
        d += one

def load_curve_or_none(date_str: str, base_dir: Optional[Path] = None) -> pd.DataFrame | None:
    """Load a curve if the partition exists; otherwise return None."""
    p = _partition_path(date_str, base_dir)
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    if not df.empty and "tenor_years" in df.columns:
        df = df.sort_values(["tenor_years"]).reset_index(drop=True)
    return df

def history_by_tenor(tenor_years: float, start: str, end: str, base_dir: Optional[Path] = None) -> pd.DataFrame:
    """Return a time series for a given tenor over [start,end].
    Columns: date, par_yield_pct, cc_rate_approx
    Missing days are skipped (e.g., weekends/holidays).
    """
    rows = []
    for ds in iter_dates(start, end):
        df = load_curve_or_none(ds, base_dir=base_dir)
        if df is None:  # no file for that day
            continue
        hit = df.loc[(df["tenor_years"] == tenor_years)]
        if not hit.empty:
            y = float(hit.iloc[0]["par_yield_pct"])
            cc = float(hit.iloc[0]["cc_rate_approx"])
            rows.append({"date": ds, "par_yield_pct": y, "cc_rate_approx": cc})
    import pandas as pd
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values("date").reset_index(drop=True)
    return out
