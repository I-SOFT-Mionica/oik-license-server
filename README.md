# OIK License Server

FastAPI + SQLite backend for §3 Лиценцирање of the Biracki Odbor application.

Two endpoints:
- `POST /api/v1/biracki/activate` — bind a license code to a machine
- `POST /api/v1/biracki/check-update` — verify update entitlement + return latest release

---

## Prerequisites

On the server that will host this (any Linux VPS/server):

| Requirement | Check | Install |
|---|---|---|
| Podman ≥ 4.x | `podman --version` | `dnf install podman` / `apt install podman` |
| podman-compose | `podman compose version` | `pip install podman-compose` or Podman Desktop |
| Python 3.12+ | `python3 --version` | only needed to run tests locally |
| Caddy or nginx | for HTTPS termination | see [Reverse proxy](#reverse-proxy-https) |

> **Podman compose note**: Modern Podman (≥ 4.7) ships `podman compose` as a built-in
> sub-command. Older versions need `pip install podman-compose` separately.

---

## 1. Get the code on the server

```bash
git clone https://github.com/I-SOFT-Mionica/oik-license-server.git
cd oik-license-server
```

---

## 2. Generate a strong JWT secret

The secret must be at least 32 characters. Keep it — if you lose it, all issued
tokens become invalid and every customer needs to re-activate.

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
# example output: 4a7f2c1e9b3d8f0a6e5c2b4d1f3a8e7c9b0d2f4a6e8c0b2d4f6a8e0c2b4d6f8a
```

---

## 3. Create `.env`

```bash
cp .env.example .env
```

Edit `.env` and fill in `JWT_SECRET` with the value from step 2.
`GITHUB_TOKEN` is optional but recommended to avoid GitHub API rate limits.

---

## 4. Build and start

```bash
podman compose up -d --build
```

Verify it started:

```bash
curl http://localhost:8000/healthz
# {"status":"ok"}
```

The SQLite database is created automatically at first start in a named volume
(`oik-license-server_license-data`). It persists across container restarts and
image rebuilds.

---

## 5. Reverse proxy + HTTPS

The container binds to `127.0.0.1:8000` only. You need a reverse proxy to
expose it over HTTPS at `api.isoft.rs`.

### Caddy (recommended — automatic HTTPS)

```
# /etc/caddy/Caddyfile
api.isoft.rs {
    reverse_proxy localhost:8000
}
```

```bash
systemctl reload caddy
```

### nginx

```nginx
# /etc/nginx/sites-available/api.isoft.rs
server {
    listen 443 ssl;
    server_name api.isoft.rs;

    ssl_certificate     /etc/letsencrypt/live/api.isoft.rs/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.isoft.rs/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
certbot --nginx -d api.isoft.rs
systemctl reload nginx
```

Verify end-to-end:

```bash
curl https://api.isoft.rs/healthz
# {"status":"ok"}
```

---

## 6. Make the container start on boot

```bash
# Generate a systemd unit from the running container
podman generate systemd --new --name oik-license-server_license-server_1 \
    > ~/.config/systemd/user/oik-license-server.service

systemctl --user daemon-reload
systemctl --user enable --now oik-license-server
loginctl enable-linger $USER     # keep service running after SSH logout
```

---

## 7. Issue your first license

```bash
podman compose exec license-server python scripts/issue_license.py \
    --issued-to "Општина Уб" \
    --updates-until 2027-06-10
```

Output:

```
License issued successfully.
  Code:          3A1F-C2E9-B4D7-F0A8
  Issued to:     Општина Уб
  Updates until: 2027-06-10
  Modules:       ["full"]
  ID (internal): e3b0c442-...
```

Hand the **Code** to the operator. They enter it in OIK → About → Activate license.

---

## 8. Configure the OIK client

In the Biracki Odbor GitHub repo, go to **Settings → Secrets → Actions** and add:

| Secret | Value |
|---|---|
| `LICENSING_SERVER_URL` | `https://api.isoft.rs` |

The next release build will bake that URL into `OIK_Setup.exe` automatically.
Installed clients will call `https://api.isoft.rs/api/v1/biracki/activate` and
`https://api.isoft.rs/api/v1/biracki/check-update`.

---

## Running tests locally

```bash
python3 -m venv .venv
source .venv/bin/activate          # Linux/macOS
# .venv\Scripts\activate           # Windows

pip install -r requirements-dev.txt
pytest -v
```

Expected: all tests pass without a running server (tests use an in-memory test
client and a temp SQLite file).

---

## Admin operations

### Revoke a license (e.g. non-payment)

```bash
podman compose exec license-server python3 - <<'EOF'
import sqlite3, sys
conn = sqlite3.connect("/data/licenses.db")
conn.execute("UPDATE licenses SET revoked=1 WHERE license_code=?", (sys.argv[1],))
conn.commit()
print("revoked")
EOF 3A1F-C2E9-B4D7-F0A8
```

### Clear a machine binding (operator moved to a new PC)

```bash
podman compose exec license-server python3 - <<'EOF'
import sqlite3, sys
conn = sqlite3.connect("/data/licenses.db")
conn.execute("UPDATE licenses SET hid=NULL WHERE license_code=?", (sys.argv[1],))
conn.commit()
print("hid cleared — operator can re-activate on the new machine")
EOF 3A1F-C2E9-B4D7-F0A8
```

### Backup the database

```bash
podman compose exec license-server \
    sqlite3 /data/licenses.db ".backup /data/licenses.backup.db"
podman cp oik-license-server_license-server_1:/data/licenses.backup.db ./
```

### Upgrade the server

```bash
git pull
podman compose up -d --build
```

The named volume is unchanged — no data loss.

---

## Environment variables reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `JWT_SECRET` | yes | — | HS256 signing secret, min 32 chars |
| `DB_PATH` | no | `/data/licenses.db` | SQLite file path |
| `GITHUB_REPO` | no | `I-SOFT-Mionica/biracki-odbor` | Repo to query for latest release |
| `GITHUB_TOKEN` | no | — | GitHub PAT for higher API rate limit |
