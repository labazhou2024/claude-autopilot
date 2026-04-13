"""
Auto-Trigger -- Self-triggering evolution conditions.

Checks harness state at session start and returns a list of actions
that should be executed autonomously (no human confirmation needed).

Integrates with: harness_state.json, EventBus, SemanticMemory, feature flags.

Usage (called by CTO at session start):
    from claude_autopilot.orchestration.auto_trigger import configure, check_triggers
    configure(harness_state_path=Path("harness_state.json"), project_root=Path("."))
    actions = check_triggers()
    for action in actions:
        print(f"Auto-trigger: {action['type']} -- {action['reason']}")
"""

import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Module-level configuration -- set via configure() before calling check_triggers()
_CONFIG: Dict[str, Any] = {}


def configure(
    harness_state_path: Optional[Path] = None,
    project_root: Optional[Path] = None,
    config: Optional[Dict] = None,
) -> None:
    """Configure auto-trigger paths and settings.

    Args:
        harness_state_path: Path to harness_state.json.
        project_root: Root directory of the project (used for git operations
                      and locating data files).
        config: Dict of runtime settings (e.g. feature_flags sub-key).
    """
    global _CONFIG
    _CONFIG = {
        "harness_path": Path(harness_state_path) if harness_state_path else Path.cwd() / "harness_state.json",
        "project_root": Path(project_root) if project_root else Path.cwd(),
        "config": config or {},
    }


def _get_harness_path() -> Path:
    return _CONFIG.get("harness_path", Path.cwd() / "harness_state.json")


def _get_project_root() -> Path:
    return _CONFIG.get("project_root", Path.cwd())


def _load_harness() -> Dict:
    harness_path = _get_harness_path()
    if harness_path.exists():
        return json.loads(harness_path.read_text(encoding="utf-8"))
    return {}


def _get_feature_flag(name: str, default: bool = False) -> bool:
    return _CONFIG.get("config", {}).get("feature_flags", {}).get(name, default)


def _count_commits_since(ref: str) -> int:
    """Count commits since a given ref."""
    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", f"{ref}..HEAD"],
            capture_output=True, text=True,
            cwd=str(_get_project_root()),
            timeout=10,
        )
        if result.returncode == 0:
            return int(result.stdout.strip())
    except Exception:
        pass
    return 0


def _run_pytest_quick() -> Dict[str, Any]:
    """Get pytest results using shared cache (no redundant subprocess)."""
    try:
        from claude_autopilot.orchestration.pytest_cache import get_test_results
        return get_test_results()
    except Exception as e:
        return {"passed": 0, "failed": 0, "errors": 1, "success": False,
                "output": str(e)}


def check_triggers() -> List[Dict[str, Any]]:
    """Check all auto-trigger conditions. Returns list of actions to execute.

    Each action: {"type": str, "reason": str, "priority": int, "data": dict}
    Priority: 1=critical, 2=high, 3=normal, 4=low

    Side effect: auto-increments session counter each time this is called,
    so the dream trigger actually fires after enough sessions.
    """
    actions: List[Dict[str, Any]] = []
    harness = _load_harness()
    autonomy = harness.get("autonomy", {})

    if not autonomy.get("enabled", False):
        return actions

    # Auto-increment session counter -- this is the missing link that
    # ensures autoDream eventually triggers. Each check_triggers() call
    # represents a new session start.
    increment_session_counter()
    # Reload harness to get updated counter
    harness = _load_harness()

    triggers = autonomy.get("auto_triggers", {})

    # 1. autoDream check
    if _get_feature_flag("auto_dream", False):
        dream_state = harness.get("auto_dream", {})
        sessions = dream_state.get("sessions_since_last_dream", 0)
        threshold = triggers.get("auto_dream_threshold", 5)
        if sessions >= threshold:
            actions.append({
                "type": "auto_dream",
                "reason": (
                    f"Accumulated {sessions} sessions (threshold {threshold}), "
                    "triggering auto-dream memory consolidation"
                ),
                "priority": 3,
                "data": {"sessions": sessions, "threshold": threshold},
            })

    # 2. mini-loop check (commits since last loop)
    # Find the first repo with a last_commit entry
    repos = harness.get("git_repos", {})
    repo_name = _CONFIG.get("config", {}).get("repo_name", next(iter(repos), "default"))
    last_commit = repos.get(repo_name, {}).get("last_commit", "")
    if last_commit:
        commits_since = _count_commits_since(last_commit)
        commit_threshold = triggers.get("mini_loop_commit_threshold", 10)
        if commits_since >= commit_threshold:
            actions.append({
                "type": "mini_loop",
                "reason": (
                    f"Accumulated {commits_since} commits (threshold {commit_threshold}), "
                    "triggering mini-loop (includes big_loop Q1-Q4)"
                ),
                "priority": 2,
                "data": {
                    "commits_since": commits_since,
                    "threshold": commit_threshold,
                    "big_loop": True,  # Signal CTO to run big_loop
                },
            })

    # 3. Test health check (always run at session start)
    if triggers.get("auto_fix_on_test_fail", False):
        test_result = _run_pytest_quick()
        if not test_result["success"]:
            actions.append({
                "type": "auto_fix_tests",
                "reason": (
                    f"Tests failed: {test_result['failed']} failed, "
                    f"{test_result['errors']} errors"
                ),
                "priority": 1,
                "data": test_result,
            })
        else:
            actions.append({
                "type": "tests_healthy",
                "reason": f"Tests passed: {test_result['passed']} passed",
                "priority": 4,
                "data": test_result,
            })

    # 4. Semantic memory consolidation check
    try:
        from claude_autopilot.learning.semantic_memory import get_semantic_memory, CONSOLIDATION_THRESHOLD
        sm = get_semantic_memory()
        if sm._episodes_since_consolidation >= CONSOLIDATION_THRESHOLD:
            actions.append({
                "type": "consolidate_memory",
                "reason": (
                    f"Semantic memory pending consolidation: "
                    f"{sm._episodes_since_consolidation} episodes awaiting consolidation"
                ),
                "priority": 3,
                "data": {"pending": sm._episodes_since_consolidation},
            })
    except Exception:
        pass

    # 5. EventBus error pattern check
    if triggers.get("auto_postmortem_error_threshold", 0) > 0:
        try:
            from claude_autopilot.core.event_bus import read_events
            recent = read_events(last_n=100)
            error_events = [
                e for e in recent
                if "fail" in e.get("type", "").lower()
                or "error" in e.get("type", "").lower()
            ]
            threshold = triggers["auto_postmortem_error_threshold"]
            if len(error_events) >= threshold:
                actions.append({
                    "type": "auto_postmortem",
                    "reason": (
                        f"Found {len(error_events)} errors in last 100 events "
                        f"(threshold {threshold}), post-mortem recommended"
                    ),
                    "priority": 2,
                    "data": {"error_count": len(error_events)},
                })
        except Exception:
            pass

    # 6. Pending CEO approvals
    try:
        from claude_autopilot.core.approval_queue import get_pending
        pending = get_pending()
        if pending:
            l3_count = sum(1 for p in pending if p["level"] == "L3")
            l2_count = sum(1 for p in pending if p["level"] == "L2")
            actions.append({
                "type": "pending_approvals",
                "reason": (
                    f"Approval queue: {l3_count} blocked + {l2_count} suspended, "
                    "pending CEO review"
                ),
                "priority": 1 if l3_count > 0 else 3,
                "data": {"l3": l3_count, "l2": l2_count, "items": pending},
            })
    except Exception:
        pass

    # 7. Pending agent specs from big_loop (CTO should invoke these)
    specs_file = _get_project_root() / "data" / "pending_agent_specs.json"
    if specs_file.exists():
        try:
            specs = json.loads(specs_file.read_text(encoding="utf-8"))
            if specs:
                actions.append({
                    "type": "pending_agent_specs",
                    "reason": (
                        f"Big loop pending: {len(specs)} agent tasks "
                        "(Q2/Q3/Q5/Q6) awaiting CTO dispatch"
                    ),
                    "priority": 2,
                    "data": {
                        "count": len(specs),
                        "agents": [s.get("agent", "?") for s in specs],
                    },
                })
        except Exception:
            pass

    # 8. Always queue briefing-agent for SessionStart summary
    actions.append({
        "type": "session_briefing",
        "reason": "SessionStart: scheduling briefing-agent for status report",
        "priority": 5,  # Low priority -- runs after all checks
        "data": {"agent": "briefing-agent", "trigger": "session_start"},
    })

    # Sort by priority
    actions.sort(key=lambda a: a["priority"])
    return actions


def format_briefing(actions: List[Dict]) -> str:
    """Format trigger check results as a briefing string."""
    if not actions:
        return "All systems nominal. No auto-triggers fired."

    lines = ["## Auto-Trigger Check Results\n"]
    priority_icons = {1: "[CRITICAL]", 2: "[HIGH]", 3: "[NORMAL]", 4: "[LOW]"}
    for a in actions:
        icon = priority_icons.get(a["priority"], "[INFO]")
        lines.append(f"{icon} **{a['type']}** -- {a['reason']}")

    critical = [a for a in actions if a["priority"] <= 2]
    if critical:
        lines.append(f"\nItems requiring immediate attention: {len(critical)}")

    return "\n".join(lines)


def increment_session_counter() -> None:
    """Increment sessions_since_last_dream in harness_state."""
    harness_path = _get_harness_path()
    harness = _load_harness()
    if "auto_dream" not in harness:
        harness["auto_dream"] = {"sessions_since_last_dream": 0, "dream_threshold": 5}
    harness["auto_dream"]["sessions_since_last_dream"] = (
        harness["auto_dream"].get("sessions_since_last_dream", 0) + 1
    )
    harness["updated_at"] = datetime.utcnow().isoformat() + "Z"
    harness_path.parent.mkdir(parents=True, exist_ok=True)
    harness_path.write_text(
        json.dumps(harness, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def reset_dream_counter() -> None:
    """Reset sessions_since_last_dream after autoDream completes."""
    harness_path = _get_harness_path()
    harness = _load_harness()
    if "auto_dream" in harness:
        harness["auto_dream"]["sessions_since_last_dream"] = 0
        harness["auto_dream"]["last_dream_time"] = datetime.utcnow().isoformat() + "Z"
    harness["updated_at"] = datetime.utcnow().isoformat() + "Z"
    harness_path.parent.mkdir(parents=True, exist_ok=True)
    harness_path.write_text(
        json.dumps(harness, indent=2, ensure_ascii=False), encoding="utf-8"
    )
