import os
import shutil
import time
from datetime import datetime

from openpyxl import Workbook
from openpyxl.utils import column_index_from_string

from app.errors import FileValidationError
from app.services.column_utils import detect_tracking_column
from app.services.google_auth_service import get_credentials
from app.services.google_sheets_service import (
    extract_spreadsheet_id,
    get_client,
    get_spreadsheet_title,
    highlight_rows,
    inspect_tab_columns,
    list_tabs,
    read_values,
)
from app.services.matching_engine import find_matches, read_tracking_numbers
from app.services.session_utils import get_or_create_session_id, get_session_id

# session_id -> connected spreadsheet info / last result. In-memory,
# single-process — same pattern/limitation as the other _STORE dicts here.
_SHEETS_STORE = {}
_RESULT_STORE = {}


def cleanup_stale_output_folders(upload_folder, retention_minutes):
    if not os.path.isdir(upload_folder):
        return
    cutoff = time.time() - retention_minutes * 60
    for name in os.listdir(upload_folder):
        path = os.path.join(upload_folder, name)
        if not os.path.isdir(path):
            continue
        try:
            if os.path.getmtime(path) < cutoff:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            continue


def connect_sheets(tracking_url, main_url):
    credentials = get_credentials()
    service = get_client(credentials)

    tracking_info = _connect_one(service, tracking_url, "tracking-number sheet")
    main_info = _connect_one(service, main_url, "main sheet")

    session_id = get_or_create_session_id()
    _SHEETS_STORE[session_id] = {
        "tracking_spreadsheet_id": tracking_info["spreadsheet_id"],
        "main_spreadsheet_id": main_info["spreadsheet_id"],
        "tracking_url": tracking_url,
        "main_url": main_url,
        "tracking_title": tracking_info["title"],
        "main_title": main_info["title"],
    }
    _RESULT_STORE.pop(session_id, None)

    return {"tracking_file": tracking_info["inspection"], "main_file": main_info["inspection"]}


def get_connected_sheets():
    session_id = get_session_id()
    store_entry = _SHEETS_STORE.get(session_id) if session_id else None
    if not store_entry:
        raise FileValidationError("No connected Google Sheets found for this session. Please paste both links again.")
    return store_entry


def clear_sheets_session():
    session_id = get_session_id()
    if session_id:
        _SHEETS_STORE.pop(session_id, None)
        _RESULT_STORE.pop(session_id, None)


def set_last_result(result):
    session_id = get_or_create_session_id()
    _RESULT_STORE[session_id] = result


def get_last_result():
    session_id = get_session_id()
    return _RESULT_STORE.get(session_id) if session_id else None


def get_sheets_status():
    try:
        store_entry = get_connected_sheets()
        credentials = get_credentials()
    except FileValidationError:
        return {"connected": False}

    service = get_client(credentials)
    try:
        tracking_inspection = _inspect_spreadsheet(
            service, store_entry["tracking_spreadsheet_id"], "tracking-number sheet"
        )
        main_inspection = _inspect_spreadsheet(service, store_entry["main_spreadsheet_id"], "main sheet")
    except FileValidationError:
        return {"connected": False}

    status = {
        "connected": True,
        "tracking_name": store_entry["tracking_title"],
        "main_name": store_entry["main_title"],
        "tracking_url": store_entry["tracking_url"],
        "main_url": store_entry["main_url"],
        "tracking_file": tracking_inspection,
        "main_file": main_inspection,
    }

    last_result = get_last_result()
    if last_result:
        status["result"] = last_result

    return status


def get_columns_for_tab(file_key, tab_title):
    store_entry = get_connected_sheets()
    spreadsheet_id_key = f"{file_key}_spreadsheet_id"
    if spreadsheet_id_key not in store_entry:
        raise FileValidationError("Invalid file reference.")

    credentials = get_credentials()
    service = get_client(credentials)
    values = read_values(service, store_entry[spreadsheet_id_key], tab_title)
    columns = inspect_tab_columns(values)
    detected_column = detect_tracking_column(columns)
    return {"columns": columns, "detected_column": detected_column}


def process_sheets(
    tracking_sheet_name,
    tracking_column_letter,
    tracking_has_header,
    main_sheet_name,
    main_column_letter,
    main_has_header,
    upload_folder,
):
    store_entry = get_connected_sheets()
    credentials = get_credentials()
    service = get_client(credentials)

    # Session-scoped so concurrent users never collide on the fixed
    # "unmatched_tracking_numbers.xlsx" filename, and so a stale session's
    # directory (this file included) is what cleanup_stale_output_folders
    # actually removes.
    session_id = get_or_create_session_id()
    output_folder = os.path.join(upload_folder, session_id, "output")

    tracking_spreadsheet_id = store_entry["tracking_spreadsheet_id"]
    main_spreadsheet_id = store_entry["main_spreadsheet_id"]

    tracking_col_idx = column_index_from_string(tracking_column_letter)
    tracking_values = read_values(service, tracking_spreadsheet_id, tracking_sheet_name)
    tracking_result = read_tracking_numbers(tracking_values, tracking_col_idx, tracking_has_header)

    search_set = tracking_result["unique_values"]
    if not search_set:
        raise FileValidationError("No valid tracking numbers were found in the tracking-number sheet.")

    main_col_idx = column_index_from_string(main_column_letter)
    main_values = read_values(service, main_spreadsheet_id, main_sheet_name)

    min_data_row = 2 if main_has_header else 1
    if len(main_values) < min_data_row:
        raise FileValidationError("The selected main worksheet contains no data.")

    match_result = find_matches(main_values, main_col_idx, search_set, main_has_header)
    if match_result["non_blank_scanned"] == 0:
        raise FileValidationError("The selected main-sheet tracking-number column contains no values.")

    main_tabs = list_tabs(service, main_spreadsheet_id)
    main_tab = next((tab for tab in main_tabs if tab["title"] == main_sheet_name), None)
    if main_tab is None:
        raise FileValidationError("The selected worksheet could not be found. Please reconnect the sheets.")

    total_columns = max((len(row) for row in main_values), default=0)
    highlight_rows(service, main_spreadsheet_id, main_tab["sheet_id"], match_result["matched_row_numbers"], total_columns)

    matched_set = match_result["matched_values"]
    unmatched_set = search_set - matched_set

    os.makedirs(output_folder, exist_ok=True)
    timestamp = datetime.now()
    unmatched_filename = "unmatched_tracking_numbers.xlsx"
    unmatched_path = os.path.join(output_folder, unmatched_filename)
    _write_unmatched_workbook(unmatched_set, unmatched_path)

    summary = {
        "total_tracking_numbers_read": tracking_result["total_read"],
        "blank_tracking_cells_ignored": tracking_result["blanks_ignored"],
        "duplicate_tracking_numbers_removed": tracking_result["duplicates_removed"],
        "unique_tracking_numbers_searched": len(search_set),
        "tracking_numbers_matched": len(matched_set),
        "tracking_numbers_not_matched": len(unmatched_set),
        "total_rows_highlighted": len(match_result["matched_row_numbers"]),
        "processing_status": "success",
        "processing_datetime": timestamp.isoformat(timespec="seconds"),
    }

    return {
        "summary": summary,
        "unmatched_filename": unmatched_filename,
        "unmatched_path": unmatched_path,
        "main_sheet_url": f"https://docs.google.com/spreadsheets/d/{main_spreadsheet_id}/edit",
    }


def _inspect_spreadsheet(service, spreadsheet_id, label):
    tabs = list_tabs(service, spreadsheet_id)
    if not tabs:
        raise FileValidationError(f"The {label} has no worksheets.")

    worksheets = [tab["title"] for tab in tabs]
    selected_sheet = worksheets[0]
    values = read_values(service, spreadsheet_id, selected_sheet)
    if not values:
        raise FileValidationError(f'The {label}\'s worksheet "{selected_sheet}" contains no data.')

    columns = inspect_tab_columns(values)
    detected_column = detect_tracking_column(columns)

    return {
        "worksheets": worksheets,
        "selected_worksheet": selected_sheet,
        "columns": columns,
        "detected_column": detected_column,
    }


def _connect_one(service, url, label):
    if not url or not url.strip():
        raise FileValidationError(f"Please paste a link for the {label}.")
    spreadsheet_id = extract_spreadsheet_id(url)
    title = get_spreadsheet_title(service, spreadsheet_id)
    inspection = _inspect_spreadsheet(service, spreadsheet_id, label)
    return {"spreadsheet_id": spreadsheet_id, "title": title, "inspection": inspection}


def _write_unmatched_workbook(unmatched_set, path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Unmatched"
    ws.append(["Tracking Number"])
    for value in sorted(unmatched_set):
        ws.append([value])
    wb.save(path)
