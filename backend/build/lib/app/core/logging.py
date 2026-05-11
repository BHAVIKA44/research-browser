import logging
import sys
from pythonjsonlogger import jsonlogger


REDACT_KEYS = {"authorization", "api_key", "token", "password", "secret"}


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, dict):
            record.msg = {
                k: ("***REDACTED***" if k.lower() in REDACT_KEYS else v)
                for k, v in record.msg.items()
            }
        return True


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handler.setFormatter(formatter)
    handler.addFilter(RedactFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
