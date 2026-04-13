# Contributing to claude-autopilot

Thank you for your interest in contributing!

## Development Setup

```bash
git clone https://github.com/labazhou2024/claude-autopilot.git
cd claude-autopilot
pip install -e ".[all,dev]"
pytest tests/ -v
```

## Code Quality

Before submitting a PR:

```bash
ruff check src/ tests/
ruff format src/ tests/
pytest tests/ -v
python scripts/pii_scanner.py verify src/ agents/ docs/ tests/ examples/
```

## PII Safety

This project has a zero-tolerance policy for personal data. The CI pipeline includes:

1. **PII Pattern Scanner** -- Checks for known sensitive patterns
2. **Canary Self-Test** -- Verifies the scanner itself works correctly
3. **Chinese Text Check** -- Ensures no untranslated strings in production code

If the PII scan fails, your PR cannot be merged.

## Pull Request Process

1. Fork and create a feature branch
2. Write tests for new functionality
3. Ensure all checks pass (lint, test, PII scan)
4. Submit PR with a clear description

## Code Style

- Python 3.9+ compatible
- Follows ruff defaults (line length 100)
- Type hints where they add clarity
- Docstrings for public APIs

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
