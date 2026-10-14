import logging
from pathlib import Path

import pytest

from streamstats.analysis import StreamStats, analyze_files, iter_events, process_file
from streamstats.errors import (
    CliConfigurationError,
    InvalidEventError,
    InvalidTimestampError,
    UnsupportedFormatError,
)
from streamstats.models import Event, parse_event

HEADER = "timestamp,level,source,message\n"


def make_event(
    timestamp: str = "2026-10-07T12:00:00Z",
    level: str = "INFO",
    source: str = "api",
) -> Event:
    return parse_event(
        {"timestamp": timestamp, "level": level, "source": source, "message": "m"}
    )


def write_csv(path: Path, *rows: str) -> Path:
    path.write_text(HEADER + "".join(row + "\n" for row in rows), encoding="utf-8")
    return path


def test_add_counts_events_by_level_and_source() -> None:
    stats = StreamStats()
    stats.add(make_event(level="INFO", source="api"))
    stats.add(make_event(level="INFO", source="db"))
    stats.add(make_event(level="ERROR", source="db"))
    assert stats.total_events == 3
    assert stats.levels == {"INFO": 2, "ERROR": 1}
    assert stats.sources == {"api": 1, "db": 2}


def test_error_sources_count_only_error_and_critical() -> None:
    stats = StreamStats()
    for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        stats.add(make_event(level=level, source="db"))
    assert stats.error_sources == {"db": 2}


def test_first_and_last_timestamp_respect_time_zones() -> None:
    stats = StreamStats()
    # 12:00+03:00 is 09:00 UTC, so it is EARLIER than 09:30Z,
    # although as plain text "09:30Z" sorts before "12:00+03:00"
    stats.add(make_event(timestamp="2026-10-07T09:30:00Z"))
    stats.add(make_event(timestamp="2026-10-07T12:00:00+03:00"))
    assert stats.first_timestamp == "2026-10-07T12:00:00+03:00"
    assert stats.last_timestamp == "2026-10-07T09:30:00Z"


def test_timestamps_are_none_for_empty_statistics() -> None:
    stats = StreamStats()
    assert stats.first_timestamp is None
    assert stats.last_timestamp is None
    assert stats.top_error_sources() == []


def test_top_error_sources_orders_by_count_then_name() -> None:
    stats = StreamStats()
    for source in ("zeta", "alpha", "alpha", "beta", "beta", "gamma"):
        stats.add(make_event(level="ERROR", source=source))
    assert stats.top_error_sources() == [
        ("alpha", 2),
        ("beta", 2),
        ("gamma", 1),
        ("zeta", 1),
    ]


def test_top_error_sources_is_limited_to_five() -> None:
    stats = StreamStats()
    for number in range(8):
        stats.add(make_event(level="CRITICAL", source=f"src{number}"))
    assert len(stats.top_error_sources()) == 5


def test_process_file_reads_all_events(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path / "a.csv",
        "2026-10-07T12:00:00Z,INFO,api,started",
        "2026-10-07T12:00:01Z,ERROR,db,failed",
    )
    stats = StreamStats()
    process_file(path, "csv", stats)
    assert stats.total_events == 2
    assert stats.skipped_lines == 0


def test_strict_mode_stops_and_names_file_and_line(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path / "bad.csv",
        "2026-10-07T12:00:00Z,INFO,api,ok",
        "2026-10-07T12:00:01Z,LOUD,api,oops",
    )
    with pytest.raises(InvalidEventError) as info:
        process_file(path, "csv", StreamStats())
    assert str(path) in str(info.value)
    assert ":3:" in str(info.value)


def test_strict_mode_keeps_the_timestamp_error_type(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "time.csv", "yesterday,INFO,api,ok")
    with pytest.raises(InvalidTimestampError):
        process_file(path, "csv", StreamStats())


def test_skip_mode_skips_counts_and_logs_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "mixed.jsonl"
    path.write_text(
        '{"timestamp": "2026-10-07T12:00:00Z", "level": "INFO", '
        '"source": "api", "message": "ok"}\n'
        '{"timestamp": "2026-10-07T12:00:01Z", "level": \n'
        '{"timestamp": "2026-10-07T12:00:02Z", "level": "LOUD", '
        '"source": "api", "message": "bad level"}\n'
        '{"timestamp": "2026-10-07T12:00:03Z", "level": "ERROR", '
        '"source": "db", "message": "failed"}\n',
        encoding="utf-8",
    )
    stats = StreamStats()
    with caplog.at_level(logging.WARNING):
        process_file(path, "jsonl", stats, skip_invalid=True)
    assert stats.total_events == 2
    assert stats.skipped_lines == 2
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 2
    assert f"{path}:2" in warnings[0].getMessage()
    assert f"{path}:3" in warnings[1].getMessage()


def test_analyze_files_merges_statistics(tmp_path: Path) -> None:
    first = write_csv(
        tmp_path / "a.csv",
        "2026-10-07T12:00:00Z,INFO,api,a",
        "2026-10-07T12:00:05Z,ERROR,db,a",
    )
    second = write_csv(
        tmp_path / "b.csv",
        "2026-10-07T11:00:00Z,ERROR,db,b",
        "2026-10-07T13:00:00Z,INFO,api,b",
    )
    stats = analyze_files([first, second], "csv")
    assert stats.total_events == 4
    assert stats.sources == {"api": 2, "db": 2}
    assert stats.top_error_sources() == [("db", 2)]
    assert stats.first_timestamp == "2026-10-07T11:00:00Z"
    assert stats.last_timestamp == "2026-10-07T13:00:00Z"


def test_file_order_does_not_change_the_result(tmp_path: Path) -> None:
    first = write_csv(tmp_path / "a.csv", "2026-10-07T12:00:00Z,ERROR,x,a")
    second = write_csv(tmp_path / "b.csv", "2026-10-07T09:00:00Z,ERROR,y,b")
    forward = analyze_files([first, second], "csv")
    backward = analyze_files([second, first], "csv")
    assert forward.top_error_sources() == backward.top_error_sources()
    assert forward.first_timestamp == backward.first_timestamp
    assert forward.last_timestamp == backward.last_timestamp
    assert forward.levels == backward.levels


def test_missing_file_raises_configuration_error(tmp_path: Path) -> None:
    with pytest.raises(CliConfigurationError):
        process_file(tmp_path / "nope.csv", "csv", StreamStats())


def test_unsupported_format_raises(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "a.csv")
    with pytest.raises(UnsupportedFormatError):
        process_file(path, "xml", StreamStats())


def test_file_with_invalid_utf8_raises_configuration_error(tmp_path: Path) -> None:
    path = tmp_path / "binary.csv"
    path.write_bytes(b"\xff\xfe\x00 not utf-8")
    with pytest.raises(CliConfigurationError):
        process_file(path, "csv", StreamStats())


def test_empty_file_gives_zero_statistics(tmp_path: Path) -> None:
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    stats = analyze_files([path], "jsonl")
    assert stats.total_events == 0
    assert stats.first_timestamp is None


def test_unicode_sources_are_counted(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "u.csv", "2026-10-07T12:00:00Z,ERROR,сервер,сбой ✓")
    stats = analyze_files([path], "csv")
    assert stats.sources == {"сервер": 1}
    assert stats.top_error_sources() == [("сервер", 1)]


def test_iter_events_is_lazy(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "a.csv", "2026-10-07T12:00:00Z,INFO,api,a")
    events = iter_events(path, "csv", StreamStats())
    assert iter(events) is events
    assert next(events).source == "api"
