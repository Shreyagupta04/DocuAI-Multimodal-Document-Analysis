"""
run.py — starts both the backend (FastAPI/uvicorn) and frontend (React/Vite)
at once, in one terminal.

Usage — run this from the project root (the DOCUAI/ folder itself):
    python run.py

Ctrl+C stops both processes together.
"""

import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()

# Adjust this if your frontend folder is named/located differently.
FRONTEND_DIR = PROJECT_ROOT / "docuai-frontend-react" / "docuai-react"


def find_venv_python():
    """
    Look for the venv's own python.exe directly, instead of trusting
    sys.executable / PATH -- those depend on Activate.ps1 having actually
    run in this shell, which isn't reliable (e.g. execution-policy errors
    fail silently and fall back to system Python, which won't have
    fastapi/uvicorn installed).
    """
    candidates = [
        PROJECT_ROOT / ".venv" / "Scripts" / "python.exe",  # Windows
        PROJECT_ROOT / ".venv" / "bin" / "python",            # macOS/Linux
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    print("Could not find .venv/Scripts/python.exe -- falling back to "
          "whatever 'python' resolves to on PATH. If uvicorn fails to "
          "import, this is why.")
    return sys.executable


PYTHON = find_venv_python()

BACKEND_CMD = [
    PYTHON, "-m", "uvicorn", "api:app",
    "--reload", "--port", "8000", "--app-dir", "inference",
]

processes = []


def start():
    print("Starting backend  (FastAPI  -> http://localhost:8000) ...")
    backend = subprocess.Popen(BACKEND_CMD, cwd=PROJECT_ROOT)
    processes.append(backend)

    print("Starting frontend (Vite/React -> http://localhost:5173) ...")
    # shell=True because on Windows `npm` is a .cmd wrapper, not a real .exe --
    # subprocess can't launch it directly without going through the shell.
    frontend = subprocess.Popen("npm run dev", cwd=FRONTEND_DIR, shell=True)
    processes.append(frontend)

    print()
    print("Both are starting up -- give it a few seconds, then open:")
    print("  http://localhost:5173")
    print()
    print("Press Ctrl+C to stop both.")
    print()


def stop():
    print("\nStopping both processes...")
    for p in processes:
        try:
            p.terminate()
        except Exception:
            pass
    time.sleep(1.5)
    for p in processes:
        if p.poll() is None:
            try:
                p.kill()
            except Exception:
                pass


if __name__ == "__main__":
    if not FRONTEND_DIR.exists():
        print(f"Couldn't find the frontend folder at:\n  {FRONTEND_DIR}")
        print("Open run.py and fix the FRONTEND_DIR path near the top if yours is named differently.")
        sys.exit(1)

    start()
    try:
        while True:
            time.sleep(1)
            for p in processes:
                if p.poll() is not None:
                    print(f"\nA process exited unexpectedly (exit code {p.returncode}). Stopping everything else.")
                    stop()
                    sys.exit(1)
    except KeyboardInterrupt:
        stop()