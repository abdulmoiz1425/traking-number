HEADER_CANDIDATES = {
    "tracking number", "tracking no", "tracking #", "tracking id",
    "shipment tracking", "awb", "awb number",
    "consignment number", "consignment no", "reference number",
}


def detect_tracking_column(columns):
    for column in columns:
        if column["header"].strip().lower() in HEADER_CANDIDATES:
            return column["letter"]
    return None
