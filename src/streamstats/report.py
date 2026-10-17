import json
import sys
from pathlib import Path
from typing import Any

from streamstats.analysis import StreamStats
from streamstats.errors import CliConfigurationError
from streamstats.models import LEVELS

Report = dict[str, Any]


def build_report(stats: StreamStats) -> Report:
    """Collect the final statistics into a plain dictionary with a fixed key order"""
    return {
        "total_events": stats.total_events,
        "levels": {level: stats.levels.get(level, 0) for level in LEVELS},
        "sources": dict(sorted(stats.sources.items())),
        "top_error_sources": [
            {"source": source, "count": count}
            for source, count in stats.top_error_sources()
        ],
        "first_timestamp": stats.first_timestamp,
        "last_timestamp": stats.last_timestamp,
        "skipped_lines": stats.skipped_lines,
    }


def render_json(report: Report) -> str:
    """Render the report as readable JSON text that ends with a newline"""
    return json.dumps(report, ensure_ascii=False, indent=2) + "\n"


def write_report(report: Report, path: Path | None = None) -> None:
    """Write the JSON report to a file or, without a path, to standard output"""
    data = render_json(report).encode("utf-8")
    if path is None:
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    except OSError as error:
        raise CliConfigurationError(
            f"cannot write report to {path}: {error}"
        ) from error
