"""승인 설계에서 실행 명세 작성·버전 보존·별도 승인까지 연결한다."""

from typing import Any, Literal, NoReturn
from uuid import UUID, uuid4

from fastapi import APIRouter
from psycopg.types.json import Jsonb
from pydantic import Field

from specton.api.auth import Mutation, UserDep
from specton.api.deps import ConnDep, SettingsDep
from specton.api.errors import ApiError
from specton.api.projects import own
from specton.contracts import DesignState, ErrorCode
from specton.contracts.base import Contract
from specton.contracts.specification import BaselineReference, PositiveVersion, Sha256, SpecBundle
from specton.specification.approval import ApprovalMismatch, verify_approved_files
from specton.specification.capabilities import ScopeReport, ScopeRequirement, assess
from specton.specification.draft import draft
from specton.specification.readiness import (
    ReadinessIssue,
    ReadinessReport,
    assess_readiness,
    spec_hash,
)

router = APIRouter(prefix="/api/v1", tags=["specifications"])
GROUPS = (
    "requirements",
    "roles",
    "entities",
    "use_cases",
    "invariants",
    "apis",
    "screens",
    "acceptance_cases",
    "questions",
)


class Expected(Contract):
    expected_version: PositiveVersion
    spec_hash: Sha256


class Edit(Expected):
    bundle: SpecBundle


class SpecView(Contract):
    bundle: SpecBundle
    status: Literal["needs_input", "ready_for_review", "approved"]
    readiness: ReadinessReport
    approved_by: UUID | None
    versions: tuple[int, ...]


def fail(status: int, message: str) -> NoReturn:
    raise ApiError(status, ErrorCode.INVALID_REQUEST, message)


def baseline_row(conn: ConnDep, baseline_id: UUID, user: UserDep) -> dict[str, Any]:
    row = conn.execute(
        "SELECT b.* FROM design_baseline b JOIN project p ON p.id=b.project_id "
        "WHERE b.id=%s AND p.owner_id=%s",
        (baseline_id, user["id"]),
    ).fetchone()
    if row is None:
        fail(404, "기준 버전을 찾을 수 없습니다.")
    assert row is not None
    own(conn, row["project_id"], user)
    return row


def reference(
    conn: ConnDep, row: dict[str, Any], user: UserDep, settings: SettingsDep
) -> BaselineReference:
    run = conn.execute("SELECT pack FROM run WHERE run_id=%s", (row["run_id"],)).fetchone()
    if run is None:
        fail(422, "승인된 원본 실행을 찾을 수 없습니다.")
    try:
        verified = verify_approved_files(
            conn,
            run_id=row["run_id"],
            revision=row["revision"],
            owner_ref=f"user:{user['id']}",
            storage_dir=settings.storage_dir,
        )
    except ApprovalMismatch:
        fail(422, "승인 설계 파일 또는 검증 근거가 변경됐습니다.")
    if (
        verified.artifact_hashes != row["artifact_hashes"]
        or verified.approval_id != row["approval_id"]
        or verified.model_hash != row["model_hash"]
    ):
        fail(422, "고정한 승인 기준과 현재 근거가 일치하지 않습니다.")
    return BaselineReference(
        project_id=row["project_id"],
        baseline_id=row["id"],
        source_run_id=row["run_id"],
        source_revision=row["revision"],
        model_hash=row["model_hash"],
        approval_id=row["approval_id"],
        manifest_hash=verified.artifact_hashes["manifest.json"],
        artifacts=tuple(
            {"kind": k.split(".")[0], "file_format": k.split(".")[1], "sha256": v}
            for k, v in sorted(verified.artifact_hashes.items())
            if k != "manifest.json"
        ),
    )


def report(bundle: SpecBundle) -> ReadinessReport:
    result = assess_readiness(bundle)
    if any(r.id == "ROLE-unconfirmed" for r in bundle.roles):
        result = result.evolve(
            ready_for_review=False,
            issues=(
                *result.issues,
                ReadinessIssue(
                    code="UNCONFIRMED_ROLE",
                    target="ROLE-unconfirmed",
                    message="실제 업무 역할을 정의하세요.",
                ),
            ),
        )
    return result


def objects(bundle: SpecBundle) -> dict[str, tuple[str, str | None]]:
    return {
        item.id: (group, getattr(item, "legacy_id", None))
        for group in GROUPS
        for item in getattr(bundle, group)
    }


def record(conn: ConnDep, bundle: SpecBundle, user: UserDep) -> None:
    items = objects(bundle)
    rows = conn.execute("SELECT * FROM spec_object WHERE spec_id=%s", (bundle.spec_id,)).fetchall()
    for old in rows:
        if old["stable_id"] in items:
            if old["retired_version"] is not None or items[old["stable_id"]] != (
                old["kind"],
                old["source_key"],
            ):
                fail(422, "삭제한 ID를 재사용하거나 기존 ID의 종류·출처를 바꿀 수 없습니다.")
        elif old["retired_version"] is None:
            conn.execute(
                "UPDATE spec_object SET retired_version=%s WHERE spec_id=%s AND stable_id=%s",
                (bundle.spec_version, bundle.spec_id, old["stable_id"]),
            )
    for key, (kind, source) in items.items():
        conn.execute(
            "INSERT INTO spec_object(spec_id,stable_id,kind,source_key) VALUES(%s,%s,%s,%s) "
            "ON CONFLICT DO NOTHING",
            (bundle.spec_id, key, kind, source),
        )
    conn.execute(
        "INSERT INTO spec_revision(spec_id,version,payload,spec_hash,created_by) "
        "VALUES(%s,%s,%s,%s,%s)",
        (
            bundle.spec_id,
            bundle.spec_version,
            Jsonb(bundle.model_dump(mode="json")),
            spec_hash(bundle),
            user["id"],
        ),
    )


def load(conn: ConnDep, spec_id: UUID, user: UserDep) -> tuple[dict[str, Any], int]:
    row = conn.execute(
        "SELECT d.baseline_id FROM spec_document d JOIN design_baseline b ON b.id=d.baseline_id "
        "JOIN project p ON p.id=b.project_id WHERE d.id=%s AND p.owner_id=%s",
        (spec_id, user["id"]),
    ).fetchone()
    if row is None:
        fail(404, "실행 명세를 찾을 수 없습니다.")
    assert row is not None
    base = baseline_row(conn, row["baseline_id"], user)
    current = conn.execute(
        "SELECT current_version FROM spec_document WHERE id=%s FOR UPDATE", (spec_id,)
    ).fetchone()
    assert current is not None
    return base, current["current_version"]


def view(conn: ConnDep, spec_id: UUID, version: int) -> SpecView:
    row = conn.execute(
        "SELECT * FROM spec_revision WHERE spec_id=%s AND version=%s", (spec_id, version)
    ).fetchone()
    if row is None:
        fail(404, "명세 버전을 찾을 수 없습니다.")
    assert row is not None
    bundle = SpecBundle.model_validate(row["payload"])
    if spec_hash(bundle) != row["spec_hash"]:
        fail(422, "저장 명세 해시가 일치하지 않습니다.")
    approval = conn.execute(
        "SELECT actor_id,spec_hash FROM spec_approval WHERE spec_id=%s AND version=%s",
        (spec_id, version),
    ).fetchone()
    if approval and approval["spec_hash"] != row["spec_hash"]:
        fail(422, "명세 승인 해시가 일치하지 않습니다.")
    readiness = report(bundle)
    versions = conn.execute(
        "SELECT version FROM spec_revision WHERE spec_id=%s ORDER BY version", (spec_id,)
    ).fetchall()
    return SpecView(
        bundle=bundle,
        readiness=readiness,
        status="approved"
        if approval
        else "ready_for_review"
        if readiness.ready_for_review
        else "needs_input",
        approved_by=approval["actor_id"] if approval else None,
        versions=tuple(r["version"] for r in versions),
    )


@router.post(
    "/baselines/{baseline_id}/specs", operation_id="createSpecification", response_model=SpecView
)
def create(
    baseline_id: UUID, user: UserDep, conn: ConnDep, settings: SettingsDep, checked: Mutation
) -> SpecView:
    with conn.transaction():
        base = baseline_row(conn, baseline_id, user)
        ref = reference(conn, base, user, settings)
        existing = conn.execute(
            "SELECT id,current_version FROM spec_document WHERE baseline_id=%s", (baseline_id,)
        ).fetchone()
        if existing:
            return view(conn, existing["id"], existing["current_version"])
        snapshot = conn.execute(
            "SELECT normalized_model FROM model_snapshot WHERE run_id=%s AND revision=%s",
            (base["run_id"], base["revision"]),
        ).fetchone()
        assert snapshot is not None
        state = DesignState.model_validate(
            {**snapshot["normalized_model"], "run_id": str(base["run_id"])}
        )
        if not state.requirements:
            fail(422, "승인 설계에 실행 명세로 가져올 요구가 없습니다.")
        bundle = draft(uuid4(), ref, state)
        conn.execute("INSERT INTO spec_document VALUES(%s,%s,1)", (bundle.spec_id, baseline_id))
        record(conn, bundle, user)
        return view(conn, bundle.spec_id, 1)


@router.get("/specs/{spec_id}", operation_id="getSpecification", response_model=SpecView)
def get(spec_id: UUID, user: UserDep, conn: ConnDep) -> SpecView:
    with conn.transaction():
        _, version = load(conn, spec_id, user)
        return view(conn, spec_id, version)


@router.get("/specs/{spec_id}/scope", operation_id="assessSpecificationScope")
def scope(spec_id: UUID, user: UserDep, conn: ConnDep, version: int | None = None) -> ScopeReport:
    with conn.transaction():
        _, current = load(conn, spec_id, user)
        bundle = view(conn, spec_id, current if version is None else version).bundle
        return assess(
            tuple(ScopeRequirement(id=r.id, text=r.text, kind=r.kind) for r in bundle.requirements),
            bundle.spec_version,
        )


@router.get(
    "/specs/{spec_id}/versions/{version}",
    operation_id="getSpecificationVersion",
    response_model=SpecView,
)
def history(spec_id: UUID, version: int, user: UserDep, conn: ConnDep) -> SpecView:
    with conn.transaction():
        load(conn, spec_id, user)
        return view(conn, spec_id, version)


def expected(current: SpecView, payload: Expected) -> None:
    if (
        current.bundle.spec_version != payload.expected_version
        or current.readiness.spec_hash != payload.spec_hash
    ):
        fail(409, "다른 변경이 먼저 저장됐습니다. 최신 버전을 다시 조회하세요.")


@router.patch("/specs/{spec_id}", operation_id="editSpecification", response_model=SpecView)
def edit(
    spec_id: UUID,
    payload: Edit,
    user: UserDep,
    conn: ConnDep,
    settings: SettingsDep,
    checked: Mutation,
) -> SpecView:
    with conn.transaction():
        base, version = load(conn, spec_id, user)
        current = view(conn, spec_id, version)
        expected(current, payload)
        proposed = payload.bundle
        ref = reference(conn, base, user, settings)
        if (
            proposed.baseline != ref
            or proposed.spec_id != spec_id
            or proposed.spec_version != version
            or proposed.parent_spec_hash != current.bundle.parent_spec_hash
            or proposed.template != current.bundle.template
        ):
            fail(422, "기준 설계·명세 ID·버전·부모 해시는 서버가 관리합니다.")
        initial = view(conn, spec_id, 1).bundle
        original = {r.id: r for r in initial.requirements}
        supplied = {r.id: r for r in proposed.requirements if r.origin == "design"}
        if set(original) != set(supplied) or any(
            (r.legacy_id, r.kind) != (supplied[k].legacy_id, supplied[k].kind)
            for k, r in original.items()
        ):
            fail(
                422,
                "원본 요구를 삭제하거나 출처를 바꿀 수 없습니다. "
                "제외 범위는 우선순위와 사유로 남기세요.",
            )
        for key, original_req in original.items():
            supplied_req = supplied[key]
            if (
                supplied_req.priority != original_req.priority
                or supplied_req.requires_ui != original_req.requires_ui
            ) and supplied_req.rationale == original_req.rationale:
                fail(422, "초안의 우선순위·화면 범위를 바꾸려면 구체적인 사유를 남기세요.")
        questions = {q.id: q for q in proposed.questions}
        if any(
            q.id not in questions or questions[q.id].req_ids != q.req_ids for q in initial.questions
        ):
            fail(422, "초기 확인 질문은 삭제하지 말고 답변과 계약으로 보완하세요.")
        if proposed == current.bundle:
            return current
        bundle = proposed.evolve(
            spec_version=version + 1, parent_spec_hash=current.readiness.spec_hash
        )
        record(conn, bundle, user)
        conn.execute(
            "UPDATE spec_document SET current_version=%s WHERE id=%s", (version + 1, spec_id)
        )
        return view(conn, spec_id, version + 1)


@router.post(
    "/specs/{spec_id}/approve", operation_id="approveSpecification", response_model=SpecView
)
def approve(
    spec_id: UUID,
    payload: Expected,
    user: UserDep,
    conn: ConnDep,
    settings: SettingsDep,
    checked: Mutation,
) -> SpecView:
    with conn.transaction():
        base, version = load(conn, spec_id, user)
        current = view(conn, spec_id, version)
        expected(current, payload)
        if current.bundle.baseline != reference(conn, base, user, settings):
            fail(422, "실행 명세의 설계 출처가 일치하지 않습니다.")
        if not current.readiness.ready_for_review:
            fail(422, "미해결 질문 또는 누락된 실행 계약을 보완해야 승인할 수 있습니다.")
        if current.bundle.domain:
            from specton.implementation.domain import compile_domain

            row = conn.execute(
                "SELECT normalized_model FROM model_snapshot WHERE run_id=%s AND revision=%s",
                (base["run_id"], base["revision"]),
            ).fetchone()
            assert row is not None
            state = DesignState.model_validate(
                {**row["normalized_model"], "run_id": str(base["run_id"])}
            )
            try:
                compile_domain(current.bundle, state)
            except ValueError as error:
                fail(422, str(error))
        conn.execute(
            "INSERT INTO spec_approval(spec_id,version,spec_hash,actor_id) "
            "VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (spec_id, version, payload.spec_hash, user["id"]),
        )
        return view(conn, spec_id, version)


class CompletionRequest(Expected):
    instruction: str = Field(default="", max_length=12000)
    consent_external_analysis: Literal[True]


class CompletionView(Contract):
    bundle: SpecBundle
    readiness: ReadinessReport
    generation_ready: bool
    generation_issue: str | None
    calls: list[dict[str, Any]]


@router.post(
    "/specs/{spec_id}/complete",
    operation_id="proposeExecutableSpecification",
    response_model=CompletionView,
)
def complete(
    spec_id: UUID,
    payload: CompletionRequest,
    user: UserDep,
    conn: ConnDep,
    settings: SettingsDep,
    checked: Mutation,
) -> CompletionView:
    from specton.implementation.compiler import Unsupported, compile_contract
    from specton.llm.errors import LLMError
    from specton.specification import completion

    if not settings.openai_api_key:
        fail(503, "실행 명세 자동 작성에 필요한 AI 키가 설정되지 않았습니다.")
    with conn.transaction():
        base, version = load(conn, spec_id, user)
        current = view(conn, spec_id, version)
        expected(current, payload)
        reference(conn, base, user, settings)
        row = conn.execute(
            "SELECT normalized_model FROM model_snapshot WHERE run_id=%s AND revision=%s",
            (base["run_id"], base["revision"]),
        ).fetchone()
        assert row is not None
        state = DesignState.model_validate(
            {**row["normalized_model"], "run_id": str(base["run_id"])}
        )
    try:
        proposal, calls = completion.propose(settings, current.bundle, state, payload.instruction)
    except LLMError:
        fail(502, "실행 명세 자동 작성에 실패했습니다. 기존 저장 버전은 유지됩니다.")
    except ValueError as exc:
        fail(422, str(exc))
    with conn.transaction():
        base, version = load(conn, spec_id, user)
        expected(view(conn, spec_id, version), payload)
        reference(conn, base, user, settings)
    issue = None
    try:
        compile_contract(proposal, state)
    except Unsupported as exc:
        issue = str(exc)
    return CompletionView(
        bundle=proposal,
        readiness=report(proposal),
        generation_ready=issue is None,
        generation_issue=issue,
        calls=calls,
    )


class DemoRequest(Expected):
    table_id: str = Field(min_length=1, max_length=100)
    screen_name: str = Field(min_length=1, max_length=120)
    acknowledge_demo_scope: Literal[True]


@router.post(
    "/specs/{spec_id}/demo", operation_id="proposeDemoSpecification", response_model=CompletionView
)
def demo(
    spec_id: UUID,
    payload: DemoRequest,
    user: UserDep,
    conn: ConnDep,
    settings: SettingsDep,
    checked: Mutation,
) -> CompletionView:
    fail(410, "고정 업무 프로필은 종료되었습니다. 승인 설계 구조 자동 연결을 사용하세요.")


class BusinessRequest(Expected):
    acknowledge_demo_defaults: Literal[True]


@router.post(
    "/specs/{spec_id}/business",
    operation_id="proposeBusinessSpecification",
    response_model=CompletionView,
)
def business(
    spec_id: UUID,
    payload: BusinessRequest,
    user: UserDep,
    conn: ConnDep,
    settings: SettingsDep,
    checked: Mutation,
) -> CompletionView:
    fail(410, "고정 업무 프로필은 종료되었습니다. 승인 설계 구조 자동 연결을 사용하세요.")


@router.post(
    "/specs/{spec_id}/derive",
    operation_id="deriveDomainSpecification",
    response_model=CompletionView,
)
def derive_domain(
    spec_id: UUID,
    payload: Expected,
    user: UserDep,
    conn: ConnDep,
    settings: SettingsDep,
    checked: Mutation,
) -> CompletionView:
    from specton.implementation.domain import compile_domain
    from specton.specification.domain import derive

    with conn.transaction():
        base, version = load(conn, spec_id, user)
        current = view(conn, spec_id, version)
        expected(current, payload)
        reference(conn, base, user, settings)
        row = conn.execute(
            "SELECT normalized_model FROM model_snapshot WHERE run_id=%s AND revision=%s",
            (base["run_id"], base["revision"]),
        ).fetchone()
        assert row is not None
        state = DesignState.model_validate(
            {**row["normalized_model"], "run_id": str(base["run_id"])}
        )
        try:
            proposal = derive(current.bundle, state)
            compile_domain(proposal, state, require_ready=False)
        except ValueError as exc:
            fail(422, str(exc))
        return CompletionView(
            bundle=proposal,
            readiness=report(proposal),
            generation_ready=False,
            generation_issue=(
                "구조를 연결했습니다. 요구별 업무 동작·역할·확인 질문을 검토한 후 승인하세요."
            ),
            calls=[],
        )
