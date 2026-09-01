"""Context token budgeting."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol


class HasContent(Protocol):
    content: str


@dataclass(frozen=True)
class ContextBudget:
    max_tokens: int = 2000
    reserved_tokens: int = 300
    chars_per_token: float = 4.0

    @property
    def available_tokens(self) -> int:
        return max(0, self.max_tokens - self.reserved_tokens)

    def estimate_tokens(self, text: str) -> int:
        return max(1, int(len(text) / max(self.chars_per_token, 1.0)))

    def fits(self, text: str, used_tokens: int = 0) -> bool:
        return used_tokens + self.estimate_tokens(text) <= self.available_tokens

    def truncate(self, text: str, token_limit: int | None = None) -> str:
        limit = self.available_tokens if token_limit is None else max(0, token_limit)
        char_limit = int(limit * self.chars_per_token)
        return text if len(text) <= char_limit else text[:char_limit].rstrip()
