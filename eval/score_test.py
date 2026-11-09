"""시험용 표본(11/9) 채점. AI 호출 없음. 결과: eval/results_test/metrics_test.md(자동 생성), scores_test.json.

채점 규칙(과제 지시 그대로)
- 마감 '날짜 다름' → 도구 마감 판정 '불일치'면 찾음.
- 마감 '시각 빠짐' → '시각 누락' 또는 '칸엔 없음·본문엔 있음'이면 찾음.
- 자격 '다름' → 빨강(불일치, 시각 누락, 요약에 없음, 칸엔 없음·본문엔 있음)이면 찾음.
- 정답 '같음'·'원문에 마감 없음'·'원문에 자격 없음'인데 빨강이면 잘못 경고.
- '확인 필요'는 찾음도 잘못 경고도 아님(따로 셈). 원문 없이 돌린 공고의 '원문 미입력'도 따로 셈.
- 확신도 '낮음'(T11 자격, T14 마감)을 뺀 숫자도 함께 낸다.
- 비교군 ①은 baseline_chat_reading.json(에이전트가 답을 읽고 적은 주장)을 같은 규칙으로 센다.

실행: .venv/bin/python -m eval.score_test --main t1 --repeat t1 t2 t3
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter

from eval.cases_test import (DL_DATE, DL_NONE, DL_SAME, DL_TIME, EL_DIFF, EL_NONE, EL_SAME, LOW_CONF,
                             NO_ORIGINAL, REPEAT_IDS, ROOT, TEST_IDS, load_truth)
from wonmun import ITEM_KEYS, ITEM_NAMES
from wonmun.judge import (DIFF, NEEDS_CHECK, NO_ORIGINAL as V_NO_ORIGINAL, NOT_IN_SUMMARY, RED, TIME_MISSING,
                          TOP_ONLY_MISSING)
from wonmun.llm import PRICE_PER_MTOK

RESULTS = ROOT / "eval/results_test"
KEY2 = ("deadline", "eligibility")
NAME2 = {"deadline": "마감", "eligibility": "자격"}

FOUND, MISSED, RED_OTHER, FALSE_ALARM, OK, CHECK, NO_ORIG, FAIL = (
    "찾음", "놓침", "빨강(이유 다름)", "잘못 경고", "경고 없음(맞음)", "확인 필요", "원문 미입력", "실행 실패")


def outcome(item: str, label: str, verdict: str | None) -> str:
    if verdict is None:
        return FAIL
    red = verdict in RED
    if item == "deadline" and label == DL_DATE:
        if verdict == DIFF:
            return FOUND
    elif item == "deadline" and label == DL_TIME:
        if verdict in (TIME_MISSING, TOP_ONLY_MISSING):
            return FOUND
    elif item == "eligibility" and label == EL_DIFF:
        if red:
            return FOUND
    elif label in (DL_SAME, DL_NONE, EL_SAME, EL_NONE):
        if red:
            return FALSE_ALARM
        if verdict == NEEDS_CHECK:
            return CHECK
        if verdict == V_NO_ORIGINAL:
            return NO_ORIG
        return OK
    else:
        raise ValueError(f"모르는 정답 이름: {item} {label}")
    # 차이가 있는 칸인데 찾지 못함
    if red:
        return RED_OTHER
    if verdict == NEEDS_CHECK:
        return CHECK
    if verdict == V_NO_ORIGINAL:
        return NO_ORIG
    return MISSED


# 비교군 ① 읽기 기록의 주장 → 도구 판정 이름으로 옮겨 같은 규칙에 넣는다.
CLAIM_TO_VERDICT = {
    "날짜 다름 지적": DIFF,
    "시각 빠짐 지적": TIME_MISSING,
    "마감 기타 차이 지적": NOT_IN_SUMMARY,  # 빨강이지만 날짜·시각 차이는 아님('도착분' 누락 등)
    "자격 차이 지적": DIFF,
    "차이 없음·언급 없음": "다른 점을 찾지 못함",
    "원문에 마감 없다고 함": NEEDS_CHECK,  # 도구가 같은 상황에서 내는 판정과 같게
    "확인 불가라고 함": NEEDS_CHECK,
    "원문 없어 비교 못 함": V_NO_ORIGINAL,
}


def load(run: str) -> dict:
    return json.loads((RESULTS / f"{run}.json").read_text(encoding="utf-8"))


def tool_table(run: str, truth: dict) -> dict:
    R = load(run)
    rows = {}
    for cid in TEST_IDS:
        r = R.get(cid)
        row = {}
        for k in KEY2:
            v = None if (not r or "error" in r) else r["items"][k]["verdict"]
            row[k] = {"label": truth[cid][k]["label"], "verdict": v, "outcome": outcome(k, truth[cid][k]["label"], v)}
        rows[cid] = row
    return rows


def chat_table(truth: dict) -> dict:
    p = RESULTS / "baseline_chat_reading.json"
    if not p.exists():
        return {}
    reading = json.loads(p.read_text(encoding="utf-8"))["cases"]
    rows = {}
    for cid in TEST_IDS:
        c = reading.get(cid)
        row = {}
        for k in KEY2:
            if not c:
                row[k] = {"label": truth[cid][k]["label"], "verdict": None, "outcome": FAIL}
                continue
            claim = c[k]["claim"]
            v = CLAIM_TO_VERDICT[claim]
            row[k] = {"label": truth[cid][k]["label"], "verdict": claim, "outcome": outcome(k, truth[cid][k]["label"], v)}
        rows[cid] = row
    return rows


def regex_table(truth: dict) -> dict:
    R = json.loads((RESULTS / "baseline_regex.json").read_text(encoding="utf-8"))["cases"]
    rows = {}
    for cid in TEST_IDS:
        v = R[cid]["verdict"]
        rows[cid] = {"deadline": {"label": truth[cid]["deadline"]["label"], "verdict": v,
                                  "outcome": outcome("deadline", truth[cid]["deadline"]["label"], v)}}
    return rows


def summarize(rows: dict, exclude_low: bool = False, ids: list[str] | None = None) -> dict:
    ids = ids or TEST_IDS
    s = {"dl_date": [0, 0], "dl_time": [0, 0], "el_diff": [0, 0],
         "fa_dl": [0, 0], "fa_el": [0, 0], "check": 0, "no_orig": 0, "red_other": 0, "fail": 0, "cells": 0,
         "fa_list": [], "missed_list": [], "check_list": []}
    for cid in ids:
        for k, cell in rows[cid].items():
            if exclude_low and (cid, k) in LOW_CONF:
                continue
            s["cells"] += 1
            lab, out = cell["label"], cell["outcome"]
            key = None
            if k == "deadline" and lab == DL_DATE:
                key = "dl_date"
            elif k == "deadline" and lab == DL_TIME:
                key = "dl_time"
            elif k == "eligibility" and lab == EL_DIFF:
                key = "el_diff"
            if key:
                s[key][1] += 1
                if out == FOUND:
                    s[key][0] += 1
                else:
                    s["missed_list"].append(f"{cid} {NAME2[k]}({lab} → {cell['verdict']})")
            else:
                fk = "fa_dl" if k == "deadline" else "fa_el"
                s[fk][1] += 1
                if out == FALSE_ALARM:
                    s[fk][0] += 1
                    s["fa_list"].append(f"{cid} {NAME2[k]}({lab} → {cell['verdict']})")
            if out == CHECK:
                s["check"] += 1
                s["check_list"].append(f"{cid} {NAME2[k]}")
            elif out == NO_ORIG:
                s["no_orig"] += 1
            elif out == RED_OTHER:
                s["red_other"] += 1
            elif out == FAIL:
                s["fail"] += 1
    return s


def repeat_metrics(runs: list[str]) -> dict:
    Rs = [load(r) for r in runs]
    out = {"all7": [0, 0], "key2": [0, 0], "value7": [0, 0], "diffs": [], "dl_norm_same": [0, 0], "dl_diffs": []}
    for cid in REPEAT_IDS:
        if any(cid not in R or "error" in R[cid] for R in Rs):
            out["diffs"].append((cid, "실행 실패 포함", []))
            continue
        for k in ITEM_KEYS:
            vs = [R[cid]["items"][k]["verdict"] for R in Rs]
            same = len(set(vs)) == 1
            out["all7"][1] += 1
            out["all7"][0] += same
            if k in KEY2:
                out["key2"][1] += 1
                out["key2"][0] += same
            if not same:
                out["diffs"].append((cid, ITEM_NAMES[k], vs))
            vals = [tuple((role, v["value"]) for role, v in sorted(R[cid]["items"][k]["values"].items())) for R in Rs]
            out["value7"][1] += 1
            out["value7"][0] += len(set(vals)) == 1
        norms = [tuple((role, v["norm"].get("date"), v["norm"].get("time"))
                       for role, v in sorted(R[cid]["items"]["deadline"]["values"].items())) for R in Rs]
        out["dl_norm_same"][1] += 1
        if len(set(norms)) == 1:
            out["dl_norm_same"][0] += 1
        else:
            out["dl_diffs"].append((cid, norms))
    return out


def ledger() -> dict:
    p = ROOT / "eval/api_calls_test.jsonl"
    rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    by = Counter(r["purpose"] for r in rows)
    tin = sum(r["input_tokens"] for r in rows)
    tout = sum(r["output_tokens"] for r in rows)

    def cost(rs):
        return sum((r["input_tokens"] * PRICE_PER_MTOK[r["model"]][0] + r["output_tokens"] * PRICE_PER_MTOK[r["model"]][1]) / 1e6
                   for r in rs)
    per = {}
    for purpose in by:
        rs = [r for r in rows if r["purpose"] == purpose]
        per[purpose] = {"calls": len(rs), "tok_in": sum(r["input_tokens"] for r in rs),
                        "tok_out": sum(r["output_tokens"] for r in rs), "cost": cost(rs),
                        "latency_mean": statistics.mean(r["latency_s"] for r in rs)}
    return {"calls": len(rows), "by_purpose": per, "tok_in": tin, "tok_out": tout, "cost": cost(rows),
            "failed": [r for r in rows if not r["ok"]]}


def pct(a, b):
    return f"{a}/{b}" + (f" ({a / b:.0%})" if b else "")


def fmt_summary(name: str, s: dict, regex: bool = False) -> list[str]:
    L = [f"- {name}"]
    L.append(f"  - 마감 날짜 다름 찾음 {pct(*s['dl_date'])}, 마감 시각(칸) 찾음 {pct(*s['dl_time'])}"
             + ("" if regex else f", 자격 다름 찾음 {pct(*s['el_diff'])}"))
    L.append(f"  - 잘못 경고: 마감 {pct(*s['fa_dl'])}" + ("" if regex else f", 자격 {pct(*s['fa_el'])}"))
    L.append(f"  - 확인 필요 {s['check']}칸, 원문 미입력 {s['no_orig']}칸, 빨강이지만 이유 다름 {s['red_other']}칸, 실행 실패 {s['fail']}칸 (전체 {s['cells']}칸)")
    if s["missed_list"]:
        L.append("  - 못 찾은 칸: " + "; ".join(s["missed_list"]))
    if s["fa_list"]:
        L.append("  - 잘못 경고 칸: " + "; ".join(s["fa_list"]))
    return L


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--main", default="t1")
    ap.add_argument("--repeat", nargs="*", default=[])
    args = ap.parse_args()
    truth = load_truth()
    tool = tool_table(args.main, truth)
    chat = chat_table(truth)
    rx = regex_table(truth)
    with_orig = [c for c in TEST_IDS if c not in NO_ORIGINAL]
    without = [c for c in TEST_IDS if c in NO_ORIGINAL]

    out = ["# 시험용 표본 자동 채점 (eval/score_test.py 생성, 손대지 말 것)", "",
           f"표본 15건: {', '.join(TEST_IDS)}. 원문 없이 돌린 공고 {len(without)}건: {', '.join(without)}.", ""]
    out.append("## 항목별 (전부)")
    out += fmt_summary(f"도구 `{args.main}`", summarize(tool))
    if chat:
        out += fmt_summary("비교군 ① 같은 모델 1회 질문(에이전트가 답을 읽고 셈)", summarize(chat))
    out += fmt_summary("비교군 ② 규칙만(마감만)", summarize(rx), regex=True)
    out += ["", "## 확신도 '낮음' 2칸(T11 자격, T14 마감) 뺀 숫자"]
    out += fmt_summary(f"도구 `{args.main}`", summarize(tool, exclude_low=True))
    if chat:
        out += fmt_summary("비교군 ①", summarize(chat, exclude_low=True))
    out += fmt_summary("비교군 ②", summarize(rx, exclude_low=True), regex=True)
    out += ["", "## 원문 유무로 나눔 (도구)"]
    out += fmt_summary(f"원문 있음 {len(with_orig)}건", summarize(tool, ids=with_orig))
    out += fmt_summary(f"원문 없이 {len(without)}건", summarize(tool, ids=without))
    if chat:
        out += ["", "## 원문 유무로 나눔 (비교군 ①)"]
        out += fmt_summary(f"원문 있음 {len(with_orig)}건", summarize(chat, ids=with_orig))
        out += fmt_summary(f"원문 없이 {len(without)}건", summarize(chat, ids=without))

    out += ["", "## 공고별 (정답 / 도구 / 비교군 ① / 비교군 ②)", "",
            "| 공고 | 원문 | 마감 정답 | 도구 마감 | ① 마감 | ② 마감 | 자격 정답 | 도구 자격 | ① 자격 |",
            "|---|---|---|---|---|---|---|---|---|"]
    for cid in TEST_IDS:
        t, r = tool[cid], rx[cid]
        c = chat.get(cid) or {k: {"verdict": "-", "outcome": "-"} for k in KEY2}
        out.append(
            f"| {cid} | {'없음' if cid in NO_ORIGINAL else '있음'} | {t['deadline']['label']} | "
            f"{t['deadline']['verdict']} → {t['deadline']['outcome']} | {c['deadline']['verdict']} → {c['deadline']['outcome']} | "
            f"{r['deadline']['verdict']} → {r['deadline']['outcome']} | {t['eligibility']['label']} | "
            f"{t['eligibility']['verdict']} → {t['eligibility']['outcome']} | {c['eligibility']['verdict']} → {c['eligibility']['outcome']} |")

    # 인용·시간·비용
    R = load(args.main)
    ok_cases = [R[c] for c in TEST_IDS if c in R and "error" not in R[c]]
    q_ok = sum(r["summary"]["quotes_verified"] for r in ok_cases)
    q_tot = sum(r["summary"]["quotes_total"] for r in ok_cases)
    runs_all = [args.main] + [x for x in args.repeat if x != args.main]
    qa_ok = qa_tot = 0
    for run in runs_all:
        for r in load(run).values():
            if "summary" in r:
                qa_ok += r["summary"]["quotes_verified"]
                qa_tot += r["summary"]["quotes_total"]
    el = [r["elapsed_s"] for r in ok_cases]
    pl = [r["pipeline_s"] for r in ok_cases]
    fetch = json.loads((RESULTS / "fetch_log.json").read_text(encoding="utf-8"))
    fs = [(fetch[c]["summary"].get("fetch_s") or 0) + (fetch[c]["original"].get("fetch_s") or 0) for c in TEST_IDS]
    out += ["", "## 인용·시간 (도구)",
            f"- AI 인용 중 출처에 글자 그대로 있던 것: `{args.main}` {pct(q_ok, q_tot)}; {', '.join(runs_all)} 합계 {pct(qa_ok, qa_tot)}",
            f"- AI 호출 시간(1건): 평균 {statistics.mean(el):.1f}초, 중앙값 {statistics.median(el):.1f}초, 최대 {max(el):.1f}초",
            f"- 판정까지(저장 원본 사용): 평균 {statistics.mean(pl):.1f}초",
            f"- 받기(요약 페이지+원문, 11/9 1회째 기록): 평균 {statistics.mean(fs):.1f}초, 최대 {max(fs):.1f}초",
            f"- 실행 실패: {[c for c in TEST_IDS if c not in R or 'error' in R[c]]}"]
    ca = RESULTS / "baseline_chat_auto.json"
    if ca.exists():
        A = json.loads(ca.read_text(encoding="utf-8"))
        lat = [c["latency_s"] for c in A["cases"].values()]
        out += [f"- 비교군 ① 답 속 따옴표 문장이 출처에 글자 그대로 있던 것: {pct(A['quotes_ok'], A['quotes_total'])}",
                f"- 비교군 ① 호출 시간: 평균 {statistics.mean(lat):.1f}초"]

    rep = None
    if args.repeat:
        rep = repeat_metrics(args.repeat)
        out += ["", f"## 3회 반복 ({', '.join(args.repeat)}) {', '.join(REPEAT_IDS)}",
                f"- 마감·자격 판정이 3번 모두 같은 칸: {pct(*rep['key2'])}",
                f"- 7항목 판정이 3번 모두 같은 칸: {pct(*rep['all7'])}",
                f"- 화면 값 글자까지 3번 모두 같은 칸(7항목): {pct(*rep['value7'])}",
                f"- 마감 값(출처별 코드가 읽은 날짜·시각) 3번 모두 같은 공고: {pct(*rep['dl_norm_same'])}"]
        for cid, name, vs in rep["diffs"]:
            out.append(f"  - {cid} {name}: {' / '.join(map(str, vs))}")
        for cid, norms in rep["dl_diffs"]:
            out.append(f"  - {cid} 마감 값: " + " / ".join(str(n) for n in norms))

    lg = ledger()
    out += ["", "## AI 호출 (eval/api_calls_test.jsonl 전체)",
            f"- 호출 {lg['calls']}회 (상한 60), 실패 {len(lg['failed'])}회",
            f"- 토큰 합계: 입력 {lg['tok_in']:,}, 출력 {lg['tok_out']:,}, 비용 추정 ${lg['cost']:.4f} (Claude Haiku 5.5, 입력 $0.10·출력 $0.50 / 100만 토큰)"]
    for p, d in lg["by_purpose"].items():
        out.append(f"  - {p}: {d['calls']}회, 입력 {d['tok_in']:,}, 출력 {d['tok_out']:,}, ${d['cost']:.4f}, "
                   f"1회 평균 ${d['cost'] / d['calls']:.4f}, 평균 {d['latency_mean']:.1f}초")
    (RESULTS / "metrics_test.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    (RESULTS / "scores_test.json").write_text(json.dumps(
        {"tool": tool, "chat": chat, "regex": rx,
         "summary": {"tool": summarize(tool), "tool_excl_low": summarize(tool, exclude_low=True),
                     "chat": summarize(chat) if chat else None,
                     "chat_excl_low": summarize(chat, exclude_low=True) if chat else None,
                     "regex": summarize(rx), "regex_excl_low": summarize(rx, exclude_low=True)},
         "repeat": rep, "ledger": {k: v for k, v in lg.items() if k != "failed"}},
        ensure_ascii=False, indent=1, default=list), encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
