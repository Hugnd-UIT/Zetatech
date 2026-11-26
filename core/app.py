import logging
import os
import secrets
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse, Response

from main import get_runtime_metadata
from database.models import ensure_db_dir
from logger import build_rotating_file_handler
from core import release
from core.limiter import limiter
from core.routers import agents, catalog, favorites, scans, semgrep, system
from core.routers.semgrep.helper import bootstrap_default_custom_rules
from core.websockets import manager

logger = logging.getLogger("zetatech")
_HOSTS = ["localhost", "127.0.0.1"]
_HOST_SET = set(_HOSTS)
_STATIC = Path(__file__).parent / "static"


def _check_runtime() -> Path:
    db_path = ensure_db_dir()
    root = db_path.parent
    logger.info("Using canonical runtime root: %s", root)
    logger.info("Critical durable-root validation succeeded for database path: %s", db_path)
    return root

_TOKEN = os.environ.get("ZETATECH_AUTH_TOKEN", "").strip()
_PUBLIC_PREFIXES = ("/static", "/assets", "/docs", "/openapi.json", "/redoc")
_PUBLIC_EXACT = {"/", "/health"}


def _rate_limit(request: Request, exc: Exception):
    return PlainTextResponse(
        "Rate limit exceeded. Please try again later.",
        status_code=429,
    )


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        res: Response = await call_next(request)
        res.headers["X-Content-Type-Options"] = "nosniff"
        res.headers["X-Frame-Options"] = "DENY"
        res.headers["X-XSS-Protection"] = "1; mode=block"
        res.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        res.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        res.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "connect-src 'self' ws://localhost:* wss://localhost:*;"
        )
        return res


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not _TOKEN:
            return await call_next(request)

        path = request.url.path
        if path in _PUBLIC_EXACT:
            return await call_next(request)
        if any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES):
            return await call_next(request)

        header = request.headers.get("authorization", "")
        if not header.startswith("Bearer "):
            return PlainTextResponse("Unauthorized", status_code=401)

        token = header[7:]
        if not secrets.compare_digest(token, _TOKEN):
            return PlainTextResponse("Forbidden", status_code=403)

        return await call_next(request)


def _ws_auth(websocket: WebSocket) -> bool:
    if not _TOKEN:
        return True
    header = websocket.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        return False
    return secrets.compare_digest(header[7:], _TOKEN)


def _setup_log() -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    file = build_rotating_file_handler()
    if file is not None:
        handlers.insert(0, file)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
        force=True,
    )
    if file is None:
        logging.getLogger("zetatech").warning(
            "File logging disabled because the log directory is not writable."
        )
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)


def create_app() -> FastAPI:
    _setup_log()
    logger.info("Starting Zetatech Server...")
    _check_runtime()
    bootstrap_default_custom_rules()
    meta = get_runtime_metadata()

    app = FastAPI(
        title="Zetatech Dashboard",
        description="WordPress Plugin & Theme Security Scanner",
        version=meta.current_version,
    )
    _configure(app)
    return app


def _configure(app: FastAPI) -> None:
    app.state.update_manager = release.manager
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit)

    app.add_middleware(SecurityMiddleware)
    app.add_middleware(AuthMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_HOSTS)
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^http://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        allow_credentials=False,
    )

    if _TOKEN:
        logger.info("Authentication enabled (ZETATECH_AUTH_TOKEN is set)")
    else:
        logger.warning(
            "Authentication DISABLED. Set ZETATECH_AUTH_TOKEN env var to enable."
        )

    _warmup()
    _routers(app)
    _mount_static(app, _STATIC)
    _root_route(app, _STATIC)
    _ws_route(app)


def _warmup() -> None:
    try:
        release.manager.get_status(force=False)
    except Exception:
        logger.warning("Startup release warmup failed.", exc_info=True)


def _routers(app: FastAPI) -> None:
    for router in (
        scans.router,
        semgrep.router,
        favorites.router,
        catalog.router,
        system.router,
        agents.router,
    ):
        app.include_router(router)


def _mount_static(app: FastAPI, static_dir: Path) -> None:
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    assets = static_dir / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")


def _root_route(app: FastAPI, static_dir: Path) -> None:

    @app.get("/", response_class=HTMLResponse)
    @limiter.limit("10000/minute")
    async def root(request: Request):
        index = static_dir / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return HTMLResponse("<h1>Zetatech Dashboard</h1><p>Static files not found.</p>")

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})


def _ws_route(app: FastAPI) -> None:

    @app.websocket("/ws/scans/{session_id}")
    async def ws(websocket: WebSocket, session_id: int):
        origin = websocket.headers.get("origin")
        if not _allow_origin(origin):
            await websocket.close(code=1008)
            return
        if not _ws_auth(websocket):
            await websocket.close(code=1008)
            return

        await manager.connect(websocket, session_id)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            await manager.disconnect(websocket, session_id)


def _allow_origin(origin: str | None) -> bool:
    if not origin:
        return False
    try:
        host = (urlparse(origin).hostname or "").lower()
    except Exception:
        return False
    return host in _HOST_SET
