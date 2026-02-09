"""
Logging setup from config.
"""
import logging
import sys
from typing import Any, Dict


def setup_logging(cfg: Dict[str, Any] | None = None) -> None:
    cfg = cfg or {}
    log_cfg = cfg.get("logging", {})
    level = log_cfg.get("level", "INFO")
    fmt = log_cfg.get("format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=fmt,
        stream=sys.stdout,
    )
