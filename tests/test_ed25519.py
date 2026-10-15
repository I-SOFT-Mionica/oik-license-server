"""Ed25519 licence tokens and the migration of HS256 installs.

With JWT_SIGNING_KEY set, new tokens are EdDSA (verifiable offline by the
desktop app's embedded public key) and /check-update re-issues EdDSA
tokens to installs still holding HS256 ones. Without it, nothing changes.
"""

import base64
import sqlite3

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tests.test_check_update import _HID, _insert


def _seed(key: Ed25519PrivateKey) -> str:
    raw = key.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    return base64.b64encode(raw).decode()


@pytest.fixture
def signing_key(monkeypatch):
    key = Ed25519PrivateKey.generate()
    monkeypatch.setenv("JWT_SIGNING_KEY", _seed(key))
    return key


def _legacy_token(row: dict) -> str:
    """An HS256 token exactly as issued before the switch."""
    import app.config as config
    from app.jwt_utils import _payload
    return jwt.encode(_payload(row, _HID), config.jwt_secret(), algorithm="HS256")


def _migrated_at(db: str, license_id: str):
    conn = sqlite3.connect(db)
    try:
        return conn.execute(
            "SELECT ed25519_issued_at FROM licenses WHERE id = ?", (license_id,)
        ).fetchone()[0]
    finally:
        conn.close()


def test_activation_issues_eddsa_verifiable_with_the_public_key(api_client, tmp_db, signing_key):
    lic = _insert(tmp_db, hid=None)
    r = api_client.post("/api/v1/biracki/activate",
                        json={"license_code": lic["license_code"], "hid": _HID})
    token = r.json()["token"]
    assert jwt.get_unverified_header(token)["alg"] == "EdDSA"
    claims = jwt.decode(token, signing_key.public_key(), algorithms=["EdDSA"])
    assert claims["hid"] == _HID
    assert _migrated_at(tmp_db, lic["id"]) is not None


def test_legacy_install_gets_a_fresh_eddsa_token(api_client, tmp_db, signing_key):
    lic = _insert(tmp_db)
    r = api_client.post("/api/v1/biracki/check-update",
                        json={"token": _legacy_token(lic), "current_version": "0.97.0"})
    body = r.json()
    assert r.status_code == 200 and body["ok"] is True
    claims = jwt.decode(body["token"], signing_key.public_key(), algorithms=["EdDSA"])
    assert claims["sub"] == lic["id"] and claims["hid"] == _HID
    assert _migrated_at(tmp_db, lic["id"]) is not None


def test_already_eddsa_install_gets_no_new_token(api_client, tmp_db, signing_key):
    lic = _insert(tmp_db)
    from app.jwt_utils import sign_token
    r = api_client.post("/api/v1/biracki/check-update",
                        json={"token": sign_token(lic, _HID), "current_version": "0.97.0"})
    assert r.status_code == 200 and r.json()["token"] == ""


def test_expired_updates_still_get_the_new_token(api_client, tmp_db, signing_key):
    lic = _insert(tmp_db, updates_until="2020-01-01")
    r = api_client.post("/api/v1/biracki/check-update",
                        json={"token": _legacy_token(lic), "current_version": "0.97.0"})
    body = r.json()
    assert body["reason"] == "updates_expired"
    assert jwt.get_unverified_header(body["token"])["alg"] == "EdDSA"


def test_revoked_licence_is_not_refreshed(api_client, tmp_db, signing_key):
    lic = _insert(tmp_db, revoked=1)
    r = api_client.post("/api/v1/biracki/check-update",
                        json={"token": _legacy_token(lic), "current_version": "0.97.0"})
    assert r.json()["reason"] == "revoked" and r.json()["token"] == ""
    assert _migrated_at(tmp_db, lic["id"]) is None


def test_token_signed_with_another_key_is_rejected(api_client, tmp_db, signing_key):
    lic = _insert(tmp_db)
    from app.jwt_utils import _payload
    forged = jwt.encode(_payload(lic, _HID), Ed25519PrivateKey.generate(), algorithm="EdDSA")
    r = api_client.post("/api/v1/biracki/check-update",
                        json={"token": forged, "current_version": "0.97.0"})
    assert r.status_code == 401


def test_without_signing_key_nothing_changes(api_client, tmp_db, monkeypatch):
    monkeypatch.delenv("JWT_SIGNING_KEY", raising=False)
    lic = _insert(tmp_db)
    r = api_client.post("/api/v1/biracki/check-update",
                        json={"token": _legacy_token(lic), "current_version": "0.97.0"})
    assert r.status_code == 200 and r.json()["token"] == ""
    assert _migrated_at(tmp_db, lic["id"]) is None
