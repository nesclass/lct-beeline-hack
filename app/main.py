"""Приложение диспетчера.

    python3 -m uvicorn app.main:app --port 8001 --reload

Если собран фронт (`npm --prefix web run build`), он отдаётся отсюда же: файлы из web/dist,
а любой путь приложения вне /api — index.html, дальше разбирается роутер в браузере.

Ассистент ходит в языковую модель через прокси LiteLLM (`litellm --config litellm_config.yaml
--port 4000`). Ключи — в .env в корне репозитория (не в git): ключ провайдера модели для прокси,
LITELLM_MASTER_KEY — им приложение авторизуется у прокси. Без ключа — шаблонные ответы.
"""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from .routers import analytics, assistant, catalog, events, geo, planning, scenarios, sessions, uploads, variants, whatif

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "web" / "dist"
load_dotenv(ROOT / ".env", override=False)      # переменные окружения процесса важнее файла


def create_app(dist: Path | None = None) -> FastAPI:
    api = FastAPI(title="Планировщик маршрутов инженеров", version="1.0")
    for r in (scenarios, uploads, sessions, planning, catalog, geo, events, whatif, analytics, variants, assistant):
        api.include_router(r.router)
    dist = (DIST if dist is None else dist).resolve()
    if (dist / "index.html").exists():
        index = dist / "index.html"

        @api.get("/{path:path}", include_in_schema=False)
        def front(path: str):
            if path == "api" or path.startswith("api/"):
                raise HTTPException(404, "нет такого адреса")
            f = (dist / path).resolve()
            if path and f.is_file() and dist in f.parents:
                return FileResponse(f)
            return FileResponse(index)
    return api


app = create_app()
