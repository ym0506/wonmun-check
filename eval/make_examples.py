"""시험 실행 결과에서 화면 예시 3건(L07, L20, Y1)을 만든다. AI 호출 없음.

- data/runs/<run>/<ID>.json → web/examples/<ID>.json
- 전화번호·전자우편은 같은 길이의 *로 가린다(글자 위치가 바뀌지 않아 하이라이트가 그대로 맞음).
- AI 원출력(ai_output)은 빼고 판정에 쓴 값만 남긴다.
실행: .venv/bin/python -m eval.make_examples --run r1c
"""

from __future__ import annotations

import argparse
import json
import re

from eval.cases import ORIGINAL_URL, ROOT, load_truth
from wonmun.portals import NOTE_ACTIVITY

EXAMPLES = {
    "L07": "KISTI 2026 DATA·AI 분석 경진대회 (링커리어 ↔ KISTI 대회 페이지)",
    "L20": "밀양 매운맛 쇼츠 공모전 (링커리어 ↔ 밀양시 공지)",
    "Y1": "콘진원 2026 우수인재 연계 기업인턴십 (온통청년 요약 붙여 넣기 ↔ 콘진원 공고)",
}
LABEL = "2026-11-04 공고 기준 저장 결과"
# 공모전이 아닌 공고의 예시(11/10 추가 확인에서 고름, 원문 없이 위쪽 칸 ↔ 본문): 예시 번호 → (링커리어 공고 번호, 제목)
EXTRA = {
    "S1": ("363176", "경기도체육대회 시민서포터즈 (링커리어 대외활동, 위쪽 칸 ↔ 같은 페이지 본문)"),
}
EXTRA_LABEL = "2026-11-10 공고 기준 저장 결과"

_PHONE = re.compile(r"(?<!\d)0\d{1,2}[-.) ]?\d{3,4}[-. ]?\d{4}(?!\d)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def _mask(m: re.Match) -> str:
    return re.sub(r"[0-9A-Za-z]", "*", m.group(0))


def mask(s: str) -> str:
    return _EMAIL.sub(_mask, _PHONE.sub(_mask, s))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="r1c")
    args = ap.parse_args()
    truth = load_truth()
    out_dir = ROOT / "web/examples"
    out_dir.mkdir(parents=True, exist_ok=True)
    for cid, title in EXAMPLES.items():
        d = json.loads((ROOT / "data/runs" / args.run / f"{cid}.json").read_text(encoding="utf-8"))
        d.pop("ai_output", None)
        d["example"] = {"id": cid, "title": title, "label": LABEL, "run": args.run,
                        "summary_url": truth[cid]["summary_url"], "original_url": ORIGINAL_URL[cid]}
        text = mask(json.dumps(d, ensure_ascii=False, indent=1))
        (out_dir / f"{cid}.json").write_text(text, encoding="utf-8")
        print(cid, len(text))
    for ex_id, (act_id, title) in EXTRA.items():
        d = json.loads((ROOT / "data/runs/extra_types" / f"{act_id}.json").read_text(encoding="utf-8"))
        d.pop("ai_output", None)
        notes = d["sources"]["top"].setdefault("notes", [])
        if NOTE_ACTIVITY not in notes:  # 저장 결과를 만든 뒤에 넣은 안내 문구
            notes.append(NOTE_ACTIVITY)
        d["example"] = {"id": ex_id, "title": title, "label": EXTRA_LABEL, "run": "extra_types",
                        "summary_url": f"https://linkareer.com/activity/{act_id}", "original_url": ""}
        text = mask(json.dumps(d, ensure_ascii=False, indent=1))
        (out_dir / f"{ex_id}.json").write_text(text, encoding="utf-8")
        print(ex_id, len(text))


if __name__ == "__main__":
    main()
