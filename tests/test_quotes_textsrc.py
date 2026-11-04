import io
import zipfile

from wonmun.money import parse_amounts, prize_kind
from wonmun.quotes import QuoteIndex, check_quotes
from wonmun.textsrc import doc_from_bytes, html_to_lines, text_doc


def make_index(text):
    return QuoteIndex(text_doc(text, "original", "t"))


def test_quote_exact_and_whitespace_tolerant():
    ix = make_index("□ 신청서 접수기간 :  ~ 2026. 11. 06.(금)   11:00\n다음 줄")
    hit = ix.locate("신청서 접수기간 : ~ 2026. 11. 06.(금) 11:00")
    assert hit is not None and hit.sid == "원문-1"


def test_quote_one_char_changed_is_rejected():
    ix = make_index("접수기간 : ~ 2026. 11. 06.(금) 11:00")
    assert ix.locate("접수기간 : ~ 2026. 11. 6.(금) 11:00") is None


def test_quote_with_ellipsis_rejected():
    ix = make_index("가나다 라마바 사아자")
    assert ix.locate("가나다 … 사아자") is None
    assert ix.locate("가나다 ... 사아자") is None


def test_quote_id_prefix_is_stripped():
    ix = make_index("첫 줄\n둘째 줄 내용")
    hit = ix.locate("[원문-2] 둘째 줄 내용")
    assert hit is not None and hit.sid == "원문-2"


def test_quote_across_lines_maps_to_both_segments():
    ix = make_index("접수기간:\n2026. 11. 7.")
    hit = ix.locate("접수기간: 2026. 11. 7.")
    assert hit is not None and hit.sids == ["원문-1", "원문-2"]


def test_check_quotes_splits_hits_and_rejects():
    ix = make_index("총 상금 1,300만원")
    hits, rejected = check_quotes(["총 상금 1,300만원", "총 상금 1300만원"], ix)
    assert len(hits) == 1 and rejected == ["총 상금 1300만원"]


def test_html_lines_keep_inline_spans_together():
    html = "<div><p><span>접수기간 :</span><span> 11. 25.(수)</span> <b>15:00</b></p><p>다음</p></div>"
    assert html_to_lines(html) == ["접수기간 : 11. 25.(수) 15:00", "다음"]


def test_html_drops_scripts_and_nav():
    html = "<nav>메뉴</nav><div id='gnb'>전체메뉴</div><script>var a=1</script><article><p>본문</p></article>"
    assert html_to_lines(html) == ["본문"]


def test_hwpx_paragraphs():
    sec = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
        'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
        '<hp:p><hp:run><hp:t>□ 접수기간: </hp:t></hp:run><hp:run><hp:t>2026. 11. 7.</hp:t></hp:run></hp:p>'
        '<hp:p><hp:run><hp:tbl><hp:tr><hp:tc><hp:subList><hp:p><hp:run><hp:t>표 안 글</hp:t></hp:run></hp:p>'
        '</hp:subList></hp:tc></hp:tr></hp:tbl></hp:run></hp:p>'
        '</hs:sec>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "application/hwp+zip")
        z.writestr("Contents/section0.xml", sec)
    doc = doc_from_bytes(buf.getvalue(), "original", "a.hwpx", filename="a.hwpx")
    assert [s.text for s in doc.segments] == ["□ 접수기간: 2026. 11. 7.", "표 안 글"]


def test_money():
    assert parse_amounts("총 상금 1,300만원 / 대상 500만 원") == [13_000_000, 5_000_000]
    assert parse_amounts("총 1천만원") == [10_000_000]
    assert prize_kind("240만원 규모의 시상품(모바일상품권 및 커피쿠폰 등)") == "현물·상품권"
    assert prize_kind("총 상금 1,300만원") == "현금"
