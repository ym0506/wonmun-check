"""git에 넣는 시험 결과에서 전화번호·전자우편·담당자 이름을 같은 길이로 가린다(채점에는 영향 없음).

실행: .venv/bin/python -m eval.redact
- eval/results/*.json, eval/fetch_log.json: 그 자리에서 가림
- data/runs/baseline_chat/*.md(원본) → eval/results/baseline_chat/*.md(가린 사본)
"""

from __future__ import annotations

from eval.cases import ROOT
from eval.make_examples import mask

# 원문 게시판에 적힌 담당자 이름처럼 가릴 낱말은 data/redact_names.txt(git 제외)에 한 줄에 하나씩 둔다.
_NAMES_FILE = ROOT / "data/redact_names.txt"
NAMES = [x.strip() for x in _NAMES_FILE.read_text(encoding="utf-8").splitlines() if x.strip()] if _NAMES_FILE.exists() else []


def clean(text: str) -> str:
    text = mask(text)
    for n in NAMES:
        text = text.replace(n, "○" * len(n))
    return text


def main() -> None:
    targets = list((ROOT / "eval/results").glob("*.json")) + [ROOT / "eval/fetch_log.json"]
    for p in targets:
        t = p.read_text(encoding="utf-8")
        c = clean(t)
        if c != t:
            p.write_text(c, encoding="utf-8")
            print("가림:", p.relative_to(ROOT))
    src = ROOT / "data/runs/baseline_chat"
    dst = ROOT / "eval/results/baseline_chat"
    dst.mkdir(parents=True, exist_ok=True)
    for p in sorted(src.glob("*")):
        (dst / p.name).write_text(clean(p.read_text(encoding="utf-8")), encoding="utf-8")
    print("비교군 답 사본:", len(list(dst.glob('*.md'))), "개")


if __name__ == "__main__":
    main()
