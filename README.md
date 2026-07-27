# Excel Tracking Number Matcher

Upload a list of tracking numbers and a main Excel workbook. The app finds
every row in the main workbook whose tracking number matches one from the
list, highlights that entire row red, and gives you a new workbook to
download — the original upload is never modified.

Sample input/output files: [`samples/`](samples/).

## Requirements

- Python 3.11+

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Run (development)

```bash
python3 run.py
```

Visit http://127.0.0.1:5000. This uses Flask's built-in dev server —
fine for local testing, not for real traffic (see Deployment below).

## Configuration

All settings are read from environment variables (`.env`, see
`.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | random per process if unset | Signs the session cookie. **Set an explicit value in production** — see the note in Deployment. |
| `MAX_CONTENT_LENGTH_MB` | 20 | Max upload size per file. |
| `UPLOAD_FOLDER` | `temp_uploads` | Where uploaded/processed files are stored temporarily. |
| `FILE_RETENTION_MINUTES` | 30 | How long an idle session's files are kept before automatic cleanup deletes them. |

## Running tests

```bash
source .venv/bin/activate
python3 -m pytest -v
```

Tests cover tracking-number normalization (leading zeros, case, numeric
values), deduplication, exact matching, row highlighting, formula/merged-cell
preservation, file validation (corrupted/password-protected/oversized
files), the full upload → process → download → reset flow, and automatic
temp-file cleanup.

## Project structure

```
app/
  __init__.py            Flask app factory, error handlers
  config.py               Config from environment variables
  routes.py                /, /upload, /worksheet-columns, /process, /download, /reset
  errors.py                FileValidationError
  services/
    excel_inspector.py     Worksheet/header/column detection
    upload_service.py      Save + validate uploads, session isolation, cleanup
    matching_engine.py      Normalization, matching, highlighting
    processing_service.py   Orchestrates matching engine, builds output files
    download_store.py       Token -> file path mapping for secure downloads
  static/, templates/       Frontend (vanilla HTML/CSS/JS)
tests/                      pytest suite
samples/                     Sample input/output Excel files
deploy/                      Gunicorn/Nginx/systemd examples for production
```

## Deployment

Recommended production stack: Gunicorn behind Nginx, HTTPS terminated at
Nginx.

1. On the server: clone the repo, create `.venv`, `pip install -r
   requirements.txt`, and create a real `.env` (**do not reuse
   `.env.example`'s placeholder `SECRET_KEY`**).
2. Start the app with [`deploy/gunicorn_start.sh`](deploy/gunicorn_start.sh)
   (or wire it up as a systemd service — see
   [`deploy/tracking-number.service.example`](deploy/tracking-number.service.example)).
3. Reverse-proxy it with Nginx — see
   [`deploy/nginx.conf.example`](deploy/nginx.conf.example) — and put a real
   TLS certificate in front of it (e.g. via certbot).

**Important — single worker only.** Upload/download session state currently
lives in an in-memory dict per process (`app/services/upload_service.py`,
`app/services/download_store.py`), so `gunicorn_start.sh` runs exactly one
worker (with threads for concurrency within that worker). Don't raise
`--workers` without first moving that state into a shared store (Redis, a
database, or similar) — otherwise a request can land on a worker that never
saw the matching upload.

A Docker setup isn't included; it's straightforward to add later (base
image + `pip install -r requirements.txt` + `CMD` running
`deploy/gunicorn_start.sh`) if you need containerized deployment.
