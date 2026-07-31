import pytest

from app import create_app, routes
from app.services import sheets_processing_service as sps


@pytest.fixture
def client():
    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as client:
        yield client


def _patch_sheets(monkeypatch):
    monkeypatch.setattr(sps, "get_credentials", lambda: object())
    monkeypatch.setattr(sps, "get_client", lambda creds: object())
    monkeypatch.setattr(sps, "get_spreadsheet_title", lambda service, sid: {"tid": "Tracking", "mid": "Main"}[sid])
    monkeypatch.setattr(
        sps,
        "list_tabs",
        lambda service, sid: {
            "tid": [{"title": "Sheet1", "sheet_id": 0}],
            "mid": [{"title": "Orders", "sheet_id": 5}],
        }[sid],
    )
    monkeypatch.setattr(
        sps,
        "read_values",
        lambda service, sid, tab: {
            ("tid", "Sheet1"): [["Tracking Number"], ["ABC123"], ["DEF456"]],
            ("mid", "Orders"): [["Order ID", "Tracking Number"], [1, "ABC123"], [2, "NOPE"]],
        }[(sid, tab)],
    )
    monkeypatch.setattr(sps, "highlight_rows", lambda *args, **kwargs: None)


def test_index_serves_ok(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_service_account_email_when_configured(client, monkeypatch):
    monkeypatch.setattr(routes, "get_service_account_email", lambda: "bot@project.iam.gserviceaccount.com")
    resp = client.get("/service-account-email")
    assert resp.get_json() == {"email": "bot@project.iam.gserviceaccount.com"}


def test_service_account_email_when_not_configured(client):
    # No real service_account.json present in the test environment, so the
    # real (unmocked) credential loader reports its own clear error instead
    # of throwing.
    resp = client.get("/service-account-email")
    data = resp.get_json()
    assert data["email"] is None
    assert "not configured" in data["error"].lower()


def test_sheets_status_false_when_nothing_connected(client):
    resp = client.get("/sheets-status")
    assert resp.get_json() == {"connected": False}


def test_connect_sheets_requires_credentials_when_unconfigured(client):
    resp = client.post("/connect-sheets", json={"tracking_sheet_url": "x", "main_sheet_url": "y"})
    assert resp.status_code == 400
    assert "not configured" in resp.get_json()["error"].lower()


def test_connect_sheets_requires_both_links(client):
    resp = client.post("/connect-sheets", json={"tracking_sheet_url": "x"})
    assert resp.status_code == 400
    assert "both" in resp.get_json()["error"].lower()


def test_full_connect_process_download_reset_flow(client, monkeypatch):
    _patch_sheets(monkeypatch)

    connect_resp = client.post(
        "/connect-sheets",
        json={
            "tracking_sheet_url": "https://docs.google.com/spreadsheets/d/tid/edit",
            "main_sheet_url": "https://docs.google.com/spreadsheets/d/mid/edit",
        },
    )
    assert connect_resp.status_code == 200
    connect_data = connect_resp.get_json()
    assert connect_data["tracking_file"]["detected_column"] == "A"
    assert connect_data["main_file"]["detected_column"] == "B"

    process_resp = client.post(
        "/process",
        json={
            "tracking_sheet": "Sheet1",
            "tracking_column": "A",
            "main_sheet": "Orders",
            "main_column": "B",
        },
    )
    assert process_resp.status_code == 200
    result = process_resp.get_json()
    assert result["summary"]["tracking_numbers_matched"] == 1
    assert result["summary"]["tracking_numbers_not_matched"] == 1
    assert result["main_sheet_url"] == "https://docs.google.com/spreadsheets/d/mid/edit"

    unmatched_resp = client.get(f"/download-unmatched/{result['unmatched_token']}")
    assert unmatched_resp.status_code == 200
    assert unmatched_resp.headers["Content-Disposition"].startswith("attachment")

    status_resp = client.get("/sheets-status")
    status = status_resp.get_json()
    assert status["connected"] is True
    assert status["tracking_url"] == "https://docs.google.com/spreadsheets/d/tid/edit"
    assert status["result"]["summary"]["tracking_numbers_matched"] == 1

    worksheet_columns_resp = client.get("/worksheet-columns?file=main&sheet=Orders")
    assert worksheet_columns_resp.status_code == 200
    assert worksheet_columns_resp.get_json()["detected_column"] == "B"

    reset_resp = client.post("/reset")
    assert reset_resp.status_code == 200

    status_after_reset = client.get("/sheets-status").get_json()
    assert status_after_reset["connected"] is False

    process_after_reset = client.post(
        "/process",
        json={"tracking_sheet": "Sheet1", "tracking_column": "A", "main_sheet": "Orders", "main_column": "B"},
    )
    assert process_after_reset.status_code == 400


def test_process_missing_column_selection_returns_error(client, monkeypatch):
    _patch_sheets(monkeypatch)
    client.post(
        "/connect-sheets",
        json={
            "tracking_sheet_url": "https://docs.google.com/spreadsheets/d/tid/edit",
            "main_sheet_url": "https://docs.google.com/spreadsheets/d/mid/edit",
        },
    )
    resp = client.post("/process", json={"tracking_sheet": "Sheet1", "main_sheet": "Orders"})
    assert resp.status_code == 400


def test_download_unmatched_with_invalid_token_returns_404(client):
    resp = client.get("/download-unmatched/not-a-real-token")
    assert resp.status_code == 404
