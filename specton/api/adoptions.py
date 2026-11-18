"""Review sealed candidates and append a compare-and-swap implementation baseline decision."""

from datetime import UTC, datetime
from itertools import pairwise
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4
from zipfile import BadZipFile

from fastapi import APIRouter
from psycopg.types.json import Jsonb
from pydantic import StringConstraints

from specton.api.auth import Mutation, UserDep
from specton.api.deps import ConnDep, SettingsDep
from specton.api.implementations import owned
from specton.api.projects import own
from specton.api.specifications import fail, load, reference, view
from specton.contracts.base import Contract
from specton.contracts.specification import BaselineReference, Sha256, SpecBundle
from specton.implementation.comparison import (
    archive,
    digest,
    evidence,
    file_changes,
    semantic_changes,
)

router = APIRouter(prefix="/api/v1/projects", tags=["adoptions"])


class AdoptionRequest(Contract):
    implementation_id: UUID
    verification_id: UUID
    expected_current_id: UUID | None
    comparison_hash: Sha256
    request_key: UUID
    rationale: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=10, max_length=2000)
    ]
    acknowledge_unverified_acceptance: Literal[True]


def event(row: dict[str, Any]) -> dict[str, Any]:
    record = row["record"]
    if digest(record) != row["record_hash"]:
        fail(422, "채택 이력 해시가 일치하지 않습니다.")
    for key in (
        "id",
        "project_id",
        "implementation_id",
        "verification_id",
        "created_by",
        "previous_id",
    ):
        if record[key] != (str(row[key]) if row[key] is not None else None):
            fail(422, "채택 이력 연결이 일치하지 않습니다.")
    if record["sequence"] != row["sequence"]:
        fail(422, "채택 순서가 일치하지 않습니다.")
    return {**record, "record_hash": row["record_hash"]}


def latest(conn: ConnDep, project_id: UUID) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM implementation_adoption WHERE project_id=%s ORDER BY sequence DESC LIMIT 1",
        (project_id,),
    ).fetchone()
    return event(row) if row else None


def project_source(
    conn: ConnDep, project_id: UUID, source_id: UUID, user: UserDep
) -> dict[str, Any]:
    row = owned(conn, source_id, user)
    if (
        conn.execute(
            "SELECT 1 FROM spec_document d JOIN design_baseline b ON b.id=d.baseline_id WHERE "
            "d.id=%s AND b.project_id=%s",
            (row["spec_id"], project_id),
        ).fetchone()
        is None
    ):
        fail(404, "프로젝트의 구현 후보가 아닙니다.")
    return row


def source_info(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: str(row[key]) if key in ("id", "spec_id") else row[key]
        for key in ("id", "spec_id", "spec_version", "spec_hash", "source_hash", "template_version")
    }


def compare(
    conn: ConnDep,
    project_id: UUID,
    candidate_id: UUID,
    user: UserDep,
    settings: SettingsDep,
    base_id: UUID | None = None,
) -> dict[str, Any]:
    current = latest(conn, project_id)
    current_id = UUID(current["implementation_id"]) if current else None
    base_id = base_id or current_id
    target = project_source(conn, project_id, candidate_id, user)
    base, version = load(conn, target["spec_id"], user)
    current_spec = view(conn, target["spec_id"], version)
    baseline = reference(conn, base, user, settings)
    current_design = conn.execute(
        "SELECT id,version FROM design_baseline WHERE project_id=%s ORDER BY version DESC LIMIT 1",
        (project_id,),
    ).fetchone()
    assert current_design is not None
    verification = conn.execute(
        "SELECT * FROM implementation_verification WHERE implementation_id=%s ORDER BY "
        "created_at DESC,id DESC LIMIT 1 FOR SHARE",
        (candidate_id,),
    ).fetchone()
    reasons = []
    proof = None
    after, target_spec = archive(target)
    if verification is not None:
        try:
            proof = evidence(verification, target)
        except ValueError as exc:
            reasons.append(str(exc))
    else:
        reasons.append("검증 결과가 없습니다.")
    if (
        current_spec.bundle.spec_version != target["spec_version"]
        or current_spec.status != "approved"
        or current_spec.readiness.spec_hash != target["spec_hash"]
    ):
        reasons.append("최신 승인 명세의 후보가 아닙니다.")
    if baseline != current_spec.bundle.baseline or baseline != BaselineReference.model_validate(
        target_spec["baseline"]
    ):
        reasons.append("승인 설계 출처가 다릅니다.")
    if base["id"] != current_design["id"]:
        reasons.append("프로젝트의 최신 설계 기준 후보가 아닙니다.")
    if base_id != current_id:
        reasons.append("채택하려면 현재 채택 기준과 다시 비교하세요.")
    if (
        current
        and current["implementation_id"] == str(candidate_id)
        and proof
        and current["verification_id"] == proof["id"]
    ):
        reasons.append("이미 같은 소스와 검증 결과를 채택했습니다.")
    before: dict[str, bytes] = {}
    base_spec: dict[str, Any] = {}
    base_source = None
    if base_id:
        base_row = project_source(conn, project_id, base_id, user)
        before, base_spec = archive(base_row)
        base_source = source_info(base_row)
    from specton.implementation.consistency import check as check_consistency
    from specton.implementation.data_transfer import plan as transfer_plan

    artifact_consistency = (
        check_consistency(
            after,
            regenerate=target["template_version"]
            in {
                "executable-design-v8",
                "executable-design-v9",
                "executable-design-v10",
                "executable-design-v11",
            },
        )
        if target["template_version"]
        in {
            "executable-design-v7",
            "executable-design-v8",
            "executable-design-v9",
            "executable-design-v10",
            "executable-design-v11",
        }
        else {"status": "not_run", "documents": "legacy_template"}
    )
    migration = (
        transfer_plan(
            bytes(base_row["source_zip"]),
            base_row["source_hash"],
            bytes(target["source_zip"]),
            target["source_hash"],
        )
        if base_id
        else {"status": "no_baseline", "execution": "not_run", "reasons": []}
    )
    changes = file_changes(before, after)
    from specton.implementation.acceptance_evidence import case_results

    cases = case_results(
        SpecBundle.model_validate(target_spec),
        proof.get("executable_acceptance") if proof else None,
    )
    unverified = [
        c for c in target_spec["acceptance_cases"] if cases[c["id"]]["status"] != "passed"
    ]
    result = {
        "project_id": str(project_id),
        "current_adoption": current,
        "base": base_source,
        "candidate": source_info(target),
        "latest_design": {"id": str(current_design["id"]), "version": current_design["version"]},
        "latest_spec": {
            "version": current_spec.bundle.spec_version,
            "status": current_spec.status,
            "spec_hash": current_spec.readiness.spec_hash,
        },
        "verification": proof,
        "latest_verification_id": str(verification["id"]) if verification else None,
        "latest_verification_status": verification["status"] if verification else "not_run",
        "eligible": not reasons,
        "reasons": reasons,
        "files": changes,
        "semantic": semantic_changes(base_spec, target_spec),
        "ddl_changed": before.get("backend/approved.sql") != after.get("backend/approved.sql"),
        "artifact_consistency": artifact_consistency,
        "data_transfer": migration,
        "unverified_acceptance_count": len(unverified),
        "unverified_acceptance": [
            {"id": c["id"], "req_ids": c["req_ids"], "tier": c["tier"]} for c in unverified[:100]
        ],
        "scope": "implementation_baseline",
        "business_acceptance": "not_run",
    }
    return {**result, "comparison_hash": digest(result)}


@router.get("/{project_id}/candidates", operation_id="listImplementationCandidates")
def candidates(project_id: UUID, user: UserDep, conn: ConnDep) -> dict[str, Any]:
    with conn.transaction():
        own(conn, project_id, user)
        rows = conn.execute(
            "SELECT "
            "i.id,i.spec_id,i.spec_version,i.spec_hash,i.source_hash,i.template_version,"
            "i.created_at,"
            "b.version AS design_version,d.current_version AS latest_spec_version,v.id AS "
            "verification_id,"
            "v.status AS verification_status,v.report->>'browser_acceptance' AS browser_acceptance "
            "FROM implementation_source i JOIN spec_document d ON d.id=i.spec_id "
            "JOIN design_baseline b ON b.id=d.baseline_id LEFT JOIN LATERAL "
            "(SELECT * FROM implementation_verification WHERE implementation_id=i.id ORDER BY "
            "created_at DESC,id DESC LIMIT 1) v ON true "
            "WHERE b.project_id=%s ORDER BY i.created_at DESC,i.id DESC LIMIT 100",
            (project_id,),
        ).fetchall()
        return {"items": rows, "current_adoption": latest(conn, project_id)}


@router.get(
    "/{project_id}/candidates/{candidate_id}/comparison",
    operation_id="compareImplementationCandidate",
)
def comparison(
    project_id: UUID,
    candidate_id: UUID,
    user: UserDep,
    conn: ConnDep,
    settings: SettingsDep,
    base_id: UUID | None = None,
) -> dict[str, Any]:
    with conn.transaction():
        own(conn, project_id, user)
        try:
            return compare(conn, project_id, candidate_id, user, settings, base_id)
        except (ValueError, BadZipFile):
            fail(422, "후보 소스·명세·검증 근거를 확인할 수 없습니다.")


@router.get("/{project_id}/implementation-baseline", operation_id="getImplementationBaseline")
def baseline(project_id: UUID, user: UserDep, conn: ConnDep) -> dict[str, Any]:
    with conn.transaction():
        own(conn, project_id, user)
        rows = conn.execute(
            "SELECT * FROM implementation_adoption WHERE project_id=%s ORDER BY sequence DESC "
            "LIMIT 50",
            (project_id,),
        ).fetchall()
        records = [event(row) for row in rows]
        for newer, older in pairwise(records):
            if (
                newer["previous_id"] != older["id"]
                or newer["previous_record_hash"] != older["record_hash"]
            ):
                fail(422, "채택 이력 연결 해시가 다릅니다.")
        return {
            "current": records[0] if records else None,
            "history": [
                {
                    key: record[key]
                    for key in (
                        "id",
                        "sequence",
                        "previous_id",
                        "implementation_id",
                        "verification_id",
                        "created_by",
                        "created_at",
                        "rationale",
                        "record_hash",
                    )
                }
                for record in records
            ],
        }


@router.post("/{project_id}/adoptions", operation_id="adoptImplementationCandidate")
def adopt(
    project_id: UUID,
    payload: AdoptionRequest,
    user: UserDep,
    conn: ConnDep,
    settings: SettingsDep,
    checked: Mutation,
) -> dict[str, Any]:
    with conn.transaction():
        # Acquire the user before project/source locks, matching preview quota operations.
        conn.execute("SELECT id FROM app_user WHERE id=%s FOR KEY SHARE", (user["id"],))
        own(conn, project_id, user)
        request_hash = digest(payload.model_dump(mode="json"))
        previous_request = conn.execute(
            "SELECT * FROM implementation_adoption WHERE project_id=%s AND request_key=%s",
            (project_id, payload.request_key),
        ).fetchone()
        if previous_request:
            if previous_request["request_hash"] != request_hash:
                fail(409, "같은 요청 키의 내용이 다릅니다.")
            return event(previous_request)
        current = latest(conn, project_id)
        if (current["id"] if current else None) != (
            str(payload.expected_current_id) if payload.expected_current_id else None
        ):
            fail(409, "채택 기준이 바뀌었습니다. 다시 비교하세요.")
        try:
            review = compare(conn, project_id, payload.implementation_id, user, settings)
        except (ValueError, BadZipFile):
            fail(422, "후보 근거를 확인할 수 없습니다.")
        if review["comparison_hash"] != payload.comparison_hash:
            fail(409, "비교 이후 후보·검증·기준이 바뀌었습니다. 다시 비교하세요.")
        if not review["eligible"] or review["verification"]["id"] != str(payload.verification_id):
            fail(422, "채택 조건을 충족하지 않습니다. 최신 검증과 명세를 확인하세요.")
        feedback = conn.execute(
            "SELECT * FROM feedback_change WHERE implementation_id=%s FOR UPDATE",
            (payload.implementation_id,),
        ).fetchone()
        if feedback and (
            feedback["state"] != "validating"
            or str(feedback["base_adoption_id"]) != (current["id"] if current else None)
        ):
            fail(409, "변경 요청의 채택 기준이 바뀌었습니다. 최신 기준에서 다시 검토하세요.")
        now = datetime.now(UTC)
        aid = uuid4()
        sequence = current["sequence"] + 1 if current else 1
        record = {
            "id": str(aid),
            "project_id": str(project_id),
            "sequence": sequence,
            "previous_id": current["id"] if current else None,
            "previous_record_hash": current["record_hash"] if current else None,
            "implementation_id": str(payload.implementation_id),
            "verification_id": str(payload.verification_id),
            "created_by": str(user["id"]),
            "created_at": now.isoformat(),
            "rationale": payload.rationale,
            "acknowledge_unverified_acceptance": True,
            "scope": "implementation_baseline",
            "comparison_hash": payload.comparison_hash,
            "source": review["candidate"],
            "verification": review["verification"],
            "design": review["latest_design"],
            "semantic": review["semantic"],
            "ddl_changed": review["ddl_changed"],
            "artifact_consistency": review["artifact_consistency"],
            "data_transfer": review["data_transfer"],
            "unverified_acceptance_count": review["unverified_acceptance_count"],
            "business_acceptance": "not_run",
        }
        row = conn.execute(
            "INSERT INTO "
            "implementation_adoption(id,project_id,sequence,previous_id,implementation_id,"
            "verification_id,request_key,request_hash,record,record_hash,created_by,"
            "created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (
                aid,
                project_id,
                sequence,
                payload.expected_current_id,
                payload.implementation_id,
                payload.verification_id,
                payload.request_key,
                request_hash,
                Jsonb(record),
                digest(record),
                user["id"],
                now,
            ),
        ).fetchone()
        assert row is not None
        if feedback:
            conn.execute(
                "UPDATE feedback_change SET state='applied',version=version+1 WHERE id=%s",
                (feedback["id"],),
            )
            conn.execute(
                "INSERT INTO feedback_event(id,change_id,actor_id,action,target_hash,note) "
                "VALUES(%s,%s,%s,'adopted',%s,'검증 후보를 새 구현 기준으로 채택')",
                (uuid4(), feedback["id"], user["id"], row["record_hash"]),
            )
        return event(row)
