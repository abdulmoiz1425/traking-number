import pytest

from app.services.matching_engine import DELIVERED_STATUS, RETURN_STATUS
from app.services.tcs_status_classifier import classify_tcs_status


@pytest.mark.parametrize(
    "raw_status,expected",
    [
        ("Delivered", DELIVERED_STATUS),
        ("delivered", DELIVERED_STATUS),
        ("  Delivered  ", DELIVERED_STATUS),
        ("Delivered Successfully", DELIVERED_STATUS),
        ("Shipment Delivered to Consignee", DELIVERED_STATUS),
        ("Undelivered Due To Incorrect Address", RETURN_STATUS),
        ("Not Delivered - Consignee Refused", RETURN_STATUS),
        ("Returned to Shipper", RETURN_STATUS),
        ("Return to Origin", RETURN_STATUS),
        ("RTO", RETURN_STATUS),
        ("Out For Delivery", None),
        ("Arrived at TCS Facility", None),
        ("Departed From TCS Facility", None),
        ("Shipment Picked Up", None),
        ("Address Information Needed (For Additional Info Contact Local TCS Office)", None),
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_classify_tcs_status(raw_status, expected):
    assert classify_tcs_status(raw_status) == expected
