import pytest

from streamstats.errors import InvalidEventError
from streamstats.models import parse_event

GOOD = {
    "timestamp": "2026-10-07T12:00:00+03:00",
    "level": "INFO",
    "source": "api",
    "message": "ok",
}


@pytest.mark.parametrize(
    ("field", "value", "fragment"),
    [
        ("source", None, "missing field"),
        ("source", "", "empty value"),
        ("source", "   ", "empty value"),
        ("level", "info", "unknown level"),
        ("timestamp", 123, "must be a string"),
    ],
)
def test_parse_event_rejects_bad_field(field, value, fragment):
    record = {**GOOD, field: value}
    with pytest.raises(InvalidEventError, match=fragment):
        parse_event(record)
