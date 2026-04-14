"""Tests for auto_trigger -- self-triggering evolution conditions."""

import json

import claude_autopilot.orchestration.auto_trigger as at_module
from claude_autopilot.orchestration.auto_trigger import (
    configure,
    format_briefing,
)


def _reset_config():
    """Reset module-level config between tests."""
    at_module._CONFIG = {}


# --- configure() ---


def test_configure_sets_paths(tmp_path):
    """configure() stores harness_path and project_root in _CONFIG."""
    harness = tmp_path / "harness_state.json"
    configure(harness_state_path=harness, project_root=tmp_path)
    assert at_module._CONFIG["harness_path"] == harness
    assert at_module._CONFIG["project_root"] == tmp_path
    _reset_config()


def test_configure_defaults_when_no_args(tmp_path):
    """configure() with no args sets defaults without raising."""
    configure()
    assert "harness_path" in at_module._CONFIG
    assert "project_root" in at_module._CONFIG
    _reset_config()


# --- check_triggers with autonomy disabled ---


def test_check_triggers_returns_empty_when_autonomy_disabled(tmp_path):
    """check_triggers returns [] when harness has autonomy.enabled=False."""
    harness_file = tmp_path / "harness_state.json"
    harness_file.write_text(
        json.dumps({"autonomy": {"enabled": False}}),
        encoding="utf-8",
    )
    configure(harness_state_path=harness_file, project_root=tmp_path)
    actions = at_module.check_triggers()
    assert actions == []
    _reset_config()


def test_check_triggers_returns_empty_when_no_harness(tmp_path):
    """check_triggers returns [] when harness file is missing (autonomy off by default)."""
    configure(harness_state_path=tmp_path / "missing.json", project_root=tmp_path)
    actions = at_module.check_triggers()
    assert actions == []
    _reset_config()


# --- format_briefing ---


def test_format_briefing_empty_actions():
    """format_briefing with no actions returns the 'nominal' message."""
    result = format_briefing([])
    assert "nominal" in result.lower() or "no auto-triggers" in result.lower()


def test_format_briefing_with_actions():
    """format_briefing with actions includes type and reason text."""
    actions = [
        {
            "type": "auto_dream",
            "reason": "5 sessions accumulated",
            "priority": 3,
            "data": {},
        },
        {
            "type": "mini_loop",
            "reason": "10 commits accumulated",
            "priority": 2,
            "data": {},
        },
    ]
    result = format_briefing(actions)
    assert "auto_dream" in result
    assert "mini_loop" in result
    assert "5 sessions" in result


def test_format_briefing_critical_items_highlighted():
    """format_briefing mentions count of critical items when priority <= 2."""
    actions = [
        {"type": "auto_fix_tests", "reason": "tests failed", "priority": 1, "data": {}},
    ]
    result = format_briefing(actions)
    assert "immediate" in result.lower() or "critical" in result.lower() or "1" in result
