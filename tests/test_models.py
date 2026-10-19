from datetime import timedelta

import pytest

from streamstats.errors import InvalidEventError, InvalidTimestampError
from streamstats.models import LEVELS, parse_event, parse_timestamp

GOOD = {
    "timestamp": "2026-10-07T12:00:00+03:00",
    "level": "INFO",
    "source": "api",
    "message": "ok",
}


def test_parse_event_builds_event_from_valid_record() -> None:
    event = parse_event(GOOD)
    assert event.level == "INFO"
    assert event.source == "api"
    assert event.message == "ok"
    assert event.timestamp_text == "2026-10-07T12:00:00+03:00"
    assert event.timestamp.utcoffset() == timedelta(hours=3)


@pytest.mark.parametrize("level", LEVELS)
def test_all_levels_are_accepted(level: str) -> None:
    assert parse_event({**GOOD, "level": level}).level == level


@pytest.mark.parametrize("field", ["timestamp", "level", "source", "message"])
def test_missing_field_is_rejected(field: str) -> None:
    record = {key: value for key, value in GOOD.items() if key != field}
    with pytest.raises(InvalidEventError, match="missing field"):
        parse_event(record)


@pytest.mark.parametrize(
    ("field", "value", "fragment"),
    [
        ("source", None, "missing field"),
        ("source", "", "empty value"),
        ("source", "   ", "empty value"),
        ("source", 5, "must be a string"),
        ("level", "", "empty value"),
        ("level", "info", "unknown level"),
        ("level", "FATAL", "unknown level"),
        ("timestamp", "", "empty value"),
        ("timestamp", 123, "must be a string"),
        ("message", 7, "must be a string"),
    ],
)
def test_parse_event_rejects_bad_field(
    field: str, value: object, fragment: str
) -> None:
    record = {**GOOD, field: value}
    with pytest.raises(InvalidEventError, match=fragment):
        parse_event(record)


def test_empty_message_is_allowed() -> None:
    assert parse_event({**GOOD, "message": ""}).message == ""


@pytest.mark.parametrize(
    "text", ["yesterday", "07.10.2026 12:00", "2026-13-01T00:00:00"]
)
def test_bad_timestamp_raises_timestamp_error(text: str) -> None:
    with pytest.raises(InvalidTimestampError):
        parse_event({**GOOD, "timestamp": text})


def test_timestamp_error_is_also_an_event_error() -> None:
    assert issubclass(InvalidTimestampError, InvalidEventError)


def test_timestamp_without_zone_is_treated_as_utc() -> None:
    moment = parse_timestamp("2026-10-07T09:00:00")
    assert moment.utcoffset() == timedelta(0)
    assert moment == parse_timestamp("2026-10-07T09:00:00Z")


def test_same_moment_in_different_zones_is_equal() -> None:
    assert parse_timestamp("2026-10-07T12:00:00+03:00") == parse_timestamp(
        "2026-10-07T09:00:00Z"
    )


def test_event_cannot_be_changed() -> None:
    event = parse_event(GOOD)
    with pytest.raises(AttributeError):
        setattr(event, "level", "ERROR")  # noqa: B010
