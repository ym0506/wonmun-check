"""배포(Vercel) 환경에서 달라지는 동작: 진입점, 접속 주소, 기록 파일 위치와 실패 처리."""

from pathlib import Path

from fastapi.testclient import TestClient

from wonmun import llm
from wonmun.config import Settings


def test_entrypoint_serves_page_and_example():
    import index

    c = TestClient(index.app)
    assert c.get("/").status_code == 200
    assert c.get("/static/app.js").status_code == 200
    assert c.get("/api/examples/L07").json()["example"]["title"]


def test_client_ip_uses_vercel_header(monkeypatch):
    from starlette.requests import Request

    from web.app import _client_ip

    scope = {"type": "http", "headers": [(b"x-real-ip", b"203.0.113.7"), (b"x-forwarded-for", b"198.51.100.1, 10.0.0.1")],
             "client": ("10.0.0.9", 1234)}
    monkeypatch.setenv("VERCEL", "1")
    assert _client_ip(Request(scope)) == "203.0.113.7"
    monkeypatch.delenv("VERCEL")
    assert _client_ip(Request(scope)) == "10.0.0.9"  # 로컬에서는 헤더를 믿지 않는다


def test_ledger_goes_to_tmp_on_vercel(monkeypatch):
    monkeypatch.delenv("WONMUN_LEDGER", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    assert Settings().ledger_path == Path("/tmp/wonmun_api_ledger.jsonl")


def test_ledger_write_failure_is_ignored(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    rec = llm.CallRecord.__new__(llm.CallRecord)
    rec.__dict__.update({"input_tokens": 1})
    llm._append_ledger(blocker / "sub" / "ledger.jsonl", rec)  # 부모가 파일이라 만들 수 없음 → 예외 없이 넘어감
