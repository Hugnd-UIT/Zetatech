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
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
ALLOWED_HOST_SET = set(ALLOWED_HOSTS)
STATIC_DIR = Path(__file__).parent / "static"


def validate_runtime_persistence() -> Path:
    db_path = ensure_db_dir()
    runtime_root = db_path.parent
    logger.info("Using canonical runtime root: %s", runtime_root)
    logger.info("Critical durable-root validation succeeded for database path: %s", db_path)
    return runtime_root

_AUTH_TOKEN = os.environ.get("ZETATECH_AUTH_TOKEN", "").strip()
_PUBLIC_PATH_PREFIXES = ("/static", "/assets", "/docs", "/openapi.json", "/redoc")
_PUBLIC_EXACT_PATHS = {"/", "/health"}


def rate_limit_exceeded_handler(request: Request, exc: Exception):
    return PlainTextResponse(
        "Rate limit exceeded. Please try again later.",
        status_code=429,
    )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "connect-src 'self' ws://localhost:* wss://localhost:*;"
        )
        return response


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not _AUTH_TOKEN:
            return await call_next(request)

        path = request.url.path
        if path in _PUBLIC_EXACT_PATHS:
            return await call_next(request)
        if any(path.startswith(prefix) for prefix in _PUBLIC_PATH_PREFIXES):
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return PlainTextResponse("Unauthorized", status_code=401)

        provided_token = auth_header[7:]
        if not secrets.compare_digest(provided_token, _AUTH_TOKEN):
            return PlainTextResponse("Forbidden", status_code=403)

        return await call_next(request)


def websocket_has_valid_auth(websocket: WebSocket) -> bool:
    if not _AUTH_TOKEN:
        return True
    auth_header = websocket.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return False
    return secrets.compare_digest(auth_header[7:], _AUTH_TOKEN)


def setup_logging() -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    file_handler = build_rotating_file_handler()
    if file_handler is not None:
        handlers.insert(0, file_handler)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
        force=True,
    )
    if file_handler is None:
        logging.getLogger("zetatech").warning(
            "File logging disabled because the log directory is not writable."
        )
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)


def create_app() -> FastAPI:
    setup_logging()
    logger.info("Starting Zetatech Server...")
    validate_runtime_persistence()
    bootstrap_default_custom_rules()
    runtime_metadata = get_runtime_metadata()

    app = FastAPI(
        title="Zetatech Dashboard",
        description="WordPress Plugin & Theme Security Scanner",
        version=runtime_metadata.current_version,
    )
    configure_application(app)
    return app


def configure_application(app: FastAPI) -> None:
    app.state.update_manager = release.manager
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(AuthMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^http://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        allow_credentials=False,
    )

    if _AUTH_TOKEN:
        logger.info("Authentication enabled (ZETATECH_AUTH_TOKEN is set)")
    else:
        logger.warning(
            "Authentication DISABLED. Set ZETATECH_AUTH_TOKEN env var to enable."
        )

    warmup_update_manager()
    register_routers(app)
    mount_static_directories(app, STATIC_DIR)
    register_root_route(app, STATIC_DIR)
    register_scan_websocket(app)


def warmup_update_manager() -> None:
    try:
        release.manager.get_status(force=False)
    except Exception:
        logger.warning("Startup release warmup failed.", exc_info=True)


def register_routers(app: FastAPI) -> None:
    for router in (
        scans.router,
        semgrep.router,
        favorites.router,
        catalog.router,
        system.router,
        agents.router,
    ):
        app.include_router(router)


def mount_static_directories(app: FastAPI, static_dir: Path) -> None:
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")


def register_root_route(app: FastAPI, static_dir: Path) -> None:

    @app.get("/", response_class=HTMLResponse)
    @limiter.limit("10000/minute")
    async def root(request: Request):
        index_path = static_dir / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return HTMLResponse("<h1>Zetatech Dashboard</h1><p>Static files not found.</p>")

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})


def register_scan_websocket(app: FastAPI) -> None:

    @app.websocket("/ws/scans/{session_id}")
    async def websocket_endpoint(websocket: WebSocket, session_id: int):
        origin = websocket.headers.get("origin")
        if not is_allowed_websocket_origin(origin):
            await websocket.close(code=1008)
            return
        if not websocket_has_valid_auth(websocket):
            await websocket.close(code=1008)
            return

        await manager.connect(websocket, session_id)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            await manager.disconnect(websocket, session_id)


def is_allowed_websocket_origin(origin: str | None) -> bool:
    if not origin:
        return False
    try:
        origin_host = (urlparse(origin).hostname or "").lower()
    except Exception:
        return False
    return origin_host in ALLOWED_HOST_SET
