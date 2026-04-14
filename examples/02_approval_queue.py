"""Example: CEO async approval workflow with L1/L2/L3 decisions."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from claude_autopilot.core import approval_queue

# Configure storage
approval_queue.configure(Path("./example_data"))

# L2 decision: needs human judgment but doesn't block
apr1 = approval_queue.submit_approval(
    level="L2",
    category="architecture",
    title="Migrate from JSON to SQLite for config storage",
    context="Current JSON config is 2MB and slow to parse on startup",
    proposal="Use SQLite with a key-value table for O(1) lookups",
    alternatives=["Keep JSON with caching", "Use TOML format"],
)
print(f"Submitted L2 approval: {apr1}")

# L3 decision: high-risk, blocks related work
apr2 = approval_queue.submit_approval(
    level="L3",
    category="deployment",
    title="Deploy v2.0 to production",
    context="All tests pass, staging verified for 48h",
    proposal="Rolling deploy with 10% canary",
    impact="Affects all users, rollback takes ~5min",
    blocked_tasks=["feature-x", "migration-y"],
)
print(f"Submitted L3 approval: {apr2}")

# Show the briefing (what CEO sees)
print("\n" + approval_queue.format_briefing())

# CEO approves the first, rejects the second
approval_queue.approve(apr1, "Good idea, proceed with SQLite")
approval_queue.reject(apr2, "Wait for Q3 release window")

print(f"\n{apr1} approved: {approval_queue.is_approved(apr1)}")
print(f"{apr2} approved: {approval_queue.is_approved(apr2)}")
print(f"Blocked tasks: {approval_queue.get_blocked_tasks()}")

# Cleanup
import shutil
shutil.rmtree("./example_data", ignore_errors=True)
