import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import jwt
from fastapi import APIRouter
from fastapi.responses import JSONResponse

import app.config as config
from app.database import get_conn
from app.jwt_utils import ALG, sign_token, signing_enabled, token_alg, verify_token
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
            "SELECT * FROM licenses WHERE id = ?", (license_id,)
        ).fetchone()

    if row is None:
        return JSONResponse(status_code=404, content={"error": "unknown_license"})

    if row["revoked"]:
        return UpdateCheckResponse(ok=False, reason="revoked")

    if row["hid"] != hid_in_token:
        return JSONResponse(status_code=403, content={"error": "machine_mismatch"})

    refreshed = _refreshed_token(req.token, dict(row), hid_in_token)

    try:
        cutoff = date.fromisoformat(updates_until)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "invalid_token_claims"})

    if date.today() > cutoff:
        return UpdateCheckResponse(
            token=refreshed,
            ok=False,
            reason="updates_expired",
            expired_on=updates_until,
        )

    # Prefer locally hosted installer — faster, our bandwidth, no GitHub dependency.
    # Falls back to GitHub Releases API if nothing has been uploaded yet (e.g. during
    # initial setup before the first release workflow run completes).
    local = _read_local_release_meta()
    if local:
        return UpdateCheckResponse(
            token=refreshed,
            ok=True,
            latest_version=local["tag"],
            download_url=local["download_url"],
            release_notes="",
        )

    try:
        release = _get_latest_release()
    except Exception as exc:
        log.warning("GitHub release fetch failed: %s", exc)
        return UpdateCheckResponse(ok=True, token=refreshed)

    tag = release.get("tag_name", "")
    download_url = (
        f"https://github.com/{config.github_repo()}/releases/download/{tag}/OIK_Setup.exe"
        if tag else ""
    )
    return UpdateCheckResponse(
        token=refreshed,
        ok=True,
        latest_version=tag,
        download_url=download_url,
        release_notes=str(release.get("body") or ""),
    )


def _read_local_release_meta() -> dict | None:
    """Return latest_release.json content, or None if no upload has happened yet."""
    p = Path(config.releases_dir()) / "latest_release.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


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


def _refreshed_token(raw: str, license_row: dict, hid: str) -> str:
    """A new Ed25519 token for an install still holding an HS256 one
    (verified, not revoked, same machine -- checked by the caller).
    Empty when signing isn't configured or the token is already Ed25519."""
    if not signing_enabled() or token_alg(raw) == ALG:
        return ""
    token = sign_token(license_row, hid)
    with get_conn() as conn:
        conn.execute(
            "UPDATE licenses SET ed25519_issued_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), license_row["id"]),
        )
    return token
