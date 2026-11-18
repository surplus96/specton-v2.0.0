import pytest
from domain_support import case
from pydantic import ValidationError

from specton.implementation.domain import compile_domain
from specton.specification.record_contract import RecordContract, apply_record_contract


def policy(bundle):
    entity = bundle.entities[0]
    name = next(f for f in entity.fields if f.name == "name")
    return RecordContract.model_validate(
        {
            "id": "RC-synthetic",
            "entity_id": entity.id,
            "req_ids": [bundle.requirements[0].id],
            "rationale": "명시한 이름만 허용하는 합성 정책",
            "allowed_values": [
                {
                    "field_id": name.id,
                    "values": [
                        {"kind": "text", "value": "north"},
                        {"kind": "text", "value": "south"},
                    ],
                }
            ],
            "scenarios": [
                {
                    "id": "TC-explicit-normal",
                    "name": "명시한 기록 등록·조회",
                    "category": "normal",
                    "steps": [
                        {
                            "action": "insert",
                            "body": {"id": "r1", "name": "north"},
                            "request_key": "create",
                            "expect": {
                                "kind": "exact",
                                "status": 200,
                                "body": {"id": "r1", "name": "north"},
                            },
                        },
                        {
                            "action": "list",
                            "expect": {
                                "kind": "exact",
                                "status": 200,
                                "body": [{"id": "r1", "name": "north"}],
                            },
                        },
                    ],
                }
            ],
        }
    )


@pytest.mark.parametrize("domain", ["booking", "maintenance"])
def test_same_policy_binds_actual_apis_without_approving_or_reducing_scope(domain):
    bundle, state, _ = case(domain)
    proposed = apply_record_contract(bundle, policy(bundle))
    assert proposed.schema_version == "spec-v0.7"
    for name in ("baseline", "requirements", "questions", "domain", "roles"):
        assert getattr(proposed, name) == getattr(bundle, name)
    compiled = compile_domain(proposed, state, require_ready=False)
    assert len(compiled["executable_cases"]) == 1
    assert any(o.get("invariants") for o in compiled["domain"]["operations"])
    assert proposed.acceptance_cases[-1].execution.steps[0].body == {"id": "r1", "name": "north"}
    with pytest.raises(ValueError, match="덮어쓸"):
        apply_record_contract(proposed, policy(bundle))


def test_explicit_oracle_is_not_replaced_by_input_or_observed_output():
    bundle, _, _ = case()
    data = policy(bundle).model_dump(mode="json")
    data["scenarios"][0]["steps"][0]["expect"]["body"]["name"] = "intentionally-wrong"
    proposed = apply_record_contract(bundle, RecordContract.model_validate(data))
    assert (
        proposed.acceptance_cases[-1].execution.steps[0].expect.body["name"]
        == "intentionally-wrong"
    )


def test_setup_uses_explicit_insert_api_and_is_replayed_before_each_case():
    bundle, _, _ = case()
    data = policy(bundle).model_dump(mode="json")
    api_id = next(o.api_id for o in bundle.domain.operations if o.action == "insert")
    data["setup"] = [
        {
            "api_id": api_id,
            "body": {"id": "prerequisite", "name": "south"},
            "request_key": "setup",
            "expect": {
                "kind": "exact",
                "status": 200,
                "body": {"id": "prerequisite", "name": "south"},
            },
        }
    ]
    result = apply_record_contract(bundle, RecordContract.model_validate(data))
    assert result.acceptance_cases[-1].execution.steps[0].body["id"] == "prerequisite"
    assert result.acceptance_cases[-1].execution.steps[1].body["id"] == "r1"
    data["setup"][0]["api_id"] = next(
        o.api_id for o in bundle.domain.operations if o.action == "update"
    )
    with pytest.raises(ValueError, match="선행 데이터"):
        apply_record_contract(bundle, RecordContract.model_validate(data))


@pytest.mark.parametrize("mutation", ["foreign_field", "foreign_requirement", "get_body", "key"])
def test_contract_rejects_wrong_binding_or_request_shape(mutation):
    bundle, _, _ = case()
    data = policy(bundle).model_dump(mode="json")
    if mutation == "foreign_field":
        data["allowed_values"][0]["field_id"] = "FIELD-missing"
    elif mutation == "foreign_requirement":
        data["req_ids"] = ["REQ-missing"]
    elif mutation == "get_body":
        data["scenarios"][0]["steps"][1]["body"] = {"id": "r1"}
    else:
        data["scenarios"][0]["steps"][0]["request_key"] = "bad/key"
    with pytest.raises((ValueError, ValidationError)):
        apply_record_contract(bundle, RecordContract.model_validate(data))
