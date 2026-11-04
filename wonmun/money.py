"""금액 읽기와 현금/현물 구분(정규식·낱말 목록)."""

from __future__ import annotations

import re

_AMOUNT = re.compile(
    r"(?P<num>\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(?P<unit>억|천만|백만|만|천)?\s*(?P<won>원)"
)
_UNIT = {"억": 100_000_000, "천만": 10_000_000, "백만": 1_000_000, "만": 10_000, "천": 1_000, None: 1}

IN_KIND = re.compile(r"상품권|기프트\s*카드|기프티콘|현물|상품(?!금)|쿠폰|크레딧|포인트|기념품|부상품|굿즈|모바일\s*상품")
CASH = re.compile(r"상금|현금|장학금|원고료|활동비")


def parse_amounts(text: str) -> list[int]:
    out = []
    for m in _AMOUNT.finditer(text or ""):
        num = float(m.group("num").replace(",", ""))
        val = int(round(num * _UNIT[m.group("unit")]))
        if val >= 1000:  # 1천 원 미만은 금액 칸 오인일 가능성이 커서 뺀다
            out.append(val)
    # "1억 2천만 원" 같은 붙은 표현
    for m in re.finditer(r"(\d+)\s*억\s*(\d{1,4})\s*(천)?만\s*원", text or ""):
        val = int(m.group(1)) * 100_000_000 + int(m.group(2)) * (10_000_000 if m.group(3) else 10_000)
        out.append(val)
    return out


def prize_kind(text: str) -> str:
    """인용 문장의 낱말로 현금/현물을 가른다. AI 판단을 쓰지 않는다."""
    kind_hit = bool(IN_KIND.search(text or ""))
    cash_hit = bool(CASH.search(text or ""))
    if kind_hit and cash_hit:
        return "현금+현물"
    if kind_hit:
        return "현물·상품권"
    if cash_hit:
        return "현금"
    return "알 수 없음"


def won_str(v: int | None) -> str:
    if not v:
        return ""
    if v % 10_000 == 0:
        return f"{v // 10_000:,}만 원"
    return f"{v:,}원"
