"""Tests for atomic_io -- atomic file write utilities."""

import json

from claude_autopilot.core.atomic_io import atomic_write_json, atomic_write_text, safe_read_json


def test_atomic_write_json_roundtrip(tmp_path):
    """Write JSON data and read it back intact."""
    target = tmp_path / "state.json"
    data = {"key": "value", "count": 42, "nested": {"a": [1, 2, 3]}}
    atomic_write_json(target, data)
    assert target.exists()
    read_back = json.loads(target.read_text(encoding="utf-8"))
    assert read_back == data


def test_atomic_write_json_creates_parent_dirs(tmp_path):
    """atomic_write_json creates missing parent directories."""
    target = tmp_path / "deep" / "nested" / "file.json"
    atomic_write_json(target, {"x": 1})
    assert target.exists()
    assert json.loads(target.read_text())["x"] == 1


def test_atomic_write_json_backup(tmp_path):
    """When backup=True, a .bak file is created from the old content."""
    target = tmp_path / "data.json"
    atomic_write_json(target, {"version": 1})
    atomic_write_json(target, {"version": 2}, backup=True)
    bak = target.with_suffix(".json.bak")
    assert bak.exists()
    old_data = json.loads(bak.read_text(encoding="utf-8"))
    assert old_data["version"] == 1
    new_data = json.loads(target.read_text(encoding="utf-8"))
    assert new_data["version"] == 2


def test_atomic_write_text_roundtrip(tmp_path):
    """Write text content and read it back."""
    target = tmp_path / "output.txt"
    content = "Hello, world!\nLine two.\n"
    atomic_write_text(target, content)
    assert target.read_text(encoding="utf-8") == content


def test_safe_read_json_valid(tmp_path):
    """safe_read_json parses a valid JSON file."""
    target = tmp_path / "valid.json"
    target.write_text('{"a": 1}', encoding="utf-8")
    result = safe_read_json(target)
    assert result == {"a": 1}


def test_safe_read_json_missing_file(tmp_path):
    """safe_read_json returns default when file does not exist."""
    target = tmp_path / "nonexistent.json"
    result = safe_read_json(target, default={"default": True})
    assert result == {"default": True}


def test_safe_read_json_corrupt_returns_default(tmp_path):
    """safe_read_json returns default on malformed JSON without raising."""
    target = tmp_path / "corrupt.json"
    target.write_text("not valid json {{{{", encoding="utf-8")
    result = safe_read_json(target, default=[])
    assert result == []
