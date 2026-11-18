"""Synthetic, different domains sharing the compiler, not an application profile."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

from specton.contracts import DesignState
from specton.contracts.specification import SpecBundle
from specton.model_hash import model_hash
from specton.specification.domain import derive


def case(domain="booking"):
    root = Path("tests/fixtures/implementation")
    state = json.loads((root / "spec/design-state.json").read_text())
    current = json.loads((root / "spec/approved-spec.json").read_text())
    parent, child = ("rooms", "reservations") if domain == "booking" else ("devices", "inspections")
    labels = ("회의실", "예약") if domain == "booking" else ("설비", "점검")
    prototype = deepcopy(state["normalized"]["tables"][0])
    proto = deepcopy(prototype["columns"][0])
    tables = []
    for _i, (name, label, cols) in enumerate(
        [
            (parent, labels[0], [("id", "varchar", True), ("name", "varchar", False)]),
            (
                child,
                labels[1],
                [
                    ("parent_id", "varchar", True),
                    ("sequence", "integer", True),
                    ("scheduled", "date", False),
                    ("status", "varchar", False),
                    ("amount", "numeric", False),
                ],
            ),
        ]
    ):
        t = deepcopy(prototype)
        t.update(
            id="TBL-" + name,
            entity_id="ENT-" + name,
            name=label,
            physical_name=name,
            columns=[],
            primary_key=[],
            unique_keys=[],
            req_ids=["REQ-01", "REQ-02", "REQ-03"],
        )
        for _n, (column, kind, key) in enumerate(cols):
            c = deepcopy(proto)
            c.update(
                id=f"COL-{name}-{column}",
                attribute_id=f"ATTR-{name}-{column}",
                name=column,
                physical_name=column,
                data_type=kind,
                nullable=False,
                req_ids=["REQ-01"],
                length=32 if kind == "varchar" else None,
                precision=10 if kind == "numeric" else None,
                scale=2 if kind == "numeric" else None,
                references=None,
                relationship_id=None,
            )
            t["columns"].append(c)
            if key:
                t["primary_key"].append(c["id"])
        tables.append(t)
    state["normalized"]["tables"] = tables
    state["normalized"]["foreign_keys"] = [
        dict(
            id="FK-parent",
            table_id=tables[1]["id"],
            columns=[tables[1]["columns"][0]["id"]],
            parent_table_id=tables[0]["id"],
            parent_columns=[tables[0]["columns"][0]["id"]],
            relationship_id="REL-parent",
            req_ids=["REQ-01"],
        )
    ]
    state = DesignState.model_validate(state)
    current.update(
        entities=[],
        storage_bindings=[],
        operation_bindings=[],
        use_cases=[],
        apis=[],
        screens=[],
        acceptance_cases=[],
        questions=[],
        roles=[{"id": "ROLE-user", "name": "사용자"}],
    )
    current["requirements"] = [r for r in current["requirements"] if r["origin"] == "design"]
    for requirement in current["requirements"]:
        requirement.update(priority="Must", requires_ui=True)
    current["baseline"]["model_hash"] = model_hash(state)
    ddl = (
        f"CREATE TABLE {parent}(id varchar(32) PRIMARY KEY,name varchar(32) NOT NULL);\n"
        f"CREATE TABLE {child}(parent_id varchar(32) REFERENCES {parent},"
        "sequence integer,scheduled date NOT NULL,status varchar(32) NOT NULL,"
        "amount numeric(10,2) NOT NULL,PRIMARY KEY(parent_id,sequence));"
    )
    artifacts = {
        "ddl.sql": ddl.encode(),
        "erd.mmd": f"erDiagram\n {parent} ||--o{{ {child} : relation\n".encode(),
        "functions.md": str(labels).encode(),
        "rtm.csv": b"requirement,function\nREQ-01,register\n",
    }
    for digest in current["baseline"]["artifacts"]:
        digest["sha256"] = hashlib.sha256(
            artifacts[digest["kind"] + "." + digest["file_format"]]
        ).hexdigest()
    artifacts["manifest.json"] = json.dumps(
        {k: hashlib.sha256(v).hexdigest() for k, v in artifacts.items()}
    ).encode()
    current["baseline"]["manifest_hash"] = hashlib.sha256(artifacts["manifest.json"]).hexdigest()
    draft = derive(SpecBundle.model_validate(current), state)
    return draft, state, artifacts


def reviewed(draft):
    data = draft.model_dump(mode="json")
    for row in data["domain"]["coverage"]:
        row.update(status="mapped", explanation="합성 테스트의 저장·조회 요구를 실행 동작에 연결함")
    return SpecBundle.model_validate(data)


def with_transition(draft):
    data = reviewed(draft).model_dump(mode="json")
    target = data["domain"]["operations"][-1]["table_id"]
    binding = next(b for b in data["storage_bindings"] if b["table_id"] == target)
    entity = next(e for e in data["entities"] if e["id"] == binding["entity_id"])
    status = next(f for f in entity["fields"] if f["name"] == "status")
    column = binding["columns"][status["id"]]
    for op in data["domain"]["operations"]:
        if op["table_id"] == target and op["action"] == "insert":
            op["guards"] = [dict(column_id=column, operator="eq", value="pending")]
    api = deepcopy(
        next(a for a in data["apis"] if a["id"] == data["domain"]["operations"][-1]["api_id"])
    )
    use = deepcopy(next(u for u in data["use_cases"] if u["id"] == api["use_case_id"]))
    keys = [f for f in entity["fields"] if f["name"] in {"parent_id", "sequence"}]
    use.update(id="UC-transition", name="승인 상태로 변경", inputs=keys)
    api.update(
        id="API-transition",
        use_case_id="UC-transition",
        path=api["path"].rsplit("/", 1)[0] + "/transition",
        request_fields=keys,
    )
    data["use_cases"].append(use)
    data["apis"].append(api)
    data["screens"][-1]["api_ids"].append(api["id"])
    data["domain"]["operations"].append(
        dict(
            api_id=api["id"],
            table_id=target,
            action="transition",
            guards=[],
            transition=dict(column_id=column, from_values=["pending"], to_value="approved"),
        )
    )
    return SpecBundle.model_validate(data)
