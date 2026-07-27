import os

from dotenv import load_dotenv
from flask import Flask, jsonify

from app.config import Config

load_dotenv()

# oauthlib refuses OAuth over plain HTTP by default. Only relax that for
# local dev (http://127.0.0.1) - production must terminate real HTTPS.
if os.environ.get("FLASK_ENV") == "development":
    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

# Google's token response can include scopes in a different order/composition
# than requested; this relaxes an overly strict oauthlib comparison. Not a
# security setting (unlike INSECURE_TRANSPORT above), safe to always set.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    from app.routes import main_bp
    app.register_blueprint(main_bp)

    max_mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)

    @app.errorhandler(413)
    def file_too_large(_exc):
        return jsonify({"error": f"File exceeds the maximum allowed size ({max_mb} MB)."}), 413

    @app.errorhandler(500)
    def internal_error(_exc):
        app.logger.exception("Unhandled server error")
        return jsonify({"error": "An unexpected server error occurred. Please try again."}), 500

    return app
