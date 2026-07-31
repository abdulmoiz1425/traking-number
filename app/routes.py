from flask import Blueprint, current_app, jsonify, render_template, request, send_file

from app.errors import FileValidationError
from app.services.download_store import register_download, resolve_download
from app.services.google_auth_service import get_service_account_email
from app.services.sheets_processing_service import (
    cleanup_stale_output_folders,
    clear_sheets_session,
    connect_sheets,
    get_columns_for_tab,
    get_connected_sheets,
    get_sheets_status,
    process_sheets,
    set_last_result,
)

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    return render_template("index.html")


@main_bp.route("/service-account-email")
def service_account_email():
    try:
        email = get_service_account_email()
    except FileValidationError as exc:
        return jsonify({"email": None, "error": str(exc)})
    return jsonify({"email": email})


@main_bp.route("/connect-sheets", methods=["POST"])
def connect_sheets_route():
    data = request.get_json(silent=True) or {}
    tracking_sheet_url = data.get("tracking_sheet_url")
    main_sheet_url = data.get("main_sheet_url")

    if not tracking_sheet_url or not main_sheet_url:
        return jsonify({"error": "Please paste both Google Sheet links."}), 400

    try:
        cleanup_stale_output_folders(current_app.config["UPLOAD_FOLDER"], current_app.config["FILE_RETENTION_MINUTES"])
        result = connect_sheets(tracking_sheet_url, main_sheet_url)
    except FileValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        current_app.logger.exception("Unexpected error while connecting Google Sheets")
        return jsonify({"error": "An unexpected error occurred while connecting to Google Sheets."}), 500

    return jsonify(result)


@main_bp.route("/worksheet-columns")
def worksheet_columns():
    file_key = request.args.get("file")
    sheet_name = request.args.get("sheet")

    if file_key not in ("tracking", "main") or not sheet_name:
        return jsonify({"error": "Invalid request parameters."}), 400

    try:
        result = get_columns_for_tab(file_key, sheet_name)
    except FileValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        current_app.logger.exception("Unexpected error while reading worksheet")
        return jsonify({"error": "An unexpected error occurred while reading the worksheet."}), 500

    return jsonify(result)


@main_bp.route("/sheets-status")
def sheets_status():
    return jsonify(get_sheets_status())


@main_bp.route("/process", methods=["POST"])
def process():
    data = request.get_json(silent=True) or {}

    tracking_sheet = data.get("tracking_sheet")
    tracking_column = data.get("tracking_column")
    main_sheet = data.get("main_sheet")
    main_column = data.get("main_column")
    tracking_has_header = bool(data.get("tracking_has_header", True))
    main_has_header = bool(data.get("main_has_header", True))

    if not tracking_sheet or not tracking_column:
        return jsonify({"error": "Please select the tracking-number worksheet and column."}), 400
    if not main_sheet or not main_column:
        return jsonify({"error": "Please select the main-sheet worksheet and column."}), 400

    try:
        get_connected_sheets()  # surfaces a clear "please connect sheets" error before touching the API
        result = process_sheets(
            tracking_sheet_name=tracking_sheet,
            tracking_column_letter=tracking_column,
            tracking_has_header=tracking_has_header,
            main_sheet_name=main_sheet,
            main_column_letter=main_column,
            main_has_header=main_has_header,
            upload_folder=current_app.config["UPLOAD_FOLDER"],
        )
    except FileValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        current_app.logger.exception("Unexpected error during processing")
        return jsonify({"error": "An unexpected error occurred while processing the sheets."}), 500

    unmatched_token = register_download(result["unmatched_path"], result["unmatched_filename"])

    response_body = {
        "summary": result["summary"],
        "unmatched_token": unmatched_token,
        "unmatched_filename": result["unmatched_filename"],
        "main_sheet_url": result["main_sheet_url"],
    }
    set_last_result(response_body)

    return jsonify(response_body)


@main_bp.route("/download-unmatched/<token>")
def download_unmatched(token):
    try:
        entry = resolve_download(token)
        return send_file(entry["path"], as_attachment=True, download_name=entry["filename"])
    except FileValidationError as exc:
        return jsonify({"error": str(exc)}), 404
    except FileNotFoundError:
        return jsonify({"error": "This file is no longer available. Please process the sheets again."}), 404


@main_bp.route("/reset", methods=["POST"])
def reset():
    clear_sheets_session()
    return jsonify({"status": "reset"})
