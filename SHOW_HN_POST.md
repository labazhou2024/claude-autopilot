# Show HN Post (Final Draft)

## Title (67 chars):
Show HN: claude-autopilot -- autonomous agent orchestration for Claude Code

## Body:

I'm a physics student at USTC doing quantum computing research. Over the past few months I built a personal AI assistant to manage my research workflow, code reviews, and project ops. It grew to ~21K LOC and actually worked well enough that I started trusting it to run autonomously while I focused on physics. I extracted the generalizable core into a clean open-source toolkit: claude-autopilot.

The central problem: Claude Code is a great copilot, but scaling it to autopilot requires structure it doesn't provide -- how do you let an agent make routine decisions while blocking anything catastrophic?

The answer I landed on is a three-tier decision framework. L1 (auto): running tests, committing passing code, updating docs -- just do it. L2 (suspend): architecture changes, priority calls -- queue for review, keep working on other things. L3 (block): production deploys, deleting data -- hard stop until approved. You review asynchronously, like a CEO checking a decision queue, not a pair programmer.

In practice: my agent runs pytest, sees 2 failures, spawns a fix-agent, patches the code, re-runs tests, and commits -- all L1, no human needed. When it wants to refactor a module's API, that's L2: it queues the proposal and moves on to other work.

Quality comes from a dual-loop system. The inner loop (write, test, review, gate) runs per-commit. The outer loop (Q1-Q7) runs periodically: test baseline, flaky detection, full audit, batch fixes, regression gates, strategic review, briefing. There's a 7-signal weighted scoring function and a semantic memory layer where stored patterns decay in confidence by 5% per cycle, so stale context gets naturally forgotten.

Unlike agent frameworks that wrap LLM calls (LangGraph, CrewAI), this works inside Claude Code's native tool-use loop -- it's orchestration glue, not another abstraction layer. 14 Python modules, 6 of the 7 core modules are pure stdlib with zero dependencies. Designed to be picked apart: use one module or the full stack.

v0.1.0, opinionated patterns, assumes Claude Code's tool interface, no UI or cloud. It's a toolkit, not a platform -- grab what's useful and ignore the rest.

https://github.com/labazhou2024/claude-autopilot
