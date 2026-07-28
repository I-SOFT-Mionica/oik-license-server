import os


def jwt_secret() -> str:
    val = os.environ.get("JWT_SECRET", "").strip()
    if not val:
        raise RuntimeError("Required env var JWT_SECRET is not set")
    return val


def db_path() -> str:
    return os.environ.get("DB_PATH", "/data/licenses.db")


def github_repo() -> str:
    return os.environ.get("GITHUB_REPO", "I-SOFT-Mionica/biracki-odbor")


def github_token() -> str | None:
    return os.environ.get("GITHUB_TOKEN") or None


def admin_token() -> str | None:
    return os.environ.get("ADMIN_TOKEN", "").strip() or None


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
