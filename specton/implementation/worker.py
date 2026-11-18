"""Trusted local worker. API servers require no Docker access.

Run on the single configured Docker host; multiple worker processes may share it.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from uuid import UUID

from specton.implementation import jobs
from specton.implementation.runtime_suite import suite_hash as runtime_suite_hash
from specton.implementation.verify import docker, inspect_package
from specton.persistence.db import Pool


def cleanup(resource_key: str) -> None:
    label = "specton.verification=" + str(UUID(resource_key))
    containers = docker(["ps", "-aq", "--filter", "label=" + label]).decode().split()
    for container in containers:
        docker(["rm", "--force", "--volumes", container])
    networks = docker(["network", "ls", "-q", "--filter", "label=" + label]).decode().split()
    for network in networks:
        docker(["network", "rm", network])
    if (
        docker(["ps", "-aq", "--filter", "label=" + label]).strip()
        or docker(["network", "ls", "-q", "--filter", "label=" + label]).strip()
    ):
        raise RuntimeError("작업 자원 회수 미완료")


def stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)


def run_once(pool: Pool, runtime: str, postgres: str, browser: str | None = None) -> bool:
    suite = runtime_suite_hash()
    host = docker(["info", "--format", "{{.ID}}"]).decode().strip()
    if not host:
        raise RuntimeError("Docker 호스트 ID를 확인할 수 없습니다")
    with pool.connection() as conn:
        from specton.implementation.browser_runner import suite_hash

        job = jobs.claim(
            conn, runtime, postgres, suite, host, browser, suite_hash() if browser else None
        )
    if job is None:
        return False
    report: dict[str, Any] | None = None
    error = None
    process = None
    try:
        if job["status"] == "recovering":
            error = "WORKER_LOST"
        else:
            with pool.connection() as conn:
                row = conn.execute(
                    "SELECT * FROM implementation_source WHERE id=%s",
                    (job["implementation_id"],),
                ).fetchone()
            if (
                row is None
                or row["source_hash"] != job["source_hash"]
                or row["spec_hash"] != job["spec_hash"]
            ):
                raise ValueError("작업 소스 불일치")
            source = bytes(row["source_zip"])
            _, manifest = inspect_package(source, job["source_hash"])
            if manifest["spec_hash"] != job["spec_hash"]:
                raise ValueError("명세 해시 불일치")
            with tempfile.TemporaryDirectory(prefix="specton-verification-") as directory:
                root = Path(directory)
                archive, result = root / "source.zip", root / "report.json"
                archive.write_bytes(source)
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
                        "--resource-key",
                        str(job["resource_key"]),
                        *(["--browser-image", browser] if browser else []),
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
                        cancel = jobs.heartbeat(conn, job)
                    if cancel is None or cancel or time.monotonic() - started > 360:
                        error = "CANCELLED" if cancel else "LEASE_LOST_OR_TIMEOUT"
                        stop(process)
                        break
                    time.sleep(1)
                if error is None:
                    if result.exists() and result.stat().st_size <= 1024 * 1024:
                        report = json.loads(result.read_bytes())
                    else:
                        error = "VERIFIER_FAILED"
    except Exception:
        error = "WORKER_FAILED"
    finally:
        if process is not None:
            stop(process)
    try:
        cleanup(str(job["resource_key"]))
        with pool.connection() as conn:
            # Renew after cleanup; an obsolete or expired lease must never publish results.
            if jobs.heartbeat(conn, job) is not None:
                try:
                    jobs.finish(conn, job, report, error)
                except (ValueError, TypeError, KeyError):
                    jobs.finish(conn, job, None, "INVALID_REPORT")
    except Exception:
        # Keep the active row reserved. A later recovery attempt must confirm cleanup.
        return True
    return True


def main() -> None:
    from specton.config import Settings
    from specton.persistence.db import create_pool
    from specton.persistence.migrate import require_current_schema

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-image", required=True)
    parser.add_argument("--postgres-image", required=True)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--browser-image")
    args = parser.parse_args()
    import re

    for image in (
        args.runtime_image,
        args.postgres_image,
        *([args.browser_image] if args.browser_image else []),
    ):
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
            parser.error("로컬 불변 image ID가 필요합니다")
        if docker(["image", "inspect", image, "--format", "{{.Id}}"]).decode().strip() != image:
            parser.error("로컬 이미지가 일치하지 않습니다")
    with create_pool(Settings()) as pool:
        require_current_schema(pool)
        while True:
            from specton.implementation.preview_worker import run_once as preview_once

            worked = preview_once(pool, args.runtime_image, args.postgres_image, args.browser_image)
            if not worked:
                worked = run_once(pool, args.runtime_image, args.postgres_image, args.browser_image)
            if args.once:
                break
            if not worked:
                time.sleep(2)


if __name__ == "__main__":
    main()
