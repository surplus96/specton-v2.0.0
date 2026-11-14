"""누락된 Must 요구·질문·업무 정책을 검토 전에 탐지한다."""

import hashlib
import json

from specton.contracts.base import Contract, NonEmptyText
from specton.contracts.specification import Key, Sha256, SpecBundle


class ReadinessIssue(Contract):
    code: NonEmptyText
    target: Key
    message: NonEmptyText


class ReadinessReport(Contract):
    spec_hash: Sha256
    ready_for_review: bool
    issues: tuple[ReadinessIssue, ...]


def canonical_bytes(bundle: SpecBundle) -> bytes:
    """객체 key 순서는 무시하고 배열 순서·정확한 수량 문자열은 보존한다."""
    validated = SpecBundle.model_validate(bundle.model_dump(mode="json"))
    return json.dumps(
        validated.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def spec_hash(bundle: SpecBundle) -> str:
    return hashlib.sha256(b"specton:spec-v0.1\0" + canonical_bytes(bundle)).hexdigest()


def assess_readiness(bundle: SpecBundle) -> ReadinessReport:
    bundle = SpecBundle.model_validate_json(canonical_bytes(bundle))
    issues = []

    def add(code: str, target: str, message: str) -> None:
        issues.append(ReadinessIssue(code=code, target=target, message=message))

    for question in bundle.questions:
        if question.answer is None:
            add("UNRESOLVED_QUESTION", question.id, question.question)
    for case in bundle.use_cases:
        if case.transaction == "atomic" and case.idempotency != "key":
            add("MISSING_IDEMPOTENCY", case.id, "변경 명령에는 중복 적용 방지 계약이 필요합니다")
    for req in bundle.requirements:
        if req.priority != "Must":
            continue
        uses = {u.id for u in bundle.use_cases if req.id in u.req_ids}
        apis = {a.id for a in bundle.apis if a.use_case_id in uses}
        tests = [t for t in bundle.acceptance_cases if req.id in t.req_ids]
        if req.kind == "FR":
            if not uses:
                add("MISSING_USE_CASE", req.id, "Must 기능 요구의 유스케이스가 없습니다")
            if not apis:
                add("MISSING_API", req.id, "Must 기능 요구의 API가 없습니다")
            if not any(t.tier in {"api", "browser"} and uses & set(t.use_case_ids) for t in tests):
                add("MISSING_ACCEPTANCE", req.id, "실제 API/브라우저 인수 사례가 필요합니다")
        elif not tests:
            add("MISSING_ACCEPTANCE", req.id, "비기능 요구의 검증 사례가 필요합니다")
        if req.requires_ui:
            if not any(apis & set(s.api_ids) for s in bundle.screens):
                add("MISSING_SCREEN", req.id, "연결 API가 있는 화면이 필요합니다")
            if not any(t.tier == "browser" and uses & set(t.use_case_ids) for t in tests):
                add("MISSING_BROWSER_CASE", req.id, "화면 요구의 브라우저 인수 사례가 필요합니다")
    return ReadinessReport(
        spec_hash=spec_hash(bundle), ready_for_review=not issues, issues=tuple(issues)
    )
