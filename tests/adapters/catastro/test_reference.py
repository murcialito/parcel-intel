import pytest

from parcel_intel.adapters.catastro.reference import to_compact_reference
from parcel_intel.ports.errors import InvalidCadastralReferenceError


def test_already_compact_reference_is_returned_as_is() -> None:
    assert to_compact_reference("99043A90100001") == "99043A90100001"


def test_full_20_character_reference_is_truncated_to_compact_form() -> None:
    assert to_compact_reference("99043A901000010000AQ") == "99043A90100001"


def test_lowercase_and_surrounding_whitespace_are_normalized() -> None:
    assert to_compact_reference("  99043a90100001  ") == "99043A90100001"


@pytest.mark.parametrize("bad_reference", ["", "123", "99043A9010000100001234"])
def test_invalid_length_raises(bad_reference: str) -> None:
    with pytest.raises(InvalidCadastralReferenceError):
        to_compact_reference(bad_reference)
