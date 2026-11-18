"""stock-ledger-v1의 기계 계약. 자유 설명 대신 승인된 고정 명령에 연결한다."""

from typing import Any

from specton.contracts.specification import SpecBundle

MOVEMENT = [
    ("id", "string"),
    ("warehouse_id", "string"),
    ("item_id", "string"),
    ("kind", "string"),
    ("quantity", "decimal"),
    ("status", "string"),
]
BALANCE = [("warehouse_id", "string"), ("item_id", "string"), ("quantity", "decimal")]
CONTRACTS = {
    "draft": (
        "POST",
        "/inventory/movements",
        201,
        MOVEMENT[:-1],
        MOVEMENT,
        ["DUPLICATE_KEY", "IDEMPOTENCY_CONFLICT", "REFERENCE_NOT_FOUND"],
    ),
    "edit": (
        "PATCH",
        "/inventory/movements/{key}",
        200,
        [("quantity", "decimal")],
        MOVEMENT,
        ["NOT_FOUND", "INVALID_STATE", "IDEMPOTENCY_CONFLICT"],
    ),
    "confirm": (
        "POST",
        "/inventory/movements/{key}/confirm",
        200,
        [],
        MOVEMENT,
        [
            "NOT_FOUND",
            "INVALID_STATE",
            "INSUFFICIENT_STOCK",
            "QUANTITY_OVERFLOW",
            "IDEMPOTENCY_CONFLICT",
        ],
    ),
    "cancel": (
        "POST",
        "/inventory/movements/{key}/cancel",
        200,
        [],
        MOVEMENT,
        [
            "NOT_FOUND",
            "INVALID_STATE",
            "INSUFFICIENT_STOCK",
            "QUANTITY_OVERFLOW",
            "IDEMPOTENCY_CONFLICT",
        ],
    ),
    "movement": (
        "GET",
        "/inventory/movements/{key}",
        200,
        [("key", "string")],
        MOVEMENT,
        ["NOT_FOUND"],
    ),
    "balance": ("GET", "/inventory/balances", 200, BALANCE[:2], BALANCE, ["REFERENCE_NOT_FOUND"]),
}


def compile_inventory(bundle: SpecBundle, stores: dict[str, Any]) -> dict[str, Any] | None:
    from specton.implementation.compiler import Unsupported

    policy = bundle.inventory
    if policy is None:
        return None
    apis = {a.id: a for a in bundle.apis}
    compiled = policy.model_dump(mode="json")
    for name, entity_id in [
        ("warehouse", policy.warehouse_entity_id),
        ("item", policy.item_entity_id),
    ]:
        store = stores[entity_id]
        primary = next(f for f in store["fields"] if f["primary"])
        if primary["data_type"] != "string" or not primary["length"] or primary["length"] > 64:
            raise Unsupported("재고 참조 키는 64자 이하 문자열 기본키여야 합니다.")
        compiled[name] = {
            "table": store["table"],
            "column": primary["column"],
            "length": primary["length"],
        }
    operations = []
    for action, aid in sorted(policy.api_ids.items()):
        api = apis[aid]
        method, path, status, inputs, outputs, errors = CONTRACTS[action]
        if (
            api.method != method
            or api.path != path
            or api.success_status != status
            or [(f.name, f.data_type) for f in api.request_fields] != inputs
            or [(f.name, f.data_type) for f in api.response_fields] != outputs
            or any(not f.required for f in (*api.request_fields, *api.response_fields))
            or api.pagination != "none"
            or set(api.error_codes) != set(errors)
            or api.concurrency != ("read_only" if method == "GET" else "row_lock")
        ):
            raise Unsupported(f"재고 {action}의 경로·입출력·오류·동시성 계약이 맞지 않습니다.")
        operations.append({**api.model_dump(mode="json"), "action": action})
    if any(
        api.path.startswith("/inventory")
        for api in bundle.apis
        if api.id not in policy.api_ids.values()
    ):
        raise Unsupported("재고 경로를 다른 API와 공유할 수 없습니다.")
    compiled["operations"] = operations
    return compiled
