import pytest
from calculation_support import calculation_case

from specton.specification.preparation import TestPreparation as Preparation
from specton.specification.preparation import validate_preparation
from specton.specification.readiness import spec_hash


def packet(domain="inventory"):
    bundle, state, _ = calculation_case(domain)
    data = bundle.model_dump(mode="json")
    data["questions"] = [
        {
            "id": "QUESTION-scope",
            "req_ids": [data["requirements"][0]["id"]],
            "question": "제안된 시험 범위를 확인하세요.",
            "answer": None,
        }
    ]
    base = type(bundle).model_validate(data)
    for r in data["requirements"]:
        r["rationale"] = "범위와 독립 API 인수 사례를 준비합니다."
    proposal = Preparation.model_validate(
        dict(
            base_spec_hash=spec_hash(base),
            bundle=data,
            scope=[
                dict(
                    requirement_id=r.id,
                    disposition="included",
                    rationale="범위와 독립 API 인수 사례를 준비합니다.",
                )
                for r in base.requirements
            ],
            answer_proposals=[
                dict(question_id=q.id, answer="검토를 기다리는 합성 시험의 가정입니다.")
                for q in base.questions
            ],
        )
    )
    return base, state, proposal


@pytest.mark.parametrize("domain", ["inventory", "maintenance"])
def test_preparation_keeps_answers_and_approval_pending(domain):
    base, state, proposal = packet(domain)
    report = validate_preparation(base, proposal, state)
    assert report["proposed_assumptions_compile"] == "passed"
    assert report["pending_owner_answers"] == len(base.questions)
    assert report["ready_for_review"] is False
    assert report["executable_cases"] == 6
    assert all(q.answer is None for q in proposal.bundle.questions)
    assert report["database_mutations"] == 0 and report["approval"] == "not_requested"


@pytest.mark.parametrize(
    "mutation",
    [
        "hash",
        "version",
        "source",
        "text",
        "scope",
        "rationale",
        "answer",
        "question",
        "missing_assumption",
        "duplicate_assumption",
        "oracle",
        "bad_reference",
    ],
)
def test_changed_source_silent_answers_or_oracles_are_rejected(mutation):
    base, state, proposal = packet()
    data = proposal.model_dump(mode="json")
    if mutation == "hash":
        data["base_spec_hash"] = "0" * 64
    elif mutation == "version":
        data["bundle"]["spec_version"] += 1
    elif mutation == "source":
        data["bundle"]["baseline"]["model_hash"] = "0" * 64
    elif mutation == "text":
        data["bundle"]["requirements"][0]["text"] = "의미를 축소한 요구"
    elif mutation == "scope":
        data["scope"][0]["disposition"] = "deferred"
    elif mutation == "rationale":
        data["scope"][0]["rationale"] = "명세와 다른 범위 설명"
    elif mutation == "answer":
        data["bundle"]["questions"][0]["answer"] = "모델이 임의로 승인한 답변"
    elif mutation == "question":
        data["bundle"]["questions"][0]["question"] = "원본과 다른 질문"
    elif mutation == "missing_assumption":
        data["answer_proposals"].pop()
    elif mutation == "duplicate_assumption":
        data["answer_proposals"].append(data["answer_proposals"][0])
    elif mutation == "oracle":
        data["bundle"]["acceptance_cases"][-3]["execution"]["steps"][-1]["expect"]["body"][
            "total"
        ] = "99.00"
    else:
        data["bundle"]["domain"]["calculations"][0]["aggregates"][1]["column_id"] = "COL-missing"
    with pytest.raises(ValueError):
        validate_preparation(base, Preparation.model_validate(data), state)
