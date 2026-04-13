"""
Approval Queue -- CEO async approval system.

Agent cluster runs fully autonomous. When a decision requires human
taste/foresight/risk judgment, it gets queued for async CEO review.

Three levels:
  L1 Auto:    Execute directly, log to EventBus
  L2 Suspend: Queue for review, continue other work
  L3 Block:   Queue for review, pause related task chain

CEO role: Super-reviewer with taste + foresight.
Does not execute -- only approves/rejects/redirects.
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Module-level data directory; override via configure()
_DATA_DIR: Optional[Path] = None


def configure(data_dir: Path) -> None:
    """Set the directory used for pending_approvals.json.

    Call this once at application startup before any other function in this
    module.  If not called, _get_data_dir() falls back to ./data relative to
    the current working directory.
    """
    global _DATA_DIR
    _DATA_DIR = Path(data_dir)


def _get_data_dir() -> Path:
    """Return the configured data directory, defaulting to cwd/data."""
    if _DATA_DIR is not None:
        return _DATA_DIR
    return Path.cwd() / "data"


def _queue_file() -> Path:
    return _get_data_dir() / "pending_approvals.json"


def _load() -> List[Dict]:
    qf = _queue_file()
    if qf.exists():
        try:
            return json.loads(qf.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save(items: List[Dict]) -> None:
    data_dir = _get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    _queue_file().write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def submit_approval(
    level: str,
    category: str,
    title: str,
    context: str,
    proposal: str,
    *,
    evidence: List[str] = None,
    impact: str = "",
    alternatives: List[str] = None,
    blocked_tasks: List[str] = None,
) -> str:
    """Submit a decision for CEO async approval.

    Returns: Approval ID
    """
    items = _load()
    apr_id = f"apr_{int(time.time())}_{len(items):03d}"
    now = datetime.utcnow().isoformat() + "Z"
    item = {
        "id": apr_id,
        "level": level,
        "category": category,
        "title": title,
        "context": context,
        "proposal": proposal,
        "evidence": evidence or [],
        "impact": impact,
        "alternatives": alternatives or [],
        "created_at": now,
        "status": "pending",
        "ceo_response": None,
        "resolved_at": None,
        "blocked_tasks": blocked_tasks or [],
    }
    items.append(item)
    _save(items)
    try:
        from .event_bus import log_event
        log_event("approval_submitted", agent="approval_queue", details={
            "id": apr_id, "level": level, "title": title[:100],
        })
    except Exception:
        pass
    logger.info(f"[APPROVAL] {level} submitted: {title} (id={apr_id})")
    return apr_id


def get_pending() -> List[Dict]:
    """Return all items with status 'pending'."""
    return [i for i in _load() if i["status"] == "pending"]


def get_all() -> List[Dict]:
    """Return all items regardless of status."""
    return _load()


def approve(apr_id: str, response: str = "") -> bool:
    """Mark an approval item as approved."""
    return _resolve(apr_id, "approved", response)


def reject(apr_id: str, response: str = "") -> bool:
    """Mark an approval item as rejected."""
    return _resolve(apr_id, "rejected", response)


def defer(apr_id: str, response: str = "") -> bool:
    """Mark an approval item as deferred."""
    return _resolve(apr_id, "deferred", response)


def _resolve(apr_id: str, status: str, response: str) -> bool:
    items = _load()
    for item in items:
        if item["id"] == apr_id and item["status"] == "pending":
            item["status"] = status
            item["ceo_response"] = response
            item["resolved_at"] = datetime.utcnow().isoformat() + "Z"
            _save(items)
            try:
                from .event_bus import log_event
                log_event("approval_resolved", agent="ceo", details={
                    "id": apr_id, "status": status,
                })
            except Exception:
                pass
            return True
    return False


def is_approved(apr_id: str) -> bool:
    """Return True if the given approval ID has been approved."""
    for item in _load():
        if item["id"] == apr_id:
            return item["status"] == "approved"
    return False


def get_blocked_tasks() -> List[str]:
    """Return all task IDs blocked by pending L3 items."""
    blocked = []
    for item in get_pending():
        if item["level"] == "L3":
            blocked.extend(item.get("blocked_tasks", []))
    return blocked


def format_briefing() -> str:
    """Format a human-readable briefing of all pending approval items."""
    pending = get_pending()
    if not pending:
        return "Approval queue empty. No pending items."
    lines = [f"## Pending Approvals ({len(pending)} items)\n"]
    for item in pending:
        icon = {"L2": "[SUSPEND]", "L3": "[BLOCK]"}.get(item["level"], "[?]")
        lines.append(f"### {icon} {item['title']}")
        lines.append(f"Category: {item['category']} | Time: {item['created_at'][:10]}")
        lines.append(f"Context: {item['context'][:200]}")
        lines.append(f"Proposal: {item['proposal'][:200]}")
        if item["impact"]:
            lines.append(f"Impact: {item['impact']}")
        if item["alternatives"]:
            lines.append(f"Alternatives: {' / '.join(item['alternatives'])}")
        lines.append(f"ID: {item['id']}\n")
    return "\n".join(lines)
