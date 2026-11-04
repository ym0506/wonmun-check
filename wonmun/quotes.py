"""인용 검사: AI가 돌려준 근거 문장이 출처에 글자 그대로 있는지 코드가 확인한다.

허용하는 차이는 공백뿐이다(연속 공백·줄바꿈을 한 칸으로). 글자 하나라도 다르면 버린다.
AI가 문장 앞에 위치 번호("[원문-12]")를 붙여 온 경우만 그 번호를 떼고 본다(내용이 아니라 표기).
말줄임표(…, ...)로 중간을 줄인 인용은 '그대로 복사'가 아니므로 버린다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .textsrc import SourceDoc

_ZW = re.compile(r"[​-‍﻿]")
_ID_PREFIX = re.compile(r"^\s*[\[［(]?\s*(?:칸|본문|원문)-(?:p\d+-)?\d+\s*[\]］)]?\s*[:：]?\s*")


def norm_ws(s: str) -> str:
    s = _ZW.sub("", s or "")
    s = s.replace(" ", " ").replace("　", " ")
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class QuoteHit:
    text: str  # 정리된 인용
    sid: str  # 시작 문단 위치 번호
    sids: list[str]  # 인용이 걸친 문단들
    start: int  # 시작 문단 안 글자 위치
    end: int  # 끝 문단 안 글자 위치(끝 문단 기준)


def strip_id(q: str) -> str:
    return _ID_PREFIX.sub("", q or "")


class QuoteIndex:
    """출처 하나의 문단을 공백 정리해 이어 붙이고, 위치를 문단으로 되돌릴 수 있게 한다."""

    def __init__(self, doc: SourceDoc):
        self.doc = doc
        parts = []
        self.bounds = []  # (sid, start, end) in joined
        pos = 0
        for seg in doc.segments:
            t = norm_ws(seg.text)
            parts.append(t)
            self.bounds.append((seg.sid, pos, pos + len(t)))
            pos += len(t) + 1  # 문단 사이 공백 한 칸
        self.joined = " ".join(parts)

    def locate(self, quote: str) -> QuoteHit | None:
        q = norm_ws(strip_id(quote))
        if len(q) < 2 or "…" in q or "..." in q:
            return None
        idx = self.joined.find(q)
        if idx < 0:
            return None
        end = idx + len(q)
        sids = [sid for sid, s, e in self.bounds if s < end and e > idx]
        first = next(((sid, s) for sid, s, e in self.bounds if e > idx), None)
        last = next(((sid, s) for sid, s, e in reversed(self.bounds) if s < end), None)
        if not first or not last:
            return None
        return QuoteHit(text=q, sid=first[0], sids=sids, start=max(0, idx - first[1]),
                        end=end - last[1])


def check_quotes(quotes: list[str], index: QuoteIndex) -> tuple[list[QuoteHit], list[str]]:
    hits, rejected = [], []
    seen = set()
    for q in quotes or []:
        hit = index.locate(q)
        if hit is None:
            rejected.append(q)
        elif hit.text not in seen:
            seen.add(hit.text)
            hits.append(hit)
    return hits, rejected
