# Getting Started

## Installation

```bash
pip install claude-autopilot
```

Or install from source:

```bash
git clone https://github.com/labazhou2024/claude-autopilot.git
cd claude-autopilot
pip install -e ".[all,dev]"
```

## Core Concepts

### The Autopilot Model

claude-autopilot implements a three-tier autonomous decision framework:

| Level | Name | Behavior | Example |
|-------|------|----------|---------|
| L1 | Auto | Execute immediately, log result | Run tests, commit passing code |
| L2 | Suspend | Queue for review, continue other work | Architecture decisions, priority changes |
| L3 | Block | Queue for review, pause related tasks | Production deploys, data deletion |

### Module Architecture

```
claude_autopilot/
  core/           # Zero-dependency standalone modules
    event_bus     # Append-only JSONL event logging
    approval_queue # L1/L2/L3 async approval system
    worker_pool   # Parallel async task execution
    local_reviewer # Static analysis code gate
    atomic_io     # Crash-safe file writes
    validators    # Input validation utilities
    episodic_log  # SQLite-backed event sourcing
  orchestration/  # Workflow automation (needs configuration)
    big_loop      # Q1-Q7 quality cycle
    auto_trigger  # Self-triggering condition detection
    quality_verifier # 7-signal weighted scoring
    llm_router    # Claude CLI subprocess wrapper
  learning/       # Pattern recognition
    semantic_memory # Confidence-decay pattern store
  reference/      # Study-only implementations
    evolution_orchestrator # Full 5-stage evolution loop
    kairos_daemon # Autonomous execution daemon
```

## Quick Examples

### Event Logging

```python
from claude_autopilot.core import event_bus

event_bus.configure("./data")
event_bus.log_event("deploy", agent="ci", details={"env": "staging"})
```

### CEO Approval Queue

```python
from claude_autopilot.core import approval_queue

approval_queue.configure("./data")
apr_id = approval_queue.submit_approval(
    level="L2", category="architecture",
    title="Switch to SQLite",
    context="JSON is slow", proposal="Use SQLite FTS5",
)
# Later: approval_queue.approve(apr_id, "Go ahead")
```

### Code Review Gate

```python
from claude_autopilot.core.local_reviewer import review_files

result = review_files(["src/my_module.py"])
if not result.passed:
    print(f"Blocked: {len(result.blocking)} issues")
```

See `examples/` for complete runnable scripts.
