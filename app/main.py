import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.database import init_db
from app.routes import activate, check_update, admin

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = FastAPI(title="OIK License Server", docs_url=None, redoc_url=None)

app.include_router(activate.router, prefix="/api/v1/biracki")
app.include_router(check_update.router, prefix="/api/v1/biracki")
app.include_router(admin.router)

_ADMIN_HTML = Path(__file__).parent / "static" / "admin.html"


@app.get("/admin/", include_in_schema=False)
def admin_ui() -> FileResponse:
    return FileResponse(_ADMIN_HTML)


@app.on_event("startup")
def startup() -> None:
    init_db()
    log.info("Database ready at %s", __import__("app.config", fromlist=["db_path"]).db_path())


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    return {"status": "ok"}
