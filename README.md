# QuantDesk — Desk-Grade Analytics Backend (Skeleton)

A reproducible, test-driven backend that ingests free market data and emits professional, derivable metrics
across asset classes. Focused on the finance/math/programming side (no website).

## Features (initial skeleton)
- **Data layer:** Parquet lake + pluggable connectors (stubs for equities, options, FRED, UST).
- **Analytics:** Returns & realized vol, options Black–Scholes + Greeks + IV, basic zero/forward curve tools.
- **APIs:** FastAPI endpoints for health, option pricing/IV/Greeks, and zero curve utilities.
- **Quality:** Pytest with finite-difference validations, Ruff lint, Mypy types, GitHub Actions CI.
- **Reproducibility:** Docker, Makefile, .env settings, deterministic tests.

> This is a starter you can extend toward the full roadmap (vol surfaces, DV01 ladder, factor models,
> portfolio optimization, event studies, backtests, TCA). The structure anticipates those modules.

## Quickstart

```bash
# 1) Python 3.11+ recommended
python -m venv .venv && source .venv/bin/activate

# 2) Install
pip install -r requirements.txt
pip install -e .

# 3) Lint & test
make lint
make test

# 4) Run API
make api
# -> http://127.0.0.1:8000/docs
```

### With Docker
```bash
docker compose up --build
# -> API available on localhost:8000
```

## Project layout

```
quantdesk/
├── README.md
├── LICENSE
├── pyproject.toml
├── requirements.txt
├── .env.example
├── Makefile
├── docker-compose.yml
├── docker/Dockerfile
├── .github/workflows/ci.yml
└── src/quantdesk
    ├── __init__.py
    ├── config.py
    ├── logging_conf.py
    ├── api/
    │   ├── __init__.py
    │   └── main.py
    ├── data/
    │   ├── __init__.py
    │   ├── schemas.py
    │   ├── ingest/
    │   │   ├── __init__.py
    │   │   ├── base.py
    │   │   ├── equities_yahoo.py
    │   │   ├── fred.py
    │   │   └── treasury.py
    │   └── store/
    │       ├── __init__.py
    │       └── parquet.py
    ├── analytics/
    │   ├── __init__.py
    │   ├── returns.py
    │   ├── options/
    │   │   ├── __init__.py
    │   │   └── black_scholes.py
    │   └── rates/
    │       ├── __init__.py
    │       └── bootstrapping.py
    └── tests/
        ├── __init__.py
        ├── test_black_scholes.py
        └── conftest.py
```

## Roadmap fit
This skeleton aligns with the earlier roadmap: you can plug in new connectors under `data/ingest/`,
add Great Expectations or Pandora/whylogs checks in `data/validation/` (to add), build SVI/SABR
in `analytics/options/`, implement DV01 ladders in `analytics/rates/`, and expand portfolio/factors.

## Licensing
MIT — see `LICENSE`.
