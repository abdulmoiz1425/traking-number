from datetime import datetime

import google_auth_oauthlib.flow
from flask import current_app, session
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from app.errors import FileValidationError
from app.services.session_utils import get_or_create_session_id, get_session_id

# session_id -> serialized credential fields. In-memory, single-process —
# same pattern/limitation as the other _STORE dicts in this app; a real
# multi-worker deployment needs this moved to a shared store (Redis/DB).
_CREDENTIALS_STORE = {}


def _build_flow(state=None):
    client_config = {
        "web": {
            "client_id": current_app.config["GOOGLE_CLIENT_ID"],
            "client_secret": current_app.config["GOOGLE_CLIENT_SECRET"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [current_app.config["GOOGLE_REDIRECT_URI"]],
        }
    }
    flow = google_auth_oauthlib.flow.Flow.from_client_config(
        client_config,
        scopes=current_app.config["GOOGLE_SCOPES"],
        state=state,
    )
    flow.redirect_uri = current_app.config["GOOGLE_REDIRECT_URI"]
    return flow


def get_authorization_url():
    flow = _build_flow()
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    session["oauth_state"] = state
    return auth_url


def store_credentials_from_callback(full_callback_url):
    state = session.get("oauth_state")
    if not state:
        raise FileValidationError("Sign-in session expired. Please try signing in again.")

    flow = _build_flow(state=state)
    try:
        flow.fetch_token(authorization_response=full_callback_url)
    except Exception:
        raise FileValidationError("Google sign-in failed. Please try again.")

    session_id = get_or_create_session_id()
    _CREDENTIALS_STORE[session_id] = _credentials_to_dict(flow.credentials)
    session.pop("oauth_state", None)


def get_credentials():
    session_id = get_session_id()
    data = _CREDENTIALS_STORE.get(session_id) if session_id else None
    if not data:
        raise FileValidationError("Please sign in with Google first.")

    creds = _dict_to_credentials(data)
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:
            _CREDENTIALS_STORE.pop(session_id, None)
            raise FileValidationError("Your Google sign-in has expired. Please sign in again.")
        _CREDENTIALS_STORE[session_id] = _credentials_to_dict(creds)
    return creds


def is_authenticated():
    session_id = get_session_id()
    return bool(session_id and session_id in _CREDENTIALS_STORE)


def clear_credentials():
    session_id = get_session_id()
    if session_id:
        _CREDENTIALS_STORE.pop(session_id, None)


def _credentials_to_dict(creds):
    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
    }


def _dict_to_credentials(data):
    creds = Credentials(
        token=data["token"],
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri"),
        client_id=data.get("client_id"),
        client_secret=data.get("client_secret"),
        scopes=data.get("scopes"),
    )
    if data.get("expiry"):
        creds.expiry = datetime.fromisoformat(data["expiry"])
    return creds
