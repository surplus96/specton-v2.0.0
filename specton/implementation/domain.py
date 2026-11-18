"""Compile domain IR against exact approved schema, including composite keys and relations."""

import re
from typing import Any

from specton.contracts import DesignState
from specton.contracts.specification import SpecBundle
from specton.specification.domain import TYPES
from specton.specification.readiness import assess_readiness


def compile_domain(
    bundle: SpecBundle, state: DesignState, *, require_ready: bool = True
) -> dict[str, Any]:
    from specton.implementation.compiler import Unsupported

    if not bundle.domain or not state.normalized:
        raise Unsupported("도메인 실행 명세와 승인 모델이 필요합니다.")
    if require_ready and not assess_readiness(bundle).ready_for_review:
        raise Unsupported("미구현 요구 또는 미확정 질문을 먼저 해결하세요.")
    tables = {t.id: t for t in state.normalized.tables}
    if set(tables) != {b.table_id for b in bundle.storage_bindings}:
        raise Unsupported("승인 설계의 테이블을 누락하거나 임의 대체할 수 없습니다.")
    if len(bundle.storage_bindings) != len(tables):
        raise Unsupported("중복 저장 연결은 허용하지 않습니다.")
    stores = {b.table_id: b for b in bundle.storage_bindings}
    entities = {e.id: e for e in bundle.entities}
    apis = {a.id: a for a in bundle.apis}
    if set(apis) != (
        {o.api_id for o in bundle.domain.operations}
        | {c.api_id for c in bundle.domain.commands}
        | {q.api_id for q in bundle.domain.calculations}
    ):
        raise Unsupported("모든 API의 실행 동작이 필요합니다.")
    if {a for s in bundle.screens for a in s.api_ids} != set(apis):
        raise Unsupported("모든 API의 화면 연결이 필요합니다.")
    for coverage in bundle.domain.coverage:
        if coverage.status == "mapped":
            for aid in coverage.api_ids:
                case = next(u for u in bundle.use_cases if u.id == apis[aid].use_case_id)
                if coverage.requirement_id not in case.req_ids:
                    raise Unsupported("요구 커버리지와 실제 유스케이스 연결이 다릅니다.")
    compiled = []
    for op in bundle.domain.operations:
        if op.table_id not in tables:
            raise Unsupported("없는 테이블 참조")
        t = tables[op.table_id]
        binding = stores[t.id]
        entity = entities[binding.entity_id]
        if entity.legacy_id != (t.entity_id or t.id) or set(binding.columns.values()) != {
            c.id for c in t.columns
        }:
            raise Unsupported("엔티티·컬럼 출처가 승인 설계와 다릅니다.")
        fields = []
        for field in entity.fields:
            col = next(c for c in t.columns if c.id == binding.columns[field.id])
            if (
                field.name != col.physical_name
                or field.data_type != TYPES.get(col.data_type.value)
                or field.required != (not col.nullable)
            ):
                raise Unsupported("원본 컬럼·자료형·필수 여부가 다릅니다.")
            fields.append(
                {
                    **field.model_dump(),
                    "column_id": col.id,
                    "label": col.name,
                    "sql_type": col.data_type.value,
                    "length": col.length,
                    "precision": col.precision,
                    "scale": col.scale,
                    "primary": col.id in t.primary_key,
                }
            )
        if (
            not t.primary_key
            or any(
                not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", n)
                for n in [t.physical_name, *[f["name"] for f in fields]]
            )
            or t.physical_name.startswith("_specton_")
        ):
            raise Unsupported("지원하지 않는 테이블/컬럼 식별자 또는 기본키입니다.")
        keys = [f for cid in t.primary_key for f in fields if f["column_id"] == cid]
        api = apis[op.api_id]
        write = op.action != "list"
        expected_inputs = (
            ()
            if not write
            else tuple(
                f for f in entity.fields if next(v for v in fields if v["id"] == f.id)["primary"]
            )
            if op.action == "transition"
            else entity.fields
        )
        if (
            api.method != ("POST" if write else "GET")
            or api.request_fields != expected_inputs
            or api.response_fields != entity.fields
            or api.success_status != 200
            or api.pagination != "none"
            or api.concurrency != ("row_lock" if write else "read_only")
            or not re.fullmatch(r"/data/[a-z0-9_-]+/[a-z0-9_-]+", api.path)
        ):
            raise Unsupported("도메인 API 입력·출력·경로·동시성 계약이 다릅니다.")
        cols = {f["column_id"]: f for f in fields}

        def literal(column_id: str, value: Any, bound_cols: dict[str, Any] = cols) -> None:
            from datetime import date, datetime
            from decimal import Decimal, InvalidOperation
            from uuid import UUID

            f = bound_cols[column_id]
            if value is None:
                if f["required"]:
                    raise Unsupported("필수 컬럼의 규칙 값에 null을 사용할 수 없습니다.")
                return
            kind = f["data_type"]
            try:
                if kind == "string":
                    if not isinstance(value, str) or len(value) > (f["length"] or 20000):
                        raise ValueError()
                elif kind == "integer":
                    if type(value) is not int:
                        raise ValueError()
                    bits = {"smallint": 16, "integer": 32, "bigint": 64}.get(f["sql_type"], 32)
                    if not -(2 ** (bits - 1)) <= value < 2 ** (bits - 1):
                        raise ValueError()
                elif kind == "boolean":
                    if type(value) is not bool:
                        raise ValueError()
                elif kind == "decimal":
                    number = Decimal(str(value))
                    if (
                        not number.is_finite()
                        or number != number.quantize(Decimal(1).scaleb(-f["scale"]))
                        or abs(number) >= Decimal(10) ** (f["precision"] - f["scale"])
                    ):
                        raise ValueError()
                elif kind == "date":
                    date.fromisoformat(str(value))
                elif kind == "datetime":
                    datetime.fromisoformat(str(value))
                elif kind == "uuid":
                    UUID(str(value))
            except (ValueError, TypeError, InvalidOperation):
                raise Unsupported("규칙 값의 타입·길이·정밀도가 승인 컬럼과 다릅니다.") from None

        for guard in op.guards:
            if guard.column_id not in cols or op.action == "list":
                raise Unsupported("잘못된 규칙 연결")
            literal(guard.column_id, guard.value)
            if guard.operator not in {"eq", "ne"} and (
                guard.value is None or cols[guard.column_id]["data_type"] == "boolean"
            ):
                raise Unsupported("순서 비교할 수 없는 규칙 값입니다.")
        if (op.action == "transition") != (op.transition is not None):
            raise Unsupported("상태 전이 정의가 필요합니다.")
        if op.transition and (
            op.transition.column_id not in cols
            or cols[op.transition.column_id]["primary"]
            or cols[op.transition.column_id]["data_type"] not in {"string", "integer", "boolean"}
        ):
            raise Unsupported("변경할 상태 컬럼이 유효하지 않습니다.")
        if op.transition:
            for value in [*op.transition.from_values, op.transition.to_value]:
                literal(op.transition.column_id, value)
        compiled.append(
            {
                **api.model_dump(mode="json"),
                **op.model_dump(mode="json"),
                "id": api.id,
                "table": t.physical_name,
                "label": entity.name,
                "fields": fields,
                "keys": keys,
            }
        )
    for tid in tables:
        actions = [o["action"] for o in compiled if o["table_id"] == tid]
        if "insert" not in actions or "list" not in actions:
            raise Unsupported("각 테이블의 등록·조회와 검증 경로가 필요합니다.")
        transitions = [o for o in compiled if o["table_id"] == tid and o["transition"]]
        for transition_op in transitions:
            transition = transition_op["transition"]
            inserts = [o for o in compiled if o["table_id"] == tid and o["action"] == "insert"]
            if not all(
                any(
                    g["column_id"] == transition["column_id"]
                    and g["operator"] == "eq"
                    and g["value"] in transition["from_values"]
                    for g in o["guards"]
                )
                for o in inserts
            ):
                raise Unsupported(
                    "상태 전이를 사용하는 테이블은 등록 시 초기 상태 조건을 명시해야 합니다."
                )
    from specton.implementation.invariants import bind_invariants

    bind_invariants(bundle, compiled)
    config: dict[str, Any] = {
        "inventory": None,
        "operations": [],
        "domain": {
            "operations": compiled,
            "tables": [t.model_dump(mode="json") for t in tables.values()],
            "foreign_keys": [f.model_dump(mode="json") for f in state.normalized.foreign_keys],
        },
        "screens": [s.model_dump(mode="json") for s in bundle.screens],
    }
    config["domain"]["fixtures"] = fixtures(config["domain"], "x")
    config["domain"]["browser_fixtures"] = fixtures(config["domain"], "b")
    records = list(compiled)
    if bundle.domain.commands:
        from specton.implementation.commands import compile_commands

        config["domain"]["operations"].extend(compile_commands(bundle, records))
    if bundle.domain.calculations:
        from specton.implementation.calculations import compile_queries

        config["domain"]["operations"].extend(compile_queries(bundle, records))
    if bundle.schema_version in {"spec-v0.7", "spec-v0.8", "spec-v0.9"}:
        config["executable_cases"] = [
            {"id": t.id, "req_ids": list(t.req_ids), **t.execution.model_dump(mode="json")}
            for t in bundle.acceptance_cases
            if t.execution
        ]
    return config


def fixtures(config: dict[str, Any], prefix: str) -> list[dict[str, Any]]:
    """Structural fixtures in FK order, not evidence for natural-language business rules."""
    from decimal import Decimal

    operations = config["operations"]
    pending = {o["table_id"]: o for o in operations if o["action"] == "insert"}
    rows: dict[str, dict[str, Any]] = {}
    result = []
    while pending:
        progress = False
        for tid, op in list(pending.items()):
            fks = [f for f in config["foreign_keys"] if f["table_id"] == tid]
            if any(f["parent_table_id"] not in rows for f in fks):
                continue
            values = {}
            for f in op["fields"]:
                value = {
                    "string": prefix[: f["length"] or 32],
                    "integer": 2 if prefix == "b" else 1,
                    "decimal": "1",
                    "boolean": True,
                    "date": "2030-01-01",
                    "datetime": "2030-01-01T10:00:00",
                    "uuid": "00000000-0000-0000-0000-000000000001",
                }[f["data_type"]]
                for guard in op["guards"]:
                    if guard["column_id"] == f["column_id"]:
                        if guard["operator"] in {"eq", "ge", "le"}:
                            value = guard["value"]
                        elif guard["operator"] in {"gt", "lt"}:
                            n = Decimal(str(guard["value"])) + (
                                1 if guard["operator"] == "gt" else -1
                            )
                            value = int(n) if f["data_type"] == "integer" else str(n)
                values[f["column_id"]] = value
            for fk in fks:
                for col, parent in zip(fk["columns"], fk["parent_columns"], strict=True):
                    values[col] = rows[fk["parent_table_id"]][parent]
            rows[tid] = values
            result.append(
                {
                    "table_id": tid,
                    "api_id": op["api_id"],
                    "values": {f["name"]: values[f["column_id"]] for f in op["fields"]},
                }
            )
            pending.pop(tid)
            progress = True
        if not progress:
            raise ValueError("자동 검증 데이터가 순환 외래키를 지원하지 않습니다.")
    return result
