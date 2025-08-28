from fastapi import FastAPI, Query
from pydantic import BaseModel
from typing import Literal, Optional
from quantdesk.analytics.options.black_scholes import bs_price, greeks, implied_volatility
from quantdesk.analytics.rates.bootstrapping import discount_factor, forward_rate
from quantdesk.logging_conf import setup_logging
from quantdesk.config import settings

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
