"""Security & integrity: run the attack tests and record each one's outcome.

The attacks themselves (bit flips, header tampering, wrong key, cropping,
keyless extraction, password-guess cost, ...) live in tests/test_security.py and
tests/test_crypto.py; tests/security_results.md maps each test to its threat.
This script runs them and writes one row per test to experiments/results/security.csv.

Usage:
    python -m experiments.security
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ElementTree
from pathlib import Path

import pandas as pd

from experiments.common import write_results

SECURITY_TEST_FILES = ("tests/test_security.py", "tests/test_crypto.py")


def main() -> None:
    """Command-line entry point."""
    results = run_security_tests()
    summary = results.groupby(["file", "outcome"]).size().rename("n_tests").reset_index()
    print(summary.to_string(index=False))
    print(f"[+] {write_results(results, 'security')}")
    if (results["outcome"] != "passed").any():
        raise SystemExit("[!] Some security tests did not pass; see experiments/results/security.csv")


def run_security_tests(test_files: tuple[str, ...] = SECURITY_TEST_FILES) -> pd.DataFrame:
    """Run the security tests with pytest and return one row per test with its outcome."""
    with tempfile.TemporaryDirectory() as scratch:
        report = Path(scratch) / "security.xml"
        command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={report}", *test_files]
        subprocess.run(command, check=False, capture_output=True)  # failures are recorded, not raised
        return parse_junit_report(report)


def parse_junit_report(report: Path) -> pd.DataFrame:
    """One row per test case in a pytest JUnit XML report (a file this script just wrote)."""
    rows = [
        {
            "file": case.get("classname", "").replace(".", "/") + ".py",
            "test": case.get("name"),
            "outcome": _outcome(case),
            "seconds": float(case.get("time", 0.0)),
        }
        for case in ElementTree.parse(report).getroot().iter("testcase")
    ]
    return pd.DataFrame(rows)


def _outcome(case: ElementTree.Element) -> str:
    for tag in ("failure", "error", "skipped"):
        if case.find(tag) is not None:
            return {"failure": "failed", "error": "error", "skipped": "skipped"}[tag]
    return "passed"


if __name__ == "__main__":
    main()
