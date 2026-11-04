"""저장해 둔 원본으로 도구를 돌린다(네트워크로 다시 받지 않음).

실행 예
  .venv/bin/python -m eval.run_tool --run r1                     # 본 표본, AI 호출
  .venv/bin/python -m eval.run_tool --run r1s --stage1 L01 L12     # 원문 없이 1단계만
  .venv/bin/python -m eval.run_tool --rescore r1 --run r1b         # AI 출력 재사용, 규칙만 다시(호출 0)

전체 결과(원문 글 포함)는 data/runs/<run>/ (git 제외), 비교용 요약은 eval/results/<run>.json.
API 호출은 eval/api_calls.jsonl에 기록하고 100회 상한을 건다.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from eval.cases import MAIN_IDS, ROOT, SOURCES_DIR, SUMMARY_PASTE, load_truth
from wonmun.config import Settings
from wonmun.llm import Extractor, LLMError
from wonmun.pipeline import run_check
from wonmun.portals import parse_linkareer
from wonmun.textsrc import decode_bytes, doc_from_bytes, text_doc

LEDGER = ROOT / "eval/api_calls.jsonl"
CALL_BUDGET = 100
TODAY = "2026-11-04"


def load_sources(cid: str, with_original: bool = True):
    d = SOURCES_DIR / cid
    m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    if cid in SUMMARY_PASTE:
        top = text_doc(SUMMARY_PASTE[cid].read_text(encoding="utf-8"), "top", "붙여 넣은 요약", kind="paste")
        top.label = "붙여 넣은 요약"
        body, meta = None, {"portal": None, "summary_note": m["summary"].get("note")}
    else:
        html = decode_bytes((d / "summary.html").read_bytes())
        top, body, meta = parse_linkareer(html, m["summary"]["url"])
    orig = None
    if with_original:
        f = d / m["original"]["file"]
        orig = doc_from_bytes(f.read_bytes(), "original", m["original"]["url"], filename=f.name)
    meta["fetched"] = FETCH_NOTE
    return top, body, orig, meta


FETCH_NOTE = f"{TODAY} 받은 페이지 기준"


def compact(result: dict) -> dict:
    """비교·채점에 필요한 것만(원문 글 제외)."""
    items = {}
    for it in result["items"]:
        vals = {}
        for role, v in it["values"].items():
            if v["status"] == "not_given":
                continue
            vals[role] = {"status": v["status"], "value": v["value"], "value_by": v["value_by"],
                          "norm": v["norm"], "quotes": [q["text"] for q in v["quotes"]],
                          "rejected": v["rejected_quotes"], "note": v["note"]}
        items[it["key"]] = {"verdict": it["verdict"], "reason": it["reason"],
                            "stage1": it["stage1"]["verdict"] if it["stage1"] else None,
                            "stage2": it["stage2"]["verdict"] if it["stage2"] else None,
                            "values": vals}
    return {"case": result["case"], "items": items, "summary": result["summary"],
            "elapsed_s": result["elapsed_s"], "pipeline_s": result.get("pipeline_s"),
            "usage": result["usage"], "dday": result["deadline_dday"],
            "source_chars": {r: sum(len(s["text"]) for s in d["segments"]) for r, d in result["sources"].items()},
            "source_notes": {r: d["notes"] for r, d in result["sources"].items() if d["notes"]}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--stage1", action="store_true", help="원문 없이 칸↔본문만")
    ap.add_argument("--rescore", help="이 run의 AI 출력을 재사용(호출 없음)")
    ap.add_argument("ids", nargs="*")
    args = ap.parse_args()
    ids = args.ids or MAIN_IDS
    load_truth()  # CSV가 읽히는지 먼저 확인

    settings = Settings()
    settings.ledger_path = LEDGER
    settings.call_budget = CALL_BUDGET
    extractor = None if args.rescore else Extractor(settings)

    out_dir = ROOT / "data/runs" / args.run
    out_dir.mkdir(parents=True, exist_ok=True)
    res_path = ROOT / "eval/results" / f"{args.run}.json"
    res_path.parent.mkdir(parents=True, exist_ok=True)
    compact_all = json.loads(res_path.read_text(encoding="utf-8")) if res_path.exists() else {}
    for cid in ids:
        top, body, orig, meta = load_sources(cid, with_original=not args.stage1)
        ai_output = None
        if args.rescore:
            prev = json.loads((ROOT / "data/runs" / args.rescore / f"{cid}.json").read_text(encoding="utf-8"))
            ai_output = prev["ai_output"]
        t0 = time.monotonic()
        try:
            result = run_check(top, body, orig, extractor=extractor, settings=settings, today=TODAY,
                               case=cid, meta=meta, ai_output=ai_output)
        except LLMError as e:
            print(cid, "실패:", e, file=sys.stderr)
            compact_all[cid] = {"case": cid, "error": str(e)}
            continue
        result["pipeline_s"] = round(time.monotonic() - t0, 2)
        if args.rescore:
            result["usage"] = prev.get("usage")
            result["elapsed_s"] = prev.get("elapsed_s")
            result["pipeline_s"] = prev.get("pipeline_s")
        (out_dir / f"{cid}.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        compact_all[cid] = compact(result)
        verdicts = {it["key"]: it["verdict"] for it in result["items"]}
        u = result.get("usage") or {}
        print(cid, f"{result['elapsed_s']}s", u.get("input_tokens"), u.get("output_tokens"),
              json.dumps(verdicts, ensure_ascii=False))
        res_path.write_text(json.dumps(compact_all, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
