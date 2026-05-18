import logging
import os
import json
from datetime import datetime, timezone
import uuid
from config import LOG_FILE

RUN_ID = str(uuid.uuid4())[:8]

os.makedirs(os.path.dirname(LOG_FILE) or ".", exist_ok=True)

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": RUN_ID,
            "level": record.levelname,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        # file handler
        fh = logging.FileHandler(LOG_FILE)
        fh.setFormatter(JSONFormatter())
        logger.addHandler(fh)

        # console handler
        ch = logging.StreamHandler()
        ch.setFormatter(JSONFormatter())
        logger.addHandler(ch)

    return logger
