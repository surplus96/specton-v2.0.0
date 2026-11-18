"""승인 명세를 고정 소스 묶음으로 생성한다. API 프로세스에서는 코드를 실행하지 않는다."""

import hashlib
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Response

from specton.api.auth import Mutation, UserDep
from specton.api.deps import ConnDep, SettingsDep
from specton.api.specifications import Expected, expected, fail, load, reference, view
from specton.contracts import DesignState
from specton.contracts.specification import Sha256
from specton.implementation.compiler import Unsupported
from specton.implementation.package import TEMPLATE_VERSION, generate

router = APIRouter(prefix="/api/v1", tags=["implementations"])


def summary(row: dict[str, Any], conn: ConnDep) -> dict[str, Any]:
    latest = conn.execute(
        "SELECT * FROM implementation_verification WHERE implementation_id=%s "
        "ORDER BY created_at DESC,id DESC LIMIT 1",
        (row["id"],),
    ).fetchone()
    if latest is not None:
        from specton.implementation.jobs import public

        try:
            public(latest)
        except ValueError:
            fail(422, "저장된 검증 결과 해시가 일치하지 않습니다.")
    return {
        key: row[key]
        for key in ("id", "spec_id", "spec_version", "spec_hash", "source_hash", "template_version")
    } | {
        "status": "source_ready",
        "validation_status": latest["status"] if latest else "not_run",
        "verification_id": latest["id"] if latest else None,
    }


@router.post("/specs/{spec_id}/implementations", operation_id="generateImplementation")
def create(
    spec_id: UUID,
    payload: Expected,
    user: UserDep,
    conn: ConnDep,
    settings: SettingsDep,
    checked: Mutation,
) -> dict[str, Any]:
    with conn.transaction():
        base, version = load(conn, spec_id, user)
        current = view(conn, spec_id, version)
        expected(current, payload)
        if current.status != "approved":
            fail(422, "최신 실행 명세를 먼저 승인해야 합니다.")
        if current.bundle.baseline != reference(conn, base, user, settings):
            fail(422, "승인 설계의 출처가 일치하지 않습니다.")
        snapshot = conn.execute(
            "SELECT normalized_model FROM model_snapshot WHERE run_id=%s AND revision=%s",
            (base["run_id"], base["revision"]),
        ).fetchone()
        assert snapshot is not None
        state = DesignState.model_validate(
            {**snapshot["normalized_model"], "run_id": str(base["run_id"])}
        )
        artifacts = read_artifacts(conn, base, settings)
        try:
            source = generate(current.bundle, state, artifacts)
        except (Unsupported, ValueError) as exc:
            fail(422, str(exc))
        if len(source) > 10 * 1024 * 1024:
            fail(422, "생성 소스 크기 한도를 초과했습니다.")
        digest = hashlib.sha256(source).hexdigest()
        row = conn.execute(
            "INSERT INTO implementation_source(id,spec_id,spec_version,spec_hash,"
            "template_version,source_hash,source_zip,created_by) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT(spec_id,spec_version,template_version) DO NOTHING RETURNING *",
            (
                uuid4(),
                spec_id,
                version,
                payload.spec_hash,
                TEMPLATE_VERSION,
                digest,
                source,
                user["id"],
            ),
        ).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT * FROM implementation_source WHERE spec_id=%s AND spec_version=%s "
                "AND template_version=%s",
                (spec_id, version, TEMPLATE_VERSION),
            ).fetchone()
        assert row is not None
        if (
            row["source_hash"] != digest
            or hashlib.sha256(bytes(row["source_zip"])).hexdigest() != digest
        ):
            fail(409, "같은 템플릿 버전의 생성 결과가 변경됐습니다. 템플릿 버전을 갱신하세요.")
        return summary(row, conn)


def owned(conn: ConnDep, impl_id: UUID, user: UserDep) -> dict[str, Any]:
    row = conn.execute(
        "SELECT i.* FROM implementation_source i JOIN spec_document d ON d.id=i.spec_id "
        "JOIN design_baseline b ON b.id=d.baseline_id JOIN project p ON p.id=b.project_id "
        "WHERE i.id=%s AND p.owner_id=%s",
        (impl_id, user["id"]),
    ).fetchone()
    if row is None:
        fail(404, "생성 소스를 찾을 수 없습니다.")
    assert row is not None
    if hashlib.sha256(bytes(row["source_zip"])).hexdigest() != row["source_hash"]:
        fail(422, "저장된 소스 해시가 일치하지 않습니다.")
    return row


@router.get("/implementations/{impl_id}", operation_id="getImplementation")
def get(impl_id: UUID, user: UserDep, conn: ConnDep) -> dict[str, Any]:
    return summary(owned(conn, impl_id, user), conn)


@router.get("/implementations/{impl_id}/source", operation_id="downloadImplementation")
def download(impl_id: UUID, user: UserDep, conn: ConnDep) -> Response:
    row = owned(conn, impl_id, user)
    return Response(
        bytes(row["source_zip"]),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="specton-{impl_id}.zip"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/specs/{spec_id}/storage-catalog", operation_id="getStorageCatalog")
def catalog(spec_id: UUID, user: UserDep, conn: ConnDep, settings: SettingsDep) -> dict[str, Any]:
    with conn.transaction():
        base, _ = load(conn, spec_id, user)
        reference(conn, base, user, settings)
        row = conn.execute(
            "SELECT normalized_model FROM model_snapshot WHERE run_id=%s AND revision=%s",
            (base["run_id"], base["revision"]),
        ).fetchone()
        assert row is not None
        state = DesignState.model_validate(
            {**row["normalized_model"], "run_id": str(base["run_id"])}
        )
        return {
            "baseline_id": base["id"],
            "normalized": state.normalized.model_dump(mode="json") if state.normalized else None,
            "supported_actions": ["insert", "get", "list", "update"],
            "supported_types": ["string", "integer", "boolean", "decimal"],
        }


# No public result-upload endpoint: only the trusted worker writes evidence.
class VerificationRequest(Expected):
    source_hash: Sha256
    request_key: UUID


@router.post("/implementations/{impl_id}/verifications", operation_id="requestVerification")
def request_verification(
    impl_id: UUID,
    payload: VerificationRequest,
    user: UserDep,
    conn: ConnDep,
    settings: SettingsDep,
    checked: Mutation,
) -> dict[str, Any]:
    from specton.implementation.jobs import public

    with conn.transaction():
        row = owned(conn, impl_id, user)
        if payload.source_hash != row["source_hash"]:
            fail(409, "소스 해시가 다릅니다.")
        base, version = load(conn, row["spec_id"], user)
        current = view(conn, row["spec_id"], version)
        expected(current, payload)
        if (
            current.status != "approved"
            or version != row["spec_version"]
            or current.readiness.spec_hash != row["spec_hash"]
        ):
            fail(409, "현재 승인 명세의 소스만 검증 요청할 수 있습니다.")
        if current.bundle.baseline != reference(conn, base, user, settings):
            fail(422, "승인 설계 출처가 일치하지 않습니다.")
        # Match source generation lock order: spec document, then source.
        conn.execute("SELECT id FROM implementation_source WHERE id=%s FOR UPDATE", (impl_id,))
        previous = conn.execute(
            "SELECT * FROM implementation_verification WHERE implementation_id=%s "
            "AND request_key=%s",
            (impl_id, payload.request_key),
        ).fetchone()
        if previous is not None:
            return public(previous)
        active = conn.execute(
            "SELECT * FROM implementation_verification WHERE implementation_id=%s "
            "AND status IN ('queued','running','cancelling','recovering')",
            (impl_id,),
        ).fetchone()
        if active is not None:
            fail(409, "이 소스의 검증 작업이 이미 진행 중입니다.")
        job = conn.execute(
            "INSERT INTO implementation_verification(id,implementation_id,requested_by,request_key,"
            "source_hash,spec_hash,resource_key) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (
                uuid4(),
                impl_id,
                user["id"],
                payload.request_key,
                row["source_hash"],
                row["spec_hash"],
                uuid4(),
            ),
        ).fetchone()
        assert job is not None
        return public(job)


@router.get("/implementations/{impl_id}/verifications", operation_id="listVerifications")
def verifications(impl_id: UUID, user: UserDep, conn: ConnDep) -> list[dict[str, Any]]:
    from specton.implementation.jobs import public

    owned(conn, impl_id, user)
    try:
        return [
            public(row)
            for row in conn.execute(
                "SELECT * FROM implementation_verification WHERE implementation_id=%s "
                "ORDER BY created_at DESC, id DESC LIMIT 50",
                (impl_id,),
            ).fetchall()
        ]
    except ValueError:
        fail(422, "저장된 검증 결과 해시가 일치하지 않습니다.")


@router.post(
    "/implementations/{impl_id}/verifications/{job_id}/cancel", operation_id="cancelVerification"
)
def cancel_verification(
    impl_id: UUID,
    job_id: UUID,
    user: UserDep,
    conn: ConnDep,
    checked: Mutation,
) -> dict[str, Any]:
    from specton.implementation.jobs import public

    with conn.transaction():
        owned(conn, impl_id, user)
        row = conn.execute(
            "SELECT * FROM implementation_verification WHERE id=%s "
            "AND implementation_id=%s FOR UPDATE",
            (job_id, impl_id),
        ).fetchone()
        if row is None:
            fail(404, "검증 작업을 찾을 수 없습니다.")
        if row["status"] in ("queued", "running", "cancelling", "recovering"):
            row = conn.execute(
                "UPDATE implementation_verification SET cancel_requested=true, "
                "status=CASE WHEN status='queued' THEN 'cancelled' "
                "WHEN status='running' THEN 'cancelling' ELSE status END, "
                "finished_at=CASE WHEN status='queued' THEN now() ELSE finished_at END "
                "WHERE id=%s RETURNING *",
                (job_id,),
            ).fetchone()
        assert row is not None
        return public(row)


def read_artifacts(conn: ConnDep, base: dict[str, Any], settings: SettingsDep) -> dict[str, bytes]:
    rows = conn.execute(
        "SELECT kind,file_format,storage_ref FROM artifact a "
        "JOIN model_snapshot s USING(snapshot_id) "
        "WHERE s.run_id=%s AND s.revision=%s",
        (base["run_id"], base["revision"]),
    ).fetchall()
    artifacts = {}
    root = settings.storage_dir.resolve(strict=True)
    for artifact_row in rows:
        key = f"{artifact_row['kind']}.{artifact_row['file_format']}"
        if key not in base["artifact_hashes"]:
            continue
        path = root / artifact_row["storage_ref"]
        try:
            path.resolve(strict=True).relative_to(root)
            if any(p.is_symlink() for p in (path, *path.parents)):
                fail(422, "산출물 링크 경로를 사용할 수 없습니다.")
            artifacts[key] = path.read_bytes()
        except (OSError, ValueError):
            fail(422, "승인 산출물을 읽을 수 없습니다.")
    return artifacts


@router.get("/specs/{spec_id}/design", operation_id="downloadExecutableDesign")
def download_design(spec_id: UUID, user: UserDep, conn: ConnDep, settings: SettingsDep) -> Response:
    from specton.specification.documents import archive, revised_files

    with conn.transaction():
        base, version = load(conn, spec_id, user)
        current = view(conn, spec_id, version)
        if current.status != "approved":
            fail(422, "실행 명세 승인 후 후속 설계 산출물을 내려받을 수 있습니다.")
        reference(conn, base, user, settings)
        originals = read_artifacts(conn, base, settings)
        try:
            data = archive(revised_files(current.bundle, originals))
        except ValueError as exc:
            fail(422, str(exc))
        return Response(
            data,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="design-{spec_id}-v{version}.zip"',
                "Cache-Control": "no-store",
            },
        )
