"""Chunking (SPEC §6): one chunk per section, long sections become sliding windows.

Chunk ID: `KID:{product_id}:p{page}:{section_slug}[:{n}]`. The `:n` suffix (1-based) only exists for windowed sections.
"""

from dataclasses import dataclass

from ..data.kid_pdf import chunk_id
from ..schemas.tools import Chunk
from .injection import scan
from .parse import ParsedKid

MAX_CHARS = 900
OVERLAP = 150


@dataclass(frozen=True)
class KidChunk:
    id: str
    product_id: str
    product_name: str
    page: int
    section: str  # heading as printed, e.g. "Kosten"
    slug: str
    text: str
    flags: tuple[str, ...] = ()

    @property
    def index_text(self) -> str:
        """What gets embedded and tokenised: the product name and section heading give every chunk its context."""
        return f"{self.product_name} | {self.section}\n{self.text}"

    def to_chunk(self, score: float = 0.0) -> Chunk:
        return Chunk(
            id=self.id,
            product_id=self.product_id,
            page=self.page,
            section=self.section,
            text=self.text,
            score=score,
            flags=list(self.flags),
        )


def windows(text: str, max_chars: int = MAX_CHARS, overlap: int = OVERLAP) -> list[str]:
    """Split on whitespace into windows of at most `max_chars` characters that overlap by about `overlap`."""
    if len(text) <= max_chars:
        return [text]
    out: list[str] = []
    start = 0
    while True:
        end = min(start + max_chars, len(text))
        if end < len(text):
            cut = text.rfind(" ", start + max_chars // 2, end)
            cut = text.rfind("\n", start + max_chars // 2, end) if cut == -1 else cut
            end = cut if cut != -1 else end
        out.append(text[start:end].strip())
        if end >= len(text):
            return out
        nxt = max(end - overlap, start + 1)
        space = text.find(" ", nxt, end)  # start the next window on a word boundary
        start = space + 1 if space != -1 else nxt


def chunk_kid(kid: ParsedKid, max_chars: int = MAX_CHARS, overlap: int = OVERLAP) -> list[KidChunk]:
    chunks: list[KidChunk] = []
    for s in kid.sections:
        base = chunk_id(s.product_id, s.page, s.slug)
        parts = windows(s.text, max_chars, overlap)
        for n, part in enumerate(parts, start=1):
            chunks.append(
                KidChunk(
                    id=base if len(parts) == 1 else f"{base}:{n}",
                    product_id=s.product_id,
                    product_name=kid.name,
                    page=s.page,
                    section=s.heading,
                    slug=s.slug,
                    text=part,
                    flags=tuple(scan(part)),
                )
            )
    return chunks
