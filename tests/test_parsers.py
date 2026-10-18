from collections.abc import Iterator
from pathlib import Path

import pytest

from streamstats import parsers
from streamstats.analysis import analyze_files
from streamstats.errors import UnsupportedFormatError
from streamstats.parsers import (
    RawRecord,
    available_formats,
    get_parser,
    register_parser,
)

CSV_HEADER = "timestamp,level,source,message\n"
CSV_TEXT = (
    CSV_HEADER
    + "2026-10-07T12:00:00+03:00,INFO,api,started\n"
    + "2026-10-07T12:00:02+03:00,ERROR,db,failed\n"
)
JSONL_TEXT = (
    '{"timestamp": "2026-10-07T12:00:00Z", "level": "INFO", '
    '"source": "api", "message": "started"}\n'
    "\n"
    '{"timestamp": "2026-10-07T12:00:01Z", "level": "ERROR", '
    '"source": "db", "message": "failed"}\n'
)


def test_csv_parser_reads_records(tmp_path: Path) -> None:
    path = tmp_path / "log.csv"
    path.write_text(CSV_TEXT, encoding="utf-8")
    records = list(get_parser("csv")(path))
    assert [record.line_number for record in records] == [2, 3]
    assert records[0].data["source"] == "api"
    assert records[1].data["level"] == "ERROR"
    assert all(record.problem is None for record in records)


def test_parsers_are_lazy(tmp_path: Path) -> None:
    path = tmp_path / "log.csv"
    path.write_text(CSV_TEXT, encoding="utf-8")
    result = get_parser("csv")(path)
    assert not isinstance(result, list)
    assert iter(result) is result
    assert next(result).line_number == 2


def test_csv_empty_file_gives_no_records(tmp_path: Path) -> None:
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")
    assert list(get_parser("csv")(path)) == []


def test_csv_header_only_gives_no_records(tmp_path: Path) -> None:
    path = tmp_path / "header.csv"
    path.write_text(CSV_HEADER, encoding="utf-8")
    assert list(get_parser("csv")(path)) == []


def test_csv_short_row_has_missing_value_and_empty_cell_is_empty(
    tmp_path: Path,
) -> None:
    path = tmp_path / "short.csv"
    path.write_text(
        CSV_HEADER + "2026-10-07T12:00:00Z,INFO\n2026-10-07T12:00:01Z,INFO,api,\n",
        encoding="utf-8",
    )
    short, empty = get_parser("csv")(path)
    assert short.data["source"] is None
    assert empty.data["message"] == ""


def test_csv_row_with_extra_values_is_a_problem(tmp_path: Path) -> None:
    path = tmp_path / "long.csv"
    path.write_text(CSV_HEADER + "2026-10-07T12:00:00Z,INFO,api,ok,extra\n")
    (record,) = get_parser("csv")(path)
    assert record.problem is not None
    assert record.line_number == 2


def test_jsonl_parser_reads_records_and_counts_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "log.jsonl"
    path.write_text(JSONL_TEXT, encoding="utf-8")
    records = list(get_parser("jsonl")(path))
    assert [record.line_number for record in records] == [1, 3]
    assert records[1].data["source"] == "db"


def test_jsonl_broken_line_is_a_problem_and_reading_continues(tmp_path: Path) -> None:
    path = tmp_path / "broken.jsonl"
    path.write_text('{"a": 1}\n{"a": \n{"a": 3}\n', encoding="utf-8")
    first, broken, last = get_parser("jsonl")(path)
    assert first.problem is None
    assert broken.problem is not None
    assert broken.line_number == 2
    assert last.data == {"a": 3}


def test_jsonl_value_that_is_not_an_object_is_a_problem(tmp_path: Path) -> None:
    path = tmp_path / "list.jsonl"
    path.write_text("[1, 2]\n", encoding="utf-8")
    (record,) = get_parser("jsonl")(path)
    assert record.problem == "JSON value is not an object"


def test_parsers_read_unicode(tmp_path: Path) -> None:
    csv_path = tmp_path / "unicode.csv"
    csv_path.write_text(
        CSV_HEADER + "2026-10-07T12:00:00Z,INFO,сервер,запуск ✓\n", encoding="utf-8"
    )
    (record,) = get_parser("csv")(csv_path)
    assert record.data["source"] == "сервер"
    assert record.data["message"] == "запуск ✓"


def test_parsers_ignore_utf8_bom(tmp_path: Path) -> None:
    path = tmp_path / "bom.csv"
    path.write_text(CSV_TEXT, encoding="utf-8-sig")
    (first, _) = get_parser("csv")(path)
    assert "timestamp" in first.data


def test_unknown_format_raises() -> None:
    with pytest.raises(UnsupportedFormatError):
        get_parser("xml")


def test_available_formats() -> None:
    assert available_formats() == ["csv", "jsonl"]


def test_custom_format_can_be_registered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(parsers, "_PARSERS", dict(parsers._PARSERS))

    @register_parser("pipe")
    def iter_pipe_records(path: Path) -> Iterator[RawRecord]:
        with path.open(encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                timestamp, level, source, message = line.rstrip("\n").split("|")
                yield RawRecord(
                    line_number,
                    {
                        "timestamp": timestamp,
                        "level": level,
                        "source": source,
                        "message": message,
                    },
                )

    assert "pipe" in available_formats()
    path = tmp_path / "log.pipe"
    path.write_text("2026-10-07T12:00:00Z|ERROR|db|failed\n", encoding="utf-8")
    stats = analyze_files([path], "pipe")
    assert stats.total_events == 1
    assert stats.top_error_sources() == [("db", 1)]
