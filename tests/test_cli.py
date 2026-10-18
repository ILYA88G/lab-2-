import json
import os
import subprocess
import sys
from pathlib import Path

HEADER = "timestamp,level,source,message\n"


def run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run `python -m streamstats` as a separate process inside a folder"""
    environment = {**os.environ, "PYTHONUTF8": "1"}
    return subprocess.run(
        [sys.executable, "-m", "streamstats", *args],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def write_csv(path: Path, *rows: str) -> Path:
    path.write_text(HEADER + "".join(row + "\n" for row in rows), encoding="utf-8")
    return path


def read_json(path: Path) -> dict[str, object]:
    report: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    return report


def test_help_works() -> None:
    result = run_cli("--help", cwd=Path.cwd())
    assert result.returncode == 0
    assert "analyze" in result.stdout


def test_analyze_help_lists_options() -> None:
    result = run_cli("analyze", "--help", cwd=Path.cwd())
    assert result.returncode == 0
    for option in ("--format", "--output", "--skip-invalid", "--log-file"):
        assert option in result.stdout


def test_missing_subcommand_exits_with_code_2(tmp_path: Path) -> None:
    assert run_cli(cwd=tmp_path).returncode == 2


def test_analyze_writes_report_and_leaves_a_log_file(tmp_path: Path) -> None:
    write_csv(
        tmp_path / "a.csv",
        "2026-10-07T12:00:00Z,INFO,api,started",
        "2026-10-07T12:00:01Z,ERROR,db,failed",
    )
    result = run_cli(
        "analyze", "a.csv", "--format", "csv", "--output", "report.json", cwd=tmp_path
    )
    assert result.returncode == 0
    report = read_json(tmp_path / "report.json")
    assert report["total_events"] == 2
    assert report["skipped_lines"] == 0
    log_text = (tmp_path / "streamstats.log").read_text(encoding="utf-8")
    assert "finished" in log_text


def test_report_goes_to_stdout_without_output_option(tmp_path: Path) -> None:
    write_csv(tmp_path / "a.csv", "2026-10-07T12:00:00Z,WARNING,api,slow")
    result = run_cli("analyze", "a.csv", "--format", "csv", cwd=tmp_path)
    assert result.returncode == 0
    assert json.loads(result.stdout)["levels"]["WARNING"] == 1
    assert "processing" in result.stderr


def test_strict_mode_exits_with_code_2_and_names_file_and_line(tmp_path: Path) -> None:
    write_csv(
        tmp_path / "bad.csv",
        "2026-10-07T12:00:00Z,INFO,api,ok",
        "2026-10-07T12:00:01Z,LOUD,api,oops",
    )
    result = run_cli(
        "analyze", "bad.csv", "--format", "csv", "--output", "report.json", cwd=tmp_path
    )
    assert result.returncode == 2
    assert "bad.csv:3" in result.stderr
    assert not (tmp_path / "report.json").exists()
    assert "ERROR" in (tmp_path / "streamstats.log").read_text(encoding="utf-8")


def test_skip_invalid_continues_and_counts_skipped_lines(tmp_path: Path) -> None:
    write_csv(
        tmp_path / "bad.csv",
        "2026-10-07T12:00:00Z,INFO,api,ok",
        "2026-10-07T12:00:01Z,LOUD,api,oops",
        "2026-10-07T12:00:02Z,ERROR,db,failed",
    )
    result = run_cli(
        "analyze",
        "bad.csv",
        "--format",
        "csv",
        "--skip-invalid",
        "--output",
        "report.json",
        cwd=tmp_path,
    )
    assert result.returncode == 0
    report = read_json(tmp_path / "report.json")
    assert report["total_events"] == 2
    assert report["skipped_lines"] == 1
    assert "WARNING" in (tmp_path / "streamstats.log").read_text(encoding="utf-8")


def test_several_files_are_combined(tmp_path: Path) -> None:
    write_csv(tmp_path / "a.csv", "2026-10-07T12:00:00Z,ERROR,db,a")
    write_csv(tmp_path / "b.csv", "2026-10-07T13:00:00Z,ERROR,db,b")
    result = run_cli(
        "analyze",
        "a.csv",
        "b.csv",
        "--format",
        "csv",
        "--output",
        "report.json",
        cwd=tmp_path,
    )
    assert result.returncode == 0
    report = read_json(tmp_path / "report.json")
    assert report["total_events"] == 2
    assert report["top_error_sources"] == [{"source": "db", "count": 2}]
    assert report["last_timestamp"] == "2026-10-07T13:00:00Z"


def test_jsonl_input_and_unicode_in_report(tmp_path: Path) -> None:
    (tmp_path / "a.jsonl").write_text(
        '{"timestamp": "2026-10-07T12:00:00Z", "level": "ERROR", '
        '"source": "сервер", "message": "сбой ✓"}\n',
        encoding="utf-8",
    )
    result = run_cli(
        "analyze",
        "a.jsonl",
        "--format",
        "jsonl",
        "--output",
        "report.json",
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert "сервер" in (tmp_path / "report.json").read_text(encoding="utf-8")


def test_unknown_format_exits_with_code_2(tmp_path: Path) -> None:
    write_csv(tmp_path / "a.csv")
    result = run_cli("analyze", "a.csv", "--format", "xml", cwd=tmp_path)
    assert result.returncode == 2
    assert "unsupported format" in result.stderr


def test_missing_input_file_exits_with_code_2(tmp_path: Path) -> None:
    result = run_cli("analyze", "nope.csv", "--format", "csv", cwd=tmp_path)
    assert result.returncode == 2
    assert "nope.csv" in result.stderr


def test_same_input_gives_identical_report(tmp_path: Path) -> None:
    write_csv(
        tmp_path / "a.csv",
        "2026-10-07T12:00:00Z,ERROR,beta,a",
        "2026-10-07T12:00:01Z,ERROR,alpha,b",
    )
    arguments = ("analyze", "a.csv", "--format", "csv", "--output")
    run_cli(*arguments, "first.json", cwd=tmp_path)
    run_cli(*arguments, "second.json", cwd=tmp_path)
    first = (tmp_path / "first.json").read_bytes()
    second = (tmp_path / "second.json").read_bytes()
    assert first == second
