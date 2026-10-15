from pydantic import BaseModel


class ActivateRequest(BaseModel):
    license_code: str
    hid: str


class ActivateResponse(BaseModel):
    token: str


class UpdateCheckRequest(BaseModel):
    token: str
    current_version: str


class UpdateCheckResponse(BaseModel):
    ok: bool
    latest_version: str = ""
    download_url: str = ""
    release_notes: str = ""
    reason: str = ""
    expired_on: str = ""
    # A freshly signed Ed25519 token for an install still holding an HS256
    # one; the desktop app replaces license.dat with it. Empty otherwise.
    token: str = ""
