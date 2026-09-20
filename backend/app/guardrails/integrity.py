"""Integrity of a delivered answer: the text is readable, and the data the tools produced is actually shown.

Two failures seen in the M7 answers eval, both invisible to the other guardrails:
- Malformed text. In a repair attempt the model mangled JSON escapes: `\\u00f6` came out as a form feed plus "6",
  so "größten" arrived as "gr\\x0c6\\x0cten"; another draft was cut off in the middle of a word and ended in
  `"} ]`. Numbers, citations and advice language were all fine, so nothing flagged it.
- Missing block. An answer to "Eignungscheck" called `suitability_check` and then delivered one broken text block,
  without the suitability block that carries the result.
"""

import re
import unicodedata

from ..schemas.ui import UIBlock
from ..tools.registry import ResultStore

_ALLOWED_CONTROL = {"\n", "\r", "\t"}
_JSON_DEBRIS = re.compile(r'"\s*[}\]]|[{\[]\s*"\w+"\s*:')  # `"}` or `]` after a quote, or an opening `{"key":`
_LITERAL_ESCAPE = re.compile(r"\\[A-Za-z0-9]")  # a backslash followed by a letter or digit is an escape that leaked

# Tool -> the block types that show its result. The final step must show a result the user asked for; the tools
# that only look things up (screen_products, search_kid) are not listed, their results can just inform the text.
DISPLAY_BLOCKS: dict[str, tuple[str, ...]] = {
    "explain_move": ("attribution",),
    "simulate_savings_plan": ("fan_chart",),
    "cost_projection": ("cost_breakdown",),
    "suitability_check": ("suitability",),
    "portfolio_lookthrough": ("exposure_bars", "overlap_matrix"),
}


def find_malformed_text(text: str) -> list[str]:
    """What is wrong with a piece of authored text (empty = clean)."""
    problems = []
    controls = sorted({repr(c) for c in text if unicodedata.category(c) == "Cc" and c not in _ALLOWED_CONTROL})
    if controls:
        problems.append(f"control characters {', '.join(controls)}")
    if "�" in text:
        problems.append("replacement character U+FFFD")
    if match := _JSON_DEBRIS.search(text):
        problems.append(f"JSON debris {match.group(0)!r}")
    if match := _LITERAL_ESCAPE.search(text):
        problems.append(f"literal escape sequence {match.group(0)!r}")
    return problems


def missing_display_blocks(blocks: list[UIBlock], results: ResultStore) -> list[str]:
    """One message per tool whose result is not shown by any block of the matching type."""
    shown = {b.type for b in blocks}
    out = []
    for name, wanted in DISPLAY_BLOCKS.items():
        ids = [r.result_id for r in results.all() if r.ok and r.name == name]
        if ids and not shown & set(wanted):
            out.append(f"{name} ({', '.join(ids)}) needs a {' or '.join(wanted)} block")
    return out
