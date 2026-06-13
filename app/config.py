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
