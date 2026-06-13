# oik-license-server — Claude Code Instructions

License server for OIK (Образац Изборне Комисије).
Runs at https://api.isoft.rs as a rootless podman container on `waterworks`.

## Quick orientation

```
app/
  main.py            — FastAPI app, /healthz, /downloads/* endpoints
  config.py          — all env vars with defaults
  database.py        — SQLite init, get_conn()
  jwt_utils.py       — sign_token(), verify_token()
  schemas.py         — Pydantic models
  routes/
    activate.py      — POST /api/v1/biracki/activate
    check_update.py  — POST /api/v1/biracki/check-update
    admin.py         — /admin/* (all protected by ADMIN_TOKEN)
  static/
    admin.html       — single-file admin web UI
```

## Deploy

Every push to `main` auto-deploys via `POST /admin/deploy` (webhook).
The GitHub Actions workflow in `.github/workflows/deploy.yml` calls this endpoint.

**Confirm deploy:**
```bash
curl https://api.isoft.rs/healthz
# {"status":"ok","started_at":"...","git":"<sha>"}
```

**Manual deploy (if webhook is broken):**
```bash
ssh velimir@api.isoft.rs
cd /home/velimir/oik-license-server
git pull origin main
podman compose up -d --build
```

## Environment / secrets

The deploy workflow writes `.env` from GitHub Secrets on every deploy.
**Do not edit `.env` manually** — change the GitHub Secret and redeploy.

GitHub Secrets in this repo:
- `ADMIN_TOKEN` — admin UI + all `/admin/*` routes + deploy webhook
- `JWT_SECRET` — signs license JWTs (min 32 chars, required)
- `SERVER_BASE_URL` — `https://api.isoft.rs`
- `GITHUB_TOKEN` — optional GitHub PAT for check-update fallback

## Data volume

Named podman volume `license-data` mounted at `/data/`:
- `/data/licenses.db` — SQLite database
- `/data/releases/` — uploaded installers
- `/data/releases/latest_release.json` — metadata for check-update

## Common operations

**Issue a license:** https://api.isoft.rs/admin/ (browser, password = ADMIN_TOKEN)

**Check what's deployed:**
```bash
curl https://api.isoft.rs/healthz
```

**See latest uploaded installer:**
```bash
curl https://api.isoft.rs/downloads/latest.json
```

**Manually upload an installer:**
```bash
curl -X POST https://api.isoft.rs/admin/releases/v0.33.0/upload \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -F "file=@OIK_Setup.exe"
```

## Debugging 502

FastAPI isn't running. Check logs:
```bash
podman logs oik-license-server_license-server_1 2>&1 | tail -40
```

If stale container state: delete the container (not the volume) and rerun
`podman compose up -d`. The `license-data` volume persists the database.

## Client contract (do not change without updating biracki-odbor)

See `CLAUDE.md` in the `biracki-odbor` repo for the full JWT schema and
API contract. Tests in `biracki-odbor/tests/test_licensing.py` define the
expected behaviour of both endpoints.
