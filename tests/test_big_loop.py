"""Tests for big_loop -- Q1->Q6 quality cycle orchestrator."""

import pytest

from claude_autopilot.orchestration.big_loop import BigLoop, BigLoopResult, configure

# --- BigLoopResult dataclass ---


def test_big_loop_result_defaults():
    """BigLoopResult has sensible defaults."""
    r = BigLoopResult(
        loop_id="bigloop_123",
        timestamp="2026-01-01T00:00:00Z",
        duration_seconds=1.5,
    )
    assert r.bugs_found == 0
    assert r.bugs_fixed == 0
    assert r.regressions == 0
    assert r.success is True
    assert r.agent_specs == []
    assert r.error is None


def test_big_loop_result_to_dict():
    """to_dict returns a plain dict with all fields."""
    r = BigLoopResult(
        loop_id="loop_1",
        timestamp="2026-01-01T00:00:00Z",
        duration_seconds=2.0,
        success=False,
        error="oops",
    )
    d = r.to_dict()
    assert isinstance(d, dict)
    assert d["loop_id"] == "loop_1"
    assert d["success"] is False
    assert d["error"] == "oops"


# --- configure() ---


def test_configure_sets_data_dir(tmp_path):
    """configure() overrides the default data directory."""
    import claude_autopilot.orchestration.big_loop as bl_module

    configure(data_dir=tmp_path / "custom_data")
    loop = BigLoop(project_root=tmp_path)
    assert loop._data_dir == tmp_path / "custom_data"
    # Reset to avoid polluting other tests
    bl_module._data_dir_override = None


# --- q1_test_baseline (mock subprocess) ---


@pytest.mark.asyncio
async def test_q1_test_baseline_mock(tmp_path, monkeypatch):
    """q1_test_baseline writes baseline and returns structured result."""
    import claude_autopilot.orchestration.big_loop as bl_module

    # Configure module-level data dir to tmp_path so BigLoop uses it
    configure(data_dir=tmp_path / "data")

    fake_output = "tests/test_foo.py::test_bar PASSED\ntests/test_foo.py::test_baz FAILED\n"

    import subprocess as sp

    def mock_run(args, **kwargs):
        class FakeResult:
            returncode = 0
            stdout = fake_output
            stderr = ""

        return FakeResult()

    monkeypatch.setattr(sp, "run", mock_run)

    loop = BigLoop(project_root=tmp_path)
    result = await loop.q1_test_baseline()

    assert result["passed_count"] == 1
    assert result["failed_count"] == 1
    assert result["total"] == 2
    assert loop._baseline_file.exists()

    # Cleanup: reset module-level override
    bl_module._data_dir_override = None


# --- q1_5_flaky_detection (mock subprocess) ---


@pytest.mark.asyncio
async def test_q1_5_flaky_detection_no_failures(tmp_path):
    """q1_5_flaky_detection skips when q1 has no failures."""
    loop = BigLoop(project_root=tmp_path)
    q1_result = {"failed_tests": []}
    result = await loop.q1_5_flaky_detection(q1_result)
    assert result["skipped"] is True
    assert result["flaky"] == []
    assert result["real_failures"] == []


@pytest.mark.asyncio
async def test_q1_5_flaky_detection_real_failure(tmp_path, monkeypatch):
    """Consistently failing test is classified as real_failure (not flaky)."""
    import subprocess as sp

    def mock_run(args, **kwargs):
        class FakeResult:
            returncode = 1
            stdout = ""
            stderr = ""

        return FakeResult()

    monkeypatch.setattr(sp, "run", mock_run)

    loop = BigLoop(project_root=tmp_path)
    q1_result = {"failed_tests": ["tests/test_x.py::test_broken"]}
    result = await loop.q1_5_flaky_detection(q1_result)
    assert "tests/test_x.py::test_broken" in result["real_failures"]
    assert result["flaky"] == []


# --- q2_qa_review_spec ---


@pytest.mark.asyncio
async def test_q2_qa_review_spec_returns_valid_spec(tmp_path):
    """q2_qa_review_spec returns a dict with 'spec' and 'file_count'."""
    loop = BigLoop(project_root=tmp_path)
    result = await loop.q2_qa_review_spec()
    assert "spec" in result
    assert "file_count" in result
    spec = result["spec"]
    assert spec["agent"] == "qa-director"
    assert "files_to_review" in spec


# --- q3_fix_specs ---


@pytest.mark.asyncio
async def test_q3_fix_specs_groups_by_file(tmp_path):
    """q3_fix_specs groups bugs by their file field."""
    loop = BigLoop(project_root=tmp_path)
    bugs = [
        {"file": "src/foo.py", "description": "null pointer"},
        {"file": "src/foo.py", "description": "wrong return type"},
        {"file": "src/bar.py", "description": "off by one"},
    ]
    result = await loop.q3_fix_specs(bugs)
    specs = result["specs"]
    # Two files -> two specs
    assert len(specs) == 2
    assert result["total_bugs"] == 3
    assert result["batches"] == 2
    # Each spec targets one file
    for spec in specs:
        assert len(spec["target_files"]) == 1


@pytest.mark.asyncio
async def test_q3_fix_specs_empty(tmp_path):
    """q3_fix_specs returns skipped=True when no bugs provided."""
    loop = BigLoop(project_root=tmp_path)
    result = await loop.q3_fix_specs([])
    assert result["skipped"] is True
    assert result["specs"] == []
