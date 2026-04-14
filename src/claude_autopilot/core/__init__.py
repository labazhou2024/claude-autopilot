"""Core modules -- zero-dependency standalone components."""

from claude_autopilot.core.approval_queue import format_briefing, get_pending, submit_approval
from claude_autopilot.core.atomic_io import atomic_write_json, safe_read_json
from claude_autopilot.core.event_bus import configure as configure_events
from claude_autopilot.core.event_bus import log_event, read_events
from claude_autopilot.core.local_reviewer import review_file, review_files
from claude_autopilot.core.validators import ValidationError
from claude_autopilot.core.worker_pool import WorkerPool

__all__ = [
    "log_event",
    "read_events",
    "configure_events",
    "submit_approval",
    "get_pending",
    "format_briefing",
    "review_file",
    "review_files",
    "WorkerPool",
    "atomic_write_json",
    "safe_read_json",
    "ValidationError",
]
