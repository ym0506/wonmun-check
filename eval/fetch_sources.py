"""개발용 표본의 요약 페이지와 원문을 받아 data/dev_sources/<날짜>/<ID>/ 에 저장한다(로컬 전용, git 제외).

실행: .venv/bin/python -m eval.fetch_sources
결과: 각 폴더의 manifest.json, 전체 요약 eval/fetch_log.json(본문 없이 상태만)
봇 확인 화면·403은 우회하지 않고 실패로 기록한다.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time

from eval.cases import (FETCH_DATE, ORIGINAL_URL, ROOT, SOURCES_DIR, SUMMARY_PASTE, candidate_ids,
                        load_truth)
from wonmun.dates import parse_dates
from wonmun.fetch import FetchError, fetch_url
from wonmun.portals import PortalError, parse_linkareer
from wonmun.textsrc import decode_bytes, doc_from_bytes, sniff_kind


def _save(path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()[:16]


def main(ids: list[str]) -> None:
    truth = load_truth()
    log = {}
    for cid in ids:
        case = truth[cid]
        d = SOURCES_DIR / cid
        m = {"id": cid, "title": case["title"], "fetch_date": FETCH_DATE, "summary": {}, "original": {}}
        # ---- 요약
        if cid in SUMMARY_PASTE:
            txt = SUMMARY_PASTE[cid].read_text(encoding="utf-8")
            m["summary"] = {"kind": "paste", "source": str(SUMMARY_PASTE[cid].relative_to(ROOT)),
                            "note": "온통청년 요약 칸은 서버 HTML에 비어 있어(자바스크립트로 채움) 붙여 넣기로 대신함",
                            "chars": len(txt)}
        else:
            url = case["summary_url"]
            try:
                res = fetch_url(url)
                sha = _save(d / "summary.html", res.content)
                html = decode_bytes(res.content, res.content_type)
                top, body, meta = parse_linkareer(html, url)
                m["summary"] = {"kind": "linkareer", "url": url, "status": res.status, "sha256_16": sha,
                                "fetched_at": res.fetched_at, "top_fields": meta["fields"],
                                "recruit_close_at": meta["recruit_close_at"],
                                "homepage_url": meta["homepage_url"], "body_chars": body.char_count()}
            except (FetchError, PortalError) as e:
                m["summary"] = {"kind": "linkareer", "url": url, "error": str(e)}
            time.sleep(1.0)
        # ---- 원문
        ourl = ORIGINAL_URL.get(cid)
        if not ourl:
            m["original"] = {"error": "원문 주소가 CSV에 특정되지 않음"}
        else:
            try:
                res = fetch_url(ourl)
                kind = sniff_kind(res.content, res.final_url, res.content_type)
                ext = {"pdf": "pdf", "hwpx": "hwpx"}.get(kind, "html")
                sha = _save(d / f"original.{ext}", res.content)
                doc = doc_from_bytes(res.content, "original", ourl, filename=res.final_url,
                                     content_type=res.content_type)
                text = doc.full_text()
                m["original"] = {"url": ourl, "final_url": res.final_url, "status": res.status,
                                 "content_type": res.content_type, "kind": kind, "file": f"original.{ext}",
                                 "sha256_16": sha, "fetched_at": res.fetched_at, "chars": doc.char_count(),
                                 "segments": len(doc.segments), "dates_found": len(parse_dates(text, 2026)),
                                 "notes": doc.notes}
            except (FetchError, ValueError) as e:
                m["original"] = {"url": ourl, "error": str(e)}
            time.sleep(1.0)
        d.mkdir(parents=True, exist_ok=True)
        (d / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
        log[cid] = {
            "summary": {k: m["summary"].get(k) for k in ("kind", "status", "error", "body_chars", "chars")
                        if m["summary"].get(k) is not None}
                       | ({"top_접수기간": m["summary"].get("top_fields", {}).get("접수기간"),
                           "top_참여대상": m["summary"].get("top_fields", {}).get("참여대상"),
                           "top_시상규모": m["summary"].get("top_fields", {}).get("시상규모"),
                           "recruit_close_at": m["summary"].get("recruit_close_at"),
                           "homepage_url": m["summary"].get("homepage_url")}
                          if m["summary"].get("top_fields") else {}),
            "original": {k: m["original"].get(k) for k in ("url", "status", "kind", "chars", "dates_found",
                                                           "notes", "error")
                         if m["original"].get(k) not in (None, [])},
        }
        print(cid, json.dumps(log[cid], ensure_ascii=False))
    out = ROOT / "eval/fetch_log.json"
    old = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    old.update(log)
    out.write_text(json.dumps(old, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:] or candidate_ids())
