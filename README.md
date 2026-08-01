# Excel Tracking Number Matcher

Sign in with Google, pick a Google Sheet, and choose which tab holds your
tracking numbers and which tab is the main data. The app finds every row
in the main tab whose tracking number matches one from the list and
highlights that entire row red — **directly in your live Google Sheet**.
There's no file upload and no separate output file to download; the sheet
itself is the result.

## Requirements

- Python 3.11+
- A Google Cloud OAuth client + API key (see setup below)

## Google Cloud setup (required before sign-in/Picker will work)

You need to do this once, in your own Google account.

1. Go to [Google Cloud Console](https://console.cloud.google.com/) and
   create a new project (or use an existing one).
2. **APIs & Services → Library** → enable both:
   - **Google Sheets API**
   - **Google Picker API**
3. **APIs & Services → OAuth consent screen**:
   - User type: External (or Internal if you have a Google Workspace).
   - Publishing status: leave it in **Testing**.
   - Under "Test users", add your own Google account's email — only
     accounts listed here can sign in while the app is unverified.
4. **APIs & Services → Credentials → Create Credentials → OAuth client ID**:
   - Application type: **Web application**.
   - Authorized redirect URI: `http://127.0.0.1:5000/google/callback`
     (add your real production URL here too later).
   - Copy the generated **Client ID** and **Client Secret**.
5. **APIs & Services → Credentials → Create Credentials → API key**:
   - This is a separate credential from the OAuth client, used only by
     the Google Picker widget in the browser (not a secret in the same
     sense as the Client Secret — it's designed to be sent to frontend JS).
   - Optionally restrict it to the Picker API for tidiness.
6. Put all three values into `.env` (see Local setup below): `GOOGLE_CLIENT_ID`,
   `GOOGLE_CLIENT_SECRET`, `GOOGLE_API_KEY`.

**Note on scope:** this app requests the `drive.file` scope, which only
grants access to files the signed-in user explicitly picks via Google
Picker (not their whole Drive). This is deliberately narrower than the
`spreadsheets` scope so it avoids Google's stricter sensitive-scope
verification requirements — fine for personal use or a handful of test
users in Testing mode; a public rollout to arbitrary users would still
need Google's OAuth verification review.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# then edit .env and fill in GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_API_KEY
```

## Run (development)

```bash
python3 run.py
```

Visit http://127.0.0.1:5000, click "Continue with Google", pick a Sheet
via the picker, then choose the tracking-number tab and the main tab. This
uses Flask's built-in dev server — fine for local testing, not for real
traffic (see Deployment below).

## Configuration

All settings are read from environment variables (`.env`, see
`.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | random per process if unset | Signs the session cookie. **Set an explicit value in production** — see the note in Deployment. |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | — | From Google Cloud Console (see setup above). Required for sign-in to work at all. |
| `GOOGLE_REDIRECT_URI` | `http://127.0.0.1:5000/google/callback` | Must exactly match a redirect URI registered on the OAuth client. |
| `GOOGLE_API_KEY` | — | Used by the Google Picker widget in the browser. Not secret in the same sense as the client secret. |
| `MAX_CONTENT_LENGTH_MB` | 20 | Max request body size. |
| `UPLOAD_FOLDER` | `temp_uploads` | Where the generated unmatched-tracking-numbers file is stored temporarily. |
| `FILE_RETENTION_MINUTES` | 30 | How long an idle session's files are kept before automatic cleanup deletes them. |

## Running tests

```bash
source .venv/bin/activate
python3 -m pytest -v
```

The suite runs entirely without real Google credentials — OAuth and the
Google Sheets API are both mocked. Tests cover tracking-number
normalization (leading zeros, case, numeric values), deduplication, exact
matching, which rows get highlighted, the connect → process → download →
reset flow, and route-level error handling (not signed in, bad links,
missing selections).

Manually verifying the real sign-in + Picker + live-sheet-editing flow
(which can't be automated without real Google credentials) requires the
Google Cloud setup above — then: sign in, pick a real Sheet with two tabs
(one tracking-number list, one main data set with a couple of matching
rows), process, and confirm the actual Google Sheet (not a downloaded
copy) shows the highlighted rows.

## Project structure

```
app/
  __init__.py                  Flask app factory, error handlers, oauthlib env setup
  config.py                    Config from environment variables
  routes.py                    /, /google/login, /google/callback, /google/logout,
                                /auth-status, /picker-token, /connect-sheet,
                                /worksheet-columns, /sheets-status, /process,
                                /download-unmatched, /reset
  errors.py                    FileValidationError
  services/
    session_utils.py           Per-browser-session id helper
    google_auth_service.py     OAuth flow, credential storage/refresh, Picker token
    google_sheets_service.py   Sheets API wrapper: list tabs, read values, highlight rows
    column_utils.py            Header-candidate detection (shared, data-source agnostic)
    matching_engine.py         Normalization, matching (plain list[list] in, row numbers out)
    sheets_processing_service.py  Orchestrates the above; connected-sheet session store
    download_store.py          Token -> file path mapping for secure downloads
  static/, templates/          Frontend (vanilla HTML/CSS/JS + Google Picker)
tests/                         pytest suite (Google API + OAuth fully mocked)
deploy/                        Gunicorn/Nginx/systemd examples for production
```

## Deployment

Recommended production stack: Gunicorn behind Nginx, HTTPS terminated at
Nginx.

1. On the server: clone the repo, create `.venv`, `pip install -r
   requirements.txt`, and create a real `.env` (**do not reuse
   `.env.example`'s placeholder `SECRET_KEY`**, and register your
   production URL's `/google/callback` as an additional redirect URI on
   the OAuth client in Google Cloud Console).
2. Start the app with [`deploy/gunicorn_start.sh`](deploy/gunicorn_start.sh)
   (or wire it up as a systemd service — see
   [`deploy/tracking-number.service.example`](deploy/tracking-number.service.example)).
3. Reverse-proxy it with Nginx — see
   [`deploy/nginx.conf.example`](deploy/nginx.conf.example) — and put a real
   TLS certificate in front of it (e.g. via certbot). OAuth requires real
   HTTPS in production; the `OAUTHLIB_INSECURE_TRANSPORT` relaxation in
   `app/__init__.py` only activates when `FLASK_ENV=development`.

**Important — single worker only.** Session state (OAuth credentials,
connected sheet, last result) currently lives in in-memory dicts per
process (`app/services/google_auth_service.py`,
`app/services/sheets_processing_service.py`,
`app/services/download_store.py`), so `gunicorn_start.sh` runs exactly one
worker (with threads for concurrency within that worker). Don't raise
`--workers` without first moving that state into a shared store (Redis, a
database, or similar) — otherwise a request can land on a worker that
never saw the matching session.

**On multi-user access:** since each user authenticates with their own
Google account (rather than a shared service account), one user's session
can only ever touch sheets they personally have access to — there's no
shared-credential/shared-quota risk between users, unlike a single fixed
service account would have.

A Docker setup isn't included; it's straightforward to add later (base
image + `pip install -r requirements.txt` + `CMD` running
`deploy/gunicorn_start.sh`) if you need containerized deployment.
