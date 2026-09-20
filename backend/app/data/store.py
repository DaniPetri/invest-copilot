"""Read access to the generated universe (data/generated/). Everything is loaded lazily and cached."""

import csv
import json
from dataclasses import dataclass
from functools import cached_property, lru_cache
from pathlib import Path

import numpy as np

from ..config import get_settings
from ..schemas.portfolio import Customer
from ..schemas.products import Company, MarketEvent, Product


class DataMissingError(RuntimeError):
    pass


@dataclass(frozen=True)
class Prices:
    """Daily levels on business days. `products` are net-of-TER NAVs (start 100), `assets` companies and issuers."""

    dates: np.ndarray  # datetime64[D]
    assets: dict[str, np.ndarray]
    products: dict[str, np.ndarray]

    def index_on_or_after(self, d) -> int:
        """Index of the first business day on or after `d` (clamped to the last day)."""
        i = int(np.searchsorted(self.dates, np.datetime64(d)))
        return min(i, len(self.dates) - 1)


def _read_prices(path: Path) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        rows = list(reader)
    dates = np.array([r[0] for r in rows], dtype="datetime64[D]")
    values = np.array([[float(x) for x in r[1:]] for r in rows])
    return dates, {name: values[:, i] for i, name in enumerate(header[1:])}


class Store:
    def __init__(self, root: Path):
        self.root = root

    def _path(self, name: str) -> Path:
        path = self.root / name
        if not path.exists():
            raise DataMissingError(f"{path} not found. Run `make data` first.")
        return path

    def _json(self, name: str):
        return json.loads(self._path(name).read_text(encoding="utf-8"))

    def _jsonl(self, name: str) -> list[dict]:
        return [json.loads(x) for x in self._path(name).read_text(encoding="utf-8").splitlines() if x.strip()]

    @cached_property
    def companies(self) -> list[Company]:
        return [Company.model_validate(x) for x in self._json("companies.json")]

    @cached_property
    def products(self) -> list[Product]:
        return [Product.model_validate(x) for x in self._json("products.json")]

    @cached_property
    def events(self) -> list[MarketEvent]:
        return [MarketEvent.model_validate(x) for x in self._json("events.json")]

    @cached_property
    def customers(self) -> list[Customer]:
        return [Customer.model_validate(x) for x in self._json("customers.json")]

    @cached_property
    def prices(self) -> Prices:
        dates, assets = _read_prices(self._path("prices_assets.csv"))
        _, products = _read_prices(self._path("prices_products.csv"))
        return Prices(dates, assets, products)

    @cached_property
    def kid_facts(self) -> list[dict]:
        return self._jsonl("kid_facts.jsonl")

    @cached_property
    def retrieval_questions(self) -> list[dict]:
        return self._jsonl("retrieval.jsonl")

    @cached_property
    def injections(self) -> list[dict]:
        return self._json("injections.json")

    def product(self, product_id: str) -> Product:
        for p in self.products:
            if p.id == product_id:
                return p
        raise KeyError(f"unknown product {product_id}")

    def customer(self, customer_id: str) -> Customer:
        for c in self.customers:
            if c.id == customer_id:
                return c
        raise KeyError(f"unknown customer {customer_id}")

    def kid_path(self, product_id: str) -> Path:
        return self._path(f"kid/{product_id}.pdf")


@lru_cache
def get_store(root: Path | None = None) -> Store:
    return Store(root or get_settings().data_dir)


def data_available(root: Path | None = None) -> bool:
    return ((root or get_settings().data_dir) / "manifest.json").exists()
