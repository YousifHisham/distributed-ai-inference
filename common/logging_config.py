import logging
import json
import os
import time

_RESET = "\033[0m"
_DIM   = "\033[2m"
_LEVEL_COLORS = {
    "DEBUG":    "\033[36m",
    "INFO":     "\033[32m",
    "WARNING":  "\033[33m",
    "ERROR":    "\033[31m",
    "CRITICAL": "\033[35m",
}


class PrettyFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        color = _LEVEL_COLORS.get(record.levelname, _RESET)
        ts    = time.strftime("%H:%M:%S", time.localtime(record.created))
        level = f"{color}{record.levelname:<8}{_RESET}"
        name  = f"{_DIM}{record.name:<28}{_RESET}"
        line  = f"{ts} {level} {name} {record.getMessage()}"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


class JSONFormatter(logging.Formatter):
    def __init__(self, service_name: str = "service"):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level":     record.levelname,
            "service":   self.service_name,
            "message":   record.getMessage(),
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry)


def setup_logging(service_name: str, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(service_name)
    logger.setLevel(level)
    if not logger.handlers:
        handler = logging.StreamHandler()
        if os.getenv("LOG_FORMAT", "pretty").lower() == "json":
            handler.setFormatter(JSONFormatter(service_name))
        else:
            handler.setFormatter(PrettyFormatter())
        logger.addHandler(handler)
    logger.propagate = False
    return logger
