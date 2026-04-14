# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [0.1.0] - 2026-04-14

### Added
- Core modules: event_bus, approval_queue, worker_pool, local_reviewer, atomic_io, validators, episodic_log
- Orchestration: big_loop (Q1-Q7), auto_trigger, quality_verifier, llm_router
- Learning: semantic_memory with confidence decay
- Reference: evolution_orchestrator, kairos_daemon
- 6 Claude Code agent definitions
- PII scanner with canary self-test
- GitHub Actions CI (lint + test + PII scan)
- Cross-platform support (Ubuntu + Windows, Python 3.9-3.12)
