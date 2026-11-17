import contextvars
import json
import logging
from datetime import UTC, datetime

request_id = contextvars.ContextVar("request_id", default=None)
logger = logging.getLogger("inbox")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
            "request_id": request_id.get(),
            **getattr(record, "fields", {}),
        }
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False


def log(event: str, **fields: object) -> None:
    logger.info(event, extra={"fields": fields})
