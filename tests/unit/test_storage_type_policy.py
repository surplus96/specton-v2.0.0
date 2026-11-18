from dataclasses import replace

import pytest
from pydantic import ValidationError

from specton.contracts import AttributeDraft
from specton.nodes.a03_entities import _checked_against
from specton.review.standard_compliance import storage_type_policy


@pytest.fixture(scope="module")
def policy():
    return storage_type_policy("maintenance")


@pytest.mark.parametrize(
    "name,wrong,right",
    [
        ("예정일자", {"data_type": "date"}, {"data_type": "char", "length": 8}),
        ("검수완료여부", {"data_type": "boolean"}, {"data_type": "char", "length": 1}),
        (
            "최대적재중량",
            {"data_type": "numeric", "precision": 18, "scale": 3},
            {"data_type": "numeric", "precision": 10, "scale": 3},
        ),
    ],
)
def test_generation_rejects_the_same_conflict_as_final_standard_policy(policy, name, wrong, right):
    bad = AttributeDraft(name=name, req_ids=["REQ-01"], **wrong)
    before = bad.model_dump()
    assert policy.problems(bad)
    assert bad.model_dump() == before  # proposals are rejected, never silently coerced
    assert policy.problems(AttributeDraft(name=name, req_ids=["REQ-01"], **right)) == []


def test_native_profile_and_pack_override_have_the_same_precedence(policy):
    date = AttributeDraft(name="예정일자", data_type="date", req_ids=["REQ-01"])
    native = replace(policy, context=replace(policy.context, profile="pg_native"))
    assert native.problems(date) == []
    overridden = replace(policy, pack_terms=policy.pack_terms | {date.name})
    assert overridden.problems(date) == []


def test_output_contract_binds_unambiguous_storage_and_keeps_an_audit_note(policy):
    model = _checked_against([], ["REQ-01"], [], {}, storage_policy=policy)
    data = {
        "entities": [
            {
                "name": "신규대상",
                "description": "합성 검사",
                "req_ids": ["REQ-01"],
                "attributes": [{"name": "예정일자", "data_type": "date", "req_ids": ["REQ-01"]}],
            }
        ],
        "entity_ops": [],
    }
    result = model.model_validate(data)
    resolved = result.entities[0].attributes[0]
    assert resolved.data_type == "char" and resolved.length == 8
    assert "모델 초안 date → char(8)" in resolved.description
    assert data["entities"][0]["attributes"][0]["data_type"] == "date"
    data["entities"][0]["attributes"][0] = {
        "name": "검수중량",
        "data_type": "text",
        "req_ids": ["REQ-01"],
    }
    with pytest.raises(ValidationError, match="저장 타입 정책"):
        model.model_validate(data)


def test_unknown_names_do_not_gain_invented_domain_mappings(policy):
    attribute = AttributeDraft(name="합성미등록속성값가나다", data_type="text", req_ids=["REQ-01"])
    assert policy.problems(attribute) == []
    hints = policy.guidance("예정일자와 최대적재중량")
    assert hints["profile"] == "strict"
    assert hints["exact_terms_in_source"]["최대적재중량"] == "numeric(10,3)"
    assert set(hints["source_hashes"]) == {"words", "terms", "domains"}
