"""Synthetic universe (SPEC §5). Deterministic for a given seed; everything is fictional.

uv run python -m app.data.generate            # writes data/generated/
"""

import argparse
import csv
import hashlib
import json
import shutil
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np

from ..config import get_settings
from ..schemas.portfolio import Customer, Position, Profile, Transaction
from ..schemas.products import COUNTRIES, SECTORS, Company, Holding, MarketEvent, Product
from .kid_pdf import INJECTIONS, PAGE_BY_SLUG, SECTIONS, Scenarios, build_kid_content, chunk_id, render_kid

SEED = 20260920
TRADING_DAYS = 252
START = np.datetime64("2021-09-01")
END = np.datetime64("2026-08-31")

ISSUERS = [
    "Alpenkapital Invest",
    "Donauwerth Asset Management",
    "Nordhafen Capital",
    "Rheingold Fonds",
    "Sonnwend Partners",
]

REGION_COUNTRIES = {
    "Welt": list(COUNTRIES),
    "Europa": ["AT", "DE", "FR", "NL", "IT", "ES", "CH", "UK"],
    "USA": ["US"],
    "Schwellenländer": ["CN", "IN", "BR", "KR", "TW"],
    "Österreich": ["AT"],
}


def rng_for(seed: int, stage: int) -> np.random.Generator:
    return np.random.default_rng([seed, stage])


# ── ISIN ────────────────────────────────────────────────────────────────────


def isin_check_digit(body: str) -> int:
    """Check digit for an ISIN body (country/prefix + 9 alphanumerics), Luhn over the letter-expanded digits."""
    digits = "".join(str(int(c, 36)) for c in body)
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            d -= 9 if d > 9 else 0
        total += d
    return (10 - total % 10) % 10


def isin_is_valid(isin: str) -> bool:
    return len(isin) == 12 and isin[-1].isdigit() and isin_check_digit(isin[:-1]) == int(isin[-1])


# ── PRIIPs market-risk bands ────────────────────────────────────────────────


def sri_from_vol(annual_vol: float) -> int:
    """< 0.5 % → 1 · 0.5–5 % → 2 · 5–12 % → 3 · 12–20 % → 4 · 20–30 % → 5 · 30–80 % → 6 · > 80 % → 7."""
    for upper, sri in ((0.005, 1), (0.05, 2), (0.12, 3), (0.20, 4), (0.30, 5), (0.80, 6)):
        if annual_vol < upper:
            return sri
    return 7


# ── companies ───────────────────────────────────────────────────────────────

COUNTRY_QUOTA = {
    "US": 34, "DE": 14, "FR": 12, "UK": 12, "JP": 10, "CN": 9, "CH": 8, "NL": 8,
    "AT": 18, "IT": 5, "ES": 4, "IN": 5, "KR": 4, "TW": 4, "BR": 3,
}  # fmt: skip
SECTOR_QUOTA = {
    "Technologie": 26, "Finanzen": 20, "Gesundheit": 16, "Industrie": 16, "Konsum zyklisch": 14,
    "Basiskonsum": 12, "Energie": 9, "Versorger": 8, "Immobilien": 7, "Rohstoffe": 8, "Kommunikation": 14,
}  # fmt: skip
MEGA_COUNTRIES = ["US", "US", "US", "US", "US", "US", "TW", "DE", "NL", "JP"]

STEMS = {
    "dach": [
        "Alpenrot",
        "Donaufeld",
        "Kaiserbrunn",
        "Lindenhof",
        "Falkenau",
        "Steinbach",
        "Bergholz",
        "Nordwall",
        "Eisenau",
        "Sonnenwald",
        "Grünwerk",
        "Rotenfels",
        "Waldmark",
        "Eichenau",
        "Birkenfeld",
        "Adlerhorst",
        "Felsenau",
        "Tannberg",
        "Mühlbach",
        "Rabenstein",
        "Silberau",
        "Weißenstein",
        "Gletscherau",
        "Hochmoor",
        "Almtal",
        "Kronfeld",
        "Stauffen",
        "Lerchenau",
        "Zinnwald",
        "Marmorstein",
    ],
    "west": [
        "Aurelle",
        "Montclair",
        "Verdana",
        "Solmare",
        "Lucente",
        "Castella",
        "Ventura",
        "Belmonte",
        "Rivalta",
        "Seebrink",
        "Oranjevaart",
        "Duinhof",
        "Marisol",
        "Altamira",
        "Vallenova",
        "Tramonte",
        "Girasole",
        "Lumiere",
    ],
    "anglo": [
        "Northbridge",
        "Ashford",
        "Kestrel",
        "Marlow",
        "Halden",
        "Brightwell",
        "Corvane",
        "Elmstead",
        "Fairmont",
        "Greystone",
        "Holloway",
        "Ironvale",
        "Larkfield",
        "Oakhurst",
        "Pinecrest",
        "Redwater",
        "Stonemere",
        "Thornbury",
        "Westmoor",
        "Yarrow",
        "Ridgeway",
        "Bluemont",
        "Cedarline",
        "Dunmore",
    ],
    "asia": [
        "Hikaro",
        "Sanoku",
        "Meihua",
        "Longwei",
        "Suryam",
        "Nirmal",
        "Paulista",
        "Verdeoro",
        "Seonu",
        "Daeryun",
        "Taiwei",
        "Kirano",
        "Zhenhai",
        "Amaravi",
        "Rioverde",
        "Hanbit",
        "Yuanlu",
        "Tokoro",
        "Bharani",
        "Cerrado",
    ],
}
COUNTRY_STEMS = {
    **dict.fromkeys(["AT", "DE", "CH"], "dach"),
    **dict.fromkeys(["FR", "IT", "ES", "NL"], "west"),
    **dict.fromkeys(["UK", "US"], "anglo"),
    **dict.fromkeys(["JP", "CN", "IN", "BR", "KR", "TW"], "asia"),
}
BRANCH = {
    "Technologie": ["Tech", "Systems", "Chip", "Data", "Soft", "Robotik"],
    "Finanzen": ["Bank", "Versicherung", "Kapital", "Finanz"],
    "Gesundheit": ["Pharma", "Medizin", "Klinik", "Biotec"],
    "Industrie": ["Maschinen", "Stahlbau", "Anlagen", "Logistik"],
    "Konsum zyklisch": ["Motoren", "Mode", "Reisen", "Möbel"],
    "Basiskonsum": ["Lebensmittel", "Brauerei", "Molkerei", "Haushalt"],
    "Energie": ["Energie", "Erdgas", "Raffinerie"],
    "Versorger": ["Wasser", "Netz", "Strom"],
    "Immobilien": ["Immobilien", "Wohnbau", "Grund"],
    "Rohstoffe": ["Bergbau", "Chemie", "Zement"],
    "Kommunikation": ["Telekom", "Medien", "Verlag", "Netzwerk"],
}
SUFFIX = {
    **dict.fromkeys(["AT", "DE", "CH"], "AG"),
    **dict.fromkeys(["FR", "IT", "ES", "NL"], "SE"),
    "UK": "plc",
    **dict.fromkeys(["JP", "CN", "IN", "BR", "KR", "TW"], "Corp"),
}

FLAG_PROB = {  # sector -> {flag: probability}
    "Industrie": {"Waffen": 0.25, "Fossile": 0.08},
    "Technologie": {"Waffen": 0.04},
    "Energie": {"Fossile": 0.9},
    "Rohstoffe": {"Fossile": 0.5},
    "Versorger": {"Fossile": 0.3},
    "Basiskonsum": {"Tabak": 0.15},
    "Konsum zyklisch": {"Glücksspiel": 0.10},
    "Kommunikation": {"Glücksspiel": 0.03},
}
FLAG_DEFAULT = {"Waffen": 0.02, "Fossile": 0.01, "Tabak": 0.005}


def make_companies(rng: np.random.Generator) -> list[Company]:
    n = sum(COUNTRY_QUOTA.values())
    assert n == 150 and sum(SECTOR_QUOTA.values()) == 150

    countries = list(MEGA_COUNTRIES)
    rest_countries = []
    quota = dict(COUNTRY_QUOTA)
    for c in MEGA_COUNTRIES:
        quota[c] -= 1
    for c, k in quota.items():
        rest_countries += [c] * k
    rng.shuffle(rest_countries)
    countries += rest_countries

    sector_quota = dict(SECTOR_QUOTA)
    sector_quota["Technologie"] -= len(MEGA_COUNTRIES)
    rest_sectors = [s for s, k in sector_quota.items() for _ in range(k)]
    rng.shuffle(rest_sectors)
    sectors = ["Technologie"] * len(MEGA_COUNTRIES) + rest_sectors

    mega_caps = np.sort(rng.uniform(250_000, 650_000, len(MEGA_COUNTRIES)))[::-1]
    other_caps = np.clip(rng.lognormal(np.log(22_000), 1.0, n - len(MEGA_COUNTRIES)), 1_500, 200_000)

    companies: list[Company] = []
    used: set[str] = set()
    for i in range(n):
        country, sector = countries[i], sectors[i]
        stems = STEMS[COUNTRY_STEMS[country]]
        while True:
            name = f"{stems[rng.integers(len(stems))]} {BRANCH[sector][rng.integers(len(BRANCH[sector]))]}"
            suffix = SUFFIX.get(country) or ("Inc" if rng.random() < 0.5 else "Corp")
            full = f"{name} {suffix}"
            if full not in used:
                used.add(full)
                break
        flags: list[str] = []
        if i >= len(MEGA_COUNTRIES):
            probs = {**FLAG_DEFAULT, **FLAG_PROB.get(sector, {})}
            flags = [f for f, pr in probs.items() if rng.random() < pr]
        cap = float(mega_caps[i]) if i < len(MEGA_COUNTRIES) else float(other_caps[i - len(MEGA_COUNTRIES)])
        companies.append(
            Company(
                id=f"C{i + 1:03d}", name=full, sector=sector, country=country,
                market_cap_eur_m=round(cap, 1), exclusion_flags=flags,
            )
        )  # fmt: skip
    return companies


# ── bond and money-market issuers (synthetic) ───────────────────────────────


@dataclass
class Issuer:
    id: str
    name: str
    sector: str  # Staatsanleihen | Unternehmensanleihen | Geldmarkt
    country: str
    factor: str  # gov | corp | short | money


def make_issuers(rng: np.random.Generator, companies: list[Company]) -> list[Issuer]:
    states = [
        ("Republik Alpenland", "AT"), ("Königreich Nordmark", "DE"), ("Republik Donaumark", "AT"),
        ("Freistaat Bergland", "CH"), ("Republik Seeland", "NL"), ("Republik Sonnenküste", "ES"),
        ("Republik Rheinmark", "DE"), ("Hansa-Union", "DE"), ("Republik Lagunia", "IT"),
        ("Königreich Weidenau", "UK"), ("Republik Ardennia", "FR"), ("Republik Kastellan", "FR"),
    ]  # fmt: skip
    out: list[Issuer] = []

    def coupon() -> str:
        return f"{rng.integers(15, 45) / 10:.2f}".replace(".", ",")

    for name, country in states:
        out.append(
            Issuer(
                f"B{len(out) + 1:03d}",
                f"{name} {coupon()} % {2029 + rng.integers(0, 8)}",
                "Staatsanleihen",
                country,
                "gov",
            )
        )
    euro = [c for c in companies if c.country in REGION_COUNTRIES["Europa"]]
    for j in rng.choice(len(euro), 30, replace=False):
        c = euro[int(j)]
        out.append(
            Issuer(
                f"B{len(out) + 1:03d}",
                f"{c.name} Anleihe {coupon()} % {2027 + rng.integers(0, 8)}",
                "Unternehmensanleihen",
                c.country,
                "corp",
            )
        )
    for k in range(10):
        name, country = states[k]
        out.append(
            Issuer(
                f"B{len(out) + 1:03d}",
                f"{name} Kurzläufer {coupon()} % {2026 + rng.integers(0, 3)}",
                "Staatsanleihen",
                country,
                "short",
            )
        )
    for k in range(12):
        c = euro[int(rng.integers(len(euro)))]
        out.append(Issuer(f"M{k + 1:03d}", f"Geldmarktpapier {c.name}", "Geldmarkt", c.country, "money"))
    return out


# ── product specs ───────────────────────────────────────────────────────────


@dataclass
class Spec:
    id: str
    name: str
    cls: str
    region: str
    sfdr: int
    excl: list[str]
    dist: str
    ter: float
    entry: float
    txn: float
    plan: float | None
    repl: str
    style: str  # cap | tilt | small | active | bond
    n: int
    bench: str
    sector: str | None = None
    sectors: list[str] | None = None
    countries: list[str] | None = None
    kind: str | None = None  # bond kind or "mixed"
    eq_share: float = 0.0
    hold_years: int = 5


T, A = "thesaurierend", "ausschüttend"
E, F, B_, M_, G = "equity_etf", "equity_fund", "bond_fund", "mixed_fund", "money_market"


# fmt: off
def _spec_list() -> list[Spec]:
    s: list[Spec] = []

    def add(*a, **k):
        s.append(Spec(f"P{len(s) + 1:02d}", *a, **k))

    # 24 equity ETFs
    add("Welt Kernmarkt ETF", E, "Welt", 6, [], T, .0009, 0, .0004, 25, "physisch", "cap", 40, "Sonnwend Welt Kern 500 Index NR")
    add("Welt ESG Leaders ETF", E, "Welt", 8, ["Waffen", "Tabak"], T, .0021, 0, .0006, 25, "physisch", "cap", 36, "Sonnwend Welt ESG Leaders Index NR")
    add("Welt ETF", E, "Welt", 6, [], T, .0015, 0, .0005, 25, "physisch", "cap", 35, "Sonnwend Welt Index NR")
    add("Welt Dividenden ETF", E, "Welt", 6, [], A, .0029, 0, .0008, 25, "physisch", "tilt", 30, "Sonnwend Welt Dividend Select Index NR")
    add("Welt Klima Fokus ETF", E, "Welt", 9, ["Waffen", "Fossile"], T, .0033, 0, .0009, 25, "physisch", "cap", 30, "Sonnwend Welt Klima Fokus Index NR")
    add("Welt Qualität ETF", E, "Welt", 6, [], T, .0025, 0, .0007, 25, "synthetisch", "tilt", 28, "Sonnwend Welt Qualität Index NR")
    add("Europa Paris-Aligned Klima ETF", E, "Europa", 9, ["Waffen", "Fossile"], T, .0015, 0, .0006, 25, "physisch", "cap", 28, "Sonnwend Europa Paris-Aligned Index NR")
    add("Europa Kernmarkt ETF", E, "Europa", 6, [], T, .0010, 0, .0005, 25, "physisch", "cap", 38, "Sonnwend Europa 300 Index NR")
    add("Europa Dividenden ETF", E, "Europa", 6, [], A, .0030, 0, .0008, 25, "physisch", "tilt", 30, "Sonnwend Europa Dividend Select Index NR")
    add("Europa Small Caps ETF", E, "Europa", 6, [], T, .0040, 0, .0012, 50, "physisch", "small", 25, "Sonnwend Europa Small Cap Index NR")
    add("Europa ESG Leaders ETF", E, "Europa", 8, ["Waffen"], A, .0022, 0, .0007, 25, "physisch", "cap", 30, "Sonnwend Europa ESG Leaders Index NR")
    add("Europa Nachhaltigkeit Plus ETF", E, "Europa", 9, ["Waffen", "Tabak"], T, .0032, 0, .0010, 25, "synthetisch", "cap", 26, "Sonnwend Europa Nachhaltigkeit Plus Index NR")
    add("Welt Small Cap Wachstum ETF", E, "Welt", 6, [], T, .0042, 0, .0012, 50, "physisch", "small", 22, "Sonnwend Welt Small Cap Growth Index NR")
    add("USA Kernmarkt ETF", E, "USA", 6, [], T, .0007, 0, .0004, 25, "physisch", "cap", 34, "Sonnwend USA Composite Index NR")
    add("USA Wachstum ETF", E, "USA", 6, [], T, .0025, 0, .0007, 25, "physisch", "tilt", 25, "Sonnwend USA Growth Index NR", sectors=["Technologie", "Kommunikation", "Konsum zyklisch"])
    add("Europa Klima Transition ETF", E, "Europa", 8, ["Waffen"], T, .0028, 0, .0008, 50, "physisch", "cap", 24, "Sonnwend Europa Klima Transition Index NR")
    add("USA Dividenden ETF", E, "USA", 6, [], A, .0030, 0, .0008, 25, "physisch", "tilt", 25, "Sonnwend USA Dividend Select Index NR")
    add("USA ESG ETF", E, "USA", 8, ["Waffen", "Tabak"], T, .0020, 0, .0006, 25, "physisch", "cap", 30, "Sonnwend USA ESG Leaders Index NR")
    add("Schwellenländer ETF", E, "Schwellenländer", 6, [], T, .0035, 0, .0015, 25, "physisch", "cap", 28, "Sonnwend Schwellenländer Index NR")
    add("Schwellenländer ESG ETF", E, "Schwellenländer", 8, ["Waffen", "Tabak", "Glücksspiel"], T, .0045, 0, .0015, 25, "synthetisch", "cap", 24, "Sonnwend Schwellenländer ESG Index NR")
    add("Asien Aufholer ETF", E, "Schwellenländer", 6, [], T, .0038, 0, .0014, 25, "physisch", "tilt", 20, "Sonnwend Asien Aufholer Index NR", countries=["CN", "IN", "KR", "TW"])
    add("Welt Tech ETF", E, "Welt", 6, [], T, .0030, 0, .0007, 25, "physisch", "cap", 24, "Sonnwend Welt Technologie Index NR", sector="Technologie")
    add("Österreich ETF", E, "Österreich", 6, [], T, .0035, 0, .0010, 50, "physisch", "cap", 16, "Sonnwend Österreich Leitindex NR")
    add("Österreich Dividenden ETF", E, "Österreich", 6, [], A, .0040, 0, .0012, 50, "physisch", "tilt", 15, "Sonnwend Österreich Dividend Index NR")
    # 8 active equity funds
    add("Alpen Europa Aktienfonds", F, "Europa", 6, [], T, .0155, .04, .0020, 50, "aktiv", "active", 22, "Sonnwend Europa Index NR")
    add("Österreich Chancen Fonds", F, "Österreich", 8, ["Waffen"], T, .0170, .04, .0025, None, "aktiv", "active", 15, "Sonnwend Österreich Leitindex NR")
    add("Welt Wachstum Aktienfonds", F, "Welt", 6, [], T, .0160, .04, .0020, 50, "aktiv", "active", 25, "Sonnwend Welt Index NR")
    add("USA Value Fonds", F, "USA", 6, [], A, .0150, .04, .0020, 50, "aktiv", "active", 22, "Sonnwend USA Value Index NR")
    add("Nachhaltig Welt Aktienfonds", F, "Welt", 9, ["Waffen", "Tabak", "Fossile"], T, .0165, .05, .0022, 50, "aktiv", "active", 24, "Sonnwend Welt ESG Leaders Index NR")
    add("Schwellenländer Chancen Fonds", F, "Schwellenländer", 6, [], T, .0185, .05, .0030, None, "aktiv", "active", 20, "Sonnwend Schwellenländer Index NR")
    add("Europa Dividenden Select Fonds", F, "Europa", 6, [], A, .0155, .04, .0020, 50, "aktiv", "active", 22, "Sonnwend Europa Dividend Select Index NR")
    add("Welt Technologie Aktienfonds", F, "Welt", 6, [], T, .0175, .05, .0025, 50, "aktiv", "small", 16, "Sonnwend Welt Technologie Index NR", sector="Technologie")
    # 4 bond funds
    add("Euro Staatsanleihen Fonds", B_, "Europa", 6, [], A, .0060, .01, .0003, 50, "aktiv", "bond", 14, "Sonnwend Euro Staatsanleihen Index", kind="gov", hold_years=4)
    add("Euro Unternehmensanleihen ESG Fonds", B_, "Europa", 8, ["Waffen", "Tabak"], A, .0075, .015, .0004, 50, "aktiv", "bond", 20, "Sonnwend Euro Unternehmensanleihen ESG Index", kind="corp", hold_years=4)
    add("Welt Anleihen Fonds", B_, "Welt", 6, [], T, .0080, .02, .0004, None, "aktiv", "bond", 24, "Sonnwend Welt Anleihen Index", kind="gov+corp", hold_years=5)
    add("Euro Kurzläufer Anleihen Fonds", B_, "Europa", 6, [], A, .0050, .01, .0002, 50, "aktiv", "bond", 10, "Sonnwend Euro Kurzläufer Index", kind="short", hold_years=2)
    # 2 mixed funds
    add("Ausgewogen Mix Fonds", M_, "Welt", 8, ["Waffen"], T, .0120, .03, .0012, 50, "aktiv", "mixed", 26, "50 % Sonnwend Welt Index NR / 50 % Sonnwend Euro Anleihen Index", kind="mixed", eq_share=0.5, hold_years=6)
    add("Defensiv Mix Fonds", M_, "Welt", 6, [], A, .0100, .025, .0010, 50, "aktiv", "mixed", 24, "30 % Sonnwend Welt Index NR / 70 % Sonnwend Euro Anleihen Index", kind="mixed", eq_share=0.3, hold_years=4)
    # 2 money-market funds
    add("Euro Geldmarkt Fonds", G, "Europa", 6, [], T, .0010, 0, 0.0, None, "aktiv", "bond", 12, "Sonnwend Euro Geldmarkt Index", kind="money", hold_years=1)
    add("Euro Geldmarkt Plus Fonds", G, "Europa", 8, [], T, .0015, 0, 0.0, None, "aktiv", "bond", 12, "Sonnwend Euro Geldmarkt Plus Index", kind="money", hold_years=1)
    assert len(s) == 40
    return s
# fmt: on


def _normalise(weights: np.ndarray) -> list[float]:
    w = np.round(weights / weights.sum(), 6)
    w[int(np.argmax(w))] += round(1.0 - float(w.sum()), 6)
    return [float(x) for x in w]


def _holding(c: Company, w: float) -> Holding:
    return Holding(id=c.id, name=c.name, sector=c.sector, country=c.country, weight=w)


def _pick_equity(
    spec: Spec, companies: list[Company], rng: np.random.Generator, n: int, share: float = 1.0
) -> list[Holding]:
    countries = spec.countries or REGION_COUNTRIES[spec.region]
    pool = [
        c for c in companies
        if c.country in countries
        and (spec.sector is None or c.sector == spec.sector)
        and not set(c.exclusion_flags) & set(spec.excl)
    ]  # fmt: skip
    n = min(n, len(pool))  # small regions (Österreich, Schwellenländer) cannot fill the nominal count
    if spec.style != "mixed" and n < 15:
        raise ValueError(f"{spec.id}: only {len(pool)} eligible companies, need at least 15")
    caps = np.array([c.market_cap_eur_m for c in pool])
    if spec.style in ("cap", "mixed"):
        idx = np.argsort(-caps)[:n]
        raw = caps[idx] ** 0.4
    elif spec.style == "small":
        start = 0 if spec.sector else min(len(pool) // 4, len(pool) - n)
        idx = np.argsort(caps)[start : start + n]
        raw = caps[idx] ** 0.3
    elif spec.style == "tilt":
        score = caps**0.3 * rng.lognormal(0, 0.5, len(pool))
        if spec.sectors:  # preferred sectors (e.g. growth) get a 3x score, others stay eligible
            score = score * np.array([3.0 if c.sector in spec.sectors else 1.0 for c in pool])
        idx = np.argsort(-score)[:n]
        raw = score[idx]
    else:  # active: concentrated, own conviction
        score = caps**0.4 * rng.lognormal(0, 0.7, len(pool))
        idx = np.argsort(-score)[:n]
        raw = score[idx] ** 1.6
    w = np.array(_normalise(raw)) * share
    return [_holding(pool[int(i)], float(x)) for i, x in zip(idx, w, strict=True)]


def _issuer_holding(i: Issuer, w: float) -> Holding:
    return Holding(id=i.id, name=i.name, sector=i.sector, country=i.country, weight=w)


def _pick_bonds(
    kinds: list[str], issuers: list[Issuer], rng: np.random.Generator, n: int, share: float = 1.0
) -> list[Holding]:
    pool = [i for i in issuers if i.factor in kinds]
    chosen = rng.choice(len(pool), min(n, len(pool)), replace=False)
    raw = rng.lognormal(0, 0.4, len(chosen))
    w = np.array(_normalise(raw)) * share
    return [_issuer_holding(pool[int(j)], float(x)) for j, x in zip(chosen, w, strict=True)]


def _fix_sum(holdings: list[Holding]) -> list[Holding]:
    """Make the weights sum to exactly 1 (within 1e-9) after scaling by shares."""
    ws = np.array([h.weight for h in holdings])
    w = np.round(ws / ws.sum(), 6)
    w[int(np.argmax(w))] += round(1.0 - float(w.sum()), 6)
    return [h.model_copy(update={"weight": float(x)}) for h, x in zip(holdings, w, strict=True)]


def make_products(
    rng: np.random.Generator, companies: list[Company], issuers: list[Issuer]
) -> tuple[list[Product], dict[str, Spec]]:
    products: list[Product] = []
    specs = {}
    used_isins: set[str] = set()
    for idx, spec in enumerate(_spec_list()):
        specs[spec.id] = spec
        if spec.style == "bond":
            kinds = {"gov+corp": ["gov", "corp"]}.get(spec.kind or "", [spec.kind or "gov"])
            holdings = _pick_bonds(kinds, issuers, rng, spec.n)
        elif spec.style == "mixed":
            eq = _pick_equity(spec, companies, rng, 14, spec.eq_share)
            bonds = _pick_bonds(["gov", "corp"], issuers, rng, spec.n - 14, 1 - spec.eq_share)
            holdings = _fix_sum(eq + bonds)
        else:
            holdings = _pick_equity(spec, companies, rng, spec.n)
        while True:
            body = "XD" + "".join(str(d) for d in rng.integers(0, 10, 9))
            isin = body + str(isin_check_digit(body))
            if isin not in used_isins:
                used_isins.add(isin)
                break
        size = float(np.round(rng.lognormal(np.log(1500 if spec.cls == E else 400), 0.8), 1))
        inception = date(int(rng.integers(2008, 2023)), int(rng.integers(1, 13)), int(rng.integers(1, 29)))
        products.append(
            Product(
                id=spec.id, isin=isin, name=spec.name, issuer=ISSUERS[idx % len(ISSUERS)], asset_class=spec.cls,
                region=spec.region, sfdr=spec.sfdr, exclusions=spec.excl, ter=spec.ter, entry_cost=spec.entry,
                distribution=spec.dist, savings_plan_min_eur=spec.plan, replication=spec.repl, inception=inception,
                fund_size_eur_m=size, benchmark=spec.bench, sri=1, recommended_holding_years=spec.hold_years,
                holdings=holdings,
            )
        )  # fmt: skip
    return products, specs


# ── events and prices ───────────────────────────────────────────────────────

EVENTS = [
    ("E01", "2021-11-26", "Neue Virusvariante: Markt gibt nach", "Sorgen vor neuen Einschränkungen belasten die Börsen weltweit.", [], -4.0, 2),
    ("E02", "2022-02-24", "Energiekrise: Ölpreis springt", "Sprunghaft steigende Energiepreise treiben Energiewerte.", ["Energie"], 9.0, 3),
    ("E03", "2022-06-13", "Zinsangst: breite Verkäufe", "Die Furcht vor schnellen Zinserhöhungen löst breite Verkäufe aus.", [], -6.5, 3),
    ("E04", "2022-09-26", "Bankensektor: Liquiditätssorgen", "Sorgen um die Liquidität einzelner Institute belasten Finanzwerte.", ["Finanzen"], -7.0, 2),
    ("E05", "2023-03-13", "Kreditinstitut in Schieflage", "Die Schieflage eines Kreditinstituts verunsichert den Finanzsektor.", ["Finanzen"], -8.0, 3),
    ("E06", "2023-11-14", "Zinswende-Hoffnung: Rally", "Hoffnung auf sinkende Zinsen löst eine breite Kursrally aus.", [], 5.0, 3),
    ("E07", "2024-04-16", "Pharma: Studie enttäuscht", "Eine enttäuschende Studie belastet Gesundheitswerte.", ["Gesundheit"], -6.0, 2),
    ("E08", "2024-08-05", "Blitz-Crash: Volatilitätsspitze", "Ein kurzer Ausverkauf lässt die Schwankungen sprunghaft steigen.", [], -5.5, 2),
    ("E09", "2025-03-10", "Zolldrohungen: Industrie unter Druck", "Neue Zolldrohungen belasten Industrie- und Konsumwerte.", ["Industrie", "Konsum zyklisch"], -5.0, 2),
    ("E10", "2025-10-21", "KI-Euphorie: Chipwerte steigen", "Optimistische Prognosen treiben Technologiewerte nach oben.", ["Technologie"], 7.0, 3),
    ("E11", "2026-02-12", "Rohstoffpreise brechen ein", "Stark fallende Rohstoffpreise belasten Rohstoff- und Energiewerte.", ["Rohstoffe", "Energie"], -6.5, 3),
    ("E12", "2026-08-12", "Chipsektor: schwache Quartalszahlen", "Mehrere Chiphersteller melden schwächere Quartalszahlen. Technologiewerte fallen weltweit über zwei Tage.", ["Technologie"], -6.0, 2),
]  # fmt: skip

SECTOR_SIGMA = {
    "Technologie": 0.0075, "Energie": 0.0080, "Rohstoffe": 0.0070, "Immobilien": 0.0045, "Versorger": 0.0035,
}  # fmt: skip
SECTOR_SIGMA_DEFAULT = 0.0035
MARKET_SIGMA = 0.0085
MARKET_DRIFT = 0.00045  # daily, about 11 % a year before volatility drag and events
GROWTH_TECH_CAP_EUR_M = 40_000  # small technology companies are the high-volatility growth names
BETA_RANGE = {
    "Technologie": (1.0, 1.35), "Finanzen": (1.0, 1.3), "Versorger": (0.5, 0.8), "Basiskonsum": (0.5, 0.8),
    "Gesundheit": (0.6, 0.9),
}  # fmt: skip
EM = {"CN", "IN", "BR", "KR", "TW"}
BOND_FACTOR = {  # daily drift, daily sigma, idiosyncratic sigma
    "gov": (0.025, 0.0040, 0.0005), "corp": (0.035, 0.0030, 0.0008),
    "short": (0.020, 0.0012, 0.0003), "money": (0.025, 0.0002, 0.00003),
}  # fmt: skip


def business_days() -> np.ndarray:
    days = np.arange(START, END + np.timedelta64(1, "D"), dtype="datetime64[D]")
    return days[np.is_busday(days)]


def make_events() -> list[MarketEvent]:
    return [
        MarketEvent(
            id=i, date=date.fromisoformat(d), name=n, description=desc, sectors=s, shock_pct=sh, duration_days=du
        )
        for i, d, n, desc, s, sh, du in EVENTS
    ]


@dataclass
class Universe:
    dates: np.ndarray
    asset_ids: list[str]
    asset_returns: np.ndarray  # (assets, T), first column 0
    products: list[Product]
    nav: dict[str, np.ndarray] = field(default_factory=dict)


def _t(rng: np.random.Generator, size) -> np.ndarray:
    """Student-t (6 dof) scaled to unit variance and demeaned: fat tails, and the drift is a chosen constant
    instead of whatever this seed's sample mean happens to be."""
    x = rng.standard_t(6, size) / np.sqrt(1.5)
    return x - x.mean()


def simulate_assets(
    rng: np.random.Generator,
    dates: np.ndarray,
    companies: list[Company],
    issuers: list[Issuer],
    events: list[MarketEvent],
) -> tuple[list[str], np.ndarray]:
    n_days = len(dates)
    market = MARKET_DRIFT + MARKET_SIGMA * _t(rng, n_days)
    sector_f = {s: SECTOR_SIGMA.get(s, SECTOR_SIGMA_DEFAULT) * _t(rng, n_days) for s in SECTORS}
    for ev in events:
        i0 = int(np.searchsorted(dates, np.datetime64(ev.date)))
        window = slice(i0, i0 + ev.duration_days)
        per_day = ev.shock_pct / 100 / ev.duration_days
        if ev.sectors:
            for s in ev.sectors:
                sector_f[s][window] += per_day
        else:
            market[window] += per_day

    ids: list[str] = []
    rows: list[np.ndarray] = []
    for k, c in enumerate(companies):
        lo, hi = BETA_RANGE.get(c.sector, (0.8, 1.2))
        beta = rng.uniform(lo, hi)
        gamma = rng.uniform(0.7, 1.3)
        idio = rng.uniform(0.006, 0.011) * (1.3 if c.country in EM else 1.0)
        if k < len(MEGA_COUNTRIES):
            idio = 0.006
        elif c.sector == "Technologie" and c.market_cap_eur_m < GROWTH_TECH_CAP_EUR_M:
            beta, idio = rng.uniform(2.0, 2.6), rng.uniform(0.035, 0.045)
        r = beta * market + gamma * sector_f[c.sector] + idio * _t(rng, n_days)
        ids.append(c.id)
        rows.append(np.clip(r, -0.5, 0.5))

    factors = {}
    for kind, (mu, sigma, _) in BOND_FACTOR.items():
        factors[kind] = mu / TRADING_DAYS + sigma * rng.standard_normal(n_days)
    for iss in issuers:
        idio = BOND_FACTOR[iss.factor][2]
        ids.append(iss.id)
        rows.append(factors[iss.factor] + idio * rng.standard_normal(n_days))

    returns = np.vstack(rows)
    returns[:, 0] = 0.0
    return ids, returns


def build_nav(products: list[Product], asset_ids: list[str], returns: np.ndarray) -> dict[str, np.ndarray]:
    index = {a: i for i, a in enumerate(asset_ids)}
    nav = {}
    for p in products:
        w = np.zeros(len(asset_ids))
        for h in p.holdings:
            w[index[h.id]] = h.weight
        r = w @ returns - p.ter / TRADING_DAYS
        r[0] = 0.0
        nav[p.id] = 100.0 * np.cumprod(1.0 + r)
    return nav


def annual_vol(nav: np.ndarray) -> float:
    r = nav[1:] / nav[:-1] - 1.0
    return float(np.std(r, ddof=1) * np.sqrt(TRADING_DAYS))


# ── KID scenarios ───────────────────────────────────────────────────────────

SCENARIO_LABELS = {
    "Stress-Szenario": 1, "Pessimistisches Szenario": 10, "Mittleres Szenario": 50, "Optimistisches Szenario": 90,
}  # fmt: skip


def bootstrap_scenarios(nav: np.ndarray, rhp_years: int, rng: np.random.Generator, n_paths: int = 2000) -> Scenarios:
    r = nav[1:] / nav[:-1] - 1.0

    def run(years: int) -> dict[str, tuple[float, float]]:
        days = TRADING_DAYS * years
        end = np.prod(1.0 + r[rng.integers(0, len(r), size=(n_paths, days))], axis=1) * 10_000
        out = {}
        for label, pct in SCENARIO_LABELS.items():
            v = float(np.percentile(end, pct))
            out[label] = (round(v), (v / 10_000) ** (1 / years) - 1)
        return out

    return Scenarios(rhp_years, run(1), run(rhp_years))


# ── customers ───────────────────────────────────────────────────────────────


def _nav_at(u: Universe, product_id: str, d: date) -> float:
    i = int(np.searchsorted(u.dates, np.datetime64(d)))
    return float(u.nav[product_id][min(i, len(u.dates) - 1)])


def _month_starts(first: date, last: date) -> list[date]:
    out, y, m = [], first.year, first.month
    while date(y, m, 1) <= last:
        out.append(date(y, m, 1))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _first_bday(u: Universe, d: date) -> date:
    i = int(np.searchsorted(u.dates, np.datetime64(d)))
    return date.fromisoformat(str(u.dates[i]))


def _buy(
    u: Universe, txs: list[Transaction], units: dict[str, float], pid: str, eur: float, d: date, kind: str
) -> None:
    """Execute a purchase on the first business day on or after `d` at that day's NAV."""
    day = _first_bday(u, d)
    n = round(eur / _nav_at(u, pid, day), 4)
    units[pid] = round(units.get(pid, 0.0) + n, 4)
    txs.append(Transaction(date=day, product_id=pid, units=n, amount_eur=eur, kind=kind))


def make_customers(u: Universe) -> list[Customer]:
    last = date(2026, 8, 31)
    plans = {
        # id: (name, age, city, persona, profile, lump sums {pid: eur}, first lump date, plan {pid: eur/month}, plan start, cash)
        "anna": (
            "Anna", 29, "Wien", "Sparplan-Einsteigerin",
            Profile(
                risk_class=3, horizon_years=15,
                knowledge={"equity_etf": "basis", "equity_fund": "keine", "bond_fund": "keine", "mixed_fund": "keine", "money_market": "basis"},
                experience={"equity_etf": "basis", "equity_fund": "keine", "bond_fund": "keine", "mixed_fund": "keine", "money_market": "keine"},
                loss_tolerance="mittel", sustainability_preference="art8", prefers_distribution=False,
            ),
            {}, None, {"P03": 50.0, "P07": 25.0}, date(2024, 4, 1), 850.0,
        ),
        "markus": (
            "Markus", 45, "Graz", "ausgewogen",
            Profile(
                risk_class=4, horizon_years=12,
                knowledge={"equity_etf": "erweitert", "equity_fund": "basis", "bond_fund": "basis", "mixed_fund": "basis", "money_market": "basis"},
                experience={"equity_etf": "erweitert", "equity_fund": "basis", "bond_fund": "keine", "mixed_fund": "keine", "money_market": "basis"},
                loss_tolerance="mittel", sustainability_preference="keine", prefers_distribution=False,
            ),
            {"P03": 2500.0, "P22": 1500.0, "P11": 1000.0}, date(2023, 10, 2),
            {"P03": 40.0, "P22": 40.0, "P11": 25.0}, date(2023, 11, 1), 1900.0,
        ),
        "elif": (
            "Elif", 61, "Linz", "vorsichtig",
            Profile(
                risk_class=2, horizon_years=8,
                knowledge={"equity_etf": "basis", "equity_fund": "basis", "bond_fund": "erweitert", "mixed_fund": "basis", "money_market": "erweitert"},
                experience={"equity_etf": "basis", "equity_fund": "basis", "bond_fund": "erweitert", "mixed_fund": "basis", "money_market": "erweitert"},
                loss_tolerance="niedrig", sustainability_preference="keine", prefers_distribution=True,
            ),
            {"P04": 3000.0, "P09": 3000.0, "P34": 2000.0, "P39": 1000.0}, date(2024, 1, 2),
            {"P04": 50.0, "P34": 50.0}, date(2024, 2, 1), 3500.0,
        ),
    }  # fmt: skip
    customers = []
    for cid, (name, age, city, persona, profile, lumps, lump_date, plan, plan_start, cash) in plans.items():
        txs: list[Transaction] = []
        units: dict[str, float] = {}

        for pid, eur in lumps.items():
            _buy(u, txs, units, pid, eur, lump_date, "kauf")
        for m in _month_starts(plan_start, last):
            for pid, eur in plan.items():
                _buy(u, txs, units, pid, eur, m, "sparplan")
        txs.sort(key=lambda t: (t.date, t.product_id))
        customers.append(
            Customer(
                id=cid, name=name, age=age, city=city, persona=persona, profile=profile,
                positions=[Position(product_id=p, units=n) for p, n in sorted(units.items())],
                cash_eur=cash, transactions=txs,
            )
        )  # fmt: skip
    return customers


# ── retrieval ground truth ──────────────────────────────────────────────────

QUESTION_TEMPLATES = {
    "ter": [
        "Wie hoch sind die laufenden Kosten beim {name}?",
        "Was kostet mich der {name} pro Jahr?",
        "{name}: wie viel Prozent Gebühren fallen jährlich an?",
    ],
    "entry_cost": [
        "Fallen beim Kauf des {name} Einstiegskosten an?",
        "Wie hoch ist der Ausgabeaufschlag beim {name}?",
        "Was zahle ich beim Einstieg in den {name}?",
    ],
    "sri": [
        "Welche Risikoklasse hat der {name}?",
        "Wie riskant ist der {name} auf einer Skala von 1 bis 7?",
        "Gesamtrisikoindikator des {name}?",
    ],
    "holding_period": [
        "Wie lange sollte ich den {name} mindestens halten?",
        "Empfohlene Haltedauer für den {name}?",
        "Für welchen Anlagezeitraum ist der {name} gedacht?",
    ],
    "sfdr": [
        "Ist der {name} nachhaltig? Welcher SFDR-Artikel gilt?",
        "Nach welchem Artikel der Offenlegungsverordnung ist der {name} eingestuft?",
        "Wie nachhaltig ist der {name} laut SFDR?",
    ],
    "exclusions": [
        "Gibt es Ausschlusskriterien beim {name}?",
        "Welche Unternehmen sind im {name} ausgeschlossen?",
        "Was schließt der {name} aus ethischen Gründen aus?",
    ],
    "distribution": [
        "Schüttet der {name} Erträge aus oder thesauriert er?",
        "Werden beim {name} die Erträge ausgeschüttet?",
        "Wie werden die Erträge des {name} verwendet?",
    ],
    "benchmark": [
        "Welchen Vergleichsindex hat der {name}?",
        "Woran orientiert sich der {name}?",
        "Welcher Index dient dem {name} als Benchmark?",
    ],
    "savings_plan": [
        "Kann ich den {name} per Sparplan besparen?",
        "Ab welchem Monatsbetrag gibt es beim {name} einen Sparplan?",
        "Ist ein Sparplan für den {name} möglich?",
    ],
}


def make_retrieval_questions(facts: list[dict], products: dict[str, Product]) -> list[dict]:
    slug_by_heading = {h: s for _, h, s in SECTIONS}
    out = []
    for f in facts:
        cid = chunk_id(f["product_id"], f["page"], slug_by_heading[f["section"]])
        for k, tpl in enumerate(QUESTION_TEMPLATES[f["field"]], start=1):
            out.append(
                {
                    "id": f"Q{len(out) + 1:04d}",
                    "question": tpl.format(name=products[f["product_id"]].name),
                    "product_id": f["product_id"],
                    "field": f["field"],
                    "phrasing": k,
                    "expected_chunk_id": cid,
                }
            )
    return out


# ── output ──────────────────────────────────────────────────────────────────


def _dump(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_csv(path: Path, dates: np.ndarray, columns: dict[str, np.ndarray]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["date", *columns])
        cols = [c for c in columns.values()]
        for i, d in enumerate(dates):
            w.writerow([str(d), *(f"{c[i]:.4f}" for c in cols)])


def _manifest(out: Path, seed: int) -> dict:
    files = {
        str(p.relative_to(out).as_posix()): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(out.rglob("*"))
        if p.is_file() and p.name != "manifest.json"
    }
    digest = hashlib.sha256("".join(f"{k}:{v}\n" for k, v in files.items()).encode()).hexdigest()
    return {"seed": seed, "hash": digest, "files": files}


def generate(out: Path, seed: int = SEED, pdfs: bool = True) -> dict:
    """Build the whole universe into `out` and return the manifest (with the overall content hash)."""
    if out.exists():
        shutil.rmtree(out)
    (out / "kid").mkdir(parents=True)

    companies = make_companies(rng_for(seed, 1))
    issuers = make_issuers(rng_for(seed, 2), companies)
    products, specs = make_products(rng_for(seed, 3), companies, issuers)
    events = make_events()

    dates = business_days()
    asset_ids, returns = simulate_assets(rng_for(seed, 4), dates, companies, issuers, events)
    nav = build_nav(products, asset_ids, returns)
    products = [p.model_copy(update={"sri": sri_from_vol(annual_vol(nav[p.id]))}) for p in products]
    universe = Universe(dates, asset_ids, returns, products, nav)
    customers = make_customers(universe)

    _dump(out / "companies.json", [c.model_dump(mode="json") for c in companies])
    _dump(out / "issuers.json", [i.__dict__ for i in issuers])
    _dump(out / "products.json", [p.model_dump(mode="json") for p in products])
    _dump(out / "events.json", [e.model_dump(mode="json") for e in events])
    _dump(out / "customers.json", [c.model_dump(mode="json") for c in customers])
    prices = {a: 100.0 * np.cumprod(1.0 + returns[i]) for i, a in enumerate(asset_ids)}
    _write_csv(out / "prices_assets.csv", dates, prices)
    _write_csv(out / "prices_products.csv", dates, nav)

    kid_rng = rng_for(seed, 5)
    facts: list[dict] = []
    for p in products:
        scen = bootstrap_scenarios(nav[p.id], p.recommended_holding_years, kid_rng)
        content = build_kid_content(p, scen, specs[p.id].txn)
        facts += content.facts
        if pdfs:
            render_kid(content, out / "kid" / f"{p.id}.pdf")
    (out / "kid_facts.jsonl").write_text(
        "".join(json.dumps(f, ensure_ascii=False) + "\n" for f in facts), encoding="utf-8"
    )
    questions = make_retrieval_questions(facts, {p.id: p for p in products})
    (out / "retrieval.jsonl").write_text(
        "".join(json.dumps(q, ensure_ascii=False) + "\n" for q in questions), encoding="utf-8"
    )
    _dump(
        out / "injections.json",
        [
            {
                "product_id": pid,
                "chunk_id": chunk_id(pid, PAGE_BY_SLUG["sonstige_informationen"], "sonstige_informationen"),
                "text": t,
            }
            for pid, t in INJECTIONS.items()
        ],
    )
    manifest = _manifest(out, seed)
    manifest["annual_vol"] = {p.id: round(annual_vol(nav[p.id]), 4) for p in products}
    _dump(out / "manifest.json", manifest)
    return manifest


def _print_table(out: Path, vols: dict[str, float]) -> None:
    products = json.loads((out / "products.json").read_text(encoding="utf-8"))
    print(f"{'ID':<4} {'Name':<38} {'SRI':>3} {'TER':>7} {'SFDR':>6} {'Vol p.a.':>9}")
    for p in products:
        print(
            f"{p['id']:<4} {p['name']:<38} {p['sri']:>3} {p['ter'] * 100:>6.2f}% "
            f"{'Art. ' + str(p['sfdr']):>6} {vols[p['id']] * 100:>8.1f}%"
        )


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=None, help="default: data/generated")
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args(argv)
    out = args.out or get_settings().data_dir
    t0 = time.time()
    manifest = generate(out, args.seed)
    print(f"generated {len(manifest['files'])} files in {time.time() - t0:.1f}s -> {out}")
    print(f"content hash {manifest['hash']}")
    _print_table(out, manifest["annual_vol"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
