"""값 정리와 판정 규칙(코드). AI 판단을 거치지 않는다.

순서
1. 인용 검사: AI 인용이 출처에 글자 그대로 없으면 버린다. 남은 인용이 없으면 그 출처 값은 '확인 필요'.
2. 값 정리: 마감은 인용 문장에서 날짜·시각을 정규식으로 다시 읽는다. 자격·시상의 AI 정규화 값도
   인용 안에 근거 낱말·숫자가 있는 것만 남긴다.
3. 판정: 설계서 2장 규칙. 요약 위쪽 칸 ↔ 원문(원문이 있으면), 요약 위쪽 칸 ↔ 요약 본문(1단계).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import ITEMS, ITEM_NAMES
from .dates import END_OF_DAY, read_deadline
from .money import parse_amounts, prize_kind, won_str
from .quotes import QuoteHit, QuoteIndex, check_quotes

# 판정 이름(화면에 그대로 나간다). '일치'라는 말은 쓰지 않는다.
DIFF = "불일치"
TIME_MISSING = "시각 누락"
TOP_ONLY_MISSING = "칸엔 없음·본문엔 있음"
NOT_IN_SUMMARY = "요약에 없음"
NEITHER = "원문에도 없음"
NO_DIFF = "다른 점을 찾지 못함"
NEEDS_CHECK = "확인 필요"
NO_ORIGINAL = "원문 미입력"

RED = {DIFF, TIME_MISSING, NOT_IN_SUMMARY, TOP_ONLY_MISSING}
SEVERITY = {DIFF: "red", TIME_MISSING: "red", NOT_IN_SUMMARY: "red", TOP_ONLY_MISSING: "red",
            NO_DIFF: "ok", NEITHER: "ok", NEEDS_CHECK: "check", NO_ORIGINAL: "check"}

_WEEKDAY = "월화수목금토일"


@dataclass
class SourceValue:
    role: str
    status: str  # found | absent | unverified | not_given
    quotes: list[QuoteHit] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    value: str = ""  # 화면에 보일 값
    value_by: str = ""  # "코드" (코드가 다시 읽음) 또는 "AI 요약"
    norm: dict = field(default_factory=dict)
    ai: dict = field(default_factory=dict)
    note: str = ""

    @property
    def found(self) -> bool:
        return self.status == "found"

    def to_dict(self) -> dict:
        return {
            "role": self.role, "status": self.status, "value": self.value, "value_by": self.value_by,
            "norm": {k: (sorted(v) if isinstance(v, set) else v) for k, v in self.norm.items()},
            "quotes": [q.__dict__ for q in self.quotes], "rejected_quotes": self.rejected,
            "ai": self.ai, "note": self.note,
        }


# ---------------------------------------------------------------- 값 정리

def _fmt_deadline(d, t) -> str:
    s = f"{d.isoformat()}({_WEEKDAY[d.weekday()]})"
    if t == "24:00":
        return s + " 24:00(그날 끝)"
    return s + (f" {t}" if t else " 시각 없음")


_OPEN_RE = re.compile(r"누구나|제한\s*없|제한없|전\s*국민|무관|대상\s*제한\s*없음|내[·ㆍ]?\s*외국인\s*누구나")
_GROUP_EVIDENCE = {
    "누구나": r"누구나|제한\s*없|제한없|전\s*국민",
    "일반인": r"일반|누구나|국민|성인",
    "초등학생": r"초등", "중학생": r"중학|중등", "고등학생": r"고등학생|고교생|고등부",
    "청소년": r"청소년", "대학생": r"대학|학부", "대학원생": r"대학원|\(원\)|석사|박사",
    "휴학생": r"휴학", "졸업(예정)자": r"졸업|학위", "고졸 이상": r"고등학교\s*졸업|고졸",
    "대졸 이상": r"대학\s*졸업|대졸|학사", "청년": r"청년", "직장인": r"직장|재직|일반인",
    "미취업자": r"미취업|구직|취업\s*준비", "재직자": r"재직", "전공자": r"전공",
    "창업자·스타트업": r"창업|스타트업", "기업·법인": r"기업|법인|사업자|회사",
    "기관·단체": r"기관|단체|협회", "외국인": r"외국",
}
_COVERS_ALL = {"누구나", "일반인"}
_AGE_LABELS = {"청년"}
_ORG_TAGS = {"기업·법인", "기관·단체"}
# '전국'·'제한 없음' 같은 지역 값은 조건이 아니다(11/4 r1 결과를 본 뒤 추가).
_NO_REGION = re.compile(r"^(전국|전\s*지역|제한\s*없음|제한없음|무관|없음|국내)$")
_COVER = {
    "고졸 이상": {"대학생", "대학원생", "휴학생", "졸업(예정)자", "대졸 이상", "직장인", "재직자",
                "미취업자", "청년", "일반인"},
    "대졸 이상": {"대학원생", "졸업(예정)자", "직장인", "재직자"},
    "대학생": {"휴학생"},
    "직장인": {"재직자"},
    "재직자": {"직장인"},
}


def _covered(groups: set[str], tag: str) -> bool:
    if tag in groups or groups & _COVERS_ALL:
        return True
    return any(tag in _COVER.get(g, set()) for g in groups)


_AGE_RANGE = re.compile(r"(?<![\d.])(\d{1,2})\s*세?\s*(?:[~∼～〜\-–—]|부터)\s*(?:만\s*)?(\d{1,2})\s*세")


def _age_numbers(text: str) -> set[int]:
    """근거 글에 적힌 나이 숫자. '19~39세'처럼 앞 숫자에 '세'가 없는 범위도 읽는다."""
    nums = {int(n) for n in re.findall(r"(\d{1,2})\s*세", text)}
    for a, b in _AGE_RANGE.findall(text):
        nums |= {int(a), int(b)}
    return nums


def _elig_norm(ai: dict, text: str) -> tuple[dict, list[str]]:
    dropped = []
    open_all = bool(ai.get("open_to_all")) and bool(_OPEN_RE.search(text))
    if ai.get("open_to_all") and not open_all:
        dropped.append("'제한 없음'(인용에 근거 낱말 없음)")
    groups = set()
    for g in ai.get("groups") or []:
        pat = _GROUP_EVIDENCE.get(g)
        if g == "기타":
            continue
        if pat and re.search(pat, text):
            groups.add(g)
        else:
            dropped.append(f"신분 '{g}'")
    nums = _age_numbers(text)
    age_min = ai.get("age_min", -1)
    age_max = ai.get("age_max", -1)
    if age_min not in (-1, None) and age_min not in nums:
        dropped.append(f"나이 {age_min}")
        age_min = -1
    if age_max not in (-1, None) and age_max not in nums:
        dropped.append(f"나이 {age_max}")
        age_max = -1
    applicant = ai.get("applicant") or "알 수 없음"
    if applicant in ("기업·기관", "개인과 기업·기관 모두") and not re.search(_GROUP_EVIDENCE["기업·법인"] + "|기관|단체", text):
        dropped.append(f"신청 주체 '{applicant}'")
        applicant = "알 수 없음"
    nationality = ai.get("nationality") or "언급 없음"
    if nationality == "외국인" and not re.search(r"외국", text):
        dropped.append("국적 '외국인'")
        nationality = "언급 없음"
    if nationality == "내국인" and not re.search(r"국민|내국인|한국\s*국적|대한민국", text):
        dropped.append("국적 '내국인'")
        nationality = "언급 없음"
    region = (ai.get("region") or "").strip()
    if _NO_REGION.match(region.replace(" ", "")) or _NO_REGION.match(region):
        region = ""
    if region and not any(tok in text for tok in re.split(r"[\s,·/]+", region) if len(tok) >= 2):
        dropped.append(f"지역 '{region}'")
        region = ""
    norm = {
        "open": open_all, "applicant": applicant,
        "age_min": age_min if age_min not in (None,) else -1,
        "age_max": age_max if age_max not in (None,) else -1,
        "groups": groups, "region": region, "nationality": nationality,
        "other": [o for o in (ai.get("other") or []) if o],
    }
    return norm, dropped


def _elig_str(n: dict) -> str:
    parts = []
    if n["open"]:
        parts.append("제한 없음")
    if n["applicant"] in ("기업·기관", "개인과 기업·기관 모두"):
        parts.append(f"신청 주체: {n['applicant']}")
    lo, hi = n["age_min"], n["age_max"]
    if lo != -1 and hi != -1:
        parts.append(f"만 {lo}~{hi}세")
    elif lo != -1:
        parts.append(f"만 {lo}세 이상")
    elif hi != -1:
        parts.append(f"만 {hi}세 이하")
    if n["groups"]:
        parts.append(", ".join(sorted(n["groups"])))
    if n["region"]:
        parts.append(f"지역: {n['region']}")
    if n["nationality"] in ("내국인", "외국인"):
        parts.append(f"국적: {n['nationality']}")
    if n["other"]:
        parts.append("기타: " + "; ".join(n["other"][:2]))
    return " · ".join(parts) if parts else "(조건 정리 못함)"


def _prize_norm(ai: dict, text: str, context: str = "") -> tuple[dict, str]:
    amounts = parse_amounts(text)
    total = int(ai.get("total_won") or 0)
    how = ""
    if total and total in amounts:
        how = "적힌 금액"
    elif total and amounts and total == sum(amounts):
        how = "적힌 금액의 합(코드 검산)"
    elif total:
        how = "AI 합산(코드 검산 못함)"
    # 현금/현물은 인용이 걸친 문단 전체 글자로 가른다(인용이 '1,000,000원'처럼 짧으면 '상금' 낱말이 빠져서).
    # (11/4 r1 결과를 본 뒤 바꿈: L13에서 현금+상품권을 상품권만으로 읽었음)
    kind = prize_kind(context or text)
    return {"total": total, "total_how": how, "verified_total": how in ("적힌 금액", "적힌 금액의 합(코드 검산)"),
            "kind": kind, "amounts": amounts}, how


def build_value(item: str, role: str, ai: dict | None, index: QuoteIndex | None,
                ref_year: int) -> SourceValue:
    if index is None or ai is None:
        return SourceValue(role=role, status="not_given")
    hits, rejected = check_quotes(ai.get("quotes") or [], index)
    sv = SourceValue(role=role, status="absent", quotes=hits, rejected=rejected, ai=ai)
    if not ai.get("found") and not hits:
        return sv
    if not hits:
        sv.status = "unverified"
        sv.note = "AI가 낸 근거 문장이 출처에 글자 그대로 없어 버렸습니다."
        return sv
    sv.status = "found"
    qtexts = [h.text for h in hits]
    text = " / ".join(qtexts)
    if item == "deadline":
        dr = read_deadline(qtexts, ai.get("deadline_date", ""), ai.get("deadline_time", ""), ref_year)
        if not dr.verified:
            sv.status = "unverified"
            sv.note = f"마감 날짜를 인용 문장에서 다시 읽지 못했습니다({dr.reason})."
            return sv
        sv.norm = {"date": dr.date.isoformat(), "time": dr.time, "raw": dr.raw,
                   "role_text": ai.get("date_role", "")}
        sv.value = _fmt_deadline(dr.date, dr.time)
        sv.value_by = "코드"
    elif item == "eligibility":
        norm, dropped = _elig_norm(ai, text)
        sv.norm = norm
        sv.value = _elig_str(norm)
        sv.value_by = "코드"
        if dropped:
            sv.note = "인용에 근거가 없어 뺀 AI 값: " + ", ".join(dropped)
    elif item == "prize":
        seg_text = {seg.sid: seg.text for seg in index.doc.segments}
        context = " / ".join(seg_text[sid] for h in hits for sid in h.sids if sid in seg_text)
        norm, how = _prize_norm(ai, text, context)
        sv.norm = norm
        val = won_str(norm["total"]) if norm["total"] else (ai.get("value") or "")
        if norm["kind"] != "알 수 없음":
            val += f" ({norm['kind']})"
        sv.value = val.strip()
        sv.value_by = "코드" if norm["verified_total"] else "AI 요약"
        if how and not norm["verified_total"]:
            sv.note = f"총액은 {how}."
    else:
        sv.value = ai.get("value") or ""
        sv.value_by = "AI 요약"
    return sv


# ---------------------------------------------------------------- 비교

@dataclass
class Finding:
    kind: str  # contradiction | missing_time | missing_dim | absent | none | check | neither
    reason: str
    dim: str = ""


def _josa(word: str, pair: str) -> str:
    """받침에 맞춰 은/는, 이/가, 와/과를 붙인다."""
    a, b = pair.split("/")
    ch = word.strip()[-1:] if word.strip() else ""
    if "가" <= ch <= "힣":
        has = (ord(ch) - 0xAC00) % 28 != 0
        return word + (a if has else b)
    return word + a


def _days(a: str, b: str) -> int:
    from datetime import date
    return (date.fromisoformat(a) - date.fromisoformat(b)).days


def compare_deadline(a: SourceValue, b: SourceValue, a_name: str, b_name: str) -> Finding:
    if a.status == "unverified" or b.status == "unverified":
        return Finding("check", "근거를 확인하지 못한 값이 있어 비교하지 않았습니다.")
    if b.status == "absent":
        if a.status == "absent":
            return Finding("neither", f"{a_name}·{b_name} 모두 마감이 없습니다.")
        return Finding("check", f"{b_name}에서 마감 문장을 찾지 못했습니다.")
    if a.status == "absent":
        return Finding("absent", f"{a_name}에 마감이 없습니다.", "date")
    ad, bd = a.norm["date"], b.norm["date"]
    at, bt = a.norm.get("time"), b.norm.get("time")
    if ad != bd:
        diff = _days(ad, bd)
        side = "늦음" if diff > 0 else "빠름"
        return Finding("contradiction",
                       f"날짜가 다릅니다. {a_name} {ad}, {b_name} {bd} ({_josa(a_name, '이/가')} {abs(diff)}일 {side}).", "date")
    if bt and bt not in END_OF_DAY:
        if not at:
            return Finding("missing_time",
                           f"같은 날이지만 {_josa(b_name, '은/는')} {bt} 마감인데 {a_name}에 시각이 없습니다. 밤까지 열린 것처럼 읽힐 수 있습니다.",
                           "time")
        if at != bt:
            return Finding("contradiction", f"시각이 다릅니다. {a_name} {at}, {b_name} {bt}.", "time")
    elif at and at not in END_OF_DAY and bt in END_OF_DAY:
        return Finding("contradiction", f"시각이 다릅니다. {a_name} {at}, {b_name} {bt}.", "time")
    return Finding("none", "날짜와 시각에서 다른 점을 찾지 못했습니다.")


def _elig_dims(n: dict) -> dict:
    groups = set(n.get("groups") or set())
    return {
        "open": bool(n.get("open")) or bool(groups & {"누구나"}),
        "covers_all": bool(n.get("open")) or bool(groups & _COVERS_ALL),
        "applicant": {"기업·기관": "org", "개인과 기업·기관 모두": "both",
                      "개인": "person", "개인 또는 팀": "person"}.get(n.get("applicant"), None),
        "age": (n.get("age_min", -1), n.get("age_max", -1)) if (n.get("age_min", -1) != -1 or n.get("age_max", -1) != -1) else None,
        # 기업·기관 태그는 '누가 신청하느냐'(applicant)에서 따로 본다. 신분·학적 제한으로 세지 않는다.
        # (11/4 r1 결과를 본 뒤 바꿈: '기관 또는 개인'이 제한으로 읽혀 L07을 잘못 경고했음)
        "groups": groups - _COVERS_ALL - {"기타"} - _ORG_TAGS,
        "region": n.get("region") or "",
        "nationality": n.get("nationality") if n.get("nationality") in ("내국인", "외국인") else None,
    }


def _restrictions(d: dict) -> list[str]:
    out = []
    if d["age"]:
        out.append("연령")
    if d["groups"] and not d["covers_all"]:
        out.append("신분·학적")
    if d["region"]:
        out.append("지역")
    if d["nationality"]:
        out.append("국적")
    if d["applicant"] == "org":
        out.append("신청 주체(기업·기관)")
    return out


def compare_eligibility(a: SourceValue, b: SourceValue, a_name: str, b_name: str) -> Finding:
    if a.status == "unverified" or b.status == "unverified":
        return Finding("check", "근거를 확인하지 못한 값이 있어 비교하지 않았습니다.")
    if b.status == "absent":
        if a.status == "absent":
            return Finding("neither", f"{a_name}·{b_name} 모두 자격 조건이 없습니다.")
        return Finding("check", f"{b_name}에서 자격 문장을 찾지 못했습니다.")
    if a.status == "absent":
        return Finding("absent", f"{a_name}에 참가 자격이 없습니다.", "all")
    A, B = _elig_dims(a.norm), _elig_dims(b.norm)
    ra, rb = _restrictions(A), _restrictions(B)
    if A["open"] and rb:
        return Finding("contradiction",
                       f"{_josa(a_name, '은/는')} '제한 없음'인데 {b_name}에는 조건이 있습니다({', '.join(rb)}: {b.value}).", "open")
    if B["open"] and ra and not A["covers_all"]:
        return Finding("contradiction",
                       f"{_josa(b_name, '은/는')} '제한 없음'인데 {a_name}에만 조건이 있습니다({', '.join(ra)}: {a.value}).", "open")
    if A["applicant"] and B["applicant"] and A["applicant"] != B["applicant"] and "both" not in (A["applicant"], B["applicant"]):
        label = {"org": "기업·기관", "person": "개인"}
        return Finding("contradiction",
                       f"신청 주체가 다릅니다. {a_name} {label[A['applicant']]}, {b_name} {label[B['applicant']]}.", "applicant")
    if B["applicant"] == "org" and A["applicant"] is None and not A["covers_all"] and A["groups"] & {"청년", "미취업자", "대학생", "일반인", "직장인"}:
        return Finding("contradiction",
                       f"{b_name}의 신청 주체는 기업·기관인데 {_josa(a_name, '은/는')} 개인 조건({', '.join(sorted(A['groups']))})만 적혀 있습니다.", "applicant")
    if A["age"] and B["age"] and A["age"] != B["age"]:
        return Finding("contradiction", f"나이 조건이 다릅니다. {a_name} {A['age']}, {b_name} {B['age']}.", "age")
    if A["nationality"] and B["nationality"] and A["nationality"] != B["nationality"]:
        return Finding("contradiction", f"국적 조건이 다릅니다. {a_name} {A['nationality']}, {b_name} {B['nationality']}.", "nationality")
    if A["groups"] and B["groups"] and not (A["covers_all"] and B["covers_all"]):
        a_in_b = all(_covered(B["groups"] | ({"누구나"} if B["covers_all"] else set()), g) for g in A["groups"])
        b_in_a = all(_covered(A["groups"] | ({"누구나"} if A["covers_all"] else set()), g) for g in B["groups"])
        if not (a_in_b and b_in_a):
            narrower = a_name if not b_in_a else b_name
            return Finding("contradiction",
                           f"대상 범위가 다릅니다. {a_name} {', '.join(sorted(A['groups']))}, {b_name} {', '.join(sorted(B['groups']))} ({narrower} 쪽이 더 좁음).",
                           "groups")
    if A["region"] and B["region"] and A["region"] not in B["region"] and B["region"] not in A["region"]:
        return Finding("contradiction", f"지역 조건이 다릅니다. {a_name} {A['region']}, {b_name} {B['region']}.", "region")
    missing = []
    if B["age"] and not A["age"]:
        missing.append(("age", "연령"))
    if B["region"] and not A["region"]:
        missing.append(("region", "지역"))
    if B["nationality"] and not A["nationality"] and not A["open"]:
        missing.append(("nationality", "국적"))
    # '청년'은 나이로 정해지는 말이라, 나이 조건이 이미 있으면 따로 빠진 조건으로 세지 않는다
    # (시험용 T13: 요약 '만 19세~만 39세' vs 원문 '19~39세 청년'을 잘못 경고했음)
    b_groups = B["groups"] - (_AGE_LABELS if A["age"] else set())
    if b_groups and not B["covers_all"] and not A["groups"] and not A["open"]:
        missing.append(("groups", "신분·학적"))
    if missing:
        return Finding("missing_dim",
                       f"{b_name}의 조건 중 {a_name}에 없는 것: {', '.join(m[1] for m in missing)} ({b.value}).",
                       ",".join(m[0] for m in missing))
    if A["region"] and not B["region"] and b.found:
        return Finding("contradiction", f"{a_name}에만 지역 조건({A['region']})이 있습니다.", "region")
    return Finding("none", "자격 조건에서 다른 점을 찾지 못했습니다.")


def compare_prize(a: SourceValue, b: SourceValue, a_name: str, b_name: str) -> Finding:
    if a.status == "unverified" or b.status == "unverified":
        return Finding("check", "근거를 확인하지 못한 값이 있어 비교하지 않았습니다.")
    if b.status == "absent":
        if a.status == "absent":
            return Finding("neither", f"{a_name}·{b_name} 모두 시상 내용이 없습니다.")
        return Finding("check", f"{b_name}에서 시상 문장을 찾지 못했습니다.")
    if a.status == "absent":
        return Finding("absent", f"{a_name}에 시상 내용이 없습니다.", "prize")
    A, B = a.norm, b.norm
    if A.get("verified_total") and B.get("verified_total") and A["total"] != B["total"]:
        return Finding("contradiction",
                       f"금액이 다릅니다. {a_name} {won_str(A['total'])}, {b_name} {won_str(B['total'])}.", "amount")
    if A.get("total") and A.get("kind") in ("현금", "알 수 없음") and B.get("kind") == "현물·상품권":
        return Finding("contradiction",
                       f"{_josa(a_name, '은/는')} 금액('{won_str(A['total'])}')만 적어 현금처럼 읽히지만 {_josa(b_name, '은/는')} 상품권·현물입니다.", "kind")
    return Finding("none", "금액과 현금/현물 구분에서 다른 점을 찾지 못했습니다.")


def compare_presence(a: SourceValue, b: SourceValue, a_name: str, b_name: str) -> Finding:
    if b.status == "unverified":
        return Finding("check", f"{b_name} 근거를 확인하지 못했습니다.")
    if b.status == "absent":
        if a.status in ("absent", "unverified"):
            return Finding("neither", f"{a_name}·{b_name} 모두 해당 내용이 없습니다.")
        return Finding("check", f"{a_name}에는 있지만 {b_name}에서 근거를 찾지 못했습니다.")
    if a.status != "found":
        return Finding("absent", f"{b_name}에는 있는데 {a_name}에는 없습니다.", "presence")
    return Finding("none", "양쪽 모두 해당 내용이 있습니다(내용 비교는 하지 않음).")


COMPARE = {"deadline": compare_deadline, "eligibility": compare_eligibility, "prize": compare_prize}

_NAME = {"top": "요약 칸", "body": "요약 본문", "original": "원문", "summary": "요약"}


def _merge_summary(top: SourceValue, body: SourceValue) -> SourceValue:
    """제출물·실격·AI 규정처럼 '있느냐 없느냐'를 보는 항목은 요약 = 위쪽 칸 + 본문."""
    if body.status == "not_given":
        return top
    if top.found or body.found:
        quotes = top.quotes + body.quotes
        value = " / ".join(v for v in (top.value, body.value) if v)
        return SourceValue(role="summary", status="found", quotes=quotes, value=value, value_by="AI 요약")
    if "unverified" in (top.status, body.status):
        return SourceValue(role="summary", status="unverified")
    return SourceValue(role="summary", status="absent")


def _finding_to_verdict(f: Finding, body_supplies: bool = False) -> str:
    if f.kind == "contradiction":
        return DIFF
    if f.kind == "missing_time":
        return TOP_ONLY_MISSING if body_supplies else TIME_MISSING
    if f.kind == "missing_dim":
        return TOP_ONLY_MISSING if body_supplies else DIFF
    if f.kind == "absent":
        return TOP_ONLY_MISSING if body_supplies else NOT_IN_SUMMARY
    if f.kind == "neither":
        return NEITHER
    if f.kind == "check":
        return NEEDS_CHECK
    return NO_DIFF


def _stage1_verdict(stage1: dict | None, body: SourceValue) -> tuple[str, str] | None:
    """원문 없이 같은 페이지 칸↔본문만 볼 때의 판정. 본문을 기준으로 본다."""
    if not stage1:
        return None
    kind = stage1["kind"]
    if kind in ("missing_time", "missing_dim", "absent"):
        verdict = TOP_ONLY_MISSING
    elif kind in ("check", "neither") and body.status == "absent":
        return NO_ORIGINAL, "요약 본문에 해당 내용이 없어 칸만으로는 확인할 수 없습니다. 원문을 넣으면 대조합니다."
    else:
        verdict = stage1["verdict"]
    return verdict, stage1["reason"] + " (같은 페이지 칸과 본문 비교)"


def judge_item(item: str, vals: dict[str, SourceValue]) -> dict:
    top, body, orig = vals["top"], vals["body"], vals["original"]
    has_body = body.status != "not_given"
    has_orig = orig.status != "not_given"
    stage1 = stage2 = None
    verdict, reason = NO_ORIGINAL, "원문을 넣으면 대조합니다."

    if item in COMPARE:
        cmp = COMPARE[item]
        if has_body:
            f1 = cmp(top, body, _NAME["top"], _NAME["body"])
            stage1 = {"verdict": _finding_to_verdict(f1), "reason": f1.reason, "kind": f1.kind}
        if has_orig:
            f2 = cmp(top, orig, _NAME["top"], _NAME["original"])
            supplies = False
            if has_body and f2.kind in ("missing_time", "missing_dim", "absent"):
                fb = cmp(body, orig, _NAME["body"], _NAME["original"])
                supplies = fb.kind == "none"
            verdict = _finding_to_verdict(f2, supplies)
            reason = f2.reason
            if supplies:
                reason += " 같은 페이지 본문에는 원문과 같은 내용이 있습니다."
            stage2 = {"verdict": verdict, "reason": reason, "kind": f2.kind}
            if verdict == DIFF and stage1 and stage1["kind"] == "contradiction":
                reason += " (같은 페이지 칸과 본문도 서로 다릅니다.)"
            s1 = _stage1_verdict(stage1, body)
            if verdict in (NEEDS_CHECK, NEITHER) and s1 and s1[0] in RED:
                # 원문에서 근거를 못 찾았어도 같은 페이지 안에서 칸과 본문이 다르면 그것을 알린다.
                verdict, reason = s1[0], f"원문에서는 근거를 찾지 못했지만, {s1[1]}"
            elif verdict == NO_DIFF and stage1 and stage1["kind"] == "contradiction":
                # 원문과는 같아 보여도 같은 페이지 칸과 본문이 서로 다르면 알린다.
                # (11/4 r3 결과를 본 뒤 추가: L07에서 AI가 원문의 대회 전체 기간 끝(11/25)을 마감으로 고른 회차가
                #  '다른 점을 찾지 못함'으로 끝났음. 본문은 문제해결 마감 11/6)
                verdict = DIFF
                reason = (f"원문과 비교해서는 다른 점을 찾지 못했지만, 같은 페이지 안에서 {stage1['reason']} "
                          "어느 쪽이 맞는지 원문을 직접 확인하세요.")
        elif stage1:
            s1 = _stage1_verdict(stage1, body)
            verdict, reason = s1
    else:
        summ = _merge_summary(top, body)
        if has_orig:
            f2 = compare_presence(summ, orig, _NAME["summary"], _NAME["original"])
            verdict, reason = _finding_to_verdict(f2), f2.reason
            stage2 = {"verdict": verdict, "reason": reason, "kind": f2.kind}

    return {
        "key": item, "name": ITEM_NAMES[item], "verdict": verdict, "severity": SEVERITY[verdict],
        "reason": reason, "stage1": stage1, "stage2": stage2,
        "values": {r: v.to_dict() for r, v in vals.items()},
    }


def judge_all(values: dict[str, dict[str, SourceValue]]) -> list[dict]:
    return [judge_item(k, values[k]) for k, _ in ITEMS]
