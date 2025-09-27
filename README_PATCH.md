
Patch: Treasury Ingestor
=========================
This patch adds `src/quantdesk/data/ingest/treasury.py` and tests.

Usage:
------
python -m quantdesk.data.ingest.treasury --start 2025-08-01 --end 2025-08-10 --out data/treasury.parquet

Testing:
--------
pytest -q tests/test_treasury_parser.py

Generated 2025-08-30T18:01:26.241836Z
