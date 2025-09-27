from fastapi import FastAPI, Query
from pydantic import BaseModel
from typing import Literal, Optional
from quantdesk.analytics.options.black_scholes import bs_price, greeks, implied_volatility
from quantdesk.analytics.rates.bootstrapping import discount_factor, forward_rate
from quantdesk.logging_conf import setup_logging
from quantdesk.config import settings
from quantdesk.data.store.treasury_reader import load_curve
from quantdesk.analytics.rates.zero_curve import make_curve_from_cc_points, dv01_zero
setup_logging(settings.log_level)

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