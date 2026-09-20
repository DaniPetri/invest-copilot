"""Parse a KID PDF into sections: pypdf per page, split on the known section headings (SPEC §6)."""

import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from ..data.kid_pdf import SECTIONS

HEADER_RE = re.compile(r"^(?P<name>.+) \| (?P<isin>XD\d{10})$")


@dataclass(frozen=True)
class ParsedSection:
    product_id: str
    page: int
    heading: str
    slug: str
    text: str


@dataclass(frozen=True)
class ParsedKid:
    product_id: str
    name: str
    isin: str
    sections: list[ParsedSection]


def parse_kid(path: Path, product_id: str) -> ParsedKid:
    """Everything before the first heading on a page (running header and footer) is dropped; the product name
    is read from the header line "<name> | <isin>"."""
    reader = PdfReader(path)
    name = isin = ""
    sections: list[ParsedSection] = []
    for page_no, page in enumerate(reader.pages, start=1):
        headings = {h: s for pg, h, s in SECTIONS if pg == page_no}
        current: tuple[str, str] | None = None
        buffer: list[str] = []

        def flush(cur: tuple[str, str] | None, lines: list[str], pg: int = page_no) -> None:
            if cur:
                sections.append(ParsedSection(product_id, pg, cur[0], cur[1], "\n".join(lines)))

        for raw in (page.extract_text() or "").splitlines():
            line = re.sub(r"[ \t]+", " ", raw).strip()
            if not line:
                continue
            if m := HEADER_RE.match(line):
                name, isin = m["name"], m["isin"]
            elif line in headings:
                flush(current, buffer)
                current, buffer = (line, headings[line]), []
            elif current:
                buffer.append(line)
        flush(current, buffer)

    found = [s.slug for s in sections]
    expected = [slug for _, _, slug in SECTIONS]
    if found != expected or not name:
        raise ValueError(f"{path.name}: unexpected KID layout, sections {found}, name {name!r}")
    return ParsedKid(product_id, name, isin, sections)
