import hashlib
import json
import logging
import secrets
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Header, HTTPException, UploadFile
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

    return {"ok": True, "tag": tag, "sha256": sha256,
            "url": f"/downloads/{tag}/OIK_Setup.exe"}


@router.post("/deploy")
def deploy(background_tasks: BackgroundTasks, _: None = Depends(_require_admin)):
    """Pull latest code and restart the container stack.

    Called by the GitHub Actions deploy workflow via curl — avoids the need
    for SSH keys entirely. Returns immediately; restart happens in background.
    """
    background_tasks.add_task(_run_deploy)
    return {"ok": True, "message": "deploy started"}


def _run_deploy() -> None:
    import app.config as _cfg  # local import to avoid circular at module load
    app_dir = Path(__file__).resolve().parent.parent.parent
    try:
        subprocess.run(
            ["git", "pull", "origin", "main"],
            cwd=app_dir, check=True, capture_output=True, text=True,
        )
        subprocess.run(
            ["podman", "compose", "up", "-d", "--build"],
            cwd=app_dir, check=True, capture_output=True, text=True,
        )
        log.info("deploy: completed OK")
    except subprocess.CalledProcessError as exc:
        log.error("deploy failed: %s\n%s", exc, exc.stderr)
