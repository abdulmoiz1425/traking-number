import pytest

from app import create_app, routes
from app.services import sheets_processing_service as sps

SPREADSHEET_ID = "sheet-id-with-enough-characters-000"
TABS = [{"title": "Sheet1", "sheet_id": 0}, {"title": "Orders", "sheet_id": 5}, {"title": "NetPayable", "sheet_id": 9}]
VALUES = {
    "Sheet1": [["Tracking Number", "Status"], ["ABC123", "Delivered"], ["DEF456", "Return"]],
    "Orders": [["Order ID", "Tracking Number"], [1, "ABC123"], [2, "NOPE"]],
    "NetPayable": [["Tracking Number", "Net Payable"], ["ABC123", 4500]],
}


@pytest.fixture
def client():
    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as client:
        yield client


def _patch_sheets(monkeypatch):
    monkeypatch.setattr(sps, "get_credentials", lambda: object())
    monkeypatch.setattr(sps, "get_client", lambda creds: object())
    monkeypatch.setattr(sps, "get_spreadsheet_title", lambda service, sid: "Tracking + Orders")
    monkeypatch.setattr(sps, "list_tabs", lambda service, sid: TABS)
    monkeypatch.setattr(sps, "read_values", lambda service, sid, tab: VALUES[tab])
    monkeypatch.setattr(sps, "highlight_rows", lambda *args, **kwargs: None)
    monkeypatch.setattr(sps, "write_values", lambda *args, **kwargs: None)


def _connect(client):
    return client.post("/connect-sheet", json={"spreadsheet_id": SPREADSHEET_ID})


def test_index_serves_ok(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_auth_status_false_when_not_signed_in(client):
    resp = client.get("/auth-status")
    assert resp.get_json() == {"authenticated": False}


def test_google_login_redirects(client, monkeypatch):
    monkeypatch.setattr(routes, "get_authorization_url", lambda: "https://accounts.google.com/o/oauth2/auth?fake=1")
    resp = client.get("/google/login")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "https://accounts.google.com/o/oauth2/auth?fake=1"


def test_google_callback_with_denied_consent_redirects_home_with_flag(client):
    resp = client.get("/google/callback?error=access_denied")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/?auth_error=consent_denied"


def test_google_logout_calls_clear_credentials(client, monkeypatch):
    calls = []
    monkeypatch.setattr(routes, "clear_credentials", lambda: calls.append("credentials"))
    monkeypatch.setattr(routes, "clear_sheets_session", lambda: calls.append("sheets"))
    resp = client.post("/google/logout")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "signed_out"}
    assert calls == ["credentials", "sheets"]


def test_picker_token_requires_sign_in(client):
    resp = client.get("/picker-token")
    assert resp.status_code == 400
    assert "sign in" in resp.get_json()["error"].lower()


def test_sheets_status_false_when_nothing_connected(client):
    resp = client.get("/sheets-status")
    assert resp.get_json() == {"connected": False}


def test_connect_sheet_requires_sign_in(client):
    resp = client.post("/connect-sheet", json={"spreadsheet_id": SPREADSHEET_ID})
    assert resp.status_code == 400
    assert "sign in" in resp.get_json()["error"].lower()


def test_connect_sheet_requires_spreadsheet_id(client):
    resp = client.post("/connect-sheet", json={})
    assert resp.status_code == 400
    assert "no google sheet was selected" in resp.get_json()["error"].lower()


def test_full_connect_process_download_reset_flow(client, monkeypatch):
    _patch_sheets(monkeypatch)

    connect_resp = _connect(client)
    assert connect_resp.status_code == 200
    connect_data = connect_resp.get_json()
    assert connect_data["tracking_tab"] == "Sheet1"
    assert connect_data["main_tab"] == "Orders"
    assert connect_data["net_payable_tab"] == "NetPayable"
    assert connect_data["tracking_file"]["detected_column"] == "A"
    assert connect_data["tracking_file"]["detected_status_column"] == "B"
    assert connect_data["main_file"]["detected_column"] == "B"
    assert connect_data["net_payable_file"]["detected_net_payable_column"] == "B"

    process_resp = client.post(
        "/process",
        json={
            "tracking_tab": "Sheet1",
            "tracking_column": "A",
            "tracking_status_column": "B",
            "main_tab": "Orders",
            "main_column": "B",
            "net_payable_tab": "NetPayable",
            "net_payable_tracking_column": "A",
            "net_payable_value_column": "B",
        },
    )
    assert process_resp.status_code == 200
    result = process_resp.get_json()
    assert result["summary"]["tracking_numbers_matched"] == 1
    assert result["summary"]["tracking_numbers_not_matched"] == 1
    assert result["summary"]["rows_marked_delivered"] == 1
    assert result["summary"]["rows_marked_return"] == 0
    assert result["summary"]["net_payable_rows_updated"] == 1
    assert result["main_sheet_url"] == f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"

    unmatched_resp = client.get(f"/download-unmatched/{result['unmatched_token']}")
    assert unmatched_resp.status_code == 200
    assert unmatched_resp.headers["Content-Disposition"].startswith("attachment")

    status_resp = client.get("/sheets-status")
    status = status_resp.get_json()
    assert status["connected"] is True
    assert status["spreadsheet_title"] == "Tracking + Orders"
    assert status["result"]["summary"]["tracking_numbers_matched"] == 1

    worksheet_columns_resp = client.get("/worksheet-columns?tab=Orders")
    assert worksheet_columns_resp.status_code == 200
    assert worksheet_columns_resp.get_json()["detected_column"] == "B"

    reset_resp = client.post("/reset")
    assert reset_resp.status_code == 200

    status_after_reset = client.get("/sheets-status").get_json()
    assert status_after_reset["connected"] is False

    process_after_reset = client.post(
        "/process",
        json={"tracking_tab": "Sheet1", "tracking_column": "A", "main_tab": "Orders", "main_column": "B"},
    )
    assert process_after_reset.status_code == 400


def test_process_missing_column_selection_returns_error(client, monkeypatch):
    _patch_sheets(monkeypatch)
    _connect(client)
    resp = client.post("/process", json={"tracking_tab": "Sheet1", "main_tab": "Orders"})
    assert resp.status_code == 400


def test_download_unmatched_with_invalid_token_returns_404(client):
    resp = client.get("/download-unmatched/not-a-real-token")
    assert resp.status_code == 404
