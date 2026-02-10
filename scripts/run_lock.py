"""
Run-lock: only one backtest at a time (for Telegram / OpenClaw).
Uses artifacts/.backtest.lock; content: pid\\ntimestamp. Stale = 600s or PID not running.
"""
import os
import sys
import time
from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _lock_path() -> Path:
    return _root() / "artifacts" / ".backtest.lock"


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _read_lock() -> tuple[int, float] | None:
    p = _lock_path()
    if not p.exists():
        return None
    try:
        raw = p.read_text().strip().split("\n")
        if len(raw) >= 2:
            return int(raw[0]), float(raw[1])
    except (ValueError, OSError):
        pass
    return None


def _write_lock(pid: int) -> None:
    _lock_path().parent.mkdir(parents=True, exist_ok=True)
    _lock_path().write_text(f"{pid}\n{time.time()}\n", encoding="utf-8")


def _remove_lock() -> None:
    p = _lock_path()
    if p.exists():
        try:
            p.unlink()
        except OSError:
            pass


STALE_SECONDS = 600  # 10 min


def acquire(reason: str = "backtest") -> bool:
    """Acquire backtest lock. Returns True if acquired, False if already held (or stale cleared and acquired)."""
    pid = os.getpid()
    existing = _read_lock()
    if existing:
        other_pid, ts = existing
        if _pid_alive(other_pid) and (time.time() - ts) < STALE_SECONDS:
            return False  # someone else is running
        _remove_lock()
    _write_lock(pid)
    return True


def release() -> None:
    """Release backtest lock (only if we hold it)."""
    existing = _read_lock()
    if existing and existing[0] == os.getpid():
        _remove_lock()


def is_locked() -> bool:
    """True if a valid (non-stale, alive) lock exists."""
    existing = _read_lock()
    if not existing:
        return False
    pid, ts = existing
    return _pid_alive(pid) and (time.time() - ts) < STALE_SECONDS
