"""Synthetic commands in two schemas; rules and expected values are fixed before execution."""

import hashlib
import json
from copy import deepcopy

from domain_support import case, reviewed

from specton.contracts import DesignState
from specton.contracts.specification import SpecBundle
from specton.implementation.commands import COMMAND_ERRORS
from specton.model_hash import model_hash
from specton.specification.domain import derive


def atomic_case(domain="inventory"):
    draft, original, _ = case("booking" if domain == "inventory" else "maintenance")
    raw = original.model_dump(mode="json")
    if domain == "inventory":
        raw = json.loads(
            json.dumps(raw, ensure_ascii=False)
            .replace("rooms", "balances")
            .replace("reservations", "movements")
            .replace("회의실", "잔고")
            .replace("예약", "변경 이력")
        )
    parent, child = raw["normalized"]["tables"]
    amount = deepcopy(next(c for c in child["columns"] if c["physical_name"] == "amount"))
    amount.update(id="COL-parent-amount", attribute_id="ATTR-parent-amount")
    parent["columns"].append(amount)
    state = DesignState.model_validate(raw)
    data = draft.model_dump(mode="json")
    data["baseline"]["model_hash"] = model_hash(state)
    p, c = parent["physical_name"], child["physical_name"]
    ddl = (
        f"CREATE TABLE {p}(id varchar(32) PRIMARY KEY,name varchar(32) NOT NULL,"
        "amount numeric(10,2) NOT NULL);\n"
        f"CREATE TABLE {c}(parent_id varchar(32) REFERENCES {p},sequence integer,"
        "scheduled date NOT NULL,status varchar(32) NOT NULL,amount numeric(10,2) NOT NULL,"
        "PRIMARY KEY(parent_id,sequence));"
    )
    artifacts = {
        "ddl.sql": ddl.encode(),
        "erd.mmd": f"erDiagram\n {p} ||--o{{ {c} : entries\n".encode(),
        "functions.md": domain.encode(),
        "rtm.csv": b"requirement,function\nREQ-01,atomic\n",
    }
    for a in data["baseline"]["artifacts"]:
        a["sha256"] = hashlib.sha256(artifacts[a["kind"] + "." + a["file_format"]]).hexdigest()
    artifacts["manifest.json"] = json.dumps(
        {k: hashlib.sha256(v).hexdigest() for k, v in artifacts.items()}
    ).encode()
    data["baseline"]["manifest_hash"] = hashlib.sha256(artifacts["manifest.json"]).hexdigest()
    bundle = reviewed(derive(SpecBundle.model_validate(data), state))
    data = bundle.model_dump(mode="json")
    data["schema_version"] = "spec-v0.8"
    data["domain"]["version"] = "domain-ir-v2"
    for q in data["questions"]:
        q["answer"] = "합성 인수 시험에서 고정한 업무 규칙"
    # Privileged fixture preparation is explicitly separate from command execution.
    data["roles"] = [
        {"id": "ROLE-admin", "name": "기준 데이터 관리자"},
        {"id": "ROLE-operator", "name": "명령 실행자"},
    ]
    for u in data["use_cases"]:
        u["actor_roles"] = ["ROLE-admin"]
    for a in data["apis"]:
        a["actor_roles"] = ["ROLE-admin"]
    for screen in data["screens"]:
        screen["actor_roles"] = ["ROLE-admin"]
    ops = {(o["table_id"], o["action"]): o["api_id"] for o in data["domain"]["operations"]}
    bycol = {
        t["id"]: {col["physical_name"]: col["id"] for col in t["columns"]} for t in (parent, child)
    }

    def inp(n):
        return {"kind": "input", "field_id": "INPUT-" + n}

    def lit(v):
        return {"kind": "literal", "value": v}

    def row(t, n):
        return {
            "kind": "row",
            "target": t,
            "column_id": bycol[parent["id"] if t == "balance" else child["id"]][n],
        }

    fields = [
        {"id": "INPUT-id", "name": "id", "data_type": "string", "required": True},
        {"id": "INPUT-sequence", "name": "sequence", "data_type": "integer", "required": True},
        {"id": "INPUT-scheduled", "name": "scheduled", "data_type": "date", "required": True},
        {"id": "INPUT-amount", "name": "amount", "data_type": "decimal", "required": True},
    ]
    response = [
        {"id": "OUTPUT-amount", "name": "amount", "data_type": "decimal", "required": True},
        {"id": "OUTPUT-status", "name": "status", "data_type": "string", "required": True},
    ]
    rid = data["requirements"][0]["id"]
    use = {
        "id": "UC-atomic",
        "name": "출고와 이력 확정" if domain == "inventory" else "측정과 점검 상태 저장",
        "req_ids": [rid],
        "actor_roles": ["ROLE-operator"],
        "preconditions": ["검토한 대상과 조건"],
        "inputs": fields,
        "outputs": response,
        "steps": ["대상 잠금", "값 변경과 결과 기록", "실패 시 전체 복구"],
        "error_codes": sorted(COMMAND_ERRORS),
        "transaction": "atomic",
        "idempotency": "key",
    }
    data["use_cases"].append(use)
    api = {
        "id": "API-atomic",
        "use_case_id": use["id"],
        "method": "POST",
        "path": "/commands/save",
        "actor_roles": use["actor_roles"],
        "request_fields": fields,
        "response_fields": response,
        "success_status": 200,
        "error_codes": use["error_codes"],
        "pagination": "none",
        "concurrency": "row_lock",
    }
    data["apis"].append(api)
    data["screens"].append(
        {
            "id": "SCREEN-atomic",
            "route": "/commands",
            "name": use["name"],
            "actor_roles": ["ROLE-operator"],
            "api_ids": [api["id"]],
            "empty_state": "값을 입력하세요",
            "loading_state": "변경 처리 중",
            "error_state": "전체 변경이 취소되었습니다",
        }
    )
    command = {
        "api_id": api["id"],
        "input_bindings": [
            {"field_id": "INPUT-" + n, "table_id": t["id"], "column_id": bycol[t["id"]][col]}
            for n, t, col in [
                ("id", parent, "id"),
                ("sequence", child, "sequence"),
                ("scheduled", child, "scheduled"),
                ("amount", parent, "amount"),
            ]
        ],
        "targets": [
            {
                "id": "balance",
                "table_id": parent["id"],
                "mode": "update",
                "keys": {bycol[parent["id"]]["id"]: inp("id")},
            },
            {
                "id": "entry",
                "table_id": child["id"],
                "mode": "insert" if domain == "inventory" else "update",
                "keys": {
                    bycol[child["id"]]["parent_id"]: inp("id"),
                    bycol[child["id"]]["sequence"]: inp("sequence"),
                },
            },
        ],
        "before": [
            {
                "left": inp("amount"),
                "operator": "gt" if domain == "inventory" else "ge",
                "right": lit("0.00"),
            }
        ],
        "writes": [
            {
                "target": "balance",
                "values": {
                    bycol[parent["id"]]["amount"]: {
                        "kind": "arithmetic",
                        "operator": "subtract",
                        "left": row("balance", "amount"),
                        "right": inp("amount"),
                    }
                    if domain == "inventory"
                    else inp("amount")
                },
            },
            {
                "target": "entry",
                "values": {
                    bycol[child["id"]]["scheduled"]: inp("scheduled"),
                    bycol[child["id"]]["status"]: lit(
                        "posted" if domain == "inventory" else "review"
                    ),
                    bycol[child["id"]]["amount"]: inp("amount"),
                },
            },
        ],
        "after": [{"left": row("balance", "amount"), "operator": "ge", "right": lit("0.00")}],
        "returns": {
            "OUTPUT-amount": row("balance", "amount"),
            "OUTPUT-status": row("entry", "status"),
        },
    }
    if domain != "inventory":
        command["before"].append(
            {"left": row("entry", "status"), "operator": "eq", "right": lit("open")}
        )
        command["after"].append(
            {"left": row("balance", "amount"), "operator": "le", "right": lit("100.00")}
        )
    data["domain"]["commands"] = [command]
    data["domain"]["coverage"][0]["api_ids"].append(api["id"])

    def step(a, body=None, key=None, expect=None, error=None):
        return {
            "api_id": a,
            "body": body,
            "request_key": key,
            "expect": {"kind": "error", "status": 409, "code": error}
            if error
            else {"kind": "exact", "status": 200, "body": expect if expect is not None else body},
        }

    for category, amount in [
        ("normal", "2.00"),
        ("boundary", "5.00" if domain == "inventory" else "0.00"),
        ("failure", "6.00" if domain == "inventory" else "101.00"),
    ]:
        steps = [
            step(
                ops[(parent["id"], "insert")],
                {"id": "one", "name": "fixture", "amount": "5.00"},
                "seed-parent",
            )
        ]
        entry = {
            "parent_id": "one",
            "sequence": 1,
            "scheduled": "2030-01-01",
            "status": "open",
            "amount": "0.00",
        }
        if domain != "inventory":
            steps.append(step(ops[(child["id"], "insert")], entry, "seed-child"))
        body = {"id": "one", "sequence": 1, "scheduled": "2030-01-01", "amount": amount}
        expected = {
            "amount": ("3.00" if category == "normal" else "0.00")
            if domain == "inventory"
            else amount,
            "status": "posted" if domain == "inventory" else "review",
        }
        steps.append(
            step(
                api["id"],
                body,
                "command",
                expected,
                error="RULE_VIOLATION" if category == "failure" else None,
            )
        )
        if category != "failure":
            steps.append(step(api["id"], body, "command", expected))
        final = "5.00" if category == "failure" else expected["amount"]
        steps.append(
            step(
                ops[(parent["id"], "list")],
                expect=[{"id": "one", "name": "fixture", "amount": final}],
            )
        )
        refs = {s["api_id"] for s in steps}
        data["acceptance_cases"].append(
            {
                "id": "TC-command-" + category,
                "req_ids": [rid],
                "use_case_ids": [a["use_case_id"] for a in data["apis"] if a["id"] in refs],
                "tier": "api",
                "given": ["빈 DB와 명시한 초기 값"],
                "when": "원자 명령 처리",
                "then": ["고정한 결과와 전체 변경 확인"],
                "fixture_ids": ["command-fixed"],
                "execution": {"category": category, "steps": steps},
            }
        )
    return SpecBundle.model_validate(data), state, artifacts
