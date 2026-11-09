"""요약 포털 페이지에서 '위쪽 칸'과 '본문'을 따로 꺼낸다.

- 링커리어: 페이지 HTML 안 __NEXT_DATA__ (Apollo 상태)에 칸 값과 상세내용 HTML이 들어 있다.
- 온통청년: 요약 칸(신청기간·신청자격 등)이 서버 HTML에는 비어 있고 브라우저에서 자바스크립트로
  채워진다. 서버 HTML로 값을 못 꺼내면 PortalError를 내고, 화면은 붙여 넣기로 안내한다.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

from .textsrc import ROLE_LABEL, SourceDoc, html_doc, lines_to_segments

KST = timezone(timedelta(hours=9))


NOTE_ACTIVITY = ("대외활동 공고의 위쪽 칸 중 활동지역·활동기간·모집인원 칸은 이 PoC가 읽지 않습니다. "
                 "지역 조건은 활동지역 칸에 적혀 있을 수 있습니다.")


class PortalError(Exception):
    pass


def detect_portal(url: str) -> str | None:
    if re.match(r"https?://(www\.)?linkareer\.com/activity/\d+", url or ""):
        return "linkareer"
    if re.match(r"https?://(www\.)?youthcenter\.go\.kr/.*ythPlcyDetail/\d+", url or ""):
        return "youthcenter"
    return None


def _ms_to_kst(ms) -> datetime | None:
    if ms in (None, "", 0):
        return None
    return datetime.fromtimestamp(int(ms) / 1000, tz=KST)


def _fmt_day(dt: datetime | None) -> str:
    return dt.strftime("%Y.%m.%d") if dt else ""


# ---------------------------------------------------------------- 링커리어

def parse_linkareer(html: str, url: str) -> tuple[SourceDoc, SourceDoc, dict]:
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise PortalError("링커리어 페이지에서 내장 데이터(__NEXT_DATA__)를 찾지 못했습니다. 요약 글을 붙여 넣어 주세요.")
    data = json.loads(m.group(1))
    try:
        state = data["props"]["pageProps"]["__APOLLO_STATE__"]
    except KeyError as e:
        raise PortalError("링커리어 내장 데이터 구조가 예상과 다릅니다. 요약 글을 붙여 넣어 주세요.") from e
    act_id = re.search(r"/activity/(\d+)", url).group(1)
    act = state.get(f"Activity:{act_id}")
    if not act:
        raise PortalError("링커리어 내장 데이터에서 공고를 찾지 못했습니다(삭제됐을 수 있음).")

    def deref(x):
        if isinstance(x, dict) and "__ref" in x:
            return state.get(x["__ref"], {})
        return x

    targets = [deref(t).get("name", "") for t in act.get("targets") or []]
    benefits = [deref(b).get("name", "") for b in act.get("benefits") or []]
    reward = act.get("tenThousandUnitOfReward")
    start = _ms_to_kst(act.get("recruitStartAt"))
    close = _ms_to_kst(act.get("recruitCloseAt"))

    fields: list[tuple[str, str]] = [("공고명", act.get("title") or "")]
    if act.get("organizationName"):
        fields.append(("주최", act["organizationName"]))
    if targets:
        fields.append(("참여대상", ", ".join(t for t in targets if t)))
    if reward not in (None, "", 0, "0"):
        fields.append(("시상규모", f"{int(reward):,}만 원"))
    if benefits:
        fields.append(("혜택", ", ".join(b for b in benefits if b)))
    if act.get("recruitType") == "ALWAYS":
        fields.append(("접수기간", "상시"))
    elif act.get("recruitType") == "ASAP":
        # 화면에는 날짜 대신 '채용 시 마감'이 나온다(내장 데이터의 마감값은 화면에 보이지 않음)
        fields.append(("접수기간", f"{_fmt_day(start)} ~ 채용 시 마감".strip(" ~")))
        close = None
    elif close:
        fields.append(("접수기간", f"{_fmt_day(start)} ~ {_fmt_day(close)}".strip(" ~")))
    lines = [f"{k}: {v}" for k, v in fields if v]
    top = SourceDoc(role="top", label=ROLE_LABEL["top"], origin=url, kind="linkareer-fields",
                    segments=lines_to_segments(lines, "top"))
    if close:
        top.notes.append(
            f"페이지 내장 데이터의 마감값(recruitCloseAt)은 {close.strftime('%Y-%m-%d %H:%M:%S')}입니다. "
            "화면의 접수기간 칸에는 시각이 나오지 않습니다."
        )

    if act.get("activityTypeID") == 1 or act.get("type") == 1:
        top.notes.append(NOTE_ACTIVITY)
    if act.get("activityTypeID") == 5 or act.get("type") == 5:
        top.notes.append("채용·인턴 공고의 위쪽 칸 중 학력·모집직무·근무지역 칸은 이 PoC가 아직 읽지 않습니다. "
                         "참가 자격의 '칸엔 없음'은 그 때문일 수 있습니다.")

    detail = deref(act.get("detailText")) or {}
    body_html = detail.get("text") or ""
    body = html_doc(body_html, "body", url, kind="linkareer-body", drop_site_chrome=False)
    body.notes = [n for n in body.notes if "자바스크립트" not in n]
    if body.char_count() < 50:
        body.notes.append("상세내용이 거의 이미지(포스터)라 글자로 읽을 수 있는 내용이 적습니다.")

    meta = {
        "portal": "linkareer",
        "title": act.get("title"),
        "homepage_url": act.get("homepageURL") or act.get("applyDetail"),
        "recruit_close_at": close.isoformat() if close else None,
        "fields": dict(fields),
    }
    return top, body, meta


# ---------------------------------------------------------------- 온통청년

_YC_FIELDS = [
    ("_plcyNm", "정책명"),
    ("_plcySprtCn", "지원내용"),
    ("_bizPrdSeCd", "사업 운영 기간"),
    ("_aplyPrdSeCd", "사업 신청기간"),
    ("_sprtSclLmtYn", "지원 규모"),
    ("_sprtTrgtAgeLmtYn", "연령"),
    ("_mrgSttsCd", "혼인여부"),
    ("_habRgnList", "거주지역"),
    ("_earnCndSeCd", "소득"),
    ("_qlfcAcbgList", "학력"),
    ("_mjrCndList", "전공"),
    ("_empmSttsList", "취업상태"),
    ("_spclFldList", "특화분야"),
    ("_addAplyQlfcCndCn", "추가사항"),
    ("_ptcpPrpTrgtCn", "참여제한 대상"),
    ("_plcyAplyMthdCn", "신청절차"),
    ("_srngMthdCn", "심사 및 발표"),
    ("_sbmsnDcmntCn", "제출 서류"),
]


def parse_youthcenter(html: str, url: str) -> tuple[SourceDoc, None, dict]:
    soup = BeautifulSoup(html, "lxml")
    fields = []
    for el_id, name in _YC_FIELDS:
        el = soup.find(id=el_id)
        if el is None:
            continue
        val = el.get_text(" ", strip=True)
        if val:
            fields.append((name, val))
    if not any(name in ("사업 신청기간", "연령", "지원내용") for name, _ in fields):
        raise PortalError(
            "온통청년 상세 페이지의 요약 칸(신청기간·신청자격 등)은 서버에서 받은 HTML에 비어 있고, "
            "브라우저에서 자바스크립트로 채워집니다. 이 PoC는 그 칸을 서버에서 읽지 못합니다. "
            "페이지의 요약 칸 글을 복사해 '요약 글 붙여 넣기'에 넣어 주세요."
        )
    lines = [f"{k}: {v}" for k, v in fields]
    top = SourceDoc(role="top", label=ROLE_LABEL["top"], origin=url, kind="youthcenter-fields",
                    segments=lines_to_segments(lines, "top"))
    return top, None, {"portal": "youthcenter", "fields": dict(fields)}
