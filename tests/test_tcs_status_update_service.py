import pytest

from app import create_app
from app.errors import FileValidationError
from app.services import sheets_processing_service as sps
from app.services import tcs_status_update_service as tsu

SPREADSHEET_ID = "sheet-id-with-enough-characters-000"


@pytest.fixture
def app_ctx():
    app = create_app()
    with app.test_request_context():
        yield app


def _fake_track_shipment(responses):
    def _track(tracking_number):
        return responses[tracking_number]

    return _track


def test_fetch_live_statuses_classifies_found_results(monkeypatch):
    monkeypatch.setattr(
        tsu,
        "track_shipment",
        _fake_track_shipment(
            {
                "ABC123": {"outcome": "found", "tracking_status": "Delivered"},
                "DEF456": {"outcome": "found", "tracking_status": "Undelivered Due To Incorrect Address"},
            }
        ),
    )
    result = tsu.fetch_live_statuses(["ABC123", "DEF456"])
    assert result["classified_status_by_tracking_number"] == {"ABC123": "DELIVERED", "DEF456": "RETURN"}
    assert result["raw_status_by_tracking_number"] == {
        "ABC123": "Delivered",
        "DEF456": "Undelivered Due To Incorrect Address",
    }
    assert result["not_found"] == []
    assert result["errors"] == {}


def test_fetch_live_statuses_records_unclassifiable_status_as_none(monkeypatch):
    monkeypatch.setattr(
        tsu,
        "track_shipment",
        _fake_track_shipment({"ABC123": {"outcome": "found", "tracking_status": "Out For Delivery"}}),
    )
    result = tsu.fetch_live_statuses(["ABC123"])
    assert result["classified_status_by_tracking_number"] == {"ABC123": None}
    assert result["raw_status_by_tracking_number"] == {"ABC123": "Out For Delivery"}


def test_fetch_live_statuses_collects_not_found_and_errors(monkeypatch):
    monkeypatch.setattr(
        tsu,
        "track_shipment",
        _fake_track_shipment(
            {
                "MISSING1": {"outcome": "not_found"},
                "BROKEN1": {"outcome": "error", "error_message": "network down"},
            }
        ),
    )
    result = tsu.fetch_live_statuses(["MISSING1", "BROKEN1"])
    assert result["not_found"] == ["MISSING1"]
    assert result["errors"] == {"BROKEN1": "network down"}
    assert result["classified_status_by_tracking_number"] == {}


def test_fetch_live_statuses_empty_list_returns_empty_results():
    result = tsu.fetch_live_statuses([])
    assert result == {
        "classified_status_by_tracking_number": {},
        "raw_status_by_tracking_number": {},
        "not_found": [],
        "errors": {},
    }


def _connect_fake_sheet(monkeypatch, tracking_values):
    monkeypatch.setattr(sps, "get_credentials", lambda: object())
    monkeypatch.setattr(sps, "get_client", lambda creds: object())
    monkeypatch.setattr(sps, "get_spreadsheet_title", lambda service, sid: "Title")
    monkeypatch.setattr(sps, "list_tabs", lambda service, sid: [{"title": "Sheet1", "sheet_id": 0}])
    monkeypatch.setattr(sps, "read_values", lambda service, sid, tab: tracking_values)
    sps.connect_sheet(f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit")


def test_fetch_statuses_for_tracking_tab_happy_path(monkeypatch, app_ctx):
    tracking_values = [["Tracking Number"], ["ABC123"], ["ABC123"], ["DEF456"]]
    _connect_fake_sheet(monkeypatch, tracking_values)

    monkeypatch.setattr(tsu, "get_credentials", lambda: object())
    monkeypatch.setattr(tsu, "get_client", lambda creds: object())
    monkeypatch.setattr(tsu, "read_values", lambda service, sid, tab: tracking_values)
    monkeypatch.setattr(
        tsu,
        "track_shipment",
        _fake_track_shipment(
            {
                "ABC123": {"outcome": "found", "tracking_status": "Delivered"},
                "DEF456": {"outcome": "found", "tracking_status": "Undelivered Due To Incorrect Address"},
            }
        ),
    )

    result = tsu.fetch_statuses_for_tracking_tab("Sheet1", "A", True)

    assert result["total_tracking_numbers_read"] == 3
    assert result["duplicate_tracking_numbers_removed"] == 1
    assert result["unique_tracking_numbers_searched"] == 2
    assert result["classified_status_by_tracking_number"] == {"ABC123": "DELIVERED", "DEF456": "RETURN"}


def test_fetch_statuses_for_tracking_tab_raises_when_no_tracking_numbers(monkeypatch, app_ctx):
    tracking_values = [["Tracking Number"], [None], [""]]
    _connect_fake_sheet(monkeypatch, tracking_values)
    monkeypatch.setattr(tsu, "get_credentials", lambda: object())
    monkeypatch.setattr(tsu, "get_client", lambda creds: object())
    monkeypatch.setattr(tsu, "read_values", lambda service, sid, tab: tracking_values)

    with pytest.raises(FileValidationError, match="No valid tracking numbers"):
        tsu.fetch_statuses_for_tracking_tab("Sheet1", "A", True)


def test_fetch_statuses_for_tracking_tab_requires_connected_sheet(app_ctx):
    with pytest.raises(FileValidationError, match="No connected Google Sheet"):
        tsu.fetch_statuses_for_tracking_tab("Sheet1", "A", True)


def _patch_write_values(monkeypatch):
    write_calls = []
    monkeypatch.setattr(
        tsu,
        "write_values",
        lambda service, sid, tab, cell_updates: write_calls.append((sid, tab, dict(cell_updates))),
    )
    return write_calls


def test_write_statuses_writes_clean_text_for_classified_results(monkeypatch, app_ctx):
    tracking_values = [["Tracking Number", "Status"], ["ABC123", "old"], ["DEF456", "old"]]
    _connect_fake_sheet(monkeypatch, tracking_values)
    monkeypatch.setattr(tsu, "get_credentials", lambda: object())
    monkeypatch.setattr(tsu, "get_client", lambda creds: object())
    monkeypatch.setattr(tsu, "read_values", lambda service, sid, tab: tracking_values)
    write_calls = _patch_write_values(monkeypatch)

    result = tsu.write_statuses_to_tracking_tab(
        tracking_tab="Sheet1",
        tracking_column_letter="A",
        status_column_letter="B",
        tracking_has_header=True,
        classified_status_by_tracking_number={"ABC123": "DELIVERED", "DEF456": "RETURN"},
        raw_status_by_tracking_number={"ABC123": "Delivered", "DEF456": "Undelivered Due To Incorrect Address"},
    )

    assert result == {"rows_updated": 2}
    sid, tab, cell_updates = write_calls[0]
    assert sid == SPREADSHEET_ID
    assert tab == "Sheet1"
    assert cell_updates == {(2, 2): "Delivered", (3, 2): "Return"}


def test_write_statuses_falls_back_to_raw_text_for_unclassified(monkeypatch, app_ctx):
    tracking_values = [["Tracking Number", "Status"], ["ABC123", "old"]]
    _connect_fake_sheet(monkeypatch, tracking_values)
    monkeypatch.setattr(tsu, "get_credentials", lambda: object())
    monkeypatch.setattr(tsu, "get_client", lambda creds: object())
    monkeypatch.setattr(tsu, "read_values", lambda service, sid, tab: tracking_values)
    write_calls = _patch_write_values(monkeypatch)

    tsu.write_statuses_to_tracking_tab(
        tracking_tab="Sheet1",
        tracking_column_letter="A",
        status_column_letter="B",
        tracking_has_header=True,
        classified_status_by_tracking_number={"ABC123": None},
        raw_status_by_tracking_number={"ABC123": "Out For Delivery"},
    )

    _, _, cell_updates = write_calls[0]
    assert cell_updates == {(2, 2): "Out For Delivery"}


def test_write_statuses_skips_tracking_numbers_not_in_the_sheet(monkeypatch, app_ctx):
    tracking_values = [["Tracking Number", "Status"], ["ABC123", "old"]]
    _connect_fake_sheet(monkeypatch, tracking_values)
    monkeypatch.setattr(tsu, "get_credentials", lambda: object())
    monkeypatch.setattr(tsu, "get_client", lambda creds: object())
    monkeypatch.setattr(tsu, "read_values", lambda service, sid, tab: tracking_values)
    write_calls = _patch_write_values(monkeypatch)

    result = tsu.write_statuses_to_tracking_tab(
        tracking_tab="Sheet1",
        tracking_column_letter="A",
        status_column_letter="B",
        tracking_has_header=True,
        classified_status_by_tracking_number={"NOTINSHEET": "DELIVERED"},
        raw_status_by_tracking_number={"NOTINSHEET": "Delivered"},
    )

    assert result == {"rows_updated": 0}
    _, _, cell_updates = write_calls[0]
    assert cell_updates == {}
