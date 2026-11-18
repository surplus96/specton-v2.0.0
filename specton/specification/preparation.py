"""Portable, unapproved E2E preparation tied to an exact saved specification."""

from typing import Literal

from pydantic import Field

from specton.contracts import DesignState
from specton.contracts.base import Contract, NonEmptyText
from specton.contracts.specification import Key, Sha256, SpecBundle
from specton.implementation.domain import compile_domain
from specton.model_hash import model_hash
from specton.specification.readiness import assess_readiness, spec_hash


class ScopeItem(Contract):
    requirement_id: Key
    disposition: Literal["included", "deferred"]
    rationale: NonEmptyText


class AnswerProposal(Contract):
    question_id: Key
    answer: NonEmptyText


class TestPreparation(Contract):
    format: Literal["specton-e2e-preparation-v1"] = "specton-e2e-preparation-v1"
    base_spec_hash: Sha256
    bundle: SpecBundle
    scope: tuple[ScopeItem, ...] = Field(min_length=1, max_length=500)
    answer_proposals: tuple[AnswerProposal, ...] = Field(max_length=500)


def validate_preparation(
    base: SpecBundle, preparation: TestPreparation, state: DesignState
) -> dict[str, object]:
    proposed = preparation.bundle
    if preparation.base_spec_hash != spec_hash(base):
        raise ValueError("준비 파일의 기준 명세 해시가 다릅니다.")
    for name in ("spec_id", "spec_version", "parent_spec_hash", "baseline", "template"):
        if getattr(base, name) != getattr(proposed, name):
            raise ValueError("출처·명세 ID·버전은 준비 파일로 변경할 수 없습니다.")
    if model_hash(state) != base.baseline.model_hash:
        raise ValueError("승인 모델의 해시가 다릅니다.")
    source = {r.id: r for r in base.requirements}
    target = {r.id: r for r in proposed.requirements}
    scope = {r.requirement_id: r for r in preparation.scope}
    if (
        source.keys() != target.keys()
        or source.keys() != scope.keys()
        or len(scope) != len(preparation.scope)
    ):
        raise ValueError("모든 원본 요구와 포함·제외 범위를 한 번씩 보존하세요.")
    for rid, before in source.items():
        after, item = target[rid], scope[rid]
        if (before.text, before.legacy_id, before.kind, before.origin) != (
            after.text,
            after.legacy_id,
            after.kind,
            after.origin,
        ):
            raise ValueError("원본 요구 내용·출처를 축소하거나 변경할 수 없습니다.")
        if (after.priority == "Won't") != (
            item.disposition == "deferred"
        ) or after.rationale != item.rationale:
            raise ValueError("명세의 범위와 준비 파일의 제외 사유가 다릅니다.")
    questions = {q.id: q for q in proposed.questions}
    if {q.id for q in base.questions} != questions.keys() or any(
        q.req_ids != questions[q.id].req_ids
        or q.question != questions[q.id].question
        or q.answer != questions[q.id].answer
        for q in base.questions
    ):
        raise ValueError("기존 질문·요구 연결·답변을 보존하세요. 가정은 별도 제안으로 작성하세요.")
    answers = {a.question_id: a.answer for a in preparation.answer_proposals}
    if len(answers) != len(preparation.answer_proposals) or set(answers) != {
        q.id for q in base.questions if q.answer is None
    }:
        raise ValueError("미답변 질문마다 검토할 가정을 한 번씩 제안하세요.")
    existing = {c.id: c for c in proposed.acceptance_cases}
    if any(c.execution and existing.get(c.id) != c for c in base.acceptance_cases):
        raise ValueError("기존 실행 인수 사례·기대값을 변경할 수 없습니다.")
    # Structural compilation checks references, permissions, types, units and executable cases.
    # The real bundle remains unanswered/unapproved. This clone checks the proposed assumptions.
    data = proposed.model_dump(mode="json")
    for q in data["questions"]:
        if q["id"] in answers:
            q["answer"] = answers[q["id"]]
    reviewed_hypothesis = SpecBundle.model_validate(data)
    compile_domain(reviewed_hypothesis, state)
    return {
        "base_spec_hash": preparation.base_spec_hash,
        "draft_spec_hash": spec_hash(proposed),
        "included": sum(r.disposition == "included" for r in preparation.scope),
        "deferred": sum(r.disposition == "deferred" for r in preparation.scope),
        "executable_cases": sum(c.execution is not None for c in proposed.acceptance_cases),
        "pending_owner_answers": len(answers),
        "ready_for_review": assess_readiness(proposed).ready_for_review,
        "proposed_assumptions_compile": "passed",
        "approval": "not_requested",
        "database_mutations": 0,
    }
