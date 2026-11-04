"""사용자가 넣은 주소 한 개만 한 번 읽는다. 저장하지 않는다(시험 스크립트는 따로 저장).

배포 대비 안전장치
- http/https만, 15MB까지
- 사설·내부 주소(127.0.0.1, 10.x, 192.168.x 등)로 가는 요청은 막는다(SSRF 방지)
- 봇 확인 화면·로그인 화면을 우회하지 않는다. 막히면 그대로 실패로 알린다.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import httpx

from .config import Settings

USER_AGENT = "Mozilla/5.0 (compatible; wonmun-check/0.1; local PoC)"


class FetchError(Exception):
    """사용자에게 그대로 보여 줄 한국어 메시지를 담는다."""


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int
    content_type: str
    content: bytes
    fetched_at: str


def _check_host(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise FetchError("http 또는 https 주소만 읽을 수 있습니다.")
    host = parsed.hostname
    if not host:
        raise FetchError("주소에서 사이트 이름을 찾지 못했습니다.")
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as e:
        raise FetchError(f"사이트 이름을 찾지 못했습니다: {host}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise FetchError("내부망 주소는 읽지 않습니다.")


def normalize_url(url: str) -> str:
    """사이트 구조 때문에 본문이 다른 주소에 있는 경우만 바꾼다(우회가 아니라 본문 주소로 이동)."""
    url = url.strip()
    m = re.match(r"https?://(?:m\.)?blog\.naver\.com/([A-Za-z0-9_\-]+)/(\d+)", url)
    if m:  # 네이버 블로그는 바깥 틀(frame) 안에 본문 주소가 따로 있다.
        return f"https://blog.naver.com/PostView.naver?blogId={m.group(1)}&logNo={m.group(2)}"
    return url


def fetch_url(url: str, settings: Settings | None = None) -> FetchResult:
    settings = settings or Settings()
    url = normalize_url(url)
    current = url
    with httpx.Client(timeout=settings.fetch_timeout, follow_redirects=False,
                      headers={"User-Agent": USER_AGENT,
                               "Accept-Language": "ko-KR,ko;q=0.9"}) as client:
        for _ in range(6):  # 리다이렉트도 한 단계씩 주소를 검사한다
            _check_host(current)
            try:
                with client.stream("GET", current) as resp:
                    if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get("location"):
                        current = urljoin(current, resp.headers["location"])
                        continue
                    chunks = []
                    size = 0
                    for chunk in resp.iter_bytes():
                        size += len(chunk)
                        if size > settings.fetch_max_bytes:
                            raise FetchError("파일이 너무 큽니다(15MB 초과).")
                        chunks.append(chunk)
                    body = b"".join(chunks)
                    if resp.status_code >= 400:
                        raise FetchError(
                            f"사이트가 요청을 거절했습니다(HTTP {resp.status_code}). 원문 파일을 내려받아 올리거나 글을 붙여 넣어 주세요."
                        )
                    return FetchResult(
                        url=url,
                        final_url=str(resp.url),
                        status=resp.status_code,
                        content_type=resp.headers.get("content-type", ""),
                        content=body,
                        fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    )
            except httpx.HTTPError as e:
                raise FetchError(f"주소를 읽지 못했습니다: {type(e).__name__}") from e
    raise FetchError("리다이렉트가 너무 많습니다.")
