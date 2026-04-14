"""Tests for local_reviewer -- zero-cost static analysis gate."""

from pathlib import Path

from claude_autopilot.core.local_reviewer import review_file, review_files


def test_valid_python(tmp_path):
    f = tmp_path / "good.py"
    f.write_text('def hello():\n    return "world"\n', encoding="utf-8")
    findings = review_file(f)
    critical = [x for x in findings if x.severity in ("critical", "high")]
    assert len(critical) == 0


def test_syntax_error(tmp_path):
    f = tmp_path / "bad.py"
    f.write_text("def foo(\n", encoding="utf-8")
    findings = review_file(f)
    assert any(x.severity == "critical" and x.category == "syntax" for x in findings)


def test_security_eval(tmp_path):
    f = tmp_path / "eval_usage.py"
    f.write_text("x = eval(input())\n", encoding="utf-8")
    findings = review_file(f)
    assert any("eval" in x.message for x in findings)


def test_security_os_system(tmp_path):
    f = tmp_path / "os_system.py"
    f.write_text('import os\nos.system("ls")\n', encoding="utf-8")
    findings = review_file(f)
    assert any("os.system" in x.message for x in findings)


def test_review_files_pass(tmp_path):
    f = tmp_path / "ok.py"
    f.write_text("x = 1\n", encoding="utf-8")
    result = review_files([str(f)])
    assert result.passed is True
    assert result.files_reviewed == 1


def test_review_files_fail(tmp_path):
    f = tmp_path / "bad.py"
    f.write_text("eval(input())\n", encoding="utf-8")
    result = review_files([str(f)])
    assert result.passed is False
    assert len(result.blocking) > 0


def test_nonexistent_file():
    findings = review_file(Path("/nonexistent/file.py"))
    assert len(findings) == 1
    assert findings[0].severity == "critical"


def test_summary_format(tmp_path):
    f = tmp_path / "ok.py"
    f.write_text("x = 1\n", encoding="utf-8")
    result = review_files([str(f)])
    assert "PASSED" in result.summary
