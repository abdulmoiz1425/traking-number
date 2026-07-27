import uuid

from app.errors import FileValidationError

# token -> {"path": str, "filename": str}. In-memory, single-process (see upload_service).
_DOWNLOAD_STORE = {}


def register_download(path, filename):
    token = uuid.uuid4().hex
    _DOWNLOAD_STORE[token] = {"path": path, "filename": filename}
    return token


def resolve_download(token):
    entry = _DOWNLOAD_STORE.get(token)
    if not entry:
        raise FileValidationError("This download link has expired or is invalid.")
    return entry
