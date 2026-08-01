import concurrent.futures

from openpyxl.utils import column_index_from_string

from app.errors import FileValidationError
from app.services.google_auth_service import get_credentials
from app.services.google_sheets_service import get_client, read_values, write_values
from app.services.matching_engine import (
    DELIVERED_STATUS,
    RETURN_STATUS,
    find_value_updates,
    read_unique_tracking_numbers,
)
from app.services.sheets_processing_service import get_connected_sheet
from app.services.tcs_status_classifier import classify_tcs_status
from app.services.tcs_tracking_service import track_shipment

DEFAULT_MAX_WORKERS = 5


def fetch_live_statuses(tracking_numbers, max_workers=DEFAULT_MAX_WORKERS):
    """Look up live TCS status for each tracking number concurrently and
    classify it. Sheet-agnostic - just takes a list of tracking numbers, so
    it's independently testable/reusable regardless of where they came from.

    Returns:
      {
        "classified_status_by_tracking_number": {tn: "DELIVERED"|"RETURN"|None},
        "raw_status_by_tracking_number": {tn: raw TCS status text},
        "not_found": [tn, ...],
        "errors": {tn: error_message, ...},
      }
    """
    tracking_numbers = list(tracking_numbers)
    classified_status_by_tracking_number = {}
    raw_status_by_tracking_number = {}
    not_found = []
    errors = {}

    if not tracking_numbers:
        return {
            "classified_status_by_tracking_number": classified_status_by_tracking_number,
            "raw_status_by_tracking_number": raw_status_by_tracking_number,
            "not_found": not_found,
            "errors": errors,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_tracking_number = {
            executor.submit(track_shipment, tracking_number): tracking_number for tracking_number in tracking_numbers
        }
        for future in concurrent.futures.as_completed(future_to_tracking_number):
            tracking_number = future_to_tracking_number[future]
            result = future.result()
            outcome = result["outcome"]

            if outcome == "found":
                raw_status = result["tracking_status"]
                raw_status_by_tracking_number[tracking_number] = raw_status
                classified_status_by_tracking_number[tracking_number] = classify_tcs_status(raw_status)
            elif outcome == "not_found":
                not_found.append(tracking_number)
            else:
                errors[tracking_number] = result.get("error_message", "Unknown error")

    return {
        "classified_status_by_tracking_number": classified_status_by_tracking_number,
        "raw_status_by_tracking_number": raw_status_by_tracking_number,
        "not_found": not_found,
        "errors": errors,
    }


def fetch_statuses_for_tracking_tab(
    tracking_tab, tracking_column_letter, tracking_has_header, max_workers=DEFAULT_MAX_WORKERS
):
    """Reads tracking numbers from the connected sheet's tracking tab, then
    looks up each one's live status via fetch_live_statuses(). Does not
    write anything back yet - that's a separate step."""
    store_entry = get_connected_sheet()
    credentials = get_credentials()
    service = get_client(credentials)
    spreadsheet_id = store_entry["spreadsheet_id"]

    tracking_col_idx = column_index_from_string(tracking_column_letter)
    tracking_values = read_values(service, spreadsheet_id, tracking_tab)
    read_result = read_unique_tracking_numbers(tracking_values, tracking_col_idx, tracking_has_header)

    unique_tracking_numbers = read_result["unique_values"]
    if not unique_tracking_numbers:
        raise FileValidationError("No valid tracking numbers were found in the tracking-number tab.")

    lookup_result = fetch_live_statuses(unique_tracking_numbers, max_workers=max_workers)

    return {
        "total_tracking_numbers_read": read_result["total_read"],
        "blank_tracking_cells_ignored": read_result["blanks_ignored"],
        "duplicate_tracking_numbers_removed": read_result["duplicates_removed"],
        "unique_tracking_numbers_searched": len(unique_tracking_numbers),
        **lookup_result,
    }


def write_statuses_to_tracking_tab(
    tracking_tab,
    tracking_column_letter,
    status_column_letter,
    tracking_has_header,
    classified_status_by_tracking_number,
    raw_status_by_tracking_number,
):
    """Writes the looked-up statuses back into the tracking tab's Status
    column. Classified results are written as clean "Delivered"/"Return"
    text, matching exactly what the existing coloring logic already expects
    (see matching_engine.read_tracking_numbers_with_status) - so nothing
    about that already-working pipeline needs to change. Anything still
    in-transit/unclassified is written as TCS's real status text instead
    (informational - it won't drive coloring, same as a blank/unrecognized
    status already didn't). Tracking numbers with no result (not found or a
    lookup error) are left untouched rather than overwritten with a guess.
    """
    store_entry = get_connected_sheet()
    credentials = get_credentials()
    service = get_client(credentials)
    spreadsheet_id = store_entry["spreadsheet_id"]

    tracking_col_idx = column_index_from_string(tracking_column_letter)
    status_col_idx = column_index_from_string(status_column_letter)
    tracking_values = read_values(service, spreadsheet_id, tracking_tab)

    display_status_by_tracking_number = {}
    for tracking_number, classified in classified_status_by_tracking_number.items():
        if classified == DELIVERED_STATUS:
            display_status_by_tracking_number[tracking_number] = "Delivered"
        elif classified == RETURN_STATUS:
            display_status_by_tracking_number[tracking_number] = "Return"
        else:
            raw_status = raw_status_by_tracking_number.get(tracking_number)
            if raw_status:
                display_status_by_tracking_number[tracking_number] = raw_status

    row_updates = find_value_updates(tracking_values, tracking_col_idx, display_status_by_tracking_number, tracking_has_header)
    cell_updates = {
        (row_number, status_col_idx): status_text for row_number, status_text in row_updates["updates"].items()
    }

    write_values(service, spreadsheet_id, tracking_tab, cell_updates)

    return {"rows_updated": len(cell_updates)}
