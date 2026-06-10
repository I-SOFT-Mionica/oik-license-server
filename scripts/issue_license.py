#!/usr/bin/env python3
"""CLI admin tool — issue a new license row and print the license code.

Usage (inside the container):
    podman compose exec license-server python scripts/issue_license.py \\
        --issued-to "Општина Уб" \\
        --updates-until 2027-06-10

Usage (against a volume directly):
    podman run --rm \\
        -v oik-license-server_license-data:/data \\
        oik-license-server:latest \\
        python scripts/issue_license.py --issued-to "Општина Уб" --updates-until 2027-06-10
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _generate_code() -> str:
    """XXXX-XXXX-XXXX-XXXX — 4 groups of 4 uppercase hex chars."""
    return "-".join(secrets.token_hex(2).upper() for _ in range(4))


def main() -> None:
    parser = argparse.ArgumentParser(description="Issue a new OIK license")
    parser.add_argument("--issued-to", required=True, help="Municipality or client name")
    parser.add_argument(
        "--updates-until",
        required=True,
        help="ISO date until which updates are valid, e.g. 2027-06-10",
    )
    parser.add_argument(
        "--modules",
        default='["full"]',
        help='JSON array of module names (default: ["full"])',
    )
    parser.add_argument(
        "--db",
        default=os.environ.get("DB_PATH", "/data/licenses.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()

    try:
        modules = json.loads(args.modules)
        if not isinstance(modules, list):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        print(f"ERROR: --modules must be a JSON array, got: {args.modules}", file=sys.stderr)
        sys.exit(1)

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: database not found at {db_path}", file=sys.stderr)
        print("Start the server first so it initialises the DB, then re-run.", file=sys.stderr)
        sys.exit(1)

    license_id = str(uuid.uuid4())
    license_code = _generate_code()
    now = datetime.now(timezone.utc).isoformat()

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO licenses
              (id, license_code, issued_to, updates_until, modules, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (license_id, license_code, args.issued_to, args.updates_until,
             json.dumps(modules), now),
        )
        conn.commit()
    finally:
        conn.close()

    print()
    print("License issued successfully.")
    print(f"  Code:          {license_code}")
    print(f"  Issued to:     {args.issued_to}")
    print(f"  Updates until: {args.updates_until}")
    print(f"  Modules:       {args.modules}")
    print(f"  ID (internal): {license_id}")
    print()
    print("Give the operator the Code above — they enter it in the OIK activation dialog.")


if __name__ == "__main__":
    main()
