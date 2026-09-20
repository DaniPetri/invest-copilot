from datetime import date
from typing import Literal

from pydantic import Field

from .base import Contract

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
