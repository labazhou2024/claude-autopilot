"""Tests for episodic_log -- event sourcing for agent actions."""

import pytest

from claude_autopilot.core.episodic_log import EpisodicLog


@pytest.mark.asyncio
async def test_initialize_and_log_and_get_history(tmp_path):
    """Initialize log, write an entry, retrieve it by task_id."""
    db = tmp_path / "episodic.db"
    log = EpisodicLog(db_path=db)
    await log.initialize()

    await log.log(
        agent="test_agent",
        action="task_start",
        task_id="task-001",
        details={"info": "hello"},
        immediate=True,
    )

    history = await log.get_task_history("task-001")
    assert len(history) == 1
    assert history[0]["agent"] == "test_agent"
    assert history[0]["action"] == "task_start"
    assert history[0]["details"]["info"] == "hello"


@pytest.mark.asyncio
async def test_buffer_flush_on_threshold(tmp_path):
    """Buffer flushes automatically when _buffer_size entries accumulate."""
    db = tmp_path / "buf.db"
    log = EpisodicLog(db_path=db)
    log._buffer_size = 3
    await log.initialize()

    # Write exactly 3 entries -- third one triggers flush
    for i in range(3):
        await log.log(agent="bot", action="step", task_id="t1", details={"i": i})

    # Buffer should be empty after auto-flush
    assert len(log._buffer) == 0

    history = await log.get_task_history("t1")
    assert len(history) == 3


@pytest.mark.asyncio
async def test_close_flushes_buffer(tmp_path):
    """close() flushes any remaining buffered entries."""
    db = tmp_path / "close.db"
    log = EpisodicLog(db_path=db)
    log._buffer_size = 100  # Large threshold so auto-flush won't fire
    await log.initialize()

    await log.log(agent="bot", action="work", task_id="t2", details={})
    # Buffer still holds the entry
    assert len(log._buffer) == 1

    await log.close()
    assert len(log._buffer) == 0

    history = await log.get_task_history("t2")
    assert len(history) == 1


@pytest.mark.asyncio
async def test_multiple_tasks_isolated(tmp_path):
    """Entries for different task_ids are returned separately."""
    db = tmp_path / "multi.db"
    log = EpisodicLog(db_path=db)
    await log.initialize()

    await log.log(agent="a", action="x", task_id="taskA", immediate=True)
    await log.log(agent="b", action="y", task_id="taskB", immediate=True)
    await log.log(agent="a", action="z", task_id="taskA", immediate=True)

    history_a = await log.get_task_history("taskA")
    history_b = await log.get_task_history("taskB")
    assert len(history_a) == 2
    assert len(history_b) == 1


@pytest.mark.asyncio
async def test_get_history_empty_task(tmp_path):
    """get_task_history returns empty list for unknown task_id."""
    db = tmp_path / "empty.db"
    log = EpisodicLog(db_path=db)
    await log.initialize()

    history = await log.get_task_history("nonexistent")
    assert history == []
