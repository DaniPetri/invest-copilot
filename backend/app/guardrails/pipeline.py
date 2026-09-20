"""Guardrail pipeline (SPEC §8). Every check emits `{name, status: pass|flag|fail, detail}`; detail is German because it
is shown in the trace panel. A `fail` triggers one repair round (violations go back to the model in English).

Input (before any LLM):   pii, router_flags
Retrieval:                quarantine
Output (on hydrated blocks): citations, numeric_grounding, advice_language, text_integrity, expected_blocks, ai_label
"""

from dataclasses import dataclass, field
from typing import Literal

from ..schemas.events import GuardrailCheck, RouterDecision
from ..schemas.ui import HandoffBlock, TextBlock, UIBlock
from ..tools.registry import ResultStore
from .advice import find_advice_language
from .citations import cited_ids, unknown_citations
from .integrity import find_malformed_text, missing_display_blocks
from .numbers import build_sources, ungrounded_numbers

Status = Literal["pass", "flag", "fail"]


def _check(name: str, status: Status, detail: str) -> GuardrailCheck:
    return GuardrailCheck(name=name, status=status, detail=detail)


@dataclass
class OutputReport:
    checks: list[GuardrailCheck]
    violations: list[str] = field(default_factory=list)  # one per failed check, written for the model

    @property
    def failed(self) -> bool:
        return bool(self.violations)


def pii_check(found: list[str]) -> GuardrailCheck:
    if found:
        return _check("pii", "flag", f"Vor dem Modellaufruf entfernt: {', '.join(found)}.")
    return _check("pii", "pass", "Keine IBAN, E-Mail oder Telefonnummer erkannt.")


def router_flags_check(router: RouterDecision) -> GuardrailCheck | None:
    raised = [
        label
        for label, on in (
            ("Empfehlungswunsch", router.flags.advice_request),
            ("Manipulationsversuch", router.flags.injection_suspected),
        )
        if on
    ]
    return _check("router_flags", "flag", f"Router meldet: {', '.join(raised)}.") if raised else None


def retrieved_chunk_ids(results: ResultStore) -> set[str]:
    return {c["id"] for r in results.all() if r.name == "search_kid" for c in r.payload["chunks"]}


def quarantined_chunk_ids(results: ResultStore) -> list[str]:
    return [q for r in results.all() if r.name == "search_kid" for q in r.payload["quarantined_ids"]]


def quarantine_check(results: ResultStore) -> GuardrailCheck | None:
    if not any(r.name == "search_kid" for r in results.all()):
        return None
    quarantined = quarantined_chunk_ids(results)
    if quarantined:
        return _check(
            "quarantine",
            "flag",
            f"{len(quarantined)} verdächtige Textabschnitte nicht an das Modell gegeben: {', '.join(quarantined)}.",
        )
    return _check("quarantine", "pass", "Keine verdächtigen Textabschnitte im Kontext.")


def authored_text(blocks: list[UIBlock]) -> str:
    """The parts of an answer the model wrote (numbers in the other blocks come from code)."""
    parts = [b.markdown for b in blocks if isinstance(b, TextBlock)]
    parts += [b.reason for b in blocks if isinstance(b, HandoffBlock)]
    return "\n".join(parts)


def check_output(
    blocks: list[UIBlock],
    results: ResultStore,
    user_message: str,
    numbers_mode: Literal["flag", "fail"] = "flag",
) -> OutputReport:
    text = authored_text(blocks)
    checks: list[GuardrailCheck] = []
    violations: list[str] = []

    if quarantine := quarantine_check(results):
        checks.append(quarantine)

    # citations: every [[cite:ID]] must be a chunk retrieved (and shown to the model) in this request
    unknown = unknown_citations(cited_ids(text), retrieved_chunk_ids(results))
    if unknown:
        checks.append(
            _check("citations", "fail", f"Quellenverweis auf nicht abgerufene Abschnitte: {', '.join(unknown)}.")
        )
        violations.append(
            f"citations: {unknown} were not returned by search_kid in this conversation. Cite only chunk IDs from "
            "search_kid results, or remove the citation."
        )
    else:
        checks.append(_check("citations", "pass", "Alle Quellenverweise stammen aus dieser Anfrage."))

    # numeric grounding: every number in model-written text comes from a tool result or the user's message
    sources = build_sources([r.payload for r in results.all() if r.ok], user_message)
    ungrounded = ungrounded_numbers(text, sources)
    if ungrounded:
        status: Status = "fail" if numbers_mode == "fail" else "flag"
        checks.append(
            _check(
                "numeric_grounding",
                status,
                f"Nicht in Werkzeugergebnissen oder Quellen gefunden: {', '.join(ungrounded)}.",
            )
        )
        if status == "fail":
            violations.append(
                f"numeric_grounding: the numbers {ungrounded} do not appear in any tool result. Copy numbers exactly "
                "from tool results or remove them; never calculate."
            )
    else:
        checks.append(_check("numeric_grounding", "pass", "Alle Zahlen stammen aus Werkzeugergebnissen oder Quellen."))

    # advice language
    advice = find_advice_language(text)
    if advice:
        checks.append(_check("advice_language", "fail", f"Empfehlungssprache gefunden: {', '.join(advice)}."))
        violations.append(
            f"advice_language: the text contains advice language ({', '.join(advice)}). Describe criteria and facts "
            "only; do not recommend, rank as best, or say what the customer should do."
        )
    else:
        checks.append(_check("advice_language", "pass", "Keine Empfehlungssprache gefunden."))

    # readable text: no control characters, JSON debris or leaked escapes (the model mangled umlaut escapes once)
    malformed = find_malformed_text(text)
    if malformed:
        checks.append(_check("text_integrity", "fail", f"Text beschädigt: {'; '.join(malformed)}."))
        violations.append(
            f"text_integrity: the text is malformed ({'; '.join(malformed)}). Write plain German text with the "
            "umlauts (ä ö ü ß) typed directly, no backslash escapes, no JSON fragments, and finish every sentence."
        )
    else:
        checks.append(_check("text_integrity", "pass", "Text ist lesbar und vollständig formatiert."))

    # every result the user asked for is shown by its block, not only mentioned
    missing = missing_display_blocks(blocks, results)
    if missing:
        checks.append(_check("expected_blocks", "fail", f"Ergebnis nicht angezeigt: {'; '.join(missing)}."))
        violations.append(
            f"expected_blocks: {'; '.join(missing)}. Add the block that shows the result, referencing its result_id."
        )
    else:
        checks.append(_check("expected_blocks", "pass", "Alle Werkzeugergebnisse werden angezeigt."))

    # AI label: the client puts the KI label on every text block, so an answer without one has nothing to carry it
    if any(isinstance(b, TextBlock) for b in blocks):
        checks.append(_check("ai_label", "pass", "KI-Kennzeichnung vorhanden."))
    else:
        checks.append(_check("ai_label", "fail", "Keine Textantwort, die die KI-Kennzeichnung trägt."))
        violations.append("ai_label: the answer needs at least one text block.")

    return OutputReport(checks, violations)
