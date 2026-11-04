"""개발용 표본 정의. 정답표는 11/4 공고대조_기록.csv(사용자 iCloud 폴더 원본의 복사본)."""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "eval/fixtures/공고대조_기록_2026-11-04.csv"
SOURCES_DIR = ROOT / "data/dev_sources/2026-11-04"
FETCH_DATE = "2026-11-04"

CSV_ITEM = {
    "마감 일시": "deadline", "참가 자격": "eligibility", "참가 형태·인원": "team", "시상": "prize",
    "제출물·분량": "submission", "실격·감점": "penalty", "생성형 AI·저작권": "ai_copyright",
}

# CSV 단계에서 빼라고 정한 공고(과제 지시)
EXCLUDED_BY_RULE = {
    "L03": "원문 확보 실패(접수 폼은 네이버 로그인 필요). CSV 전 칸 '확인 불가'.",
    "L06": "원문이 주최 인스타그램 게시물(대체 원문). HTML로 읽을 수 없음.",
    "L09": "원문이 주최 인스타그램 게시물(대체 원문). HTML로 읽을 수 없음.",
    "L16": "원문 확보 실패(KOCCA 게시판·검색 모두 없음), 상세내용이 포스터 1장.",
    "Y3": "원문 사이트가 프레임 구조라 개별 공지 미확인. CSV 전 칸 '확인 불가'.",
}

# 원문 주소(CSV 원문_파일 칸에서 고름). 요약 주소는 CSV 요약_URL.
ORIGINAL_URL = {
    "L01": "https://www.silson24.or.kr/claim/web/custSupp/custSuppNoticeDetail?postNo=32526&postType=notice",
    "L02": "https://www.hanaw.com/contest/contest.html",
    "L04": "https://www.nafi.re.kr/home/kor/board.do?menuPos=37&act=detail&idx=4498",
    "L05": "https://appdevchallenge.auto-hmg.io/",
    "L07": "https://aida.kisti.re.kr/competition/main/competition/COMP_000000000000050/detail.do",
    "L08": "https://wma.co.kr/ax",
    "L10": "https://www.forest.go.kr/kfsweb/cop/bbs/selectBoardArticle.do?nttId=3225569&bbsId=BBSMSTR_1855&mn=NKFS_06_08_07",
    "L11": "https://jb-ai.kr/2026-song",
    "L12": "https://www.mak.or.kr:444/html/assct_event/others.asp?no=13029",
    "L13": "https://blog.naver.com/smwupradweek/224460464457",
    # CSV에는 고시공고 번호와 '동구청 공식 블로그'만 적혀 있다. 블로그 주소는 링커리어 홈페이지 칸의 주소.
    "L14": "https://blog.naver.com/bsdonggublog/224463183087",
    "L15": "https://www.knu39.org/bbs/board.php?bo_table=notice&wr_id=615",
    "L17": "https://www.eariul.go.kr/smgeco/planweb/board/view.9is?dataUid=52dc4f85a09e8c8b01a19476582b5217",
    "L18": "https://www.dobong.or.kr/main/main.php?categoryid=06&menuid=01&groupid=00&board=view&no=3856",
    "L19": "https://www.yeosu.go.kr/tour/information/news/tour_news?idx=15874&mode=view",
    "L20": "https://www.miryang.go.kr/tur/bbs/selectBoardDetail.do?bbsId=BBSMSTR_000000000227&mnNo=60101000000&nttId=197957",
    # 온통청년 페이지의 '신청바로가기' 주소(menuNo 포함). CSV 주소는 menuNo가 없어 다른 화면이 열림.
    "Y1": "https://www.kocca.kr/kocca/bbs/view/B0000137/2012372.do?menuNo=204802",
    "Y2": "https://www.dgist.ac.kr/tim/sub02_02.do",
}

# 온통청년 요약 칸은 서버 HTML에 비어 있어 붙여 넣기로 대신한다.
SUMMARY_PASTE = {"Y1": ROOT / "eval/fixtures/Y1_summary_paste.txt"}


def load_truth() -> dict[str, dict]:
    """{공고ID: {"title", "summary_url", "items": {item_key: {"label", "summary", "original", "memo"}}}}"""
    out: dict[str, dict] = {}
    with CSV_PATH.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            cid = row["공고ID"]
            if cid == "예시":
                continue
            case = out.setdefault(cid, {"title": row["공고명"], "summary_url": "", "items": {}})
            if row["요약_URL"]:
                case["summary_url"] = row["요약_URL"]
            case["items"][CSV_ITEM[row["칸"]]] = {
                "label": row["판정"], "summary": row["요약에_적힌_값"], "original": row["원문_값"],
                "location": row["원문_위치"], "memo": row["메모"],
            }
    return out


def candidate_ids() -> list[str]:
    truth = load_truth()
    ids = [c for c in truth if c not in EXCLUDED_BY_RULE]
    order = {f"L{i:02d}": i for i in range(1, 21)} | {f"Y{i}": 100 + i for i in range(1, 4)}
    return sorted(ids, key=lambda c: order.get(c, 999))


# ---------------------------------------------------------------- 11/4 받아 본 결과로 정한 표본
# (eval/fetch_log.json 근거) 원문이 HTML 글자로 읽힌 공고만 본 표본에 넣는다.
MAIN_IDS = ["L02", "L04", "L05", "L07", "L10", "L11", "L13", "L14", "L19", "L20", "Y1"]

EXCLUDED_AFTER_FETCH = {
    "L01": "원문(실손24 공지)이 자바스크립트 화면이라 서버 HTML에 본문 글자가 0자. CSV도 포스터 이미지 기준.",
    "L08": "원문(wma.co.kr/ax)이 자바스크립트 화면이라 서버 HTML 글자 131자, 날짜 0개.",
    "L12": "원문(음협 게시판) 본문이 이미지(jpg)라 글자 248자뿐. 링커리어 안 칸↔본문 비교만 보조 실행.",
    "L15": "원문 사이트가 자바스크립트 확인 화면(js_check)을 먼저 보냄. 우회하지 않음.",
    "L17": "원문 주소가 11/4 오후 받았을 때 '게시판이 존재하지 않습니다' 오류 화면(29자). 11/4 조사 이후 바뀐 것으로 보임.",
    "L18": "원문 HTML 본문이 이미지이고 공고문은 PDF 첨부(자바스크립트 POST 내려받기)라 주소로 읽지 못함.",
    "Y2": "원문(DGIST)이 자동 요청을 거부(사전 확인 때 HTTP 403, 본 수집 때 연결 오류). 요약(온통청년)도 서버 HTML에 칸 값이 없음.",
}

# 원문 없이 '요약 위쪽 칸 ↔ 요약 본문'만 보는 보조 실행(본 표본 숫자에 섞지 않는다)
STAGE1_IDS = ["L01", "L08", "L12", "L15", "L17", "L18"]

# 3회 반복 일치율을 볼 5건(마감·자격 차이가 있는 공고 위주)
REPEAT_IDS = ["L02", "L07", "L13", "L20", "Y1"]
