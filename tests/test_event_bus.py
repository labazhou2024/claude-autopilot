"""Tests for event_bus -- append-only JSONL event sourcing."""

from claude_autopilot.core import event_bus


def test_log_and_read(tmp_path):
    data_dir = tmp_path / "data"
    event_bus.configure(data_dir)
    event_bus.log_event("test_event", agent="test", details={"key": "value"})
    events = event_bus.read_events(last_n=10)
    assert len(events) == 1
    assert events[0]["type"] == "test_event"
    assert events[0]["agent"] == "test"
    assert events[0]["details"]["key"] == "value"


def test_multiple_events(tmp_path):
    data_dir = tmp_path / "data"
    event_bus.configure(data_dir)
    for i in range(5):
        event_bus.log_event(f"event_{i}", agent="test")
    events = event_bus.read_events(last_n=10)
    assert len(events) == 5


def test_read_empty(tmp_path):
    data_dir = tmp_path / "data"
    event_bus.configure(data_dir)
    events = event_bus.read_events(last_n=10)
    assert events == []


def test_event_count(tmp_path):
    data_dir = tmp_path / "data"
    event_bus.configure(data_dir)
    for i in range(3):
        event_bus.log_event("count_test", agent="test")
    count = event_bus.get_event_count()
    assert count == 3


def test_count_by_type(tmp_path):
    data_dir = tmp_path / "data"
    event_bus.configure(data_dir)
    event_bus.log_event("type_a", agent="test")
    event_bus.log_event("type_a", agent="test")
    event_bus.log_event("type_b", agent="test")
    counts = event_bus.count_events_by_type()
    assert counts["type_a"] == 2
    assert counts["type_b"] == 1
