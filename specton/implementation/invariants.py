"""Compile approved field comparisons; no expressions or SQL are evaluated."""

from typing import Any

from specton.contracts.specification import FieldRef, SpecBundle, SpecField, ValueExpression


def operand(value: ValueExpression, fields: dict[str, SpecField]) -> dict[str, Any]:
    if isinstance(value, FieldRef):
        return {"kind": "field", "name": fields[value.field_id].name}
    return value.model_dump(mode="json")


def bind_invariants(bundle: SpecBundle, operations: list[dict[str, Any]]) -> None:
    from specton.implementation.compiler import Unsupported

    bindings = {b.entity_id: b for b in bundle.storage_bindings}
    entities = {e.id: e for e in bundle.entities}
    for invariant in bundle.invariants:
        if set(invariant.layers) != {"api"}:
            raise Unsupported(
                "업무 조건의 DB CHECK 생성은 미지원입니다. API 적용 범위를 명시하세요."
            )
        refs = [
            v for c in invariant.comparisons for v in (c.left, c.right) if isinstance(v, FieldRef)
        ]
        eids = {r.entity_id for r in refs}
        if len(eids) != 1:
            raise Unsupported(
                "필드 간 조건은 한 엔티티 안에서만 지원합니다. "
                "교차 데이터 조회는 추가 구현이 필요합니다."
            )
        eid = next(iter(eids))
        if eid not in bindings:
            raise Unsupported("업무 조건의 저장 연결이 없습니다.")
        binding = bindings[eid]
        targets = [
            o for o in operations if o["table_id"] == binding.table_id and o["action"] != "list"
        ]
        if not targets:
            raise Unsupported("업무 조건을 적용할 변경 동작이 없습니다.")
        cases = {u.id: u for u in bundle.use_cases}
        if not set(invariant.req_ids) <= {
            rid for op in targets for rid in cases[op["use_case_id"]].req_ids
        }:
            raise Unsupported("업무 조건과 적용 API의 요구사항 연결이 다릅니다.")
        if any("RULE_VIOLATION" not in op["error_codes"] for op in targets):
            raise Unsupported("조건 위반을 반환할 RULE_VIOLATION 오류 계약이 필요합니다.")
        fields = {f.id: f for f in entities[eid].fields}
        if any(not fields[r.field_id].required for r in refs):
            raise Unsupported(
                "선택 입력의 null 비교 정책은 미지원입니다. 조건 대상은 필수 필드여야 합니다."
            )

        rule = {
            "id": invariant.id,
            "req_ids": list(invariant.req_ids),
            "match": invariant.match,
            "comparisons": [
                {
                    "operator": c.operator,
                    "left": operand(c.left, fields),
                    "right": operand(c.right, fields),
                }
                for c in invariant.comparisons
            ],
        }
        for op in targets:
            op.setdefault("invariants", []).append(rule)
