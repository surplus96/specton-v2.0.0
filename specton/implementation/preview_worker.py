"""Expiring, owner-proxied preview resources on the configured local Docker host."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from specton.implementation.verify import docker
from specton.implementation.worker import cleanup, stop
from specton.persistence.db import Pool


def run_once(pool: Pool, runtime: str, postgres: str, browser: str | None) -> bool:
    host = docker(["info", "--format", "{{.ID}}"]).decode().strip()
    with pool.connection() as conn, conn.transaction():
        job = conn.execute(
            "SELECT * FROM implementation_preview WHERE executor_host=%s AND ("
            "(status='queued' AND %s) OR (status='ready' AND (cancel_requested OR "
            "expires_at<=now())) OR "
            "(status IN ('closing','recovering') AND lease_until<=now()) OR "
            "(status='starting' AND lease_until<now() AND deadline+interval '180 seconds'<now())) "
            "ORDER BY CASE WHEN status='queued' THEN 1 ELSE 0 END,created_at "
            "FOR UPDATE SKIP LOCKED LIMIT 1",
            (host, browser is not None),
        ).fetchone()
        if job is None:
            return False
        launch = job["status"] == "queued" and not job["cancel_requested"]
        freshness = conn.execute(
            "SELECT expires_at>now() AS valid FROM implementation_preview WHERE id=%s", (job["id"],)
        ).fetchone()
        assert freshness is not None
        launch = launch and freshness["valid"]
        token = uuid4()
        conn.execute(
            "UPDATE implementation_preview SET "
            "status=%s,lease_token=%s,lease_until=now()+interval '120 "
            "seconds',deadline=now()+interval '360 seconds' WHERE id=%s",
            ("starting" if launch else "recovering", token, job["id"]),
        )
    process = None
    handoff = None
    error = None
    try:
        if launch:
            assert browser is not None
            with pool.connection() as conn:
                source = conn.execute(
                    "SELECT * FROM implementation_source WHERE id=%s", (job["implementation_id"],)
                ).fetchone()
                verification = conn.execute(
                    "SELECT * FROM implementation_verification WHERE id=%s",
                    (job["verification_id"],),
                ).fetchone()
            from specton.implementation.jobs import public

            if source is None or verification is None:
                raise ValueError("미리보기 출처 없음")
            public(verification)
            if (
                verification["status"] != "smoke_passed"
                or verification["report"]["browser_acceptance"] != "passed"
                or source["source_hash"] != job["source_hash"]
                or verification["source_hash"] != job["source_hash"]
                or verification["runtime_image"] != runtime
                or verification["postgres_image"] != postgres
                or verification["browser_image"] != browser
            ):
                raise ValueError("검증한 릴리스와 미리보기 이미지가 다릅니다")
            with tempfile.TemporaryDirectory(prefix="specton-preview-") as directory:
                root = Path(directory)
                archive = root / "source.zip"
                result = root / "result.json"
                archive.write_bytes(bytes(source["source_zip"]))
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "specton.implementation.verify",
                        str(archive),
                        "--expected-source-hash",
                        job["source_hash"],
                        "--runtime-image",
                        runtime,
                        "--postgres-image",
                        postgres,
                        "--browser-image",
                        browser,
                        "--resource-key",
                        str(job["resource_key"]),
                        "--preview-lifetime",
                        "900",
                        "--report",
                        str(result),
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                    env={
                        key: os.environ[key]
                        for key in (
                            "PATH",
                            "HOME",
                            "DOCKER_HOST",
                            "DOCKER_CONTEXT",
                            "DOCKER_CONFIG",
                        )
                        if key in os.environ
                    },
                )
                started = time.monotonic()
                while process.poll() is None:
                    with pool.connection() as conn:
                        lease = conn.execute(
                            "UPDATE implementation_preview SET lease_until=now()+interval "
                            "'120 seconds' WHERE id=%s AND lease_token=%s AND "
                            "lease_until>now() RETURNING cancel_requested,expires_at>now() "
                            "AS valid",
                            (job["id"], token),
                        ).fetchone()
                    if (
                        not lease
                        or lease["cancel_requested"]
                        or not lease["valid"]
                        or time.monotonic() - started > 360
                    ):
                        stop(process)
                        error = "CANCELLED_OR_TIMEOUT"
                        break
                    time.sleep(1)
                if error is None and result.exists() and result.stat().st_size <= 2 * 1024 * 1024:
                    report = json.loads(result.read_bytes())
                    if (
                        report["status"] != "smoke_passed"
                        or report["browser_acceptance"] != "passed"
                    ):
                        raise ValueError("미리보기 브라우저 검사 실패")
                    for key in (
                        "source_hash",
                        "spec_hash",
                        "runtime_image",
                        "postgres_image",
                        "suite_hash",
                        "browser_image",
                        "browser_suite_hash",
                    ):
                        if report[key] != verification[key]:
                            raise ValueError("미리보기 출처 불일치")
                    handoff = report["_preview"]
                    if (
                        not isinstance(handoff["port"], int)
                        or not 1024 <= handoff["port"] <= 65535
                        or not isinstance(handoff["html"], str)
                        or len(handoff["html"]) > 1024 * 1024
                    ):
                        raise ValueError("미리보기 전달값 오류")
                else:
                    error = error or "PREVIEW_FAILED"
    except Exception:
        error = "PREVIEW_FAILED"
    finally:
        if process is not None:
            stop(process)
    if handoff and not error:
        with pool.connection() as conn:
            ready = conn.execute(
                "UPDATE implementation_preview SET "
                "status='ready',app_port=%s,access_token=%s,html=%s,html_hash=%s,lease_until=NULL"
                " WHERE id=%s AND lease_token=%s AND lease_until>now() AND expires_at>now()"
                " AND NOT cancel_requested RETURNING id",
                (
                    handoff["port"],
                    handoff["access_token"],
                    handoff["html"],
                    hashlib.sha256(handoff["html"].encode()).hexdigest(),
                    job["id"],
                    token,
                ),
            ).fetchone()
        if ready:
            return True
    try:
        cleanup(str(job["resource_key"]))
        with pool.connection() as conn:
            conn.execute(
                "UPDATE implementation_preview SET status=CASE WHEN %s AND NOT "
                "cancel_requested AND expires_at>now() THEN 'failed' ELSE 'closed' "
                "END,error_code=%s,app_port=NULL,access_token=NULL,html=NULL,html_hash=NULL,lease_until=NULL"
                " WHERE id=%s AND lease_token=%s AND lease_until>now()",
                (launch, error, job["id"], token),
            )
    except Exception:
        pass  # Keep reserved; the same daemon must confirm cleanup on a later recovery attempt.
    return True
