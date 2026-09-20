"""PII redaction before anything reaches an LLM (SPEC §8): IBAN, e-mail, phone numbers.

The redacted text is what the router, the orchestrator and the trace see; the raw message is never stored.
"""

import re

# 2 letters + 2 check digits + 3-7 blocks of 4 + a short tail: at least 16 characters, so a 12-character ISIN
# (which also starts with two letters) never matches.
IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){3,7}(?:[ ]?[A-Z0-9]{1,4})?\b")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Candidates start with + / 0 and mix digits with spaces, slashes, brackets and dashes. A dot is not a separator, so
# dates such as 01.08.2026 do not match; the digit count filter below drops the remaining short numbers.
PHONE_RE = re.compile(r"(?<![\w.,])(?:\+\d{1,3}|00\d{1,3}|0)[\s/()-]*\d(?:[\s/()-]*\d){7,13}(?![\w])")

REDACTED = {"IBAN": "[IBAN entfernt]", "E-Mail": "[E-Mail entfernt]", "Telefonnummer": "[Telefonnummer entfernt]"}


def _phone_sub(found: list[str]):
    def sub(m: re.Match) -> str:
        digits = sum(c.isdigit() for c in m.group(0))
        if not 9 <= digits <= 15:
            return m.group(0)
        found.append("Telefonnummer")
        return REDACTED["Telefonnummer"]

    return sub


def redact(text: str) -> tuple[str, list[str]]:
    """Returns the text with PII replaced and the kinds found (each kind once, in order of detection)."""
    found: list[str] = []
    text, n = EMAIL_RE.subn(REDACTED["E-Mail"], text)
    found += ["E-Mail"] * n
    text, n = IBAN_RE.subn(REDACTED["IBAN"], text)
    found += ["IBAN"] * n
    text = PHONE_RE.sub(_phone_sub(found), text)
    return text, list(dict.fromkeys(found))
