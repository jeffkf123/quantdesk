from __future__ import annotations
import numpy as np
import pandas as pd

def simple_returns(prices: pd.Series) -> pd.Series:
    return prices.pct_change().dropna()

def log_returns(prices: pd.Series) -> pd.Series:
    return np.log(prices).diff().dropna()

def realized_vol_cc(returns: pd.Series, annualize: int = 252) -> float:
    r = returns.dropna().values
    if r.size == 0:
        return float("nan")
    return float(np.sqrt((r**2).sum() * (annualize / len(r))))
