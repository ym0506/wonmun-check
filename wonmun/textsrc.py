"""글자 꺼내기. HTML·PDF·HWPX·TXT를 문단(줄) 단위로 나누고 위치 번호를 붙인다.

위치 번호 형식
- 요약 위쪽 칸: 칸-1, 칸-2 ...
- 요약 본문:   본문-1 ...
- 원문:        원문-12 (HTML·TXT·HWPX), 원문-p3-4 (PDF 3쪽 4번째 문단)
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field, asdict

from bs4 import BeautifulSoup, NavigableString, Tag

ROLE_PREFIX = {"top": "칸", "body": "본문", "original": "원문"}
ROLE_LABEL = {"top": "요약 위쪽 칸", "body": "요약 본문", "original": "원문"}


@dataclass
class Segment:
    sid: str
    text: str
    page: int | None = None


@dataclass
class SourceDoc:
    role: str  # top | body | original
    label: str
    origin: str  # URL 또는 파일 이름
    kind: str  # linkareer-fields, html, pdf, hwpx, txt, paste ...
    segments: list[Segment] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    truncated: bool = False

    def full_text(self) -> str:
        return "\n".join(s.text for s in self.segments)

    def char_count(self) -> int:
        return sum(len(s.text) for s in self.segments)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# ---------------------------------------------------------------- 공통

_WS = re.compile(r"[ \t\r\f\v  - 　]+")
_ZW = re.compile(r"[​-‍﻿]")
# 긴 문단은 문장 끝에서 나눈다(날짜 "11. 6." 사이는 나누지 않도록 한글 종결형 뒤에서만).
_SENT_END = re.compile(r"(?<=(?:다|요|음|함|임|됨|람|오)\.)\s+")


def clean_line(s: str) -> str:
    s = _ZW.sub("", s)
    s = _WS.sub(" ", s)
    return s.strip()


def split_long(line: str, limit: int = 300) -> list[str]:
    if len(line) <= limit:
        return [line]
    parts = [p.strip() for p in _SENT_END.split(line) if p.strip()]
    return parts or [line]


def lines_to_segments(lines: list[str], role: str, page: int | None = None,
                      start: int = 1) -> list[Segment]:
    prefix = ROLE_PREFIX[role]
    segs: list[Segment] = []
    n = start
    for raw in lines:
        line = clean_line(raw)
        if not line:
            continue
        for part in split_long(line):
            sid = f"{prefix}-p{page}-{n}" if page is not None else f"{prefix}-{n}"
            segs.append(Segment(sid=sid, text=part, page=page))
            n += 1
    return segs


def limit_segments(doc: SourceDoc, max_chars: int) -> SourceDoc:
    """너무 긴 출처는 앞부분만 남기고 그 사실을 기록한다(조용히 자르지 않는다)."""
    total = 0
    kept: list[Segment] = []
    for s in doc.segments:
        if total + len(s.text) > max_chars:
            doc.truncated = True
            break
        kept.append(s)
        total += len(s.text)
    if doc.truncated:
        doc.notes.append(
            f"글이 길어 앞부분 {total:,}자(전체 {doc.char_count():,}자 중)만 AI에 보냈습니다. 뒷부분은 대조하지 않았습니다."
        )
        doc.segments = kept
    return doc


# ---------------------------------------------------------------- HTML

_BLOCK_TAGS = {
    "p", "div", "li", "ul", "ol", "tr", "table", "tbody", "thead", "h1", "h2", "h3", "h4",
    "h5", "h6", "section", "article", "dd", "dt", "dl", "blockquote", "pre", "main",
    "header", "footer", "figure", "figcaption", "caption", "form", "fieldset", "address",
}
_CELL_TAGS = {"td", "th"}
_DROP_TAGS = ["script", "style", "noscript", "svg", "template", "iframe", "object", "button",
              "select", "option", "input", "textarea", "head", "nav"]
# 사이트 메뉴·머리말·꼬리말로 흔히 쓰이는 id/class 앞부분
_NOISE_ID = re.compile(
    r"^(gnb|lnb|snb|tnb|skip|skipnav|quick|quickmenu|sitemap|site-map|breadcrumb|location|"
    r"footer|foot|header|head_wrap|top_menu|topmenu|allmenu|all_menu|mobile_menu|m_menu|"
    r"family_site|familysite|util|banner)([_\-]|$)",
    re.I,
)


def _is_noise(tag: Tag) -> bool:
    if tag.name in ("header", "footer", "aside"):
        return True
    ident = " ".join([tag.get("id") or ""] + list(tag.get("class") or []))
    return any(_NOISE_ID.match(tok) for tok in ident.split())


def html_to_lines(html: str, drop_site_chrome: bool = True) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    for name in _DROP_TAGS:
        for t in soup.find_all(name):
            t.decompose()
    if drop_site_chrome:
        for t in list(soup.find_all(True)):
            if getattr(t, "decomposed", False) or t.parent is None:  # 이미 지워진 조상 아래
                continue
            try:
                if _is_noise(t):
                    t.decompose()
            except Exception:  # noqa: BLE001 - 깨진 태그는 그대로 둔다
                continue
    for br in soup.find_all("br"):
        br.replace_with(NavigableString("\n"))
    for t in soup.find_all(list(_BLOCK_TAGS)):
        t.insert_before(NavigableString("\n"))
        t.insert_after(NavigableString("\n"))
    for t in soup.find_all(list(_CELL_TAGS)):
        t.insert_after(NavigableString(" | "))
    for img in soup.find_all("img"):
        img.decompose()
    text = soup.get_text("")
    lines = []
    for line in text.split("\n"):
        line = clean_line(line)
        line = re.sub(r"(\s*\|\s*)+$", "", line)  # 줄 끝 칸 구분자
        line = re.sub(r"^(\s*\|\s*)+", "", line)
        if line:
            lines.append(line)
    return lines


def html_doc(html: str, role: str, origin: str, kind: str = "html",
             drop_site_chrome: bool = True) -> SourceDoc:
    lines = html_to_lines(html, drop_site_chrome=drop_site_chrome)
    doc = SourceDoc(role=role, label=ROLE_LABEL[role], origin=origin, kind=kind,
                    segments=lines_to_segments(lines, role))
    if doc.char_count() < 200:
        doc.notes.append(
            "서버에서 받은 HTML에 글자가 거의 없습니다. 본문이 자바스크립트나 이미지로 그려지는 페이지일 수 있습니다."
        )
    return doc


def decode_bytes(data: bytes, content_type: str = "") -> str:
    m = re.search(r"charset=([\w\-]+)", content_type or "", re.I)
    candidates = []
    if m:
        candidates.append(m.group(1))
    head = data[:3000].decode("ascii", "ignore")
    m2 = re.search(r"<meta[^>]+charset=[\"']?([\w\-]+)", head, re.I)
    if m2:
        candidates.append(m2.group(1))
    candidates += ["utf-8", "cp949"]
    for enc in candidates:
        try:
            return data.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", "replace")


# ---------------------------------------------------------------- PDF

def pdf_doc(data: bytes, role: str, origin: str) -> SourceDoc:
    import pymupdf as fitz  # PyMuPDF

    doc = SourceDoc(role=role, label=ROLE_LABEL[role], origin=origin, kind="pdf")
    with fitz.open(stream=data, filetype="pdf") as pdf:
        for pno, page in enumerate(pdf, start=1):
            blocks = page.get_text("blocks", sort=True)
            lines = []
            for b in blocks:
                if len(b) >= 7 and b[6] != 0:  # 이미지 블록
                    continue
                txt = " ".join(x.strip() for x in str(b[4]).splitlines() if x.strip())
                if txt:
                    lines.append(txt)
            doc.segments += lines_to_segments(lines, role, page=pno)
    if doc.char_count() < 100:
        doc.notes.append("PDF에서 글자를 거의 못 꺼냈습니다. 스캔본(이미지) PDF는 이 PoC가 읽지 못합니다.")
    return doc


# ---------------------------------------------------------------- HWPX

_HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"


def hwpx_lines(data: bytes) -> list[str]:
    from lxml import etree

    lines: list[str] = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = [n for n in z.namelist() if re.match(r"Contents/section\d+\.xml$", n)]
        names.sort(key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[1]).group(1)))
        for name in names:
            root = etree.fromstring(z.read(name))
            # 글자(hp:t)를 가장 가까운 문단(hp:p)별로 모은다. 표 안 문단이 바깥 문단에 섞이지 않는다.
            order: list = []
            texts: dict = {}
            for t in root.iter(f"{{{_HP_NS}}}t"):
                p = t.getparent()
                while p is not None and p.tag != f"{{{_HP_NS}}}p":
                    p = p.getparent()
                if p is None:
                    continue
                if p not in texts:
                    texts[p] = []
                    order.append(p)
                texts[p].append("".join(t.itertext()))
            for p in order:
                line = "".join(texts[p]).strip()
                if line:
                    lines.append(line)
    return lines


def hwpx_doc(data: bytes, role: str, origin: str) -> SourceDoc:
    doc = SourceDoc(role=role, label=ROLE_LABEL[role], origin=origin, kind="hwpx",
                    segments=lines_to_segments(hwpx_lines(data), role))
    return doc


# ---------------------------------------------------------------- TXT / 붙여 넣기

def text_doc(text: str, role: str, origin: str, kind: str = "txt") -> SourceDoc:
    return SourceDoc(role=role, label=ROLE_LABEL[role], origin=origin, kind=kind,
                     segments=lines_to_segments(text.splitlines(), role))


def sniff_kind(data: bytes, filename: str = "", content_type: str = "") -> str:
    name = filename.lower()
    ct = (content_type or "").lower()
    if data[:5] == b"%PDF-" or name.endswith(".pdf") or "pdf" in ct:
        return "pdf"
    if data[:2] == b"PK" and (name.endswith(".hwpx") or b"Contents/section" in data[:20000]
                              or "hwp" in ct):
        return "hwpx"
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "hwp-binary"
    if name.endswith(".txt") or ct.startswith("text/plain"):
        return "txt"
    return "html"


def doc_from_bytes(data: bytes, role: str, origin: str, filename: str = "",
                   content_type: str = "") -> SourceDoc:
    kind = sniff_kind(data, filename, content_type)
    if kind == "pdf":
        return pdf_doc(data, role, origin)
    if kind == "hwpx":
        return hwpx_doc(data, role, origin)
    if kind == "hwp-binary":
        raise ValueError("구형 HWP(바이너리) 파일은 읽지 않습니다. 한글에서 HWPX나 PDF로 저장해 넣어 주세요.")
    if kind == "txt":
        return text_doc(decode_bytes(data, content_type), role, origin)
    return html_doc(decode_bytes(data, content_type), role, origin)
