"""Tests for approval_queue -- CEO async approval system."""

from claude_autopilot.core import approval_queue


def test_submit_and_get(tmp_path):
    approval_queue.configure(tmp_path)
    apr_id = approval_queue.submit_approval(
        level="L2", category="architecture",
        title="Test Decision", context="Testing",
        proposal="Do something",
    )
    assert apr_id.startswith("apr_")
    pending = approval_queue.get_pending()
    assert len(pending) == 1
    assert pending[0]["title"] == "Test Decision"


def test_approve(tmp_path):
    approval_queue.configure(tmp_path)
    apr_id = approval_queue.submit_approval(
        level="L2", category="test",
        title="Approve Me", context="ctx", proposal="prop",
    )
    result = approval_queue.approve(apr_id, "Looks good")
    assert result is True
    assert approval_queue.is_approved(apr_id) is True
    assert len(approval_queue.get_pending()) == 0


def test_reject(tmp_path):
    approval_queue.configure(tmp_path)
    apr_id = approval_queue.submit_approval(
        level="L3", category="risk",
        title="Risky Change", context="ctx", proposal="prop",
    )
    result = approval_queue.reject(apr_id, "Too risky")
    assert result is True
    assert approval_queue.is_approved(apr_id) is False


def test_format_briefing_empty(tmp_path):
    approval_queue.configure(tmp_path)
    briefing = approval_queue.format_briefing()
    assert "empty" in briefing.lower() or "no pending" in briefing.lower()


def test_format_briefing_with_items(tmp_path):
    approval_queue.configure(tmp_path)
    approval_queue.submit_approval(
        level="L3", category="deploy",
        title="Deploy v2", context="ctx", proposal="prop",
    )
    briefing = approval_queue.format_briefing()
    assert "Deploy v2" in briefing
    assert "BLOCK" in briefing or "block" in briefing.lower()


def test_blocked_tasks(tmp_path):
    approval_queue.configure(tmp_path)
    approval_queue.submit_approval(
        level="L3", category="deploy",
        title="Blocked Task", context="ctx", proposal="prop",
        blocked_tasks=["task_1", "task_2"],
    )
    blocked = approval_queue.get_blocked_tasks()
    assert "task_1" in blocked
    assert "task_2" in blocked
