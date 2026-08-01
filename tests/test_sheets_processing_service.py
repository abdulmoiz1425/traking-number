import pytest

from app import create_app
from app.errors import FileValidationError
from app.services import sheets_processing_service as sps
from app.services.google_sheets_service import GREEN_BACKGROUND, RED_BACKGROUND

SPREADSHEET_ID = "sheet-id-with-enough-characters-000"
TABS = [
    {"title": "Sheet1", "sheet_id": 0, "row_count": 10, "column_count": 5},
    {"title": "Orders", "sheet_id": 111, "row_count": 10, "column_count": 5},
    {"title": "NetPayable", "sheet_id": 222, "row_count": 10, "column_count": 5},
]
VALUES = {
    "Sheet1": [
        ["Tracking Number", "Status"],
        ["ABC123", "Delivered"],
        ["DEF456", "Return"],
        ["XYZ789", "Pending"],
    ],
    "Orders": [
        ["Order ID", "Customer", "Tracking Number", "Amount"],
        [1001, "Ali", "ABC123", 5000],
        [1002, "Ahmed", "TEST111", 3500],
        [1003, "Sara", "DEF456", 7200],
    ],
    "NetPayable": [
        ["Tracking Number", "Net Payable"],
        ["ABC123", 4500],
        ["DEF456", 7000],
    ],
}


@pytest.fixture
def app_ctx():
    app = create_app()
    with app.test_request_context():
        yield app


@pytest.fixture
def patched(monkeypatch, app_ctx):
    monkeypatch.setattr(sps, "get_credentials", lambda: object())
    monkeypatch.setattr(sps, "get_client", lambda creds: object())
    monkeypatch.setattr(sps, "get_spreadsheet_title", lambda service, sid: "Tracking + Orders")
    monkeypatch.setattr(sps, "list_tabs", lambda service, sid: TABS)
    monkeypatch.setattr(sps, "read_values", lambda service, sid, tab: VALUES[tab])

    highlight_calls = []
    monkeypatch.setattr(
        sps,
        "highlight_rows",
        lambda service, sid, sheet_id_numeric, row_colors, total_columns: highlight_calls.append(
            (sid, sheet_id_numeric, dict(row_colors), total_columns)
        ),
    )

    write_calls = []
    monkeypatch.setattr(
        sps,
        "write_values",
        lambda service, sid, tab, cell_updates: write_calls.append((sid, tab, dict(cell_updates))),
    )

    return {"highlight_calls": highlight_calls, "write_calls": write_calls}


def _connect():
    return sps.connect_sheet(f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit")


def _process(**overrides):
    kwargs = dict(
        tracking_tab="Sheet1",
        tracking_column_letter="A",
        tracking_status_column_letter="B",
        tracking_has_header=True,
        main_tab="Orders",
        main_column_letter="C",
        main_has_header=True,
        net_payable_tab="NetPayable",
        net_payable_tracking_column_letter="A",
        net_payable_value_column_letter="B",
        net_payable_has_header=True,
    )
    kwargs.update(overrides)
    return sps.process_sheets(**kwargs)


def test_connect_sheet_returns_inspection_for_default_tabs(patched):
    result = _connect()
    assert result["tabs"] == ["Sheet1", "Orders", "NetPayable"]
    assert result["tracking_tab"] == "Sheet1"
    assert result["main_tab"] == "Orders"
    assert result["net_payable_tab"] == "NetPayable"
    assert result["tracking_file"]["detected_column"] == "A"
    assert result["tracking_file"]["detected_status_column"] == "B"
    assert result["main_file"]["detected_column"] == "C"
    assert result["net_payable_file"]["detected_column"] == "A"
    assert result["net_payable_file"]["detected_net_payable_column"] == "B"


def test_process_sheets_colors_rows_and_writes_net_payable(patched, tmp_path):
    _connect()

    result = _process(upload_folder=str(tmp_path))

    summary = result["summary"]
    assert summary["tracking_numbers_matched"] == 2
    assert summary["tracking_numbers_not_matched"] == 1
    assert summary["rows_marked_delivered"] == 1
    assert summary["rows_marked_return"] == 1
    assert summary["rows_with_unrecognized_status"] == 0
    assert summary["total_rows_highlighted"] == 2
    assert summary["net_payable_rows_updated"] == 2
    assert summary["net_payable_column"] == "E"  # Orders has 4 used columns, so appended at E
    assert result["main_sheet_url"] == f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"

    highlight_calls = patched["highlight_calls"]
    assert len(highlight_calls) == 1
    sid, sheet_id_numeric, row_colors, total_columns = highlight_calls[0]
    assert sid == SPREADSHEET_ID
    assert sheet_id_numeric == 111
    assert row_colors == {2: GREEN_BACKGROUND, 4: RED_BACKGROUND}
    assert total_columns == 4

    write_calls = patched["write_calls"]
    assert len(write_calls) == 1
    write_sid, write_tab, cell_updates = write_calls[0]
    assert write_sid == SPREADSHEET_ID
    assert write_tab == "Orders"
    assert cell_updates == {
        (1, 5): "Net Payable",  # header written since no existing "Net Payable" column
        (2, 5): 4500,  # Ali / ABC123
        (4, 5): 7000,  # Sara / DEF456
    }


def test_process_sheets_reuses_existing_net_payable_column(monkeypatch, patched, tmp_path):
    _connect()

    orders_with_column = [
        ["Order ID", "Customer", "Tracking Number", "Amount", "Net Payable"],
        [1001, "Ali", "ABC123", 5000, None],
        [1002, "Ahmed", "TEST111", 3500, None],
        [1003, "Sara", "DEF456", 7200, None],
    ]
    values_with_np_column = dict(VALUES)
    values_with_np_column["Orders"] = orders_with_column
    monkeypatch.setattr(sps, "read_values", lambda service, sid, tab: values_with_np_column[tab])

    result = _process(upload_folder=str(tmp_path))

    write_sid, write_tab, cell_updates = patched["write_calls"][0]
    # Existing column E reused - no header rewrite, since it's already there.
    assert cell_updates == {(2, 5): 4500, (4, 5): 7000}
    assert result["summary"]["net_payable_column"] == "E"


def test_process_sheets_without_connect_raises(patched, tmp_path):
    with pytest.raises(FileValidationError, match="No connected Google Sheet"):
        _process(upload_folder=str(tmp_path))


def test_connect_sheet_rejects_bad_link(patched):
    with pytest.raises(FileValidationError):
        sps.connect_sheet("not a real link")


def test_get_sheets_status_reflects_connection(patched):
    assert sps.get_sheets_status() == {"connected": False}
    _connect()
    status = sps.get_sheets_status()
    assert status["connected"] is True
    assert status["spreadsheet_title"] == "Tracking + Orders"
    assert status["tabs"] == ["Sheet1", "Orders", "NetPayable"]


def test_reset_clears_connection(patched):
    _connect()
    sps.clear_sheets_session()
    with pytest.raises(FileValidationError):
        sps.get_connected_sheet()


def test_empty_tracking_values_raises(monkeypatch, app_ctx, tmp_path):
    monkeypatch.setattr(sps, "get_credentials", lambda: object())
    monkeypatch.setattr(sps, "get_client", lambda creds: object())
    monkeypatch.setattr(sps, "get_spreadsheet_title", lambda service, sid: sid)
    monkeypatch.setattr(
        sps,
        "list_tabs",
        lambda service, sid: [
            {"title": "Tracking", "sheet_id": 0},
            {"title": "Main", "sheet_id": 1},
        ],
    )

    def fake_values(service, sid, tab):
        if tab == "Tracking":
            return [["Tracking Number", "Status"], [None, None], ["", ""]]
        return [["Tracking Number"], ["ABC123"]]

    monkeypatch.setattr(sps, "read_values", fake_values)

    sps.connect_sheet(f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit")

    with pytest.raises(FileValidationError, match="No valid tracking numbers"):
        _process(tracking_tab="Tracking", main_tab="Main", upload_folder=str(tmp_path))


def test_empty_main_column_raises(monkeypatch, app_ctx, tmp_path):
    monkeypatch.setattr(sps, "get_credentials", lambda: object())
    monkeypatch.setattr(sps, "get_client", lambda creds: object())
    monkeypatch.setattr(sps, "get_spreadsheet_title", lambda service, sid: sid)
    monkeypatch.setattr(
        sps,
        "list_tabs",
        lambda service, sid: [
            {"title": "Tracking", "sheet_id": 0},
            {"title": "Main", "sheet_id": 1},
        ],
    )

    def fake_values(service, sid, tab):
        if tab == "Main":
            return [["Tracking Number", "Amount"], [None, 100], [None, 200]]
        return [["Tracking Number", "Status"], ["ABC123", "Delivered"]]

    monkeypatch.setattr(sps, "read_values", fake_values)

    sps.connect_sheet(f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit")

    with pytest.raises(FileValidationError, match="contains no values"):
        _process(
            tracking_tab="Tracking",
            main_tab="Main",
            main_column_letter="A",
            upload_folder=str(tmp_path),
        )


def test_empty_net_payable_values_raises(monkeypatch, patched, tmp_path):
    _connect()

    def fake_values(service, sid, tab):
        if tab == "NetPayable":
            return [["Tracking Number", "Net Payable"], [None, None], ["", ""]]
        return VALUES[tab]

    monkeypatch.setattr(sps, "read_values", fake_values)

    with pytest.raises(FileValidationError, match="No valid tracking numbers were found in the Net Payable tab"):
        _process(upload_folder=str(tmp_path))


def test_process_sheets_unrecognized_status_left_uncolored(monkeypatch, patched, tmp_path):
    _connect()

    # XYZ789's status is "Pending" (neither Delivered nor Return); put it in
    # the main sheet too so it's a genuine matched-but-uncolored case.
    values_with_pending_match = dict(VALUES)
    values_with_pending_match["Orders"] = VALUES["Orders"] + [[1004, "Zara", "XYZ789", 1000]]
    monkeypatch.setattr(sps, "read_values", lambda service, sid, tab: values_with_pending_match[tab])

    result = _process(upload_folder=str(tmp_path))
    summary = result["summary"]
    assert summary["rows_with_unrecognized_status"] == 1
    assert summary["tracking_numbers_matched"] == 3
    assert summary["tracking_numbers_not_matched"] == 0
