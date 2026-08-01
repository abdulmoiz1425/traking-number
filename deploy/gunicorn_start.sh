#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate

# --workers 1 is required, not a tuning choice: session state (OAuth
# credentials, connected sheet, download tokens) lives in in-memory dicts
# per process (see app/services/google_auth_service.py,
# app/services/sheets_processing_service.py, app/services/download_store.py).
# Multiple workers would each have their own copy, so a request could land
# on a worker that never saw the matching session (e.g. a signed-in user
# suddenly looking signed out).
# --threads lets one worker still handle concurrent requests.
# To scale beyond one process, move that state into a shared store (e.g.
# Redis or a database) first, then raise --workers.
exec gunicorn run:app \
  --bind 127.0.0.1:8000 \
  --workers 1 \
  --threads 4 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile -
