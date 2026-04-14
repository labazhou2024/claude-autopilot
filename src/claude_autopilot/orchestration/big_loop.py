"""
Big Loop Orchestrator — Q1->Q6 quality cycle.

Automatable stages (pure Python):
  Q1: Run pytest + record baseline
  Q1.5: Flaky test detection (re-run failures 3x)
  Q4: Regression comparison vs Q1 baseline

Agent-delegated stages (return specs for CTO to invoke):
  Q2: QA Director deep review (returns prompt spec for qa-director Agent)
  Q3: Bug batch fixes (returns fix specs for sonnet-executor Agents)
  Q5: Release gate (returns spec for release-gate Agent)
  Q6: Strategic advisor (returns spec for strategic-advisor Agent)

Usage:
    loop = BigLoop(project_root=Path("my_project"))
    result = await loop.run()
"""

import json
import logging
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Module-level data dir state (overridable via configure())
_data_dir_override: Optional[Path] = None


def _get_data_dir() -> Path:
    """Return configured data dir, defaulting to cwd/data."""
    if _data_dir_override is not None:
        return _data_dir_override
    return Path.cwd() / "data"


def configure(data_dir: Path = None) -> None:
    """Configure module-level defaults.

    Args:
        data_dir: Override the default data directory (default: cwd/data).
    """
    global _data_dir_override
    if data_dir is not None:
        _data_dir_override = Path(data_dir)


@dataclass
class BigLoopResult:
    loop_id: str
    timestamp: str
    duration_seconds: float
    stages: Dict[str, Any] = field(default_factory=dict)
    bugs_found: int = 0
    bugs_fixed: int = 0
    regressions: int = 0
    success: bool = True
    agent_specs: List[Dict] = field(default_factory=list)  # Specs for CTO to invoke
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class BigLoop:
    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()
        self._data_dir = _get_data_dir()
        self._baseline_file = self._data_dir / "test_baseline_q1.json"

    # === Q1: Automated Testing + Baseline ===
    async def q1_test_baseline(self) -> Dict[str, Any]:
        """Run all tests and record baseline."""
        results = self._run_pytest_detailed()

        # Save baseline
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._baseline_file.write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        try:
            from .event_bus import log_event

            log_event(
                "big_loop_q1",
                agent="big_loop",
                details={
                    "passed": results["passed_count"],
                    "failed": results["failed_count"],
                    "total": results["total"],
                },
            )
        except ImportError:
            pass

        return results

    # === Q1.5: Flaky Test Detection ===
    async def q1_5_flaky_detection(self, q1_result: Dict) -> Dict[str, Any]:
        """Re-run failed tests 3x to detect flaky tests."""
        failed_tests = q1_result.get("failed_tests", [])
        if not failed_tests:
            return {"flaky": [], "real_failures": [], "skipped": True}

        flaky = []
        real_failures = []

        for test_name in failed_tests:
            pass_count = 0
            for _ in range(3):
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        test_name,
                        "-x",
                        "-q",
                        "--tb=no",
                        "--no-header",
                    ],
                    capture_output=True,
                    text=True,
                    cwd=str(self.project_root),
                    timeout=60,
                )
                if result.returncode == 0:
                    pass_count += 1

            if 0 < pass_count < 3:
                flaky.append({"test": test_name, "pass_rate": pass_count / 3})
            elif pass_count == 0:
                real_failures.append(test_name)
            # pass_count == 3 means Q1 was a one-off failure, treat as flaky
            else:
                flaky.append({"test": test_name, "pass_rate": 1.0})

        return {"flaky": flaky, "real_failures": real_failures, "skipped": False}

    # === Q2: QA Director Deep Review (Agent spec) ===
    async def q2_qa_review_spec(self) -> Dict[str, Any]:
        """Generate spec for qa-director Agent. CTO invokes the Agent."""
        # Collect all source files for the Agent to review
        src_files = [
            str(p.relative_to(self.project_root))
            for p in self.project_root.rglob("*.py")
            if "__pycache__" not in str(p) and ".git" not in str(p) and "archive" not in str(p)
        ]

        spec = {
            "agent": "qa-director",
            "model": "opus",
            "prompt": f"Full code review of {len(src_files)} Python files in project. "
            f"Output numbered Bug JSON with severity + fix suggestions.",
            "files_to_review": src_files[:50],  # Cap for context
            "output_format": "json_bug_list",
        }
        return {"spec": spec, "file_count": len(src_files)}

    # === Q3: Bug Batch Fix (Agent specs) ===
    async def q3_fix_specs(self, bugs: List[Dict]) -> Dict[str, Any]:
        """Generate fix specs for sonnet-executor Agents. CTO invokes them."""
        if not bugs:
            return {"specs": [], "skipped": True}

        # Group bugs by file
        by_file: Dict[str, List[Dict]] = {}
        for bug in bugs:
            f = bug.get("file", "unknown")
            if f not in by_file:
                by_file[f] = []
            by_file[f].append(bug)

        specs = []
        for file_path, file_bugs in by_file.items():
            specs.append(
                {
                    "agent": "sonnet-executor",
                    "model": "sonnet",
                    "target_files": [file_path],
                    "bugs": file_bugs,
                    "prompt": f"Fix {len(file_bugs)} bugs in {file_path}: "
                    + "; ".join(b.get("description", "")[:60] for b in file_bugs),
                }
            )

        return {"specs": specs, "total_bugs": len(bugs), "batches": len(specs)}

    # === Q4: Regression Verification ===
    async def q4_regression_check(self) -> Dict[str, Any]:
        """Re-run tests and compare against Q1 baseline."""
        current = self._run_pytest_detailed()

        # Load baseline
        if not self._baseline_file.exists():
            return {"error": "No Q1 baseline found", "regressions": []}

        baseline = json.loads(self._baseline_file.read_text(encoding="utf-8"))

        regressions = []
        new_passes = []

        baseline_tests = {t: "passed" for t in baseline.get("passed_tests", [])}
        baseline_tests.update({t: "failed" for t in baseline.get("failed_tests", [])})

        current_tests = {t: "passed" for t in current.get("passed_tests", [])}
        current_tests.update({t: "failed" for t in current.get("failed_tests", [])})

        for test, q1_status in baseline_tests.items():
            q4_status = current_tests.get(test, "missing")
            if q1_status == "passed" and q4_status == "failed":
                regressions.append(test)
            elif q1_status == "failed" and q4_status == "passed":
                new_passes.append(test)

        return {
            "regressions": regressions,
            "new_passes": new_passes,
            "q1_total": baseline.get("total", 0),
            "q4_total": current.get("total", 0),
            "passed": len(regressions) == 0,
        }

    # === Q5: Release Gate (Agent spec) ===
    async def q5_release_gate_spec(self) -> Dict[str, Any]:
        """Generate spec for release-gate Agent."""
        return {
            "spec": {
                "agent": "release-gate",
                "model": "sonnet",
                "prompt": (
                    "Full release gate: build verification + test + harness_state sync + CHANGELOG"
                ),
            }
        }

    # === Q6: Strategic Advisor (Agent spec) ===
    async def q6_strategic_advisor_spec(self) -> Dict[str, Any]:
        """Generate spec for strategic-advisor Agent."""
        return {
            "spec": {
                "agent": "strategic-advisor",
                "model": "opus",
                "prompt": "Read global state (harness_state + memory + events). "
                "Identify improvement opportunities across 5 dimensions. "
                "Output ROI-sorted recommendations.",
            }
        }

    # === Full Loop ===
    async def run(self, bugs: List[Dict] = None) -> BigLoopResult:
        """Execute full big loop Q1->Q6."""
        loop_id = f"bigloop_{int(time.time())}"
        start = time.time()
        stages: Dict[str, Any] = {}
        agent_specs: List[Dict] = []

        try:
            from .event_bus import log_event

            log_event("big_loop_start", agent="big_loop", details={"loop_id": loop_id})
        except ImportError:
            pass

        try:
            # Q1: Test baseline
            logger.info("Q1: Running test baseline...")
            stages["q1"] = await self.q1_test_baseline()
            logger.info(
                "Q1: %d passed, %d failed",
                stages["q1"]["passed_count"],
                stages["q1"]["failed_count"],
            )

            # Q1.5: Flaky detection
            logger.info("Q1.5: Detecting flaky tests...")
            stages["q1_5"] = await self.q1_5_flaky_detection(stages["q1"])
            if stages["q1_5"].get("flaky"):
                logger.warning("Q1.5: %d flaky tests detected", len(stages["q1_5"]["flaky"]))

            # Q2: QA review spec (for CTO to invoke)
            logger.info("Q2: Generating QA review spec...")
            stages["q2"] = await self.q2_qa_review_spec()
            agent_specs.append(stages["q2"]["spec"])

            # Q3: Fix specs (for CTO to invoke)
            if bugs:
                logger.info("Q3: Generating fix specs for %d bugs...", len(bugs))
                stages["q3"] = await self.q3_fix_specs(bugs)
                agent_specs.extend(stages["q3"].get("specs", []))
            else:
                stages["q3"] = {"skipped": True, "reason": "no bugs provided"}

            # Q4: Regression check
            logger.info("Q4: Running regression check...")
            stages["q4"] = await self.q4_regression_check()
            regressions = len(stages["q4"].get("regressions", []))
            if regressions > 0:
                logger.error("Q4: %d REGRESSIONS detected!", regressions)

            # Only proceed to Q5/Q6/Q7 if Q4 passed (no regressions)
            if regressions > 0:
                logger.error(
                    "Q4 FAILED: %d regressions. Blocking Q5-Q7.",
                    regressions,
                )
                stages["q5"] = {"skipped": True, "reason": f"Q4 found {regressions} regressions"}
                stages["q6"] = {"skipped": True, "reason": "blocked by Q4 failure"}
                # Do NOT append agent_specs — release is blocked
            else:
                # Q5: Release gate spec
                logger.info("Q5: Generating release gate spec...")
                stages["q5"] = await self.q5_release_gate_spec()
                agent_specs.append(stages["q5"]["spec"])

                # Q6: Strategic advisor spec
                logger.info("Q6: Generating strategic advisor spec...")
                stages["q6"] = await self.q6_strategic_advisor_spec()
                agent_specs.append(stages["q6"]["spec"])

            # Q7: Briefing agent spec (always generated — reports success or failure)
            logger.info("Q7: Generating briefing spec...")
            q1 = stages["q1"]
            flaky_n = len(stages.get("q1_5", {}).get("flaky", []))
            q7_prompt = (
                f"Generate big loop report. Loop: {loop_id}. "
                f"Q1: {q1.get('passed_count', 0)} passed, "
                f"{q1.get('failed_count', 0)} failed. "
                f"Q1.5: {flaky_n} flaky. "
                f"Q4: {regressions} regressions. "
            )
            if regressions > 0:
                q7_prompt += "CRITICAL: Q4 regressions detected. Q5/Q6 BLOCKED. Fix before release."
            q7_prompt += "Read all data sources and output structured CEO report."
            q7_spec = {
                "agent": "briefing-agent",
                "model": "sonnet",
                "prompt": q7_prompt,
            }
            stages["q7_briefing"] = {"spec": q7_spec}
            agent_specs.append(stages["q7_briefing"]["spec"])

            duration = time.time() - start
            result = BigLoopResult(
                loop_id=loop_id,
                timestamp=datetime.utcnow().isoformat() + "Z",
                duration_seconds=round(duration, 2),
                stages=stages,
                bugs_found=len(bugs) if bugs else 0,
                regressions=regressions,
                success=regressions == 0,
                agent_specs=agent_specs,
            )

        except Exception as e:
            logger.error("Big loop failed: %s", e)
            result = BigLoopResult(
                loop_id=loop_id,
                timestamp=datetime.utcnow().isoformat() + "Z",
                duration_seconds=round(time.time() - start, 2),
                stages=stages,
                success=False,
                error=str(e),
            )

        # Save result
        self._save_result(result)

        # Persist agent specs for CTO to pick up at next SessionStart
        if agent_specs:
            specs_file = self._data_dir / "pending_agent_specs.json"
            try:
                existing = []
                if specs_file.exists():
                    existing = json.loads(specs_file.read_text(encoding="utf-8"))
                existing.extend(agent_specs)
                specs_file.write_text(
                    json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                logger.info("Queued %d agent specs for CTO: %s", len(agent_specs), specs_file)
            except Exception as e:
                logger.warning("Failed to save agent specs: %s", e)

        try:
            from .event_bus import log_event

            log_event(
                "big_loop_end",
                agent="big_loop",
                details={
                    "loop_id": loop_id,
                    "success": result.success,
                    "bugs_found": result.bugs_found,
                    "regressions": result.regressions,
                    "agent_specs_queued": len(agent_specs),
                    "duration_min": round(result.duration_seconds / 60, 1),
                },
            )
        except ImportError:
            pass

        return result

    def _run_pytest_detailed(self) -> Dict:
        """Run pytest with detailed per-test results."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=no", "--no-header"],
                capture_output=True,
                text=True,
                cwd=str(self.project_root),
                timeout=180,
            )
            output = result.stdout

            passed_tests = []
            failed_tests = []
            for line in output.splitlines():
                if " PASSED" in line:
                    test_name = line.split(" PASSED")[0].strip()
                    passed_tests.append(test_name)
                elif " FAILED" in line:
                    test_name = line.split(" FAILED")[0].strip()
                    failed_tests.append(test_name)

            return {
                "passed_count": len(passed_tests),
                "failed_count": len(failed_tests),
                "total": len(passed_tests) + len(failed_tests),
                "passed_tests": passed_tests,
                "failed_tests": failed_tests,
                "success": len(failed_tests) == 0,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
        except Exception as e:
            return {
                "passed_count": 0,
                "failed_count": 0,
                "total": 0,
                "passed_tests": [],
                "failed_tests": [],
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }

    def _save_result(self, result: BigLoopResult):
        """Save big loop result."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        result_file = self._data_dir / f"big_loop_{result.loop_id}.json"
        result_file.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info("Big loop result saved: %s", result_file)


# Convenience function
async def run_big_loop(project_root: Path = None, bugs: List[Dict] = None) -> Dict[str, Any]:
    """Run one big loop cycle and return result dict."""
    if project_root is None:
        project_root = Path.cwd()
    loop = BigLoop(project_root=project_root)
    result = await loop.run(bugs=bugs)
    return result.to_dict()


def run_big_loop_sync(project_root: Path = None, bugs: List[Dict] = None) -> Dict[str, Any]:
    """Synchronous wrapper for run_big_loop."""
    import asyncio

    return asyncio.run(run_big_loop(project_root=project_root, bugs=bugs))
