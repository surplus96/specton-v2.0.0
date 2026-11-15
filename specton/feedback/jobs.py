"""Durable work with lease fencing. External calls never hold a DB transaction."""

from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import DictRow

Conn = Connection[DictRow]


def enqueue(
    conn: Conn, owner_id: UUID, kind: str, target_id: UUID, generation: int
) -> dict[str, Any]:
    column = "connection_id" if kind == "sync" else "change_id"
    row = conn.execute(
        f"INSERT INTO feedback_job(id,owner_id,kind,{column},generation,state) "
        "VALUES(%s,%s,%s,%s,%s,'queued') ON CONFLICT DO NOTHING RETURNING *",
        (uuid4(), owner_id, kind, target_id, generation),
    ).fetchone()
    if row is None:
        row = conn.execute(
            f"SELECT * FROM feedback_job WHERE {column}=%s AND state IN ('queued','running')",
            (target_id,),
        ).fetchone()
    assert row is not None
    return row


def public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        k: row[k] for k in ("id", "kind", "state", "attempt", "error_code", "result", "created_at")
    }


def claim(conn: Conn) -> dict[str, Any] | None:
    # Expired analysis calls require explicit retry to avoid unbounded paid requests.
    conn.execute(
        "UPDATE feedback_job SET state=CASE WHEN kind='sync' AND attempt<5 THEN 'queued' "
        "ELSE 'failed' END,error_code='worker_lease_expired',lease_token=NULL "
        "WHERE state='running' AND lease_until<now()"
    )
    conn.execute(
        "UPDATE feedback_change c SET state='failed' WHERE c.state='analysing' "
        "AND EXISTS(SELECT 1 FROM feedback_job j WHERE j.change_id=c.id "
        "AND j.generation=c.version AND j.state='failed')"
    )
    with conn.transaction():
        row = conn.execute(
            "SELECT * FROM feedback_job WHERE state='queued' AND next_at<=now() "
            "ORDER BY created_at,id LIMIT 1 FOR UPDATE SKIP LOCKED"
        ).fetchone()
        if row is None:
            return None
        return conn.execute(
            "UPDATE feedback_job SET state='running',attempt=attempt+1,lease_token=%s,"
            "lease_until=now()+interval '300 seconds' WHERE id=%s RETURNING *",
            (uuid4(), row["id"]),
        ).fetchone()


def fenced(conn: Conn, job: dict[str, Any]) -> bool:
    return (
        conn.execute(
            "SELECT id FROM feedback_job WHERE id=%s AND state='running' AND lease_token=%s "
            "AND lease_until>now() FOR UPDATE",
            (job["id"], job["lease_token"]),
        ).fetchone()
        is not None
    )
