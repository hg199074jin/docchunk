import pytest

from docchunk.models.pdf import (
    format_page_ranges,
    page_index_to_number,
    page_number_to_index,
)


def test_page_index_conversion_is_the_single_boundary() -> None:
    assert page_index_to_number(0) == 1
    assert page_index_to_number(37) == 38
    assert page_number_to_index(1) == 0
    assert page_number_to_index(38) == 37


@pytest.mark.parametrize("value", [-1])
def test_page_index_rejects_negative_values(value: int) -> None:
    with pytest.raises(ValueError, match="page_idx"):
        page_index_to_number(value)


def test_page_number_rejects_zero() -> None:
    with pytest.raises(ValueError, match="page_number"):
        page_number_to_index(0)


def test_format_page_ranges_compacts_human_page_numbers() -> None:
    assert format_page_ranges([3, 1, 2, 7, 9, 8]) == "1-3, 7-9"
    assert format_page_ranges([]) == "none"
