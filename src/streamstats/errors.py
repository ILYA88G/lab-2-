class StreamStatsError(Exception):
    """Class for all stream errors"""


class UnsupportedFormatError(StreamStatsError):
    """Requested input format has no registered parser"""


class InvalidEventError(StreamStatsError):
    """Log record is damaged or does not satisfy the event requirements"""


class InvalidTimestampError(InvalidEventError):
    """Time value is not a valid ISO 8601 date and time"""


class CliConfigurationError(StreamStatsError):
    """Arguments or files passed to the CLI cannot be used"""
