"""비교군 ② 규칙만: '접수기간|공모기간|신청기간|원서접수' 줄의 마지막 날짜를 마감으로 읽는다. AI 호출 없음.

요약(위쪽 칸 또는 붙여 넣은 글)과 원문에서 각각 그 줄을 찾고, 판정은 도구와 같은 마감 규칙
(날짜 다르면 불일치, 같은 날 원문 시각이 23:59·24:00이 아니고 요약에 시각이 없으면 시각 누락)을 쓴다.
실행: .venv/bin/python -m eval.baseline_regex
"""

from __future__ import annotations

import json
import re

from eval.cases import MAIN_IDS, ROOT, load_truth
from eval.run_tool import load_sources
from wonmun.dates import END_OF_DAY, all_points, guess_ref_year

KEY_LINE = re.compile(r"접수\s*기간|공모\s*기간|신청\s*기간|원서\s*접수")


def regex_deadline(doc, ref_year: int):
    for seg in doc.segments:
        if KEY_LINE.search(seg.text):
            pts = all_points(seg.text, ref_year)
            if pts:
                p = pts[-1]
                return {"date": p.date.isoformat(), "time": p.time, "line": seg.text, "sid": seg.sid}
    return None


def judge(a, b) -> str:
    if not a or not b:
        return "확인 필요"
    if a["date"] != b["date"]:
        return "불일치"
    if b["time"] and b["time"] not in END_OF_DAY and not a["time"]:
        return "시각 누락"
    return "다른 점을 찾지 못함"


def main() -> None:
    truth = load_truth()
    out = {}
    for cid in MAIN_IDS:
        top, body, orig, _ = load_sources(cid)
        ry = guess_ref_year(orig.full_text() + top.full_text(), 2026)
        a = regex_deadline(top, ry)
        b = regex_deadline(orig, ry)
        v = judge(a, b)
        out[cid] = {"summary": a, "original": b, "verdict": v, "csv": truth[cid]["items"]["deadline"]["label"]}
        print(cid, v, "| CSV", out[cid]["csv"], "|", a and a["date"], a and a["time"], "|", b and b["date"], b and b["time"],
              "|", b and b["line"][:60])
    targets = [c for c in MAIN_IDS if out[c]["csv"] in ("불일치", "시각 누락")]
    found = [c for c in targets if out[c]["verdict"] in ("불일치", "시각 누락")]
    fa = [c for c in MAIN_IDS if out[c]["csv"] in ("일치", "원문에도 없음") and out[c]["verdict"] in ("불일치", "시각 누락")]
    na = [c for c in MAIN_IDS if out[c]["verdict"] == "확인 필요"]
    summary = {"targets": targets, "found": found, "false_alarms": fa, "cannot_read": na}
    print(json.dumps(summary, ensure_ascii=False))
    (ROOT / "eval/results/baseline_regex.json").write_text(
        json.dumps({"cases": out, "summary": summary}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
