import hashlib

import pytest
from domain_support import case, reviewed

from specton.implementation.compiler import Unsupported
from specton.implementation.domain import compile_domain
from specton.implementation.package import generate
from specton.implementation.verify import inspect_package
from specton.specification.readiness import assess_readiness


@pytest.mark.parametrize("domain", ["booking", "maintenance"])
def test_domain_uses_actual_tables_keys_relations_and_original_ddl(domain):
    draft, state, artifacts = case(domain)
    assert not assess_readiness(draft).ready_for_review
    assert all(r.priority == "Must" for r in draft.requirements)
    with pytest.raises(Unsupported):
        compile_domain(draft, state)
    spec = reviewed(draft)
    config = compile_domain(spec, state)
    assert len(config["domain"]["operations"]) == 6
    assert len(config["domain"]["operations"][-1]["keys"]) == 2
    assert [s["name"] for s in config["screens"]] == [t.name for t in state.normalized.tables]
    source = generate(spec, state, artifacts)
    files, _ = inspect_package(source, hashlib.sha256(source).hexdigest())
    assert files["backend/approved.sql"] == artifacts["ddl.sql"]
    assert not spec.commerce and not spec.inventory
    assert b"_specton_c_" not in files["backend/approved.sql"]


def test_missing_source_table_is_rejected():
    draft, state, _ = case()
    spec = reviewed(draft)
    missing = spec.model_copy(update={"storage_bindings": spec.storage_bindings[:1]})
    with pytest.raises(Unsupported):
        compile_domain(missing, state)


def test_transition_requires_initial_state_and_preserves_source_schema():
    from domain_support import with_transition

    from specton.contracts.specification import SpecBundle

    draft, state, _ = case()
    spec = with_transition(draft)
    compile_domain(spec, state)
    data = spec.model_dump(mode="json")
    for op in data["domain"]["operations"]:
        if op["action"] == "insert":
            op["guards"] = []
    with pytest.raises(Unsupported):
        compile_domain(SpecBundle.model_validate(data), state)


def test_ai_cannot_silently_reduce_requirements():
    from specton.contracts.specification import SpecBundle
    from specton.specification.completion import validate_proposal

    current, _, _ = case()
    data = current.model_dump(mode="json")
    data["requirements"][0]["priority"] = "Won't"
    with pytest.raises(ValueError, match="축소"):
        validate_proposal(current, SpecBundle.model_validate(data))


def test_declared_function_read_trace_is_kept_without_marking_it_implemented():
    from specton.contracts import Function
    from specton.specification.domain import derive

    current, state, _ = case()
    table = state.normalized.tables[0]
    # Remove one requirement from the table; retain its explicit function->entity read link.
    missing = table.req_ids[-1]
    state = state.evolve(
        normalized=state.normalized.evolve(
            tables=tuple(
                t.evolve(req_ids=tuple(r for r in t.req_ids if r != missing))
                for t in state.normalized.tables
            )
        ),
        functions=(
            Function(
                id="FUNC-read",
                name="선언된 조회",
                description="읽기만 연결",
                req_ids=(missing,),
                entity_ops=({"entity_id": table.entity_id, "operations": ["R"]},),
            ),
        ),
    )
    proposed = derive(current, state)
    requirement = next(r.id for r in proposed.requirements if r.legacy_id == missing)
    coverage = next(c for c in proposed.domain.coverage if c.requirement_id == requirement)
    assert coverage.status == "needs_review" and len(coverage.api_ids) == 1
    op = next(o for o in proposed.domain.operations if o.api_id == coverage.api_ids[0])
    assert op.action == "list" and op.table_id == table.id
