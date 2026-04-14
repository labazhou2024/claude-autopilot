"""Tests for llm_router -- Claude CLI backend for autonomous agents."""

import subprocess
from unittest.mock import MagicMock

import pytest

from claude_autopilot.orchestration.llm_router import LLMRouter, TaskType

# --- TaskType enum ---


def test_task_type_values():
    """TaskType enum has expected string values."""
    assert TaskType.CHAT.value == "chat"
    assert TaskType.SUMMARY.value == "summary"
    assert TaskType.CODE_REVIEW.value == "code_review"
    assert TaskType.STRUCTURED_EXTRACT.value == "structured_extract"
    assert TaskType.DEEP_ANALYSIS.value == "deep_analysis"
    assert TaskType.EMBEDDING.value == "embedding"


# --- LLMRouter init ---


def test_llm_router_init():
    """LLMRouter initializes with zero call/error counts."""
    router = LLMRouter()
    assert router._call_count == 0
    assert router._error_count == 0
    assert isinstance(router._model_usage, dict)


def test_llm_router_get_client_returns_self():
    """get_client() returns self (backward compat)."""
    router = LLMRouter()
    assert router.get_client() is router


# --- get_stats ---


def test_get_stats_returns_dict():
    """get_stats returns a dict with required keys."""
    router = LLMRouter()
    stats = router.get_stats()
    assert isinstance(stats, dict)
    assert "provider" in stats
    assert "call_count" in stats
    assert "error_count" in stats
    assert "total_cost" in stats
    assert stats["provider"] == "claude-cli"
    assert stats["total_cost"] == 0.0


# --- route returns string ---


def test_route_returns_string():
    """route() returns a string model identifier."""
    router = LLMRouter()
    result = router.route(TaskType.CHAT)
    assert isinstance(result, str)
    assert "claude" in result.lower()


def test_route_all_task_types():
    """route() works for every TaskType without raising."""
    router = LLMRouter()
    for tt in TaskType:
        result = router.route(tt)
        assert isinstance(result, str)


# --- estimate_complexity ---


def test_estimate_complexity_simple():
    """Short code is classified as simple."""
    router = LLMRouter()
    short_code = "def foo():\n    return 1\n"
    assert router.estimate_complexity(short_code) == "simple"


def test_estimate_complexity_moderate():
    """Medium-sized code is classified as moderate."""
    router = LLMRouter()
    # 3 functions, ~110 lines
    funcs = "def f():\n    pass\n\n" * 6
    medium_code = funcs + "\n" * 100
    assert router.estimate_complexity(medium_code) == "moderate"


def test_estimate_complexity_complex():
    """Large code (>500 lines or >15 functions) is classified as complex."""
    router = LLMRouter()
    many_funcs = "def f():\n    pass\n\n" * 16
    complex_code = many_funcs
    assert router.estimate_complexity(complex_code) == "complex"


# --- call() with mocked subprocess ---


def test_call_success(monkeypatch):
    """call() returns stripped stdout on successful claude invocation."""
    fake_result = MagicMock()
    fake_result.returncode = 0
    fake_result.stdout = "  response text  "
    fake_result.stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: fake_result)

    router = LLMRouter()
    response = router.call(
        task_type=TaskType.CHAT,
        messages=[{"role": "user", "content": "hello"}],
    )
    assert response == "response text"
    assert router._call_count == 1
    assert router._error_count == 0


def test_call_increments_error_count_on_nonzero_returncode(monkeypatch):
    """call() increments error_count and raises when claude returns non-zero."""
    fake_result = MagicMock()
    fake_result.returncode = 1
    fake_result.stdout = ""
    fake_result.stderr = "some error"

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: fake_result)

    router = LLMRouter()
    with pytest.raises(RuntimeError, match="claude -p failed"):
        router.call(task_type=TaskType.CHAT, messages=[{"role": "user", "content": "hi"}])
    assert router._error_count == 1
