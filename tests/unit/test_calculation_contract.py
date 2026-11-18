import hashlib
import json

import pytest
from calculation_support import calculated_command, calculation_case

from specton.contracts.specification import SpecBundle
from specton.implementation.compiler import Unsupported, compile_contract
from specton.implementation.package import generate
from specton.implementation.verify import inspect_package
from specton.specification.readiness import canonical_bytes


@pytest.mark.parametrize("domain", ["inventory", "maintenance"])
def test_queries_and_calculated_commands_use_actual_schema_and_keep_original_sql(domain):
    for factory in [calculation_case, calculated_command]:
        bundle, state, artifacts = factory(domain)
        content = generate(bundle, state, artifacts)
        assert generate(bundle, state, artifacts) == content
        files, manifest = inspect_package(content, hashlib.sha256(content).hexdigest())
        assert manifest["template_version"] == "executable-design-v11"
        assert files["backend/approved.sql"] == artifacts["ddl.sql"]
        assert b'"calculations"' in files["design/revised/functions.md"]


@pytest.mark.parametrize(
    "mutation",
    [
        "unit",
        "column",
        "cycle",
        "missing_binding",
        "missing_case",
        "writes",
        "window",
        "wrong_return",
        "precision",
        "unknown_input",
        "float",
        "unbounded",
    ],
)
def test_invalid_ambiguous_or_unbounded_queries_fail_before_generation(mutation):
    bundle, state, _ = calculation_case()
    data = bundle.model_dump(mode="json")
    q = data["domain"]["calculations"][0]
    if mutation == "unit":
        q["calculations"][0]["result"]["unit"] = {"money": 1}
    elif mutation == "column":
        q["aggregates"][1]["column_id"] = "no-column"
    elif mutation == "cycle":
        q["calculations"][0]["left"] = {"kind": "calculated", "calculation_id": "ratio"}
    elif mutation == "missing_binding":
        q["input_bindings"].pop()
    elif mutation == "missing_case":
        data["acceptance_cases"] = [
            c for c in data["acceptance_cases"] if c["id"] != "TC-summary-failure"
        ]
    elif mutation == "writes":
        data["use_cases"][-1]["transaction"] = "atomic"
    elif mutation == "window":
        q["windows"][0]["end_field_id"] = "QI-id"
    elif mutation == "wrong_return":
        q["returns"]["QO-total"] = {"kind": "aggregate", "aggregate_id": "missing"}
    elif mutation == "precision":
        q["aggregates"][0]["result"]["precision"] = 39
    elif mutation == "unknown_input":
        q["calculations"][0]["right"]["field_id"] = "QI-missing"
    elif mutation == "float":
        q["calculations"][0]["left"] = {"kind": "number", "value": 0.1, "unit": {}}
    else:
        q["max_rows"] = 10001
    with pytest.raises((ValueError, Unsupported)):
        compile_contract(SpecBundle.model_validate(data), state)


def test_v08_hash_has_no_new_default_fields_and_real_prior_packages_still_inspect():
    from command_support import atomic_case

    old, _, _ = atomic_case()
    domain = json.loads(canonical_bytes(old))["domain"]
    assert "calculations" not in domain
    assert "calculations" not in domain["commands"][0]
    assert "column_units" not in domain["commands"][0]


def test_calculated_result_must_match_write_column_units():
    bundle, state, _ = calculated_command()
    data = bundle.model_dump(mode="json")
    data["domain"]["commands"][0]["column_units"][1]["unit"] = {"money": 1}
    with pytest.raises(Unsupported, match=r"단위|타입"):
        compile_contract(SpecBundle.model_validate(data), state)


def test_proposal_and_structural_derivation_cannot_remove_saved_queries():
    from specton.specification.completion import validate_proposal
    from specton.specification.domain import derive

    bundle, state, _ = calculation_case()
    data = bundle.model_dump(mode="json")
    data["domain"]["calculations"] = []
    # Removing only the contract would also violate read-only API binding;
    # remove its objects to prove the proposal preservation gate is independent.
    data["apis"] = [a for a in data["apis"] if a["id"] != "API-summary"]
    data["use_cases"] = [u for u in data["use_cases"] if u["id"] != "UC-summary"]
    data["screens"] = [s for s in data["screens"] if s["id"] != "SCREEN-summary"]
    data["acceptance_cases"] = [
        c for c in data["acceptance_cases"] if not c["id"].startswith("TC-summary")
    ]
    for coverage in data["domain"]["coverage"]:
        coverage["api_ids"] = [a for a in coverage["api_ids"] if a != "API-summary"]
    with pytest.raises(ValueError, match="계산·집계 계약"):
        validate_proposal(bundle, SpecBundle.model_validate(data))
    with pytest.raises(ValueError, match="덮어쓸"):
        derive(bundle, state)


def test_record_policy_preserves_v09_queries():
    from test_record_contract import policy

    from specton.specification.record_contract import apply_record_contract

    bundle, _, _ = calculation_case()
    result = apply_record_contract(bundle, policy(bundle))
    assert result.schema_version == "spec-v0.9" and result.domain == bundle.domain


def test_numeric_filter_units_and_constant_precision_are_checked():
    from specton.contracts.calculations import NumericLiteral

    with pytest.raises(ValueError, match="유효 자릿수"):
        NumericLiteral(value="12345678901234567890123456789012345678.1", unit={})
    bundle, state, _ = calculation_case()
    data = bundle.model_dump(mode="json")
    q = data["domain"]["calculations"][0]
    col = q["aggregates"][1]["column_id"]
    q["filters"].append({"column_id": col, "operator": "ge", "input_field_id": "QI-budget"})
    q["column_units"][0]["unit"] = {"money": 1}
    with pytest.raises(Unsupported, match="필터"):
        compile_contract(SpecBundle.model_validate(data), state)
