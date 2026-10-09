#!/usr/bin/env python3
"""Create a local virtual environment and install every project dependency.

Run once immediately after cloning:

    python bootstrap.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"
ENV_EXAMPLE = ROOT / ".env.example"
ENV_FILE = ROOT / ".env"


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def run(*args: str) -> None:
    print("+", " ".join(args))
    subprocess.check_call(args, cwd=ROOT)


def main() -> int:
    if sys.version_info < (3, 11):
        print("Python 3.11 or newer is required.", file=sys.stderr)
        return 1
    if not REQUIREMENTS.is_file():
        print("requirements.txt was not found.", file=sys.stderr)
        return 1

    if not venv_python().is_file():
        if VENV.exists():
            print("Existing .venv is incomplete; remove it and re-run this command.", file=sys.stderr)
            return 1
        run(sys.executable, "-m", "venv", str(VENV))

    python = str(venv_python())
    run(python, "-m", "pip", "install", "--upgrade", "pip")
    run(python, "-m", "pip", "install", "-r", str(REQUIREMENTS))

    if not ENV_FILE.exists():
        shutil.copyfile(ENV_EXAMPLE, ENV_FILE)
        print("Created .env from .env.example. Review it before production use.")
    else:
        print("Kept existing .env unchanged.")

    command = ".venv\\Scripts\\python.exe -m uvicorn app.main:app --reload" if sys.platform == "win32" else ".venv/bin/python -m uvicorn app.main:app --reload"
    print("\nSetup complete. Start the app with:\n  " + command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
