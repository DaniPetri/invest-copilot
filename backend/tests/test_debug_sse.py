import json

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.events import SSEEventAdapter

from .conftest import FIXTURE_DIR


def _parse_sse(text: str) -> list[tuple[str, str]]:
    events = []
    for block in text.replace("\r\n", "\n").strip().split("\n\n"):
        name, data = None, []
        for line in block.split("\n"):
            if line.startswith("event:"):
                name = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                data.append(line.removeprefix("data:").removeprefix(" "))
        if name:
            events.append((name, "\n".join(data)))
    return events


def test_debug_sse_streams_fixture_over_real_sse():
    with TestClient(app) as client:
        res = client.get("/api/_debug/sse/advice_refusal", params={"fast": True})
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(res.text)
    expected = [
        json.loads(x)["event"] for x in (FIXTURE_DIR / "advice_refusal.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [name for name, _ in events] == expected
    for name, data in events:
        SSEEventAdapter.validate_python({"event": name, "data": json.loads(data)})


def test_debug_sse_rejects_unknown_and_traversal():
    with TestClient(app) as client:
        assert client.get("/api/_debug/sse/nope").status_code == 404
        assert client.get("/api/_debug/sse/..%2F..%2Fpackage").status_code == 404
