import hashlib
import json
from pathlib import Path

import pytest
from implementation_support import collection_executable
from pydantic import ValidationError

from specton.contracts import DesignState
from specton.contracts.specification import SpecBundle
from specton.implementation.compiler import Unsupported, compile_contract
from specton.implementation.package import generate
from specton.implementation.verify import inspect_package
from specton.specification.completion import validate_proposal
from specton.specification.documents import revised_files

ROOT = Path("tests/fixtures/implementation")


def inputs():
    b = SpecBundle.model_validate_json((ROOT / "spec/approved-spec.json").read_bytes())
    s = DesignState.model_validate_json((ROOT / "spec/design-state.json").read_bytes())
    a = {p.name: p.read_bytes() for p in (ROOT / "design").iterdir()}
    return b, s, a


def test_list_update_require_explicit_version_and_concurrency():
    b, state, artifacts = inputs()
    data = collection_executable(b.model_dump(mode="json"))
    proposal = SpecBundle.model_validate(data)
    contract = compile_contract(proposal, state)
    assert {"list", "update"} <= {op["action"] for op in contract["operations"]}
    package = generate(proposal, state, artifacts)
    files, _ = inspect_package(package, hashlib.sha256(package).hexdigest())
    assert "design/revised/functions.md" in files
    data["schema_version"] = "spec-v0.2"
    with pytest.raises(ValidationError):
        SpecBundle.model_validate(data)
    data["schema_version"] = "spec-v0.4"
    data["apis"][-1]["concurrency"] = "optimistic"
    with pytest.raises(Unsupported):
        compile_contract(SpecBundle.model_validate(data), state)


def test_revised_design_changes_screen_and_preserves_source_schema():
    b, _, originals = inputs()
    data = b.model_dump(mode="json")
    data["screens"][0]["name"] = "고객 상품 정보"
    revised = revised_files(SpecBundle.model_validate(data), originals)
    assert "고객 상품 정보" in revised["functions.md"].decode()
    assert revised["ddl.sql"] == originals["ddl.sql"]
    assert revised["erd.mmd"] == originals["erd.mmd"]
    assert json.loads(revised["manifest.json"])["business_acceptance"] == "not_run"
    with pytest.raises(ValueError):
        revised_files(b, {**originals, "ddl.sql": b"tampered"})


def test_completion_cannot_forge_answers_or_provenance():
    b, _, _ = inputs()
    validate_proposal(b, b)
    data = b.model_dump(mode="json")
    data["questions"][0]["answer"] = "AI decided this policy"
    with pytest.raises(ValueError, match="답변"):
        validate_proposal(b, SpecBundle.model_validate(data))
    data = b.model_dump(mode="json")
    data["baseline"]["model_hash"] = "0" * 64
    with pytest.raises(ValueError, match="출처"):
        validate_proposal(b, SpecBundle.model_validate(data))


def test_decimal_demo_preserves_ddl_limits_and_rejects_out_of_range_values():
    import ast
    from decimal import Decimal

    from pydantic import ConfigDict, Field, StrictBool, StrictInt, StrictStr, create_model

    from specton.specification.demo import demo_draft

    current, state, _ = inputs()
    table_id = current.storage_bindings[0].table_id
    data = state.model_dump(mode="json")
    table = next(t for t in data["normalized"]["tables"] if t["id"] == table_id)
    column = next(c for c in table["columns"] if c["id"] not in table["primary_key"])
    column.update(data_type="numeric", length=None, precision=5, scale=2)
    state = DesignState.model_validate(data)
    initial = current.model_copy(
        update={"requirements": tuple(r for r in current.requirements if r.id != "REQ-masterdata")}
    )
    proposal = demo_draft(initial, state, table_id, "데모")
    operation = compile_contract(proposal, state)["operations"][0]
    decimal = next(f for f in operation["fields"] if f["data_type"] == "decimal")
    assert (decimal["precision"], decimal["scale"]) == (5, 2)
    # Execute the generated runtime's actual model factory, without booting its DB/API.
    template = Path("specton/implementation/templates/runtime/app.py.txt").read_text()
    factory = next(
        n
        for n in ast.parse(template).body
        if isinstance(n, ast.FunctionDef) and n.name == "model_for"
    )
    namespace = dict(
        __name__=__name__,
        Decimal=Decimal,
        ConfigDict=ConfigDict,
        Field=Field,
        StrictBool=StrictBool,
        StrictInt=StrictInt,
        StrictStr=StrictStr,
        create_model=create_model,
    )
    exec(compile(ast.Module(body=[factory], type_ignores=[]), "generated-model", "exec"), namespace)
    model = namespace["model_for"](operation)
    payload = {f["name"]: "a" for f in operation["fields"]}
    name = decimal["name"]
    assert (
        model.model_validate({**payload, name: "999.99"}).model_dump(mode="json")[name] == "999.99"
    )
    for value in ("1000.00", "0.001", "NaN", "Infinity"):
        with pytest.raises(ValidationError):
            model.model_validate({**payload, name: value})
    previous = proposal.model_dump(mode="json")
    previous["schema_version"] = "spec-v0.2"
    with pytest.raises(Unsupported):
        compile_contract(SpecBundle.model_validate(previous), state)
