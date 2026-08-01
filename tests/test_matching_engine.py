from app.services.matching_engine import (
    find_status_matches,
    normalize_tracking_number,
    read_tracking_numbers_with_status,
)


def test_normalize_handles_case_and_whitespace():
    assert normalize_tracking_number("  abc123  ") == "ABC123"
    assert normalize_tracking_number("ABC123") == "ABC123"


def test_normalize_preserves_leading_zeros():
    assert normalize_tracking_number("0012345") == "0012345"


def test_normalize_converts_whole_number_floats_without_scientific_notation():
    assert normalize_tracking_number(123456789012.0) == "123456789012"
    assert normalize_tracking_number(123456789012) == "123456789012"


def test_normalize_ignores_blanks():
    assert normalize_tracking_number(None) is None
    assert normalize_tracking_number("") is None
    assert normalize_tracking_number("   ") is None


def test_read_tracking_numbers_with_status_sample():
    values = [
        ["Tracking Number", "Status"],
        ["ABC123", "Delivered"],
        ["DEF456", "Return"],
        ["XYZ789", "Pending"],
    ]
    result = read_tracking_numbers_with_status(values, tracking_column_index=1, status_column_index=2, has_header=True)
    assert result["status_map"] == {"ABC123": "DELIVERED", "DEF456": "RETURN", "XYZ789": "PENDING"}
    assert result["total_read"] == 3
    assert result["blanks_ignored"] == 0
    assert result["duplicates_removed"] == 0


def test_read_tracking_numbers_with_status_dedupes_last_status_wins_and_counts_blanks():
    values = [
        ["Tracking Number", "Status"],
        ["ABC123", "Delivered"],
        [None, "x"],
        ["", "y"],
        ["ABC123", "Return"],
        ["DEF456", "Delivered"],
    ]
    result = read_tracking_numbers_with_status(values, tracking_column_index=1, status_column_index=2, has_header=True)
    assert result["status_map"] == {"ABC123": "RETURN", "DEF456": "DELIVERED"}
    assert result["total_read"] == 3
    assert result["blanks_ignored"] == 2
    assert result["duplicates_removed"] == 1


def test_read_tracking_numbers_with_status_no_header_starts_at_row_one():
    values = [["ABC123", "Delivered"], ["DEF456", "Return"]]
    result = read_tracking_numbers_with_status(values, tracking_column_index=1, status_column_index=2, has_header=False)
    assert result["status_map"] == {"ABC123": "DELIVERED", "DEF456": "RETURN"}
    assert result["total_read"] == 2


def test_read_tracking_numbers_with_status_handles_ragged_rows():
    # Sheets API omits trailing empty cells, so the status column may not
    # exist on a row at all - that should be treated as a blank status.
    values = [["Tracking Number", "Status"], ["ABC123"], ["DEF456", "Return"]]
    result = read_tracking_numbers_with_status(values, tracking_column_index=1, status_column_index=2, has_header=True)
    assert result["status_map"] == {"ABC123": None, "DEF456": "RETURN"}


def test_find_status_matches_srs_sample_colors_correct_rows():
    main_values = [
        ["Order ID", "Customer", "Tracking Number", "Amount"],
        [1001, "Ali", "ABC123", 5000],
        [1002, "Ahmed", "TEST111", 3500],
        [1003, "Sara", "DEF456", 7200],
    ]
    status_map = {"ABC123": "DELIVERED", "DEF456": "RETURN", "XYZ789": "PENDING"}
    result = find_status_matches(main_values, column_index=3, status_map=status_map, has_header=True)

    assert result["delivered_row_numbers"] == [2]
    assert result["return_row_numbers"] == [4]
    assert result["unrecognized_status_rows"] == []
    assert result["matched_values"] == {"ABC123", "DEF456"}
    assert result["non_blank_scanned"] == 3


def test_find_status_matches_unrecognized_status_not_colored_but_counts_as_matched():
    main_values = [["Tracking Number"], ["XYZ789"]]
    status_map = {"XYZ789": "PENDING"}
    result = find_status_matches(main_values, column_index=1, status_map=status_map, has_header=True)

    assert result["unrecognized_status_rows"] == [2]
    assert result["delivered_row_numbers"] == []
    assert result["return_row_numbers"] == []
    assert result["matched_values"] == {"XYZ789"}


def test_find_status_matches_blank_status_treated_as_unrecognized():
    main_values = [["Tracking Number"], ["ABC123"]]
    status_map = {"ABC123": None}
    result = find_status_matches(main_values, column_index=1, status_map=status_map, has_header=True)

    assert result["unrecognized_status_rows"] == [2]
    assert result["matched_values"] == {"ABC123"}


def test_find_status_matches_leading_zeros_do_not_collapse():
    main_values = [["Tracking Number"], ["0012345"], ["12345"]]
    result = find_status_matches(main_values, column_index=1, status_map={"0012345": "DELIVERED"}, has_header=True)
    assert result["delivered_row_numbers"] == [2]


def test_find_status_matches_case_insensitive():
    main_values = [["Tracking Number"], ["ABC123"]]
    result = find_status_matches(main_values, column_index=1, status_map={"ABC123": "DELIVERED"}, has_header=True)
    assert result["delivered_row_numbers"] == [2]

    result_lower_key = find_status_matches(main_values, column_index=1, status_map={"abc123": "DELIVERED"}, has_header=True)
    assert result_lower_key["delivered_row_numbers"] == []  # status_map keys must already be normalized


def test_find_status_matches_duplicate_main_rows_all_highlighted():
    main_values = [["Tracking Number"], ["ABC123"], ["OTHER"], ["ABC123"]]
    result = find_status_matches(main_values, column_index=1, status_map={"ABC123": "RETURN"}, has_header=True)
    assert result["return_row_numbers"] == [2, 4]
    assert result["matched_values"] == {"ABC123"}


def test_find_status_matches_non_blank_scanned_zero_when_column_all_empty():
    main_values = [["Tracking Number", "Amount"], [None, 100], [None, 200]]
    result = find_status_matches(main_values, column_index=1, status_map={"ABC123": "DELIVERED"}, has_header=True)
    assert result["non_blank_scanned"] == 0
    assert result["delivered_row_numbers"] == []
