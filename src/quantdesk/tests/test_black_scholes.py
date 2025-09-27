from math import isclose
from quantdesk.analytics.options.black_scholes import bs_price, implied_volatility, greeks

def test_call_price_and_iv_roundtrip():
    S, K, r, q, T, sigma = 100.0, 100.0, 0.01, 0.0, 1.0, 0.20
    price = bs_price(S,K,r,q,T,sigma,"call")
    assert isclose(price, 8.4333, rel_tol=1e-3, abs_tol=1e-3)
    iv = implied_volatility(price, S,K,r,q,T,"call")
    assert isclose(iv, sigma, rel_tol=1e-3, abs_tol=1e-3)

def test_put_call_parity_delta_sign():
    S, K, r, q, T, sigma = 100.0, 95.0, 0.02, 0.0, 0.5, 0.25
    gc = greeks(S,K,r,q,T,sigma,"call")
    gp = greeks(S,K,r,q,T,sigma,"put")
    assert gc["delta"] > 0
    assert gp["delta"] < 0
