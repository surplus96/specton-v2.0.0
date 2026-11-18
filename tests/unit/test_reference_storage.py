import pytest

from specton.contracts import DesignState, Entity, Relationship
from specton.nodes.reference_storage import bind_reference_storage
from specton.packs.build import DEFAULT_ROOT


def entity(number, name, length, *, data_type="varchar"):
    return Entity(
        id=f"ENT-{number}",
        pack="inventory",
        name=f"대상{number}",
        description="합성 참조",
        req_ids=["REQ-01"],
        attributes=[
            {
                "id": f"ATTR-{number}",
                "name": name,
                "data_type": data_type,
                "length": length,
                "is_key": True,
                "nullable": False,
                "req_ids": ["REQ-01"],
            }
        ],
    )


def relationship(parent, child):
    return Relationship(
        id=f"REL-{parent}-{child}",
        parent=f"ENT-{parent}",
        child=f"ENT-{child}",
        cardinality="1:N",
        optional=False,
        identifying=False,
        req_ids=["REQ-01"],
        rationale="명시적 기존 키 참조",
        fk_bindings=[
            {
                "parent_attribute_id": f"ATTR-{parent}",
                "child_attribute_id": f"ATTR-{child}",
            }
        ],
    )


def state(entities, relationships):
    return DesignState(
        run_id="test-only",
        versions={"pack_id": "inventory"},
        entities=entities,
        relationships=relationships,
    )


def test_explicit_chain_aligns_sizes_without_changing_keys_nullability_or_source():
    before = state(
        [entity(1, "재고번호", 100), entity(2, "출발재고번호", 20), entity(3, "도착재고번호", 30)],
        [relationship(1, 2), relationship(2, 3)],
    )
    after = bind_reference_storage(before, root=DEFAULT_ROOT)
    assert [e.attributes[0].length for e in after.entities] == [100, 100, 100]
    assert [e.attributes[0].length for e in before.entities] == [100, 20, 30]
    assert after.relationships == before.relationships
    for old, new in zip(before.entities, after.entities, strict=True):
        a, b = old.attributes[0], new.attributes[0]
        assert (a.id, a.name, a.req_ids, a.is_key, a.nullable) == (
            b.id,
            b.name,
            b.req_ids,
            b.is_key,
            b.nullable,
        )
    assert "FK 저장 타입 정책" in after.entities[1].attributes[0].description
    assert bind_reference_storage(after, root=DEFAULT_ROOT) == after


@pytest.mark.parametrize(
    "case",
    ["no_binding", "standard_conflict", "pack_conflict", "two_roots", "cycle", "type_conflict"],
)
def test_conflicts_are_not_hidden_by_guessing_or_partial_rewrites(case):
    entities = [entity(1, "재고번호", 100), entity(2, "출발재고번호", 20)]
    relations = [relationship(1, 2)]
    if case == "no_binding":
        relations = [relations[0].evolve(fk_bindings=None)]
    elif case == "standard_conflict":
        entities[1] = entity(2, "항목번호", 10)
    elif case == "pack_conflict":
        entities[1] = entity(2, "품목코드", 10)
    elif case == "two_roots":
        entities.append(entity(3, "다른번호", 50))
        relations.append(relationship(3, 2))
    elif case == "cycle":
        relations.append(relationship(2, 1))
    else:
        entities[1] = entity(2, "출발재고번호", None, data_type="integer")
    before = state(entities, relations)
    assert bind_reference_storage(before, root=DEFAULT_ROOT) == before
