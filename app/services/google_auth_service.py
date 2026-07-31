import os

from flask import current_app
from google.oauth2 import service_account

from app.errors import FileValidationError

# Cached across requests within a process — a service account is a single,
# fixed identity shared by every user, unlike the old per-session OAuth
# credentials this replaced, so there's nothing session-specific to store.
_credentials_cache = None


def get_credentials():
    global _credentials_cache
    if _credentials_cache is not None:
        return _credentials_cache

    key_path = current_app.config["GOOGLE_SERVICE_ACCOUNT_FILE"]
    if not key_path or not os.path.isfile(key_path):
        raise FileValidationError(
            "Google service account credentials are not configured. Set "
            "GOOGLE_SERVICE_ACCOUNT_FILE in .env to your service account "
            "JSON key file path (see README ‘Google Cloud setup’)."
        )

    try:
        _credentials_cache = service_account.Credentials.from_service_account_file(
            key_path, scopes=current_app.config["GOOGLE_SCOPES"]
        )
    except Exception:
        raise FileValidationError(
            "Could not load Google service account credentials. Check that "
            "GOOGLE_SERVICE_ACCOUNT_FILE points to a valid key file."
        )

    return _credentials_cache


def get_service_account_email():
    return getattr(get_credentials(), "service_account_email", None)
