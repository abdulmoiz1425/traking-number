def normalize_tracking_number(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float):
        value = int(value) if value.is_integer() else value
    text = str(value).strip()
    if text == "":
        return None
    return text.upper()


def read_tracking_numbers(values, column_index, has_header):
    data_start_row = 2 if has_header else 1
    unique = set()
    total_read = 0
    blanks_ignored = 0
    duplicates_removed = 0

    for row in values[data_start_row - 1 :]:
        raw_value = row[column_index - 1] if column_index - 1 < len(row) else None
        normalized = normalize_tracking_number(raw_value)
        if normalized is None:
            blanks_ignored += 1
            continue
        total_read += 1
        if normalized in unique:
            duplicates_removed += 1
        else:
            unique.add(normalized)

    return {
        "unique_values": unique,
        "total_read": total_read,
        "blanks_ignored": blanks_ignored,
        "duplicates_removed": duplicates_removed,
    }


def find_matches(values, column_index, search_set, has_header):
    data_start_row = 2 if has_header else 1
    matched = set()
    matched_row_numbers = []
    non_blank_scanned = 0

    for offset, row in enumerate(values[data_start_row - 1 :]):
        row_number = data_start_row + offset
        raw_value = row[column_index - 1] if column_index - 1 < len(row) else None
        normalized = normalize_tracking_number(raw_value)
        if normalized is None:
            continue
        non_blank_scanned += 1
        if normalized in search_set:
            matched.add(normalized)
            matched_row_numbers.append(row_number)

    return {
        "matched_values": matched,
        "matched_row_numbers": matched_row_numbers,
        "non_blank_scanned": non_blank_scanned,
    }
