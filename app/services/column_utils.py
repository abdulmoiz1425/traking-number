HEADER_CANDIDATES = {
    "tracking number", "tracking no", "tracking #", "tracking id",
    "shipment tracking", "awb", "awb number",
    "consignment number", "consignment no", "reference number",
}

STATUS_HEADER_CANDIDATES = {
    "status", "delivery status", "shipment status", "order status",
}

NET_PAYABLE_HEADER_CANDIDATES = {
    "net payable", "net amount", "payable amount", "amount payable",
}


def detect_tracking_column(columns):
    for column in columns:
        if column["header"].strip().lower() in HEADER_CANDIDATES:
            return column["letter"]
    return None


def detect_status_column(columns):
    for column in columns:
        if column["header"].strip().lower() in STATUS_HEADER_CANDIDATES:
            return column["letter"]
    return None


def detect_net_payable_column(columns):
    for column in columns:
        if column["header"].strip().lower() in NET_PAYABLE_HEADER_CANDIDATES:
            return column["letter"]
    return None
