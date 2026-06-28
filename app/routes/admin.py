import hashlib
import json
import logging
import secrets
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from pydantic import BaseModel

log = logging.getLogger(__name__)

import app.config as config
from app.database import get_conn

router = APIRouter(prefix="/admin")


def _require_admin(authorization: str = Header(...)) -> None:
    tok = config.admin_token()
    if not tok:
        raise HTTPException(503, {"error": "ADMIN_TOKEN not configured on server"})
    if authorization != f"Bearer {tok}":
        raise HTTPException(401, {"error": "unauthorized"})


def _prune_old_releases(releases_path: Path, keep: int = 2) -> None:
    """Delete all but the `keep` most recently uploaded release directories.

    Sorted by upload time (mtime), so the newest `keep` releases are always
    retained and older ones are removed to cap disk usage.
    """
    dirs = sorted(
        [d for d in releases_path.iterdir() if d.is_dir()],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    for old in dirs[keep:]:
        log.info("pruning old release: %s", old.name)
        shutil.rmtree(old)


class IssueRequest(BaseModel):
    issued_to: str
    updates_until: str
    modules: list[str] = ["full"]


@router.get("/licenses")
def list_licenses(_: None = Depends(_require_admin)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, license_code, issued_to, updates_until, modules, hid, revoked, created_at"
            " FROM licenses ORDER BY created_at DESC"
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["modules"] = json.loads(d["modules"])
        d["revoked"] = bool(d["revoked"])
        result.append(d)
    return result


@router.post("/licenses", status_code=201)
def issue_license(req: IssueRequest, _: None = Depends(_require_admin)):
    license_id = str(uuid.uuid4())
    code = "-".join(secrets.token_hex(2).upper() for _ in range(4))
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO licenses (id, license_code, issued_to, updates_until, modules, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (license_id, code, req.issued_to, req.updates_until, json.dumps(req.modules), now),
        )
    return {"license_code": code, "id": license_id}


@router.post("/licenses/{license_id}/revoke")
def revoke(license_id: str, _: None = Depends(_require_admin)):
    with get_conn() as conn:
        conn.execute("UPDATE licenses SET revoked=1 WHERE id=?", (license_id,))
    return {"ok": True}


@router.post("/licenses/{license_id}/unrevoke")
def unrevoke(license_id: str, _: None = Depends(_require_admin)):
    with get_conn() as conn:
        conn.execute("UPDATE licenses SET revoked=0 WHERE id=?", (license_id,))
    return {"ok": True}


@router.post("/licenses/{license_id}/clear-hid")
def clear_hid(license_id: str, _: None = Depends(_require_admin)):
    with get_conn() as conn:
        conn.execute("UPDATE licenses SET hid=NULL WHERE id=?", (license_id,))
    return {"ok": True}


@router.post("/releases/{tag}/upload")
def upload_release(
    tag: str,
    file: UploadFile = File(...),
    _: None = Depends(_require_admin),
) -> dict:
    """Store a signed installer binary for a release tag.

    Called automatically by the biracki-odbor release.yml workflow after
    building OIK_Setup.exe. Also usable manually for backfilling older tags.

    The file lands at {releases_dir}/{tag}/OIK_Setup.exe.
    latest_release.json is updated to point check-update at the new version.
    """
    releases_path = Path(config.releases_dir())
    dest_dir = releases_path / tag
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "OIK_Setup.exe"

    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    sha256 = hashlib.sha256(dest.read_bytes()).hexdigest()
    meta = {
        "tag": tag,
        "sha256": sha256,
        "size_bytes": dest.stat().st_size,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "download_url": f"{config.server_base_url()}/downloads/{tag}/OIK_Setup.exe",
    }
    (releases_path / "latest_release.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )

    _prune_old_releases(releases_path)

    return {"ok": True, "tag": tag, "sha256": sha256,
            "url": f"/downloads/{tag}/OIK_Setup.exe"}
