#!/usr/bin/env python3
"""Run both the OCR regression test and the UI test suite."""
import subprocess
import sys


def main():
    print("=" * 60)
    print("1. OCR parser regression (test_real.py)")
    print("=" * 60)
    rc = subprocess.call([sys.executable, "-W", "ignore", "test_real.py"])
    if rc:
        print("OCR regression FAILED")
        return rc
    print("\n" + "=" * 60)
    print("2. UI test suite (pytest tests/test_ui.py)")
    print("=" * 60)
    rc = subprocess.call([
        sys.executable, "-W", "ignore", "-m", "pytest",
        "tests/test_ui.py", "-v", "--timeout=30", "--tb=short",
    ])
    return rc


if __name__ == "__main__":
    sys.exit(main())
