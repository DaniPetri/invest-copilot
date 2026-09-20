"""Advice-language detection (SPEC §1.3, §8): the assistant filters, explains, compares and simulates. It never says
what a person should buy or sell. Patterns are deliberately specific verbs and phrases, so a refusal such as
"Eine persönliche Empfehlung darf ich dir nicht geben" does not trigger."""

import re

_F = re.IGNORECASE
_ACTIONS = r"(?:kaufen|verkaufen|investieren|wählen|nehmen|anlegen|umschichten|entscheiden|besparen)"

OUTPUT_PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        "ich empfehle",
        re.compile(
            r"\b(?:ich|wir)\s+(?:(?:dir|ihnen)\s+)?(?:(?:auch|gerne|klar|ganz)\s+)?(?:empfehle|empfehlen|rate)\b", _F
        ),
    ),
    (
        "ich würde empfehlen",
        re.compile(
            r"\b(?:ich|wir)\s+(?:würde|würden)\s+(?:(?:dir|ihnen)\s+)?(?:\w+\s+)?(?:empfehlen|raten|kaufen|verkaufen|nehmen|wählen)\b",
            _F,
        ),
    ),
    (
        "du solltest kaufen",
        re.compile(rf"\b(?:du|sie)\s+(?:solltest|sollten|sollst)\s+(?:\w+\s+){{0,4}}{_ACTIONS}\b", _F),
    ),
    (
        "Kaufaufforderung",
        re.compile(
            r"\b(?:kauf|kaufe|kaufst|verkauf|verkaufe|verkaufst)\s+(?:jetzt|sofort|unbedingt|den|die|das|diesen|diese|dieses)\b",
            _F,
        ),
    ),
    (
        "beste Wahl",
        re.compile(r"\b(?:beste|optimale|perfekte|ideale|richtige)\s+(?:wahl|produkt|etf|fonds|lösung|anlage)\b", _F),
    ),
    ("empfehlenswert", re.compile(r"\bempfehlenswert\w*|\bzu\s+empfehlen\b|\bkann\s+ich\s+nur\s+empfehlen\b", _F)),
    ("unbedingt kaufen", re.compile(rf"\bunbedingt\s+{_ACTIONS}\b|\buneingeschränkt\b", _F)),
    (
        "passt zu dir",
        re.compile(
            r"\bpasst\s+(?:also\s+|damit\s+)?(?:gut|perfekt|optimal|ideal)\s+(?:zu\s+dir|zu\s+deinem|zu\s+deiner|zu\s+deinen|für\s+dich)\b",
            _F,
        ),
    ),
    ("am besten kaufen", re.compile(r"\bam\s+besten\s+(?:kaufst|investierst|nimmst|wählst|legst)\b", _F)),
    (
        "you should",
        re.compile(
            r"\b(?:you\s+should\s+(?:buy|sell|invest)|i\s+(?:recommend|suggest)\s+(?:you\s+)?(?:buy|sell|invest))\b", _F
        ),
    ),
]

# What a *user* message looks like when it asks for a personal recommendation. Only a safety net for when the
# router model is unavailable; the router is the real classifier.
INPUT_ADVICE_PATTERNS: list[re.Pattern] = [
    re.compile(rf"\bsoll(?:te)?\s+ich\b.*\b{_ACTIONS}\b", _F),
    re.compile(r"\bwas\s+(?:soll|sollte)\s+ich\b", _F),
    re.compile(r"\bempfiehl|\bempfehl", _F),
    re.compile(r"\b(?:bester|beste|besten)\s+(?:etf|fonds|wahl)\s+für\s+mich\b", _F),
]


def find_advice_language(text: str) -> list[str]:
    """Names of the advice patterns found in an answer (empty = clean)."""
    return [name for name, pat in OUTPUT_PATTERNS if pat.search(text)]


def looks_like_advice_request(message: str) -> bool:
    return any(p.search(message) for p in INPUT_ADVICE_PATTERNS)
