"""Shared test fixtures for claude-autopilot."""

import sys
from pathlib import Path

# Ensure src/ is on the path (handles Unicode directory names on Windows)
_SRC_DIR = str(Path(__file__).parent.parent / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import pytest  # noqa: E402


@pytest.fixture
def tmp_data_dir(tmp_path):
    """Provide a temporary data directory for tests."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


@pytest.fixture
def sample_python_file(tmp_path):
    """Create a sample Python file for review testing."""
    f = tmp_path / "sample.py"
    f.write_text('def hello():\n    return "world"\n', encoding="utf-8")
    return f


@pytest.fixture
def sample_python_file_with_issues(tmp_path):
    """Create a Python file with known review issues."""
    f = tmp_path / "bad_sample.py"
    f.write_text(
        'import os\nimport sys\n\ndef run():\n    os.system("rm -rf /")\n    eval(input())\n',
        encoding="utf-8",
    )
    return f
