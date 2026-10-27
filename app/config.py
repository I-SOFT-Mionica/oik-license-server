import os


def jwt_secret() -> str:
    val = os.environ.get("JWT_SECRET", "").strip()
    if not val:
        raise RuntimeError("Required env var JWT_SECRET is not set")
    return val


def jwt_signing_key() -> str:
    """Ed25519 private key for licence tokens: base64 of the raw 32-byte
    seed (one line, so it fits an env file). Empty => tokens stay HS256.
    The matching public key is embedded in the desktop app."""
    return os.environ.get("JWT_SIGNING_KEY", "").strip()


def db_path() -> str:
    return os.environ.get("DB_PATH", "/data/licenses.db")


def github_repo() -> str:
    return os.environ.get("GITHUB_REPO", "I-SOFT-Mionica/biracki-odbor")


def github_token() -> str | None:
    return os.environ.get("GITHUB_TOKEN") or None


def admin_token() -> str | None:
    return os.environ.get("ADMIN_TOKEN", "").strip() or None


def changelog_token() -> str | None:
    """Separate, narrowly-scoped credential for POST /admin/changelog.

    Deliberately NOT the same secret as ADMIN_TOKEN: that token also
    gates issuing/revoking real licenses and uploading the installer
    executable users download. Changelog content is public marketing
    text (the GET side has no auth at all) — a leaked or delegated
    CHANGELOG_TOKEN can only ever post/correct "what's new" copy,
    never touch licensing or the shipped binary.
    """
    return os.environ.get("CHANGELOG_TOKEN", "").strip() or None


# Installers this server will accept and serve, by exact filename.
#
# A whitelist rather than an open path: both the upload destination and the
# download route take a caller-supplied segment, and the files involved are
# executables handed to municipal machines that run them. Anything not named
# here is rejected outright, which also disposes of path traversal without
# relying on separate sanitising.
#
# One release tag holds several products — OIK and its Formalizator companion
# are built from the same tag in biracki-odbor and published side by side.
OIK_INSTALLER = "OIK_Setup.exe"
FORMALIZATOR_INSTALLER = "Formalizator_Setup.exe"
# Signed by the release build (key only in GitHub CI); the desktop app
# refuses any installer that doesn't match it. Stored and served like an
# installer, but never touches latest_release.json.
RELEASE_MANIFEST = "release-manifest.json"
INSTALLER_FILENAMES = frozenset({OIK_INSTALLER, FORMALIZATOR_INSTALLER, RELEASE_MANIFEST})


def releases_dir() -> str:
    """Directory where uploaded installer binaries are stored in the data volume."""
    return os.environ.get("RELEASES_DIR", "/data/releases")


def server_base_url() -> str:
    """Public base URL of this server — used to build download URLs in check-update."""
    return os.environ.get("SERVER_BASE_URL", "https://api.isoft.rs").rstrip("/")


def changelog_path() -> str:
    """Flat JSON file for the in-app "what's new" changelog — mirrors
    latest_release.json's storage pattern (durable volume, no DB table)."""
    return os.environ.get("CHANGELOG_PATH", "/data/changelog.json")
