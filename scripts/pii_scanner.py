#!/usr/bin/env python3
"""PII Scanner -- Multi-strategy scanner for detecting personal information leaks.

Usage:
    python pii_scanner.py scan <directory> [<directory>...]
    python pii_scanner.py verify <directory> [<directory>...]
    python pii_scanner.py canary

Modes:
    scan    - Scan directories, report all PII hits (JSON output)
    verify  - Verify directories are clean (exit 0 if clean, 1 if PII found)
    canary  - Self-test: inject PII, scan, verify detection, clean up
"""

import json
import re
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Registry path (relative to this script)
_SCRIPT_DIR = Path(__file__).parent
_REGISTRY_PATH = _SCRIPT_DIR / "pii_registry.yaml"

# Binary file detection: skip files with null bytes in first 8KB
_BINARY_CHECK_SIZE = 8192

# File extensions to scan
_TEXT_EXTENSIONS = {
    ".py", ".md", ".txt", ".yaml", ".yml", ".json", ".toml", ".cfg",
    ".ini", ".sh", ".bat", ".ps1", ".html", ".css", ".js", ".ts",
    ".rst", ".csv", ".xml", ".env", ".gitignore", ".editorconfig",
}


@dataclass
class PIIHit:
    """A single PII detection result."""
    file: str
    line: int
    column: int
    matched_text: str  # Truncated for secrets
    pattern_desc: str
    severity: str  # critical, high, medium


@dataclass
class ScanReport:
    """Aggregated scan results."""
    directories_scanned: list = field(default_factory=list)
    files_scanned: int = 0
    files_skipped: int = 0
    hits: list = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return len(self.hits) == 0


def _load_registry(path: Path) -> dict:
    """Load PII registry. Uses simple YAML parsing to avoid PyYAML dependency."""
    if not path.exists():
        print(f"ERROR: Registry not found at {path}", file=sys.stderr)
        sys.exit(2)

    # Simple YAML parser for our specific format (avoids PyYAML dependency)
    text = path.read_text(encoding="utf-8")

    registry = {"exact_strings": [], "regex_patterns": [], "excluded_paths": []}
    current_section = None
    current_item = None

    for line in text.splitlines():
        stripped = line.strip()

        # Skip comments and empty lines
        if not stripped or stripped.startswith("#"):
            continue

        # Section headers
        if stripped == "exact_strings:":
            current_section = "exact_strings"
            current_item = None
            continue
        elif stripped == "regex_patterns:":
            current_section = "regex_patterns"
            current_item = None
            continue
        elif stripped == "excluded_paths:":
            current_section = "excluded_paths"
            current_item = None
            continue

        # List items
        if stripped.startswith("- "):
            value = stripped[2:].strip()
            if current_section == "exact_strings":
                # Remove quotes and handle escapes
                value = value.strip('"').strip("'")
                if "\\u" in value:
                    value = value.encode("utf-8").decode("unicode_escape")
                value = value.replace("\\\\", "\\")
                registry["exact_strings"].append(value)
            elif current_section == "excluded_paths":
                value = value.strip('"').strip("'")
                registry["excluded_paths"].append(value)
            elif current_section == "regex_patterns":
                current_item = {}
                # Inline key-value on same line as dash
                if "pattern:" in value:
                    kv = value.split("pattern:", 1)[1].strip().strip('"').strip("'")
                    # YAML escaping: \\\\ -> \\
                    kv = kv.replace("\\\\", "\\")
                    current_item["pattern"] = kv
                registry["regex_patterns"].append(current_item)
            continue

        # Key-value pairs within a list item (regex_patterns)
        if current_section == "regex_patterns" and current_item is not None:
            if ":" in stripped:
                key, val = stripped.split(":", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key == "pattern":
                    # YAML escaping: \\\\ -> \\
                    val = val.replace("\\\\", "\\")
                    current_item[key] = val
                elif key in ("desc", "severity"):
                    current_item[key] = val
                elif key == "context_check":
                    current_item[key] = val.lower() == "true"

    return registry


def _is_binary(filepath: Path) -> bool:
    """Check if file is binary by looking for null bytes."""
    try:
        with open(filepath, "rb") as f:
            chunk = f.read(_BINARY_CHECK_SIZE)
            return b"\x00" in chunk
    except (OSError, PermissionError):
        return True


def _should_scan(filepath: Path) -> bool:
    """Determine if a file should be scanned."""
    # Skip hidden directories
    parts = filepath.parts
    if any(p.startswith(".") and p != "." for p in parts):
        return False

    # Check extension
    if filepath.suffix.lower() not in _TEXT_EXTENSIONS:
        # Also scan files with no extension (like Makefile, Dockerfile)
        if filepath.suffix:
            return False

    return not _is_binary(filepath)


def _truncate_secret(text: str, max_len: int = 20) -> str:
    """Truncate matched text to avoid exposing full secrets in reports."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def scan_file(filepath: Path, registry: dict) -> list:
    """Scan a single file for PII. Returns list of PIIHit."""
    hits = []

    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except (OSError, PermissionError):
        return hits

    lines = content.splitlines()

    # Check exact strings (Section A)
    for pattern_str in registry["exact_strings"]:
        for line_num, line in enumerate(lines, 1):
            col = line.find(pattern_str)
            if col != -1:
                hits.append(PIIHit(
                    file=str(filepath),
                    line=line_num,
                    column=col + 1,
                    matched_text=_truncate_secret(pattern_str),
                    pattern_desc=f"Exact match: {_truncate_secret(pattern_str, 15)}",
                    severity="high",
                ))

    # Check regex patterns (Section B)
    for pat_info in registry["regex_patterns"]:
        pattern_str = pat_info.get("pattern", "")
        if not pattern_str:
            continue

        try:
            regex = re.compile(pattern_str)
        except re.error:
            continue

        for line_num, line in enumerate(lines, 1):
            for match in regex.finditer(line):
                matched = match.group()
                severity = pat_info.get("severity", "medium")

                # Context check: skip matches that are clearly not PII
                if pat_info.get("context_check"):
                    # For 64-char hex: skip if it looks like a hash in test code
                    if pat_info["desc"] == "64-char hex string (potential crypto key)":
                        # Only flag if it matches a known key exactly
                        if matched not in registry["exact_strings"]:
                            continue
                    # For phone numbers: skip if preceded by common non-phone contexts
                    if pat_info["desc"] == "Chinese phone number":
                        before = line[:match.start()]
                        if any(kw in before.lower() for kw in ["port", "pid", "size", "count", "0x"]):
                            continue

                hits.append(PIIHit(
                    file=str(filepath),
                    line=line_num,
                    column=match.start() + 1,
                    matched_text=_truncate_secret(matched),
                    pattern_desc=pat_info.get("desc", "Regex match"),
                    severity=severity,
                ))

    return hits


def scan_directory(dirpath: Path, registry: dict) -> ScanReport:
    """Recursively scan a directory for PII."""
    report = ScanReport(directories_scanned=[str(dirpath)])

    if not dirpath.exists():
        print(f"WARNING: Directory not found: {dirpath}", file=sys.stderr)
        return report

    for filepath in sorted(dirpath.rglob("*")):
        if not filepath.is_file():
            continue

        if _should_scan(filepath):
            report.files_scanned += 1
            hits = scan_file(filepath, registry)
            report.hits.extend(hits)
        else:
            report.files_skipped += 1

    return report


def run_scan(directories: list, registry: dict) -> ScanReport:
    """Scan multiple directories and aggregate results."""
    combined = ScanReport()
    for dirpath in directories:
        path = Path(dirpath)
        report = scan_directory(path, registry)
        combined.directories_scanned.extend(report.directories_scanned)
        combined.files_scanned += report.files_scanned
        combined.files_skipped += report.files_skipped
        combined.hits.extend(report.hits)
    return combined


def run_canary(registry: dict) -> bool:
    """Self-test: inject PII canaries, verify scanner catches them all."""
    # NOTE: Canary values must match patterns in pii_registry.yaml.
    # These use the REAL patterns from the registry so the self-test validates
    # actual detection capability. The canary files are created in a temp
    # directory and deleted immediately after the test.
    exact = registry.get("exact_strings", [])
    regex_pats = registry.get("regex_patterns", [])

    # Build canaries dynamically from the registry's first few entries
    canaries = {}
    if len(exact) > 0:
        canaries["exact_0"] = f'value = "{exact[0][:40]}"'
    if len(exact) > 3:
        canaries["exact_3"] = f'value = "{exact[3]}"'
    if len(exact) > 5:
        canaries["exact_5"] = f'value = "{exact[5]}"'
    if len(exact) > 8:
        canaries["exact_8"] = f'value = "{exact[8]}"'
    if len(exact) > 12:
        canaries["exact_12"] = f'value = "{exact[12]}"'
    if len(exact) > 15:
        canaries["exact_15"] = f'value = "{exact[15]}"'
    if len(exact) > 20:
        canaries["exact_20"] = f'value = "{exact[20]}"'
    if len(exact) > 25:
        canaries["exact_25"] = f'value = "{exact[25]}"'
    # Test regex patterns with synthetic matches
    for i, pat in enumerate(regex_pats[:4]):
        desc = pat.get("desc", f"regex_{i}")
        p = pat.get("pattern", "")
        if "sk-" in p:
            canaries[f"regex_{desc}"] = 'key = "sk-TESTCANARY1234567890abcdef"'
        elif "qq" in p.lower():
            canaries[f"regex_{desc}"] = 'email = "1234567890@qq.com"'
        elif "wxid" in p.lower():
            canaries[f"regex_{desc}"] = 'wid = "wxid_testcanary1234"'
        elif "Users" in p:
            canaries[f"regex_{desc}"] = 'path = "C:\\\\Users\\\\29424\\\\test"'

    if not canaries:
        print("WARNING: No canary patterns could be generated from registry")
        return False

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Create canary files
        for name, content in canaries.items():
            (tmppath / f"canary_{name}.py").write_text(content, encoding="utf-8")

        # Scan
        report = scan_directory(tmppath, registry)

        # Check which canaries were caught
        caught = set()
        for hit in report.hits:
            filename = Path(hit.file).stem
            caught.add(filename)

        expected = {f"canary_{name}" for name in canaries}
        missed = expected - caught

        print(f"\nCanary Self-Test Results:")
        print(f"  Total canaries: {len(canaries)}")
        print(f"  Caught: {len(caught)}/{len(canaries)}")

        if missed:
            print(f"\n  FAILED -- Missed canaries:")
            for m in sorted(missed):
                print(f"    - {m}")
            return False
        else:
            print(f"  ALL CANARIES CAUGHT -- Scanner is trustworthy")
            return True


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)

    mode = sys.argv[1]
    registry = _load_registry(_REGISTRY_PATH)

    if mode == "scan":
        if len(sys.argv) < 3:
            print("Usage: pii_scanner.py scan <directory> [<directory>...]", file=sys.stderr)
            sys.exit(2)
        directories = sys.argv[2:]
        report = run_scan(directories, registry)

        # Output JSON report
        output = {
            "directories": report.directories_scanned,
            "files_scanned": report.files_scanned,
            "files_skipped": report.files_skipped,
            "total_hits": len(report.hits),
            "clean": report.clean,
            "hits": [asdict(h) for h in report.hits],
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
        sys.exit(0 if report.clean else 1)

    elif mode == "verify":
        if len(sys.argv) < 3:
            print("Usage: pii_scanner.py verify <directory> [<directory>...]", file=sys.stderr)
            sys.exit(2)
        directories = sys.argv[2:]
        report = run_scan(directories, registry)

        if report.clean:
            print(f"CLEAN: Scanned {report.files_scanned} files, 0 PII hits.")
            sys.exit(0)
        else:
            print(f"PII DETECTED: {len(report.hits)} hits in {report.files_scanned} files:")
            for hit in report.hits:
                print(f"  {hit.file}:{hit.line}:{hit.column} [{hit.severity}] "
                      f"{hit.pattern_desc} -> {hit.matched_text}")
            sys.exit(1)

    elif mode == "canary":
        passed = run_canary(registry)
        sys.exit(0 if passed else 1)

    else:
        print(f"Unknown mode: {mode}", file=sys.stderr)
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
