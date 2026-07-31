# Excel Tracking Number Matcher

Paste a link to a tracking-number Google Sheet and a main Google Sheet.
The app finds every row in the main sheet whose tracking number matches
one from the list and highlights that entire row red — **directly in your
live main sheet**. There's no upload, no sign-in, and no separate output
file to download; the sheet itself is the result.

## Requirements

- Python 3.11+
- A Google Cloud service account (see setup below)

## Google Cloud setup (required before the app can access any Sheet)

You need to do this once. There's no per-user sign-in — a **service
account** is a fixed, permanent Google identity the app uses for every
request, and you grant it access by sharing each Sheet with it (like
sharing with a coworker).

1. Go to [Google Cloud Console](https://console.cloud.google.com/) and
   create a new project (or use an existing one).
2. **APIs & Services → Library** → search "Google Sheets API" → Enable.
3. **IAM & Admin → Service Accounts → Create Service Account**. Give it
   any name (e.g. `sheet-matcher-bot`). No project-level roles are
   needed — access is controlled entirely by what you share with it.
4. Open the new service account → **Keys** tab → **Add Key → Create new
   key → JSON**. This downloads a `.json` credentials file — treat it
   like a password: never commit it to git, never share it.
5. Move that downloaded file into the project root as `service_account.json`
   (or point `GOOGLE_SERVICE_ACCOUNT_FILE` in `.env` at wherever you keep it).
6. Note the service account's **email address** — shown on its details
   page and inside the JSON file as `client_email`, looks like
   `sheet-matcher-bot@your-project-id.iam.gserviceaccount.com`. The
   running app also displays this email at the top of the page once
   configured.
7. **For every Google Sheet you want to process**: open it → **Share** →
   paste the service account's email → give it **Editor** access → Share.
   This is the only "connect" step, ever — no login screen, no consent
   prompt.

**Note on access:** because there's no per-user login, the app can't tell
who's using it — anyone who can reach the app and knows a sheet's link can
process any sheet that's been shared with the service account. Fine for
personal/internal use; don't expose the app publicly without adding your
own access control on top, and never commit `service_account.json`.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# then place your downloaded service_account.json in the project root
# (or set GOOGLE_SERVICE_ACCOUNT_FILE in .env to its path)
```

## Run (development)

```bash
python3 run.py
```

Visit http://127.0.0.1:5000 — it displays the service account's email at
the top; share your two Google Sheets with that email, then paste both
links in. This uses Flask's built-in dev server — fine for local testing,
not for real traffic (see Deployment below).

## Configuration

All settings are read from environment variables (`.env`, see
`.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | random per process if unset | Signs the session cookie. **Set an explicit value in production** — see the note in Deployment. |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | `service_account.json` | Path to the service account JSON key file (see setup above). Required for any Sheets access to work. |
| `MAX_CONTENT_LENGTH_MB` | 20 | Max request body size. |
| `UPLOAD_FOLDER` | `temp_uploads` | Where the generated unmatched-tracking-numbers file is stored temporarily. |
| `FILE_RETENTION_MINUTES` | 30 | How long an idle session's files are kept before automatic cleanup deletes them. |

## Running tests

```bash
source .venv/bin/activate
python3 -m pytest -v
```

The suite runs entirely without a real service account — the Google
Sheets API calls are mocked. Tests cover tracking-number normalization
(leading zeros, case, numeric values), deduplication, exact matching,
which rows get highlighted, the connect → process → download → reset
flow, and route-level error handling (missing credentials, bad links,
missing selections).

Manually verifying the real live-sheet-editing flow (which can't be
automated without a real service account) requires the Google Cloud setup
above — then: share two real Sheets with the service account email, paste
both links in the running app, process, and confirm the actual Google
Sheet (not a downloaded copy) shows the highlighted rows.

## Project structure

```
app/
  __init__.py                  Flask app factory, error handlers
  config.py                    Config from environment variables
  routes.py                    /, /service-account-email, /connect-sheets,
                                /worksheet-columns, /sheets-status, /process,
                                /download-unmatched, /reset
  errors.py                    FileValidationError
  services/
    session_utils.py           Per-browser-session id helper
    google_auth_service.py     Loads/caches the service account credentials
    google_sheets_service.py   Sheets API wrapper: list tabs, read values, highlight rows
    column_utils.py            Header-candidate detection (shared, data-source agnostic)
    matching_engine.py         Normalization, matching (plain list[list] in, row numbers out)
    sheets_processing_service.py  Orchestrates the above; connected-sheets session store
    download_store.py          Token -> file path mapping for secure downloads
  static/, templates/          Frontend (vanilla HTML/CSS/JS)
tests/                         pytest suite (Google API fully mocked)
deploy/                        Gunicorn/Nginx/systemd examples for production
```

## Deployment

Recommended production stack: Gunicorn behind Nginx, HTTPS terminated at
Nginx.

1. On the server: clone the repo, create `.venv`, `pip install -r
   requirements.txt`, create a real `.env` (**do not reuse
   `.env.example`'s placeholder `SECRET_KEY`**), and place a real
   `service_account.json` there too (never commit it — copy it to the
   server directly, e.g. via `scp`).
2. Start the app with [`deploy/gunicorn_start.sh`](deploy/gunicorn_start.sh)
   (or wire it up as a systemd service — see
   [`deploy/tracking-number.service.example`](deploy/tracking-number.service.example)).
3. Reverse-proxy it with Nginx — see
   [`deploy/nginx.conf.example`](deploy/nginx.conf.example) — and put a real
   TLS certificate in front of it (e.g. via certbot).

**Important — single worker only.** Session state (connected sheets, last
result) currently lives in in-memory dicts per process
(`app/services/sheets_processing_service.py`,
`app/services/download_store.py`), so `gunicorn_start.sh` runs exactly one
worker (with threads for concurrency within that worker). Don't raise
`--workers` without first moving that state into a shared store (Redis, a
database, or similar) — otherwise a request can land on a worker that
never saw the matching session. (The service account credentials
themselves are cached per-process and are fine either way, since they're
not session-specific.)

A Docker setup isn't included; it's straightforward to add later (base
image + `pip install -r requirements.txt` + `CMD` running
`deploy/gunicorn_start.sh`) if you need containerized deployment.
