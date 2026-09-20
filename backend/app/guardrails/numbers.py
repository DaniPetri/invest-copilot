"""Numeric grounding (SPEC §1.1, §8): every number in model-written text must come from a tool result, the user's own
message or a fixed constant. The LLM never does arithmetic that reaches the user.

Matching is tolerant in the ways a German answer needs:
  * formats: `1.234,56`  `1 234,5`  `0,15`  `12,5 %`  `50 €`; also the English `0.15` the model may slip into
  * fractions vs percent: a tool value 0.0015 is grounded when the text says `0,15 %` (value x 100)
  * rounding: the text may show fewer decimals than the tool value (`28.897` for 28897.3) but never different digits
  * signs: `-316,98 €` and `316,98 €` both match the tool value -316.98
  * dates: `12.08.`, `12.08.2026` and `12. August` are read as day and month (and year) and are grounded when every part
    appears in a source (a tool result with `2026-08-12` grounds all three); a wrong date is still reported
  * rankings: `Top-10` is grounded by a top-10 metric in the payload (`top10_over_30pct`); `Top-7` would be reported
Not compared: numbers glued to letters (`P22`, `XD6355122915`, `KID:P07:p2`) and citation markers.
"""

import re
from bisect import bisect_left
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from .citations import strip_citations

# 1.234,56 | 1 234,5 | 12,5 | 0.15 | 2026 | 50. Not preceded/followed by a word character or by another separator.
NUMBER_RE = re.compile(r"(?<![\w.,])(\d{1,3}(?:[.   ]\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)(?![\w])")

# The capital gains tax rate (KESt) is a product constant that only appears in a tool description, not in a payload.
# The look-through thresholds (5 %, 30 %) are read from the flag names in the payload (`single_company_over_5pct`).
KNOWN_CONSTANTS = {27.5}
_FLAG_THRESHOLD = re.compile(r"_(\d+)pct")
# "4 von 7", "1 bis 7", "1-7", "1–7": the scale of the risk indicator, not a claim.
SCALE_RE = re.compile(r"\b\d\s*(?:von|bis|[-–])\s*7\b")
YEAR_RANGE = range(1900, 2101)
_DATE_TOKEN = re.compile(r"\d{4}-\d{2}-\d{2}")
_MONTHS = [
    "januar",
    "februar",
    "märz",
    "april",
    "mai",
    "juni",
    "juli",
    "august",
    "september",
    "oktober",
    "november",
    "dezember",
]
_MONTH_ALIASES = {"jänner": 1, "maerz": 3}
_DATE_NUMERIC = re.compile(r"(?<![\w.,])(\d{1,2})\.\s?(\d{1,2})\.(?:\s?(\d{4}))?(?![\w])")  # 12.08. | 12.08.2026
_DATE_NAMED = re.compile(
    r"(?<![\w.,])(\d{1,2})\.\s?(" + "|".join([*_MONTHS, *_MONTH_ALIASES]) + r")\b(?:\s+(\d{4}))?", re.IGNORECASE
)  # 12. August | 12. August 2026
_TOP_N = re.compile(r"top[\s_-]?(\d+)", re.IGNORECASE)  # Top-10, top10_over_30pct: the size of a ranking


def parse_candidates(token: str) -> list[tuple[float, int]]:
    """(value, decimals) readings of one number token. `1.234` is ambiguous (thousands or decimal): both are kept."""
    t = token.replace(" ", " ").replace(" ", " ")
    out: list[tuple[float, int]] = []
    if "," in t:  # German decimal comma; dots or spaces before it are thousands separators
        whole, frac = t.rsplit(",", 1)
        whole = re.sub(r"[. ]", "", whole)
        out.append((float(f"{whole}.{frac}"), len(frac)))
    elif re.fullmatch(r"\d{1,3}(?:[. ]\d{3})+", t):  # 1.234 / 1 234 / 1.234.567
        out.append((float(re.sub(r"[. ]", "", t)), 0))
        if "." in t and t.count(".") == 1:
            out.append((float(t), len(t.split(".")[1])))
    elif "." in t:  # 0.15
        out.append((float(t), len(t.split(".")[1])))
    else:
        out.append((float(t), 0))
    return out


def _month_number(name: str) -> int:
    n = name.lower()
    return _MONTH_ALIASES[n] if n in _MONTH_ALIASES else _MONTHS.index(n) + 1


def split_dates(text: str) -> tuple[str, list[tuple[str, list[int]]]]:
    """(text without its dates, [(date as written, [day, month, year?])]). Only real calendar dates count: `45.67.`
    and `1.234.567` are left alone as numbers."""
    dates: list[tuple[str, list[int]]] = []

    def take(m: re.Match, month: int) -> str:
        day, year = int(m.group(1)), m.group(3)
        if not (1 <= day <= 31 and 1 <= month <= 12):
            return m.group(0)
        dates.append((m.group(0).strip(), [day, month, *([int(year)] if year else [])]))
        return " "

    text = _DATE_NUMERIC.sub(lambda m: take(m, int(m.group(2))), text)
    text = _DATE_NAMED.sub(lambda m: take(m, _month_number(m.group(2))), text)
    return text, dates


def extract_numbers(text: str) -> list[tuple[str, list[tuple[float, int]]]]:
    """(token, readings) for every number in `text` outside dates, after removing citation markers and scales."""
    text, _ = split_dates(SCALE_RE.sub(" ", strip_citations(text)))
    return [(m.group(1), parse_candidates(m.group(1))) for m in NUMBER_RE.finditer(text)]


@dataclass
class NumberSources:
    """Numbers a text may legitimately contain. `add_*` collect them; `is_grounded` answers for one reading."""

    values: list[float] = field(default_factory=list)
    _sorted: list[float] | None = field(default=None, repr=False)

    def add_number(self, v: float) -> None:
        v = abs(float(v))
        self.values.append(v)
        self.values.append(v * 100)  # a fraction shown as percent
        self._sorted = None

    def add_text(self, text: str) -> None:
        """Numbers written in a string (dates, chunk text, the user's message)."""
        for m in _DATE_TOKEN.finditer(text):
            for part in m.group(0).split("-"):
                self.add_number(int(part))
        for _, parts in split_dates(text)[1]:
            for part in parts:
                self.add_number(part)
        for _, readings in extract_numbers(text):
            for value, _ in readings:
                self.add_number(value)
        for m in _FLAG_THRESHOLD.finditer(text):
            self.add_number(int(m.group(1)))
        for m in _TOP_N.finditer(text):
            self.add_number(int(m.group(1)))

    def add_payload(self, node: Any) -> None:
        """Walk a tool payload: every number, every number inside strings, and the length of every list (counts)."""
        if isinstance(node, bool) or node is None:
            return
        if isinstance(node, int | float):
            self.add_number(node)
        elif isinstance(node, str):
            self.add_text(node)
        elif isinstance(node, dict):
            for key, v in node.items():
                for m in _TOP_N.finditer(str(key)):  # a field called top10_share names the ranking size 10
                    self.add_number(int(m.group(1)))
                self.add_payload(v)
        elif isinstance(node, list | tuple):
            self.add_number(len(node))
            for v in node:
                self.add_payload(v)

    def is_grounded(self, value: float, decimals: int) -> bool:
        if value in KNOWN_CONSTANTS:
            return True
        if decimals == 0 and float(value).is_integer() and int(value) in YEAR_RANGE:
            return True
        if self._sorted is None:
            self._sorted = sorted(self.values)
        tol = 0.5 * 10**-decimals + 1e-9
        i = bisect_left(self._sorted, value - tol)
        return i < len(self._sorted) and self._sorted[i] <= value + tol


def build_sources(payloads: Iterable[Any], user_message: str) -> NumberSources:
    s = NumberSources()
    s.add_text(user_message)
    for p in payloads:
        s.add_payload(p)
    return s


def ungrounded_numbers(text: str, sources: NumberSources) -> list[str]:
    """Number tokens of `text` that no reading of matches a source. Empty = every number is grounded."""
    bad = []
    _, dates = split_dates(SCALE_RE.sub(" ", strip_citations(text)))
    for token, parts in dates:  # a date is grounded when its day, month and year each are
        if not all(sources.is_grounded(part, 0) for part in parts):
            bad.append(token)
    for token, readings in extract_numbers(text):
        if not any(sources.is_grounded(v, d) for v, d in readings):
            bad.append(token)
    return list(dict.fromkeys(bad))
