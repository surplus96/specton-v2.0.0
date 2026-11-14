"""명세 누락·권한/추적 모순·변조가 검토 준비 검사에서 차단되는지 검증한다."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from specton.contracts.specification import SpecBundle, TextLiteral
from specton.specification.readiness import assess_readiness, canonical_bytes, spec_hash

FIXTURE = Path("tests/fixtures/specification/item-create-v0.1.json")


def _payload() -> dict:
    return json.loads(FIXTURE.read_bytes())


def test_complete_contract_is_ready_for_review_but_contains_no_approval_claim() -> None:
    bundle = SpecBundle.model_validate(_payload())
    report = assess_readiness(bundle)
    assert report.ready_for_review and not report.issues
    assert report.spec_hash == spec_hash(bundle)
    assert "approved" not in SpecBundle.model_fields
    assert canonical_bytes(
        SpecBundle.model_validate_json(canonical_bytes(bundle))
    ) == canonical_bytes(bundle)


def test_key_order_does_not_change_hash_but_business_content_does() -> None:
    payload = _payload()
    bundle = SpecBundle.model_validate(payload)
    reordered = SpecBundle.model_validate(dict(reversed(list(payload.items()))))
    assert spec_hash(bundle) == spec_hash(reordered)
    changed = deepcopy(payload)
    changed["acceptance_cases"][0]["then"] = ["코드 중복 등록을 허용한다"]
    assert spec_hash(bundle) != spec_hash(SpecBundle.model_validate(changed))


@pytest.mark.parametrize(
    "section,field,value",
    [
        ("apis", "actor_roles", ["ROLE-unknown"]),
        ("apis", "use_case_id", "UC-unknown"),
        ("apis", "response_fields", []),
        ("apis", "concurrency", "read_only"),
        ("apis", "error_codes", ["UNRELATED"]),
        ("screens", "api_ids", ["API-unknown"]),
        ("acceptance_cases", "req_ids", ["REQ-unknown"]),
        ("acceptance_cases", "use_case_ids", ["UC-unknown"]),
        ("requirements", "origin", "user"),
    ],
)
def test_invalid_references_and_contract_disagreement_are_rejected(section, field, value) -> None:
    payload = _payload()
    payload[section][0][field] = value
    with pytest.raises(ValidationError):
        SpecBundle.model_validate(payload)


@pytest.mark.parametrize("missing", ["use_cases", "apis", "screens", "acceptance_cases"])
def test_missing_must_coverage_cannot_be_ready(missing: str) -> None:
    payload = _payload()
    payload[missing] = []
    if missing == "use_cases":
        payload["apis"] = []
        payload["screens"] = []
        for case in payload["acceptance_cases"]:
            case["use_case_ids"] = []
    if missing == "apis":
        payload["screens"] = []
    report = assess_readiness(SpecBundle.model_validate(payload))
    assert not report.ready_for_review


def test_unanswered_question_and_missing_idempotency_block_review() -> None:
    payload = _payload()
    payload["questions"] = [
        {
            "id": "QUESTION-code",
            "req_ids": ["REQ-item-create"],
            "question": "코드 길이를 확정해 주세요",
            "answer": None,
        }
    ]
    payload["use_cases"][0]["idempotency"] = "not_applicable"
    report = assess_readiness(SpecBundle.model_validate(payload))
    assert {i.code for i in report.issues} == {"UNRESOLVED_QUESTION", "MISSING_IDEMPOTENCY"}


def test_non_ui_nonfunctional_requirement_can_use_policy_acceptance() -> None:
    payload = _payload()
    payload["requirements"][0].update(kind="NFR", requires_ui=False)
    payload.update(use_cases=[], apis=[], screens=[])
    payload["acceptance_cases"][0].update(tier="policy", use_case_ids=[])
    assert assess_readiness(SpecBundle.model_validate(payload)).ready_for_review


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "format", "hash", "approval"])
def test_baseline_reference_requires_four_distinct_hashed_artifacts(mutation: str) -> None:
    payload = _payload()
    baseline = payload["baseline"]
    if mutation == "missing":
        baseline["artifacts"].pop()
    elif mutation == "duplicate":
        baseline["artifacts"][3] = baseline["artifacts"][0]
    elif mutation == "format":
        baseline["artifacts"][0]["file_format"] = "sql"
    elif mutation == "hash":
        baseline["manifest_hash"] = "not-a-hash"
    else:
        baseline["approved"] = True
    with pytest.raises(ValidationError):
        SpecBundle.model_validate(payload)


def test_rules_reject_executable_strings_and_unknown_fields() -> None:
    payload = _payload()
    payload["invariants"][0]["comparisons"][0]["left"] = {"kind": "eval", "code": "print('x')"}
    with pytest.raises(ValidationError):
        SpecBundle.model_validate(payload)
    payload = _payload()
    payload["invariants"][0]["comparisons"][0]["left"]["field_id"] = "FIELD-unknown"
    with pytest.raises(ValidationError, match="없는 규칙 필드"):
        SpecBundle.model_validate(payload)


def test_mutated_unvalidated_model_is_checked_again_before_hashing() -> None:
    bundle = SpecBundle.model_validate(_payload())
    with pytest.raises(ValidationError):
        spec_hash(bundle.model_copy(update={"spec_version": 0}))
    assert TextLiteral(value="  literal  ").value == "  literal  "


def test_rename_preserves_object_id_but_changes_version_hash() -> None:
    original = SpecBundle.model_validate(_payload())
    renamed = original.evolve(
        spec_version=2,
        parent_spec_hash=spec_hash(original),
        use_cases=(original.use_cases[0].evolve(name="품목 신규 등록"),),
    )
    assert original.use_cases[0].id == renamed.use_cases[0].id
    assert spec_hash(original) != spec_hash(renamed)
