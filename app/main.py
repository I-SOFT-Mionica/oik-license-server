import logging

from fastapi import FastAPI

from app.database import init_db
from app.routes import activate, check_update

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = FastAPI(title="OIK License Server", docs_url=None, redoc_url=None)

app.include_router(activate.router, prefix="/api/v1/biracki")
app.include_router(check_update.router, prefix="/api/v1/biracki")


@app.on_event("startup")
def startup() -> None:
    init_db()
    log.info("Database ready at %s", __import__("app.config", fromlist=["db_path"]).db_path())


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    return {"status": "ok"}
