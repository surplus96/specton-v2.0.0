import importlib.machinery
import importlib.util
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from domain_support import case, reviewed
from fastapi import HTTPException
from invariant_support import quantity_bounds

from specton.contracts.specification import SpecBundle
from specton.implementation.compiler import Unsupported
from specton.implementation.domain import compile_domain


def runtime():
    path = Path("specton/implementation/templates/runtime/domain.py.txt")
    loader = importlib.machinery.SourceFileLoader("generated_domain", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_invariants_attach_to_every_write_and_keep_exact_fields():
    draft, state, _ = case()
    bundle = quantity_bounds(reviewed(draft))
    config = compile_domain(bundle, state)
    writes = [o for o in config["domain"]["operations"] if o.get("invariants")]
    assert {o["action"] for o in writes} == {"insert", "update"}
    enforce = runtime().enforce_invariants
    for op in writes:
        for value in (Decimal("0"), Decimal("0.5"), Decimal("1")):
            enforce(op, {"amount": value, "sequence": 1})
        for value in (Decimal("-0.01"), Decimal("1.01"), None):
            with pytest.raises(HTTPException) as error:
                enforce(op, {"amount": value, "sequence": 1})
            assert error.value.status_code == 409


def test_database_and_cross_entity_rules_are_explicitly_rejected():
    draft, state, _ = case()
    bundle = quantity_bounds(reviewed(draft))
    data = bundle.model_dump(mode="json")
    data["invariants"][0]["layers"] = ["database"]
    with pytest.raises(Unsupported, match="DB CHECK"):
        compile_domain(SpecBundle.model_validate(data), state)
    data = bundle.model_dump(mode="json")
    field = data["entities"][0]["fields"][0]
    data["invariants"][0]["comparisons"].append(
        {
            "operator": "ne",
            "left": {
                "kind": "field",
                "entity_id": data["entities"][0]["id"],
                "field_id": field["id"],
            },
            "right": {"kind": "text", "value": "excluded"},
        }
    )
    with pytest.raises(Unsupported, match="한 엔티티"):
        compile_domain(SpecBundle.model_validate(data), state)


def test_any_and_date_comparison_use_typed_values():
    rule = {
        "match": "any",
        "comparisons": [
            {
                "operator": "le",
                "left": {"kind": "field", "name": "start"},
                "right": {"kind": "field", "name": "end"},
            },
            {
                "operator": "eq",
                "left": {"kind": "field", "name": "waived"},
                "right": {"kind": "boolean", "value": True},
            },
        ],
    }
    enforce = runtime().enforce_invariants
    values = {"start": date(2030, 1, 2), "end": date(2030, 1, 1), "waived": False}
    with pytest.raises(HTTPException):
        enforce({"invariants": [rule]}, values)
    enforce({"invariants": [rule]}, {**values, "waived": True})
    enforce({"invariants": [rule]}, {**values, "end": date(2030, 1, 2)})
