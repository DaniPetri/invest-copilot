from datetime import date
from typing import Literal

from pydantic import Field

from .base import Contract

SECTORS = [
    "Technologie",
    "Finanzen",
    "Gesundheit",
    "Industrie",
    "Konsum zyklisch",
    "Basiskonsum",
    "Energie",
    "Versorger",
    "Immobilien",
    "Rohstoffe",
    "Kommunikation",
]
COUNTRIES = ["AT", "DE", "FR", "NL", "IT", "ES", "CH", "UK", "US", "JP", "CN", "IN", "BR", "KR", "TW"]

AssetClass = Literal["equity_etf", "equity_fund", "bond_fund", "mixed_fund", "money_market"]
Region = Literal["Europa", "USA", "Welt", "Schwellenländer", "Österreich"]
Exclusion = Literal["Waffen", "Fossile", "Tabak", "Glücksspiel"]
Distribution = Literal["thesaurierend", "ausschüttend"]
Replication = Literal["physisch", "synthetisch", "aktiv"]


class Company(Contract):
    id: str
    name: str
    sector: str
    country: str
    market_cap_eur_m: float = Field(ge=0)


class Holding(Contract):
    """One position inside a product. For bond and money-market funds these are synthetic issuers."""

    id: str
    name: str
    sector: str
    country: str
    weight: float = Field(ge=0, le=1)


class Product(Contract):
    id: str = Field(pattern=r"^P\d{2}$")
    isin: str = Field(pattern=r"^XD\d{9}\d$")
    name: str
    issuer: str
    asset_class: AssetClass
    region: Region
    sfdr: Literal[6, 8, 9]
    exclusions: list[Exclusion]
    ter: float = Field(ge=0, description="Ongoing costs as a fraction, 0.0015 = 0.15 % p. a.")
    entry_cost: float = Field(ge=0, description="Entry cost as a fraction")
    distribution: Distribution
    savings_plan_min_eur: float | None
    replication: Replication
    inception: date
    fund_size_eur_m: float = Field(ge=0)
    benchmark: str
    sri: int = Field(ge=1, le=7)
    recommended_holding_years: int = Field(ge=1)
    holdings: list[Holding]


class MarketEvent(Contract):
    """Ground truth for attribution: a dated shock to the whole market or to single sectors."""

    id: str
    date: date
    name: str
    description: str
    sectors: list[str] = Field(description="Empty list = whole market")
    shock_pct: float
    duration_days: int = Field(ge=1)
