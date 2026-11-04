"""원문 확인: 공고 요약과 원문을 7항목으로 대조하는 PoC 엔진."""

ITEMS = [
    ("deadline", "마감 일시"),
    ("eligibility", "참가 자격"),
    ("team", "참가 형태·인원"),
    ("prize", "시상"),
    ("submission", "제출물·분량"),
    ("penalty", "실격·감점"),
    ("ai_copyright", "생성형 AI·저작권"),
]
ITEM_NAMES = dict(ITEMS)
ITEM_KEYS = [k for k, _ in ITEMS]
