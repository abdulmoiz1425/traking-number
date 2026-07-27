import re

import googleapiclient.discovery
from googleapiclient.errors import HttpError
from openpyxl.utils import get_column_letter

from app.errors import FileValidationError

_URL_ID_PATTERN = re.compile(r"/spreadsheets/d/([a-zA-Z0-9_-]+)")
_BARE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{20,}$")

RED_BACKGROUND = {"red": 1, "green": 0, "blue": 0}


def extract_spreadsheet_id(url_or_id):
    text = (url_or_id or "").strip()
    match = _URL_ID_PATTERN.search(text)
    if match:
        return match.group(1)
    if _BARE_ID_PATTERN.match(text):
        return text
    raise FileValidationError("That doesn't look like a valid Google Sheets link.")


def get_client(credentials):
    return googleapiclient.discovery.build("sheets", "v4", credentials=credentials, cache_discovery=False)


def get_spreadsheet_title(service, spreadsheet_id):
    try:
        response = service.spreadsheets().get(spreadsheetId=spreadsheet_id, fields="properties.title").execute()
    except HttpError as exc:
        raise _wrap_http_error(exc)
    return response.get("properties", {}).get("title", spreadsheet_id)


def list_tabs(service, spreadsheet_id):
    try:
        response = (
            service.spreadsheets()
            .get(spreadsheetId=spreadsheet_id, fields="sheets.properties(sheetId,title,gridProperties)")
            .execute()
        )
    except HttpError as exc:
        raise _wrap_http_error(exc)

    tabs = []
    for sheet in response.get("sheets", []):
        props = sheet["properties"]
        grid = props.get("gridProperties", {})
        tabs.append(
            {
                "title": props["title"],
                "sheet_id": props["sheetId"],
                "row_count": grid.get("rowCount"),
                "column_count": grid.get("columnCount"),
            }
        )
    return tabs


def read_values(service, spreadsheet_id, tab_title):
    try:
        response = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=_quote_sheet_title(tab_title))
            .execute()
        )
    except HttpError as exc:
        raise _wrap_http_error(exc)
    return response.get("values", [])


def inspect_tab_columns(values, max_example_rows=20):
    if not values:
        return []
    header_row = values[0]
    total_columns = max(len(row) for row in values)

    columns = []
    for idx in range(1, total_columns + 1):
        letter = get_column_letter(idx)
        raw_header = header_row[idx - 1] if idx - 1 < len(header_row) else None
        header = str(raw_header).strip() if raw_header not in (None, "") else ""
        example = _find_example_value(values, idx, max_example_rows)
        columns.append({"letter": letter, "header": header, "example": example})
    return columns


def highlight_rows(service, spreadsheet_id, sheet_id_numeric, row_numbers, total_columns):
    if not row_numbers:
        return
    requests = [
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id_numeric,
                    "startRowIndex": row_number - 1,
                    "endRowIndex": row_number,
                    "startColumnIndex": 0,
                    "endColumnIndex": total_columns,
                },
                "cell": {"userEnteredFormat": {"backgroundColor": RED_BACKGROUND}},
                "fields": "userEnteredFormat.backgroundColor",
            }
        }
        for row_number in row_numbers
    ]
    try:
        service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": requests}).execute()
    except HttpError as exc:
        raise _wrap_http_error(exc)


def _quote_sheet_title(title):
    return "'" + title.replace("'", "''") + "'"


def _find_example_value(values, col_idx, max_scan_rows):
    for row in values[1 : 1 + max_scan_rows]:
        if col_idx - 1 < len(row):
            value = row[col_idx - 1]
            if value not in (None, ""):
                return str(value).strip()
    return None


def _wrap_http_error(exc):
    status = exc.resp.status if exc.resp is not None else None
    if status == 404:
        return FileValidationError("Couldn't find this Google Sheet. Please check the link and try again.")
    if status == 403:
        return FileValidationError(
            "This Google account doesn't have access to this Google Sheet. "
            "Make sure you're signed in with an account that can view or edit it."
        )
    return FileValidationError("Couldn't access this Google Sheet. Please check the link and try again.")
