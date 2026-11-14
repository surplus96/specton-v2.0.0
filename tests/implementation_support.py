"""생성기 계약 시험용 합성 기준정보 명세. 원래 업무 요구를 충족했다고 주장하지 않는다."""

from copy import deepcopy


def executable(initial, state):
    bundle = deepcopy(initial["bundle"])
    table = next(
        t
        for t in state.normalized.tables
        if len(t.primary_key) == 1
        and all(c.data_type.value in {"varchar", "integer", "boolean"} for c in t.columns)
        and not any(f.table_id == t.id for f in state.normalized.foreign_keys)
    )
    fields = [
        {
            "id": f"FIELD-value{i}",
            "name": f"value{i}",
            "data_type": {"varchar": "string", "integer": "integer", "boolean": "boolean"}[
                c.data_type.value
            ],
            "required": not c.nullable,
        }
        for i, c in enumerate(table.columns)
    ]
    primary = next(fields[i] for i, c in enumerate(table.columns) if c.id == table.primary_key[0])
    for r in bundle["requirements"]:
        r.update(
            priority="Won't",
            requires_ui=False,
            rationale="합성 생성기 시험에서 원래 입출고 업무는 제외한다.",
        )
    bundle["requirements"].append(
        {
            "id": "REQ-masterdata",
            "text": "기준정보 등록과 단건 조회",
            "kind": "FR",
            "priority": "Must",
            "origin": "user",
            "legacy_id": None,
            "rationale": "검증용으로 명시적으로 추가한 제한된 범위",
            "requires_ui": True,
        }
    )
    for q in bundle["questions"]:
        q["answer"] = "원래 업무는 이번 합성 기준정보 시험에서 제외하며 별도 후속 구현한다."
    bundle.update(
        schema_version="spec-v0.2",
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
            "name": "기준정보",
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
    return bundle
