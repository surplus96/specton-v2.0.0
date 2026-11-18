"""Owned, version-specific handoff review. No approvals, jobs or customer data writes."""

from typing import Annotated, Any
from uuid import UUID
from zipfile import BadZipFile

from fastapi import APIRouter, Query, Response

from specton.api.auth import UserDep
from specton.api.deps import ConnDep, SettingsDep
from specton.api.specifications import fail, load, reference, view
from specton.contracts import DesignState
from specton.contracts.specification import SpecBundle
from specton.implementation.acceptance_evidence import case_results
from specton.implementation.comparison import archive, evidence
from specton.implementation.compiler import compile_contract
from specton.implementation.consistency import check
from specton.implementation.package import TEMPLATE_VERSION
from specton.specification.handoff import (
    HandoffGate,
    HandoffReport,
    SourceAssessment,
    assess_handoff,
)

router = APIRouter(prefix="/api/v1", tags=["handoff"])


def source_assessment(conn: ConnDep, bundle: SpecBundle, digest: str) -> SourceAssessment | None:
    source = conn.execute(
        "SELECT * FROM implementation_source WHERE spec_id=%s AND spec_version=%s AND "
        "spec_hash=%s ORDER BY (template_version=%s) DESC,created_at DESC,id DESC LIMIT 1",
        (bundle.spec_id, bundle.spec_version, digest, TEMPLATE_VERSION),
    ).fetchone()
    if source is None:
        return None
    integrity = HandoffGate(
        id="source", name="명세·설계·생성 소스 일치", status="blocked", detail="검사 전"
    )
    proof_gate = HandoffGate(
        id="verification",
        name="격리 실행·브라우저 검증",
        status="not_run",
        detail="동일 소스의 검증 결과가 없습니다.",
    )
    passed: tuple[str, ...] = ()
    verification: dict[str, Any] | None = None
    try:
        files, saved = archive(source)
        if SpecBundle.model_validate(saved) != bundle:
            raise ValueError("생성 소스와 저장 명세가 다릅니다.")
        if source["template_version"] != TEMPLATE_VERSION:
            raise ValueError("최신 고객 앱 납품 템플릿으로 생성한 후보가 필요합니다.")
        check(files)
        integrity = integrity.evolve(
            status="passed", detail="소스 해시·고정 파일·명세·파생 설계 일치"
        )
    except (ValueError, BadZipFile, KeyError):
        integrity = integrity.evolve(
            detail="소스 무결성·명세 일치 또는 최신 납품 템플릿 검사를 통과하지 못했습니다."
        )
    if integrity.status == "passed":
        verification = conn.execute(
            "SELECT * FROM implementation_verification WHERE implementation_id=%s "
            "ORDER BY created_at DESC,id DESC LIMIT 1",
            (source["id"],),
        ).fetchone()
        if verification:
            try:
                proof = evidence(verification, source)
                results = case_results(bundle, proof.get("executable_acceptance"))
                passed = tuple(k for k, v in results.items() if v["status"] == "passed")
                proof_gate = proof_gate.evolve(
                    status="passed",
                    detail="동일 소스의 플랫폼 API·브라우저·정리 근거 확인. 업무 전체 인수와 별도",
                )
            except (ValueError, BadZipFile, KeyError):
                proof_gate = proof_gate.evolve(
                    status="blocked",
                    detail="최신 검증이 미완료·실패하거나 근거 검사를 통과하지 못했습니다.",
                )
    return SourceAssessment(
        implementation_id=source["id"],
        source_hash=source["source_hash"],
        template_version=source["template_version"],
        verification_id=verification["id"] if verification else None,
        integrity=integrity,
        verification=proof_gate,
        passed_case_ids=passed,
    )


@router.get("/specs/{spec_id}/handoff", operation_id="assessHandoffReadiness")
def handoff(
    spec_id: UUID,
    user: UserDep,
    conn: ConnDep,
    settings: SettingsDep,
    response: Response,
    version: Annotated[int | None, Query(ge=1)] = None,
) -> HandoffReport:
    response.headers["Cache-Control"] = "no-store"
    with conn.transaction():
        base, latest_version = load(conn, spec_id, user)
        current = view(conn, spec_id, version if version is not None else latest_version)
        bundle = current.bundle
        if bundle.baseline != reference(conn, base, user, settings):
            fail(422, "승인 설계 출처와 명세가 일치하지 않습니다.")
        latest_base = conn.execute(
            "SELECT id FROM design_baseline WHERE project_id=%s ORDER BY version DESC LIMIT 1",
            (base["project_id"],),
        ).fetchone()
        snapshot = conn.execute(
            "SELECT normalized_model FROM model_snapshot WHERE run_id=%s AND revision=%s",
            (base["run_id"], base["revision"]),
        ).fetchone()
        if snapshot is None:
            fail(422, "승인 설계 모델이 없습니다.")
        state = DesignState.model_validate(
            {**snapshot["normalized_model"], "run_id": str(base["run_id"])}
        )
        generator_error = None
        try:
            compile_contract(bundle, state)
        except ValueError as exc:
            generator_error = str(exc)
        return assess_handoff(
            bundle,
            current.readiness,
            approved=current.status == "approved",
            is_latest=bundle.spec_version == latest_version
            and bool(latest_base and latest_base["id"] == base["id"]),
            generator_error=generator_error,
            source=source_assessment(conn, bundle, current.readiness.spec_hash),
        )
