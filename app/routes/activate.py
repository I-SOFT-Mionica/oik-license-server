from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.database import get_conn
from app.jwt_utils import sign_token
from app.schemas import ActivateRequest, ActivateResponse

router = APIRouter()


@router.post("/activate", response_model=ActivateResponse)
def activate(req: ActivateRequest):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM licenses WHERE license_code = ?",
            (req.license_code,),
        ).fetchone()

    if row is None:
        return JSONResponse(status_code=404, content={"error": "unknown_license"})

    lic = dict(row)

    if lic["revoked"]:
        return JSONResponse(status_code=403, content={"error": "revoked"})

    if lic["hid"] is not None and lic["hid"] != req.hid:
        return JSONResponse(status_code=403, content={"error": "machine_mismatch"})

    if lic["hid"] is None:
        with get_conn() as conn:
            conn.execute(
                "UPDATE licenses SET hid = ? WHERE id = ?",
                (req.hid, lic["id"]),
            )

    return ActivateResponse(token=sign_token(lic, req.hid))
