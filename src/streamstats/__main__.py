import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from streamstats.analysis import analyze_files
from streamstats.errors import StreamStatsError
from streamstats.parsers import available_formats, get_parser
from streamstats.report import build_report, write_report

DEFAULT_LOG_FILE = Path("streamstats.log")
PACKAGE_LOGGER_NAME = "streamstats"

logger = logging.getLogger(f"{PACKAGE_LOGGER_NAME}.cli")


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser with the analyze subcommand"""
    parser = argparse.ArgumentParser(
        prog="streamstats",
        description="Streaming analyzer of CSV and JSON Lines logs",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    analyze = subparsers.add_parser(
        "analyze", help="Analyze log files and build a JSON report"
    )
    analyze.add_argument(
        "inputs", nargs="+", type=Path, metavar="INPUT", help="Log files to analyze"
    )
    analyze.add_argument(
        "--format",
        required=True,
        metavar="FORMAT",
        help=f"Input format ({', '.join(available_formats())})",
    )
    analyze.add_argument(
        "--output",
        type=Path,
        metavar="REPORT.json",
        help="Write the JSON report to this file (default: standard output)",
    )
    analyze.add_argument(
        "--skip-invalid",
        action="store_true",
        help="Skip damaged records with a warning instead of stopping",
    )
    analyze.add_argument(
        "--log-file",
        type=Path,
        default=DEFAULT_LOG_FILE,
        metavar="LOG",
        help=f"File for the execution log (default: {DEFAULT_LOG_FILE})",
    )
    return parser


def configure_logging(log_file: Path) -> list[logging.Handler]:
    """Attach a console handler and a log file handler to the package logger"""
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    package_logger = logging.getLogger(PACKAGE_LOGGER_NAME)
    package_logger.setLevel(logging.INFO)
    handlers: list[logging.Handler] = [console, file_handler]
    for handler in handlers:
        package_logger.addHandler(handler)
    return handlers


def release_logging(handlers: Sequence[logging.Handler]) -> None:
    """Detach and close the handlers created by configure_logging"""
    package_logger = logging.getLogger(PACKAGE_LOGGER_NAME)
    for handler in handlers:
        package_logger.removeHandler(handler)
        handler.close()


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line interface and return the process exit code"""
    args = build_parser().parse_args(argv)
    try:
        handlers = configure_logging(args.log_file)
    except OSError as error:
        print(f"error: cannot open log file {args.log_file}: {error}", file=sys.stderr)
        return 2
    try:
        get_parser(args.format)
        stats = analyze_files(args.inputs, args.format, skip_invalid=args.skip_invalid)
        write_report(build_report(stats), args.output)
    except StreamStatsError as error:
        logger.error("%s", error)
        return 2
    finally:
        release_logging(handlers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
