from __future__ import annotations

import logging
import os

_LOG_DIR = os.getenv("LOG_DIR", "./data/logs")
os.makedirs(_LOG_DIR, exist_ok=True)

logger = logging.getLogger("billiard.audit")
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.FileHandler(os.path.join(_LOG_DIR, "audit.log"), encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
    logger.addHandler(handler)


def log_action(actor_id: int, action: str, details: str = "") -> None:
    logger.info("actor=%s action=%s %s", actor_id, action, details)
