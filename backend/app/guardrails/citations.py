"""Citation handling: `[[cite:CHUNK_ID]]` markers in text blocks (SPEC §8)."""

import re

CITE_RE = re.compile(r"\[\[cite:([^\]\s]+)\]\]")


def cited_ids(text: str) -> list[str]:
    """Chunk IDs cited in `text`, in order of first appearance."""
    return list(dict.fromkeys(CITE_RE.findall(text)))


def strip_citations(text: str) -> str:
    return CITE_RE.sub("", text)


def unknown_citations(cited: list[str], retrieved: set[str]) -> list[str]:
    """Cited IDs that were not retrieved (and therefore not shown to the model) in this request. Quarantined chunks
    are never in `retrieved`, so citing one fails as well."""
    return [c for c in cited if c not in retrieved]
