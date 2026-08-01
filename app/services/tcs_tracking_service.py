import requests

TCS_API_URL = "https://www.tcsexpress.com/apibridge"

_HEADERS = {
    "Content-Type": "application/json; charset=UTF-8",
    "Accept": "application/json, text/plain, */*",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def track_shipment(tracking_number, timeout=15):
    """Look up a TCS Express shipment's current status via TCS's own
    internal tracking API (the same one their tracking page calls) - no
    browser automation needed.

    Always returns a dict, never raises, so a batch of lookups can treat
    every tracking number uniformly:
      {"outcome": "found", "tracking_status": "..."}
      {"outcome": "not_found"}
      {"outcome": "error", "error_message": "..."}
    """
    tracking_number = (tracking_number or "").strip()
    if not tracking_number:
        return {"outcome": "error", "error_message": "Empty tracking number."}

    payload = {
        "body": {
            "url": "trackapinew",
            "type": "GET",
            "headers": {},
            "payload": {},
            "param": f"consignee={tracking_number}",
        }
    }

    try:
        response = requests.post(TCS_API_URL, headers=_HEADERS, json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        return {"outcome": "error", "error_message": str(exc)}

    if not data.get("isSuccess"):
        message = (data.get("responseData") or {}).get("message", "Unknown error from TCS.")
        return {"outcome": "error", "error_message": message}

    delivery_info = (data.get("responseData") or {}).get("deliveryinfo") or []

    # TCS's API can return unrelated shipments for some queries (observed:
    # it also matches against a "reference number" field, not just the
    # exact consignment number) - only trust an entry whose consignmentno
    # is an exact match for what we asked for, so we never report a
    # stranger's shipment status as the user's own.
    match = next((entry for entry in delivery_info if entry.get("consignmentno") == tracking_number), None)
    if match is None:
        return {"outcome": "not_found"}

    return {"outcome": "found", "tracking_status": match.get("status")}
