"""Session-bound read-only Gmail connection and bounded collection configuration."""

import secrets
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from pydantic import Field

from specton.api.auth import COOKIE, Mutation, UserDep, digest
from specton.api.deps import ConnDep, SettingsDep
from specton.api.specifications import fail
from specton.contracts.base import Contract
from specton.feedback import jobs
from specton.integrations import gmail

router = APIRouter(prefix="/api/v1/integrations/gmail", tags=["gmail"])


class Filter(Contract):
    query: str = Field(min_length=1, max_length=500)
    automatic: bool = False


def owned(conn: ConnDep, connection_id: UUID, user: UserDep) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM gmail_connection WHERE id=%s AND owner_id=%s FOR UPDATE",
        (connection_id, user["id"]),
    ).fetchone()
    if row is None:
        fail(404, "Gmail 연결을 찾을 수 없습니다.")
    return row


@router.get("", operation_id="getGmailConnection")
def status(user: UserDep, conn: ConnDep, settings: SettingsDep) -> dict[str, Any]:
    row = conn.execute(
        "SELECT id,email,state,query,automatic,last_sync_at,error_code FROM gmail_connection "
        "WHERE owner_id=%s",
        (user["id"],),
    ).fetchone()
    return {
        "connection": row,
        "configured": bool(
            settings.google_client_id and settings.google_client_secret and settings.gmail_token_key
        ),
        "analysis_enabled": settings.feedback_analysis_enabled and bool(settings.openai_api_key),
    }


@router.post("/connect", operation_id="connectGmail")
def connect(
    request: Request, user: UserDep, conn: ConnDep, settings: SettingsDep, checked: Mutation
) -> dict[str, str]:
    state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
    try:
        url = gmail.authorization_url(settings, state, nonce, verifier)
    except gmail.GmailError:
        fail(503, "Google 클라이언트와 Gmail 토큰 암호화 키 설정이 필요합니다.")
    with conn.transaction():
        conn.execute("SELECT id FROM app_user WHERE id=%s FOR UPDATE", (user["id"],))
        conn.execute(
            "DELETE FROM gmail_oauth WHERE owner_id=%s OR expires_at<=now()", (user["id"],)
        )
        conn.execute(
            "INSERT INTO gmail_oauth(state_hash,owner_id,session_hash,nonce,verifier,expires_at) "
            "VALUES(%s,%s,%s,%s,%s,now()+interval '10 minutes')",
            (digest(state), user["id"], digest(request.cookies.get(COOKIE, "")), nonce, verifier),
        )
    return {"url": url}


@router.get("/callback", operation_id="gmailCallback", status_code=303)
def callback(
    request: Request,
    user: UserDep,
    conn: ConnDep,
    settings: SettingsDep,
    state: str = "",
    code: str = "",
    error: str = "",
) -> RedirectResponse:
    attempt = conn.execute(
        "UPDATE gmail_oauth SET consumed=true WHERE state_hash=%s AND owner_id=%s "
        "AND session_hash=%s AND NOT consumed AND expires_at>now() RETURNING *",
        (digest(state), user["id"], digest(request.cookies.get(COOKIE, ""))),
    ).fetchone()
    if attempt is None:
        fail(400, "Gmail 연결 요청이 만료됐거나 로그인 세션이 다릅니다.")
    outcome = "connected"
    if error or not code:
        outcome = "denied"
    else:
        try:
            identity, refresh = gmail.exchange(
                settings, code, attempt["nonce"], attempt["verifier"]
            )
            account = conn.execute(
                "SELECT google_subject FROM app_user WHERE id=%s", (user["id"],)
            ).fetchone()
            if account is None or identity.subject != account["google_subject"]:
                raise gmail.GmailError("gmail_account_mismatch")
            encrypted = gmail.seal(settings, refresh) if refresh else None
            with conn.transaction():
                # Serializes reconnect/disconnect; never returns credentials to the client.
                conn.execute("SELECT id FROM app_user WHERE id=%s FOR UPDATE", (user["id"],))
                if encrypted is None:
                    old = conn.execute(
                        "SELECT encrypted_token FROM gmail_connection WHERE owner_id=%s",
                        (user["id"],),
                    ).fetchone()
                    if not old or not old["encrypted_token"]:
                        raise gmail.GmailError("gmail_consent_required")
                    encrypted = old["encrypted_token"]
                valid = conn.execute(
                    "DELETE FROM gmail_oauth WHERE state_hash=%s AND owner_id=%s "
                    "AND consumed AND expires_at>now() RETURNING state_hash",
                    (digest(state), user["id"]),
                ).fetchone()
                if valid is None:
                    raise gmail.GmailError("gmail_request_cancelled")
                row = conn.execute(
                    "INSERT INTO gmail_connection(id,owner_id,google_subject,email,state,"
                    "encrypted_token) "
                    "VALUES(%s,%s,%s,%s,'active',%s) ON CONFLICT(owner_id) DO UPDATE SET "
                    "state='active',encrypted_token=excluded.encrypted_token,email=excluded.email,"
                    "generation=gmail_connection.generation+1,error_code=NULL RETURNING id",
                    (uuid4(), user["id"], identity.subject, identity.email, encrypted),
                ).fetchone()
                assert row is not None
                conn.execute(
                    "UPDATE feedback_job SET state='cancelled',lease_token=NULL "
                    "WHERE connection_id=%s AND state IN ('queued','running')",
                    (row["id"],),
                )
        except Exception:
            outcome = "failed"
    response = RedirectResponse("/feedback?gmail=" + outcome, status_code=303)
    response.headers["Cache-Control"] = "no-store"
    return response


@router.patch("/{connection_id}", operation_id="configureGmailCollection")
def configure(
    connection_id: UUID, payload: Filter, user: UserDep, conn: ConnDep, checked: Mutation
) -> dict[str, str]:
    with conn.transaction():
        row = owned(conn, connection_id, user)
        if row["state"] != "active":
            fail(409, "Gmail을 다시 연결하세요.")
        conn.execute(
            "UPDATE gmail_connection SET query=%s,automatic=%s,history_id=NULL,"
            "generation=generation+1,next_sync_at=now(),error_code=NULL WHERE id=%s",
            (payload.query, payload.automatic, connection_id),
        )
        conn.execute(
            "UPDATE feedback_job SET state='cancelled',lease_token=NULL "
            "WHERE connection_id=%s AND state IN ('queued','running')",
            (connection_id,),
        )
    return {"status": "saved"}


@router.post("/{connection_id}/sync", operation_id="syncGmail", status_code=202)
def sync(connection_id: UUID, user: UserDep, conn: ConnDep, checked: Mutation) -> dict[str, Any]:
    with conn.transaction():
        row = owned(conn, connection_id, user)
        if row["state"] != "active":
            fail(409, "Gmail을 다시 연결하세요.")
        return jobs.public(jobs.enqueue(conn, user["id"], "sync", connection_id, row["generation"]))


@router.delete("/{connection_id}", operation_id="disconnectGmail")
def disconnect(
    connection_id: UUID, user: UserDep, conn: ConnDep, settings: SettingsDep, checked: Mutation
) -> dict[str, Any]:
    with conn.transaction():
        conn.execute("SELECT id FROM app_user WHERE id=%s FOR UPDATE", (user["id"],))
        row = owned(conn, connection_id, user)
        conn.execute("DELETE FROM gmail_oauth WHERE owner_id=%s", (user["id"],))
        conn.execute(
            "UPDATE gmail_connection SET state='disconnected',encrypted_token=NULL,"
            "generation=generation+1,automatic=false WHERE id=%s",
            (connection_id,),
        )
        conn.execute(
            "UPDATE feedback_job SET state='cancelled',lease_token=NULL "
            "WHERE connection_id=%s AND state IN ('queued','running')",
            (connection_id,),
        )
    revoked = gmail.revoke(settings, row["encrypted_token"]) if row["encrypted_token"] else True
    return {"state": "disconnected", "google_revoked": revoked}
