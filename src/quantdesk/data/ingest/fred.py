from __future__ import annotations
from typing import Iterable, Dict
from .base import Ingestor

class FRED(Ingestor):
    """Stub for FRED macro series downloader (use 'fredapi' or HTTP with API key)."""
    def fetch(self, series_id: str, start: str, end: str) -> Iterable[Dict]:
        # TODO: implement API calls to FRED respecting the API terms.
        return []

    def save(self, records: Iterable[Dict]) -> int:
        # TODO: persist to Parquet/Timeseries DB
        return 0
