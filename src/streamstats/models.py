from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from streamstats.errors import InvalidEventError, InvalidTimestampError

LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
ERROR_LEVELS = ("ERROR", "CRITICAL")


@dataclass(frozen=True)
class Event:
    timestamp: datetime
    timestamp_text: str
    level: str
    source: str
    message: str


def _read_text_field(
    record: Mapping[str, object], name: str, *, allow_empty: bool = False
) -> str:
    """Return a field value as a string or raise InvalidEventError"""
    value = record.get(name)
    if value is None:
        raise InvalidEventError(f"missing field '{name}'")
    if not isinstance(value, str):
        raise InvalidEventError(f"field '{name}' must be a string")
    if not allow_empty and not value.strip():
        raise InvalidEventError(f"empty value in field '{name}'")
    return value


def parse_timestamp(text: str) -> datetime:
    """Parse an ISO 8601 timestamp; naive values are treated as UTC"""
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as error:
        raise InvalidTimestampError(f"invalid timestamp: {text!r}") from error
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment


def parse_event(record: Mapping[str, object]) -> Event:
    """Validate a raw record and build an Event"""
    timestamp_text = _read_text_field(record, "timestamp")
    timestamp = parse_timestamp(timestamp_text)
    level = _read_text_field(record, "level")
    if level not in LEVELS:
        raise InvalidEventError(f"unknown level {level!r}")
    source = _read_text_field(record, "source")
    message = _read_text_field(record, "message", allow_empty=True)
    return Event(
        timestamp=timestamp,
        timestamp_text=timestamp_text,
        level=level,
        source=source,
        message=message,
    )
