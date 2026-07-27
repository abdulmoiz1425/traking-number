import pytest

from app import create_app
from app.errors import FileValidationError
from app.services import sheets_processing_service as sps


@pytest.fixture
def app_ctx():
    app = create_app()
    with app.test_request_context():
        yield app


def _fake_tabs(spreadsheet_id):
    return {
        "tracking-id": [{"title": "Sheet1", "sheet_id": 0, "row_count": 10, "column_count": 5}],
        "main-id": [{"title": "Orders", "sheet_id": 111, "row_count": 10, "column_count": 5}],
    }[spreadsheet_id]


def _fake_values(spreadsheet_id, tab_title):
    data = {
        ("tracking-id", "Sheet1"): [["Tracking Number"], ["ABC123"], ["DEF456"], ["XYZ789"]],
        ("main-id", "Orders"): [
            ["Order ID", "Customer", "Tracking Number", "Amount"],
            [1001, "Ali", "ABC123", 5000],
            [1002, "Ahmed", "TEST111", 3500],
            [1003, "Sara", "DEF456", 7200],
        ],
    }
    return data[(spreadsheet_id, tab_title)]


def _fake_title(spreadsheet_id):
    return {"tracking-id": "Tracking List", "main-id": "Main Orders"}[spreadsheet_id]


@pytest.fixture
def patched(monkeypatch, app_ctx):
    monkeypatch.setattr(sps, "get_credentials", lambda: object())
    monkeypatch.setattr(sps, "get_client", lambda creds: object())
    monkeypatch.setattr(sps, "get_spreadsheet_title", lambda service, sid: _fake_title(sid))
    monkeypatch.setattr(sps, "list_tabs", lambda service, sid: _fake_tabs(sid))
    monkeypatch.setattr(sps, "read_values", lambda service, sid, tab: _fake_values(sid, tab))

    highlight_calls = []
    monkeypatch.setattr(
        sps,
        "highlight_rows",
        lambda service, sid, sheet_id_numeric, row_numbers, total_columns: highlight_calls.append(
            (sid, sheet_id_numeric, row_numbers, total_columns)
        ),
    )
    return highlight_calls


def _connect(patched=None):
    return sps.connect_sheets(
        "https://docs.google.com/spreadsheets/d/tracking-id/edit",
        "https://docs.google.com/spreadsheets/d/main-id/edit",
    )


def test_connect_sheets_returns_inspection_for_both_files(patched):
    result = _connect()
    assert result["tracking_file"]["detected_column"] == "A"
    assert result["main_file"]["detected_column"] == "C"
    assert result["tracking_file"]["worksheets"] == ["Sheet1"]
    assert result["main_file"]["worksheets"] == ["Orders"]


def test_process_sheets_highlights_correct_rows(patched, tmp_path):
    _connect()

    result = sps.process_sheets(
        tracking_sheet_name="Sheet1",
        tracking_column_letter="A",
        tracking_has_header=True,
        main_sheet_name="Orders",
        main_column_letter="C",
        main_has_header=True,
        upload_folder=str(tmp_path),
    )

    summary = result["summary"]
    assert summary["tracking_numbers_matched"] == 2
    assert summary["tracking_numbers_not_matched"] == 1
    assert summary["total_rows_highlighted"] == 2
    assert result["main_sheet_url"] == "https://docs.google.com/spreadsheets/d/main-id/edit"

    assert len(patched) == 1
    sid, sheet_id_numeric, row_numbers, total_columns = patched[0]
    assert sid == "main-id"
    assert sheet_id_numeric == 111
    assert sorted(row_numbers) == [2, 4]
    assert total_columns == 4


def test_process_sheets_without_connect_raises(patched, tmp_path):
    with pytest.raises(FileValidationError, match="No connected Google Sheets"):
        sps.process_sheets(
            tracking_sheet_name="Sheet1",
            tracking_column_letter="A",
            tracking_has_header=True,
            main_sheet_name="Orders",
            main_column_letter="C",
            main_has_header=True,
            upload_folder=str(tmp_path),
        )


def test_connect_sheets_rejects_bad_link(patched):
    with pytest.raises(FileValidationError):
        sps.connect_sheets("not a real link", "also not real")


def test_get_sheets_status_reflects_connection(patched):
    assert sps.get_sheets_status() == {"connected": False}
    _connect()
    status = sps.get_sheets_status()
    assert status["connected"] is True
    assert status["tracking_name"] == "Tracking List"
    assert status["main_name"] == "Main Orders"


def test_reset_clears_connection(patched):
    _connect()
    sps.clear_sheets_session()
    with pytest.raises(FileValidationError):
        sps.get_connected_sheets()


def test_empty_tracking_values_raises(monkeypatch, app_ctx, tmp_path):
    monkeypatch.setattr(sps, "get_credentials", lambda: object())
    monkeypatch.setattr(sps, "get_client", lambda creds: object())
    monkeypatch.setattr(sps, "get_spreadsheet_title", lambda service, sid: sid)
    monkeypatch.setattr(sps, "list_tabs", lambda service, sid: [{"title": "Sheet1", "sheet_id": 0}])

    def fake_values(service, sid, tab):
        if sid == "empty-tracking-id":
            return [["Tracking Number"], [None], [""]]
        return [["Tracking Number"], ["ABC123"]]

    monkeypatch.setattr(sps, "read_values", fake_values)

    sps.connect_sheets(
        "https://docs.google.com/spreadsheets/d/empty-tracking-id/edit",
        "https://docs.google.com/spreadsheets/d/main-ok-id/edit",
    )

    with pytest.raises(FileValidationError, match="No valid tracking numbers"):
        sps.process_sheets(
            tracking_sheet_name="Sheet1",
            tracking_column_letter="A",
            tracking_has_header=True,
            main_sheet_name="Sheet1",
            main_column_letter="A",
            main_has_header=True,
            upload_folder=str(tmp_path),
        )


def test_empty_main_column_raises(monkeypatch, app_ctx, tmp_path):
    monkeypatch.setattr(sps, "get_credentials", lambda: object())
    monkeypatch.setattr(sps, "get_client", lambda creds: object())
    monkeypatch.setattr(sps, "get_spreadsheet_title", lambda service, sid: sid)
    monkeypatch.setattr(sps, "list_tabs", lambda service, sid: [{"title": "Sheet1", "sheet_id": 0}])

    def fake_values(service, sid, tab):
        if sid == "main-blank-col-id":
            return [["Tracking Number", "Amount"], [None, 100], [None, 200]]
        return [["Tracking Number"], ["ABC123"]]

    monkeypatch.setattr(sps, "read_values", fake_values)

    sps.connect_sheets(
        "https://docs.google.com/spreadsheets/d/tracking-ok-id/edit",
        "https://docs.google.com/spreadsheets/d/main-blank-col-id/edit",
    )

    with pytest.raises(FileValidationError, match="contains no values"):
        sps.process_sheets(
            tracking_sheet_name="Sheet1",
            tracking_column_letter="A",
            tracking_has_header=True,
            main_sheet_name="Sheet1",
            main_column_letter="A",
            main_has_header=True,
            upload_folder=str(tmp_path),
        )
