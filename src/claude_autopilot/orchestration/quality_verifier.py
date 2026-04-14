"""
Quality Verifier -- Low-noise multi-signal scoring for agent outputs.

Replaces _compute_quality_score's pure-rule approach with objective signals.

GVU theorem: verifier noise is the sole bottleneck for exponential evolution.
Old verifier noise: ~100% (rule-based, garbage gets 4/5).
New verifier noise: ~13% (weighted: 50% objective + 20% semi-objective + 30% LLM).

Signal weights:
  tests_pass      0.15  -- pytest all pass after execution
  no_regressions  0.15  -- no new failures vs baseline
  syntax_valid    0.10  -- all .py files ast.parse OK
  review_clean    0.10  -- local_reviewer no critical/high
  commit_made     0.10  -- git commit actually happened
  diff_reasonable 0.10  -- change size within reasonable range
  llm_judge       0.30  -- LLM independent quality evaluation

Usage:
    from claude_autopilot.orchestration.quality_verifier import verify_quality
    report = await verify_quality(project, result)
    print(report.score, report.verdict)
"""

import ast
import json
import logging
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Module-level configurable roots (overridable via configure())
_project_root_override: Optional[Path] = None
_data_dir_override: Optional[Path] = None


def _get_project_root() -> Path:
    """Return configured project root, defaulting to cwd."""
    if _project_root_override is not None:
        return _project_root_override
    return Path.cwd()


def _get_data_dir() -> Path:
    """Return configured data dir, defaulting to cwd/data."""
    if _data_dir_override is not None:
        return _data_dir_override
    return Path.cwd() / "data"


def configure(project_root: Path = None, data_dir: Path = None) -> None:
    """Configure module-level path defaults.

    Args:
        project_root: Override project root for git commands and syntax checks
                      (default: cwd).
        data_dir: Override the data directory for baseline files (default: cwd/data).
    """
    global _project_root_override, _data_dir_override
    if project_root is not None:
        _project_root_override = Path(project_root)
    if data_dir is not None:
        _data_dir_override = Path(data_dir)


def _get_baseline_file() -> Path:
    return _get_data_dir() / "test_baseline_q1.json"


# Signal weights — must sum to 1.0
WEIGHTS = {
    "tests_pass": 0.15,
    "no_regressions": 0.15,
    "syntax_valid": 0.10,
    "review_clean": 0.10,
    "commit_made": 0.10,
    "diff_reasonable": 0.10,
    "llm_judge": 0.30,
}

# Verdict thresholds
VERDICT_THRESHOLDS = {
    "good": 0.70,
    "acceptable": 0.45,
    "poor": 0.25,
    # below 0.25 = "failed"
}


@dataclass
class QualityReport:
    """Result of quality verification."""

    score: float  # 0.0 - 1.0 weighted score
    signals: Dict[str, float]  # individual signal values (0.0 - 1.0)
    verdict: str  # "good" / "acceptable" / "poor" / "failed"
    details: str  # human-readable summary
    score_1_5: int  # legacy 1-5 scale for backward compat

    def to_dict(self) -> dict:
        return asdict(self)


def _check_tests_pass() -> float:
    """Check pytest results using shared cache (no redundant subprocess)."""
    try:
        from .pytest_cache import get_test_results

        results = get_test_results()
        if results.get("success"):
            return 1.0
        if results.get("timeout") or results.get("error"):
            return 0.5  # infrastructure -> neutral
        return 0.0
    except ImportError:
        return 0.5
    except Exception:
        return 0.5


def _check_no_regressions() -> float:
    """Compare current test count vs baseline using shared cache."""
    baseline_file = _get_baseline_file()
    if not baseline_file.exists():
        return 0.5

    try:
        baseline = json.loads(baseline_file.read_text(encoding="utf-8"))
        baseline_passed = baseline.get("passed_count", 0)

        from .pytest_cache import get_test_results

        results = get_test_results()
        current_passed = results.get("passed", 0)

        if current_passed >= baseline_passed:
            return 1.0
        return max(0.0, current_passed / max(baseline_passed, 1))
    except ImportError:
        return 0.5
    except Exception:
        return 0.5


def _check_syntax_valid() -> float:
    """Check all .py files in src directory parse correctly."""
    core_dir = _get_project_root() / "src"
    if not core_dir.exists():
        return 0.5

    total = 0
    valid = 0
    for f in core_dir.glob("*.py"):
        if f.name == "__init__.py":
            continue
        total += 1
        try:
            ast.parse(f.read_text(encoding="utf-8"))
            valid += 1
        except SyntaxError:
            logger.warning("Syntax error in %s", f.name)

    return valid / max(total, 1)


def _check_review_clean() -> float:
    """Run local_reviewer on recently modified files. 1.0 if no critical/high."""
    try:
        # Get recently modified .py files (last 30 min)
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1"],
            capture_output=True,
            text=True,
            cwd=str(_get_project_root()),
            timeout=10,
        )
        py_files = [
            f
            for f in result.stdout.strip().splitlines()
            if f.endswith(".py") and not f.startswith("tests/")
        ]

        if not py_files:
            return 1.0  # no files to review

        from .local_reviewer import review_files

        r = review_files(py_files[:10])  # cap at 10
        critical_high = sum(1 for f in r.findings if f.severity in ("critical", "high"))
        return 1.0 if critical_high == 0 else 0.0
    except ImportError:
        return 0.5  # local_reviewer unavailable -> neutral
    except Exception:
        return 0.5  # infra failure -> neutral


def _check_commit_made(result: Dict) -> float:
    """Check if a git commit was made during the project's execution window.

    The old approach string-matched on result["output"] for keywords like
    "committed" or "[main ".  This fails because claude -p --output-format json
    returns only the final assistant text, not tool-call stdout (where git
    output lives).  Average signal was 0.14 -- almost always 0.0 even when
    commits were actually made.

    New approach: query git log for commits within the execution duration.
    Falls back to output string matching if git is unavailable.
    """
    duration = result.get("duration_seconds", 0)
    if duration > 0:
        # Add 60s buffer for clock skew / commit happening just after
        since_seconds = int(duration) + 60
        try:
            git_result = subprocess.run(
                ["git", "log", "--oneline", f"--since={since_seconds} seconds ago"],
                capture_output=True,
                text=True,
                cwd=str(_get_project_root()),
                timeout=10,
            )
            commits = [ln for ln in git_result.stdout.strip().splitlines() if ln.strip()]
            if len(commits) > 0:
                return 1.0
            # No commits in window — could be a read-only task, give partial credit
            # if turns suggest substantial work
            if result.get("num_turns", 0) > 5:
                return 0.3  # work done but no commit (e.g. analysis task)
            return 0.0
        except Exception:
            pass  # fall through to string matching

    # Fallback: string matching on output (unreliable but better than nothing)
    output = (result.get("output") or "").lower()
    commit_signals = ["committed", "commit ", "git add", "[main ", "files changed"]
    return 1.0 if any(s in output for s in commit_signals) else 0.0


def _check_diff_reasonable(result: Dict) -> float:
    """Check if code changes are reasonable size via git diff --stat."""
    # Use actual git diff instead of parsing output text (same issue as commit_made)
    try:
        git_result = subprocess.run(
            ["git", "diff", "--stat", "HEAD~1"],
            capture_output=True,
            text=True,
            cwd=str(_get_project_root()),
            timeout=10,
        )
        stat_output = git_result.stdout.strip()
        match = re.search(r"(\d+)\s+files?\s+changed", stat_output)
        if match:
            files_changed = int(match.group(1))
            if files_changed == 0:
                return 0.0
            if files_changed > 30:
                return 0.3  # suspiciously large
            return 1.0
    except Exception:
        pass

    # Fallback: infer from turns
    turns = result.get("num_turns", 0)
    if turns > 3:
        return 0.7  # some work done
    return 0.3  # probably too little


async def _check_llm_judge(project: Dict, result: Dict) -> float:
    """Use LLM Judge for independent quality evaluation. Returns 0-1."""
    try:
        from .llm_judge import judge

        title = project.get("title", "")
        output = (result.get("output") or "")[:3000]

        verdict = await judge(
            task_description=title,
            output=output,
            context=f"Cost: ${result.get('cost_usd', 0):.3f}, "
            f"Turns: {result.get('num_turns', 0)}, "
            f"Success: {result.get('success', False)}",
        )
        score = verdict.get("score", 3)
        # Normalize 1-5 -> 0-1
        return max(0.0, min(1.0, (score - 1) / 4))
    except Exception as e:
        logger.warning("LLM Judge unavailable: %s -- using fallback 0.5", e)
        return 0.5  # LLM Judge unavailable -> neutral fallback


async def verify_quality(project: Dict, result: Dict) -> QualityReport:
    """Core verification function. Returns multi-signal quality report.

    Args:
        project: project dict (title, prompt, priority, etc.)
        result: Execution result (success, output, cost, turns, etc.)

    Returns:
        QualityReport with weighted score, individual signals, and verdict.
    """
    signals = {}

    # Fast objective checks (no API, no subprocess for some)
    if not result.get("success"):
        # Failed execution -> skip expensive checks
        signals = {k: 0.0 for k in WEIGHTS}
        signals["llm_judge"] = 0.1  # tiny credit for attempting
        score = sum(signals[k] * WEIGHTS[k] for k in WEIGHTS)
        return QualityReport(
            score=round(score, 3),
            signals=signals,
            verdict="failed",
            details=f"Execution failed: {result.get('error', 'unknown')}",
            score_1_5=1,
        )

    # Run all checks
    signals["tests_pass"] = _check_tests_pass()
    signals["syntax_valid"] = _check_syntax_valid()
    signals["review_clean"] = _check_review_clean()
    signals["commit_made"] = _check_commit_made(result)
    signals["diff_reasonable"] = _check_diff_reasonable(result)

    # Skip expensive regression check if tests already fail
    if signals["tests_pass"] >= 1.0:
        signals["no_regressions"] = _check_no_regressions()
    else:
        signals["no_regressions"] = 0.0

    # LLM Judge (async, may timeout)
    signals["llm_judge"] = await _check_llm_judge(project, result)

    # Weighted score
    score = sum(signals[k] * WEIGHTS[k] for k in WEIGHTS)
    score = round(max(0.0, min(1.0, score)), 3)

    # Verdict
    if score >= VERDICT_THRESHOLDS["good"]:
        verdict = "good"
    elif score >= VERDICT_THRESHOLDS["acceptable"]:
        verdict = "acceptable"
    elif score >= VERDICT_THRESHOLDS["poor"]:
        verdict = "poor"
    else:
        verdict = "failed"

    # Legacy 1-5 scale
    score_1_5 = max(1, min(5, round(score * 4 + 1)))

    # Human-readable details
    details_parts = []
    for k in sorted(WEIGHTS, key=lambda x: -WEIGHTS[x]):
        val = signals[k]
        icon = "+" if val >= 0.7 else ("-" if val <= 0.3 else "~")
        details_parts.append(f"{icon}{k}={val:.1f}")
    details = f"[{verdict}] score={score:.2f} | " + " ".join(details_parts)

    return QualityReport(
        score=score,
        signals={k: round(v, 3) for k, v in signals.items()},
        verdict=verdict,
        details=details,
        score_1_5=score_1_5,
    )


def verify_quality_sync(project: Dict, result: Dict) -> QualityReport:
    """Synchronous wrapper."""
    import asyncio

    try:
        asyncio.get_running_loop()
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, verify_quality(project, result)).result(timeout=180)
    except RuntimeError:
        return asyncio.run(verify_quality(project, result))
