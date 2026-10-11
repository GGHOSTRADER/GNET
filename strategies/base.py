"""Shared interface for completed-bar, long-entry strategies."""
from typing import Protocol


class EntryStrategy(Protocol):
    def on_session_start(self) -> None: ...

    def on_bar(self, bar: dict) -> bool: ...
