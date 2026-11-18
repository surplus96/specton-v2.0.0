"""Run bounded Gmail reconciliation and explicitly requested feedback analysis."""

import argparse
import random
import time
from typing import Any
from uuid import uuid4

import httpx
from psycopg.types.json import Jsonb

from specton.config import Settings
from specton.feedback import analysis, jobs
from specton.integrations import gmail
from specton.persistence.db import Pool, create_pool
from specton.persistence.migrate import require_current_schema


def schedule(pool: Pool) -> None:
    with pool.connection() as conn, conn.transaction():
        rows = conn.execute(
            "SELECT * FROM gmail_connection WHERE state='active' AND automatic "
            "AND next_sync_at<=now() ORDER BY next_sync_at LIMIT 20 FOR UPDATE SKIP LOCKED"
        ).fetchall()
        for row in rows:
            jobs.enqueue(conn, row["owner_id"], "sync", row["id"], row["generation"])
            conn.execute(
                "UPDATE gmail_connection SET next_sync_at=now()+interval '5 minutes' WHERE id=%s",
                (row["id"],),
            )


def failure(
    pool: Pool, job: dict[str, Any], code: str, retry: bool = False, delay: int = 0
) -> None:
    with pool.connection() as conn, conn.transaction():
        # Match publisher's target-before-job locking order.
        if job["kind"] == "sync":
            conn.execute(
                "SELECT id FROM gmail_connection WHERE id=%s FOR UPDATE", (job["connection_id"],)
            )
        else:
            from specton.api.feedback import change

            try:
                change(conn, job["change_id"], {"id": job["owner_id"]})
            except Exception:
                return
        if not jobs.fenced(conn, job):
            return
        repeat = retry and job["kind"] == "sync" and job["attempt"] < 5
        wait = max(delay, min(3600, 2 ** job["attempt"] * 10 + random.randint(0, 10)))
        conn.execute(
            "UPDATE feedback_job SET state=%s,error_code=%s,lease_token=NULL,"
            "next_at=now()+%s*interval '1 second' WHERE id=%s",
            ("queued" if repeat else "failed", code, wait, job["id"]),
        )
        if job["kind"] == "sync":
            conn.execute(
                "UPDATE gmail_connection SET error_code=%s,state=CASE WHEN %s THEN "
                "'reauth_required' ELSE state END,next_sync_at=now()+interval '1 hour' "
                "WHERE id=%s AND generation=%s AND state='active'",
                (code, code == "gmail_reauth_required", job["connection_id"], job["generation"]),
            )
        else:
            conn.execute(
                "UPDATE feedback_change SET state='failed' WHERE id=%s AND version=%s "
                "AND state='analysing'",
                (job["change_id"], job["generation"]),
            )


def sync(pool: Pool, settings: Settings, job: dict[str, Any]) -> None:
    with pool.connection() as conn:
        connection = conn.execute(
            "SELECT * FROM gmail_connection WHERE id=%s", (job["connection_id"],)
        ).fetchone()
        if (
            connection is None
            or connection["generation"] != job["generation"]
            or connection["state"] != "active"
        ):
            raise gmail.GmailError("gmail_connection_changed")
        connection["known_ids"] = {
            r["gmail_id"]
            for r in conn.execute(
                "SELECT gmail_id FROM feedback_message WHERE connection_id=%s",
                (job["connection_id"],),
            ).fetchall()
        }
    messages, history, recovered = gmail.collect(settings, connection)
    with pool.connection() as conn, conn.transaction():
        current = conn.execute(
            "SELECT * FROM gmail_connection WHERE id=%s FOR UPDATE", (job["connection_id"],)
        ).fetchone()
        if (
            current is None
            or current["generation"] != job["generation"]
            or current["state"] != "active"
            or not jobs.fenced(conn, job)
        ):
            return
        for msg in messages:
            conn.execute(
                "INSERT INTO feedback_message(id,connection_id,gmail_id,thread_id,subject,sender,"
                "received_at,body,content_hash,attachments) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT(connection_id,gmail_id) DO NOTHING",
                (
                    uuid4(),
                    connection["id"],
                    msg["gmail_id"],
                    msg["thread_id"],
                    msg["subject"],
                    msg["sender"],
                    msg["received_at"],
                    msg["body"],
                    msg["content_hash"],
                    Jsonb(msg["attachments"]),
                ),
            )
        conn.execute(
            "UPDATE gmail_connection SET history_id=%s,last_sync_at=now(),error_code=NULL,"
            "next_sync_at=now()+%s*interval '1 second' WHERE id=%s",
            (history, settings.gmail_poll_seconds, connection["id"]),
        )
        conn.execute(
            "UPDATE feedback_job SET state='succeeded',lease_token=NULL,error_code=NULL,result=%s "
            "WHERE id=%s",
            (Jsonb({"collected": len(messages), "history_recovered": recovered}), job["id"]),
        )


def analyse(pool: Pool, settings: Settings, job: dict[str, Any]) -> None:
    from specton.api.feedback import change, event, fresh, message, snapshot, validate_contract

    user = {"id": job["owner_id"]}
    with pool.connection() as conn, conn.transaction():
        row = change(conn, job["change_id"], user)
        if row["version"] != job["generation"] or row["state"] != "analysing":
            raise gmail.GmailError("feedback_changed")
        message(conn, row["message_id"], user)
        spec = fresh(conn, row, user)
    output, calls = analysis.run(settings, row["quote"], row["instruction"], spec.bundle)
    proposed, details = analysis.propose(spec.bundle, output, row["quote"])
    details["calls"] = calls
    document = proposed.model_dump(mode="json")
    target_hash = analysis.proposal_hash(row["spec_hash"], row["quote"], document, details)
    with pool.connection() as conn, conn.transaction():
        current = change(conn, job["change_id"], user)
        if (
            current["version"] != job["generation"]
            or current["state"] != "analysing"
            or not jobs.fenced(conn, job)
        ):
            return
        fresh(conn, current, user)
        message(conn, current["message_id"], user)
        validate_contract(conn, proposed, details)
        status = "needs_input" if analysis.needs_input(details) else "awaiting_decision"
        conn.execute(
            "UPDATE feedback_change SET state=%s,version=version+1,analysis=%s,proposal=%s,"
            "proposal_hash=%s WHERE id=%s",
            (status, Jsonb(details), Jsonb(document), target_hash, row["id"]),
        )
        snapshot(conn, row, details, document, target_hash)
        event(
            conn,
            {**row, "proposal_hash": target_hash},
            user,
            "analysed",
            "고정 출력 계약으로 분석 완료; 전체 회귀와 별도 업무 인수 필요",
        )
        conn.execute(
            "UPDATE feedback_job SET state='succeeded',lease_token=NULL,error_code=NULL,result=%s "
            "WHERE id=%s",
            (
                Jsonb({"change_id": str(row["id"]), "proposal_hash": target_hash, "calls": calls}),
                job["id"],
            ),
        )


def run_once(pool: Pool, settings: Settings) -> bool:
    with pool.connection() as conn:
        job = jobs.claim(conn)
    if job is None:
        return False
    try:
        (sync if job["kind"] == "sync" else analyse)(pool, settings, job)
    except gmail.GmailError as exc:
        failure(pool, job, exc.code, exc.retryable, exc.retry_after)
    except httpx.TransportError:
        failure(pool, job, "gmail_network_error", True)
    except Exception:
        # Do not persist provider exceptions containing mail, tokens, or request bodies.
        failure(pool, job, "feedback_processing_failed")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    pool = create_pool(settings)
    try:
        require_current_schema(pool)
        while True:
            schedule(pool)
            busy = run_once(pool, settings)
            if args.once:
                break
            if not busy:
                time.sleep(2)
    finally:
        pool.close()


if __name__ == "__main__":
    main()
