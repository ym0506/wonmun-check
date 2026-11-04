"""요청 한 건의 흐름: 입력 → 글자 꺼내기 → AI 근거 찾기 → 인용 검사·값 정리 → 판정 → 결과 JSON."""

from __future__ import annotations

import time
from datetime import date, datetime, timezone

from . import ITEMS
from .config import Settings
from .dates import guess_ref_year, parse_iso
from .fetch import FetchError, fetch_url
from .judge import RED, NEEDS_CHECK, build_value, judge_all
from .llm import Extractor
from .portals import PortalError, detect_portal, parse_linkareer, parse_youthcenter
from .quotes import QuoteIndex
from .textsrc import SourceDoc, decode_bytes, doc_from_bytes, limit_segments, text_doc

RESULT_VERSION = 1


class InputError(Exception):
    pass


def summary_from_html(html: str, url: str) -> tuple[SourceDoc, SourceDoc | None, dict]:
    portal = detect_portal(url)
    if portal == "linkareer":
        return parse_linkareer(html, url)
    if portal == "youthcenter":
        return parse_youthcenter(html, url)
    raise InputError("요약 주소는 링커리어 공고나 온통청년 정책 상세 주소만 지원합니다. 다른 곳은 요약 글을 붙여 넣어 주세요.")


def build_summary(summary_url: str = "", summary_text: str = "",
                  settings: Settings | None = None) -> tuple[SourceDoc, SourceDoc | None, dict]:
    if summary_text.strip():
        top = text_doc(summary_text, "top", "붙여 넣은 요약", kind="paste")
        top.label = "붙여 넣은 요약"
        return top, None, {"portal": None}
    if not summary_url.strip():
        raise InputError("요약 주소나 요약 글 중 하나를 넣어 주세요.")
    if not detect_portal(summary_url):
        raise InputError("요약 주소는 링커리어 공고나 온통청년 정책 상세 주소만 지원합니다. 다른 곳은 요약 글을 붙여 넣어 주세요.")
    try:
        res = fetch_url(summary_url, settings)
    except FetchError as e:
        raise InputError(f"요약 페이지를 읽지 못했습니다. {e} 요약 글을 붙여 넣어 주세요.") from e
    html = decode_bytes(res.content, res.content_type)
    try:
        return summary_from_html(html, summary_url)
    except PortalError as e:
        raise InputError(str(e)) from e


def build_original(original_url: str = "", file_bytes: bytes | None = None, filename: str = "",
                   settings: Settings | None = None) -> SourceDoc | None:
    if file_bytes:
        try:
            return doc_from_bytes(file_bytes, "original", filename or "올린 파일", filename=filename)
        except ValueError as e:
            raise InputError(str(e)) from e
    if not original_url.strip():
        return None
    try:
        res = fetch_url(original_url, settings)
    except FetchError as e:
        raise InputError(f"원문을 읽지 못했습니다. {e}") from e
    try:
        return doc_from_bytes(res.content, "original", original_url, filename=res.final_url,
                              content_type=res.content_type)
    except ValueError as e:
        raise InputError(str(e)) from e


def _ref_year(docs: list[SourceDoc], today: date) -> int:
    text = "\n".join(d.full_text() for d in docs)
    return guess_ref_year(text, today.year)


def run_check(top: SourceDoc, body: SourceDoc | None, original: SourceDoc | None, *,
              extractor: Extractor | None = None, settings: Settings | None = None,
              today: str | None = None, case: str = "", meta: dict | None = None,
              ai_output: dict | None = None) -> dict:
    """ai_output을 주면 AI를 부르지 않고 그 출력으로 판정만 다시 한다(시험용 재채점)."""
    settings = settings or Settings()
    today_d = parse_iso(today) if today else date.today()
    docs = [d for d in (top, body, original) if d is not None]
    for d in docs:
        limit_segments(d, settings.max_source_chars)
    indexes = {d.role: QuoteIndex(d) for d in docs}
    ref_year = _ref_year(docs, today_d)

    t0 = time.monotonic()
    usage = None
    if ai_output is None:
        extractor = extractor or Extractor(settings)
        ai_output, rec = extractor.extract(docs, today=today_d.isoformat(), case=case)
        usage = rec.__dict__ | {"cost_usd": round(rec.cost_usd(), 6)}
    elapsed = round(time.monotonic() - t0, 2)

    values = {}
    for key, _ in ITEMS:
        ai_item = (ai_output.get("items") or {}).get(key) or {}
        values[key] = {
            role: build_value(key, role, ai_item.get(role), indexes.get(role), ref_year)
            for role in ("top", "body", "original")
        }
    items = judge_all(values)

    q_total = q_ok = 0
    for key, _ in ITEMS:
        for v in values[key].values():
            q_ok += len(v.quotes)
            q_total += len(v.quotes) + len(v.rejected)
    red = [it["name"] for it in items if it["verdict"] in RED]
    result = {
        "version": RESULT_VERSION,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "today": today_d.isoformat(),
        "model": settings.model,
        "case": case,
        "meta": meta or {},
        "sources": {d.role: d.to_dict() for d in docs},
        "items": items,
        "summary": {
            "red_items": red,
            "needs_check": [it["name"] for it in items if it["verdict"] == NEEDS_CHECK],
            "quotes_total": q_total, "quotes_verified": q_ok,
        },
        "deadline_dday": _dday(items, today_d),
        "elapsed_s": elapsed,
        "usage": usage,
        "ai_output": ai_output,
    }
    return result


def _dday(items: list[dict], today_d: date) -> dict | None:
    """원문(없으면 본문) 마감 기준 남은 날. 시각은 그대로 보여 준다."""
    dl = next(it for it in items if it["key"] == "deadline")
    for role in ("original", "body", "top"):
        v = dl["values"].get(role) or {}
        if v.get("status") == "found" and v.get("norm", {}).get("date"):
            d = date.fromisoformat(v["norm"]["date"])
            return {"basis": role, "date": d.isoformat(), "time": v["norm"].get("time"),
                    "days_left": (d - today_d).days}
    return None
