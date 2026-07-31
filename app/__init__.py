import os

from dotenv import load_dotenv
from flask import Flask, jsonify

from app.config import Config

load_dotenv()


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
