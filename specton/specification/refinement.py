"""Bounded edits to an existing large specification, merged before full contract validation."""

import hashlib
import json
from typing import Literal

from pydantic import Field

from specton.contracts.base import Contract
from specton.contracts.specification import SpecBundle

FIELDS = {
    "screens": {
        "name",
        "empty_state",
        "loading_state",
        "error_state",
    },
    "use_cases": {"name", "preconditions", "steps"},
    "requirements": {"rationale"},
    "questions": {"question"},
    "domain_coverage": {"explanation"},
}


class ExistingEdit(Contract):
    section: Literal["screens", "use_cases", "requirements", "questions", "domain_coverage"]
    object_id: str = Field(min_length=1, max_length=100)
    field: str = Field(min_length=1, max_length=100)
    value_json: str = Field(min_length=1, max_length=16000)
    rationale: str = Field(min_length=1, max_length=2000)


class OpenQuestion(Contract):
    req_ids: tuple[str, ...] = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1, max_length=4000)


class Refinement(Contract):
    edits: tuple[ExistingEdit, ...] = Field(max_length=100)
    questions: tuple[OpenQuestion, ...] = Field(max_length=20)


def apply_refinement(current: SpecBundle, refinement: Refinement) -> SpecBundle:
    data = current.model_dump(mode="json")
    seen = set()
    for edit in refinement.edits:
        key = (edit.section, edit.object_id, edit.field)
        if key in seen or edit.field not in FIELDS[edit.section]:
            raise ValueError("지원하지 않거나 중복된 명세 보완입니다.")
        seen.add(key)
        group = (
            (data.get("domain") or {}).get("coverage", [])
            if edit.section == "domain_coverage"
            else data[edit.section]
        )
        identity = "requirement_id" if edit.section == "domain_coverage" else "id"
        obj = next((o for o in group if o[identity] == edit.object_id), None)
        if obj is None:
            raise ValueError("기존 명세에 없는 대상을 보완할 수 없습니다.")
        obj[edit.field] = json.loads(edit.value_json)
    requirements = {r.id for r in current.requirements}
    question_ids = {q.id for q in current.questions}
    for question in refinement.questions:
        if not set(question.req_ids) <= requirements:
            raise ValueError("확인 질문이 기존 요구를 참조하지 않습니다.")
        question_id = (
            "QUESTION-ai-" + hashlib.sha256(question.model_dump_json().encode()).hexdigest()[:24]
        )
        if question_id in question_ids:
            raise ValueError("확인 질문이 중복됩니다.")
        question_ids.add(question_id)
        data["questions"].append(
            {
                "id": question_id,
                "req_ids": list(question.req_ids),
                "question": question.question,
                "answer": None,
            }
        )
    return SpecBundle.model_validate(data)
