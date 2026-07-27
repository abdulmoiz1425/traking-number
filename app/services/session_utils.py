import uuid

from flask import session


def get_or_create_session_id():
    if "session_id" not in session:
        session["session_id"] = uuid.uuid4().hex
    return session["session_id"]


def get_session_id():
    return session.get("session_id")
