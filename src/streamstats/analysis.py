import logging
from collections import Counter
from collections.abc import Iterator, Sequence
from datetime import datetime
from pathlib import Path

from streamstats.errors import CliConfigurationError, InvalidEventError
from streamstats.models import ERROR_LEVELS, Event, parse_event
from streamstats.parsers import RawRecord, get_parser

logger = logging.getLogger(__name__)


class StreamStats:
    """Accumulates statistics event by event without storing the events"""

    def __init__(self) -> None:
        self.total_events = 0
        self.skipped_lines = 0
        self.levels: Counter[str] = Counter()
        self.sources: Counter[str] = Counter()
        self.error_sources: Counter[str] = Counter()
        self._first: tuple[datetime, str] | None = None
        self._last: tuple[datetime, str] | None = None

    def add(self, event: Event) -> None:
        """Take one event into account"""
        self.total_events += 1
        self.levels[event.level] += 1
        self.sources[event.source] += 1
        if event.level in ERROR_LEVELS:
            self.error_sources[event.source] += 1
        stamp = (event.timestamp, event.timestamp_text)
        if self._first is None or stamp < self._first:
            self._first = stamp
        if self._last is None or stamp > self._last:
            self._last = stamp

    @property
    def first_timestamp(self) -> str | None:
        """Original text of the earliest timestamp or None if there are no events"""
        return None if self._first is None else self._first[1]

    @property
    def last_timestamp(self) -> str | None:
        """Original text of the latest timestamp or None if there are no events"""
        return None if self._last is None else self._last[1]

    def top_error_sources(self, limit: int = 5) -> list[tuple[str, int]]:
        """Sources of ERROR and CRITICAL events: by count descending, then by name"""
        ranked = sorted(
            self.error_sources.items(), key=lambda item: (-item[1], item[0])
        )
        return ranked[:limit]


def _build_event(record: RawRecord) -> Event:
    """Turn a raw record into an event or raise InvalidEventError"""
    if record.problem is not None:
        raise InvalidEventError(record.problem)
    return parse_event(record.data)


def iter_events(
    path: Path, fmt: str, stats: StreamStats, *, skip_invalid: bool = False
) -> Iterator[Event]:
    """Lazily read, parse and validate a file, applying the error policy"""
    parser = get_parser(fmt)
    try:
        for record in parser(path):
            try:
                event = _build_event(record)
            except InvalidEventError as error:
                if not skip_invalid:
                    raise type(error)(f"{path}:{record.line_number}: {error}") from error
                logger.warning(
                    "%s:%d: skipped invalid record: %s", path, record.line_number, error
                )
                stats.skipped_lines += 1
                continue
            yield event
    except OSError as error:
        raise CliConfigurationError(f"cannot read {path}: {error}") from error
    except UnicodeDecodeError as error:
        raise CliConfigurationError(f"{path}: file is not valid UTF-8") from error


def process_file(
    path: Path, fmt: str, stats: StreamStats, *, skip_invalid: bool = False
) -> None:
    """Add all events of one file to the shared statistics"""
    events_before = stats.total_events
    skipped_before = stats.skipped_lines
    logger.info("processing %s as %s", path, fmt)
    for event in iter_events(path, fmt, stats, skip_invalid=skip_invalid):
        stats.add(event)
    logger.info(
        "finished %s: %d events, %d skipped",
        path,
        stats.total_events - events_before,
        stats.skipped_lines - skipped_before,
    )


def analyze_files(
    paths: Sequence[Path], fmt: str, *, skip_invalid: bool = False
) -> StreamStats:
    """Process files one after another into one combined statistics"""
    stats = StreamStats()
    for path in paths:
        process_file(path, fmt, stats, skip_invalid=skip_invalid)
    return stats
