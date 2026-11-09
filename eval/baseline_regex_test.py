"""비교군 ② 규칙만(정규식) 시험용 표본: eval/baseline_regex.py와 같은 규칙(마감만). AI 호출 없음.

'접수기간|공모기간|신청기간|원서접수' 줄의 마지막 날짜를 마감으로 읽고, 요약(위쪽 칸 또는 붙여 넣은 글) ↔ 원문을 비교한다.
원문 없이 돌린 공고는 기존 방식대로 '확인 필요'(원문 줄을 읽을 수 없음).
--with-body: 원문이 없을 때 포털 본문을 원문 대신 준다(도구와 같은 입력, 공정성 확인용).
실행: .venv/bin/python -m eval.baseline_regex_test [--with-body]
"""

from __future__ import annotations

import json
import sys

from eval.baseline_regex import judge, regex_deadline
from eval.cases_test import TEST_IDS, load_truth
from eval.run_test import RESULTS, load_sources
from wonmun.dates import guess_ref_year


def main() -> None:
    with_body = "--with-body" in sys.argv
    truth = load_truth()
    out = {}
    for cid in TEST_IDS:
        top, body, orig, _ = load_sources(cid)
        used_body = with_body and orig is None
        if used_body:
            orig = body
        ry = guess_ref_year((orig.full_text() if orig else "") + top.full_text(), 2026)
        a = regex_deadline(top, ry)
        b = regex_deadline(orig, ry) if orig else None
        v = judge(a, b)
        out[cid] = {"summary": a, "original": b, "verdict": v, "has_original": orig is not None and not used_body, "used_body": used_body,
                    "truth": truth[cid]["deadline"]["label"]}
        print(cid, v, "| 정답", out[cid]["truth"], "|", a and a["date"], a and a["time"], "|",
              b and b["date"], b and b["time"], "|", (b and b["line"][:60]) or "")
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / ("baseline_regex_body.json" if with_body else "baseline_regex.json")).write_text(json.dumps({"cases": out}, ensure_ascii=False, indent=1),
                                                 encoding="utf-8")


if __name__ == "__main__":
    main()
