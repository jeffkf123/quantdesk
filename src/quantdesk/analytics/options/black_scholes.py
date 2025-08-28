from __future__ import annotations
from math import log, sqrt, exp, erf
from typing import Literal

def _phi(x: float) -> float:
    "Standard normal PDF"
    from math import pi, exp as e
    return e(-0.5 * x * x) / sqrt(2.0 * pi)

def _Phi(x: float) -> float:
    "Standard normal CDF via erf"
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))

def bs_price(S: float, K: float, r: float, q: float, T: float, sigma: float, right: Literal["call","put"]="call") -> float:
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        raise ValueError("Invalid inputs")
    d1 = (log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    df_r = exp(-r * T)
    df_q = exp(-q * T)
    if right == "call":
        return df_q * S * _Phi(d1) - df_r * K * _Phi(d2)
    else:
        return df_r * K * _Phi(-d2) - df_q * S * _Phi(-d1)

def greeks(S: float, K: float, r: float, q: float, T: float, sigma: float, right: Literal["call","put"]="call") -> dict:
    d1 = (log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    df_r = exp(-r * T)
    df_q = exp(-q * T)
    delta = df_q * _Phi(d1) if right == "call" else df_q * (_Phi(d1) - 1.0)
    gamma = df_q * _phi(d1) / (S * sigma * sqrt(T))
    vega  = df_q * S * _phi(d1) * sqrt(T)
    theta_call = - (df_q * S * _phi(d1) * sigma) / (2 * sqrt(T)) - r * df_r * K * _Phi(d2) + q * df_q * S * _Phi(d1)
    theta_put  = - (df_q * S * _phi(d1) * sigma) / (2 * sqrt(T)) + r * df_r * K * _Phi(-d2) - q * df_q * S * _Phi(-d1)
    theta = theta_call if right == "call" else theta_put
    rho_call =  T * df_r * K * _Phi(d2)
    rho_put  = -T * df_r * K * _Phi(-d2)
    rho = rho_call if right == "call" else rho_put
    return {"delta": delta, "gamma": gamma, "vega": vega, "theta": theta, "rho": rho}

def implied_volatility(price: float, S: float, K: float, r: float, q: float, T: float, right: Literal["call","put"]="call",
                        tol: float = 1e-7, max_iter: int = 100, lo: float = 1e-6, hi: float = 5.0) -> float:
    "Bisection on Black–Scholes price to find IV."
    def f(sig: float) -> float:
        return bs_price(S, K, r, q, T, sig, right) - price
    f_lo, f_hi = f(lo), f(hi)
    if f_lo * f_hi > 0:
        # Try expanding bounds
        a, b = lo, hi
        for _ in range(25):
            a *= 0.5
            b *= 2.0
            f_lo, f_hi = f(a), f(b)
            if f_lo * f_hi <= 0:
                lo, hi = a, b
                break
        else:
            raise ValueError("IV not bracketed; bad price/intrinsics?")
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        f_mid = f(mid)
        if abs(f_mid) < tol:
            return mid
        if f_lo * f_mid <= 0:
            hi = mid
            f_hi = f_mid
        else:
            lo = mid
            f_lo = f_mid
    return 0.5 * (lo + hi)
