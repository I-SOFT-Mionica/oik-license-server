import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

import app.config as config
from app.database import init_db
from app.routes import activate, check_update, admin

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = FastAPI(title="OIK License Server", docs_url=None, redoc_url=None)

_STARTED_AT: str = ""
_GIT_SHA: str = ""

app.include_router(activate.router, prefix="/api/v1/biracki")
app.include_router(check_update.router, prefix="/api/v1/biracki")
app.include_router(admin.router)

_ADMIN_HTML = Path(__file__).parent / "static" / "admin.html"


@app.get("/admin/", include_in_schema=False)
def admin_ui() -> FileResponse:
    return FileResponse(_ADMIN_HTML)


# ── Installer download endpoints ─────────────────────────────────────────────
# Serve binaries uploaded via POST /admin/releases/{tag}/upload.
# Public — no auth. Clients receive the URL from check-update.

@app.get("/downloads/{tag}/OIK_Setup.exe", include_in_schema=False)
def download_versioned(tag: str) -> FileResponse:
    path = Path(config.releases_dir()) / tag / "OIK_Setup.exe"
    if not path.exists():
        raise HTTPException(404, {"error": "not_found", "tag": tag})
    return FileResponse(
        path,
        filename="OIK_Setup.exe",
        media_type="application/octet-stream",
    )


@app.get("/downloads/latest/OIK_Setup.exe", include_in_schema=False)
def download_latest() -> FileResponse:
    meta = _read_latest_release_meta()
    if meta is None:
        raise HTTPException(404, {"error": "no_release_uploaded_yet"})
    return download_versioned(meta["tag"])


@app.get("/downloads/latest.json", include_in_schema=False)
def latest_release_json() -> dict:
    meta = _read_latest_release_meta()
    if meta is None:
        raise HTTPException(404, {"error": "no_release_uploaded_yet"})
    return meta


# ── In-app "what's new" changelog ────────────────────────────────────────────
# Public — no auth. Lets biracki-odbor's About page show/correct release
# notes without a client build (see POST /admin/changelog in routes/admin.py).
# Always 200 + {"entries": [...]} — an empty list before the first admin
# POST, never 404 (the client merges this over its own built-in list).

@app.get("/downloads/changelog.json", include_in_schema=False)
def changelog_json() -> dict:
    p = Path(config.changelog_path())
    if not p.exists():
        return {"entries": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"entries": []}


def _read_latest_release_meta() -> dict | None:
    p = Path(config.releases_dir()) / "latest_release.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


# ── Lifecycle ─────────────────────────────────────────────────────────────────

@app.on_event("startup")
def startup() -> None:
    global _STARTED_AT, _GIT_SHA
    _STARTED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    _GIT_SHA = os.environ.get("GIT_SHA", "unknown")[:7]
    init_db()
    log.info("Started at %s  git=%s", _STARTED_AT, _GIT_SHA)
    log.info("Database ready at %s", config.db_path())
    log.info("Releases dir: %s", config.releases_dir())


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    return {"status": "ok", "started_at": _STARTED_AT, "git": _GIT_SHA}
