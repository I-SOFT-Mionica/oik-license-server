"""Tests for the server-hosted "what's new" changelog feed.

GET /downloads/changelog.json is public and always returns
{"entries": [...]} -- an empty list before any admin POST, never 404
(biracki-odbor's About page merges this over its built-in list on
every launch, so a hard failure here would be worse than showing
nothing new). POST /admin/changelog lets an entry be added/corrected
without a client release; the server entry wins on a version collision
client-side.

Auth: CHANGELOG_TOKEN, deliberately NOT ADMIN_TOKEN. Changelog content
is public marketing text, not licensing data or the shipped
executable -- reusing ADMIN_TOKEN (which also gates issuing/revoking
real licenses and uploading the installer) would mean anyone trusted
with changelog-posting also holds the keys to the whole admin surface.
See test_changelog_token_is_not_interchangeable_with_admin_token below.
"""

import pytest


@pytest.fixture
def changelog_path(tmp_path, monkeypatch):
    p = tmp_path / "changelog.json"
    monkeypatch.setenv("CHANGELOG_PATH", str(p))
    return p


@pytest.fixture
def changelog_headers(monkeypatch):
    monkeypatch.setenv("CHANGELOG_TOKEN", "test-changelog-token")
    return {"Authorization": "Bearer test-changelog-token"}


def test_get_changelog_before_any_entry_returns_empty_list(api_client, changelog_path):
    r = api_client.get("/downloads/changelog.json")
    assert r.status_code == 200
    assert r.json() == {"entries": []}


def test_post_changelog_happy_path(api_client, changelog_path, changelog_headers):
    body = {"version": "0.74.0", "date": "1.8.2026.", "bullets": ["Прва ставка", "Друга ставка"]}
    r = api_client.post("/admin/changelog", json=body, headers=changelog_headers)
    assert r.status_code == 201
    assert r.json() == body

    got = api_client.get("/downloads/changelog.json").json()
    assert got["entries"] == [body]


def test_post_changelog_strips_leading_v_and_whitespace(api_client, changelog_path, changelog_headers) -> None:
    r = api_client.post(
        "/admin/changelog",
        json={"version": "  v0.74.0 ", "date": " 1.8.2026. ", "bullets": [" x "]},
        headers=changelog_headers,
    )
    assert r.status_code == 201
    assert r.json() == {"version": "0.74.0", "date": "1.8.2026.", "bullets": ["x"]}


def test_post_changelog_second_entry_is_prepended(api_client, changelog_path, changelog_headers) -> None:
    api_client.post(
        "/admin/changelog",
        json={"version": "0.73.1", "date": "28.7.2026.", "bullets": ["old"]},
        headers=changelog_headers,
    )
    api_client.post(
        "/admin/changelog",
        json={"version": "0.74.0", "date": "1.8.2026.", "bullets": ["new"]},
        headers=changelog_headers,
    )
    got = api_client.get("/downloads/changelog.json").json()
    assert [e["version"] for e in got["entries"]] == ["0.74.0", "0.73.1"]


def test_post_changelog_duplicate_version_returns_409(api_client, changelog_path, changelog_headers) -> None:
    body = {"version": "0.74.0", "date": "1.8.2026.", "bullets": ["x"]}
    api_client.post("/admin/changelog", json=body, headers=changelog_headers)
    r = api_client.post("/admin/changelog", json=body, headers=changelog_headers)
    assert r.status_code == 409


def test_post_changelog_bad_auth_returns_401(api_client, changelog_path, changelog_headers) -> None:
    r = api_client.post(
        "/admin/changelog",
        json={"version": "0.74.0", "date": "1.8.2026.", "bullets": ["x"]},
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert r.status_code == 401


def test_post_changelog_token_not_configured_returns_503(api_client, changelog_path, monkeypatch) -> None:
    monkeypatch.delenv("CHANGELOG_TOKEN", raising=False)
    r = api_client.post(
        "/admin/changelog",
        json={"version": "0.74.0", "date": "1.8.2026.", "bullets": ["x"]},
        headers={"Authorization": "Bearer whatever"},
    )
    assert r.status_code == 503


def test_changelog_token_is_not_interchangeable_with_admin_token(api_client, changelog_path, monkeypatch) -> None:
    """The whole point of the separate token: a valid ADMIN_TOKEN must
    NOT unlock changelog posting, and vice versa (proven elsewhere by
    admin routes already requiring ADMIN_TOKEN specifically)."""
    monkeypatch.setenv("ADMIN_TOKEN", "the-real-admin-token")
    monkeypatch.setenv("CHANGELOG_TOKEN", "the-real-changelog-token")

    r = api_client.post(
        "/admin/changelog",
        json={"version": "0.74.0", "date": "1.8.2026.", "bullets": ["x"]},
        headers={"Authorization": "Bearer the-real-admin-token"},
    )
    assert r.status_code == 401

    r2 = api_client.post(
        "/admin/changelog",
        json={"version": "0.74.0", "date": "1.8.2026.", "bullets": ["x"]},
        headers={"Authorization": "Bearer the-real-changelog-token"},
    )
    assert r2.status_code == 201


@pytest.mark.parametrize("bad_version", ["not-semver", "v1.2", "1.2.3.4", ""])
def test_post_changelog_malformed_version_returns_422(api_client, changelog_path, changelog_headers, bad_version) -> None:
    r = api_client.post(
        "/admin/changelog",
        json={"version": bad_version, "date": "1.8.2026.", "bullets": ["x"]},
        headers=changelog_headers,
    )
    assert r.status_code == 422


def test_post_changelog_empty_date_returns_422(api_client, changelog_path, changelog_headers) -> None:
    r = api_client.post(
        "/admin/changelog",
        json={"version": "0.74.0", "date": "   ", "bullets": ["x"]},
        headers=changelog_headers,
    )
    assert r.status_code == 422


def test_post_changelog_empty_bullets_returns_422(api_client, changelog_path, changelog_headers) -> None:
    r = api_client.post(
        "/admin/changelog",
        json={"version": "0.74.0", "date": "1.8.2026.", "bullets": []},
        headers=changelog_headers,
    )
    assert r.status_code == 422


def test_post_changelog_too_many_bullets_returns_422(api_client, changelog_path, changelog_headers) -> None:
    r = api_client.post(
        "/admin/changelog",
        json={"version": "0.74.0", "date": "1.8.2026.", "bullets": ["a", "b", "c", "d", "e"]},
        headers=changelog_headers,
    )
    assert r.status_code == 422


def test_get_changelog_survives_corrupt_file(api_client, changelog_path) -> None:
    changelog_path.write_text("not json at all", encoding="utf-8")
    r = api_client.get("/downloads/changelog.json")
    assert r.status_code == 200
    assert r.json() == {"entries": []}
