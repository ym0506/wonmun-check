"""웹 화면(FastAPI). 실행: .venv/bin/uvicorn web.app:app --port 8000

- GET  /                 정적 화면(index.html)
- GET  /evidence         근거 자료(표본·정답·캡처, eval/make_evidence.py로 만듦)
- GET  /api/meta         모델 이름, 호출 제한
- GET  /api/examples     저장 예시 목록
- GET  /api/examples/ID  저장 예시 결과(API 호출 없음)
- POST /api/check        직접 확인(요약 주소/글 + 원문 주소/파일). 하루 전체·IP당 호출 제한.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import date
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from wonmun.config import Settings, load_api_key
from wonmun.llm import Extractor, LLMError
from wonmun.pipeline import InputError, build_original, build_summary, run_check

HERE = Path(__file__).resolve().parent
EXAMPLES = HERE / "examples"
MODEL_LABEL = {"claude-haiku-5-5": "Claude Haiku 5.5", "claude-sonnet-5-5": "Claude Sonnet 5.5",
               "claude-opus-5-5": "Claude Opus 5.5"}

settings = Settings()
app = FastAPI(title="원문 확인", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


class DailyLimiter:
    """메모리 안 하루 단위 카운터(서버를 다시 켜면 초기화). 배포 대비 최소한의 제한."""

    def __init__(self, total: int, per_ip: int):
        self.total, self.per_ip = total, per_ip
        self.day = date.today()
        self.count = 0
        self.by_ip: dict[str, int] = {}
        self.lock = threading.Lock()

    def take(self, ip: str) -> str | None:
        with self.lock:
            if date.today() != self.day:
                self.day, self.count, self.by_ip = date.today(), 0, {}
            if self.count >= self.total:
                return "오늘 직접 확인 횟수(전체)를 다 썼습니다. 예시는 계속 볼 수 있습니다."
            if self.by_ip.get(ip, 0) >= self.per_ip:
                return "이 접속 주소의 오늘 직접 확인 횟수를 다 썼습니다. 예시는 계속 볼 수 있습니다."
            self.count += 1
            self.by_ip[ip] = self.by_ip.get(ip, 0) + 1
            return None

    def remaining(self) -> int:
        return max(0, self.total - self.count)


limiter = DailyLimiter(settings.daily_limit, settings.ip_daily_limit)


def _client_ip(request: Request) -> str:
    """접속 주소. Vercel에서는 프록시 뒤라 Vercel이 채우는 x-real-ip를 쓴다."""
    if os.environ.get("VERCEL"):
        ip = request.headers.get("x-real-ip") or request.headers.get("x-forwarded-for", "").split(",")[0]
        if ip.strip():
            return ip.strip()
    return request.client.host if request.client else "unknown"


@app.get("/")
def index():
    return FileResponse(HERE / "static/index.html")


@app.get("/evidence")
def evidence():
    return FileResponse(HERE / "static/evidence.html")


@app.get("/api/meta")
def meta():
    return {
        "model": settings.model,
        "model_label": MODEL_LABEL.get(settings.model, settings.model),
        "live_enabled": bool(load_api_key(settings)) and settings.daily_limit > 0,
        "daily_limit": settings.daily_limit, "ip_daily_limit": settings.ip_daily_limit,
        "remaining_today": limiter.remaining(),
    }


def _example_list():
    out = []
    for p in sorted(EXAMPLES.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        out.append({"id": p.stem, "title": d.get("example", {}).get("title", p.stem),
                    "label": d.get("example", {}).get("label", "")})
    return out


@app.get("/api/examples")
def examples():
    return _example_list()


@app.get("/api/examples/{ex_id}")
def example(ex_id: str):
    if ex_id not in {e["id"] for e in _example_list()}:
        raise HTTPException(404, "예시를 찾지 못했습니다.")
    return JSONResponse(json.loads((EXAMPLES / f"{ex_id}.json").read_text(encoding="utf-8")))


@app.post("/api/check")
async def check(request: Request,
                summary_url: str = Form(""), summary_text: str = Form(""),
                original_url: str = Form(""), original_file: UploadFile | None = File(None)):
    if not load_api_key(settings):
        raise HTTPException(503, "서버에 AI 키가 없어 직접 확인을 쓸 수 없습니다. 예시는 볼 수 있습니다.")
    if len(summary_text) > 30000:
        raise HTTPException(400, "요약 글이 너무 깁니다(3만 자 이하).")
    file_bytes, filename = None, ""
    if original_file is not None and original_file.filename:
        file_bytes = await original_file.read(settings.fetch_max_bytes + 1)
        if len(file_bytes) > settings.fetch_max_bytes:
            raise HTTPException(400, "파일이 너무 큽니다(15MB 이하).")
        filename = original_file.filename
    msg = limiter.take(_client_ip(request))
    if msg:
        raise HTTPException(429, msg)
    def work():
        top, body, meta = build_summary(summary_url, summary_text, settings)
        orig = build_original(original_url, file_bytes, filename, settings)
        return run_check(top, body, orig, extractor=Extractor(settings), settings=settings,
                         meta=meta, case="live")

    try:
        result = await run_in_threadpool(work)  # 페이지 받기·AI 호출이 이벤트 루프를 막지 않게
    except InputError as e:
        raise HTTPException(400, str(e)) from e
    except LLMError as e:
        raise HTTPException(502, str(e)) from e
    result.pop("ai_output", None)  # 화면에는 판정에 쓴 값만
    return JSONResponse(result)
