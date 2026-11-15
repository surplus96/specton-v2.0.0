import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from implementation_support import inventory_executable
from test_identity_projects import headers, login
from test_specifications import edit, expectation
from test_specifications import settings as settings
from test_specifications import workspace as workspace

from specton.api.main import create_app
from specton.contracts import DesignState
from specton.implementation import jobs, worker
from specton.implementation.package import json_bytes

pytestmark = pytest.mark.db


@pytest.fixture
def source(workspace, pool):
    client, initial, _, run = workspace
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT normalized_model FROM model_snapshot WHERE run_id=%s "
            "ORDER BY revision DESC LIMIT 1",
            (run,),
        ).fetchone()
    state = DesignState.model_validate({**row["normalized_model"], "run_id": run})
    spec = edit(client, initial, inventory_executable(initial, state)).json()
    url = "/api/v1/specs/" + spec["bundle"]["spec_id"]
    assert (
        client.post(url + "/approve", json=expectation(spec), headers=headers(client)).status_code
        == 200
    )
    impl = client.post(
        url + "/implementations", json=expectation(spec), headers=headers(client)
    ).json()
    return client, spec, impl


def enqueue(source, key=None):
    client, spec, impl = source
    return client.post(
        "/api/v1/implementations/" + impl["id"] + "/verifications",
        json={
            **expectation(spec),
            "source_hash": impl["source_hash"],
            "request_key": str(key or uuid4()),
        },
        headers=headers(client),
    )


def test_request_ownership_idempotency_and_cancel(source, pool, settings, monkeypatch):
    client, spec, impl = source
    url = "/api/v1/implementations/" + impl["id"] + "/verifications"
    key = uuid4()
    first = enqueue(source, key)
    assert first.status_code == 200, first.text
    job = first.json()
    assert enqueue(source, key).json()["id"] == job["id"]
    assert enqueue(source).status_code == 409
    assert (
        client.post(
            url,
            json={
                **expectation(spec),
                "source_hash": impl["source_hash"],
                "request_key": str(uuid4()),
            },
        ).status_code
        == 403
    )
    other = TestClient(create_app(settings, pool))
    login(other, monkeypatch, "other")
    assert other.get(url).status_code == 404
    assert other.post(url + "/" + job["id"] + "/cancel", headers=headers(other)).status_code == 404
    result = client.post(url + "/" + job["id"] + "/cancel", headers=headers(client))
    assert result.json()["status"] == "cancelled"
    assert enqueue(source, key).json()["status"] == "cancelled"
    assert enqueue(source).status_code == 200
    assert (
        client.get("/api/v1/implementations/" + impl["id"]).json()["validation_status"] == "queued"
    )


def test_claim_fencing_recovery_and_report_binding(source, pool):
    assert enqueue(source).status_code == 200

    def claim():
        with pool.connection() as conn:
            return jobs.claim(conn, "runtime", "postgres", "suite")

    with ThreadPoolExecutor(max_workers=2) as executor:
        claimed = list(executor.map(lambda _: claim(), range(2)))
    assert sum(job is not None for job in claimed) == 1
    job = next(job for job in claimed if job is not None)
    with pool.connection() as conn:
        with pytest.raises(ValueError):
            jobs.finish(conn, job, {"source_hash": "wrong"})
        conn.execute(
            "UPDATE implementation_verification SET lease_until=now()-interval '1 second' "
            "WHERE id=%s",
            (job["id"],),
        )
        assert jobs.heartbeat(conn, job) is None
        assert jobs.finish(conn, job, None, "late") is False
        assert jobs.claim(conn, "r", "p", "s") is None  # orphan execution grace
        conn.execute(
            "UPDATE implementation_verification SET deadline=now()-interval '181 seconds' "
            "WHERE id=%s",
            (job["id"],),
        )
        assert jobs.claim(conn, "r", "p", "s", "different-host") is None
        recovered = jobs.claim(conn, "r", "p", "s")
        assert recovered["status"] == "recovering"
        assert recovered["lease_token"] != job["lease_token"]
        assert jobs.finish(conn, job, None, "late") is False
        assert jobs.finish(conn, recovered, None, "WORKER_LOST") is True
    assert enqueue(source).status_code == 200


def test_running_cancel_wins_over_completion(source, pool):
    job_id = enqueue(source).json()["id"]
    with pool.connection() as conn:
        job = jobs.claim(conn, "runtime", "postgres", "suite")
    client, _, impl = source
    url = "/api/v1/implementations/" + impl["id"] + "/verifications/" + job_id + "/cancel"
    assert client.post(url, headers=headers(client)).json()["status"] == "cancelling"
    with pool.connection() as conn:
        assert jobs.heartbeat(conn, job) is True
        assert jobs.finish(conn, job, None, "CANCELLED")
    assert (
        client.get("/api/v1/implementations/" + impl["id"]).json()["validation_status"]
        == "cancelled"
    )


def test_worker_registers_report(source, pool, monkeypatch):
    enqueue(source)
    client, _, impl = source
    runtime = os.environ.get("SPECTON_TEST_WORKER_RUNTIME", "sha256:" + "1" * 64)
    postgres = os.environ.get("SPECTON_TEST_WORKER_POSTGRES", "sha256:" + "2" * 64)
    if not os.environ.get("SPECTON_TEST_WORKER_RUNTIME"):

        class Process:
            def __init__(self, args, **kwargs):
                from pathlib import Path

                from specton.implementation.package import TEMPLATES

                report = dict(
                    status="smoke_passed",
                    source_hash=impl["source_hash"],
                    spec_hash=impl["spec_hash"],
                    runtime_image=runtime,
                    postgres_image=postgres,
                    suite_hash=hashlib.sha256(
                        (TEMPLATES / "runtime/probe.py.txt").read_bytes()
                    ).hexdigest(),
                    business_acceptance="not_run",
                    browser_acceptance="not_run",
                    cleanup_complete=True,
                    checks=[{"status": "passed"}],
                )
                Path(args[args.index("--report") + 1]).write_text(json.dumps(report))

            def poll(self):
                return 0

        monkeypatch.setattr(worker, "docker", lambda args: b"test-host")
        monkeypatch.setattr(worker.subprocess, "Popen", Process)
        monkeypatch.setattr(worker, "cleanup", lambda key: None)
    assert worker.run_once(pool, runtime, postgres)
    assert not worker.run_once(pool, runtime, postgres)
    result = client.get("/api/v1/implementations/" + impl["id"] + "/verifications").json()[0]
    assert result["status"] == "smoke_passed", result
    assert hashlib.sha256(json_bytes(result["report"])).hexdigest() == result["report_hash"]
    assert result["source_hash"] == impl["source_hash"]
    if os.environ.get("SPECTON_TEST_WORKER_REPORT"):
        from pathlib import Path

        Path(os.environ["SPECTON_TEST_WORKER_REPORT"]).write_text(json.dumps(result, indent=2))
        Path(os.environ["SPECTON_TEST_WORKER_REPORT"]).with_suffix(".zip").write_bytes(
            client.get("/api/v1/implementations/" + impl["id"] + "/source").content
        )
    with pool.connection() as conn:
        conn.execute(
            "UPDATE implementation_verification SET report_hash=%s WHERE id=%s",
            ("0" * 64, result["id"]),
        )
    assert client.get("/api/v1/implementations/" + impl["id"] + "/verifications").status_code == 422
    assert client.get("/api/v1/implementations/" + impl["id"]).status_code == 422


def test_worker_failure_and_cleanup_retry(source, pool, monkeypatch):
    enqueue(source)

    def fail(key):
        raise RuntimeError("unavailable")

    monkeypatch.setattr(worker, "docker", lambda args: b"test-host")
    monkeypatch.setattr(worker, "cleanup", fail)
    with pool.connection() as conn:
        conn.execute(
            "UPDATE implementation_source SET source_zip='tampered'::bytea WHERE id=%s",
            (source[2]["id"],),
        )
    assert worker.run_once(pool, "r", "p")
    with pool.connection() as conn:
        row = conn.execute("SELECT * FROM implementation_verification").fetchone()
        assert row["status"] == "running" and row["report"] is None
        conn.execute(
            "UPDATE implementation_verification SET lease_until=now()-interval '1 second', "
            "deadline=now()-interval '181 seconds'"
        )
    monkeypatch.setattr(worker, "cleanup", lambda key: None)
    assert worker.run_once(pool, "r", "p")
    with pool.connection() as conn:
        row = conn.execute("SELECT * FROM implementation_verification").fetchone()
        assert row["status"] == "failed" and row["error_code"] == "WORKER_LOST"


def test_request_rejects_stale_approval_and_hash(source):
    client, spec, impl = source
    url = "/api/v1/implementations/" + impl["id"] + "/verifications"
    response = client.post(
        url,
        json={**expectation(spec), "source_hash": "0" * 64, "request_key": str(uuid4())},
        headers=headers(client),
    )
    assert response.status_code == 409
    proposal = spec["bundle"]
    proposal["requirements"][-1]["text"] += " revised"
    assert edit(client, spec, proposal).status_code == 200
    assert enqueue(source).status_code == 409


def test_cancel_stops_worker_process_before_registering(source, pool, monkeypatch):
    from pathlib import Path

    client, _, impl = source
    job_id = enqueue(source).json()["id"]
    stopped = []

    class Process:
        def __init__(self, args, **kwargs):
            assert "SPECTON_APP_DATABASE_URL" not in kwargs["env"]
            assert Path(args[3]).exists()
            result = client.post(
                "/api/v1/implementations/" + impl["id"] + "/verifications/" + job_id + "/cancel",
                headers=headers(client),
            )
            assert result.status_code == 200

        def poll(self):
            return 0 if stopped else None

    monkeypatch.setattr(worker, "docker", lambda args: b"test-host")
    monkeypatch.setattr(worker.subprocess, "Popen", Process)
    monkeypatch.setattr(worker, "stop", lambda process: stopped.append(True))
    cleaned = []
    monkeypatch.setattr(worker, "cleanup", lambda key: cleaned.append(key))
    assert worker.run_once(pool, "r", "p")
    assert stopped and cleaned
    with pool.connection() as conn:
        result = conn.execute("SELECT * FROM implementation_verification").fetchone()
        assert result["status"] == "cancelled" and result["report"] is None


def test_upgrade_keeps_approved_source(source, pool):
    from specton.persistence.db import apply_schema
    from specton.persistence.migrate import current_version
    from specton.persistence.migrations import HEAD

    with pool.connection() as conn:
        before = conn.execute("SELECT * FROM implementation_source").fetchall()
        conn.execute(
            "DROP TABLE feedback_revision,"
            "feedback_event,feedback_job,feedback_change,feedback_message,"
            "gmail_connection,gmail_oauth,implementation_adoption,"
            "implementation_preview,implementation_verification"
        )
        conn.execute("UPDATE alembic_version SET version_num='0004_implementation'")
    apply_schema(pool)
    apply_schema(pool)
    assert current_version(pool) == HEAD
    with pool.connection() as conn:
        assert conn.execute("SELECT * FROM implementation_source").fetchall() == before
    assert enqueue(source).status_code == 200


def test_verification_schema_drift_is_rejected(pool):
    from specton.persistence.db import apply_schema
    from specton.persistence.migrations import SchemaVersionError

    with pool.connection() as conn:
        conn.execute("DROP INDEX verification_active")
    with pytest.raises(SchemaVersionError):
        apply_schema(pool)


def test_concurrent_generation_and_requests_share_one_job(source, pool):
    client, spec, _ = source
    key = uuid4()

    def request(index):
        if index % 2:
            return enqueue(source, key)
        return client.post(
            "/api/v1/specs/" + spec["bundle"]["spec_id"] + "/implementations",
            json=expectation(spec),
            headers=headers(client),
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        responses = list(executor.map(request, range(8)))
    assert all(response.status_code == 200 for response in responses)
    with pool.connection() as conn:
        assert (
            conn.execute("SELECT count(*) AS count FROM implementation_verification").fetchone()[
                "count"
            ]
            == 1
        )
