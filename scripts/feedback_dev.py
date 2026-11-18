"""Start/status/stop the local feedback browser-test services (not production deployment)."""

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "var/feedback-dev/processes.json"


def alive(item):
    try:
        args = subprocess.check_output(
            ["ps", "-p", str(item["pid"]), "-o", "args="],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return item["identity"] in args
    except subprocess.CalledProcessError:
        return False


def listening(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "status", "stop"])
    action = parser.parse_args().action
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    records = json.loads(STATE.read_text()) if STATE.exists() else {}
    if action == "stop":
        for name, item in records.items():
            if alive(item):
                os.killpg(item["pid"], signal.SIGTERM)
                print(name + ": stopping")
        return
    if action == "start":
        from specton.config import Settings
        from specton.integrations.gmail import cipher
        from specton.persistence.db import create_pool
        from specton.persistence.migrate import require_current_schema

        settings = Settings()
        if settings.public_origin != "http://localhost:5173":
            raise SystemExit("This helper requires SPECTON_PUBLIC_ORIGIN=http://localhost:5173")
        cipher(settings)
        pool = create_pool(settings)
        try:
            require_current_schema(pool)
        finally:
            pool.close()

        def image(name):
            return subprocess.check_output(
                ["docker", "image", "inspect", name, "--format", "{{.Id}}"],
                text=True,
            ).strip()

        commands = {
            "api": (
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "specton.api.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8000",
                ],
                "uvicorn specton.api.main:app",
                8000,
            ),
            "web": (
                [
                    "npm",
                    "--prefix",
                    "frontend",
                    "run",
                    "dev",
                    "--",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "5173",
                    "--strictPort",
                ],
                "npm",
                5173,
            ),
            "feedback": (
                [sys.executable, "-m", "specton.feedback.worker"],
                "specton.feedback.worker",
                None,
            ),
            "verification": (
                [
                    sys.executable,
                    "-m",
                    "specton.implementation.worker",
                    "--runtime-image",
                    image("specton-generated-runtime:inventory-ledger-v1"),
                    "--postgres-image",
                    image("postgres:18"),
                    "--browser-image",
                    image("specton-browser:generated-ui-v1"),
                ],
                "specton.implementation.worker",
                None,
            ),
        }
        STATE.parent.mkdir(parents=True, exist_ok=True)
        for name, (command, identity, port) in commands.items():
            if name in records and alive(records[name]):
                continue
            if port and listening(port):
                raise SystemExit(
                    f"Port {port} is already occupied; no existing process was stopped."
                )
            with (STATE.parent / (name + ".log")).open("ab") as log:
                process = subprocess.Popen(
                    command,
                    cwd=ROOT,
                    stdout=log,
                    stderr=log,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                )
            records[name] = {"pid": process.pid, "identity": identity}
            STATE.write_text(json.dumps(records, indent=2))
        for _ in range(100):
            if listening(8000) and listening(5173):
                break
            time.sleep(0.2)
    for name, item in records.items():
        print(name + ": " + ("running" if alive(item) else "stopped"))
    print("Browser: http://localhost:5173/feedback")
    print("Logs: var/feedback-dev/")


if __name__ == "__main__":
    main()
