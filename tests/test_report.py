import json
from pathlib import Path

import pytest

from streamstats.analysis import StreamStats
from streamstats.errors import CliConfigurationError
from streamstats.models import LEVELS, Event, parse_event
from streamstats.report import build_report, render_json, write_report


def make_event(timestamp: str, level: str, source: str) -> Event:
    return parse_event(
        {"timestamp": timestamp, "level": level, "source": source, "message": "m"}
    )


def sample_stats() -> StreamStats:
    stats = StreamStats()
    stats.add(make_event("2026-10-07T12:00:00Z", "INFO", "сервер"))
    stats.add(make_event("2026-10-07T12:00:05+03:00", "ERROR", "db"))
    stats.add(make_event("2026-10-07T12:00:09Z", "CRITICAL", "db"))
    stats.skipped_lines = 2
    return stats


def test_build_report_contains_all_required_values() -> None:
    report = build_report(sample_stats())
    assert report["total_events"] == 3
    assert report["levels"] == {
        "DEBUG": 0,
        "INFO": 1,
        "WARNING": 0,
        "ERROR": 1,
        "CRITICAL": 1,
    }
    assert report["sources"] == {"db": 2, "сервер": 1}
    assert report["top_error_sources"] == [{"source": "db", "count": 2}]
    assert report["first_timestamp"] == "2026-10-07T12:00:05+03:00"
    assert report["last_timestamp"] == "2026-10-07T12:00:09Z"
    assert report["skipped_lines"] == 2


def test_levels_are_listed_in_severity_order() -> None:
    report = build_report(sample_stats())
    assert list(report["levels"]) == list(LEVELS)


def test_report_of_empty_statistics() -> None:
    report = build_report(StreamStats())
    assert report["total_events"] == 0
    assert report["sources"] == {}
    assert report["top_error_sources"] == []
    assert report["first_timestamp"] is None
    assert report["last_timestamp"] is None


def test_render_json_is_deterministic_and_keeps_unicode() -> None:
    first = render_json(build_report(sample_stats()))
    second = render_json(build_report(sample_stats()))
    assert first == second
    assert "сервер" in first
    assert "\\u" not in first
    assert first.endswith("\n")


def test_write_report_creates_missing_folders(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "folder" / "report.json"
    report = build_report(sample_stats())
    write_report(report, target)
    assert json.loads(target.read_text(encoding="utf-8")) == report


def test_write_report_to_unusable_path_raises(tmp_path: Path) -> None:
    with pytest.raises(CliConfigurationError):
        write_report(build_report(StreamStats()), tmp_path)
