"""
Atomic IO - Atomic file write utilities.
Prevents partial data on crash. Replaces all open().write() JSON state file operations.

Features:
- Atomic JSON and text file writes (write-to-tmp + os.replace)
- Post-write flush + fsync ensures data durability
- Automatic temp file cleanup on exceptions
- Optional old file backup (.bak)
- Safe JSON read (returns default on parse failure)
"""

import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Optional, Union

logger = logging.getLogger(__name__)

# Type alias for path arguments
PathLike = Union[str, Path]


def atomic_write_json(
    path: PathLike,
    data: Any,
    indent: int = 2,
    backup: bool = False,
    encoding: str = "utf-8",
) -> None:
    """
    Atomic JSON file write.

    Process:
    1. (Optional) Back up old file to {path}.bak
    2. Create a temp file in the same directory and write serialized JSON
    3. flush + fsync to ensure data durability
    4. os.replace atomically swaps the target file

    Args:
        path:     Target file path
        data:     JSON-serializable data object
        indent:   JSON indentation spaces, default 2
        backup:   When True, back up old file to {path}.bak before writing
        encoding: File encoding, default utf-8

    Raises:
        TypeError: data cannot be serialized to JSON
        OSError:   Filesystem operation failed
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    # --- optional backup ---
    if backup and target.exists():
        bak_path = target.with_suffix(target.suffix + ".bak")
        try:
            shutil.copy2(target, bak_path)
            logger.debug(f"Backed up {target} -> {bak_path}")
        except OSError as exc:
            # Backup failure is non-fatal; log and continue
            logger.warning(f"Failed to create backup for {target}: {exc}")

    # Serialize before touching the filesystem so we fail fast on bad data
    content = json.dumps(data, ensure_ascii=False, indent=indent)
    encoded = content.encode(encoding)

    _atomic_write_bytes(target, encoded)
    logger.debug(f"atomic_write_json: wrote {len(encoded)} bytes to {target}")


def atomic_write_text(
    path: PathLike,
    content: str,
    encoding: str = "utf-8",
) -> None:
    """
    Atomic text file write.

    Args:
        path:     Target file path
        content:  Text content
        encoding: File encoding, default utf-8

    Raises:
        OSError: Filesystem operation failed
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    encoded = content.encode(encoding)
    _atomic_write_bytes(target, encoded)
    logger.debug(f"atomic_write_text: wrote {len(encoded)} bytes to {target}")


def safe_read_json(
    path: PathLike,
    default: Any = None,
    encoding: str = "utf-8",
) -> Any:
    """
    Safe JSON file read. Returns default on any error without raising.

    Args:
        path:     Target file path
        default:  Return value on read or parse failure, default None
        encoding: File encoding, default utf-8

    Returns:
        Parsed Python object, or default
    """
    target = Path(path)
    try:
        text = target.read_text(encoding=encoding)
        return json.loads(text)
    except FileNotFoundError:
        logger.debug(f"safe_read_json: file not found: {target}")
        return default
    except json.JSONDecodeError as exc:
        logger.warning(f"safe_read_json: JSON parse error in {target}: {exc}")
        return default
    except OSError as exc:
        logger.warning(f"safe_read_json: OS error reading {target}: {exc}")
        return default


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _atomic_write_bytes(target: Path, data: bytes) -> None:
    """
    Write *data* to *target* atomically using a sibling temp file.

    Uses NamedTemporaryFile in the same directory as *target* so that
    os.replace() stays on the same filesystem (required for atomicity on
    NTFS and POSIX).  Calls flush() + os.fsync() before the rename to
    guarantee durability even on crash.

    Cleans up the temp file on any exception.
    """
    dir_path = target.parent
    tmp_fd = None
    tmp_path = None

    try:
        # delete=False so we can close the file before calling os.replace
        # (Windows requires the file to be closed before renaming)
        tmp_fd = tempfile.NamedTemporaryFile(
            mode="wb",
            dir=dir_path,
            suffix=".tmp",
            delete=False,
        )
        tmp_path = Path(tmp_fd.name)

        tmp_fd.write(data)
        tmp_fd.flush()
        os.fsync(tmp_fd.fileno())  # force kernel buffer -> disk
        tmp_fd.close()
        tmp_fd = None  # mark as closed so the except block skips close()

        # Atomic rename - on NTFS (Windows 10+) and POSIX this is a single
        # syscall that either succeeds fully or leaves the original intact.
        # Retry on Windows PermissionError (OneDrive sync, antivirus locks).
        import time as _time
        for _attempt in range(3):
            try:
                os.replace(tmp_path, target)
                tmp_path = None  # rename succeeded; nothing to clean up
                break
            except PermissionError:
                if _attempt < 2:
                    _time.sleep(0.1 * (_attempt + 1))
                else:
                    raise  # Give up after 3 attempts

    except Exception:
        # Best-effort cleanup of the temp file
        if tmp_fd is not None:
            try:
                tmp_fd.close()
            except OSError:
                pass
        if tmp_path is not None and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise
