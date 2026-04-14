"""Example: Using EventBus for append-only event logging."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from claude_autopilot.core import event_bus

# Configure data directory
event_bus.configure(Path("./example_data"))

# Log some events
event_bus.log_event("task_started", agent="my-agent", details={"task": "refactor auth"})
event_bus.log_event("task_completed", agent="my-agent", details={"result": "success", "lines_changed": 42})
event_bus.log_event("test_failed", agent="test-runner", details={"test": "test_login", "error": "timeout"})

# Read recent events
events = event_bus.read_events(last_n=10)
print(f"Recent events: {len(events)}")
for e in events:
    print(f"  [{e['type']}] agent={e['agent']} | {e.get('details', {})}")

# Count by type
counts = event_bus.count_events_by_type()
print(f"\nEvent counts: {counts}")

# Cleanup
import shutil
shutil.rmtree("./example_data", ignore_errors=True)
