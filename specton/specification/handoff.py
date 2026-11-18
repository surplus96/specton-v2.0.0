"""Separate structural feasibility, executable evidence and customer handoff obligations."""

from typing import Literal
from uuid import UUID

from specton.contracts.base import Contract
from specton.contracts.specification import Sha256, SpecBundle
from specton.specification.business_contracts import BusinessContractWorksheet, worksheets
from specton.specification.capabilities import VERSION
from specton.specification.readiness import ReadinessReport


class HandoffGate(Contract):
    id: str
    name: str
    status: Literal["passed", "blocked", "review_required", "not_run"]
    detail: str


class SourceAssessment(Contract):
    implementation_id: UUID
    source_hash: Sha256
    template_version: str
    verification_id: UUID | None = None
    integrity: HandoffGate
    verification: HandoffGate
    passed_case_ids: tuple[str, ...] = ()


class HandoffReport(Contract):
    version: Literal["handoff-readiness-v1"] = "handoff-readiness-v1"
    catalog_version: str = VERSION
    assessment_kind: Literal["read_only_review"] = "read_only_review"
    spec_id: UUID
    spec_version: int
    spec_hash: Sha256
    project_id: UUID
    baseline_id: UUID
    is_latest: bool
    conclusion: Literal["contract_work_required", "technical_review_only"]
    included_requirements: int
    excluded_requirements: int
    extension_hint_requirements: int
    requirements_without_executable_cases: int
    gates: tuple[HandoffGate, ...]
    contracts: tuple[BusinessContractWorksheet, ...]
    source: SourceAssessment | None = None
    business_acceptance: Literal["not_run"] = "not_run"
    customer_handoff: Literal["not_recorded"] = "not_recorded"
    notice: str = (
        "저장된 명세와 해당 소스의 근거를 확인한 읽기 전용 점검입니다. "
        "표현 기반 확장 후보는 제외·부정 문맥까지 검토해야 합니다. "
        "계약 초안의 기대 조건은 실행된 테스트가 아니며 답변·구현·승인을 대신하지 않습니다. "
        "기술 검사 통과와 고객의 업무 인수·실제 환경 납품은 별도입니다."
    )


def assess_handoff(
    bundle: SpecBundle,
    readiness: ReadinessReport,
    *,
    approved: bool,
    is_latest: bool,
    generator_error: str | None,
    source: SourceAssessment | None = None,
) -> HandoffReport:
    contracts = worksheets(bundle)
    included = [c for c in contracts if c.scope == "included"]
    extensions = sum(any(t.detection == "text_hint" for t in c.topics) for c in included)
    missing = sum(not c.executable_case_ids for c in included)
    incomplete = any(c.missing_api_case_categories for c in included)
    contract_work = (
        not included
        or not readiness.ready_for_review
        or bool(extensions)
        or incomplete
        or generator_error is not None
    )
    gates = [
        HandoffGate(
            id="scope_contract",
            name="요구별 업무 계약",
            status="review_required" if contract_work else "passed",
            detail=(
                f"포함 {len(included)}건 · 확장 표현 검토 {extensions}건 · "
                f"실행 사례 없는 요구 {missing}건. "
                "API 연결·사례 분류 존재 여부이며 업무 의미 전체의 충족 판정은 별도입니다."
            ),
        ),
        HandoffGate(
            id="specification",
            name="명세 구조·미답변 질문",
            status="passed" if readiness.ready_for_review else "blocked",
            detail=f"명세 검토 준비 검사 {len(readiness.issues)}건 미해결. "
            "기존 승인·생성 조건을 변경하지 않습니다.",
        ),
        HandoffGate(
            id="approval",
            name="최신 설계·명세 승인",
            status="passed" if approved and is_latest else "blocked",
            detail="최신 설계의 최신 명세 승인 확인"
            if approved and is_latest
            else "현재 보고서는 미승인 또는 과거 설계/명세 버전입니다.",
        ),
        HandoffGate(
            id="generator",
            name="현재 생성기의 엄격한 계약 검사",
            status="blocked" if generator_error else "passed",
            detail=generator_error
            or "현재 생성기로 계약 컴파일 가능. 앱 실행·업무 인수와 별도입니다.",
        ),
    ]
    if source:
        gates.extend((source.integrity, source.verification))
    else:
        gates.extend(
            (
                HandoffGate(
                    id="source",
                    name="명세·설계·생성 소스 일치",
                    status="not_run",
                    detail="이 명세 버전·해시에 연결된 생성 소스가 없습니다.",
                ),
                HandoffGate(
                    id="verification",
                    name="격리 실행·브라우저 검증",
                    status="not_run",
                    detail="동일 소스의 플랫폼 검증을 요청하고 결과를 확인하세요.",
                ),
            )
        )
    planned = {case for c in included for case in c.executable_case_ids}
    passed = set(source.passed_case_ids) if source else set()
    all_cases = bool(planned) and planned <= passed and not missing
    gates.extend(
        (
            HandoffGate(
                id="executable_cases",
                name="포함 요구의 명시적 API 인수 사례",
                status="passed" if all_cases else "not_run",
                detail=f"계획 {len(planned)}건 중 근거 확인 {len(planned & passed)}건. "
                "사례가 없거나 일부 요구에만 있으면 전체 통과로 표시하지 않습니다.",
            ),
            HandoffGate(
                id="customer_environment",
                name="고객 환경 설치·인증·복구",
                status="not_run",
                detail="합성 앱 회귀와 별도로 납품 소스 해시·환경·계정 "
                "역할·백업 복구 결과를 고객 환경에서 확인해야 합니다.",
            ),
            HandoffGate(
                id="business_handoff",
                name="고객 업무 인수·납품 합의",
                status="review_required",
                detail="포함/제외 범위, 미구현 항목, 실제 업무 시나리오, "
                "데이터 이전·운영 책임·고객 인수 기록이 필요합니다.",
            ),
        )
    )
    return HandoffReport(
        spec_id=bundle.spec_id,
        spec_version=bundle.spec_version,
        spec_hash=readiness.spec_hash,
        project_id=bundle.baseline.project_id,
        baseline_id=bundle.baseline.baseline_id,
        is_latest=is_latest,
        conclusion="contract_work_required" if contract_work else "technical_review_only",
        included_requirements=len(included),
        excluded_requirements=len(contracts) - len(included),
        extension_hint_requirements=extensions,
        requirements_without_executable_cases=missing,
        gates=tuple(gates),
        contracts=contracts,
        source=source,
    )
