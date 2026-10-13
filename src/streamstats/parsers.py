import csv
import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from streamstats.errors import UnsupportedFormatError


@dataclass(frozen=True)
class RawRecord:
    """One physical record of a file: its data or a description of the damage"""

    line_number: int
    data: dict[str, object]
    problem: str | None = None


Parser = Callable[[Path], Iterator[RawRecord]]
_PARSERS: dict[str, Parser] = {}


def register_parser(name: str) -> Callable[[Parser], Parser]:
    """Register a parser function under a format name"""

    def decorate(function: Parser) -> Parser:
        _PARSERS[name] = function
        return function

    return decorate


def get_parser(name: str) -> Parser:
    """Return the parser registered for a format or raise UnsupportedFormatError"""
    try:
        return _PARSERS[name]
    except KeyError as error:
        raise UnsupportedFormatError(f"unsupported format: {name!r}") from error


def available_formats() -> list[str]:
    """Return registered format names in alphabetical order"""
    return sorted(_PARSERS)


@register_parser("csv")
def iteration_csv_records(path: Path) -> Iterator[RawRecord]:
    """Lazily read a CSV file with a header, one record at a time"""
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            if None in row:
                yield RawRecord(
                    reader.line_num, {}, "row has more values than the header"
                )
            else:
                data: dict[str, object] = {key: value for key, value in row.items()}
                yield RawRecord(reader.line_num, data)


@register_parser("jsonl")
def iteration_jsonl_records(path: Path) -> Iterator[RawRecord]:
    """Lazily read a JSON Lines file, one line at a time"""
    with path.open(encoding="utf-8-sig") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                yield RawRecord(line_number, {}, f"invalid JSON: {error.msg}")
                continue
            if not isinstance(value, dict):
                yield RawRecord(line_number, {}, "JSON value is not an object")
                continue
            yield RawRecord(line_number, value)
