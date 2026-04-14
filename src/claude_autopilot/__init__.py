"""claude-autopilot: From Copilot to Autopilot.

Autonomous multi-agent orchestration for Claude Code.
"""

__version__ = "0.1.0"

# Convenience imports for top-level access
from claude_autopilot.core.approval_queue import (
    approve,
    defer,
    format_briefing,
    get_pending,
    reject,
    submit_approval,
)
from claude_autopilot.core.approval_queue import (
    configure as configure_approvals,
)
from claude_autopilot.core.atomic_io import atomic_write_json, atomic_write_text, safe_read_json
from claude_autopilot.core.event_bus import configure as configure_events
from claude_autopilot.core.event_bus import log_event, read_events
from claude_autopilot.core.local_reviewer import Finding, ReviewResult, review_file, review_files
from claude_autopilot.core.validators import ValidationError, validate_task_id
from claude_autopilot.core.worker_pool import PoolStatus, WorkerPool

__all__ = [
    "__version__",
    # Event Bus
    "log_event",
    "read_events",
    "configure_events",
    # Approval Queue
    "submit_approval",
    "approve",
    "reject",
    "defer",
    "get_pending",
    "format_briefing",
    "configure_approvals",
    # Local Reviewer
    "review_file",
    "review_files",
    "ReviewResult",
    "Finding",
    # Worker Pool
    "WorkerPool",
    "PoolStatus",
    # Atomic IO
    "atomic_write_json",
    "atomic_write_text",
    "safe_read_json",
    # Validators
    "ValidationError",
    "validate_task_id",
]
