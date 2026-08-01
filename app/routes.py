from flask import Blueprint, current_app, jsonify, redirect, render_template, request, send_file

from app.errors import FileValidationError
from app.services.download_store import register_download, resolve_download
from app.services.google_auth_service import (
    clear_credentials,
    get_authorization_url,
    get_picker_token,
    is_authenticated,
    store_credentials_from_callback,
)
from app.services.sheets_processing_service import (
    cleanup_stale_output_folders,
    clear_sheets_session,
    connect_sheet,
    get_columns_for_tab,
    get_connected_sheet,
    get_sheets_status,
    process_sheets,
    set_last_result,
)

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    return render_template("index.html", google_api_key=current_app.config["GOOGLE_API_KEY"])


@main_bp.route("/google/login")
def google_login():
    return redirect(get_authorization_url())


@main_bp.route("/google/callback")
def google_callback():
    if request.args.get("error"):
        return redirect("/?auth_error=consent_denied")

    try:
        store_credentials_from_callback(request.url)
    except FileValidationError:
        return redirect("/?auth_error=sign_in_failed")

    return redirect("/")


@main_bp.route("/google/logout", methods=["POST"])
def google_logout():
    clear_credentials()
    clear_sheets_session()
    return jsonify({"status": "signed_out"})


@main_bp.route("/auth-status")
def auth_status():
    return jsonify({"authenticated": is_authenticated()})


@main_bp.route("/picker-token")
def picker_token():
    try:
        token = get_picker_token()
    except FileValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    # Picker needs the Cloud project number (the leading numeric segment of
    # the OAuth client ID) via setAppId() to actually grant the app per-file
    # access to whatever's selected under the narrow drive.file scope -
    # without it, Picker shows the file but never registers the grant, and
    # later API calls report the file as not found at all.
    app_id = current_app.config["GOOGLE_CLIENT_ID"].split("-")[0]
    return jsonify({"token": token, "api_key": current_app.config["GOOGLE_API_KEY"], "app_id": app_id})


@main_bp.route("/connect-sheet", methods=["POST"])
def connect_sheet_route():
    data = request.get_json(silent=True) or {}
    spreadsheet_id = data.get("spreadsheet_id")

    if not spreadsheet_id:
        return jsonify({"error": "No Google Sheet was selected."}), 400

    try:
        cleanup_stale_output_folders(current_app.config["UPLOAD_FOLDER"], current_app.config["FILE_RETENTION_MINUTES"])
        result = connect_sheet(spreadsheet_id)
    except FileValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        current_app.logger.exception("Unexpected error while connecting Google Sheet")
        return jsonify({"error": "An unexpected error occurred while connecting to the Google Sheet."}), 500

    return jsonify(result)


@main_bp.route("/worksheet-columns")
def worksheet_columns():
    tab_name = request.args.get("tab")

    if not tab_name:
        return jsonify({"error": "Invalid request parameters."}), 400

    try:
        result = get_columns_for_tab(tab_name)
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

    tracking_tab = data.get("tracking_tab")
    tracking_column = data.get("tracking_column")
    tracking_status_column = data.get("tracking_status_column")
    main_tab = data.get("main_tab")
    main_column = data.get("main_column")
    net_payable_tab = data.get("net_payable_tab")
    net_payable_tracking_column = data.get("net_payable_tracking_column")
    net_payable_value_column = data.get("net_payable_value_column")
    tracking_has_header = bool(data.get("tracking_has_header", True))
    main_has_header = bool(data.get("main_has_header", True))
    net_payable_has_header = bool(data.get("net_payable_has_header", True))

    if not tracking_tab or not tracking_column or not tracking_status_column:
        return jsonify({"error": "Please select the tracking-number tab, tracking column, and status column."}), 400
    if not main_tab or not main_column:
        return jsonify({"error": "Please select the main tab and column."}), 400
    if not net_payable_tab or not net_payable_tracking_column or not net_payable_value_column:
        return jsonify(
            {"error": "Please select the Net Payable tab, its tracking column, and its Net Payable column."}
        ), 400

    try:
        get_connected_sheet()  # surfaces a clear "please connect a sheet" error before touching the API
        result = process_sheets(
            tracking_tab=tracking_tab,
            tracking_column_letter=tracking_column,
            tracking_status_column_letter=tracking_status_column,
            tracking_has_header=tracking_has_header,
            main_tab=main_tab,
            main_column_letter=main_column,
            main_has_header=main_has_header,
            net_payable_tab=net_payable_tab,
            net_payable_tracking_column_letter=net_payable_tracking_column,
            net_payable_value_column_letter=net_payable_value_column,
            net_payable_has_header=net_payable_has_header,
            upload_folder=current_app.config["UPLOAD_FOLDER"],
        )
    except FileValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        current_app.logger.exception("Unexpected error during processing")
        return jsonify({"error": "An unexpected error occurred while processing the sheet."}), 500

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
        return jsonify({"error": "This file is no longer available. Please process the sheet again."}), 404


@main_bp.route("/reset", methods=["POST"])
def reset():
    clear_sheets_session()
    return jsonify({"status": "reset"})
