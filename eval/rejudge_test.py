"""시험용 15건을 저장된 AI 출력(data/runs/test/t1)으로 다시 판정한다. AI 호출 없음.

엔진 결함을 고친 뒤 다른 칸이 나빠지지 않았는지 보는 참고용이다. 결함을 이 표본에서 찾았으므로
여기서 나온 숫자는 시험 점수로 쓰지 않는다(시험 점수는 고치기 전 t1 그대로).

실행: .venv/bin/python -m eval.rejudge_test
결과: eval/results_test/t1_rejudged.json, 화면에 칸별 변화와 요약
"""

from __future__ import annotations

import json
import warnings

from eval.cases_test import ROOT, TEST_IDS, TODAY, load_truth
from eval.run_test import RESULTS, load_sources, make_settings
from eval.run_tool import compact
from eval.score_test import summarize, tool_table
from wonmun.pipeline import run_check

warnings.filterwarnings("ignore", category=FutureWarning)


def main() -> None:
    settings = make_settings()
    out = {}
    for cid in TEST_IDS:
        saved = json.loads((ROOT / "data/runs/test/t1" / f"{cid}.json").read_text(encoding="utf-8"))
        top, body, orig, meta = load_sources(cid)
        r = run_check(top, body, orig, settings=settings, today=TODAY, case=cid, meta=meta,
                      ai_output=saved["ai_output"])
        c = compact(r)
        c["has_original"] = orig is not None
        c["has_body"] = body is not None
        out[cid] = c
    (RESULTS / "t1_rejudged.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    truth = load_truth()
    before, after = tool_table("t1", truth), tool_table("t1_rejudged", truth)
    for cid in TEST_IDS:
        for item in ("deadline", "eligibility"):
            b, a = before[cid][item], after[cid][item]
            if (b["verdict"], b["outcome"]) != (a["verdict"], a["outcome"]):
                print(f"{cid} {item}: {b['verdict']}({b['outcome']}) -> {a['verdict']}({a['outcome']})")
    print("before", summarize(before))
    print("after ", summarize(after))


if __name__ == "__main__":
    main()
