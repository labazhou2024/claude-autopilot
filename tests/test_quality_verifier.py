"""Tests for quality_verifier -- multi-signal quality scoring."""

import pytest

import claude_autopilot.orchestration.quality_verifier as qv_module
from claude_autopilot.orchestration.quality_verifier import (
    WEIGHTS,
    QualityReport,
    configure,
    verify_quality,
)

# --- QualityReport dataclass ---


def test_quality_report_to_dict():
    """QualityReport.to_dict returns a plain dict."""
    report = QualityReport(
        score=0.75,
        signals={"tests_pass": 1.0},
        verdict="good",
        details="[good] score=0.75",
        score_1_5=4,
    )
    d = report.to_dict()
    assert isinstance(d, dict)
    assert d["score"] == 0.75
    assert d["verdict"] == "good"
    assert d["score_1_5"] == 4


# --- WEIGHTS sum to 1.0 ---


def test_weights_sum_to_one():
    """Signal weights must sum exactly to 1.0 (GVU theorem requires calibrated verifier)."""
    total = sum(WEIGHTS.values())
    assert abs(total - 1.0) < 1e-9, f"WEIGHTS sum={total}, expected 1.0"


# --- configure() ---


def test_configure_sets_project_root(tmp_path):
    """configure() overrides the project root."""
    configure(project_root=tmp_path)
    assert qv_module._project_root_override == tmp_path
    # Reset
    qv_module._project_root_override = None


def test_configure_sets_data_dir(tmp_path):
    """configure() overrides the data directory."""
    configure(data_dir=tmp_path / "mydata")
    assert qv_module._data_dir_override == tmp_path / "mydata"
    # Reset
    qv_module._data_dir_override = None


# --- verify_quality with failed result ---


@pytest.mark.asyncio
async def test_verify_quality_failed_result_returns_failed_verdict(tmp_path):
    """verify_quality returns verdict='failed' when result.success is False."""
    project = {"title": "Test project"}
    result = {"success": False, "error": "subprocess crashed"}

    report = await verify_quality(project, result)

    assert report.verdict == "failed"
    assert report.score < 0.45  # Below "acceptable" threshold
    assert report.score_1_5 == 1


@pytest.mark.asyncio
async def test_verify_quality_failed_skips_expensive_checks(tmp_path):
    """When success=False, signals are all near-zero except llm_judge=0.1."""
    project = {"title": "Broken task"}
    result = {"success": False, "error": "timeout"}

    report = await verify_quality(project, result)

    # All objective signals should be 0.0
    assert report.signals.get("tests_pass", 0.0) == 0.0
    assert report.signals.get("syntax_valid", 0.0) == 0.0
    # llm_judge gets a tiny 0.1 credit
    assert report.signals.get("llm_judge", 0.0) == pytest.approx(0.1)


@pytest.mark.asyncio
async def test_verify_quality_report_has_all_signal_keys(tmp_path, monkeypatch):
    """Returned report.signals contains all keys from WEIGHTS."""
    # Mock all subprocess-based checks to avoid side effects
    monkeypatch.setattr(
        "claude_autopilot.orchestration.quality_verifier._check_tests_pass", lambda: 0.5
    )
    monkeypatch.setattr(
        "claude_autopilot.orchestration.quality_verifier._check_syntax_valid", lambda: 0.5
    )
    monkeypatch.setattr(
        "claude_autopilot.orchestration.quality_verifier._check_review_clean", lambda: 0.5
    )
    monkeypatch.setattr(
        "claude_autopilot.orchestration.quality_verifier._check_no_regressions", lambda: 0.5
    )

    async def mock_llm_judge(project, result):
        return 0.5

    monkeypatch.setattr(
        "claude_autopilot.orchestration.quality_verifier._check_llm_judge", mock_llm_judge
    )

    project = {"title": "A task"}
    result = {"success": True, "output": "Done.", "duration_seconds": 30}

    report = await verify_quality(project, result)

    for key in WEIGHTS:
        assert key in report.signals, f"Missing signal key: {key}"
