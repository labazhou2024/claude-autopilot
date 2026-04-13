# claude-autopilot

> **From Copilot to Autopilot** -- Autonomous multi-agent orchestration for Claude Code.

Every AI coding tool today follows the same paradigm: *human gives instructions, AI executes*. claude-autopilot flips this: **AI runs autonomously, human reviews asynchronously as CEO**.

## Key Features

- **CEO Async Approval** -- L1/L2/L3 decision framework. AI handles routine tasks automatically (L1), queues taste/strategy decisions for human review (L2), and blocks on high-risk irreversible actions (L3).
- **Quality Big Loop** -- 7-stage quality cycle (Q1-Q7): test baseline, flaky detection, full audit, batch fixes, regression gates, strategic review, and briefing.
- **Self-Triggering Evolution** -- Conditions that fire automatically: session counters, commit thresholds, test failures, error patterns, memory consolidation.
- **Semantic Memory** -- Pattern learning with confidence decay, usage boost, and automatic pruning. Patterns earn trust through successful application (Instinct Model).
- **Event Sourcing** -- Append-only JSONL event bus with automatic rotation for full audit trail.
- **Worker Pool** -- Async parallel task execution with status tracking and cancellation.
- **Static Analysis Gate** -- Zero-cost, zero-API-call code quality checks (syntax, security, imports, dead code, hardcoded paths).

## Quick Start

```bash
pip install claude-autopilot
```

### Use individual modules

```python
from claude_autopilot.core import event_bus, approval_queue, local_reviewer

# Log events
event_bus.configure(data_dir="./data")
event_bus.log_event("task_completed", agent="my-agent", details={"result": "success"})

# Submit decisions for CEO review
approval_queue.configure(data_dir="./data")
apr_id = approval_queue.submit_approval(
    level="L2", category="architecture",
    title="Migrate from JSON to SQLite",
    context="Current JSON store is 50MB and slow",
    proposal="Use SQLite with FTS5 for full-text search",
)

# Zero-cost code review
from claude_autopilot.core.local_reviewer import review_files
result = review_files(["src/my_module.py"])
print(result.summary)  # "PASSED: 0C 0H 0M 1L across 1 files"
```

### Use the full orchestration stack

```python
from claude_autopilot.orchestration.big_loop import BigLoop
from pathlib import Path

loop = BigLoop(project_root=Path("my_project"))
result = await loop.run()
# Q1: 142 passed, 3 failed
# Q1.5: 1 flaky test detected
# Q4: 0 regressions
# Q5-Q7: Agent specs generated for CTO dispatch
```

## Architecture

```
                    +-----------------------+
                    |    CEO (Human)        |
                    |  Async Review Queue   |
                    +----------+------------+
                               |
              L2 Suspend / L3 Block
                               |
+------------------------------v-------------------------------+
|                      CTO (Claude)                            |
|                                                              |
|  +------------------+  +------------------+  +-----------+   |
|  |  Auto-Trigger    |  |  Big Loop        |  |  Worker   |   |
|  |  (conditions)    |  |  (Q1-Q7 cycle)   |  |  Pool     |   |
|  +--------+---------+  +--------+---------+  +-----+-----+   |
|           |                      |                  |         |
|  +--------v---------+  +--------v---------+  +-----v-----+   |
|  |  Event Bus       |  |  Quality         |  |  LLM      |   |
|  |  (audit trail)   |  |  Verifier        |  |  Router    |   |
|  +------------------+  +------------------+  +-----------+   |
|                                                              |
|  +------------------+  +------------------+                  |
|  |  Semantic Memory |  |  Local Reviewer  |                  |
|  |  (pattern learn) |  |  (static gate)   |                  |
|  +------------------+  +------------------+                  |
+--------------------------------------------------------------+
```

## Agent Definitions

Drop-in Claude Code agent definitions in `agents/*.md`:

| Agent | Purpose | Ready to use? |
|-------|---------|:---:|
| code-reviewer | 3-stage code review (pre-screen + local + deep) | Yes |
| fix-agent | Review-fix-review loop until APPROVED | Yes |
| gate-keeper | Multi-gate checklist before commit | Yes |
| test-runner | Multi-stack test orchestration | Yes |
| sonnet-executor | Generic parallel task executor | Customize |
| chief-researcher | Industry research workflow | Customize |

## Comparison

| Feature | claude-autopilot | everything-claude-code | Raw Claude Code |
|---------|:---:|:---:|:---:|
| Autonomous operation | Yes | No | No |
| CEO async approval (L1/L2/L3) | Yes | No | No |
| Self-triggering conditions | Yes | No | No |
| Quality big loop (Q1-Q7) | Yes | No | No |
| Semantic memory / learning | Yes | No | No |
| Zero-cost static analysis | Yes | No | No |

## Reference Implementations

The `src/claude_autopilot/reference/` directory contains two complete autonomous systems for study:

- **evolution_orchestrator.py** -- Full 5-stage evolution loop: Observe, Reflect, Consolidate, Evolve, Measure
- **kairos_daemon.py** -- Autonomous execution daemon with parallel workers, self-healing, and pattern injection

These are provided as architectural references. They require significant customization and depend on modules not included in this package.

## Inspired By

- [TextGrad](https://arxiv.org/abs/2406.07496) (Nature) -- Gradient-based prompt optimization
- [DSPy](https://github.com/stanfordnlp/dspy) -- Declarative language model programming
- [EvoAgentX](https://github.com/EvoAgentX/EvoAgentX) -- Population-based agent evolution
- Anthropic Claude Code -- Harness architecture, hooks, agent definitions

## License

MIT
