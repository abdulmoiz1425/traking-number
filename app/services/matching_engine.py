DELIVERED_STATUS = "DELIVERED"
RETURN_STATUS = "RETURN"


def normalize_tracking_number(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float):
        value = int(value) if value.is_integer() else value
    text = str(value).strip()
    if text == "":
        return None
    return text.upper()


def _read_tracking_pairs(values, tracking_column_index, other_column_index, has_header):
    data_start_row = 2 if has_header else 1
    pair_map = {}
    total_read = 0
    blanks_ignored = 0
    duplicates_removed = 0

    for row in values[data_start_row - 1 :]:
        raw_tracking = row[tracking_column_index - 1] if tracking_column_index - 1 < len(row) else None
        normalized = normalize_tracking_number(raw_tracking)
        if normalized is None:
            blanks_ignored += 1
            continue
        total_read += 1
        if normalized in pair_map:
            duplicates_removed += 1

        raw_other = row[other_column_index - 1] if other_column_index - 1 < len(row) else None
        pair_map[normalized] = raw_other

    return {
        "pair_map": pair_map,
        "total_read": total_read,
        "blanks_ignored": blanks_ignored,
        "duplicates_removed": duplicates_removed,
    }


def read_tracking_numbers_with_status(values, tracking_column_index, status_column_index, has_header):
    result = _read_tracking_pairs(values, tracking_column_index, status_column_index, has_header)
    # Same normalization as tracking numbers (trim, uppercase) - blank cells
    # become None, meaning "no recognized status" downstream.
    status_map = {
        tracking: normalize_tracking_number(raw_status) for tracking, raw_status in result["pair_map"].items()
    }
    return {
        "status_map": status_map,
        "total_read": result["total_read"],
        "blanks_ignored": result["blanks_ignored"],
        "duplicates_removed": result["duplicates_removed"],
    }


def read_tracking_numbers_with_value(values, tracking_column_index, value_column_index, has_header):
    result = _read_tracking_pairs(values, tracking_column_index, value_column_index, has_header)
    # Unlike status, the value is kept as-is (not uppercased/stringified) so
    # numeric Net Payable amounts get written back as numbers, not text.
    value_map = {
        tracking: raw_value for tracking, raw_value in result["pair_map"].items() if raw_value not in (None, "")
    }
    return {
        "value_map": value_map,
        "total_read": result["total_read"],
        "blanks_ignored": result["blanks_ignored"],
        "duplicates_removed": result["duplicates_removed"],
    }


def find_status_matches(values, column_index, status_map, has_header):
    data_start_row = 2 if has_header else 1
    matched_values = set()
    delivered_row_numbers = []
    return_row_numbers = []
    unrecognized_status_rows = []
    non_blank_scanned = 0

    for offset, row in enumerate(values[data_start_row - 1 :]):
        row_number = data_start_row + offset
        raw_value = row[column_index - 1] if column_index - 1 < len(row) else None
        normalized = normalize_tracking_number(raw_value)
        if normalized is None:
            continue
        non_blank_scanned += 1
        if normalized not in status_map:
            continue

        matched_values.add(normalized)
        status = status_map[normalized]
        if status == DELIVERED_STATUS:
            delivered_row_numbers.append(row_number)
        elif status == RETURN_STATUS:
            return_row_numbers.append(row_number)
        else:
            unrecognized_status_rows.append(row_number)

    return {
        "matched_values": matched_values,
        "delivered_row_numbers": delivered_row_numbers,
        "return_row_numbers": return_row_numbers,
        "unrecognized_status_rows": unrecognized_status_rows,
        "non_blank_scanned": non_blank_scanned,
    }


def find_value_updates(values, column_index, value_map, has_header):
    data_start_row = 2 if has_header else 1
    updates = {}
    matched_values = set()

    for offset, row in enumerate(values[data_start_row - 1 :]):
        row_number = data_start_row + offset
        raw_value = row[column_index - 1] if column_index - 1 < len(row) else None
        normalized = normalize_tracking_number(raw_value)
        if normalized is None or normalized not in value_map:
            continue
        updates[row_number] = value_map[normalized]
        matched_values.add(normalized)

    return {"updates": updates, "matched_values": matched_values}
