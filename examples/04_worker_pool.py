"""Example: Parallel task execution with WorkerPool."""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from claude_autopilot.core.worker_pool import WorkerPool


def simulate_task(project: dict) -> dict:
    """Simulate a long-running task."""
    duration = project.get("duration", 1)
    time.sleep(duration)
    if project.get("should_fail"):
        raise RuntimeError(f"Task {project['id']} failed intentionally")
    return {"success": True, "cost_usd": duration * 0.01}


async def main():
    pool = WorkerPool(max_workers=3, status_file=Path("./pool_status.json"))

    # Submit 5 tasks (3 will run in parallel, 2 will queue)
    tasks = [
        {"id": "task-1", "title": "Refactor auth module", "duration": 2},
        {"id": "task-2", "title": "Fix login bug", "duration": 1},
        {"id": "task-3", "title": "Update docs", "duration": 1, "should_fail": True},
        {"id": "task-4", "title": "Add tests", "duration": 1},
        {"id": "task-5", "title": "Code review", "duration": 1},
    ]

    print(f"Submitting {len(tasks)} tasks to pool (max {pool.max_workers} workers)...")
    for task in tasks:
        await pool.submit(task, simulate_task)
        status = pool.get_status()
        print(f"  Submitted {task['id']}: {status.active_workers} active, {status.idle_workers} idle")

    # Wait for all to complete
    await pool.drain(timeout=30)

    status = pool.get_status()
    print(f"\nCompleted: {status.total_completed}")
    print(f"Failed: {status.total_failed}")
    print(f"Total cost: ${status.total_cost_usd:.2f}")

    # Show history
    for entry in pool.get_history():
        icon = "+" if entry["success"] else "x"
        print(f"  [{icon}] {entry['project_title']} ({entry['state']})")

    # Cleanup
    Path("./pool_status.json").unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(main())
