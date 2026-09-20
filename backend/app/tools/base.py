"""Shared plumbing for the deterministic tools: context and error type."""

from dataclasses import dataclass, field
from typing import Literal

from ..data.store import Store
from ..rag.search import KidIndex, get_index


class ToolError(Exception):
    """A problem the caller can act on: unknown ID, bad date range, invalid weights.

    `code` maps to HTTP (404 / 422) and, in the agent, to an `is_error` tool result the model can correct.
    """

    def __init__(self, code: Literal["not_found", "invalid"], message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ToolContext:
    """What a tool needs: the generated universe and, for `search_kid`, the retrieval index."""

    store: Store
    _index: KidIndex | None = field(default=None, repr=False)

    @property
    def index(self) -> KidIndex:
        if self._index is None:
            self._index = get_index(self.store.root)
        return self._index

    def product(self, product_id: str):
        try:
            return self.store.product(product_id)
        except KeyError:
            raise ToolError("not_found", f"Unknown product {product_id!r}") from None

    def customer(self, customer_id: str):
        try:
            return self.store.customer(customer_id)
        except KeyError:
            raise ToolError("not_found", f"Unknown customer {customer_id!r}") from None
