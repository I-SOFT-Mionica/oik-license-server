"""Licence tokens.

New tokens are signed with an Ed25519 private key (JWT_SIGNING_KEY), so
the desktop app can verify them offline with the matching public key it
ships with -- licences must keep working indefinitely, even with this
server gone. Tokens issued before the switch are HS256 (JWT_SECRET) and
are still accepted here; /check-update hands those installs a fresh
Ed25519 token.

Without JWT_SIGNING_KEY the server keeps issuing HS256 exactly as before.
"""

import base64
import json
from datetime import date

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import app.config as config

ALG = "EdDSA"
LEGACY_ALG = "HS256"


def _private_key() -> Ed25519PrivateKey | None:
    raw = config.jwt_signing_key()
    if not raw:
        return None
    return Ed25519PrivateKey.from_private_bytes(base64.b64decode(raw))


def signing_enabled() -> bool:
    return _private_key() is not None


def _payload(license_row: dict, hid: str) -> dict:
    modules = license_row["modules"]
    if isinstance(modules, str):
        modules = json.loads(modules)
    return {
        "sub": license_row["id"],
        "license_code": license_row["license_code"],
        "issued_to": license_row["issued_to"],
        "hid": hid,
        "issued_at": date.today().isoformat(),
        "updates_until": license_row["updates_until"],
        "modules": modules,
    }


def sign_token(license_row: dict, hid: str) -> str:
    key = _private_key()
    if key is None:
        return jwt.encode(_payload(license_row, hid), config.jwt_secret(), algorithm=LEGACY_ALG)
    return jwt.encode(_payload(license_row, hid), key, algorithm=ALG)


def token_alg(raw: str) -> str:
    """Algorithm named in the token header. Raises jwt.InvalidTokenError if malformed."""
    return str(jwt.get_unverified_header(raw).get("alg", ""))


def verify_token(raw: str) -> dict:
    """Decode and verify a token of either generation. Raises jwt.InvalidTokenError on failure."""
    if token_alg(raw) == ALG:
        key = _private_key()
        if key is None:
            raise jwt.InvalidTokenError("EdDSA token but JWT_SIGNING_KEY is not configured")
        return jwt.decode(raw, key.public_key(), algorithms=[ALG])
    return jwt.decode(raw, config.jwt_secret(), algorithms=[LEGACY_ALG])
