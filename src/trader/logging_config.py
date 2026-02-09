"""
Logging setup from config. Optionally writes to a log file (logging.file_path).
The filename gets date and time before the extension, e.g. oclw_bot.log -> oclw_bot_2025-02-09_14-30-22.log
If env OCLW_LOG_FILE is set, that path is used as-is (so one file per run when set by run_full_test).
"""
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


def log_path_with_timestamp(file_path: str) -> Path:
    """
    One new log file per run: logs/oclw_bot_YYYY-MM-DD_HH-mm-ss.log
    (zelfde formaat als voorheen, alle logs in map logs/)
    """
    path = Path(file_path)
    now = datetime.now()
    stamp = now.strftime("%Y-%m-%d_%H-%M-%S")
    base = (path.stem if path.suffix else path.name) or "oclw_bot"
    new_name = f"{base}_{stamp}.log"
    return path.parent / new_name


def setup_logging(cfg: Dict[str, Any] | None = None) -> None:
    cfg = cfg or {}
    log_cfg = cfg.get("logging", {})
    level = log_cfg.get("level", "INFO")
    fmt = log_cfg.get("format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    level_value = getattr(logging, level.upper(), logging.INFO)

    # Console (stdout)
    logging.basicConfig(
        level=level_value,
        format=fmt,
        stream=sys.stdout,
        force=True,
    )
    root = logging.getLogger()

    # Log file (optional): same format, append; filename includes date and time
    # If OCLW_LOG_FILE is set (e.g. by run_full_test), use that path so all subprocesses share one file
    file_path = os.environ.get("OCLW_LOG_FILE") or log_cfg.get("file_path") or log_cfg.get("file")
    if file_path:
        path = Path(file_path) if os.environ.get("OCLW_LOG_FILE") else log_path_with_timestamp(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fh = logging.FileHandler(path, mode="a", encoding="utf-8")
            fh.setLevel(level_value)
            fh.setFormatter(logging.Formatter(fmt))
            root.addHandler(fh)
        except OSError as e:
            root.warning("Could not open log file %s: %s", path, e)
