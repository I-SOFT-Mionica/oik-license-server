import sqlite3
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

_HID = "a" * 64

_RELEASE = {"tag_name": "v0.33.0", "body": "Bug fixes."}


def _insert(db_path: str, **overrides) -> dict:
    row = {
        "id": str(uuid.uuid4()),
        "license_code": "ABCD-1234-EFGH-5678",
        "issued_to": "Општина Тест",
        "updates_until": "2027-12-31",
        "modules": '["full"]',
        "hid": _HID,
        "revoked": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        **overrides,
    }
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO licenses (id,license_code,issued_to,updates_until,modules,hid,revoked,created_at)"
        " VALUES (:id,:license_code,:issued_to,:updates_until,:modules,:hid,:revoked,:created_at)",
        row,
    )
    conn.commit()
    conn.close()
    return row


def _token(row: dict, hid: str = _HID) -> str:
    from app.jwt_utils import sign_token
    return sign_token(row, hid)


def test_valid_update_check(api_client, tmp_db):
    lic = _insert(tmp_db)
    with patch("app.routes.check_update._get_latest_release", return_value=_RELEASE):
        r = api_client.post("/api/v1/biracki/check-update",
                            json={"token": _token(lic), "current_version": "v0.32.0"})
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["latest_version"] == "v0.33.0"
    assert "OIK_Setup.exe" in d["download_url"]
    assert "v0.33.0" in d["download_url"]


def test_github_unreachable_still_ok(api_client, tmp_db):
    lic = _insert(tmp_db)
    with patch("app.routes.check_update._get_latest_release", side_effect=Exception("timeout")):
        r = api_client.post("/api/v1/biracki/check-update",
                            json={"token": _token(lic), "current_version": "v0.32.0"})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_updates_expired(api_client, tmp_db):
    lic = _insert(tmp_db, updates_until="2020-01-01")
    r = api_client.post("/api/v1/biracki/check-update",
                        json={"token": _token(lic), "current_version": "v0.32.0"})
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is False
    assert d["reason"] == "updates_expired"
    assert d["expired_on"] == "2020-01-01"


def test_revoked(api_client, tmp_db):
    lic = _insert(tmp_db, revoked=1)
    r = api_client.post("/api/v1/biracki/check-update",
                        json={"token": _token(lic), "current_version": "v0.32.0"})
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is False
    assert d["reason"] == "revoked"


def test_invalid_token(api_client, tmp_db):
    r = api_client.post("/api/v1/biracki/check-update",
                        json={"token": "not.a.real.jwt", "current_version": "v0.32.0"})
    assert r.status_code == 401
    assert r.json()["error"] == "invalid_token"
