from fastapi import FastAPI, Query
from pydantic import BaseModel
from typing import Literal, Optional
from quantdesk.analytics.options.black_scholes import bs_price, greeks, implied_volatility
from quantdesk.analytics.rates.bootstrapping import discount_factor, forward_rate
from quantdesk.logging_conf import setup_logging
from quantdesk.config import settings
from quantdesk.data.store.treasury_reader import load_curve
from quantdesk.data.store.treasury_reader import (
    load_curve,
    iter_dates,
    load_curve_or_none,
)
from quantdesk.analytics.rates.zero_curve import make_curve_from_cc_points, dv01_zero
setup_logging(settings.log_level)
from pathlib import Path
from quantdesk.data.store.price_reader import load_price_series, compute_returns
from quantdesk.data.store.fred_reader import load_series
import pandas as pd
app = FastAPI(title="QuantDesk API", version="0.1.0")

class BSRequest(BaseModel):
    S: float
    K: float
    r: float
    q: float = 0.0
    T: float
    sigma: float
    right: Literal["call", "put"] = "call"

class IVRequest(BaseModel):
    price: float
    S: float
    K: float
    r: float
    q: float = 0.0
    T: float
    right: Literal["call", "put"] = "call"

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}

@app.post("/options/bs")
def options_bs(req: BSRequest) -> dict:
    p = bs_price(req.S, req.K, req.r, req.q, req.T, req.sigma, req.right)
    g = greeks(req.S, req.K, req.r, req.q, req.T, req.sigma, req.right)
    return {"price": p, "greeks": g}

@app.post("/options/iv")
def options_iv(req: IVRequest) -> dict:
    iv = implied_volatility(req.price, req.S, req.K, req.r, req.q, req.T, req.right)
    return {"implied_vol": iv}

@app.get("/rates/df")
def rates_df(t: float = Query(..., description="Maturity in years"), r: float = Query(..., description="Zero rate (annualized, cc)")) -> dict:
    df = discount_factor(r, t)
    return {"t": t, "r": r, "df": df}

@app.get("/rates/fwd")
def rates_fwd(t1: float, t2: float, r1: float, r2: float) -> dict:
    f = forward_rate(t1, t2, r1, r2)
    return {"t1": t1, "t2": t2, "fwd": f}


# --- Treasury curve endpoint (points + spreads) ---
from quantdesk.data.store.treasury_reader import load_curve
from pathlib import Path

def _make_zero_curve_for_date(date: str, base_dir: str | None = None):
    """
    Load the partition for `date`, then fit a log-DF piecewise-linear zero curve
    from cc_rate_approx points. Returns (curve, df_rows) or raises FileNotFoundError.
    """
    df = load_curve(date, base_dir=Path(base_dir) if base_dir else None)
    pts = [
        (float(r["tenor_years"]), float(r["cc_rate_approx"]))
        for _, r in df.iterrows()
        if float(r["tenor_years"]) > 0
    ]
    crv = make_curve_from_cc_points(pts)
    return crv, df

def _to_points(df):
    return [
        {
            "bc_code": r["bc_code"],
            "tenor_years": float(r["tenor_years"]),
            "par_yield_pct": float(r["par_yield_pct"]),
        }
        for _, r in df.iterrows()
    ]

def _spreads(df):
    # Map tenor years to par yields for quick lookup
    by_tenor = {float(r["tenor_years"]): float(r["par_yield_pct"]) for _, r in df.iterrows()}
    out = {}
    # 2s10s: 10y - 2y
    if 10.0 in by_tenor and 2.0 in by_tenor:
        out["2s10s"] = by_tenor[10.0] - by_tenor[2.0]
    # 3m10y: 10y - 3m (0.25y). If 1.5m (0.125y) exists but 3m doesn't, skip for now.
    if 10.0 in by_tenor and 0.25 in by_tenor:
        out["3m10y"] = by_tenor[10.0] - by_tenor[0.25]
    return out

@app.get("/rates/curve")
def rates_curve(date: str, base_dir: str | None = None):
    """Return Treasury par yield curve points and a few standard spreads for the given date.

    - `date`: YYYY-MM-DD (must correspond to an ingested partition)

    Returns: { "date": ..., "points": [...], "spreads": {...} }

    """
    try:
        df = load_curve(date, base_dir=Path(base_dir) if base_dir else None)
    except FileNotFoundError as e:
        return {
            "date": date,
            "points": [],
            "spreads": {},
            "error": str(e),
        }
    return {
        "date": date,
        "points": _to_points(df),
        "spreads": _spreads(df),
    }


# --- Forward rates & history endpoints ---
from quantdesk.data.store.treasury_reader import load_curve, history_by_tenor

def _tenor_map(df):
    return {float(r["tenor_years"]): (float(r["par_yield_pct"]), float(r["cc_rate_approx"])) for _, r in df.iterrows()}

@app.get("/rates/forwards")
def rates_forwards(date: str, pairs: str | None = None, base_dir: str | None = None):
    """Approximate forward rates computed from cc_rate_approx on the par curve.
    - `date`: YYYY-MM-DD
    - `pairs`: semicolon-separated tenor pairs like "2,10;0.25,10" (years)
    Returns: { "date": ..., "forwards": [{"t1":2.0, "t2":10.0, "fwd_cc": ...}], "note": ... }
    NOTE: These forwards use cc_rate_approx (log(1+par/100)). For precise forwards,
    use a bootstrapped zero curve (coming next).
    """
    try:
        df = load_curve(date, base_dir=Path(base_dir) if base_dir else None)
    except FileNotFoundError as e:
        return { "date": date, "forwards": [], "error": str(e) }
    m = _tenor_map(df)

    req_pairs = []
    if pairs:
        for chunk in pairs.split(";"):
            if not chunk.strip():
                continue
            a, b = chunk.split(",")
            t1, t2 = float(a), float(b)
            if t2 <= t1:
                continue
            req_pairs.append((t1, t2))
    else:
        # sensible defaults if not provided
        req_pairs = [(1.0, 2.0), (2.0, 5.0), (5.0, 10.0), (0.25, 10.0)]

    forwards = []
    missing = []
    for t1, t2 in req_pairs:
        if t1 not in m or t2 not in m:
            missing.append((t1, t2))
            continue
        r1 = m[t1][1]  # cc_rate_approx (from par yields)
        r2 = m[t2][1]
        fwd = (r2 * t2 - r1 * t1) / (t2 - t1)  # cc forward (approx from par)
        # Clamp to bracket because par-based cc approximations can drift outside [min(r1,r2)]
        lo, hi = (r1, r2) if r1 <= r2 else (r2, r1)
        if fwd < lo:
            fwd = lo
        elif fwd > hi:
            fwd = hi
        forwards.append({"t1": t1, "t2": t2, "fwd_cc": fwd})
    note = "Forwards computed from cc_rate_approx derived from par yields; use zero curve for precision."
    out = {"date": date, "forwards": forwards, "note": note}
    if missing:
        out["missing_pairs"] = missing
    return out

@app.get("/rates/history")
def rates_history(tenor: float, start: str, end: str, base_dir: str | None = None):
    """Return historical time series for a given tenor in years over [start,end].
    Skips days with no partition (weekends/holidays or missing data).
    Returns: { "tenor": tenor, "series": [{"date":..., "par_yield_pct":..., "cc_rate_approx":...}, ...] }
    """
    df = history_by_tenor(tenor, start, end, base_dir=Path(base_dir) if base_dir else None)
    series = [] if df.empty else [
        {"date": d, "par_yield_pct": float(y), "cc_rate_approx": float(c)}
        for d, y, c in zip(df["date"], df["par_yield_pct"], df["cc_rate_approx"])
    ]
    return {"tenor": tenor, "start": start, "end": end, "series": series}


def _parse_grid(grid: str | None):
    if not grid:
        return [0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 20.0, 30.0]
    out = []
    for x in grid.split(","):
        x = x.strip()
        if not x:
            continue
        out.append(float(x))
    return out

@app.get("/rates/zero")
def rates_zero(date: str, grid: str | None = None, base_dir: str | None = None):
    """Fit log-DF piecewise-linear zero curve from cc_rate_approx points."""
    try:
        df = load_curve(date, base_dir=Path(base_dir) if base_dir else None)
    except FileNotFoundError as e:
        return {"date": date, "grid": [], "zeros_cc": [], "dfs": [], "error": str(e)}
    pts = [(float(r["tenor_years"]), float(r["cc_rate_approx"])) for _, r in df.iterrows() if float(r["tenor_years"]) > 0]
    crv = make_curve_from_cc_points(pts)
    G = _parse_grid(grid)
    zeros = [crv.zero_cc(t) for t in G]
    dfs = [crv.df(t) for t in G]
    return {"date": date, "grid": G, "zeros_cc": zeros, "dfs": dfs, "method": "logdf_piecewise_linear_from_cc_approx"}

@app.get("/rates/dv01")
def rates_dv01(date: str, keys: str | None = None, base_dir: str | None = None):
    """Key-rate DV01 ladder for $1 zeros on selected keys (years)."""
    try:
        df = load_curve(date, base_dir=Path(base_dir) if base_dir else None)
    except FileNotFoundError as e:
        return {"date": date, "keys": [], "dv01": [], "error": str(e)}
    pts = [(float(r["tenor_years"]), float(r["cc_rate_approx"])) for _, r in df.iterrows() if float(r["tenor_years"]) > 0]
    crv = make_curve_from_cc_points(pts)
    K = _parse_grid(keys) if keys else [0.25, 2.0, 5.0, 10.0, 30.0]
    dv = [dv01_zero(t, crv) for t in K]
    return {"date": date, "keys": K, "dv01": dv, "method": "dv01_zero_from_logdf_curve"}




@app.get("/rates/forwards/zero")
def rates_forwards_zero(date: str, pairs: str | None = None, base_dir: str | None = None):
    """
    Precise continuous-compounded forwards computed from the fitted zero curve:
      f_{t1,t2} = (r(t2)*t2 - r(t1)*t1) / (t2 - t1), where r(.) are zero CC rates.
    - date: YYYY-MM-DD
    - pairs: "2,10;0.25,10" (years). If omitted, defaults to common pairs.
    """
    try:
        crv, _ = _make_zero_curve_for_date(date, base_dir)
    except FileNotFoundError as e:
        return {"date": date, "forwards": [], "error": str(e)}

    req_pairs: list[tuple[float, float]] = []
    if pairs:
        for chunk in pairs.split(";"):
            if not chunk.strip():
                continue
            a, b = chunk.split(",")
            t1, t2 = float(a), float(b)
            if t2 > t1:
                req_pairs.append((t1, t2))
    else:
        req_pairs = [(1.0, 2.0), (2.0, 5.0), (5.0, 10.0), (0.25, 10.0)]

    forwards = []
    bad = []
    for t1, t2 in req_pairs:
        try:
            fwd = crv.fwd_cc(t1, t2)
            forwards.append({"t1": t1, "t2": t2, "fwd_cc": fwd})
        except Exception as ex:
            bad.append({"t1": t1, "t2": t2, "error": str(ex)})

    out = {"date": date, "forwards": forwards, "method": "zero_curve_fwd_cc"}
    if bad:
        out["failed_pairs"] = bad
    return out


@app.get("/rates/zero/history")
def rates_zero_history(start: str, end: str, grid: str | None = None, base_dir: str | None = None):
    """
    Return daily zero CC rates (and DFs) evaluated on `grid` for all available days in [start,end].
    Skips missing partitions (e.g., weekends/holidays).
    Response:
      {
        "start": "...", "end": "...", "grid": [...],
        "series": [
          {"date": "YYYY-MM-DD", "zeros_cc": [...], "dfs": [...]},
          ...
        ]
      }
    """
    G = _parse_grid(grid) if "_parse_grid" in globals() else [0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 20.0, 30.0]
    series = []
    for ds in iter_dates(start, end):
        df = load_curve_or_none(ds, base_dir=Path(base_dir) if base_dir else None)
        if df is None or df.empty:
            continue
        pts = [
            (float(r["tenor_years"]), float(r["cc_rate_approx"]))
            for _, r in df.iterrows()
            if float(r["tenor_years"]) > 0
        ]
        try:
            crv = make_curve_from_cc_points(pts)
        except Exception:
            # If the day's points are pathological, skip gracefully
            continue
        zeros = [crv.zero_cc(t) for t in G]
        dfs = [crv.df(t) for t in G]
        series.append({"date": ds, "zeros_cc": zeros, "dfs": dfs})

    return {"start": start, "end": end, "grid": G, "series": series, "method": "logdf_piecewise_linear_from_cc_approx"}


@app.get("/macro/series/{series_id}")
def macro_series(
    series_id: str,
    start: str | None = None,
    end: str | None = None,
    features: bool = True,
    base_dir: str | None = None,
):
    """
    Return a FRED macro series (CPI, PCE, UNRATE, DFF, etc.) with optional features:
      - YoY (%), 12-month change (monthly-like)
      - 3m annualized (%), ((v/v[-3])^(12/3)-1)*100
    Params:
      - start/end: YYYY-MM-DD (optional)
      - features: bool (default True)
      - base_dir: overrides default data root
    """
    df = load_series(series_id, base_dir=Path(base_dir) if base_dir else None)
    if start:
        df = df[df["date"] >= pd.to_datetime(start)]
    if end:
        df = df[df["date"] <= pd.to_datetime(end)]

    # compute features if requested (same logic as ingestor)
    if features:
        # inline feature computation (no hard import of ingestor to avoid cycles)
        value = df["value"].astype("float64")
        out = df.copy()
        out = out.sort_values("date").reset_index(drop=True)
        out["value_yoy"] = (value / value.shift(12) - 1.0) * 100.0
        ratio_3m = value / value.shift(3)
        out["value_3m_ann"] = (ratio_3m ** (12.0 / 3.0) - 1.0) * 100.0
        df = out

    # shape a compact JSON
    series = [
        {
            "date": d.date().isoformat() if hasattr(d, "date") else str(d)[:10],
            "value": None if (pd.isna(v) if v is not None else True) else float(v),
            **(
                {} if not features else {
                    "value_yoy": None if (pd.isna(y) if 'y' in locals() else pd.isna(df.loc[i, 'value_yoy'])) else float(df.loc[i, 'value_yoy']),
                    "value_3m_ann": None if (pd.isna(df.loc[i, 'value_3m_ann'])) else float(df.loc[i, 'value_3m_ann']),
                }
            ),
        }
        for i, (d, v) in enumerate(zip(df["date"], df["value"]))
    ]

    return {
        "series_id": series_id,
        "count": len(series),
        "start": start,
        "end": end,
        "features": features,
        "data": series,
    }


@app.get("/prices/daily")
def prices_daily(
    symbol: str,
    start: str | None = None,
    end: str | None = None,
    adjusted: bool = True,
    base_dir: str | None = None,
):
    """
    Return daily OHLCV for a symbol + 1D returns.
    Symbol format:
      - US stocks/ETFs: 'spy' or 'spy.us' (we normalize to 'spy.us').
    """
    df = load_price_series(symbol, base_dir=Path(base_dir) if base_dir else None)
    if df.empty:
        return {"symbol": symbol, "data": []}
    if start:
        df = df[df["date"] >= pd.to_datetime(start)]
    if end:
        df = df[df["date"] <= pd.to_datetime(end)]
    df = compute_returns(df, adjusted=adjusted)
    data = [
        {
            "date": d.date().isoformat(),
            "open": float(o),
            "high": float(h),
            "low": float(l),
            "close": float(c),
            "volume": None if pd.isna(v) else float(v),
            "adjusted_close": float(ac),
            "ret_1d": None if pd.isna(r) else float(r),
        }
        for d, o, h, l, c, v, ac, r in zip(
            df["date"], df["open"], df["high"], df["low"], df["close"], df["volume"], df["adjusted_close"], df["ret_1d"]
        )
    ]
    return {"symbol": symbol, "adjusted": adjusted, "count": len(data), "data": data}
