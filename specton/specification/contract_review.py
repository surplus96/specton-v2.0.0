"""Validate manually authored business contracts against their immutable source spec.

These are review artifacts, not DomainPlan instructions. Validation establishes
provenance and references only; it cannot grant runtime support or customer consent.
"""

from typing import Literal

from pydantic import Field, JsonValue

from specton.contracts.base import Contract, NonEmptyText
from specton.contracts.specification import Key, Sha256, SpecBundle
from specton.specification.business_contracts import TOPICS
from specton.specification.readiness import spec_hash


class SourceRule(Contract):
    requirement_id: Key
    quote: NonEmptyText


class BusinessExample(Contract):
    id: Key
    category: Literal["normal", "boundary", "failure", "concurrency", "security", "recovery"]
    given: dict[str, JsonValue]
    when: NonEmptyText
    expected: dict[str, JsonValue]
    proposed_policy_ids: tuple[Key, ...] = ()
    execution: Literal["not_executable"] = "not_executable"


class PolicyProposal(Contract):
    id: Key
    text: NonEmptyText
    approval: Literal["not_requested"] = "not_requested"


class WorkContract(Contract):
    id: Key
    name: NonEmptyText
    requirement_ids: tuple[Key, ...] = Field(min_length=1)
    source_rules: tuple[SourceRule, ...] = Field(min_length=1)
    entity_ids: tuple[Key, ...] = Field(min_length=1)
    required_capabilities: tuple[str, ...] = Field(min_length=1)
    proposed_policies: tuple[PolicyProposal, ...] = ()
    open_questions: tuple[NonEmptyText, ...] = ()
    examples: tuple[BusinessExample, ...] = Field(min_length=3)
    implementation: Literal["extension_required"] = "extension_required"


class ContractReview(Contract):
    version: Literal["business-contract-review-v1"] = "business-contract-review-v1"
    document: NonEmptyText
    source_spec_hash: Sha256
    contracts: tuple[WorkContract, ...] = Field(min_length=1, max_length=100)
    status: Literal["draft_not_executable"] = "draft_not_executable"


def validate_review(bundle: SpecBundle, review: ContractReview) -> dict[str, JsonValue]:
    if spec_hash(bundle) != review.source_spec_hash:
        raise ValueError("계약 초안의 출처 명세 해시가 다릅니다.")
    requirements = {r.id: r for r in bundle.requirements}
    entities = {e.id for e in bundle.entities}
    seen = set()
    covered: set[str] = set()
    for contract in review.contracts:
        if contract.id in seen:
            raise ValueError("계약 ID가 중복됩니다.")
        seen.add(contract.id)
        if not set(contract.requirement_ids) <= set(requirements):
            raise ValueError("계약의 요구 출처가 없습니다.")
        if not set(contract.entity_ids) <= entities:
            raise ValueError("계약의 데이터 연결이 없습니다.")
        if not set(contract.required_capabilities) <= TOPICS.keys() - {
            "record_review",
            "nonfunctional_review",
        }:
            raise ValueError("추가 구현 능력 ID를 확인하세요.")
        if {r.requirement_id for r in contract.source_rules} != set(contract.requirement_ids):
            raise ValueError("모든 계약 요구의 원문 근거가 필요합니다.")
        for rule in contract.source_rules:
            if rule.quote not in requirements[rule.requirement_id].text:
                raise ValueError("원문에서 확인할 수 없는 업무 규칙입니다.")
        proposals = {p.id for p in contract.proposed_policies}
        if len(proposals) != len(contract.proposed_policies):
            raise ValueError("정책 제안 ID가 중복됩니다.")
        example_ids = {e.id for e in contract.examples}
        if len(example_ids) != len(contract.examples):
            raise ValueError("인수 예시 ID가 중복됩니다.")
        if not {"normal", "boundary", "failure"} <= {e.category for e in contract.examples}:
            raise ValueError("정상·경계·실패 인수 예시가 필요합니다.")
        if any(not e.given or not e.expected for e in contract.examples):
            raise ValueError("고정 입력과 기대 결과가 필요합니다.")
        if any(not set(e.proposed_policy_ids) <= proposals for e in contract.examples):
            raise ValueError("인수 예시가 참조한 정책 제안이 없습니다.")
        covered.update(contract.requirement_ids)
    return {
        "status": "references_validated",
        "source_spec_hash": review.source_spec_hash,
        "contracts": len(review.contracts),
        "examples": sum(len(c.examples) for c in review.contracts),
        "covered_requirement_ids": [str(k) for k in sorted(covered)],
        "remaining_requirement_ids": [str(k) for k in sorted(set(requirements) - covered)],
        "approval": "not_requested",
        "runtime_execution": "not_run",
        "business_acceptance": "not_run",
    }
