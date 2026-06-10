import sqlite3
import uuid
from datetime import datetime, timezone

_HID = "a" * 64


def _insert(db_path: str, **overrides) -> dict:
    row = {
        "id": str(uuid.uuid4()),
        "license_code": "ABCD-1234-EFGH-5678",
        "issued_to": "Општина Тест",
        "updates_until": "2027-12-31",
        "modules": '["full"]',
        "hid": None,
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


def test_fresh_activation(api_client, tmp_db):
    _insert(tmp_db)
    r = api_client.post("/api/v1/biracki/activate",
                        json={"license_code": "ABCD-1234-EFGH-5678", "hid": _HID})
    assert r.status_code == 200
    assert "token" in r.json()


def test_token_claims(api_client, tmp_db):
    _insert(tmp_db)
    token = api_client.post("/api/v1/biracki/activate",
                            json={"license_code": "ABCD-1234-EFGH-5678", "hid": _HID}).json()["token"]
    from app.jwt_utils import verify_token
    p = verify_token(token)
    assert p["license_code"] == "ABCD-1234-EFGH-5678"
    assert p["hid"] == _HID
    assert p["issued_to"] == "Општина Тест"
    assert p["updates_until"] == "2027-12-31"
    assert p["modules"] == ["full"]
    assert "issued_at" in p


def test_reactivation_same_hid(api_client, tmp_db):
    _insert(tmp_db, hid=_HID)
    r = api_client.post("/api/v1/biracki/activate",
                        json={"license_code": "ABCD-1234-EFGH-5678", "hid": _HID})
    assert r.status_code == 200


def test_unknown_license(api_client, tmp_db):
    r = api_client.post("/api/v1/biracki/activate",
                        json={"license_code": "XXXX-XXXX-XXXX-XXXX", "hid": _HID})
    assert r.status_code == 404
    assert r.json()["error"] == "unknown_license"


def test_revoked(api_client, tmp_db):
    _insert(tmp_db, revoked=1)
    r = api_client.post("/api/v1/biracki/activate",
                        json={"license_code": "ABCD-1234-EFGH-5678", "hid": _HID})
    assert r.status_code == 403
    assert r.json()["error"] == "revoked"


def test_machine_mismatch(api_client, tmp_db):
    _insert(tmp_db, hid="b" * 64)
    r = api_client.post("/api/v1/biracki/activate",
                        json={"license_code": "ABCD-1234-EFGH-5678", "hid": _HID})
    assert r.status_code == 403
    assert r.json()["error"] == "machine_mismatch"
