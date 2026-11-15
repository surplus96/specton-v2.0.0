import hashlib
import json
import os
import subprocess
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from test_identity_projects import headers, login
from test_verification_jobs import enqueue
from test_verification_jobs import settings as settings
from test_verification_jobs import source as source
from test_verification_jobs import workspace as workspace

from specton.api.main import create_app
from specton.implementation import jobs, preview_worker, worker
from specton.implementation.browser_runner import suite_hash

pytestmark = pytest.mark.db


@pytest.fixture
def verified(source, pool, settings, monkeypatch):
    real = os.environ.get("SPECTON_TEST_BROWSER_IMAGE")
    host = (
        subprocess.check_output(["docker", "info", "--format", "{{.ID}}"], text=True).strip()
        if real
        else "test-host"
    )
    settings.preview_worker_host = host
    runtime = os.environ.get("SPECTON_TEST_WORKER_RUNTIME", "r")
    postgres = os.environ.get("SPECTON_TEST_WORKER_POSTGRES", "p")
    browser = real or "b"
    enqueue(source)
    if real:
        assert worker.run_once(pool, runtime, postgres, browser)
    else:
        with pool.connection() as conn:
            job = jobs.claim(conn, runtime, postgres, "suite", host, browser, suite_hash())
            report = {
                key: job[key]
                for key in (
                    "source_hash",
                    "spec_hash",
                    "runtime_image",
                    "postgres_image",
                    "suite_hash",
                    "browser_image",
                    "browser_suite_hash",
                )
            }
            report.update(
                status="smoke_passed",
                cleanup_complete=True,
                business_acceptance="not_run",
                browser_acceptance="passed",
                checks=[{"status": "passed"}],
                browser={"status": "passed", "checks": [{"status": "passed"}]},
            )
            assert jobs.finish(conn, job, report)
        monkeypatch.setattr(preview_worker, "docker", lambda args: b"test-host")
    client, _, impl = source
    evidence = client.get("/api/v1/implementations/" + impl["id"] + "/verifications").json()[0]
    assert evidence["status"] == "smoke_passed", evidence
    return source, evidence, (runtime, postgres, browser)


def request(verified, key=None):
    (client, _, impl), evidence, _ = verified
    return client.post(
        "/api/v1/implementations/" + impl["id"] + "/previews",
        json={"verification_id": str(evidence["id"]), "request_key": str(key or uuid4())},
        headers=headers(client),
    )


def test_preview_owner_idempotency_close(verified, pool, settings, monkeypatch):
    (client, _, _), _, _ = verified
    key = uuid4()
    first = request(verified, key)
    assert first.status_code == 200, first.text
    preview = first.json()
    assert request(verified, key).json()["id"] == preview["id"]
    assert request(verified).status_code == 409
    assert client.get("/api/v1/previews/" + preview["id"] + "/document").status_code == 410
    other = TestClient(create_app(settings, pool))
    login(other, monkeypatch, "other")
    assert other.get("/api/v1/previews/" + preview["id"] + "/document").status_code == 404
    assert (
        other.post(
            "/api/v1/previews/" + preview["id"] + "/close", headers=headers(other)
        ).status_code
        == 404
    )
    assert client.post("/api/v1/previews/" + preview["id"] + "/close").status_code == 403
    assert (
        client.post("/api/v1/previews/" + preview["id"] + "/close", headers=headers(client)).json()[
            "status"
        ]
        == "closed"
    )
    assert request(verified).status_code == 200


def test_preview_requires_browser_evidence(source, pool, settings):
    settings.preview_worker_host = "test-host"
    response = enqueue(source)
    job_id = response.json()["id"]
    client, _, impl = source
    result = client.post(
        "/api/v1/implementations/" + impl["id"] + "/previews",
        json={"verification_id": job_id, "request_key": str(uuid4())},
        headers=headers(client),
    )
    assert result.status_code == 422


def test_preview_runtime_proxy_and_expiry(verified, pool, monkeypatch):
    (client, _, impl), evidence, images = verified
    preview = request(verified).json()
    pid = preview["id"]
    real = os.environ.get("SPECTON_TEST_BROWSER_IMAGE")
    if not real:
        from pathlib import Path

        class Process:
            def __init__(self, args, **kwargs):
                report = {
                    **evidence["report"],
                    "_preview": {"port": 45678, "access_token": "demo", "html": "<p>isolated</p>"},
                }
                Path(args[args.index("--report") + 1]).write_text(json.dumps(report))

            def poll(self):
                return 0

        monkeypatch.setattr(preview_worker.subprocess, "Popen", Process)
        monkeypatch.setattr(preview_worker, "cleanup", lambda key: None)
    assert preview_worker.run_once(pool, *images)
    base = "/api/v1/previews/" + pid
    doc = client.get(base + "/document")
    assert doc.status_code == 200, doc.text
    assert hashlib.sha256(doc.json()["html"].encode()).hexdigest() == doc.json()["sha256"]
    listing = client.get("/api/v1/implementations/" + impl["id"] + "/previews").json()[0]
    assert (
        listing["status"] == "ready" and "access_token" not in listing and "app_port" not in listing
    )
    for path in ["http://example.com", "/api/../health", "/api/docs", "//127.0.0.1/secret"]:
        assert (
            client.post(
                base + "/rpc", json={"method": "GET", "path": path}, headers=headers(client)
            ).status_code
            == 422
        )
    if not real:

        def handler(req):
            assert req.url.host == "127.0.0.1" and req.url.port == 45678
            assert req.headers["authorization"] == "Bearer demo"
            return httpx.Response(200, json={"quantity": "0.000"})

        original = httpx.Client
        monkeypatch.setattr(
            "specton.api.previews.httpx.Client",
            lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
        )
    result = client.post(
        base + "/rpc",
        json={"method": "GET", "path": "/api/inventory/balances?warehouse_id=b&item_id=b"},
        headers=headers(client),
    )
    assert result.status_code == 200, result.text
    assert json.loads(result.json()["body"])["quantity"] == "0.000"
    with pool.connection() as conn:
        conn.execute(
            "UPDATE implementation_preview SET expires_at=now()-interval '1 second' WHERE id=%s",
            (pid,),
        )
    assert client.get(base + "/document").status_code == 410
    assert (
        client.post(
            base + "/rpc",
            json={"method": "GET", "path": "/api/inventory/balances"},
            headers=headers(client),
        ).status_code
        == 410
    )
    assert preview_worker.run_once(pool, *images)
    with pool.connection() as conn:
        row = conn.execute("SELECT * FROM implementation_preview WHERE id=%s", (pid,)).fetchone()
        assert row["status"] == "closed" and row["access_token"] is None and row["html"] is None

    if real and os.environ.get("SPECTON_TEST_PREVIEW_REPORT"):
        from pathlib import Path

        report = {
            "cleanup_complete": True,
            "status": "passed",
            "verification": evidence,
            "checks": ["owner_proxy", "sandbox_document_hash", "route_allowlist", "expiry_denied"],
        }
        Path(os.environ["SPECTON_TEST_PREVIEW_REPORT"]).write_text(json.dumps(report, indent=2))
        Path(os.environ["SPECTON_TEST_PREVIEW_REPORT"]).with_suffix(".zip").write_bytes(
            client.get("/api/v1/implementations/" + impl["id"] + "/source").content
        )


def test_preview_close_and_lost_worker_recovery(verified, pool, monkeypatch):
    (client, _, _), _, images = verified
    first = request(verified).json()
    with pool.connection() as conn:
        conn.execute(
            "UPDATE implementation_preview SET "
            "status='ready',html='demo',access_token='secret' WHERE id=%s",
            (first["id"],),
        )
    assert (
        client.post("/api/v1/previews/" + first["id"] + "/close", headers=headers(client)).json()[
            "status"
        ]
        == "closing"
    )
    assert client.get("/api/v1/previews/" + first["id"] + "/document").status_code == 410
    cleaned = []
    monkeypatch.setattr(preview_worker, "cleanup", lambda key: cleaned.append(key))
    assert preview_worker.run_once(pool, *images)
    second = request(verified).json()
    with pool.connection() as conn:
        conn.execute(
            "UPDATE implementation_preview SET status='starting',lease_until=now()-interval"
            " '1 second',deadline=now() WHERE id=%s",
            (second["id"],),
        )
    assert not preview_worker.run_once(pool, *images)
    with pool.connection() as conn:
        conn.execute(
            "UPDATE implementation_preview SET deadline=now()-interval '181 "
            "seconds',executor_host='other' WHERE id=%s",
            (second["id"],),
        )
    assert not preview_worker.run_once(pool, *images)
    with pool.connection() as conn:
        conn.execute(
            "UPDATE implementation_preview SET executor_host='test-host' WHERE id=%s",
            (second["id"],),
        )
    assert preview_worker.run_once(pool, *images)
    assert len(cleaned) == 2


def test_preview_document_hash_and_host_are_checked(verified, pool, settings):
    (client, _, _), _, _ = verified
    preview = request(verified).json()
    with pool.connection() as conn:
        conn.execute(
            "UPDATE implementation_preview SET "
            "status='ready',html='tampered',html_hash='wrong' WHERE id=%s",
            (preview["id"],),
        )
    assert client.get("/api/v1/previews/" + preview["id"] + "/document").status_code == 422
    settings.preview_worker_host = "different"
    assert client.get("/api/v1/previews/" + preview["id"] + "/document").status_code == 503


def test_upgrade_keeps_existing_verification(verified, pool):
    from specton.persistence.db import apply_schema
    from specton.persistence.migrate import current_version
    from specton.persistence.migrations import HEAD

    with pool.connection() as conn:
        before = conn.execute(
            "SELECT report,report_hash,source_hash FROM implementation_verification"
        ).fetchall()
        conn.execute(
            "DROP TABLE feedback_revision,"
            "feedback_event,feedback_job,feedback_change,feedback_message,"
            "gmail_connection,gmail_oauth,implementation_adoption,"
            "implementation_preview"
        )
        conn.execute(
            "ALTER TABLE implementation_verification DROP COLUMN browser_image, DROP COLUMN"
            " browser_suite_hash"
        )
        conn.execute("UPDATE alembic_version SET version_num='0005_verification'")
    apply_schema(pool)
    apply_schema(pool)
    assert current_version(pool) == HEAD
    with pool.connection() as conn:
        assert (
            conn.execute(
                "SELECT report,report_hash,source_hash FROM implementation_verification"
            ).fetchall()
            == before
        )


def test_account_preview_quota_can_be_released(verified, pool):
    from test_specifications import edit, expectation

    current = verified
    first = request(current).json()
    client, _, _ = current[0]
    for index in (2, 3):
        _, spec, _ = current[0]
        bundle = spec["bundle"]
        bundle["requirements"][-1]["text"] += " updated"
        spec = edit(client, spec, bundle).json()
        url = "/api/v1/specs/" + spec["bundle"]["spec_id"]
        assert (
            client.post(
                url + "/approve", json=expectation(spec), headers=headers(client)
            ).status_code
            == 200
        )
        impl = client.post(
            url + "/implementations", json=expectation(spec), headers=headers(client)
        ).json()
        new_source = (client, spec, impl)
        enqueue(new_source)
        with pool.connection() as conn:
            job = jobs.claim(conn, "r", "p", "suite", "test-host", "b", suite_hash())
            report = {
                **current[1]["report"],
                **{
                    key: job[key]
                    for key in (
                        "source_hash",
                        "spec_hash",
                        "runtime_image",
                        "postgres_image",
                        "suite_hash",
                        "browser_image",
                        "browser_suite_hash",
                    )
                },
            }
            assert jobs.finish(conn, job, report)
            evidence = jobs.public(
                conn.execute(
                    "SELECT * FROM implementation_verification WHERE id=%s", (job["id"],)
                ).fetchone()
            )
        current = (new_source, evidence, ("r", "p", "b"))
        response = request(current)
        assert response.status_code == (200 if index == 2 else 429), response.text
    assert (
        client.post(
            "/api/v1/previews/" + first["id"] + "/close", headers=headers(client)
        ).status_code
        == 200
    )
    assert request(current).status_code == 200
