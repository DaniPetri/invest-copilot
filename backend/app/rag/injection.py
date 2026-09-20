"""Heuristic scanner for indirect prompt injection inside retrieved document text (SPEC §6).

Chunks that trip a rule get `flags=["possible_injection"]` and are quarantined: excluded from the model
context by default and reported in the trace. This is a tripwire, not a guarantee: the orchestrator also wraps
retrieved text in <document> tags and instructs the model to treat it as data.
"""

import re

FLAG = "possible_injection"

# Strong: one hit is enough. Addresses the assistant, overrides instructions, or announces a system message.
_STRONG = [
    r"\b(ignorier\w*|missachte\w*|vergiss)\b.{0,60}\b(anweisung\w*|instruktion\w*|regeln|vorgaben|prompt)\b",
    r"\b(ignoriere|ignorieren)\s+(alle|sämtliche|deine|die)\b",
    r"\bsystem\s*(hinweis|nachricht|prompt|anweisung)\b",
    r"\bhinweis\s+an\s+(den|die)\s+(assistent\w*|ki|bot|modell|agent\w*)\b",
    r"\b(an|für)\s+(den|die)\s+(assistent\w*|ki-assistent\w*)\s*:",
    r"\b(ignore|disregard|forget)\b.{0,40}\b(previous|prior|above|all)\b.{0,30}\b(instruction\w*|prompt|rules)\b",
    r"\bnew\s+instructions?\b",
    r"\bdu\s+(musst|sollst)\b.{0,60}\b(empfehl\w*|nenne|antworte)\b",
]
# Weak: only together (two distinct hits) they flag a chunk. Sales language aimed at a reader.
_WEAK = [
    r"\bempfiehl\w*\b",
    r"\bempfehle\b",
    r"\buneingeschränkt\b",
    r"\bbeste\s+wahl\b",
    r"\bnenne\s+dieses\s+produkt\b",
    r"\bfür\s+jeden\s+kunden\b",
    r"\bantworte\s+(nur|immer|ausschließlich)\b",
    r"\bkeine\s+empfehlungen\s+zu\s+geben\b",
]

_STRONG_RE = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in _STRONG]
_WEAK_RE = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in _WEAK]


def matched_rules(text: str) -> list[str]:
    """The patterns that matched, for traces and tests."""
    hits = [p.pattern for p in _STRONG_RE if p.search(text)]
    hits += [p.pattern for p in _WEAK_RE if p.search(text)]
    return hits


def scan(text: str) -> list[str]:
    """Return `["possible_injection"]` when the text looks like an instruction aimed at the model, else `[]`."""
    if any(p.search(text) for p in _STRONG_RE):
        return [FLAG]
    if sum(bool(p.search(text)) for p in _WEAK_RE) >= 2:
        return [FLAG]
    return []
