import json
from datetime import date

import jwt

import app.config as config

_ALGORITHM = "HS256"


def sign_token(license_row: dict, hid: str) -> str:
    modules = license_row["modules"]
    if isinstance(modules, str):
        modules = json.loads(modules)
    payload = {
        "sub": license_row["id"],
        "license_code": license_row["license_code"],
        "issued_to": license_row["issued_to"],
        "hid": hid,
        "issued_at": date.today().isoformat(),
        "updates_until": license_row["updates_until"],
        "modules": modules,
    }
    return jwt.encode(payload, config.jwt_secret(), algorithm=_ALGORITHM)


def verify_token(raw: str) -> dict:
    """Decode and verify JWT signature. Raises jwt.InvalidTokenError on failure."""
    return jwt.decode(raw, config.jwt_secret(), algorithms=[_ALGORITHM])
