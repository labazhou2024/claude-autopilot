"""
EventBus — Append-only event logging with automatic rotation.

All critical workflow events are logged to data/events.jsonl.
Used for: debug, post-mortem, big-loop Q2 input, cost tracking.

Log rotation: when events.jsonl exceeds MAX_EVENTS lines, older events
are archived to data/events_archive/YYYY-MM-DD_events.jsonl and the
active file is truncated to the most recent KEEP_EVENTS entries.

Efficient tail read: read_events() seeks from end-of-file instead of
loading the entire file into memory.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_UTC = timezone.utc
_DATA_DIR: Optional[Path] = None
_EVENTS_FILE: Optional[Path] = None
_ARCHIVE_DIR: Optional[Path] = None


def _get_data_dir() -> Path:
    return _DATA_DIR or Path.cwd() / "data"


def _get_events_file() -> Path:
    if _EVENTS_FILE is not None:
        return _EVENTS_FILE
    return _get_data_dir() / "events.jsonl"


def _get_archive_dir() -> Path:
    if _ARCHIVE_DIR is not None:
        return _ARCHIVE_DIR
    return _get_data_dir() / "events_archive"


def configure(data_dir: Path) -> None:
    """Configure the data directory for the EventBus.

    Must be called before any log_event() calls if the default
    (cwd/data) is not appropriate.
    """
    global _DATA_DIR, _EVENTS_FILE, _ARCHIVE_DIR
    _DATA_DIR = Path(data_dir)
    _EVENTS_FILE = _DATA_DIR / "events.jsonl"
    _ARCHIVE_DIR = _DATA_DIR / "events_archive"


# Rotation thresholds
MAX_EVENTS = 5000  # Rotate when file exceeds this many lines
KEEP_EVENTS = 1000  # Keep this many recent events after rotation
_ROTATION_CHECK_INTERVAL = 50  # Check rotation every N writes
_write_counter = 0


def log_event(
    event_type: str,
    agent: str = "system",
    details: Optional[Dict[str, Any]] = None,
    *,
    session_id: str = "",
) -> None:
    """Append a structured event to events.jsonl.

    Automatically checks for rotation every _ROTATION_CHECK_INTERVAL writes.
    """
    global _write_counter

    data_dir = _get_data_dir()
    events_file = _get_events_file()

    data_dir.mkdir(parents=True, exist_ok=True)
    event = {
        "ts": datetime.now(tz=_UTC).isoformat(),
        "type": event_type,
        "agent": agent,
        "session": session_id,
        "details": details or {},
    }
    try:
        with open(events_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning("EventBus write failed: %s", e)
        return

    # Periodic rotation check (amortized cost)
    _write_counter += 1
    if _write_counter >= _ROTATION_CHECK_INTERVAL:
        _write_counter = 0
        try:
            _maybe_rotate()
        except Exception as e:
            logger.warning("EventBus rotation check failed: %s", e)


def read_events(last_n: int = 100) -> List[Dict]:
    """Read the last N events efficiently by seeking from end of file.

    Uses a reverse-read strategy: seeks to the end and reads backwards
    in chunks until enough lines are found. O(last_n) memory, not O(file_size).
    """
    events_file = _get_events_file()
    if not events_file.exists():
        return []

    try:
        lines = _tail_lines(events_file, last_n)
    except Exception:
        # Fallback: read whole file (old behavior)
        lines = events_file.read_text(encoding="utf-8").strip().splitlines()
        lines = lines[-last_n:]

    result = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return result


def count_events_by_type(last_n: int = 10000) -> Dict[str, int]:
    """Count events grouped by type (for dashboard / Q2 analysis)."""
    events = read_events(last_n=last_n)
    counts: Dict[str, int] = {}
    for e in events:
        t = e.get("type", "unknown")
        counts[t] = counts.get(t, 0) + 1
    return counts


def rotate_events(
    max_events: int = MAX_EVENTS,
    keep_events: int = KEEP_EVENTS,
) -> Optional[str]:
    """Force rotate events.jsonl.

    Archives old events and keeps only the most recent `keep_events`.
    Returns the archive file path if rotation occurred, None otherwise.
    """
    events_file = _get_events_file()
    if not events_file.exists():
        return None

    lines = events_file.read_text(encoding="utf-8").strip().splitlines()
    if len(lines) <= max_events:
        return None

    return _do_rotate(lines, keep_events)


def get_event_count() -> int:
    """Get approximate event count without loading full file."""
    events_file = _get_events_file()
    if not events_file.exists():
        return 0
    try:
        # Count newlines efficiently
        count = 0
        with open(events_file, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                count += chunk.count(b"\n")
        return count
    except Exception:
        return 0


# --- Internal helpers ---


def _tail_lines(filepath: Path, n: int, chunk_size: int = 8192) -> List[str]:
    """Read last N lines of a file efficiently by seeking from end.

    Reads backwards in chunks of chunk_size bytes until at least N lines
    are found. Much faster than reading the entire file for large files.
    """
    with open(filepath, "rb") as f:
        f.seek(0, 2)  # Seek to end
        file_size = f.tell()

        if file_size == 0:
            return []

        lines_found: List[bytes] = []
        remaining = file_size
        fragment = b""

        while remaining > 0 and len(lines_found) < n + 1:
            read_size = min(chunk_size, remaining)
            remaining -= read_size
            f.seek(remaining)
            chunk = f.read(read_size)
            chunk = chunk + fragment
            parts = chunk.split(b"\n")
            fragment = parts[0]
            lines_found = parts[1:] + lines_found

        # The fragment is the beginning of the first line
        if fragment:
            lines_found = [fragment] + lines_found

    # Decode and return last N non-empty lines
    decoded = []
    for raw in lines_found:
        try:
            line = raw.decode("utf-8").strip()
            if line:
                decoded.append(line)
        except UnicodeDecodeError:
            continue

    return decoded[-n:]


def _maybe_rotate():
    """Check if rotation is needed and perform it."""
    events_file = _get_events_file()
    if not events_file.exists():
        return

    event_count = get_event_count()
    if event_count > MAX_EVENTS:
        lines = events_file.read_text(encoding="utf-8").strip().splitlines()
        _do_rotate(lines, KEEP_EVENTS)


def _do_rotate(lines: List[str], keep_events: int) -> str:
    """Perform the actual rotation: archive old, keep recent."""
    archive_dir = _get_archive_dir()
    events_file = _get_events_file()
    archive_dir.mkdir(parents=True, exist_ok=True)

    # Archive filename with timestamp
    ts = datetime.now(tz=_UTC).strftime("%Y-%m-%d_%H%M%S")
    archive_file = archive_dir / f"{ts}_events.jsonl"

    # Write ALL lines to archive (complete history)
    archive_lines = lines[:-keep_events] if len(lines) > keep_events else []
    if archive_lines:
        archive_file.write_text("\n".join(archive_lines) + "\n", encoding="utf-8")

    # Rewrite active file with only recent events
    recent = lines[-keep_events:]
    events_file.write_text("\n".join(recent) + "\n", encoding="utf-8")

    logger.info(
        "EventBus rotated: archived %d events to %s, kept %d recent",
        len(archive_lines),
        archive_file.name,
        len(recent),
    )
    return str(archive_file)
