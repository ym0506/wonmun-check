"""Vercel 진입점. Vercel은 루트의 index.py에서 FastAPI 인스턴스 app을 찾는다.

로컬 실행은 그대로: .venv/bin/uvicorn web.app:app --port 8000
"""

from web.app import app  # noqa: F401
