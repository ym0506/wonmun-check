"""시험용 표본의 요약 페이지(링커리어)와 원문(정답표 원문_URL 첫 주소)을 엔진의 fetch_url로 한 번씩 받는다.

- 저장: data/runs/test_sources/2026-11-09/<ID>/ (로컬 전용, git 제외)
- 상태 요약(본문 없이): eval/results_test/fetch_log.json
- 봇 확인·로그인·403은 우회하지 않고 실패로 적는다. AI 호출 없음.
실행: .venv/bin/python -m eval.fetch_test [ID ...]
"""

from __future__ import annotations

import hashlib
import json
import sys
import time

from eval.cases_test import ROOT, SOURCES_DIR, TEST_IDS, YOUTH_IDS, load_truth
from wonmun.dates import parse_dates
from wonmun.fetch import FetchError, fetch_url
from wonmun.portals import PortalError, parse_linkareer
from wonmun.textsrc import decode_bytes, doc_from_bytes, sniff_kind

OUT_LOG = ROOT / "eval/results_test/fetch_log.json"


def _save(path, data: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()[:16]


def main(ids: list[str]) -> None:
    truth = load_truth()
    log = json.loads(OUT_LOG.read_text(encoding="utf-8")) if OUT_LOG.exists() else {}
    for cid in ids:
        case = truth[cid]
        d = SOURCES_DIR / cid
        d.mkdir(parents=True, exist_ok=True)
        m = {"id": cid, "title": case["title"], "summary": {}, "original": {}}
        if cid in YOUTH_IDS:
            m["summary"] = {"kind": "paste", "note": "온통청년 summary_text를 붙여 넣은 요약으로 씀(받지 않음)"}
        else:
            url = case["portal_url"]
            t0 = time.monotonic()
            try:
                res = fetch_url(url)
                sha = _save(d / "summary.html", res.content)
                html = decode_bytes(res.content, res.content_type)
                top, body, meta = parse_linkareer(html, url)
                m["summary"] = {"kind": "linkareer", "url": url, "status": res.status, "sha256_16": sha,
                                "fetched_at": res.fetched_at, "fetch_s": round(time.monotonic() - t0, 2),
                                "top_fields": meta["fields"], "recruit_close_at": meta["recruit_close_at"],
                                "homepage_url": meta["homepage_url"], "body_chars": body.char_count(),
                                "body_notes": body.notes}
                (d / "summary_top.txt").write_text(top.full_text(), encoding="utf-8")
                (d / "summary_body.txt").write_text(body.full_text(), encoding="utf-8")
            except (FetchError, PortalError) as e:
                m["summary"] = {"kind": "linkareer", "url": url, "error": str(e),
                                "fetch_s": round(time.monotonic() - t0, 2)}
            time.sleep(1.0)
        ourl = case["original_url"]
        t0 = time.monotonic()
        try:
            res = fetch_url(ourl)
            kind = sniff_kind(res.content, res.final_url, res.content_type)
            ext = {"pdf": "pdf", "hwpx": "hwpx", "hwp-binary": "hwp"}.get(kind, "html")
            sha = _save(d / f"original.{ext}", res.content)
            info = {"url": ourl, "final_url": res.final_url, "status": res.status,
                    "content_type": res.content_type, "kind": kind, "file": f"original.{ext}",
                    "bytes": len(res.content), "sha256_16": sha, "fetched_at": res.fetched_at,
                    "fetch_s": round(time.monotonic() - t0, 2)}
            try:
                doc = doc_from_bytes(res.content, "original", ourl, filename=res.final_url,
                                     content_type=res.content_type)
                text = doc.full_text()
                (d / "original.txt").write_text(text, encoding="utf-8")
                info |= {"chars": doc.char_count(), "segments": len(doc.segments),
                         "dates_found": len(parse_dates(text, 2026)), "notes": doc.notes}
            except ValueError as e:
                info["parse_error"] = str(e)
            m["original"] = info
        except FetchError as e:
            m["original"] = {"url": ourl, "error": str(e), "fetch_s": round(time.monotonic() - t0, 2)}
        time.sleep(1.0)
        (d / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
        log[cid] = {
            "summary": {k: v for k, v in m["summary"].items()
                        if k in ("kind", "status", "error", "body_chars", "fetch_s", "recruit_close_at",
                                 "homepage_url", "note")}
                       | ({"top_접수기간": m["summary"]["top_fields"].get("접수기간"),
                           "top_참여대상": m["summary"]["top_fields"].get("참여대상")}
                          if m["summary"].get("top_fields") else {}),
            "original": {k: v for k, v in m["original"].items()
                         if k in ("url", "final_url", "status", "content_type", "kind", "bytes", "chars",
                                  "segments", "dates_found", "notes", "error", "parse_error", "fetch_s")
                         and v not in (None, [])},
        }
        print(cid, json.dumps(log[cid], ensure_ascii=False))
    OUT_LOG.parent.mkdir(parents=True, exist_ok=True)
    OUT_LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:] or TEST_IDS)
