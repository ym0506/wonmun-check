"""설정값. 모두 환경변수로 바꿀 수 있다.

API 키는 코드나 저장소에 두지 않는다. 실행할 때 키 파일(기본 ~/.config/kic-hanbaguni/.env)의
ANTHROPIC_API_KEY 한 줄만 읽고, 값은 어디에도 출력하지 않는다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass
class Settings:
    model: str = field(default_factory=lambda: os.environ.get("WONMUN_MODEL", "claude-haiku-5-5"))
    effort: str = field(default_factory=lambda: os.environ.get("WONMUN_EFFORT", "low"))
    # "adaptive"(기본) 또는 "disabled". Haiku 5.5는 effort low/medium/high에서만 disabled를 받는다.
    thinking: str = field(default_factory=lambda: os.environ.get("WONMUN_THINKING", "adaptive"))
    max_tokens: int = field(default_factory=lambda: _int_env("WONMUN_MAX_TOKENS", 16000))
    key_file: Path = field(
        default_factory=lambda: Path(
            os.environ.get("WONMUN_KEY_FILE", str(Path.home() / ".config/kic-hanbaguni/.env"))
        )
    )
    # 원문이 이보다 길면 앞부분만 AI에 보내고 화면에 그 사실을 적는다.
    max_source_chars: int = field(default_factory=lambda: _int_env("WONMUN_MAX_SOURCE_CHARS", 60000))
    # 직접 확인 모드 호출 제한(배포 대비). 0이면 막는다.
    daily_limit: int = field(default_factory=lambda: _int_env("WONMUN_DAILY_LIMIT", 30))
    ip_daily_limit: int = field(default_factory=lambda: _int_env("WONMUN_IP_DAILY_LIMIT", 5))
    # API 호출 기록(토큰 수만, 키·본문 없음)
    # Vercel 함수는 /tmp만 쓸 수 있어 그곳에 둔다(인스턴스가 바뀌면 지워진다).
    ledger_path: Path = field(
        default_factory=lambda: Path(os.environ.get(
            "WONMUN_LEDGER",
            "/tmp/wonmun_api_ledger.jsonl" if os.environ.get("VERCEL") else str(ROOT / "data/api_ledger.jsonl"),
        ))
    )
    # 이 기록 파일 기준 누적 호출 상한. 넘으면 호출하지 않는다.
    call_budget: int = field(default_factory=lambda: _int_env("WONMUN_CALL_BUDGET", 1000))
    fetch_timeout: float = 20.0
    fetch_max_bytes: int = 15 * 1024 * 1024


def load_api_key(settings: Settings | None = None) -> str | None:
    """키 파일에서 ANTHROPIC_API_KEY를 읽는다. 없으면 환경변수, 그것도 없으면 None."""
    settings = settings or Settings()
    path = settings.key_file
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("export "):
                line = line[len("export "):]
            if line.startswith("ANTHROPIC_API_KEY="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if value:
                    return value
    except OSError:
        pass
    value = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    return value or None
