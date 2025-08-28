from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Iterable, Any

class Ingestor(ABC):
    """Abstract base for data connectors."""
    @abstractmethod
    def fetch(self, *args: Any, **kwargs: Any) -> Iterable[dict]:
        raise NotImplementedError

    @abstractmethod
    def save(self, records: Iterable[dict]) -> int:
        """Persist records to storage; return count saved."""
        raise NotImplementedError
