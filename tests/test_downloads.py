"""Tests for installer upload/download.

One release tag holds several products: OIK and its Formalizator
companion are built from the same tag in biracki-odbor and published
side by side.

The dangerous case these pin down: the upload used to hardcode its
destination as OIK_Setup.exe and ignore the uploaded filename, so a
second upload for the same tag overwrote the OIK installer *and* then
rewrote latest_release.json with the new file's sha256 while still
advertising it as OIK_Setup.exe. Every client that auto-updates would
have downloaded the wrong installer — and the hash would have matched
it, so a client-side integrity check would not have caught it either.
"""

import pytest

OIK = "OIK_Setup.exe"
FORMALIZATOR = "Formalizator_Setup.exe"


@pytest.fixture
def releases_dir(tmp_path, monkeypatch):
    d = tmp_path / "releases"
    d.mkdir()
    monkeypatch.setenv("RELEASES_DIR", str(d))
    return d


@pytest.fixture
def admin_headers(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "test-admin-token")
    return {"Authorization": "Bearer test-admin-token"}


def _upload(client, headers, tag, filename, payload=b"MZ installer"):
    return client.post(
        f"/admin/releases/{tag}/upload",
        headers=headers,
        files={"file": (filename, payload, "application/octet-stream")},
    )


# ── Storage is keyed on (tag, filename) ──────────────────────────────


def test_both_installers_coexist_under_one_tag(api_client, releases_dir, admin_headers):
    _upload(api_client, admin_headers, "v1.0.0", OIK, b"OIK BINARY")
    _upload(api_client, admin_headers, "v1.0.0", FORMALIZATOR, b"FORMALIZATOR BINARY")

    assert (releases_dir / "v1.0.0" / OIK).read_bytes() == b"OIK BINARY"
    assert (releases_dir / "v1.0.0" / FORMALIZATOR).read_bytes() == b"FORMALIZATOR BINARY"


def test_the_companion_upload_does_not_overwrite_the_oik_installer(
    api_client, releases_dir, admin_headers,
):
    """The regression that would have shipped the wrong binary to every
    auto-updating client."""
    _upload(api_client, admin_headers, "v1.0.0", OIK, b"OIK BINARY")

    _upload(api_client, admin_headers, "v1.0.0", FORMALIZATOR, b"FORMALIZATOR BINARY")

    assert (releases_dir / "v1.0.0" / OIK).read_bytes() == b"OIK BINARY"


def test_only_the_oik_upload_updates_the_update_manifest(
    api_client, releases_dir, admin_headers,
):
    """latest_release.json describes what OIK's own updater fetches. If a
    companion upload rewrote it, the sha256 would describe the companion
    while download_url still said OIK_Setup.exe."""
    _upload(api_client, admin_headers, "v1.0.0", OIK, b"OIK BINARY")
    before = (releases_dir / "latest_release.json").read_text(encoding="utf-8")

    _upload(api_client, admin_headers, "v1.0.0", FORMALIZATOR, b"FORMALIZATOR BINARY")

    assert (releases_dir / "latest_release.json").read_text(encoding="utf-8") == before


def test_the_manifest_hash_describes_the_file_it_advertises(
    api_client, releases_dir, admin_headers,
):
    import hashlib
    import json

    _upload(api_client, admin_headers, "v1.0.0", OIK, b"OIK BINARY")
    _upload(api_client, admin_headers, "v1.0.0", FORMALIZATOR, b"FORMALIZATOR BINARY")

    meta = json.loads((releases_dir / "latest_release.json").read_text(encoding="utf-8"))
    served = (releases_dir / "v1.0.0" / OIK).read_bytes()

    assert meta["download_url"].endswith(OIK)
    assert meta["sha256"] == hashlib.sha256(served).hexdigest()


def test_an_unknown_filename_is_refused(api_client, releases_dir, admin_headers):
    r = _upload(api_client, admin_headers, "v1.0.0", "totally_other.exe")

    assert r.status_code == 400
    assert not (releases_dir / "v1.0.0").exists()


def test_a_traversing_filename_cannot_escape_the_tag_directory(
    api_client, releases_dir, admin_headers,
):
    r = _upload(api_client, admin_headers, "v1.0.0", "../../evil.exe")

    assert r.status_code == 400
    assert not (releases_dir.parent / "evil.exe").exists()


def test_upload_still_requires_the_admin_token(api_client, releases_dir, admin_headers):
    # admin_headers is requested for its side effect of configuring
    # ADMIN_TOKEN — without it the server answers 503 "not configured",
    # which would pass a naive `!= 200` check while proving nothing.
    r = _upload(api_client, {"Authorization": "Bearer wrong"}, "v1.0.0", OIK)

    assert r.status_code == 401
    assert not (releases_dir / "v1.0.0").exists()


# ── Download ─────────────────────────────────────────────────────────


def test_each_installer_is_served_from_its_tag(api_client, releases_dir, admin_headers):
    _upload(api_client, admin_headers, "v1.0.0", OIK, b"OIK BINARY")
    _upload(api_client, admin_headers, "v1.0.0", FORMALIZATOR, b"FORMALIZATOR BINARY")

    assert api_client.get(f"/downloads/v1.0.0/{OIK}").content == b"OIK BINARY"
    assert api_client.get(f"/downloads/v1.0.0/{FORMALIZATOR}").content == b"FORMALIZATOR BINARY"


def test_the_stable_latest_link_works(api_client, releases_dir, admin_headers):
    """It existed but had never worked: /downloads/{tag}/... was declared
    first, so "latest" was matched as a tag and looked for a release
    directory of that name. Support hands this link out, so it must not
    change between releases."""
    _upload(api_client, admin_headers, "v1.0.0", OIK, b"OIK BINARY")

    r = api_client.get(f"/downloads/latest/{OIK}")

    assert r.status_code == 200
    assert r.content == b"OIK BINARY"


def test_the_stable_latest_link_follows_new_releases(
    api_client, releases_dir, admin_headers,
):
    _upload(api_client, admin_headers, "v1.0.0", OIK, b"OLD")
    _upload(api_client, admin_headers, "v1.1.0", OIK, b"NEW")

    assert api_client.get(f"/downloads/latest/{OIK}").content == b"NEW"


def test_the_stable_latest_link_serves_the_companion_too(
    api_client, releases_dir, admin_headers,
):
    _upload(api_client, admin_headers, "v1.0.0", OIK, b"OIK BINARY")
    _upload(api_client, admin_headers, "v1.0.0", FORMALIZATOR, b"FORMALIZATOR BINARY")

    r = api_client.get(f"/downloads/latest/{FORMALIZATOR}")

    assert r.status_code == 200
    assert r.content == b"FORMALIZATOR BINARY"


def test_an_unknown_download_filename_is_not_found(api_client, releases_dir, admin_headers):
    _upload(api_client, admin_headers, "v1.0.0", OIK)

    assert api_client.get("/downloads/v1.0.0/passwords.txt").status_code == 404


def test_latest_json_is_untouched_by_the_new_routes(api_client, releases_dir, admin_headers):
    """The manifest shape is the client contract — biracki-odbor's
    fetch_release_manifest() and check-update both read it."""
    _upload(api_client, admin_headers, "v1.0.0", OIK)

    body = api_client.get("/downloads/latest.json").json()

    assert body["tag"] == "v1.0.0"
    assert set(body) == {"tag", "sha256", "size_bytes", "uploaded_at", "download_url"}


# ── Retention ────────────────────────────────────────────────────────


def test_pruning_keeps_both_files_of_a_retained_tag(
    api_client, releases_dir, admin_headers,
):
    """Pruning removes whole tag directories, so a paired upload must not
    be able to lose half of itself."""
    _upload(api_client, admin_headers, "v1.0.0", OIK)
    _upload(api_client, admin_headers, "v1.0.0", FORMALIZATOR)

    assert (releases_dir / "v1.0.0" / OIK).exists()
    assert (releases_dir / "v1.0.0" / FORMALIZATOR).exists()


def test_pruning_still_caps_the_number_of_tags(api_client, releases_dir, admin_headers):
    for tag in ("v1.0.0", "v1.1.0", "v1.2.0"):
        _upload(api_client, admin_headers, tag, OIK)

    kept = sorted(d.name for d in releases_dir.iterdir() if d.is_dir())

    assert kept == ["v1.1.0", "v1.2.0"]
