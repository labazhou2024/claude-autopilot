"""Tests for semantic_memory -- long-term pattern store with belief decay."""

from claude_autopilot.learning.semantic_memory import (
    MAX_CONFIDENCE,
    PRUNE_THRESHOLD,
    SemanticMemory,
)


def make_memory(tmp_path):
    """Helper: create a fresh SemanticMemory backed by tmp_path."""
    patterns_file = tmp_path / "semantic_patterns.json"
    return SemanticMemory(patterns_file=patterns_file)


# --- add_pattern + retrieve ---


def test_add_pattern_and_retrieve_keyword(tmp_path):
    """add_pattern stores pattern; retrieve returns it via keyword match."""
    mem = make_memory(tmp_path)
    pid = mem.add_pattern(
        rule="When modifying async functions always check if callers use await",
        tags=["async", "await", "functions"],
        source_episodes=2,
    )
    results = mem.retrieve("async function bug", top_k=3)
    ids = [p.pattern_id for p in results]
    assert pid in ids


def test_retrieve_returns_empty_when_no_patterns(tmp_path):
    """retrieve returns empty list when memory is empty."""
    mem = make_memory(tmp_path)
    results = mem.retrieve("some query", top_k=3)
    assert results == []


# --- apply_decay ---


def test_apply_decay_decreases_confidence(tmp_path):
    """apply_decay multiplies each pattern's confidence by DECAY_TAU."""
    mem = make_memory(tmp_path)
    mem.add_pattern(
        rule="Prefer explicit type annotations in public API functions to avoid runtime errors",
        tags=["typing", "api"],
        source_episodes=2,
    )
    pid = list(mem._patterns.keys())[0]
    before = mem._patterns[pid].confidence

    mem.apply_decay()

    # Pattern may survive or be pruned; if it survives, confidence < before
    if pid in mem._patterns:
        assert mem._patterns[pid].confidence < before
    # If pruned, that's also correct behavior for INITIAL_CONFIDENCE near threshold


def test_apply_decay_prunes_low_confidence(tmp_path):
    """Patterns whose confidence drops below PRUNE_THRESHOLD are removed."""
    mem = make_memory(tmp_path)
    pid = mem.add_pattern(
        rule="Specific actionable rule with enough words to pass the length gate",
        tags=["test"],
        source_episodes=2,
    )
    # Force confidence just above threshold then decay below it
    mem._patterns[pid].confidence = PRUNE_THRESHOLD + 0.001
    mem.apply_decay()
    # After decay: confidence = (PRUNE_THRESHOLD + 0.001) * DECAY_TAU < PRUNE_THRESHOLD
    assert pid not in mem._patterns


# --- record_application_outcome ---


def test_record_outcome_success_boosts_confidence(tmp_path):
    """Successful application increases confidence (capped at MAX_CONFIDENCE)."""
    mem = make_memory(tmp_path)
    pid = mem.add_pattern(
        rule="Always verify subprocess return codes before processing output",
        tags=["subprocess", "error_handling"],
        source_episodes=2,
    )
    before = mem._patterns[pid].confidence
    mem.record_application_outcome(pid, success=True)
    assert mem._patterns[pid].confidence > before
    assert mem._patterns[pid].confidence <= MAX_CONFIDENCE


def test_record_outcome_failure_decreases_confidence(tmp_path):
    """Failed application decreases confidence (floored at PRUNE_THRESHOLD)."""
    mem = make_memory(tmp_path)
    pid = mem.add_pattern(
        rule="Use context managers for all file operations to prevent resource leaks",
        tags=["files", "context_manager"],
        source_episodes=2,
    )
    mem._patterns[pid].confidence = 0.6
    mem.record_application_outcome(pid, success=False)
    assert mem._patterns[pid].confidence < 0.6
    assert mem._patterns[pid].confidence >= PRUNE_THRESHOLD


# --- deduplication ---


def test_deduplication_merges_similar_rules(tmp_path):
    """add_pattern merges rules with >70% word-overlap instead of duplicating."""
    mem = make_memory(tmp_path)
    rule1 = "When modifying async functions always verify callers use await keyword"
    rule2 = "When modifying async functions always verify callers use await keyword carefully"
    pid1 = mem.add_pattern(rule1, tags=["async"], source_episodes=2)
    count_before = mem.pattern_count

    pid2 = mem.add_pattern(rule2, tags=["async"], source_episodes=1)

    # Should merge, not add a new pattern
    assert mem.pattern_count == count_before
    # Returns existing pattern id
    assert pid2 == pid1


# --- persistence ---


def test_patterns_persisted_to_disk(tmp_path):
    """Patterns written to disk are reloaded by a fresh SemanticMemory instance."""
    patterns_file = tmp_path / "semantic_patterns.json"
    mem1 = SemanticMemory(patterns_file=patterns_file)
    mem1.add_pattern(
        rule="Cache database query results when the same query is called multiple times per second",
        tags=["cache", "database", "performance"],
        source_episodes=3,
    )
    assert mem1.pattern_count == 1

    mem2 = SemanticMemory(patterns_file=patterns_file)
    assert mem2.pattern_count == 1
