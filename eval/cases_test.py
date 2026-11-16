"""시험용 표본(2026-11-09, 15건) 정의.

정답표는 11/9 도구 코드와 결과를 보지 않은 별도 AI 세션이 원문만 보고 1차로 적은 `정답표.csv`의 사본이다(사람 전수 확인 없음).
사본은 eval/fixtures/test_2026-11-09/에 두고 sha256으로 원본과 같은지 확인했다(읽기만 함).

엔진(wonmun/)·프롬프트·판정 규칙은 이 시험 전후로 고치지 않는다.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "eval/fixtures/test_2026-11-09"
CSV_PATH = FIX / "정답표.csv"
YC_JSON = FIX / "온통청년_요약.json"
CSV_SHA256 = "f46ae7fa9cfb00eccf90c5dceb562662f08fc33e0aa8ba158446dacfe4b83214"
# 받은 원본(로컬 전용, git 제외: data/runs/ 아래)
SOURCES_DIR = ROOT / "data/runs/test_sources/2026-11-09"
TODAY = "2026-11-09"

TEST_IDS = ["T01", "T02", "T03", "T04", "T05", "T06", "T08", "T10", "R1", "R2",
            "T11", "T12", "T13", "T14", "T15"]
YOUTH_IDS = ["T11", "T12", "T13", "T14", "T15"]
REPEAT_IDS = ["T02", "T06", "T10", "T12", "R2"]

# 확신도 '낮음'(정답표 확신도 칸): 빼고 센 숫자도 따로 낸다.
LOW_CONF = {("T11", "eligibility"), ("T14", "deadline")}

# 원문을 넣을지: 11/9 엔진의 fetch_url로 받아 본 뒤, AI 호출 전에 정함(eval/results_test/fetch_log.json 근거).
# 기준: 받지 못함(로그인·차단·연결 실패) 또는 받은 글에 그 공고 본문이 없음(이미지·첨부뿐, 다른 페이지) → 원문 없이.
# 그 밖에는 받은 그대로 넣는다(마감·자격 문장이 일부 빠져 있어도).
NO_ORIGINAL = {
    "T02": "원문 주소(forms.gle 구글폼)가 HTTP 401(로그인 요구)로 거절. 우회하지 않음.",
    "T03": "원문 게시물 본문이 비어 있고 첨부(포스터 JPG·출품원서 HWP)뿐. 받은 글 103자(제목·첨부 이름).",
    "T05": "원문(한국석유관리원 게시물) 받기 실패: 연결 끊김(ReadError, Connection reset by peer). 2회 시도.",
    "T08": "원문(창비) 받기 실패: SSL 인증서 확인 실패(CERTIFICATE_VERIFY_FAILED). 인증서 검사를 끄지 않음. 2회 시도.",
    "R1": "원문 첫 주소(gb.go.kr/page/10109/67.do)가 경상북도 고시공고 '목록' 1쪽이라 이 공고 글이 없음(다른 공고 제목만).",
    "R2": "원문(CJ ENM 오펜 모집요강)이 통이미지라 받은 글 5자('스토리', '뮤직').",
}

# 정답 이름
DL_DATE = "날짜 다름"
DL_TIME = "시각 빠짐"
DL_SAME = "같음"
DL_NONE = "원문에 마감 없음"
EL_DIFF = "다름"
EL_SAME = "같음"
EL_NONE = "원문에 자격 없음"


def first_url(cell: str) -> str:
    """원문_URL 칸의 첫 주소(괄호 안 보조 주소는 쓰지 않음)."""
    m = re.match(r"\s*(https?://\S+)", cell)
    if not m:
        raise ValueError(f"원문 주소를 읽지 못함: {cell!r}")
    return m.group(1).rstrip(",")


def load_truth() -> dict[str, dict]:
    out: dict[str, dict] = {}
    with CSV_PATH.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            cid = row["번호"]
            out[cid] = {
                "source_portal": row["출처"], "title": row["공고명"], "portal_url": row["포털_URL"],
                "original_url_cell": row["원문_URL"], "original_url": first_url(row["원문_URL"]),
                "deadline": {"label": row["마감_정답"], "summary": row["요약_마감"],
                             "summary_body_time": row["요약_본문_마감시각"], "original": row["원문_마감"],
                             "quote": row["원문_마감_인용"]},
                "eligibility": {"label": row["자격_정답"], "summary": row["요약_자격"],
                                "original": row["원문_자격"], "quote": row["원문_자격_인용"]},
                "confidence": row["확신도"], "memo": row["메모"],
            }
    missing = [c for c in TEST_IDS if c not in out]
    if missing:
        raise ValueError(f"정답표에 없는 공고: {missing}")
    return out


def youth_paste(cid: str) -> str:
    """온통청년 요약(summary_text)을 붙여 넣은 요약 글로 쓴다.

    summary_text는 칸 사이를 ' / '로 이어 적어 둔 것이라, 개발용 Y1 붙여 넣기와 같이 한 칸을 한 줄로 바꾼다.
    글자는 바꾸지 않는다(구분자 ' / '만 줄바꿈으로).
    """
    rows = json.loads(YC_JSON.read_text(encoding="utf-8"))
    row = next(r for r in rows if r["id"] == cid)
    return "\n".join(part.strip() for part in row["summary_text"].split(" / "))
