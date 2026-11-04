"""채점. API 호출 없음. 결과를 eval/metrics_dev.md(자동 생성)로 쓴다.

실행: .venv/bin/python -m eval.score --main r1 [--alt r1b] [--repeat r1 r2 r3]
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict

from eval.cases import (EXCLUDED_AFTER_FETCH, EXCLUDED_BY_RULE, MAIN_IDS, REPEAT_IDS, ROOT, STAGE1_IDS,
                        load_truth)
from wonmun import ITEM_KEYS, ITEM_NAMES
from wonmun.judge import RED
from wonmun.llm import PRICE_PER_MTOK

TARGET_LABELS = {"불일치", "시각 누락"}
OK_LABELS = {"일치", "원문에도 없음"}
KEY2 = ("deadline", "eligibility")


def load(run: str) -> dict:
    return json.loads((ROOT / "eval/results" / f"{run}.json").read_text(encoding="utf-8"))


def core_metrics(run: str, ids: list[str], truth: dict) -> dict:
    R = load(run)
    targets, found_any, found_exact, missed = [], [], [], []
    fa2, fa7, cm = [], [], defaultdict(Counter)
    q_total = q_ok = 0
    needs = 0
    n_items = 0
    times, ptimes, tin, tout, cost = [], [], [], [], []
    for cid in ids:
        r = R.get(cid)
        if not r or "error" in r:
            continue
        q_total += r["summary"]["quotes_total"]
        q_ok += r["summary"]["quotes_verified"]
        u = r.get("usage") or {}
        if u:
            tin.append(u["input_tokens"])
            tout.append(u["output_tokens"])
            cost.append(u.get("cost_usd", 0))
        if r.get("elapsed_s") is not None:
            times.append(r["elapsed_s"])
        if r.get("pipeline_s") is not None:
            ptimes.append(r["pipeline_s"])
        for k in ITEM_KEYS:
            label = truth[cid]["items"].get(k, {}).get("label", "CSV 없음")
            v = r["items"][k]["verdict"]
            n_items += 1
            cm[label][v] += 1
            if v == "확인 필요":
                needs += 1
            if k in KEY2 and label in TARGET_LABELS:
                targets.append((cid, k, label, v))
                if v in RED:
                    found_any.append((cid, k))
                    if v == label:
                        found_exact.append((cid, k))
                else:
                    missed.append((cid, k, label, v))
            if label in OK_LABELS and v in RED:
                fa7.append((cid, k, label, v))
                if k in KEY2:
                    fa2.append((cid, k, label, v))
    return {
        "run": run, "n_cases": len(ids), "n_items": n_items,
        "targets": targets, "found_any": found_any, "found_exact": found_exact, "missed": missed,
        "false_alarm_key2": fa2, "false_alarm_all": fa7, "confusion": cm,
        "quotes_total": q_total, "quotes_ok": q_ok, "needs_check": needs,
        "times": times, "pipeline_times": ptimes, "tok_in": tin, "tok_out": tout, "cost": cost,
    }


def repeat_metrics(runs: list[str], ids: list[str]) -> dict:
    Rs = [load(r) for r in runs]
    same_v = same_val = total = 0
    diffs = []
    for cid in ids:
        if any(cid not in R or "error" in R[cid] for R in Rs):
            continue
        for k in ITEM_KEYS:
            total += 1
            vs = [R[cid]["items"][k]["verdict"] for R in Rs]
            if len(set(vs)) == 1:
                same_v += 1
            else:
                diffs.append((cid, k, vs))
            # 화면에 보이는 값(요약 칸·원문)까지 같은지
            vals = [tuple((role, v["value"]) for role, v in sorted(R[cid]["items"][k]["values"].items()))
                    for R in Rs]
            if len(set(vals)) == 1:
                same_val += 1
    # 마감: 출처별로 코드가 다시 읽은 날짜·시각이 3번 모두 같은 공고
    dl_same = 0
    dl_diff = []
    for cid in ids:
        if any(cid not in R or "error" in R[cid] for R in Rs):
            continue
        norms = [tuple((role, v["norm"].get("date"), v["norm"].get("time"))
                       for role, v in sorted(R[cid]["items"]["deadline"]["values"].items())) for R in Rs]
        if len(set(norms)) == 1:
            dl_same += 1
        else:
            dl_diff.append((cid, norms))
    return {"runs": runs, "ids": ids, "total": total, "same_verdict": same_v, "same_value": same_val,
            "diffs": diffs, "dl_same": dl_same, "dl_diff": dl_diff}


def quote_stats(runs: list[str]) -> tuple[int, int]:
    tot = ok = 0
    for run in runs:
        for r in load(run).values():
            if "summary" in r:
                tot += r["summary"]["quotes_total"]
                ok += r["summary"]["quotes_verified"]
    return ok, tot


def ledger() -> dict:
    rows = [json.loads(line) for line in (ROOT / "eval/api_calls.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()]
    by = Counter(r["purpose"] for r in rows)
    tin = sum(r["input_tokens"] for r in rows)
    tout = sum(r["output_tokens"] for r in rows)
    cost = sum((r["input_tokens"] * PRICE_PER_MTOK.get(r["model"], (0, 0))[0]
                + r["output_tokens"] * PRICE_PER_MTOK.get(r["model"], (0, 0))[1]) / 1e6 for r in rows)
    fails = [r for r in rows if not r["ok"]]
    return {"calls": len(rows), "by_purpose": dict(by), "tok_in": tin, "tok_out": tout, "cost": cost,
            "failed": len(fails), "fail_reasons": Counter(r["stop_reason"] for r in fails)}


def fmt_core(m: dict) -> str:
    L = []
    t = len(m["targets"])
    L.append(f"- 공고 {m['n_cases']}건, 항목 {m['n_items']}칸")
    L.append(f"- 마감·자격 차이(CSV 불일치/시각 누락) 찾은 수: **{len(m['found_any'])}/{t}** "
             f"(판정 이름까지 CSV와 같은 것 {len(m['found_exact'])}/{t})")
    if m["missed"]:
        L.append("  - 놓친 것: " + ", ".join(f"{c} {ITEM_NAMES[k]}(CSV {lab} → 도구 {v})" for c, k, lab, v in m["missed"]))
    L.append(f"- 잘못 경고(CSV 일치·원문에도 없음인데 빨강): 마감·자격 {len(m['false_alarm_key2'])}칸, "
             f"7항목 전체 {len(m['false_alarm_all'])}칸")
    for c, k, lab, v in m["false_alarm_all"]:
        L.append(f"  - {c} {ITEM_NAMES[k]}: CSV {lab} → 도구 {v}")
    qr = m["quotes_ok"] / m["quotes_total"] if m["quotes_total"] else 0
    L.append(f"- AI 인용 원문 일치율(코드 검사 통과): {m['quotes_ok']}/{m['quotes_total']} = {qr:.1%} "
             "(통과 못한 인용은 화면에 내보내지 않음 → 화면 근거의 일치율은 100%)")
    L.append(f"- '확인 필요' 비율: {m['needs_check']}/{m['n_items']} = {m['needs_check'] / m['n_items']:.1%}")
    if m["times"]:
        L.append(f"- AI 호출 시간(1건): 평균 {statistics.mean(m['times']):.1f}초, 중앙값 {statistics.median(m['times']):.1f}초, "
                 f"최대 {max(m['times']):.1f}초")
    if m["pipeline_times"]:
        L.append(f"- 판정까지 전체(저장 원본 사용, 받기 시간 제외): 평균 {statistics.mean(m['pipeline_times']):.1f}초")
    if m["tok_in"]:
        L.append(f"- 토큰(1건 평균): 입력 {statistics.mean(m['tok_in']):,.0f}, 출력 {statistics.mean(m['tok_out']):,.0f} "
                 f"→ 1건 약 ${statistics.mean(m['cost']):.4f}")
    return "\n".join(L)


def fmt_confusion(m: dict) -> str:
    verdicts = ["불일치", "시각 누락", "칸엔 없음·본문엔 있음", "요약에 없음", "다른 점을 찾지 못함",
                "원문에도 없음", "확인 필요", "원문 미입력"]
    labels = ["일치", "불일치", "시각 누락", "칸엔 없음·본문엔 있음", "요약에 없음", "원문에도 없음", "모호", "확인 불가", "CSV 없음"]
    head = "| CSV 판정 \\ 도구 판정 | " + " | ".join(verdicts) + " | 합 |"
    sep = "|" + "---|" * (len(verdicts) + 2)
    rows = [head, sep]
    for lab in labels:
        c = m["confusion"].get(lab, Counter())
        if not sum(c.values()):
            continue
        rows.append(f"| {lab} | " + " | ".join(str(c.get(v, 0) or "") for v in verdicts) + f" | {sum(c.values())} |")
    return "\n".join(rows)


def fmt_cases(run: str, ids: list[str], truth: dict) -> str:
    R = load(run)
    head = "| 공고 | " + " | ".join(ITEM_NAMES[k] for k in ITEM_KEYS) + " |"
    rows = [head, "|" + "---|" * (len(ITEM_KEYS) + 1)]
    for cid in ids:
        r = R.get(cid)
        if not r or "error" in r:
            rows.append(f"| {cid} | 실패 |")
            continue
        cells = []
        for k in ITEM_KEYS:
            lab = truth[cid]["items"].get(k, {}).get("label", "CSV 없음")
            v = r["items"][k]["verdict"]
            mark = "★" if (k in KEY2 and lab in TARGET_LABELS and v in RED) else ("✗" if lab in OK_LABELS and v in RED else "")
            cells.append(f"{v} / CSV {lab}{mark}")
        rows.append(f"| {cid} | " + " | ".join(cells) + " |")
    return "\n".join(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--main", default="r1")
    ap.add_argument("--alt", nargs="*", default=[])
    ap.add_argument("--repeat", nargs="*", default=[])
    ap.add_argument("--stage1", default="")
    args = ap.parse_args()
    truth = load_truth()
    out = ["# 개발용 표본 자동 채점 (eval/score.py 생성, 손대지 말 것)", ""]
    out.append("표본: " + ", ".join(MAIN_IDS))
    out.append("규칙상 제외: " + "; ".join(f"{k} {v}" for k, v in EXCLUDED_BY_RULE.items()))
    out.append("받아 본 뒤 제외: " + "; ".join(f"{k} {v}" for k, v in EXCLUDED_AFTER_FETCH.items()))
    out.append("")
    for run in [args.main] + args.alt:
        m = core_metrics(run, MAIN_IDS, truth)
        out += [f"## 도구 run `{run}`", "", fmt_core(m), "", "### 7항목 혼동표(칸 수)", "", fmt_confusion(m), "",
                "### 공고별 (★ = 마감·자격 차이를 찾음, ✗ = 잘못 경고)", "", fmt_cases(run, MAIN_IDS, truth), ""]
    if args.repeat:
        rm = repeat_metrics(args.repeat, REPEAT_IDS)
        out += [f"## 3회 반복 ({', '.join(args.repeat)}) 공고 {len(REPEAT_IDS)}건", "",
                f"- 판정이 3번 모두 같은 칸: {rm['same_verdict']}/{rm['total']} = {rm['same_verdict'] / rm['total']:.1%}",
                f"- 화면 값(출처별 값 글자)까지 3번 모두 같은 칸: {rm['same_value']}/{rm['total']} = {rm['same_value'] / rm['total']:.1%}"]
        for cid, k, vs in rm["diffs"]:
            out.append(f"  - {cid} {ITEM_NAMES[k]}: {' / '.join(vs)}")
        out.append(f"- 마감 값(출처별로 코드가 읽은 날짜·시각)이 3번 모두 같은 공고: {rm['dl_same']}/{len(REPEAT_IDS)}")
        for cid, norms in rm["dl_diff"]:
            out.append(f"  - {cid}: " + " / ".join(str([x for x in n if x[0] == 'original']) for n in norms))
        out.append("")
    all_runs = [args.main] + [r for r in args.repeat if r != args.main] + ([args.stage1] if args.stage1 else [])
    ok, tot = quote_stats([r for r in all_runs if r])
    out += [f"## AI 인용 검사 합계 (도구 실행 {', '.join(all_runs)})", "",
            f"- AI가 낸 인용 {tot}개 중 출처에 글자 그대로 있던 것 {ok}개 = {ok / tot:.1%}. 나머지는 화면에 내보내지 않음.", ""]
    if args.stage1:
        R = load(args.stage1)
        out += [f"## 보조: 원문 없이 칸↔본문만 (`{args.stage1}`)", "",
                "| 공고 | 마감 | 자격 | 시상 | CSV 마감 | CSV 자격 | CSV 메모 |", "|---|---|---|---|---|---|---|"]
        for cid in STAGE1_IDS:
            r = R.get(cid)
            if not r or "error" in r:
                continue
            t = truth[cid]["items"]
            out.append(f"| {cid} | {r['items']['deadline']['verdict']} | {r['items']['eligibility']['verdict']} | "
                       f"{r['items']['prize']['verdict']} | {t['deadline']['label']} | {t['eligibility']['label']} | "
                       f"{(t['eligibility']['memo'] or t['deadline']['memo'])[:60]} |")
        out.append("")
    lg = ledger()
    out += ["## API 호출 기록(eval/api_calls.jsonl 전체)", "",
            f"- 호출 {lg['calls']}회 (용도별 {lg['by_purpose']}), 실패 {lg['failed']}회 {dict(lg['fail_reasons'])}",
            f"- 토큰 합계: 입력 {lg['tok_in']:,}, 출력 {lg['tok_out']:,}",
            f"- 비용 추정: ${lg['cost']:.4f} (Claude Haiku 5.5, 입력 $0.10·출력 $0.50 / 100만 토큰, 프롬프트 10만 토큰 이하 요율)"]
    (ROOT / "eval/metrics_dev.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
