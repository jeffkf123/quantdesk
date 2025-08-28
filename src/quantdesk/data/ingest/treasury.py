from __future__ import annotations
from typing import Iterable, Dict
from .base import Ingestor

class Treasury(Ingestor):
    """Stub for U.S. Treasury daily yield curve downloader."""
    def fetch(self, start: str, end: str) -> Iterable[Dict]:
        # TODO: implement download from treasury.gov published CSVs/JSON
        return []

    def save(self, records: Iterable[Dict]) -> int:
        # TODO: persist to Parquet/Timeseries DB
        return 0
