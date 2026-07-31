import os
import secrets

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Still used for the one remaining local file: the unmatched-tracking-
    # numbers .xlsx download generated after processing.
    UPLOAD_FOLDER = os.path.join(BASE_DIR, os.environ.get("UPLOAD_FOLDER", "temp_uploads"))
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH_MB", 20)) * 1024 * 1024
    FILE_RETENTION_MINUTES = int(os.environ.get("FILE_RETENTION_MINUTES", 30))

    # Path to the service account JSON key file downloaded from Google Cloud
    # Console (see README "Google Cloud setup"). Relative paths are resolved
    # against the project root.
    GOOGLE_SERVICE_ACCOUNT_FILE = os.path.join(
        BASE_DIR, os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
    )
    GOOGLE_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
