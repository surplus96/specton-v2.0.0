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


def inventory_executable(initial, state):
    from specton.implementation.inventory_contract import CONTRACTS

    bundle = executable(initial, state)
    warehouse = next(
        t for t in state.normalized.tables if t.id == bundle["storage_bindings"][0]["table_id"]
    )
    item = next(t for t in state.normalized.tables if t.name == "품목" and t.id != warehouse.id)
    fields = [
        {
            "id": f"FIELD-item{i}",
            "name": f"item{i}",
            "data_type": "string",
            "required": not c.nullable,
        }
        for i, c in enumerate(item.columns)
    ]
    bundle["entities"].append(
        {"id": "ENTITY-item", "legacy_id": item.entity_id, "name": item.name, "fields": fields}
    )
    bundle["storage_bindings"].append(
        {
            "entity_id": "ENTITY-item",
            "table_id": item.id,
            "columns": {f["id"]: c.id for f, c in zip(fields, item.columns, strict=True)},
        }
    )
    primary = next(fields[i] for i, c in enumerate(item.columns) if c.id == item.primary_key[0])
    for action in ("insert", "get"):
        use = deepcopy(next(u for u in bundle["use_cases"] if u["id"] == "UC-" + action))
        api = deepcopy(next(a for a in bundle["apis"] if a["id"] == "API-" + action))
        use.update(
            id="UC-item-" + action,
            inputs=fields if action == "insert" else [primary],
            outputs=fields,
        )
        api.update(
            id="API-item-" + action,
            use_case_id=use["id"],
            path="/items" if action == "insert" else "/items/{key}",
            request_fields=use["inputs"],
            response_fields=fields,
        )
        bundle["use_cases"].append(use)
        bundle["apis"].append(api)
        bundle["screens"][0]["api_ids"].append(api["id"])
        bundle["operation_bindings"].append(
            {
                "api_id": api["id"],
                "entity_id": "ENTITY-item",
                "action": action,
                "key_field_id": primary["id"],
                "key_format": "url-safe-segment",
            }
        )
    bundle["roles"].append({"id": "ROLE-admin", "name": "취소 관리자"})
    bundle["requirements"].append(
        {
            "id": "REQ-stock",
            "text": "승인한 단일 품목 입출고 정책을 원장과 잔량으로 검증한다.",
            "kind": "FR",
            "priority": "Must",
            "origin": "user",
            "legacy_id": None,
            "rationale": "stock-ledger-v1 합성 인수 범위",
            "requires_ui": True,
        }
    )
    bundle["schema_version"] = "spec-v0.3"
    bundle["inventory"] = {
        "profile": "stock-ledger-v1",
        "storage": "generated-ledger-v1",
        "warehouse_entity_id": "ENTITY-master",
        "item_entity_id": "ENTITY-item",
        "quantity_scale": 3,
        "negative_stock": False,
        "cancel_received": "require_available_stock",
        "api_ids": {},
    }
    for action, (method, path, status, inputs, outputs, errors) in CONTRACTS.items():

        def fields_for(values):
            return [
                {"id": "FIELD-stock-" + name, "name": name, "data_type": dtype, "required": True}
                for name, dtype in values
            ]

        aid, uid = "API-stock-" + action, "UC-stock-" + action
        roles = ["ROLE-admin"] if action == "cancel" else ["ROLE-operator"]
        use = {
            "id": uid,
            "name": action,
            "req_ids": ["REQ-stock"],
            "actor_roles": roles,
            "preconditions": ["역할 확인"],
            "inputs": fields_for(inputs),
            "steps": [action],
            "outputs": fields_for(outputs),
            "error_codes": errors,
            "transaction": "read_only" if method == "GET" else "atomic",
            "idempotency": "not_applicable" if method == "GET" else "key",
        }
        bundle["use_cases"].append(use)
        bundle["apis"].append(
            {
                "id": aid,
                "use_case_id": uid,
                "method": method,
                "path": path,
                "actor_roles": roles,
                "request_fields": use["inputs"],
                "response_fields": use["outputs"],
                "error_codes": errors,
                "success_status": status,
                "pagination": "none",
                "concurrency": "read_only" if method == "GET" else "row_lock",
            }
        )
        bundle["inventory"]["api_ids"][action] = aid
        bundle["screens"].append(
            {
                "id": "SCREEN-stock-" + action,
                "name": action,
                "route": "/stock/" + action,
                "actor_roles": roles,
                "api_ids": [aid],
                "empty_state": "입력하세요",
                "loading_state": "처리 중",
                "error_state": "요청 실패",
            }
        )
    bundle["acceptance_cases"].append(
        {
            "id": "TC-stock",
            "req_ids": ["REQ-stock"],
            "use_case_ids": ["UC-stock-" + action for action in CONTRACTS],
            "tier": "browser",
            "given": ["기준정보가 있다"],
            "when": "입고 확정·출고·취소",
            "then": ["재고 음수 없음", "원장과 잔량 일치"],
            "fixture_ids": ["synthetic-stock-ledger-v1"],
        }
    )
    return bundle
