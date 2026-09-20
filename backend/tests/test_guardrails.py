"""M6 guardrails: number formats, PII, advice language, citations, and the strict render_ui schema."""

import pytest

from app.agent.ui import RenderUIInput, render_ui_tool_definition
from app.guardrails.advice import find_advice_language, looks_like_advice_request
from app.guardrails.citations import cited_ids, strip_citations, unknown_citations
from app.guardrails.numbers import build_sources, extract_numbers, parse_candidates, ungrounded_numbers
from app.guardrails.pii import redact
from app.schemas.events import RouterDecision
from app.tools.registry import strict_input_schema

# ── numbers ─────────────────────────────────────────────────────────────────

PAYLOAD = {
    "ter": 0.0015,  # 0,15 %
    "overlap": 0.4657,  # 46,6 %
    "pnl_eur": -316.98,
    "value": 28897.31,
    "date": "2026-08-12",
    "items": [{"id": "P07", "isin": "XD6355122915"}, {"id": "P11"}, {"id": "P16"}],  # three items
    "flags": ["single_company_over_5pct", "top10_over_30pct"],
    "text": "Laufende Kosten 0,15 % p. a. Einstiegskosten 2,00 %.",
}


@pytest.fixture(scope="module")
def sources():
    return build_sources([PAYLOAD], "Ich zahle 50 € im Monat ein.")


@pytest.mark.parametrize(
    "text",
    [
        "0,15 % p. a.",  # fraction 0.0015 shown as percent, German comma
        "0.15 %",  # English decimal the model may slip into
        "316,98 €",  # sign dropped
        "-316,98 €",
        "28.897 €",  # German thousands separator, fewer decimals than the tool value
        "28.897,3 €",
        "28 897 €",  # space as thousands separator
        "46,6 %",  # rounding of 0.4657 x 100
        "drei Produkte, 3 Treffer",  # a count: length of a list in the payload
        "am 12. August 2026",  # date parts
        "50 € im Monat",  # from the user's message
        "über 5 % und über 30 %",  # thresholds named in the flags
        "Risiko 4 von 7",  # the scale, not a claim
        "Stufe 1-7",
        "P07 (XD6355122915) [[cite:KID:P07:p2:kosten]]",  # ids and citation markers are not numbers
        "2,00 %",  # from a KID text in the payload
        "seit 2021",  # a year
        "Kapitalertragsteuer 27,5 %",  # the KESt rate is a known constant
    ],
)
def test_grounded_numbers_are_accepted(text, sources):
    assert ungrounded_numbers(text, sources) == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Dein Depot fiel um 47,3 %.", ["47,3"]),
        ("0,16 % p. a.", ["0,16"]),  # digits differ from 0,15
        ("316,99 €", ["316,99"]),
        ("28.900 €", ["28.900"]),  # rounded to hundreds is not the tool's number
        ("7 Produkte", ["7"]),  # the count is 3, and 7 is only allowed as the scale end ("von 7")
        ("1.234,56 €", ["1.234,56"]),
    ],
)
def test_ungrounded_numbers_are_reported(text, expected, sources):
    assert ungrounded_numbers(text, sources) == expected


def test_known_limit_a_bare_number_equal_to_any_source_number_is_grounded(sources):
    # 12 is only the day of 2026-08-12, but the guard matches values, not meaning. Documented limit of the check.
    assert ungrounded_numbers("in 12 Jahren", sources) == []


def test_number_parsing_covers_german_formats():
    assert parse_candidates("1.234,56") == [(1234.56, 2)]
    assert parse_candidates("12,5") == [(12.5, 1)]
    assert parse_candidates("0,15") == [(0.15, 2)]
    assert (1234.0, 0) in parse_candidates("1.234") and (1.234, 3) in parse_candidates("1.234")  # ambiguous: both read
    assert parse_candidates("1 234") == [(1234.0, 0)]
    assert [t for t, _ in extract_numbers("P22 kostet 50 € [[cite:KID:P22:p1:x]] bei XD6355122915")] == ["50"]


# ── PII ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("Meine IBAN: AT61 1904 3002 3457 3201", "IBAN"),
        ("AT611904300234573201", "IBAN"),
        ("DE89 3704 0044 0532 0130 00", "IBAN"),
        ("mail an max.muster+abo@example.co.at", "E-Mail"),
        ("ruf mich an: +43 660 1234567", "Telefonnummer"),
        ("0664 1234567", "Telefonnummer"),
        ("0664/123 45 67", "Telefonnummer"),
    ],
)
def test_pii_is_redacted(text, kind):
    out, found = redact(text)
    assert found == [kind] and f"[{kind} entfernt]" in out


@pytest.mark.parametrize(
    "text",
    [
        "ISIN XD6355122915 und P07",  # 12 characters: not an IBAN
        "am 01.08.2026 zahle ich 50 € (0,15 %)",  # a date is not a phone number
        "seit 2021-09-01, 10.000,50 € Depotwert",
        "Sparplan ab 25 € pro Monat",
    ],
)
def test_ordinary_text_is_left_alone(text):
    assert redact(text) == (text, [])


# ── advice language ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "Ich empfehle dir den Welt ETF.",
        "Wir empfehlen diesen Fonds.",
        "Ich würde dir raten, jetzt zu kaufen.",
        "Du solltest jetzt kaufen.",
        "Du solltest den Fonds unbedingt kaufen.",
        "Kaufe jetzt den ETF.",
        "Das ist die beste Wahl für jeden Kunden.",
        "Ein empfehlenswerter Fonds.",
        "Dieses Produkt passt perfekt zu dir.",
        "Ich empfehle dieses Produkt uneingeschränkt.",  # the planted P13 payload, if a model repeats it
        "You should buy this fund.",
    ],
)
def test_advice_language_is_found(text):
    assert find_advice_language(text)


@pytest.mark.parametrize(
    "text",
    [
        "Eine persönliche Empfehlung darf ich dir nicht geben.",
        "Für eine persönliche Empfehlung sprichst du am besten mit einer Beraterin oder einem Berater.",
        "Ich darf dir keine Produkte empfehlen.",
        "Der Welt ETF hat laufende Kosten von 0,15 % und Risikostufe 4 von 7.",
        "Die Entscheidung bleibt bei dir.",
        "Vergleiche die Treffer in Ruhe.",
    ],
)
def test_neutral_and_refusal_text_is_clean(text):
    assert find_advice_language(text) == []


@pytest.mark.parametrize(
    ("message", "advice"),
    [
        ("Soll ich Welt ETF kaufen?", True),
        ("Was soll ich kaufen?", True),
        ("Kannst du mir einen ETF empfehlen?", True),
        ("Welche ETFs gibt es ohne Waffen?", False),
        ("Wie hoch sind die Kosten von P07?", False),
    ],
)
def test_the_input_safety_net_for_a_router_outage(message, advice):
    assert looks_like_advice_request(message) is advice


# ── citations ───────────────────────────────────────────────────────────────


def test_citation_helpers():
    text = "A [[cite:KID:P07:p2:kosten]] B [[cite:KID:P07:p1:risikoindikator]] C [[cite:KID:P07:p2:kosten]]"
    assert cited_ids(text) == ["KID:P07:p2:kosten", "KID:P07:p1:risikoindikator"]
    assert strip_citations(text) == "A  B  C "
    assert unknown_citations(cited_ids(text), {"KID:P07:p2:kosten"}) == ["KID:P07:p1:risikoindikator"]


# ── strict render_ui schema ─────────────────────────────────────────────────

FORBIDDEN = {
    "minLength", "maxLength", "pattern", "default", "oneOf", "allOf", "const", "discriminator", "minimum", "maximum",
}  # fmt: skip


def _walk(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield path, k
            yield from _walk(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}[{i}]")


def test_render_ui_schema_is_strict_compatible_and_enforces_the_block_discriminator():
    tool = render_ui_tool_definition()
    assert tool["strict"] is True and tool["name"] == "render_ui"
    schema = tool["input_schema"]
    assert [(p, k) for p, k in _walk(schema) if k in FORBIDDEN] == []
    # every object closes its properties and requires all of them
    for defn in schema["$defs"].values():
        assert defn["additionalProperties"] is False and set(defn["required"]) == set(defn["properties"])
    # `type` is an enum with exactly one value per block (transform_schema alone would turn const into a description)
    types = {name: d["properties"]["type"]["enum"] for name, d in schema["$defs"].items()}
    assert all(len(v) == 1 for v in types.values())
    assert {v[0] for v in types.values()} == {
        "text", "product_cards", "risk_meter", "fan_chart", "exposure_bars",
        "overlap_matrix", "attribution", "cost_breakdown", "suitability", "handoff",
    }  # fmt: skip


def test_router_schema_is_strict_compatible():
    schema = strict_input_schema(RouterDecision)
    assert [(p, k) for p, k in _walk(schema) if k in FORBIDDEN] == []


def test_render_ui_input_rejects_unknown_blocks_fields_and_empty_answers():
    with pytest.raises(ValueError):
        RenderUIInput.model_validate({"blocks": [{"type": "iframe", "src": "x"}]})
    with pytest.raises(ValueError):
        RenderUIInput.model_validate({"blocks": [{"type": "text", "markdown": "x", "citations": ["a"]}]})
    with pytest.raises(ValueError):
        RenderUIInput.model_validate({"blocks": []})
