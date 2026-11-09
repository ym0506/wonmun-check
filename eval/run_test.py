"""시험용 표본(11/9)으로 도구를 돌린다. 엔진(wonmun/)은 그대로 쓴다(고치지 않음).

- 입력: eval.fetch_test로 받아 둔 원본(data/runs/test_sources/, git 제외)
  링커리어 = 포털 페이지(위쪽 칸 + 본문), 온통청년 = summary_text 붙여 넣기(본문 없음)
  원문 = 정답표 원문_URL 첫 주소를 받은 것. eval.cases_test.NO_ORIGINAL 공고는 원문 없이.
- 전체 결과: data/runs/test/<run>/<ID>.json (git 제외), 비교용 요약: eval/results_test/<run>.json
- AI 호출 기록: eval/api_calls_test.jsonl, 이 작업 전체 60회 상한(기록 줄 수 기준).
- 엔진 안에서 오류가 나면 고치지 않고 그 공고를 '실행 실패'로 적는다.

실행
  .venv/bin/python -m eval.run_test --run t1                 # 15건
  .venv/bin/python -m eval.run_test --run t2 T02 T06 T10 T12 R2
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback

from eval.cases_test import NO_ORIGINAL, ROOT, SOURCES_DIR, TEST_IDS, TODAY, YOUTH_IDS, load_truth, youth_paste
from eval.run_tool import compact
from wonmun.config import Settings
from wonmun.llm import Extractor
from wonmun.pipeline import run_check
from wonmun.portals import parse_linkareer
from wonmun.textsrc import decode_bytes, doc_from_bytes, text_doc

LEDGER = ROOT / "eval/api_calls_test.jsonl"
CALL_BUDGET = 60
RESULTS = ROOT / "eval/results_test"


def load_sources(cid: str):
    d = SOURCES_DIR / cid
    m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    if cid in YOUTH_IDS:
        top = text_doc(youth_paste(cid), "top", "붙여 넣은 요약", kind="paste")
        top.label = "붙여 넣은 요약"
        body, meta = None, {"portal": None, "summary_note": "온통청년 summary_text(11/9 캡처) 붙여 넣기"}
    else:
        html = decode_bytes((d / "summary.html").read_bytes())
        top, body, meta = parse_linkareer(html, m["summary"]["url"])
    orig = None
    if cid in NO_ORIGINAL:
        meta["original_note"] = "원문 없이 실행: " + NO_ORIGINAL[cid]
    else:
        o = m["original"]
        f = d / o["file"]
        orig = doc_from_bytes(f.read_bytes(), "original", o["url"], filename=o.get("final_url") or f.name,
                              content_type=o.get("content_type", ""))
    meta["fetched"] = f"{TODAY} 받은 페이지 기준"
    return top, body, orig, meta


def make_settings() -> Settings:
    s = Settings()
    s.ledger_path = LEDGER
    s.call_budget = CALL_BUDGET
    return s


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("ids", nargs="*")
    args = ap.parse_args()
    ids = args.ids or TEST_IDS
    load_truth()
    settings = make_settings()
    extractor = Extractor(settings)
    out_dir = ROOT / "data/runs/test" / args.run
    out_dir.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    res_path = RESULTS / f"{args.run}.json"
    compact_all = json.loads(res_path.read_text(encoding="utf-8")) if res_path.exists() else {}
    for cid in ids:
        t0 = time.monotonic()
        try:
            top, body, orig, meta = load_sources(cid)
            result = run_check(top, body, orig, extractor=extractor, settings=settings, today=TODAY,
                               case=cid, meta=meta)
        except Exception as e:  # noqa: BLE001 - 엔진 오류는 고치지 않고 실패로 센다
            err = f"{type(e).__name__}: {e}"
            print(cid, "실행 실패:", err, file=sys.stderr)
            compact_all[cid] = {"case": cid, "error": err, "traceback": traceback.format_exc()[-1500:],
                                "pipeline_s": round(time.monotonic() - t0, 2)}
            res_path.write_text(json.dumps(compact_all, ensure_ascii=False, indent=1), encoding="utf-8")
            continue
        result["pipeline_s"] = round(time.monotonic() - t0, 2)
        (out_dir / f"{cid}.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        c = compact(result)
        c["has_original"] = orig is not None
        c["has_body"] = body is not None
        compact_all[cid] = c
        verdicts = {it["key"]: it["verdict"] for it in result["items"]}
        u = result.get("usage") or {}
        print(cid, f"{result['elapsed_s']}s", u.get("input_tokens"), u.get("output_tokens"),
              json.dumps({k: verdicts[k] for k in ("deadline", "eligibility")}, ensure_ascii=False))
        res_path.write_text(json.dumps(compact_all, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
