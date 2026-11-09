"""공모전이 아닌 공고(대외활동, 인턴)에도 같은 문제가 있는지 보는 추가 확인. 정답표 없이 돌린다.

- 표본 규칙(돌리기 전에 정함): 링커리어 대외활동 목록 1쪽(모집 중, 최신 등록순)과 채용 목록의 인턴 필터 1쪽(최신순)에서
  광고 칸을 빼고 위에서부터 각 10건. 목록 페이지는 scratch에 받아 둔 HTML에서 읽는다(--lists 폴더).
- 원문 없이 포털 페이지 안의 위쪽 칸과 본문만 대조한다(1단계). 공고마다 AI 호출 1회.
- 정답이 없으므로 '찾은 비율'은 말할 수 없다. 빨갛게 나온 마감·자격 칸만 사람이(Claude) 페이지를 열어 맞는지 본다.
- 전체 결과: data/runs/extra_types/<ID>.json (git 제외), 요약: eval/results_extra/extra_types.json

실행: .venv/bin/python -m eval.extra_types --lists <목록 HTML 폴더> [--today 2026-11-10] [--only 인턴]
"""

from __future__ import annotations

import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from eval.run_tool import compact
from wonmun.config import Settings
from wonmun.fetch import FetchError, fetch_url
from wonmun.llm import Extractor
from wonmun.pipeline import run_check
from wonmun.portals import PortalError, parse_linkareer
from wonmun.textsrc import decode_bytes

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data/runs/extra_types"
RESULTS = ROOT / "eval/results_extra/extra_types.json"
LEDGER = ROOT / "eval/api_calls_extra.jsonl"
PER_TYPE = 10


def list_ids(html: str) -> list[tuple[str, str, str]]:
    d = json.loads(re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S).group(1))
    st = d["props"]["pageProps"]["__APOLLO_STATE__"]
    key = next(k for k in st["ROOT_QUERY"] if k.startswith("activities("))  # 광고 칸은 다른 키에 들어 있다
    out = []
    for n in st["ROOT_QUERY"][key]["nodes"][:PER_TYPE]:
        a = st[n["__ref"]]
        out.append((str(a["id"]), a.get("title") or "", a.get("organizationName") or ""))
    return out


def run_one(kind: str, act_id: str, title: str, org: str, today: str, settings: Settings) -> dict:
    url = f"https://linkareer.com/activity/{act_id}"
    base = {"id": act_id, "kind": kind, "title": title, "org": org, "url": url}
    try:
        res = fetch_url(url)
        top, body, meta = parse_linkareer(decode_bytes(res.content, res.content_type), url)
        r = run_check(top, body, None, extractor=Extractor(settings), settings=settings, today=today,
                      case=f"extra-{act_id}", meta=meta)
    except (FetchError, PortalError) as e:
        return base | {"error": str(e)}
    except Exception as e:  # noqa: BLE001 - 엔진 오류는 고치지 않고 실패로 적는다
        return base | {"error": f"{type(e).__name__}: {e}"}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{act_id}.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    c = compact(r)
    return base | {"fetched_at": res.fetched_at, "top_fields": meta["fields"], "body_chars": body.char_count(),
                   "items": c["items"], "elapsed_s": r["elapsed_s"], "usage": r.get("usage")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lists", required=True)
    ap.add_argument("--today", default=time.strftime("%Y-%m-%d"))
    ap.add_argument("--only", choices=["대외활동", "인턴"], help="이 종류만 다시 돌리고 나머지는 저장된 결과를 둔다")
    args = ap.parse_args()
    settings = Settings()
    settings.ledger_path = LEDGER
    settings.call_budget = 30
    jobs = []
    for kind, fname in (("대외활동", "list_activity.html"), ("인턴", "list_intern.html")):
        html = (Path(args.lists) / fname).read_text(encoding="utf-8", errors="ignore")
        for act_id, title, org in list_ids(html):
            jobs.append((kind, act_id, title, org))
    kept = []
    if args.only:
        kept = [c for c in json.loads(RESULTS.read_text(encoding="utf-8"))["cases"] if c["kind"] != args.only]
        jobs = [j for j in jobs if j[0] == args.only]
    with ThreadPoolExecutor(max_workers=2) as ex:
        results = list(ex.map(lambda j: run_one(*j, args.today, settings), jobs))
    results = sorted(kept + results, key=lambda c: (c["kind"] != "대외활동", -int(c["id"])))
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps({"today": args.today, "rule": __doc__.split("\n")[2].strip(), "cases": results},
                                  ensure_ascii=False, indent=1), encoding="utf-8")
    for r in results:
        if "error" in r:
            print(r["kind"], r["id"], "실패:", r["error"][:80])
            continue
        it = r["items"]
        v = lambda k: it[k]["verdict"] if isinstance(it.get(k), dict) else it.get(k)  # noqa: E731
        print(r["kind"], r["id"], "| 마감", v("deadline"), "| 자격", v("eligibility"), "|", r["title"][:30])


if __name__ == "__main__":
    main()
