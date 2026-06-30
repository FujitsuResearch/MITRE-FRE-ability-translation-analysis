"""Logging utility with origin tracking."""

import inspect
import logging
import os
import sys


class LogFilter(logging.Filter):
    """Filter to ensure origin is always present."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "origin"):
            record.origin = "unknown"
        return True


class CustomFormatter(logging.Formatter):
    """Custom formatter with colored output and origin tracking."""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.RESET)
        origin = getattr(record, "origin", "unknown")
        timestamp = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        return (
            f"{color}[{timestamp}] [{record.levelname}] [{origin}]{self.RESET} "
            f"{record.getMessage()}"
        )


class ProcedureLogger:
    """Custom logger with origin tracking."""

    def __init__(self, name: str = "procedure_generator"):
        self.logger = logging.getLogger(name)
        loglevel = os.getenv("LOGLEVEL", "INFO").upper()
        self.logger.setLevel(getattr(logging, loglevel))
        self.logger.propagate = False
        self.logger.addFilter(LogFilter())

        # Clear existing handlers
        for h in self.logger.handlers[:]:
            h.close()
            self.logger.removeHandler(h)

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(CustomFormatter())
        self.logger.addHandler(console_handler)

    def _get_origin(self) -> str:
        """Get caller function name and line number."""
        frame = inspect.currentframe()
        try:
            caller_frame = frame.f_back.f_back.f_back
            if caller_frame:
                func = caller_frame.f_code.co_name
                line = caller_frame.f_lineno
                return f"{self.logger.name}:{func}:{line}"
            return "unknown"
        finally:
            del frame

    def _log(self, level: str, message: str, origin: str | None = None):
        if not origin:
            origin = self._get_origin()
        getattr(self.logger, level.lower())(message, extra={"origin": origin})

    def debug(self, message: str, origin: str | None = None):
        self._log("DEBUG", message, origin)

    def info(self, message: str, origin: str | None = None):
        self._log("INFO", message, origin)

    def warning(self, message: str, origin: str | None = None):
        self._log("WARNING", message, origin)

    def error(self, message: str, origin: str | None = None):
        self._log("ERROR", message, origin)

    def critical(self, message: str, origin: str | None = None):
        self._log("CRITICAL", message, origin)


def get_logger(name: str = "procedure_generator") -> ProcedureLogger:
    """Get a ProcedureLogger instance with the given name."""
    return ProcedureLogger(name)
