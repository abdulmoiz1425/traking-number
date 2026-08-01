import requests

from app.services import tcs_tracking_service as tts


class _FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")

    def json(self):
        return self._json_data


def _success_body(consignment_no, status_text):
    return {
        "isSuccess": True,
        "responseData": {
            "shipmentinfo": [{"consignmentno": consignment_no}],
            "deliveryinfo": [{"consignmentno": consignment_no, "status": status_text}],
            "message": "SUCCESS",
        },
    }


def _not_found_body():
    return {
        "isSuccess": True,
        "responseData": {
            "shipmentinfo": None,
            "deliveryinfo": None,
            "shipmentsummary": "No Data Found/Invalid CN",
            "message": "SUCCESS",
        },
    }


def test_track_shipment_found(monkeypatch):
    monkeypatch.setattr(
        tts.requests, "post", lambda *a, **k: _FakeResponse(_success_body("173015867181", "Delivered"))
    )
    result = tts.track_shipment("173015867181")
    assert result == {"outcome": "found", "tracking_status": "Delivered"}


def test_track_shipment_not_found_when_deliveryinfo_null(monkeypatch):
    monkeypatch.setattr(tts.requests, "post", lambda *a, **k: _FakeResponse(_not_found_body()))
    result = tts.track_shipment("ZZZQQQXXX999999")
    assert result == {"outcome": "not_found"}


def test_track_shipment_not_found_when_no_exact_match(monkeypatch):
    # Simulates the real cross-contamination quirk observed from TCS: the
    # API returns other shipments (e.g. matched via a reference-number
    # field) instead of the exact consignment number queried. We must
    # refuse to trust any of them rather than report a stranger's status.
    body = {
        "isSuccess": True,
        "responseData": {
            "shipmentinfo": [{"consignmentno": "9147354141"}, {"consignmentno": "9147354116"}],
            "deliveryinfo": [
                {"consignmentno": "9147354141", "status": "Delivered"},
                {"consignmentno": "9147354116", "status": "In Transit"},
            ],
            "message": "SUCCESS",
        },
    }
    monkeypatch.setattr(tts.requests, "post", lambda *a, **k: _FakeResponse(body))
    result = tts.track_shipment("0000000000")
    assert result == {"outcome": "not_found"}


def test_track_shipment_error_when_api_reports_failure(monkeypatch):
    body = {"isSuccess": False, "responseData": {"message": "Something went wrong"}}
    monkeypatch.setattr(tts.requests, "post", lambda *a, **k: _FakeResponse(body))
    result = tts.track_shipment("173015867181")
    assert result["outcome"] == "error"
    assert "Something went wrong" in result["error_message"]


def test_track_shipment_error_on_http_error_status(monkeypatch):
    monkeypatch.setattr(tts.requests, "post", lambda *a, **k: _FakeResponse({}, status_code=500))
    result = tts.track_shipment("173015867181")
    assert result["outcome"] == "error"


def test_track_shipment_error_on_network_exception(monkeypatch):
    def raise_connection_error(*args, **kwargs):
        raise requests.ConnectionError("network down")

    monkeypatch.setattr(tts.requests, "post", raise_connection_error)
    result = tts.track_shipment("173015867181")
    assert result["outcome"] == "error"
    assert "network down" in result["error_message"]


def test_track_shipment_error_on_invalid_json(monkeypatch):
    class BadJsonResponse(_FakeResponse):
        def json(self):
            raise ValueError("not valid json")

    monkeypatch.setattr(tts.requests, "post", lambda *a, **k: BadJsonResponse({}))
    result = tts.track_shipment("173015867181")
    assert result["outcome"] == "error"


def test_track_shipment_empty_input_returns_error():
    result = tts.track_shipment("   ")
    assert result == {"outcome": "error", "error_message": "Empty tracking number."}


def test_track_shipment_sends_expected_payload(monkeypatch):
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return _FakeResponse(_success_body("ABC123", "Delivered"))

    monkeypatch.setattr(tts.requests, "post", fake_post)
    tts.track_shipment(" ABC123 ")

    assert captured["url"] == tts.TCS_API_URL
    assert captured["json"]["body"]["param"] == "consignee=ABC123"
    assert captured["json"]["body"]["url"] == "trackapinew"
