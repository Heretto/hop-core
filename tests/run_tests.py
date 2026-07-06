#!/usr/bin/env python3
"""
Main test runner for hop-core.
Runs every test suite with per-suite output and prints a summary.

hop-core is a library, so unlike an app-level runner there are no services to
health-check or test data to clean up — every suite is plain pytest against
the local checkout.
"""

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path


class TestRunner:
    def __init__(self):
        self.tests_dir = Path(__file__).parent
        self.repo_root = self.tests_dir.parent
        self.test_results = {}

    # ------------------------------------------------------------------
    # Environment checks
    # ------------------------------------------------------------------

    def check_environment(self) -> bool:
        """Check that the local environment can run the suite."""
        print("\nChecking environment...")

        if sys.version_info < (3, 11):
            print(f"✗ Python 3.11+ required (running {sys.version.split()[0]})")
            return False
        print(f"✓ Python {sys.version.split()[0]}")

        # hop_core must resolve to this repo (editable install)
        spec = importlib.util.find_spec("hop_core")
        if spec is None or not (spec.origin or "").startswith(str(self.repo_root / "src")):
            origin = spec.origin if spec else "not installed"
            print(f"✗ hop_core does not resolve to this repo ({origin})")
            print(f"  Install it editable first:  pip install -e '{self.repo_root}[dev]'")
            return False
        print("✓ hop_core installed from this repo")

        if importlib.util.find_spec("lxml") is None:
            print("✗ lxml not installed (needed by the DITA suites)")
            print(f"  Install dev dependencies:  pip install -e '{self.repo_root}[dev]'")
            return False
        print("✓ lxml available")

        if importlib.util.find_spec("pytest") is None:
            print("✗ pytest not installed")
            print(f"  Install dev dependencies:  pip install -e '{self.repo_root}[dev]'")
            return False
        print("✓ pytest available")

        # xmllint is optional — DITA DTD tests skip without it.
        if shutil.which("xmllint"):
            print("✓ xmllint available (full DTD validation exercised)")
        else:
            print("⚠️  xmllint not found — DITA DTD tests will be skipped")
            print("   (apt-get install libxml2-utils  /  brew install libxml2)")

        return True

    # ------------------------------------------------------------------
    # Suite execution
    # ------------------------------------------------------------------

    def run_pytest(self, test_path: str, description: str) -> bool:
        """Run one pytest suite and return success status."""
        print(f"\n{'='*60}")
        print(f"Running: {description} (pytest)")
        print(f"Path: {test_path}")
        print('='*60)

        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", test_path, "-v", "--tb=short"],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(self.repo_root),
            )

            if result.stdout:
                print(result.stdout)
            if result.stderr and result.stderr.strip():
                print("STDERR:", result.stderr)

            success = result.returncode == 0
            self.test_results[description] = "✓ PASSED" if success else "✗ FAILED"
            return success

        except subprocess.TimeoutExpired:
            print("✗ Test timed out after 300 seconds")
            self.test_results[description] = "✗ TIMEOUT"
            return False
        except Exception as e:
            print(f"✗ Error running test: {e}")
            self.test_results[description] = "✗ ERROR"
            return False

    def run_all_tests(self):
        """Run all suites in order and print a summary. Returns exit code."""
        print("\n" + "="*60)
        print("HOP-CORE - TEST SUITE")
        print("="*60)

        if not self.check_environment():
            print("\n⚠️  Environment check failed — see instructions above.")
            return 1

        # Each entry is (path relative to the repo root, description).
        pytest_suites = [
            # Platform (app-level, in-process FastAPI via TestClient)
            ("tests/test_auth.py",          "Authentication & Password Reset"),
            ("tests/test_account.py",       "Account Management"),
            ("tests/test_organizations.py", "Organizations & Members"),
            ("tests/test_invitations.py",   "Invitations"),
            ("tests/test_credentials.py",   "Credential Storage"),

            # DITA validation library (hop_core.dita)
            ("tests/test_dita_validator.py",           "DITA Validator (DTD/xmllint)"),
            ("tests/test_dita_root_element.py",        "DITA Root-Element Regression"),
            ("tests/test_dita_fixture_validation.py",  "DITA Fixture Validation Cases"),
        ]

        passed = 0
        failed = 0

        for test_path, description in pytest_suites:
            if (self.repo_root / test_path).exists():
                if self.run_pytest(test_path, description):
                    passed += 1
                else:
                    failed += 1
            else:
                print(f"\n⚠️  Test file not found: {test_path}")
                self.test_results[description] = "⚠️ NOT FOUND"
                failed += 1

        self.print_summary(passed, failed)
        return 0 if failed == 0 else 1

    def print_summary(self, passed: int, failed: int):
        """Print test results summary."""
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)

        for test, result in self.test_results.items():
            print(f"{result:12} {test}")

        print("\n" + "-"*60)
        total = passed + failed
        print(f"Total Suites: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")

        if failed == 0:
            print("\n🎉 All tests passed!")
        else:
            print(f"\n⚠️  {failed} suite(s) failed")
        print("="*60)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run hop-core tests")
    parser.add_argument("--test", help="Run a specific test file (path relative to repo root)", default=None)
    parser.add_argument("--list", action="store_true", help="List available tests")

    args = parser.parse_args()

    runner = TestRunner()

    if args.list:
        print("\nAvailable test files:")
        print("-" * 40)
        for file in sorted(runner.tests_dir.glob("test_*.py")):
            print(f"  tests/{file.name}")
        return 0

    if args.test:
        ok = runner.run_pytest(args.test, args.test)
        runner.print_summary(int(ok), int(not ok))
        return 0 if ok else 1

    return runner.run_all_tests()


if __name__ == "__main__":
    sys.exit(main())
