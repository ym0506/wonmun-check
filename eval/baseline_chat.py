"""비교군 ① 같은 모델에 한 번 묻기: "요약과 원문의 다른 점을 찾아 근거 문장과 함께 알려 줘."

- 도구와 같은 출처 글(요약 위쪽 칸, 요약 본문, 원문)을 위치 번호 없이 그대로 넣는다.
- 답은 data/runs/baseline_chat/<ID>.md(원본, git 제외)에 저장하고, eval.redact로 가린 사본을
  eval/results/baseline_chat/에 둔다.
- 채점은 '사람이 읽듯' 규칙으로 한다: 답을 문단·목록 단위로 나누고, 그 덩어리 안에
  마감(또는 자격) 낱말 + 원문의 정답 값(날짜·시각·조건 낱말) + 차이를 말하는 낱말이 함께 있으면 찾은 것으로 센다.
  규칙 파서는 거칠어서, 에이전트가 답을 직접 읽고 고친 값을 baseline_chat_reading.json에 따로 적는다.

실행
  .venv/bin/python -m eval.baseline_chat --ask      # AI 호출(공고 수만큼)
  .venv/bin/python -m eval.baseline_chat            # 저장된 답으로 채점만
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date

from eval.cases import MAIN_IDS, ROOT, load_truth
from eval.run_tool import CALL_BUDGET, LEDGER, load_sources
from wonmun.config import Settings
from wonmun.dates import all_points, standalone_times
from wonmun.llm import Extractor
from wonmun.quotes import QuoteIndex, norm_ws

OUT = ROOT / "data/runs/baseline_chat"  # 원래 답(로컬 전용). eval/results/baseline_chat/에는 전화번호 등을 가린 사본
QUESTION = "요약과 원문의 다른 점을 찾아 근거 문장과 함께 알려 줘."

# 마감·자격 차이 정답(CSV 원문_값에서 옮김)
TARGETS = {
    ("L02", "deadline"): {"kind": "time", "time": "17:00"},
    ("L07", "deadline"): {"kind": "date", "orig": "2026-11-06", "summ": "2026-11-25"},
    ("L20", "deadline"): {"kind": "date", "orig": "2026-11-07", "summ": "2026-11-15"},
    ("Y1", "deadline"): {"kind": "time", "time": "11:00"},
    ("L02", "eligibility"): {"kind": "terms", "terms": ["19세", "고등학교", "고졸"]},
    ("L13", "eligibility"): {"kind": "terms", "terms": ["대학생", "휴학생"]},
    ("Y1", "eligibility"): {"kind": "terms", "terms": ["기업", "법인"]},
}
DL_WORD = re.compile(r"마감|접수|기간|제출|신청|일정|D-")
EL_WORD = re.compile(r"자격|대상|주체|신청\s*가능|누가|참가자|참여자")
DIFF_WORD = re.compile(r"다르|다릅|불일치|차이|상이|아닌|아니|틀|오류|잘못|누락|없|빠져|빠짐|빠졌|명시되지|표기되지|늦|빠르|반면|그러나|하지만|만 적|만 표기|vs|→|↔")
TIME_WORD = re.compile(r"시각|시간|누락|없|명시|빠|표기|언급|까지|마감")


def build_prompt(docs) -> str:
    parts = [f"아래는 한 공고의 요약(포털 글)과 원문(주최 측 공고)입니다. {QUESTION}", ""]
    names = {"top": "[요약 - 위쪽 칸]", "body": "[요약 - 본문]", "original": "[원문]"}
    for d in docs:
        if d.role == "top" and d.kind == "paste":
            parts.append("[요약]")
        else:
            parts.append(names[d.role])
        parts.append(d.full_text())
        parts.append("")
    return "\n".join(parts)


def chunks(answer: str) -> list[str]:
    blocks = re.split(r"\n\s*\n|\n(?=\s*(?:[-*•]|\d+[.)]|#{1,4}\s|\|))", answer)
    return [b.strip() for b in blocks if b.strip()]


def _md(d: str) -> tuple[int, int]:
    x = date.fromisoformat(d)
    return x.month, x.day


def found_target(answer: str, spec: dict) -> bool:
    for ch in chunks(answer):
        if spec["kind"] == "date":
            if not DL_WORD.search(ch):
                continue
            mds = {(p.date.month, p.date.day) for p in all_points(ch, 2026)}
            if _md(spec["orig"]) in mds and (_md(spec["summ"]) in mds or DIFF_WORD.search(ch)):
                return True
        elif spec["kind"] == "time":
            if DL_WORD.search(ch) and spec["time"] in standalone_times(ch) and TIME_WORD.search(ch) and DIFF_WORD.search(ch):
                return True
        else:
            if EL_WORD.search(ch) and DIFF_WORD.search(ch) and any(t in ch for t in spec["terms"]):
                return True
    return False


def claims_diff(answer: str, item: str) -> bool:
    """정답이 '일치'인 칸에서 답이 차이를 주장하는지(잘못 경고 후보)."""
    word = DL_WORD if item == "deadline" else EL_WORD
    for ch in chunks(answer):
        if word.search(ch) and DIFF_WORD.search(ch):
            if item == "deadline" and not (all_points(ch, 2026) or standalone_times(ch)):
                continue
            return True
    return False


# 따옴표 짝: “…”, 「…」, 『…』, `…`, "…"(여는 따옴표 바로 뒤·닫는 따옴표 바로 앞이 공백이 아닌 것만)
_QUOTE = re.compile(r"“([^”\n]{8,200})”|「([^」\n]{8,200})」|『([^』\n]{8,200})』|`([^`\n]{8,200})`"
                    r"|(?<![\w])\"(?! )([^\"\n]{8,200})(?<! )\"")


def quotes_in(answer: str) -> list[str]:
    qs = [next(g for g in m.groups() if g) for m in _QUOTE.finditer(answer)]
    for line in answer.splitlines():
        if line.strip().startswith(">"):
            q = line.strip().lstrip(">").strip()
            if len(q) >= 8:
                qs.append(q)
    return qs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ask", action="store_true")
    ap.add_argument("ids", nargs="*")
    args = ap.parse_args()
    ids = args.ids or MAIN_IDS
    OUT.mkdir(parents=True, exist_ok=True)
    if args.ask:
        s = Settings()
        s.ledger_path, s.call_budget = LEDGER, CALL_BUDGET
        ex = Extractor(s)
        for cid in ids:
            top, body, orig, _ = load_sources(cid)
            docs = [d for d in (top, body, orig) if d]
            text, rec = ex.ask_plain(build_prompt(docs), case=cid)
            (OUT / f"{cid}.md").write_text(text, encoding="utf-8")
            (OUT / f"{cid}.usage.json").write_text(json.dumps(rec.__dict__, ensure_ascii=False), encoding="utf-8")
            print(cid, rec.latency_s, rec.input_tokens, rec.output_tokens)

    truth = load_truth()
    res = {"cases": {}, "found": [], "missed": [], "false_alarms": [], "quotes_total": 0, "quotes_ok": 0}
    for cid in MAIN_IDS:
        p = OUT / f"{cid}.md"
        if not p.exists():
            continue
        ans = p.read_text(encoding="utf-8")
        top, body, orig, _ = load_sources(cid)
        idxs = [QuoteIndex(d) for d in (top, body, orig) if d]
        qs = quotes_in(ans)
        ok = [q for q in qs if any(norm_ws(q) in ix.joined for ix in idxs)]
        res["quotes_total"] += len(qs)
        res["quotes_ok"] += len(ok)
        case = {"quotes": len(qs), "quotes_ok": len(ok), "bad_quotes": [q for q in qs if q not in ok][:5]}
        for item in ("deadline", "eligibility"):
            spec = TARGETS.get((cid, item))
            label = truth[cid]["items"][item]["label"]
            if spec:
                hit = found_target(ans, spec)
                case[item] = "찾음" if hit else "못 찾음"
                (res["found"] if hit else res["missed"]).append(f"{cid} {item}")
            elif label in ("일치", "원문에도 없음"):
                fa = claims_diff(ans, item)
                case[item] = "차이 주장(잘못 경고 후보)" if fa else "차이 주장 없음"
                if fa:
                    res["false_alarms"].append(f"{cid} {item}")
            else:
                case[item] = f"CSV {label}(채점 제외)"
        u = json.loads((OUT / f"{cid}.usage.json").read_text(encoding="utf-8")) if (OUT / f"{cid}.usage.json").exists() else {}
        case["latency_s"] = u.get("latency_s")
        case["tokens"] = [u.get("input_tokens"), u.get("output_tokens")]
        res["cases"][cid] = case
        print(cid, json.dumps(case, ensure_ascii=False)[:300])
    print(json.dumps({k: res[k] for k in ("found", "missed", "false_alarms", "quotes_total", "quotes_ok")},
                     ensure_ascii=False))
    (ROOT / "eval/results/baseline_chat_auto.json").write_text(json.dumps(res, ensure_ascii=False, indent=1),
                                                               encoding="utf-8")


if __name__ == "__main__":
    main()
