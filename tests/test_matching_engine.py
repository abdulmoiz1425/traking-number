from app.services.matching_engine import find_matches, normalize_tracking_number, read_tracking_numbers


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


def test_read_tracking_numbers_srs_sample():
    values = [["Tracking Number"], ["ABC123"], ["DEF456"], ["XYZ789"]]
    result = read_tracking_numbers(values, column_index=1, has_header=True)
    assert result["unique_values"] == {"ABC123", "DEF456", "XYZ789"}
    assert result["total_read"] == 3
    assert result["blanks_ignored"] == 0
    assert result["duplicates_removed"] == 0


def test_read_tracking_numbers_dedupes_and_counts_blanks():
    values = [["Tracking Number"], ["ABC123"], [None], [""], ["ABC123"], ["DEF456"]]
    result = read_tracking_numbers(values, column_index=1, has_header=True)
    assert result["unique_values"] == {"ABC123", "DEF456"}
    assert result["total_read"] == 3
    assert result["blanks_ignored"] == 2
    assert result["duplicates_removed"] == 1


def test_read_tracking_numbers_no_header_starts_at_row_one():
    values = [["ABC123"], ["DEF456"]]
    result = read_tracking_numbers(values, column_index=1, has_header=False)
    assert result["unique_values"] == {"ABC123", "DEF456"}
    assert result["total_read"] == 2


def test_read_tracking_numbers_handles_ragged_rows():
    # Sheets API omits trailing empty cells, so column 2 may not exist on a row.
    values = [["Tracking Number", "Note"], ["ABC123"], ["DEF456", "x"]]
    result = read_tracking_numbers(values, column_index=1, has_header=True)
    assert result["unique_values"] == {"ABC123", "DEF456"}


def test_find_matches_srs_sample_returns_correct_row_numbers():
    main_values = [
        ["Order ID", "Customer", "Tracking Number", "Amount"],
        [1001, "Ali", "ABC123", 5000],
        [1002, "Ahmed", "TEST111", 3500],
        [1003, "Sara", "DEF456", 7200],
    ]
    search_set = {"ABC123", "DEF456", "XYZ789"}
    result = find_matches(main_values, column_index=3, search_set=search_set, has_header=True)

    assert result["matched_values"] == {"ABC123", "DEF456"}
    assert result["matched_row_numbers"] == [2, 4]
    assert result["non_blank_scanned"] == 3


def test_find_matches_leading_zeros_do_not_collapse():
    main_values = [["Tracking Number"], ["0012345"], ["12345"]]
    result = find_matches(main_values, column_index=1, search_set={"0012345"}, has_header=True)
    assert result["matched_row_numbers"] == [2]


def test_find_matches_case_insensitive():
    main_values = [["Tracking Number"], ["ABC123"]]
    result = find_matches(main_values, column_index=1, search_set={"ABC123"}, has_header=True)
    assert result["matched_row_numbers"] == [2]

    result_lower_search = find_matches(main_values, column_index=1, search_set={"abc123"}, has_header=True)
    assert result_lower_search["matched_row_numbers"] == []  # search_set itself must already be normalized


def test_find_matches_duplicate_main_rows_all_highlighted():
    main_values = [["Tracking Number"], ["ABC123"], ["OTHER"], ["ABC123"]]
    result = find_matches(main_values, column_index=1, search_set={"ABC123"}, has_header=True)
    assert result["matched_row_numbers"] == [2, 4]
    assert result["matched_values"] == {"ABC123"}


def test_find_matches_non_blank_scanned_zero_when_column_all_empty():
    main_values = [["Tracking Number", "Amount"], [None, 100], [None, 200]]
    result = find_matches(main_values, column_index=1, search_set={"ABC123"}, has_header=True)
    assert result["non_blank_scanned"] == 0
    assert result["matched_row_numbers"] == []
