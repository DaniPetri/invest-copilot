from datetime import date
from typing import Literal

from pydantic import Field

from .base import Contract
from .products import AssetClass, MarketEvent

Level = Literal["keine", "basis", "erweitert"]
LossTolerance = Literal["niedrig", "mittel", "hoch"]
SustainabilityPreference = Literal["keine", "art8", "art9"]
ProductType = Literal["equity_etf", "equity_fund", "bond_fund", "mixed_fund", "money_market"]


class Profile(Contract):
    """MiFID-style investor profile."""

    risk_class: int = Field(ge=1, le=5)
    horizon_years: int = Field(ge=1)
    knowledge: dict[ProductType, Level]
    experience: dict[ProductType, Level]
    loss_tolerance: LossTolerance
    sustainability_preference: SustainabilityPreference
    prefers_distribution: bool = False


class Position(Contract):
    product_id: str
    units: float = Field(ge=0)


class Transaction(Contract):
    date: date
    product_id: str
    units: float
    amount_eur: float
    kind: Literal["sparplan", "kauf", "verkauf"]


class Customer(Contract):
    id: str
    name: str
    age: int
    city: str
    persona: str
    profile: Profile
    positions: list[Position]
    cash_eur: float
    transactions: list[Transaction]


# ── GET /api/customers/{id}/portfolio ───────────────────────────────────────


class SeriesPoint(Contract):
    date: date
    value_eur: float


class PortfolioPosition(Contract):
    product_id: str
    name: str
    asset_class: AssetClass
    sri: int = Field(ge=1, le=7)
    units: float
    value_eur: float
    weight: float = Field(ge=0, le=1)


class EventMarker(Contract):
    """A ground-truth market event that touched the customer's holdings, with what it did to the depot."""

    event: MarketEvent
    change_eur: float
    change_pct: float = Field(description="Portfolio move over the event window (day before to end of shock), in %")


class PortfolioView(Contract):
    customer_id: str
    as_of: date
    total_value_eur: float
    cash_eur: float
    change_3m_eur: float = Field(description="Market P&L over the last 3 months, excluding money paid in")
    change_3m_pct: float
    series: list[SeriesPoint] = Field(description="Daily depot value, last 12 months")
    positions: list[PortfolioPosition]
    events: list[EventMarker]
