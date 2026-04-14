"""Tests for validators -- unified input validation layer."""

import pytest

from claude_autopilot.core.validators import (
    ValidationError,
    check_sql_injection,
    sanitize_user_input,
    validate_agent_name,
    validate_date_string,
    validate_file_path,
    validate_task_id,
)

# --- validate_task_id ---


def test_validate_task_id_valid():
    assert validate_task_id("my-task_01") == "my-task_01"


def test_validate_task_id_too_short():
    with pytest.raises(ValidationError, match="length"):
        validate_task_id("ab")


def test_validate_task_id_invalid_chars():
    with pytest.raises(ValidationError, match="invalid characters"):
        validate_task_id("task with spaces!")


# --- validate_agent_name ---


def test_validate_agent_name_valid():
    assert validate_agent_name("sonnet_executor") == "sonnet_executor"


def test_validate_agent_name_hyphen_rejected():
    with pytest.raises(ValidationError, match="invalid characters"):
        validate_agent_name("my-agent")


def test_validate_agent_name_too_long():
    with pytest.raises(ValidationError, match="length"):
        validate_agent_name("a" * 33)


# --- validate_date_string ---


def test_validate_date_string_valid():
    assert validate_date_string("2026-04-13") == "2026-04-13"


def test_validate_date_string_wrong_format():
    with pytest.raises(ValidationError):
        validate_date_string("13/04/2026")


def test_validate_date_string_invalid_date():
    with pytest.raises(ValidationError):
        validate_date_string("2026-13-01")


# --- validate_file_path ---


def test_validate_file_path_basic(tmp_path):
    """Valid path within base_dir is accepted."""
    f = tmp_path / "file.py"
    f.write_text("x")
    result = validate_file_path(str(f), base_dir=tmp_path)
    assert result == f.resolve()


def test_validate_file_path_traversal_rejected(tmp_path):
    """Path traversal outside base_dir raises ValidationError."""
    with pytest.raises(ValidationError, match="must be within"):
        validate_file_path(str(tmp_path / ".." / "etc" / "passwd"), base_dir=tmp_path)


# --- sanitize_user_input ---


def test_sanitize_user_input_removes_control_chars():
    """Control characters (except newline/tab) are stripped."""
    dirty = "hello\x00world\x01\x1f"
    clean = sanitize_user_input(dirty)
    assert "\x00" not in clean
    assert "hello" in clean
    assert "world" in clean


def test_sanitize_user_input_preserves_newline_tab():
    text = "line1\n\tline2"
    assert sanitize_user_input(text) == text


# --- check_sql_injection ---


def test_check_sql_injection_detected():
    # Patterns matched by check_sql_injection's suspicious_patterns list:
    # r"\bOR\s+1\s*=\s*1\b"
    assert check_sql_injection("1 OR 1=1") is True
    # r"\bDROP\s+TABLE\b"
    assert check_sql_injection("DROP TABLE users") is True
    # r"\bUNION\s+SELECT\b"
    assert check_sql_injection("UNION SELECT * FROM secrets") is True
    # r"--\s*$"  (SQL comment at end of line)
    assert check_sql_injection("admin'--") is True


def test_check_sql_injection_clean():
    assert check_sql_injection("hello world") is False
    assert check_sql_injection("my_variable_name") is False
