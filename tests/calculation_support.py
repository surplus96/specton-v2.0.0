"""Fixed synthetic numerical oracles in two domains, authored before observing output."""

from command_support import atomic_case

from specton.contracts.specification import SpecBundle
from specton.implementation.calculations import QUERY_ERRORS


def calculation_case(domain="inventory"):
    bundle, state, artifacts = atomic_case(domain)
    data = bundle.model_dump(mode="json")
    data["schema_version"] = "spec-v0.9"
    data["domain"]["version"] = "domain-ir-v3"
    parent, child = state.normalized.tables
    pc = {c.physical_name: c.id for c in parent.columns}
    cc = {c.physical_name: c.id for c in child.columns}
    unit = {"item": 1} if domain == "inventory" else {"kWh": 1}

    def policy(scale=2, dimension=None):
        return {
            "precision": 12,
            "scale": scale,
            "rounding": "half_even",
            "unit": unit if dimension is None else dimension,
        }

    def agg(name):
        return {"kind": "aggregate", "aggregate_id": name}

    fields = [
        {"id": "QI-id", "name": "id", "data_type": "string", "required": True},
        {"id": "QI-start", "name": "start", "data_type": "date", "required": True},
        {"id": "QI-end", "name": "end", "data_type": "date", "required": True},
        {"id": "QI-budget", "name": "budget", "data_type": "decimal", "required": True},
    ]
    response = [
        {"id": "QO-" + n, "name": n, "data_type": "decimal", "required": n != "average"}
        for n in ["count", "total", "average", "minimum", "maximum", "ratio"]
    ]
    rid = data["requirements"][0]["id"]
    use = {
        "id": "UC-summary",
        "name": "기간 수량 집계" if domain == "inventory" else "기간 측정량 집계",
        "req_ids": [rid],
        "actor_roles": ["ROLE-operator"],
        "preconditions": ["승인한 날짜 범위"],
        "inputs": fields,
        "outputs": response,
        "steps": ["범위와 최대 건수 확인", "정확한 소수 집계", "단위와 반올림 적용"],
        "error_codes": sorted(QUERY_ERRORS),
        "transaction": "read_only",
        "idempotency": "not_applicable",
    }
    api = {
        "id": "API-summary",
        "use_case_id": use["id"],
        "method": "POST",
        "path": "/calculations/summary",
        "actor_roles": use["actor_roles"],
        "request_fields": fields,
        "response_fields": response,
        "success_status": 200,
        "error_codes": use["error_codes"],
        "pagination": "none",
        "concurrency": "read_only",
    }
    query = {
        "api_id": api["id"],
        "table_id": child.id,
        "input_bindings": [
            {"field_id": "QI-id", "table_id": parent.id, "column_id": pc["id"]},
            {"field_id": "QI-budget", "table_id": parent.id, "column_id": pc["amount"]},
            *[
                {"field_id": "QI-" + n, "table_id": child.id, "column_id": cc["scheduled"]}
                for n in ["start", "end"]
            ],
        ],
        "column_units": [
            {"table_id": t.id, "column_id": c, "unit": unit}
            for t, c in [(parent, pc["amount"]), (child, cc["amount"])]
        ],
        "filters": [{"column_id": cc["parent_id"], "operator": "eq", "input_field_id": "QI-id"}],
        "windows": [
            {
                "column_id": cc["scheduled"],
                "start_field_id": "QI-start",
                "end_field_id": "QI-end",
                "start_inclusive": True,
                "end_inclusive": False,
            }
        ],
        "max_rows": 3,
        "aggregates": [
            {
                "id": n,
                "operator": operator,
                "column_id": None if n == "count" else cc["amount"],
                "null_policy": "ignore",
                "empty_policy": "null" if n == "average" else "zero",
                "result": policy(0, {}) if n == "count" else policy(),
            }
            for n, operator in [
                ("count", "count"),
                ("total", "sum"),
                ("average", "average"),
                ("minimum", "min"),
                ("maximum", "max"),
            ]
        ],
        "calculations": [
            {
                "id": "ratio",
                "operator": "divide",
                "left": agg("total"),
                "right": {"kind": "input", "field_id": "QI-budget"},
                "result": policy(4, {}),
                "null_policy": "error",
                "zero_division": "error",
            }
        ],
        "returns": {
            "QO-" + n: {"kind": "calculated", "calculation_id": n} if n == "ratio" else agg(n)
            for n in ["count", "total", "average", "minimum", "maximum", "ratio"]
        },
    }
    data["use_cases"].append(use)
    data["apis"].append(api)
    data["screens"].append(
        {
            "id": "SCREEN-summary",
            "route": "/summary",
            "name": use["name"],
            "actor_roles": use["actor_roles"],
            "api_ids": [api["id"]],
            "empty_state": "기간을 입력하세요",
            "loading_state": "계산 중",
            "error_state": "계산 범위와 값을 확인하세요",
        }
    )
    data["domain"]["calculations"] = [query]
    data["domain"]["coverage"][0]["api_ids"].append(api["id"])
    ops = {(o["table_id"], o["action"]): o["api_id"] for o in data["domain"]["operations"]}

    def insert(t, body, key):
        return {
            "api_id": ops[t.id, "insert"],
            "body": body,
            "request_key": key,
            "expect": {"kind": "exact", "status": 200, "body": body},
        }

    seed = [insert(parent, {"id": "one", "name": "fixture", "amount": "5.00"}, "parent")]
    for seq, (when, amount) in enumerate(
        [("2030-01-01", "1.01"), ("2030-01-02", "2.02"), ("2030-02-01", "99.00")], 1
    ):
        seed.append(
            insert(
                child,
                {
                    "parent_id": "one",
                    "sequence": seq,
                    "scheduled": when,
                    "status": "open",
                    "amount": amount,
                },
                "entry-" + str(seq),
            )
        )
    body = {"id": "one", "start": "2030-01-01", "end": "2030-02-01", "budget": "3.00"}
    expected = {
        "count": "2",
        "total": "3.03",
        "average": "1.52",
        "minimum": "1.01",
        "maximum": "2.02",
        "ratio": "1.0100",
    }
    for category, payload, expect in [
        ("normal", body, {"kind": "exact", "status": 200, "body": expected}),
        (
            "boundary",
            {**body, "end": "2030-01-01"},
            {
                "kind": "exact",
                "status": 200,
                "body": {
                    "count": "0",
                    "total": "0.00",
                    "average": None,
                    "minimum": "0.00",
                    "maximum": "0.00",
                    "ratio": "0.0000",
                },
            },
        ),
        (
            "failure",
            {**body, "budget": "0.00"},
            {"kind": "error", "status": 409, "code": "CALCULATION_ERROR"},
        ),
    ]:
        data["acceptance_cases"].append(
            {
                "id": "TC-summary-" + category,
                "req_ids": [rid],
                "use_case_ids": [
                    use["id"],
                    *[
                        a["use_case_id"]
                        for a in data["apis"]
                        if a["id"] in {s["api_id"] for s in seed}
                    ],
                ],
                "tier": "api",
                "given": ["고정 합성 데이터"],
                "when": "기간 집계",
                "then": ["독립 기대값 확인"],
                "fixture_ids": ["FIX-summary"],
                "execution": {
                    "category": category,
                    "steps": [*seed, {"api_id": api["id"], "body": payload, "expect": expect}],
                },
            }
        )
    return SpecBundle.model_validate(data), state, artifacts


def calculated_command(domain="inventory"):
    bundle, state, artifacts = atomic_case(domain)
    data = bundle.model_dump(mode="json")
    data["schema_version"] = "spec-v0.9"
    data["domain"]["version"] = "domain-ir-v3"
    command = data["domain"]["commands"][0]
    field = {"id": "INPUT-divisor", "name": "divisor", "data_type": "integer", "required": True}
    next(a for a in data["apis"] if a["id"] == "API-atomic")["request_fields"].append(field)
    next(u for u in data["use_cases"] if u["id"] == "UC-atomic")["inputs"].append(field)
    child = state.normalized.tables[1]
    seq = next(c.id for c in child.columns if c.physical_name == "sequence")
    command["input_bindings"].append(
        {"field_id": field["id"], "table_id": child.id, "column_id": seq}
    )
    command["column_units"] = [
        {"table_id": t.id, "column_id": c.id, "unit": {"item": 1}}
        for t in state.normalized.tables
        for c in t.columns
        if c.physical_name == "amount"
    ]
    command["calculations"] = [
        {
            "id": "checked-amount",
            "operator": "divide",
            "left": {"kind": "input", "field_id": "INPUT-amount"},
            "right": {"kind": "input", "field_id": "INPUT-divisor"},
            "result": {"precision": 10, "scale": 2, "rounding": "half_even", "unit": {"item": 1}},
            "null_policy": "error",
            "zero_division": "error",
        }
    ]
    command["column_units"].append({"table_id": child.id, "column_id": seq, "unit": {}})
    command["before"].append(
        {
            "left": {"kind": "input", "field_id": "INPUT-divisor"},
            "operator": "gt",
            "right": {"kind": "literal", "value": 0},
        }
    )
    for case in data["acceptance_cases"]:
        if case["execution"]:
            for step in case["execution"]["steps"]:
                if step["api_id"] == "API-atomic":
                    step["body"]["divisor"] = 1
    # Calculate once before writes, then retain the same independently authored command oracles.
    for write in command["writes"]:
        for key, value in write["values"].items():
            if value.get("kind") == "input" and value.get("field_id") == "INPUT-amount":
                write["values"][key] = {"kind": "calculated", "calculation_id": "checked-amount"}
            elif value.get("kind") == "arithmetic":
                value["right"] = {"kind": "calculated", "calculation_id": "checked-amount"}
    for group in [data["apis"], data["use_cases"]]:
        next(a for a in group if a["id"] in {"API-atomic", "UC-atomic"})["error_codes"].append(
            "CALCULATION_ERROR"
        )
    return SpecBundle.model_validate(data), state, artifacts
