import hashlib
import json
from copy import deepcopy

import pytest
from command_support import atomic_case
from domain_support import case
from test_customer_delivery_package import repack

from specton.contracts.specification import SpecBundle
from specton.implementation.compiler import Unsupported, compile_contract
from specton.implementation.package import generate
from specton.implementation.verify import inspect_package
from specton.specification.readiness import canonical_bytes, spec_hash


@pytest.mark.parametrize("domain", ["inventory", "maintenance"])
def test_commands_compile_actual_schema_and_package_without_changing_business_ddl(domain):
    bundle, state, artifacts = atomic_case(domain)
    source = generate(bundle, state, artifacts)
    assert generate(bundle, state, artifacts) == source
    files, manifest = inspect_package(source, hashlib.sha256(source).hexdigest())
    assert manifest["template_version"] == "executable-design-v11"
    command = next(
        o
        for o in json.loads(files["backend/contract.json"])["domain"]["operations"]
        if o["action"] == "command"
    )
    assert {t["table"] for t in command["targets"]} == {
        t.physical_name for t in state.normalized.tables
    }
    assert files["backend/approved.sql"] == artifacts["ddl.sql"]
    assert b'"commands"' in files["design/revised/functions.md"]
    assert "commands" in json.loads(files["spec/approved-spec.json"])["domain"]
    assert command["actor_roles"] == ["ROLE-operator"]


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown_table",
        "partial_key",
        "duplicate_target",
        "duplicate_write",
        "key_change",
        "forward_reference",
        "wrong_type",
        "wrong_literal",
        "missing_input",
        "missing_return",
        "bypass_role",
        "missing_failure_case",
        "fake_normal_case",
        "missing_idempotency",
    ],
)
def test_invalid_or_unsafe_command_contracts_are_rejected(mutation):
    bundle, state, _ = atomic_case()
    data = bundle.model_dump(mode="json")
    c = data["domain"]["commands"][0]
    if mutation == "unknown_table":
        c["targets"][0]["table_id"] = "TBL-missing"
    elif mutation == "partial_key":
        c["targets"][1]["keys"].pop(next(iter(c["targets"][1]["keys"])))
    elif mutation == "duplicate_target":
        c["targets"][1]["id"] = c["targets"][0]["id"]
    elif mutation == "duplicate_write":
        c["writes"][1]["target"] = c["writes"][0]["target"]
    elif mutation == "key_change":
        c["writes"][0]["values"] = deepcopy(c["targets"][0]["keys"])
    elif mutation == "forward_reference":
        c["before"].append(
            {
                "left": {
                    "kind": "row",
                    "target": "entry",
                    "column_id": next(iter(c["targets"][1]["keys"])),
                },
                "operator": "eq",
                "right": {"kind": "literal", "value": "one"},
            }
        )
    elif mutation == "wrong_type":
        c["writes"][0]["values"][next(iter(c["writes"][0]["values"]))] = {
            "kind": "input",
            "field_id": "INPUT-id",
        }
    elif mutation == "wrong_literal":
        c["before"][0]["right"]["value"] = "NaN"
    elif mutation == "missing_input":
        c["input_bindings"].pop()
    elif mutation == "missing_return":
        c["returns"].pop(next(iter(c["returns"])))
    elif mutation == "bypass_role":
        data["apis"][-1]["actor_roles"] = ["ROLE-admin"]
        data["use_cases"][-1]["actor_roles"] = ["ROLE-admin"]
        data["screens"][-1]["actor_roles"] = ["ROLE-admin"]
    elif mutation == "missing_failure_case":
        data["acceptance_cases"] = [
            t for t in data["acceptance_cases"] if t["id"] != "TC-command-failure"
        ]
    elif mutation == "fake_normal_case":
        for t in data["acceptance_cases"]:
            if t["id"] == "TC-command-normal":
                for step in t["execution"]["steps"]:
                    if step["api_id"] == "API-atomic":
                        step["actor"] = "denied"
                        step["expect"] = {"kind": "error", "status": 403, "code": "FORBIDDEN"}
    else:
        data["use_cases"][-1]["idempotency"] = "not_applicable"
    with pytest.raises((ValueError, Unsupported)):
        compile_contract(SpecBundle.model_validate(data), state)


def test_old_spec_hash_omits_new_defaults_and_v08_requires_explicit_version():
    old, _, _ = case()
    payload = json.loads(canonical_bytes(old))
    assert "commands" not in payload["domain"]
    assert spec_hash(SpecBundle.model_validate(payload)) == spec_hash(old)
    bundle, _, _ = atomic_case()
    data = bundle.model_dump(mode="json")
    data["schema_version"] = "spec-v0.7"
    with pytest.raises(ValueError, match=r"v0\.8"):
        SpecBundle.model_validate(data)


@pytest.mark.parametrize(
    "path", ["backend/commands.py", "frontend/src/commands.tsx", "backend/contract.json"]
)
def test_resigned_source_cannot_forge_command_code_or_contract(path):
    source = generate(*atomic_case())
    files, _ = inspect_package(source, hashlib.sha256(source).hexdigest())
    files[path] = b"{}" if path.endswith(".json") else b"forged"
    changed = repack(files)
    with pytest.raises(ValueError):
        inspect_package(changed, hashlib.sha256(changed).hexdigest())


def test_existing_commands_cannot_be_erased_by_structural_rederivation():
    from specton.specification.domain import derive

    bundle, state, _ = atomic_case()
    with pytest.raises(ValueError, match="덮어쓸"):
        derive(bundle, state)


def test_record_policy_preserves_v08_and_commands():
    from test_record_contract import policy

    from specton.specification.record_contract import apply_record_contract

    bundle, _, _ = atomic_case()
    result = apply_record_contract(bundle, policy(bundle))
    assert result.schema_version == "spec-v0.8"
    assert result.domain.commands == bundle.domain.commands


def test_completion_rejects_silent_removal_of_existing_commands():
    from specton.specification.completion import validate_proposal

    bundle, _, _ = atomic_case()
    data = bundle.model_dump(mode="json")
    data["domain"]["commands"] = []
    with pytest.raises(ValueError, match="명령을 제거"):
        validate_proposal(bundle, SpecBundle.model_validate(data))


def test_changed_atomic_contract_requires_data_and_idempotency_migration_review():
    from specton.implementation.data_transfer import plan

    bundle, state, artifacts = atomic_case()
    source = generate(bundle, state, artifacts)
    source_hash = hashlib.sha256(source).hexdigest()
    assert plan(source, source_hash, source, source_hash)["status"] == "ready_for_rehearsal"
    data = bundle.model_dump(mode="json")
    data["domain"]["commands"][0]["before"][0]["operator"] = "ge"
    changed = generate(SpecBundle.model_validate(data), state, artifacts)
    result = plan(source, source_hash, changed, hashlib.sha256(changed).hexdigest())
    assert result["schema_changed"] is False
    assert result["status"] == "blocked"
    assert any("중복 요청" in reason for reason in result["reasons"])
