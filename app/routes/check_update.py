import logging
from datetime import date

import httpx
import jwt
from fastapi import APIRouter
from fastapi.responses import JSONResponse

import app.config as config
from app.database import get_conn
from app.jwt_utils import verify_token
from app.schemas import UpdateCheckRequest, UpdateCheckResponse

log = logging.getLogger(__name__)
router = APIRouter()


@router.post("/check-update", response_model=UpdateCheckResponse)
def check_update(req: UpdateCheckRequest):
    try:
        payload = verify_token(req.token)
    except jwt.InvalidTokenError:
        return JSONResponse(status_code=401, content={"error": "invalid_token"})

    license_id = payload.get("sub", "")
    hid_in_token = payload.get("hid", "")
    updates_until = payload.get("updates_until", "")

    with get_conn() as conn:
        row = conn.execute(
            "SELECT revoked, hid FROM licenses WHERE id = ?", (license_id,)
        ).fetchone()

    if row is None:
        return JSONResponse(status_code=404, content={"error": "unknown_license"})

    if row["revoked"]:
        return UpdateCheckResponse(ok=False, reason="revoked")

    if row["hid"] != hid_in_token:
        return JSONResponse(status_code=403, content={"error": "machine_mismatch"})

    try:
        cutoff = date.fromisoformat(updates_until)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "invalid_token_claims"})

    if date.today() > cutoff:
        return UpdateCheckResponse(
            ok=False,
            reason="updates_expired",
            expired_on=updates_until,
        )

    try:
        release = _get_latest_release()
    except Exception as exc:
        log.warning("GitHub release fetch failed: %s", exc)
        return UpdateCheckResponse(ok=True)

    tag = release.get("tag_name", "")
    download_url = (
        f"https://github.com/{config.github_repo()}/releases/download/{tag}/OIK_Setup.exe"
        if tag else ""
    )
    return UpdateCheckResponse(
        ok=True,
        latest_version=tag,
        download_url=download_url,
        release_notes=str(release.get("body") or ""),
    )


def _get_latest_release() -> dict:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    tok = config.github_token()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    resp = httpx.get(
        f"https://api.github.com/repos/{config.github_repo()}/releases/latest",
        headers=headers,
        timeout=10,
        follow_redirects=True,
    )
    resp.raise_for_status()
    return resp.json()
