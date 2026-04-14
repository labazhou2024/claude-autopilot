"""Tests for worker_pool -- async parallel execution."""

import pytest

from claude_autopilot.core.worker_pool import WorkerPool


@pytest.mark.asyncio
async def test_submit_and_complete(tmp_path):
    pool = WorkerPool(max_workers=2, status_file=tmp_path / "status.json")

    def task(project):
        return {"success": True, "cost_usd": 0.01}

    await pool.submit({"id": "p1", "title": "Test"}, task)
    await pool.drain(timeout=10)

    status = pool.get_status()
    assert status.total_completed == 1
    assert status.total_failed == 0


@pytest.mark.asyncio
async def test_failed_task(tmp_path):
    pool = WorkerPool(max_workers=1)

    def failing_task(project):
        raise RuntimeError("Boom")

    await pool.submit({"id": "p1"}, failing_task)
    await pool.drain(timeout=10)

    status = pool.get_status()
    assert status.total_failed == 1


@pytest.mark.asyncio
async def test_max_workers_respected():
    pool = WorkerPool(max_workers=2)
    assert pool.max_workers == 2


def test_invalid_max_workers():
    with pytest.raises(ValueError):
        WorkerPool(max_workers=0)


@pytest.mark.asyncio
async def test_history(tmp_path):
    pool = WorkerPool(max_workers=1)

    def task(project):
        return {"success": True}

    await pool.submit({"id": "p1", "title": "First"}, task)
    await pool.drain(timeout=10)

    history = pool.get_history()
    assert len(history) == 1
    assert history[0]["project_id"] == "p1"
