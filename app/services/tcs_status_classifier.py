from app.services.matching_engine import DELIVERED_STATUS, RETURN_STATUS

# TCS's free-text statuses are far richer than our two canonical outcomes
# (e.g. "Out For Delivery", "Arrived at TCS Facility", "Address Information
# Needed..."). Anything not clearly Delivered or Return is intentionally
# left unclassified (None) - same "leave uncolored rather than guess" rule
# already used for unrecognized values in a manually-typed Status column.
_UNDELIVERED_EXCLUSIONS = ("undelivered", "not delivered", "non delivered", "non-delivered")
_RETURN_KEYWORDS = ("return", "rto", "undelivered", "not delivered", "non delivered", "non-delivered")


def classify_tcs_status(raw_status):
    """Map a raw TCS status string (e.g. "Undelivered Due To Incorrect
    Address") to this app's canonical DELIVERED_STATUS/RETURN_STATUS
    values, or None if it doesn't clearly indicate either outcome yet."""
    if not raw_status:
        return None
    text = raw_status.strip().lower()

    # "delivered" is a substring of "undelivered", so a plain `in` check
    # would misclassify failed deliveries as successful ones - must check
    # for the negated form first.
    if "delivered" in text and not any(neg in text for neg in _UNDELIVERED_EXCLUSIONS):
        return DELIVERED_STATUS

    if any(keyword in text for keyword in _RETURN_KEYWORDS):
        return RETURN_STATUS

    return None
