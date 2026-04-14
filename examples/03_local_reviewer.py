"""Example: Zero-cost static analysis with local_reviewer."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from claude_autopilot.core.local_reviewer import review_files

# Create sample files to review
with tempfile.TemporaryDirectory() as tmpdir:
    # Good file
    good = Path(tmpdir) / "good.py"
    good.write_text(
        'import json\nfrom pathlib import Path\n\n'
        'def load_config(path: Path) -> dict:\n'
        '    return json.loads(path.read_text(encoding="utf-8"))\n',
        encoding="utf-8",
    )

    # File with security issues
    bad = Path(tmpdir) / "risky.py"
    bad.write_text(
        'import os\n\n'
        'def run_command(cmd):\n'
        '    os.system(cmd)  # Security: should use subprocess\n'
        '    return eval(input("Enter expression: "))\n',
        encoding="utf-8",
    )

    result = review_files([str(good), str(bad)])
    print(f"Review: {result.summary}")
    print(f"Passed: {result.passed}")
    print(f"Blocking issues: {len(result.blocking)}")
    print()
    for finding in result.findings:
        print(f"  {finding}")
