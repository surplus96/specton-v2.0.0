"""Explicitly bounded demo proposal; no fabricated source approval or business completion."""

from specton.contracts import DesignState
from specton.contracts.specification import SpecBundle


def demo_draft(
    current: SpecBundle, state: DesignState, table_id: str, screen_name: str
) -> SpecBundle:
    if state.normalized is None:
        raise ValueError("승인 정규화 설계가 필요합니다.")
    bundle = current.model_dump(mode="json")
    table = next(
        t
        for t in state.normalized.tables
        if t.id == table_id
        and len(t.primary_key) == 1
        and all(
            c.data_type.value in {"varchar", "integer", "boolean", "numeric"} for c in t.columns
        )
        and not any(f.table_id == t.id for f in state.normalized.foreign_keys)
    )
    fields = [
        {
            "id": f"FIELD-value{i}",
            "name": c.physical_name,
            "data_type": {
                "varchar": "string",
                "integer": "integer",
                "boolean": "boolean",
                "numeric": "decimal",
            }[c.data_type.value],
            "required": not c.nullable,
        }
        for i, c in enumerate(table.columns)
    ]
    primary = next(fields[i] for i, c in enumerate(table.columns) if c.id == table.primary_key[0])
    for r in bundle["requirements"]:
        r.update(
            priority="Won't",
            requires_ui=False,
            rationale="데모 연결 검증 범위 밖의 업무는 후속 구현 대상으로 보존합니다.",
        )
    bundle["requirements"].append(
        {
            "id": "REQ-masterdata",
            "text": "기준정보 등록과 단건 조회",
            "kind": "FR",
            "priority": "Must",
            "origin": "user",
            "legacy_id": None,
            "rationale": "데모 검증 범위이며 고객 요구의 구현 완료가 아닙니다.",
            "requires_ui": True,
        }
    )
    for q in bundle["questions"]:
        q["answer"] = "데모 등록·조회만 시험합니다. 원래 업무 정책의 승인이 아닙니다."
    bundle.update(
        schema_version="spec-v0.4",
        roles=[{"id": "ROLE-operator", "name": "처리 담당자"}],
        entities=[
            {
                "id": "ENTITY-master",
                "legacy_id": table.entity_id,
                "name": table.name,
                "fields": fields,
            }
        ],
        use_cases=[],
        apis=[],
        screens=[],
        acceptance_cases=[],
        invariants=[],
        storage_bindings=[
            {
                "entity_id": "ENTITY-master",
                "table_id": table.id,
                "columns": {f["id"]: c.id for f, c in zip(fields, table.columns, strict=True)},
            }
        ],
        operation_bindings=[],
    )
    for action in ("insert", "get"):
        uid, aid = "UC-" + action, "API-" + action
        inputs = fields if action == "insert" else [primary]
        errors = ["DUPLICATE_KEY", "IDEMPOTENCY_CONFLICT"] if action == "insert" else ["NOT_FOUND"]
        bundle["use_cases"].append(
            {
                "id": uid,
                "name": action,
                "req_ids": ["REQ-masterdata"],
                "actor_roles": ["ROLE-operator"],
                "preconditions": ["데모 토큰 인증"],
                "inputs": inputs,
                "steps": [action],
                "outputs": fields,
                "error_codes": errors,
                "transaction": "atomic" if action == "insert" else "read_only",
                "idempotency": "key" if action == "insert" else "not_applicable",
            }
        )
        bundle["apis"].append(
            {
                "id": aid,
                "use_case_id": uid,
                "method": "POST" if action == "insert" else "GET",
                "path": "/records" if action == "insert" else "/records/{key}",
                "actor_roles": ["ROLE-operator"],
                "request_fields": inputs,
                "response_fields": fields,
                "success_status": 201 if action == "insert" else 200,
                "error_codes": errors,
                "pagination": "none",
                "concurrency": "optimistic" if action == "insert" else "read_only",
            }
        )
        bundle["operation_bindings"].append(
            {
                "api_id": aid,
                "entity_id": "ENTITY-master",
                "action": action,
                "key_field_id": primary["id"],
                "key_format": "url-safe-segment",
            }
        )
    bundle["screens"] = [
        {
            "id": "SCREEN-master",
            "route": "/records",
            "name": screen_name,
            "actor_roles": ["ROLE-operator"],
            "api_ids": ["API-insert", "API-get"],
            "empty_state": "자료 없음",
            "loading_state": "처리 중",
            "error_state": "요청 실패",
        }
    ]
    bundle["acceptance_cases"] = [
        {
            "id": "TC-master",
            "req_ids": ["REQ-masterdata"],
            "use_case_ids": ["UC-insert", "UC-get"],
            "tier": "browser",
            "given": ["등록 전"],
            "when": "등록 후 조회",
            "then": ["값이 같다"],
            "fixture_ids": ["synthetic-master"],
        }
    ]
    return SpecBundle.model_validate(bundle)
