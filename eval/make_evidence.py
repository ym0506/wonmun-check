"""'근거 자료' 페이지(web/static/evidence.html)를 기록 파일에서 만든다. AI 호출 없음.

- 11/4 표본 23건: eval/fixtures/공고대조_기록_2026-11-04.csv
- 11/9 시험용 15건: eval/fixtures/test_2026-11-09/정답표.csv + eval/results_test/scores_test.json
- 화면 캡처: web/static/evidence/*.jpg (연락처·다른 사용자 프로필·채팅 미리보기는 가림)

실행: .venv/bin/python -m eval.make_evidence
"""

from __future__ import annotations

import csv
import json
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REC = ROOT / "eval/fixtures/공고대조_기록_2026-11-04.csv"
TRUTH = ROOT / "eval/fixtures/test_2026-11-09/정답표.csv"
SCORES = ROOT / "eval/results_test/scores_test.json"
OUT = ROOT / "web/static/evidence.html"

DIFF = {"불일치", "시각 누락"}
OUTCOME_CLASS = {"찾음": "hit", "놓침": "miss", "잘못 경고": "fa", "경고 없음(맞음)": "ok", "확인 필요": "chk"}


def link(url: str, text: str) -> str:
    url = url.strip()
    if url.startswith("http"):
        first = url.split()[0]
        return f'<a href="{escape(first)}" target="_blank" rel="noopener noreferrer">{escape(text)}</a>'
    return escape(text)


def orig_cell(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return '<span class="muted">없음</span>'
    for tok in raw.replace(",", " ").split():
        if tok.startswith("http"):
            note = raw.replace(tok, "").strip(" ,()")
            return link(tok, "원문") + (f' <span class="muted">{escape(note[:40])}</span>' if note else "")
    return f'<span class="muted">{escape(raw[:60])}</span>'


def sample_1104() -> tuple[str, str]:
    rows = [r for r in csv.DictReader(REC.open(encoding="utf-8")) if r["공고ID"] != "예시"]
    order, by_id = [], {}
    for r in rows:
        if r["공고ID"] not in by_id:
            order.append(r["공고ID"])
            by_id[r["공고ID"]] = {"head": r, "cells": {}}
        by_id[r["공고ID"]]["cells"][r["칸"]] = r
    trs = []
    for cid in order:
        h, cells = by_id[cid]["head"], by_id[cid]["cells"]
        dl = cells.get("마감 일시", {}).get("판정", "")
        el = cells.get("참가 자격", {}).get("판정", "")
        differ = dl in DIFF or el in DIFF
        trs.append(
            f'<tr class="{"diffrow" if differ else ""}"><td>{escape(cid)}</td>'
            f'<td>{link(h["요약_URL"], h["공고명"])}<div class="muted">{escape(h["요약_출처"])}</div></td>'
            f'<td>{orig_cell(h["원문_파일"])}</td>'
            f'<td class="{"red" if dl in DIFF else ""}">{escape(dl)}</td>'
            f'<td class="{"red" if el in DIFF else ""}">{escape(el)}</td></tr>')
    table = ('<table><thead><tr><th>번호</th><th>공고(요약 페이지)</th><th>원문</th><th>마감</th><th>자격</th></tr></thead>'
             f'<tbody>{"".join(trs)}</tbody></table>')
    det = []
    for cid in order:
        for item in ("마감 일시", "참가 자격"):
            r = by_id[cid]["cells"].get(item)
            if r and r["판정"] in DIFF:
                det.append(f'<tr><td>{escape(cid)}</td><td>{escape(item)}</td><td class="red">{escape(r["판정"])}</td>'
                           f'<td>{escape(r["요약에_적힌_값"])}</td><td>{escape(r["원문_값"])}</td>'
                           f'<td class="muted">{escape(r["원문_위치"])}</td></tr>')
    detail = ('<table><thead><tr><th>번호</th><th>항목</th><th>판정</th><th>요약에 적힌 값</th><th>원문 값</th>'
              f'<th>원문 위치</th></tr></thead><tbody>{"".join(det)}</tbody></table>')
    return table, detail


def cell(o: dict | None) -> str:
    if not o:
        return '<td class="muted">-</td>'
    cls = OUTCOME_CLASS.get(o["outcome"], "")
    return f'<td class="oc {cls}">{escape(o["verdict"])}<div class="tag">{escape(o["outcome"])}</div></td>'


def test_0911() -> str:
    truth = list(csv.DictReader(TRUTH.open(encoding="utf-8")))
    sc = json.loads(SCORES.read_text(encoding="utf-8"))
    trs = []
    for t in truth:
        cid = t["번호"]
        g = lambda who, item: (sc.get(who, {}).get(cid) or {}).get(item)  # noqa: E731
        trs.append(
            f'<tr><td>{escape(cid)}</td><td>{link(t["포털_URL"], t["공고명"])}<div class="muted">{escape(t["출처"])}</div></td>'
            f'<td>{orig_cell(t["원문_URL"])}</td>'
            f'<td><b>{escape(t["마감_정답"])}</b></td>{cell(g("tool", "deadline"))}{cell(g("chat", "deadline"))}{cell(g("regex", "deadline"))}'
            f'<td><b>{escape(t["자격_정답"])}</b></td>{cell(g("tool", "eligibility"))}{cell(g("chat", "eligibility"))}</tr>')
    return ('<table class="wide"><thead><tr><th rowspan="2">번호</th><th rowspan="2">공고(요약 페이지)</th><th rowspan="2">원문</th>'
            '<th colspan="4">마감</th><th colspan="3">자격</th></tr>'
            '<tr><th>정답</th><th>원문 확인</th><th>같은 AI 1회</th><th>규칙만</th><th>정답</th><th>원문 확인</th><th>같은 AI 1회</th></tr></thead>'
            f'<tbody>{"".join(trs)}</tbody></table>')


SHOTS = [
    ("1104_kisti_portal.jpg", "11/4 링커리어 KISTI 경진대회: D-21, 접수기간 칸 2026.08.11 ~ 2026.11.25"),
    ("1104_calendar_1125.jpg", "11/4 링커리어 공고 달력: 이 대회가 11월 25일 마감으로 올라 있음"),
    ("1109_kisti_portal.jpg", "11/9 22:08 같은 공고: 원문 제출 마감(11/6)이 지났는데 D-16, 스크랩 1,047명. 아래는 같은 페이지 본문의 접수기간"),
    ("1104_miryang_portal.jpg", "11/4 링커리어 밀양 쇼츠 공모전: 접수기간 칸 ~ 2026.11.15 (원문 공지는 11.7 마감)"),
    ("1104_dgist_youthcenter.jpg", "11/4 온통청년 DGIST 사업: 사업 신청기간 2026년 11월 1일 ~ 11월 30일"),
    ("1104_dgist_original.jpg", "11/4 DGIST 원문: 2027학년도 봄학기 3차 원서접수 '26.11.5 ~ 11.19"),
]

CSS = """
.ev h2 { margin: 28px 0 8px; font-size: 1.1rem; }
.ev p { line-height: 1.6; }
.ev .scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; border: 1px solid var(--line); border-radius: var(--radius); }
.ev table { border-collapse: collapse; width: 100%; font-size: .86rem; }
.ev table.wide { min-width: 980px; }
.ev th, .ev td { border-bottom: 1px solid var(--line); padding: 6px 8px; text-align: left; vertical-align: top; }
.ev th { background: #f6f6f6; font-weight: 600; white-space: nowrap; }
.ev .muted { color: var(--summary); font-size: .8rem; }
.ev .red { color: var(--red); font-weight: 600; }
.ev tr.diffrow td:first-child { box-shadow: inset 3px 0 0 var(--red); }
.ev .oc .tag { font-size: .75rem; margin-top: 2px; }
.ev .oc.hit .tag { color: #1b7a3a; } .ev .oc.ok .tag { color: #1b7a3a; }
.ev .oc.miss .tag, .ev .oc.fa .tag { color: var(--red); font-weight: 600; }
.ev .oc.chk .tag { color: var(--check); }
.ev .shots { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
.ev figure { margin: 0; border: 1px solid var(--line); border-radius: var(--radius); overflow: hidden; background: #fff; }
.ev figure img { display: block; width: 100%; height: auto; }
.ev figcaption { font-size: .82rem; padding: 6px 8px; color: var(--summary); }
.ev .nums li { margin: 2px 0; }
"""


def main() -> None:
    t1104, d1104 = sample_1104()
    shots = "".join(f'<figure><a href="/static/evidence/{f}" target="_blank"><img src="/static/evidence/{f}" alt="{escape(c)}" loading="lazy"></a>'
                    f'<figcaption>{escape(c)}</figcaption></figure>' for f, c in SHOTS)
    html = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>원문 확인 근거 자료</title>
<link rel="stylesheet" href="/static/style.css">
<style>{CSS}</style>
</head>
<body>
<header class="top"><div class="wrap"><h1>근거 자료</h1>
<p class="sub">기획안의 숫자가 어디서 나왔는지: 표본 목록, 원문 주소, 칸별 판정, 화면 캡처. <a href="/">← 원문 확인으로</a></p></div></header>
<main class="wrap ev">

<h2>0. 시연 영상 (1분 10초)</h2>
<p>저장 예시 3건을 보고, 포털 주소 하나로 직접 확인을 1번 돌린 화면이다(11월 9일 녹화). AI를 기다리는 약 20초는 영상에서 줄였다. 자막은 영상 위에 덧씌운 것이다.</p>
<video controls preload="metadata" playsinline style="width:100%;max-width:960px;border:1px solid var(--line);border-radius:var(--radius)" src="/static/demo/demo.mp4"></video>

<h2>1. 11월 4일 표본 23건 (문제 정의)</h2>
<p>링커리어 공모전 목록 1쪽을 순서대로 20건(공모가 아닌 1건 제외), 온통청년 최신순 1쪽에서 신청기간이 날짜로 적힌 정책 3건. 원문을 찾지 못하거나 열 수 없던 3건(L03, L16, Y3)을 빼고 20건을 원문과 대조했고, 2건(L06, L09)은 주최 측 공식 SNS로 원문을 대신했다. 빨간 줄이 마감이나 자격이 원문과 다른 7건이다. 항목별 1차 판정은 Claude가 했고, 원문과 다른 7건은 Claude가 원문을 다시 열어 확인했다.</p>
<div class="scroll">{t1104}</div>

<h2>2. 원문과 다른 7건의 값</h2>
<p>'요약에 적힌 값'은 포털 위쪽 칸(링커리어) 또는 정책 요약 칸(온통청년)이다.</p>
<div class="scroll">{d1104}</div>

<h2>3. 화면 캡처</h2>
<p>로그인하지 않은 상태로 찍었다. 다른 사용자의 프로필 사진과 채팅 미리보기는 회색으로 가렸다.</p>
<div class="shots">{shots}</div>

<h2>4. 11월 9일 시험용 15건 (PoC 실측)</h2>
<p>11/4 표본과 겹치지 않게 새로 뽑았다: 링커리어 공모전 목록 1쪽(추천 제외) 최신순 10건(주최 원문이 없는 1건과 공모가 아닌 경품 이벤트 1건은 넘기고 다음 2건 R1·R2로 채움), 온통청년 최신순으로 신청기간이 날짜로 적힌 정책 5건. 정답은 PoC와 분리된 작업에서 Claude가 원문만 보고 PoC를 돌리기 전에 적었다. 마감의 '시각 빠짐'은 위쪽 칸 기준이다. 엔진은 시험 동안 고치지 않았다.</p>
<ul class="nums">
<li>원문과 다른 칸 16개 중 찾은 수: 원문 확인 13, 같은 AI에 한 번 질문 11, 규칙만(마감 8칸) 0</li>
<li>같은 칸 14개 중 잘못 경고: 원문 확인 1(T13 '19~39세'를 잘못 읽음), 같은 AI 5, 규칙만(마감 7칸) 1. 애매한 5칸(T01 자격, T04 마감, T13 마감, T11 자격, T15 자격)을 반대로 보면 같은 AI는 찾음 최대 12, 잘못 경고 1까지 바뀐다.</li>
<li>근거 문장이 준 글에 글자 그대로 있는 비율: 원문 확인 300/300, 같은 AI 139/173</li>
<li>규칙만은 원문이 없는 6건에 포털 본문을 원문 대신 줘도 마감 0/8, 잘못 경고 1/7로 같았다.</li>
<li>같은 공고 5건을 세 번 돌렸을 때 7항목 판정이 같은 칸 34/35. 1건 평균 22초, 약 0.0033달러(Claude Haiku 5.5)</li>
<li>시험 뒤 고친 결함: '19~39세' 나이 범위와 원문의 '청년'을 빠진 조건으로 센 것(T13), 같은 날 '10:00~17:30'에서 시작 시각을 마감으로 읽은 것(R1). 저장된 AI 출력으로 다시 판정하면 T13 잘못 경고가 사라지고 나머지 29칸과 개발용 77칸은 그대로다. 결함을 이 표본에서 찾았으므로 위 숫자는 고치기 전 값이다.</li>
</ul>
<div class="scroll">{test_0911()}</div>
<p class="muted">칸 아래 작은 글씨: 찾음·놓침(정답이 '다름'인 칸), 경고 없음(맞음)·잘못 경고(정답이 '같음'인 칸), 확인 필요(판정을 미룸). '같은 AI 1회'의 판정은 Claude가 답을 읽고 매겼다.</p>

<h2>5. 생성형 AI 활용</h2>
<p>Claude(Anthropic, Claude Code): 주제 조사, 표본 1차 판정과 7건 재확인, 시험용 표본 선정·정답 작성, 시험 실행·채점, PoC 코드와 문서 작성. Claude Haiku 5.5(PoC 안): 근거 문장 찾기, 마감 날짜·자격 조건 고르기, 항목별 짧은 요약. 날짜·시각·금액 읽기와 판정은 코드가 한다.</p>
</main>
<footer class="wrap foot"><p><a href="/">원문 확인으로 돌아가기</a></p></footer>
</body>
</html>
"""
    OUT.write_text(html, encoding="utf-8")
    print("wrote", OUT.relative_to(ROOT), len(html))


if __name__ == "__main__":
    main()
