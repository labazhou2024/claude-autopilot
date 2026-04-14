"""
Input Validators -- unified input validation layer.

Shared validation functions for all components.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple


class ValidationError(ValueError):
    """Validation error"""

    pass


# Common regex patterns
FILE_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.]+$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SQL_KEYWORDS = re.compile(
    r"\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|EXECUTE|UNION|"
    r"SCRIPT|JAVASCRIPT|VBSCRIPT|ONERROR|ONLOAD|ONCLICK)\b",
    re.IGNORECASE,
)


def validate_task_id(task_id: str) -> str:
    """
    Validate task ID.

    Rules:
    - Length: 3-64 characters
    - Allowed: letters, digits, underscores, hyphens
    - Disallowed: special characters, SQL keywords
    """
    if not isinstance(task_id, str):
        raise ValidationError(f"task_id must be string, got {type(task_id)}")

    if len(task_id) < 3 or len(task_id) > 64:
        raise ValidationError(f"task_id length must be 3-64, got {len(task_id)}")

    if not FILE_NAME_PATTERN.match(task_id):
        raise ValidationError(f"task_id contains invalid characters: {task_id}")

    return task_id


def validate_agent_name(agent: str) -> str:
    """
    Validate agent name.

    Rules:
    - Length: 1-32 characters
    - Allowed: letters, digits, underscores
    """
    if not isinstance(agent, str):
        raise ValidationError(f"agent must be string, got {type(agent)}")

    if len(agent) < 1 or len(agent) > 32:
        raise ValidationError(f"agent length must be 1-32, got {len(agent)}")

    if not re.match(r"^[a-zA-Z0-9_]+$", agent):
        raise ValidationError(f"agent contains invalid characters: {agent}")

    return agent


def validate_context_key(key: str) -> str:
    """
    Validate context key name.

    Rules:
    - Length: 1-64 characters
    - Allowed: letters, digits, underscores, dots
    """
    if not isinstance(key, str):
        raise ValidationError(f"key must be string, got {type(key)}")

    if len(key) < 1 or len(key) > 64:
        raise ValidationError(f"key length must be 1-64, got {len(key)}")

    if not re.match(r"^[a-zA-Z0-9_\.]+$", key):
        raise ValidationError(f"key contains invalid characters: {key}")

    return key


def validate_date_string(date_str: str) -> str:
    """
    Validate date string (YYYY-MM-DD).
    """
    if not isinstance(date_str, str):
        raise ValidationError(f"date must be string, got {type(date_str)}")

    if not DATE_PATTERN.match(date_str):
        raise ValidationError(f"date must be YYYY-MM-DD format: {date_str}")

    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as e:
        raise ValidationError(f"invalid date: {date_str}, {e}")

    return date_str


def validate_days(days: int, min_days: int = 1, max_days: int = 3650) -> int:
    """
    Validate days parameter.

    Used for: time-range queries, data cleanup, etc.
    """
    if not isinstance(days, int):
        raise ValidationError(f"days must be integer, got {type(days)}")

    if days < min_days or days > max_days:
        raise ValidationError(f"days must be between {min_days}-{max_days}, got {days}")

    return days


def validate_file_path(
    path: str,
    must_exist: bool = False,
    base_dir: Optional[Path] = None,
) -> Path:
    """
    Validate file path.

    Rules:
    - Prevent path traversal attacks
    - Optional: verify file existence
    - Optional: verify within base directory
    """
    if not isinstance(path, (str, Path)):
        raise ValidationError(f"path must be string or Path, got {type(path)}")

    path_obj = Path(path).resolve()

    # Path traversal check
    if base_dir:
        base = Path(base_dir).resolve()
        try:
            path_obj.relative_to(base)
        except ValueError:
            raise ValidationError(f"path must be within {base}, got {path_obj}")

    # Existence check
    if must_exist and not path_obj.exists():
        raise ValidationError(f"file not found: {path_obj}")

    return path_obj


def sanitize_user_input(text: str, max_length: int = 10000) -> str:
    """
    Sanitize user input.

    Used for: WebSocket input, API params, etc.
    """
    if not isinstance(text, str):
        raise ValidationError(f"input must be string, got {type(text)}")

    # Length limit
    if len(text) > max_length:
        raise ValidationError(f"input exceeds max length {max_length}: {len(text)}")

    # Remove control characters (preserve newlines, tabs)
    sanitized = "".join(
        char
        for char in text
        if char == "\n"
        or char == "\t"
        or (ord(char) >= 32 and ord(char) <= 126)
        or ord(char) > 127  # Allow non-ASCII characters (e.g. CJK)
    )

    return sanitized


def validate_websocket_message(data: dict) -> Tuple[str, str]:
    """
    Validate WebSocket message format.

    Returns: (message_type, content)
    """
    if not isinstance(data, dict):
        raise ValidationError(f"message must be dict, got {type(data)}")

    msg_type = data.get("type")
    content = data.get("content")

    if not msg_type:
        raise ValidationError("message missing 'type' field")

    if not isinstance(msg_type, str):
        raise ValidationError(f"type must be string, got {type(msg_type)}")

    if msg_type not in ("chat", "ping", "command"):
        raise ValidationError(f"invalid message type: {msg_type}")

    if content and not isinstance(content, str):
        raise ValidationError(f"content must be string, got {type(content)}")

    return msg_type, content or ""


def check_sql_injection(text: str) -> bool:
    """
    Detect potential SQL injection.

    Returns: True if suspicious
    """
    if not isinstance(text, str):
        return False

    suspicious_patterns = [
        r"--\s*$",  # SQL comment
        r"/\*.*\*/",  # Block comment
        r"\bOR\s+1\s*=\s*1\b",
        r"\bDROP\s+TABLE\b",
        r"\bUNION\s+SELECT\b",
        r"\bEXEC\s*\(",
    ]

    for pattern in suspicious_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True

    return False


def validate_api_key(api_key: str) -> str:
    """
    Validate API key format.
    """
    if not isinstance(api_key, str):
        raise ValidationError(f"API key must be string, got {type(api_key)}")

    # Basic length check
    if len(api_key) < 10:
        raise ValidationError("API key too short (min 10 chars)")

    if len(api_key) > 512:
        raise ValidationError("API key too long (max 512 chars)")

    return api_key
