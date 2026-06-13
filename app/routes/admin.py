import json
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

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
