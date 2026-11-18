"""Owner-only preview control and bounded loopback RPC; never serve app JS on platform origin."""

import hashlib
import io
import json
import re
import zipfile
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter
from pydantic import Field

from specton.api.auth import Mutation, UserDep
from specton.api.deps import ConnDep, SettingsDep
from specton.api.implementations import owned
from specton.api.specifications import fail
from specton.contracts.base import Contract
from specton.implementation.jobs import public as verification_public

router = APIRouter(prefix="/api/v1", tags=["previews"])


class PreviewRequest(Contract):
    verification_id: UUID
    request_key: UUID


class PreviewRPC(Contract):
    method: Literal["GET", "POST", "PATCH"]
    path: str = Field(min_length=1, max_length=1024)
    body: str | None = Field(default=None, max_length=16384)
    command_key: UUID | None = None


def public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: row[key]
        for key in (
            "id",
            "implementation_id",
            "verification_id",
            "source_hash",
            "status",
            "created_at",
            "expires_at",
            "cancel_requested",
            "error_code",
        )
    }


def load(conn: ConnDep, preview_id: UUID, user: UserDep) -> tuple[dict[str, Any], dict[str, Any]]:
    row = conn.execute("SELECT * FROM implementation_preview WHERE id=%s", (preview_id,)).fetchone()
    if row is None:
        fail(404, "미리보기를 찾을 수 없습니다.")
    source = owned(conn, row["implementation_id"], user)
    return row, source


def ready(
    conn: ConnDep, preview_id: UUID, user: UserDep, settings: SettingsDep
) -> tuple[dict[str, Any], dict[str, Any]]:
    row, source = load(conn, preview_id, user)
    available = conn.execute(
        "SELECT expires_at>now() AS valid FROM implementation_preview WHERE id=%s", (preview_id,)
    ).fetchone()
    assert available is not None
    if row["status"] != "ready" or row["cancel_requested"] or not available["valid"]:
        fail(410, "미리보기가 준비되지 않았거나 만료·종료됐습니다.")
    if not settings.preview_worker_host or row["executor_host"] != settings.preview_worker_host:
        fail(503, "API와 같은 호스트의 미리보기 작업자 설정이 필요합니다.")
    if row["source_hash"] != source["source_hash"]:
        fail(422, "미리보기 소스가 일치하지 않습니다.")
    return row, source


@router.post("/implementations/{impl_id}/previews", operation_id="requestPreview")
def create(
    impl_id: UUID,
    payload: PreviewRequest,
    user: UserDep,
    conn: ConnDep,
    settings: SettingsDep,
    checked: Mutation,
) -> dict[str, Any]:
    if not settings.preview_worker_host:
        fail(503, "미리보기 작업자 호스트 설정이 필요합니다.")
    with conn.transaction():
        conn.execute("SELECT id FROM app_user WHERE id=%s FOR UPDATE", (user["id"],))
        source = owned(conn, impl_id, user)
        conn.execute("SELECT id FROM implementation_source WHERE id=%s FOR UPDATE", (impl_id,))
        verification = conn.execute(
            "SELECT * FROM implementation_verification WHERE id=%s AND implementation_id=%s",
            (payload.verification_id, impl_id),
        ).fetchone()
        if verification is None:
            fail(404, "검증 결과를 찾을 수 없습니다.")
        try:
            verification_public(verification)
        except ValueError:
            fail(422, "검증 결과 해시가 일치하지 않습니다.")
        if (
            verification["status"] != "smoke_passed"
            or verification["source_hash"] != source["source_hash"]
            or verification["report"].get("browser_acceptance") != "passed"
            or not verification["browser_image"]
            or verification["executor_host"] != settings.preview_worker_host
        ):
            fail(422, "같은 호스트에서 브라우저 검증까지 통과한 소스가 필요합니다.")
        previous = conn.execute(
            "SELECT * FROM implementation_preview WHERE implementation_id=%s AND request_key=%s",
            (impl_id, payload.request_key),
        ).fetchone()
        if previous:
            if previous["verification_id"] != payload.verification_id:
                fail(409, "요청 키의 검증 대상이 다릅니다.")
            return public(previous)
        if conn.execute(
            "SELECT 1 FROM implementation_preview WHERE implementation_id=%s AND status IN "
            "('queued','starting','ready','closing','recovering')",
            (impl_id,),
        ).fetchone():
            fail(409, "이 소스의 미리보기가 이미 활성 상태입니다.")
        quota = conn.execute(
            "SELECT count(*) AS count FROM implementation_preview WHERE requested_by=%s "
            "AND status IN ('queued','starting','ready','closing','recovering')",
            (user["id"],),
        ).fetchone()
        assert quota is not None
        if quota["count"] >= 2:
            fail(429, "동시에 유지할 수 있는 미리보기는 계정당 2개입니다.")
        row = conn.execute(
            "INSERT INTO "
            "implementation_preview(id,implementation_id,verification_id,requested_by,request_key,source_hash,resource_key,expires_at,executor_host)"
            " VALUES(%s,%s,%s,%s,%s,%s,%s,now()+interval '15 minutes',%s) RETURNING *",
            (
                uuid4(),
                impl_id,
                payload.verification_id,
                user["id"],
                payload.request_key,
                source["source_hash"],
                uuid4(),
                settings.preview_worker_host,
            ),
        ).fetchone()
        assert row is not None
        return public(row)


@router.get("/implementations/{impl_id}/previews", operation_id="listPreviews")
def listing(impl_id: UUID, user: UserDep, conn: ConnDep) -> list[dict[str, Any]]:
    owned(conn, impl_id, user)
    return [
        public(row)
        for row in conn.execute(
            "SELECT * FROM implementation_preview WHERE implementation_id=%s ORDER BY "
            "created_at DESC LIMIT 20",
            (impl_id,),
        ).fetchall()
    ]


@router.post("/previews/{preview_id}/close", operation_id="closePreview")
def close(preview_id: UUID, user: UserDep, conn: ConnDep, checked: Mutation) -> dict[str, Any]:
    with conn.transaction():
        load(conn, preview_id, user)
        row = conn.execute(
            "UPDATE implementation_preview SET cancel_requested=true, status=CASE WHEN "
            "status='queued' THEN 'closed' WHEN status='ready' THEN 'closing' ELSE status "
            "END, lease_until=CASE WHEN status='ready' THEN now() ELSE lease_until END "
            "WHERE id=%s RETURNING *",
            (preview_id,),
        ).fetchone()
        assert row is not None
        return public(row)


@router.get("/previews/{preview_id}/document", operation_id="getPreviewDocument")
def document(
    preview_id: UUID, user: UserDep, conn: ConnDep, settings: SettingsDep
) -> dict[str, str]:
    row, _ = ready(conn, preview_id, user, settings)
    if not row["html"] or hashlib.sha256(row["html"].encode()).hexdigest() != row["html_hash"]:
        fail(422, "미리보기 문서 해시가 일치하지 않습니다.")
    return {"html": row["html"], "sha256": row["html_hash"]}


@router.post("/previews/{preview_id}/rpc", operation_id="previewRPC")
def rpc(
    preview_id: UUID,
    payload: PreviewRPC,
    user: UserDep,
    conn: ConnDep,
    settings: SettingsDep,
    checked: Mutation,
) -> dict[str, Any]:
    row, source = ready(conn, preview_id, user, settings)
    path = urlsplit(payload.path)
    if path.scheme or path.netloc or path.fragment or not path.path.startswith("/api/"):
        fail(422, "미리보기 API 경로가 아닙니다.")
    with zipfile.ZipFile(io.BytesIO(bytes(source["source_zip"]))) as archive:
        contract = json.loads(archive.read("backend/contract.json"))
    operations = (
        contract["operations"]
        + (contract["inventory"]["operations"] if contract.get("inventory") else [])
        + (contract["commerce"]["operations"] if contract.get("commerce") else [])
        + (contract["domain"]["operations"] if contract.get("domain") else [])
    )
    if not any(
        op["method"] == payload.method
        and re.fullmatch(
            re.escape("/api" + op["path"]).replace(r"\{key\}", r"[A-Za-z0-9_-]+"), path.path
        )
        for op in operations
    ):
        fail(422, "승인된 미리보기 API가 아닙니다.")
    if payload.body is not None:
        try:
            json.loads(payload.body)
        except ValueError:
            fail(422, "JSON 본문이 필요합니다.")
    try:
        with (
            httpx.Client(timeout=5, trust_env=False, follow_redirects=False) as client,
            client.stream(
                payload.method,
                f"http://127.0.0.1:{row['app_port']}" + payload.path[4:],
                headers={
                    "Authorization": "Bearer " + row["access_token"],
                    "Content-Type": "application/json",
                    "Idempotency-Key": str(payload.command_key or uuid4()),
                },
                content=payload.body,
            ) as response,
        ):
            chunks = []
            size = 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > 256 * 1024:
                    fail(502, "미리보기 응답 크기 초과")
                chunks.append(chunk)
            body = b"".join(chunks).decode()
            json.loads(body)
            if not 200 <= response.status_code < 500:
                fail(502, "미리보기 응답 오류")
            return {"status": response.status_code, "body": body}
    except (httpx.HTTPError, ValueError, UnicodeError):
        fail(502, "미리보기 서버에 연결할 수 없습니다.")
