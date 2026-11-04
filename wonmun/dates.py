"""날짜·시각 읽기(정규식). AI가 고른 마감 값을 코드가 원래 글자에서 다시 읽어 확인하는 데 쓴다.

읽는 형식 예
- 2026. 11. 06.(금) 11:00      -> 2026-11-06 11:00
- 11월 30일(월) 17:00          -> (연도 추정) 11-30 17:00
- '26.11.5.(목)∼11.19.(목)     -> 2026-11-05 ~ 2026-11-19
- 11. 7. 24:00                 -> 11-07 24:00 (그날 끝)
- ~11.25                       -> 11-25 (시작 없는 기간)
- 2026.08.11 ~ 2026.11.25      -> 기간
- 2026년 8월 12일 ~ 2026년 11월 6일, 11월 20일(금) 오후 6시, 자정까지, 오후 5:00
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime

END_OF_DAY = {"23:59", "24:00"}

_WD = r"(?:\s*[\(（]\s*[월화수목금토일](?:요일)?\s*[\)）])"
_FULL_DOT = (
    r"(?P<y>(?:19|20)\d{2}|['’‘`]\d{2})\s*[.\-/]\s*(?P<m>\d{1,2})\s*[.\-/]\s*(?P<d>\d{1,2})"
    r"(?!\d)\s*\.?"
)
_FULL_KO = r"(?P<y2>(?:19|20)\d{2})\s*년\s*(?P<m2>\d{1,2})\s*월\s*(?P<d2>\d{1,2})\s*일"
_MD_KO = r"(?P<m3>\d{1,2})\s*월\s*(?P<d3>\d{1,2})\s*일"
_MD_DOT = r"(?<![\d.,:/\-])(?P<m4>\d{1,2})\s*[./]\s*(?P<d4>\d{1,2})(?![\d,])(?P<dot4>\s*\.)?"

_ATOM = re.compile(f"(?:{_FULL_KO}|{_FULL_DOT}|{_MD_KO}|{_MD_DOT})(?P<wd>{_WD})?")

_TIME = re.compile(
    r"\s*[\(（]?\s*(?:(?P<ampm>오전|오후|낮|밤|저녁|새벽|AM|PM|am|pm)\s*)?"
    r"(?:(?P<h>\d{1,2})\s*(?::\s*(?P<mi>\d{2})(?::\d{2})?|시(?:\s*(?P<mi2>\d{1,2})\s*분)?)"
    r"|(?P<mid>자정|밤\s*12\s*시)|(?P<noon>정오))"
)
_STANDALONE_TIME = re.compile(
    r"(?:(?P<ampm>오전|오후|낮|밤|저녁|새벽)\s*)?(?<![\d:])(?P<h>\d{1,2})\s*(?::\s*(?P<mi>\d{2})(?::\d{2})?|시(?:\s*(?P<mi2>\d{1,2})\s*분)?)(?![\d])"
    r"|(?P<mid>자정)|(?P<noon>정오)"
)
_RANGE_SEP = re.compile(r"^\s*(?:부터|에서)?\s*[~∼～〜\-–—]\s*$|^\s*부터\s*$")
_OPEN_START = re.compile(r"[~∼～〜]\s*$")
_UNIT_AFTER = re.compile(
    r"^\s*(?:%|퍼센트|배|점|만|천|억|원|초|분|시간|MB|GB|KB|mm|cm|kg|km|m\b|명|개|회|차|인|편|매|쪽|페이지|p\b|px|위|등|년|세)"
)


@dataclass(frozen=True)
class DatePoint:
    date: date
    time: str | None  # "HH:MM", 자정은 "24:00"
    year_given: bool
    raw: str
    start: int
    end: int

    @property
    def end_of_day(self) -> bool:
        return self.time in END_OF_DAY

    def iso(self) -> str:
        return self.date.isoformat() + (f" {self.time}" if self.time else "")


@dataclass(frozen=True)
class DateMention:
    start: DatePoint | None
    end: DatePoint
    is_range: bool
    raw: str


def _norm_time(ampm: str | None, h: int, mi: int) -> str | None:
    if ampm in ("오후", "저녁", "밤", "PM", "pm") and h < 12:
        h += 12
    if ampm in ("오전", "새벽", "AM", "am") and h == 12:
        h = 0
    if h > 24 or mi > 59 or (h == 24 and mi != 0):
        return None
    return f"{h:02d}:{mi:02d}"


def _time_after(text: str, pos: int) -> tuple[str | None, int]:
    """날짜 바로 뒤(괄호 하나까지 허용)에 붙은 시각을 읽는다."""
    m = _TIME.match(text, pos)
    if not m:
        return None, pos
    if m.group("mid"):
        return "24:00", m.end()
    if m.group("noon"):
        return "12:00", m.end()
    h = int(m.group("h"))
    mi = int(m.group("mi") or m.group("mi2") or 0)
    # '11. 6. 3시간' 같은 것은 시각이 아니다
    if re.match(r"\s*간", text[m.end():m.end() + 2]):
        return None, pos
    t = _norm_time(m.group("ampm"), h, mi)
    return (t, m.end()) if t else (None, pos)


def guess_ref_year(text: str, default: int | None = None) -> int:
    years = [int(y) for y in re.findall(r"(?<!\d)(20[2-3]\d)\s*[.\-/년]\s*\d{1,2}", text)]
    if years:
        return Counter(years).most_common(1)[0][0]
    return default or datetime.now().year


def _atoms(text: str, ref_year: int):
    out = []
    last_year = None
    for m in _ATOM.finditer(text):
        gd = m.groupdict()
        year_given = True
        if gd.get("y2"):
            y, mo, d = int(gd["y2"]), int(gd["m2"]), int(gd["d2"])
        elif gd.get("y"):
            ys = gd["y"]
            y = int(ys) if ys[0].isdigit() else 2000 + int(ys[1:])
            mo, d = int(gd["m"]), int(gd["d"])
        elif gd.get("m3"):
            y, mo, d = None, int(gd["m3"]), int(gd["d3"])
            year_given = False
        else:
            y, mo, d = None, int(gd["m4"]), int(gd["d4"])
            year_given = False
            # 점 찍은 월.일은 오인이 많아서 조건을 붙인다
            after = text[m.end():m.end() + 6]
            before = text[max(0, m.start() - 3):m.start()]
            ok = bool(gd.get("dot4") or gd.get("wd") or _OPEN_START.search(before)
                      or re.match(r"^\s*[~∼～〜\-–—]", text[m.end():m.end() + 3])
                      or re.match(r"^\s*\d{1,2}\s*:\s*\d{2}", after))
            if not ok or _UNIT_AFTER.match(text[m.end():m.end() + 6]):
                continue
        if not (1 <= mo <= 12 and 1 <= d <= 31):
            continue
        if y is None:
            y = last_year or ref_year
        else:
            last_year = y
        try:
            dt = date(y, mo, d)
        except ValueError:
            continue
        t, tend = _time_after(text, m.end())
        end = tend if t else m.end()
        out.append(DatePoint(date=dt, time=t, year_given=year_given,
                             raw=text[m.start():end].strip(), start=m.start(), end=end))
    return out


def parse_dates(text: str, ref_year: int | None = None) -> list[DateMention]:
    """글 안의 날짜 표현을 모두 읽는다. 기간(~)은 시작·끝을 묶는다."""
    if not text:
        return []
    ref_year = ref_year or guess_ref_year(text)
    atoms = _atoms(text, ref_year)
    mentions: list[DateMention] = []
    i = 0
    while i < len(atoms):
        a = atoms[i]
        if i + 1 < len(atoms) and _RANGE_SEP.match(text[a.end:atoms[i + 1].start]):
            b = atoms[i + 1]
            bd = b.date
            if not b.year_given:
                y = a.date.year + (1 if bd.month < a.date.month else 0)
                try:
                    bd = date(y, bd.month, bd.day)
                except ValueError:
                    pass
                b = DatePoint(bd, b.time, False, b.raw, b.start, b.end)
            mentions.append(DateMention(start=a, end=b, is_range=True, raw=text[a.start:b.end]))
            i += 2
            continue
        before = text[max(0, a.start - 3):a.start]
        is_open = bool(_OPEN_START.search(before))
        raw_start = a.start - (len(before) - len(before.rstrip())) - 1 if is_open else a.start
        mentions.append(DateMention(start=None, end=a, is_range=is_open,
                                    raw=text[max(0, raw_start):a.end]))
        i += 1
    return mentions


def all_points(text: str, ref_year: int | None = None) -> list[DatePoint]:
    pts = []
    for m in parse_dates(text, ref_year):
        if m.start:
            pts.append(m.start)
        pts.append(m.end)
    return pts


def standalone_times(text: str) -> list[str]:
    """날짜와 떨어져 적힌 시각('제출 마감 당일 23:59')도 모은다."""
    out = []
    for m in _STANDALONE_TIME.finditer(text or ""):
        if m.group("mid"):
            out.append("24:00")
            continue
        if m.group("noon"):
            out.append("12:00")
            continue
        h = int(m.group("h"))
        mi = int(m.group("mi") or m.group("mi2") or 0)
        t = _norm_time(m.group("ampm"), h, mi)
        if t:
            out.append(t)
    return out


def parse_iso(s: str) -> date | None:
    try:
        return date.fromisoformat((s or "").strip()[:10])
    except ValueError:
        return None


def norm_time_str(s: str) -> str | None:
    s = (s or "").strip()
    m = re.match(r"^(\d{1,2}):(\d{2})", s)
    if not m:
        return None
    return _norm_time(None, int(m.group(1)), int(m.group(2)))


@dataclass
class DeadlineRead:
    date: date | None
    time: str | None
    raw: str
    verified: bool
    reason: str


def read_deadline(quotes: list[str], model_date: str, model_time: str,
                  ref_year: int | None = None) -> DeadlineRead:
    """인용 문장에서 마감 날짜·시각을 코드로 다시 읽는다.

    - AI가 고른 날짜가 인용 안 날짜 중 하나와 같아야 채택한다(연도가 안 적힌 날짜는 월·일만 비교).
    - 시각은 그 날짜 바로 뒤에 붙은 시각을 코드가 읽은 값으로 쓴다. 붙은 시각이 없고 AI 시각이
      인용 안에 따로 적혀 있으면 그것을 쓴다.
    - AI 날짜가 비어 있으면 인용 안 날짜 중 가장 늦은 끝 날짜를 쓴다.
    """
    joined = " / ".join(q for q in quotes if q)
    if not joined:
        return DeadlineRead(None, None, "", False, "인용 문장이 없음")
    if ref_year is None:
        ref_year = guess_ref_year(joined)
    mentions = []
    for q in quotes:
        mentions += parse_dates(q, ref_year)
    points = []
    for m in mentions:
        if m.start:
            points.append((m.start, False))
        points.append((m.end, True))
    if not points:
        return DeadlineRead(None, None, "", False, "인용 문장에서 날짜를 읽지 못함")
    md = parse_iso(model_date)
    chosen = None
    if md:
        cands = [(p, is_end) for p, is_end in points
                 if (p.date == md) or (not p.year_given and (p.date.month, p.date.day) == (md.month, md.day))]
        if not cands:
            return DeadlineRead(None, None, "", False,
                                f"AI가 고른 날짜 {md.isoformat()}가 인용 문장에 없음")
        cands.sort(key=lambda x: (not x[1], x[0].time is None))  # 끝 날짜, 시각 있는 것 우선
        chosen = cands[0][0]
        d = md if chosen.year_given is False and chosen.date != md else chosen.date
    else:
        ends = [p for p, is_end in points if is_end]
        chosen = max(ends, key=lambda p: (p.date, p.time or ""))
        d = chosen.date
    t = chosen.time
    if t is None:
        mt = norm_time_str(model_time)
        if mt and mt in standalone_times(joined):
            t = mt
    return DeadlineRead(d, t, chosen.raw, True, "")
