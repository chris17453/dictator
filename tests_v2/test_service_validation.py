"""The D-Bus surface is a trust boundary: any process on the bus may call it."""
import pytest

from dictatord.errors import Fault
from dictatord.service import (
    MAX_LIMIT,
    MAX_NAME,
    MAX_QUERY,
    _bounded,
    _bounded_limit,
)


def test_ordinary_input_passes_through():
    assert _bounded("large-v3-turbo", MAX_NAME, "the model name") == "large-v3-turbo"


def test_oversized_input_is_refused():
    with pytest.raises(Fault, match="limit"):
        _bounded("x" * (MAX_QUERY + 1), MAX_QUERY, "the search query")


def test_control_characters_are_refused():
    """They corrupt terminal output when echoed back in a fault message."""
    with pytest.raises(Fault, match="control characters"):
        _bounded("hello\x00world", MAX_NAME, "the device name")
    with pytest.raises(Fault, match="control characters"):
        _bounded("\x1b[31mred", MAX_NAME, "the device name")


def test_tabs_and_newlines_are_allowed():
    _bounded("a\tb\nc", MAX_NAME, "the query")


def test_non_text_is_refused():
    with pytest.raises(Fault):
        _bounded(1234, MAX_NAME, "the device name")


@pytest.mark.parametrize("given,expected", [
    (0, 20), (1, 1), (50, 50), (MAX_LIMIT + 5000, MAX_LIMIT), (-1, 1),
])
def test_limits_are_clamped_not_rejected(given, expected):
    """An absurd limit is a client bug, not a reason to fail the call."""
    assert _bounded_limit(given) == expected
