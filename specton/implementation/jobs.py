"""Database queue, lease fencing and trusted worker result registration."""

import hashlib
from typing import Any
from uuid import uuid4

from psycopg import Connection
from psycopg.rows import DictRow
from psycopg.types.json import Jsonb

from specton.implementation.package import json_bytes

ACTIVE = ("queued", "running", "cancelling", "recovering")


def public(row: dict[str, Any]) -> dict[str, Any]:
    if row["report"] is not None and (
        hashlib.sha256(json_bytes(row["report"])).hexdigest() != row["report_hash"]
    ):
        raise ValueError("저장된 검증 결과 해시가 일치하지 않습니다")
    return {
        key: row[key]
        for key in (
            "id",
            "implementation_id",
            "source_hash",
            "spec_hash",
            "status",
            "created_at",
            "started_at",
            "finished_at",
            "runtime_image",
            "postgres_image",
            "suite_hash",
            "report",
            "report_hash",
            "error_code",
            "cancel_requested",
        )
    }


def claim(
    conn: Connection[DictRow], runtime: str, postgres: str, suite: str, host: str = "test-host"
) -> dict[str, Any] | None:
    with conn.transaction():
        row = conn.execute(
            "SELECT * FROM implementation_verification WHERE status='queued' OR "
            "(status IN ('running','cancelling','recovering') AND lease_until < now() "
            "AND deadline + interval '180 seconds' < now() AND executor_host=%s) "
            "ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1",
            (host,),
        ).fetchone()
        if row is None:
            return None
        recovery = row["status"] != "queued"
        return conn.execute(
            "UPDATE implementation_verification SET status=%s, lease_token=%s, "
            "lease_until=now()+interval '120 seconds', "
            "started_at=coalesce(started_at,now()), "
            "deadline=CASE WHEN %s THEN deadline ELSE now()+interval '360 seconds' END, "
            "runtime_image=coalesce(runtime_image,%s), postgres_image=coalesce(postgres_image,%s), "
            "suite_hash=coalesce(suite_hash,%s), executor_host=coalesce(executor_host,%s) "
            "WHERE id=%s RETURNING *",
            (
                "recovering" if recovery else "running",
                uuid4(),
                recovery,
                runtime,
                postgres,
                suite,
                host,
                row["id"],
            ),
        ).fetchone()


def heartbeat(conn: Connection[DictRow], job: dict[str, Any]) -> bool | None:
    row = conn.execute(
        "UPDATE implementation_verification SET lease_until=now()+interval '120 seconds' "
        "WHERE id=%s AND lease_token=%s AND lease_until>now() "
        "AND status IN ('running','cancelling','recovering') RETURNING cancel_requested",
        (job["id"], job["lease_token"]),
    ).fetchone()
    return row["cancel_requested"] if row is not None else None


def finish(
    conn: Connection[DictRow],
    job: dict[str, Any],
    report: dict[str, Any] | None,
    error: str | None = None,
) -> bool:
    if report is not None:
        for key in ("source_hash", "spec_hash", "runtime_image", "postgres_image", "suite_hash"):
            if report.get(key) != job[key]:
                raise ValueError("검증 증거가 작업에 고정한 해시·이미지와 다릅니다")
        if (
            report.get("status") not in ("smoke_passed", "failed")
            or report.get("business_acceptance") != "not_run"
            or report.get("browser_acceptance") != "not_run"
        ):
            raise ValueError("지원하지 않는 검증 판정")
        if report.get("cleanup_complete") is not True:
            raise ValueError("자원 정리 확인이 필요합니다")
        if report["status"] == "smoke_passed" and (
            not isinstance(report.get("checks"), list)
            or not report["checks"]
            or any(
                not isinstance(check, dict) or check.get("status") != "passed"
                for check in report["checks"]
            )
        ):
            raise ValueError("검증 항목 통과 증거가 없습니다")
    with conn.transaction():
        row = conn.execute(
            "SELECT * FROM implementation_verification WHERE id=%s AND lease_token=%s "
            "AND lease_until>now() AND status IN ('running','cancelling','recovering') FOR UPDATE",
            (job["id"], job["lease_token"]),
        ).fetchone()
        if row is None:
            return False
        status = (
            "cancelled"
            if row["cancel_requested"]
            else "smoke_passed"
            if report and report["status"] == "smoke_passed" and not error
            else "failed"
        )
        conn.execute(
            "UPDATE implementation_verification SET status=%s, report=%s, report_hash=%s, "
            "error_code=%s, finished_at=now(), lease_until=NULL WHERE id=%s",
            (
                status,
                Jsonb(report) if report else None,
                hashlib.sha256(json_bytes(report)).hexdigest() if report else None,
                error,
                job["id"],
            ),
        )
        return True
