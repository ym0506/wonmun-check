"""비교군 ① 시험용 표본: 같은 모델에 한 번 묻기(eval/baseline_chat.py와 같은 질문·같은 입력 방식).

- 질문: "요약과 원문의 다른 점을 찾아 근거 문장과 함께 알려 줘." (build_prompt 그대로)
- 입력: 도구와 같은 출처 글(요약 위쪽 칸·붙여 넣은 요약, 요약 본문, 원문). 원문 없이 돌린 공고는 원문 없이.
- 답 원본: data/runs/test/baseline_chat/<ID>.md (git 제외), 전화번호·전자우편을 가린 사본: eval/results_test/baseline_chat/
- 판정: Claude가 답을 직접 읽고 eval/results_test/baseline_chat_reading.json에 근거 문장과 함께 적는다.
  이 스크립트는 인용 일치율(답 속 따옴표 문장이 출처에 글자 그대로 있는지)만 자동으로 센다.

실행
  .venv/bin/python -m eval.baseline_chat_test --ask    # AI 호출(공고 수만큼)
  .venv/bin/python -m eval.baseline_chat_test          # 저장된 답으로 인용 일치율만
"""

from __future__ import annotations

import argparse
import json

from eval.baseline_chat import build_prompt, quotes_in
from eval.cases_test import ROOT, TEST_IDS
from eval.make_examples import mask
from eval.run_test import RESULTS, load_sources, make_settings
from wonmun.llm import Extractor
from wonmun.quotes import QuoteIndex, norm_ws

OUT = ROOT / "data/runs/test/baseline_chat"
COPY = RESULTS / "baseline_chat"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ask", action="store_true")
    ap.add_argument("ids", nargs="*")
    args = ap.parse_args()
    ids = args.ids or TEST_IDS
    OUT.mkdir(parents=True, exist_ok=True)
    COPY.mkdir(parents=True, exist_ok=True)
    if args.ask:
        ex = Extractor(make_settings())
        for cid in ids:
            top, body, orig, _ = load_sources(cid)
            docs = [d for d in (top, body, orig) if d]
            try:
                text, rec = ex.ask_plain(build_prompt(docs), case=cid)
            except Exception as e:  # noqa: BLE001
                print(cid, "실패:", type(e).__name__, e)
                (OUT / f"{cid}.error.txt").write_text(f"{type(e).__name__}: {e}", encoding="utf-8")
                continue
            (OUT / f"{cid}.md").write_text(text, encoding="utf-8")
            (OUT / f"{cid}.usage.json").write_text(json.dumps(rec.__dict__, ensure_ascii=False), encoding="utf-8")
            print(cid, rec.latency_s, rec.input_tokens, rec.output_tokens)

    res = {"cases": {}, "quotes_total": 0, "quotes_ok": 0}
    for cid in TEST_IDS:
        p = OUT / f"{cid}.md"
        if not p.exists():
            continue
        ans = p.read_text(encoding="utf-8")
        (COPY / f"{cid}.md").write_text(mask(ans), encoding="utf-8")
        top, body, orig, _ = load_sources(cid)
        idxs = [QuoteIndex(d) for d in (top, body, orig) if d]
        qs = quotes_in(ans)
        ok = [q for q in qs if any(norm_ws(q) in ix.joined for ix in idxs)]
        res["quotes_total"] += len(qs)
        res["quotes_ok"] += len(ok)
        u = json.loads((OUT / f"{cid}.usage.json").read_text(encoding="utf-8"))
        res["cases"][cid] = {"quotes": len(qs), "quotes_ok": len(ok),
                             "bad_quotes": [mask(q) for q in qs if q not in ok][:8],
                             "latency_s": u.get("latency_s"),
                             "tokens": [u.get("input_tokens"), u.get("output_tokens")],
                             "has_original": orig is not None}
        print(cid, len(qs), len(ok), u.get("latency_s"))
    print("인용", res["quotes_ok"], "/", res["quotes_total"])
    (RESULTS / "baseline_chat_auto.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
