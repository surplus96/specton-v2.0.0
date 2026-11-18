"""Explicit Docker browser suite; external accounts remain scripted."""

import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from pydantic import SecretStr
from test_feedback import adopted, mail, suggested
from test_feedback import connected as connected
from test_feedback import settings as settings
from test_feedback import source as source
from test_feedback import verified as verified
from test_feedback import workspace as workspace

from specton.api.main import create_app
from specton.feedback import analysis, worker
from specton.implementation import preview_worker
from specton.implementation import worker as implementation_worker
from specton.integrations import gmail

pytestmark = [pytest.mark.db, pytest.mark.docker_browser]


def test_browser_mail_to_adoption(connected, pool, settings, monkeypatch):
    assert os.environ.get("SPECTON_TEST_BROWSER_IMAGE"), "Explicit browser/runtime images required"
    client, _, verified = connected
    adopted(verified)
    contract_change = any(a["id"] == "API-summary" for a in verified[0][1]["bundle"]["apis"])
    selected_mail, selected_analysis = mail(), suggested(verified)
    if contract_change:
        from test_feedback_calculations import mail as calculation_mail
        from test_feedback_calculations import proposed

        selected_mail, selected_analysis = calculation_mail(), proposed(verified)
    settings.openai_api_key = SecretStr("scripted-test-key")
    monkeypatch.setattr(
        gmail, "collect", lambda *a: ([selected_mail], "12345678901234567890", False)
    )
    monkeypatch.setattr(analysis, "run", lambda *a: (selected_analysis, []))
    output = Path(
        os.environ.get("SPECTON_TEST_FEEDBACK_REPORT_DIR", "var/test-results/feedback-browser")
    ).resolve()
    output.mkdir(parents=True, exist_ok=True)
    output.chmod(0o777)  # Synthetic output must be writable by the container UID.
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(create_app(settings, pool), log_level="error", access_log=False)
    )
    serving = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    stop = threading.Event()
    errors = []
    runtime, postgres, browser = verified[2]

    def work():
        try:
            while not stop.is_set():
                worker.run_once(pool, settings)
                implementation_worker.run_once(pool, runtime, postgres, browser)
                preview_worker.run_once(pool, runtime, postgres, browser)
                stop.wait(0.1)
        except Exception as exc:
            errors.append(type(exc).__name__)

    working = threading.Thread(target=work, daemon=True)
    serving.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    working.start()
    root = Path.cwd()
    network = ["--network", "host"] if sys.platform == "linux" else []
    backend = (
        "http://127.0.0.1:" if sys.platform == "linux" else "http://host.docker.internal:"
    ) + str(port)
    command = [
        "docker",
        "run",
        "--rm",
        "-i",
        *network,
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--tmpfs",
        "/tmp:rw,size=256m",
        "--shm-size=256m",
        "--cpus=1",
        "--memory=1g",
        "--pids-limit=256",
        "-v",
        str(root / "frontend/dist") + ":/app:ro",
        "-v",
        str(root / "tests/browser/feedback-flow.mjs") + ":/runner/feedback-flow.mjs:ro",
        "-v",
        str(output) + ":/out",
        browser,
        "node",
        "/runner/feedback-flow.mjs",
    ]
    try:
        result = subprocess.run(
            command,
            input=json.dumps(
                {
                    "backend": backend,
                    "contractChange": contract_change,
                    "subject": selected_mail["subject"],
                    "quote": selected_mail["body"],
                    "cookies": [{"name": k, "value": v} for k, v in client.cookies.items()],
                }
            ),
            text=True,
            capture_output=True,
            timeout=420,
        )
        assert result.returncode == 0, result.stderr[-6000:] + str(errors)
        report = json.loads(result.stdout)
        assert report["status"] == "passed"
        row = client.get("/api/v1/changes/" + report["change_id"]).json()
        assert row["state"] == "applied"
        report["implementation_id"] = row["implementation_id"]
        report["verification"] = row["verification"]
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        stop.set()
        working.join(timeout=240)
        # A preview might have been created even if a later browser assertion failed.
        with pool.connection() as conn:
            conn.execute(
                "UPDATE implementation_preview SET cancel_requested=true "
                "WHERE status NOT IN ('closed','failed','expired')"
            )
        preview_worker.run_once(pool, runtime, postgres, browser)
        server.should_exit = True
        serving.join(timeout=10)
        sock.close()
    assert not errors
