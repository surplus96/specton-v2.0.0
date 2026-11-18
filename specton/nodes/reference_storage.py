"""Bind sizes of explicitly declared FK fields in a new draft, before normalization.

No name-based relationship inference, SQL-type conversion, NULL/key changes or approved data edits.
Conflicting anchors/standards remain unchanged so the existing normalizer can report the conflict.
"""

from pathlib import Path
from typing import Any

from specton.contracts import DesignState
from specton.nodes.a03_entities import load_pack_context
from specton.review.standard_compliance import storage_type_policy

_FIELDS = ("data_type", "length", "precision", "scale")


def bind_reference_storage(design: DesignState, *, root: Path) -> DesignState:
    attributes = {a.id: a for e in design.entities for a in e.attributes}
    entities = {e.id: e for e in design.entities}
    neighbors: dict[str, set[str]] = {}
    children: set[str] = set()
    for relation in design.relationships:
        parent, child = entities.get(relation.parent), entities.get(relation.child)
        if parent is None or child is None:
            continue
        keys = {a.id for a in parent.attributes if a.is_key}
        fields = {a.id for a in child.attributes}
        for binding in relation.fk_bindings or ():
            p, c = binding.parent_attribute_id, binding.child_attribute_id
            if p not in keys or c not in fields:
                continue  # The normalizer still rejects invalid references.
            neighbors.setdefault(p, set()).add(c)
            neighbors.setdefault(c, set()).add(p)
            children.add(c)
    if not neighbors:
        return design
    pack = design.versions.pack_id
    if pack is None:
        raise ValueError("FK 저장 정책에 실행 팩이 필요합니다")
    policy = storage_type_policy(pack, root=root)
    terms = {t.term: t for t in load_pack_context(pack, root=root).terms}
    visited: set[str] = set()
    replacements = {}
    for start in sorted(neighbors):
        if start in visited:
            continue
        component: set[str] = set()
        pending = [start]
        while pending:
            node = pending.pop()
            if node in component:
                continue
            component.add(node)
            pending.extend(neighbors[node] - component)
        visited.update(component)
        anchors = component - children
        if not anchors:
            continue  # Cycles have no authoritative root; do not guess.
        signatures = {tuple(getattr(attributes[i], f) for f in _FIELDS) for i in anchors}
        if len(signatures) != 1:
            continue
        signature = next(iter(signatures))
        changes: dict[str, Any] = dict(zip(_FIELDS, signature, strict=True))
        candidates = {}
        for key in sorted(component - anchors):
            old = attributes[key]
            if old.data_type != changes["data_type"]:
                break  # Only size alignment; a type conversion needs explicit review.
            candidate = old.evolve(**changes)
            term = terms.get(candidate.name)
            if policy.problems(candidate) or (
                term is not None and any(getattr(candidate, f) != getattr(term, f) for f in _FIELDS)
            ):
                break  # Keep the entire component unchanged, never a partially valid graph.
            if any(getattr(old, f) != getattr(candidate, f) for f in _FIELDS):
                basis = ", ".join(sorted(anchors))
                before = (old.length, old.precision, old.scale)
                after = (candidate.length, candidate.precision, candidate.scale)
                note = f"[FK 저장 타입 정책: {basis}; 길이/정밀도/소수 {before} → {after}]"
                candidates[key] = candidate.evolve(
                    description=((old.description or "") + "\n" + note).strip()
                )
        else:
            replacements.update(candidates)
    if not replacements:
        return design
    return design.evolve(
        entities=tuple(
            e.evolve(attributes=tuple(replacements.get(a.id, a) for a in e.attributes))
            for e in design.entities
        ),
        normalized=None,
    )
