"""Type/unit-check bounded programs and bind aggregates to approved physical columns."""

import re
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from specton.contracts.acceptance import ErrorResponse, ExactResponse
from specton.contracts.calculations import (
    CalculationQuery,
    CalculationStep,
    ColumnUnit,
    NumericPolicy,
)
from specton.contracts.specification import SpecBundle
from specton.implementation.compiler import Unsupported

QUERY_ERRORS = {
    "CALCULATION_ERROR",
    "RESULT_LIMIT_EXCEEDED",
    "COMMAND_TIMEOUT",
    "TRANSACTION_FAILED",
}
Resolved = tuple[dict[str, Any], dict[str, Any]]


def numeric_meta(policy: NumericPolicy, required: bool) -> dict[str, Any]:
    return {
        "data_type": "decimal",
        "sql_type": "numeric",
        "required": required,
        "precision": policy.precision,
        "scale": policy.scale,
        "length": None,
        "unit": dict(policy.unit),
        "primary": False,
    }


def units_for(
    units: tuple[ColumnUnit, ...], records: list[dict[str, Any]]
) -> dict[tuple[str, str], dict[str, int]]:
    columns = {(o["table_id"], f["column_id"]): f for o in records for f in o["fields"]}
    result = {}
    for u in units:
        key = (u.table_id, u.column_id)
        if (
            key in result
            or key not in columns
            or columns[key]["data_type"] not in {"integer", "decimal"}
            or any(v == 0 for v in u.unit.values())
        ):
            raise Unsupported("계산 단위는 실제 숫자 컬럼마다 한 번, 0이 아닌 지수로 선언하세요.")
        result[key] = dict(u.unit)
    return result


def compile_program(
    steps: tuple[CalculationStep, ...], resolve: Callable[[dict[str, Any]], Resolved]
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    program: list[dict[str, Any]] = []
    known: dict[str, dict[str, Any]] = {}

    def operand(obj: Any) -> Resolved:
        value = obj.model_dump(mode="json")
        if value["kind"] == "calculated":
            if value["calculation_id"] not in known:
                raise Unsupported("계산은 앞서 정의한 결과만 참조할 수 있습니다.")
            return value, known[value["calculation_id"]]
        if value["kind"] == "number":
            if any(v == 0 for v in value["unit"].values()):
                raise Unsupported("상수의 단위 지수 0은 생략하세요.")
            return value, {"data_type": "decimal", "required": True, "unit": value["unit"]}
        expr, meta = resolve(value)
        if meta["data_type"] not in {"integer", "decimal"} or "unit" not in meta:
            raise Unsupported("계산 피연산자는 단위를 선언한 숫자 값이어야 합니다.")
        if meta.get("precision", 0) and meta["precision"] > 38:
            raise Unsupported("계산 입력의 숫자 정밀도는 최대 38입니다.")
        return expr, meta

    for step in steps:
        if step.id in known:
            raise Unsupported("계산 결과 ID가 중복됩니다.")
        left, lm = operand(step.left)
        right, rm = operand(step.right) if step.right else (None, lm)
        unit = dict(lm["unit"])
        if step.operator in {"add", "subtract"} and unit != rm["unit"]:
            raise Unsupported("덧셈·뺄셈의 단위가 다릅니다.")
        if step.operator in {"multiply", "divide"}:
            sign = 1 if step.operator == "multiply" else -1
            for key, power in rm["unit"].items():
                unit[key] = unit.get(key, 0) + sign * power
            unit = {k: v for k, v in unit.items() if v}
        if unit != step.result.unit:
            raise Unsupported("계산 결과의 선언 단위와 식의 단위가 다릅니다.")
        required = not (
            step.null_policy == "propagate" and (not lm["required"] or not rm["required"])
        ) and not (step.operator == "divide" and step.zero_division == "null")
        known[step.id] = numeric_meta(step.result, required)
        program.append({**step.model_dump(mode="json"), "left": left, "right": right})
    return program, known


def require_cases(bundle: SpecBundle, api_id: str) -> None:
    use_id = next(a.use_case_id for a in bundle.apis if a.id == api_id)
    reqs = set(next(u.req_ids for u in bundle.use_cases if u.id == use_id))
    categories = {
        c.execution.category
        for c in bundle.acceptance_cases
        if c.execution
        and reqs <= set(c.req_ids)
        and any(
            s.api_id == api_id
            and s.actor == "allowed"
            and (
                isinstance(s.expect, ErrorResponse)
                if c.execution.category == "failure"
                else isinstance(s.expect, ExactResponse)
            )
            for s in c.execution.steps
        )
    }
    if not {"normal", "boundary", "failure"} <= categories:
        raise Unsupported("계산·집계에도 요구와 연결된 정상·경계·실패 API 사례가 필요합니다.")


def compile_queries(bundle: SpecBundle, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    assert bundle.domain is not None
    return [_compile_query(bundle, records, query) for query in bundle.domain.calculations]


def _compile_query(
    bundle: SpecBundle, records: list[dict[str, Any]], query: CalculationQuery
) -> dict[str, Any]:
    by_table = {r["table_id"]: r for r in records}
    apis = {a.id: a for a in bundle.apis}
    uses = {u.id: u for u in bundle.use_cases}
    api = apis[query.api_id]
    use = uses[api.use_case_id]
    if (
        api.method != "POST"
        or api.success_status != 200
        or api.pagination != "none"
        or api.concurrency != "read_only"
        or use.transaction != "read_only"
        or use.idempotency != "not_applicable"
        or set(api.error_codes) != QUERY_ERRORS
        or not re.fullmatch(r"/calculations/[a-z0-9_-]+", api.path)
    ):
        raise Unsupported("집계는 POST /calculations/...·읽기 전용·명시한 오류 계약이 필요합니다.")
    if any(hasattr(BaseModel, f.name) for f in (*api.request_fields, *api.response_fields)):
        raise Unsupported("계산 DTO에는 예약 이름을 사용할 수 없습니다.")
    table = by_table.get(query.table_id)
    if table is None:
        raise Unsupported("집계 테이블은 승인 설계에 있어야 합니다.")
    units = units_for(query.column_units, records)
    columns = {f["column_id"]: f for f in table["fields"]}
    inputs = {}
    bindings = {b.field_id: b for b in query.input_bindings}
    if len(bindings) != len(query.input_bindings) or set(bindings) != {
        f.id for f in api.request_fields
    }:
        raise Unsupported("집계 입력을 실제 컬럼에 한 번씩 연결하세요.")
    for f in api.request_fields:
        b = bindings[f.id]
        meta = next(
            (
                c
                for c in by_table.get(b.table_id, {}).get("fields", [])
                if c["column_id"] == b.column_id
            ),
            None,
        )
        if meta is None or f.data_type != meta["data_type"] or f.required != meta["required"]:
            raise Unsupported("집계 입력 타입이 승인 컬럼과 다릅니다.")
        inputs[f.id] = {**meta, **f.model_dump(mode="json"), "label": f.name, "primary": False}
        if (b.table_id, b.column_id) in units:
            inputs[f.id]["unit"] = units[(b.table_id, b.column_id)]
    filters, windows = [], []
    for rule in query.filters:
        col, inp = columns.get(rule.column_id), inputs.get(rule.input_field_id)
        if not col or not inp or col["data_type"] != inp["data_type"] or not inp["required"]:
            raise Unsupported("집계 필터는 같은 타입의 필수 입력에 연결하세요.")
        if col["data_type"] in {"integer", "decimal"} and (
            (query.table_id, rule.column_id) not in units
            or inputs[rule.input_field_id].get("unit") != units[(query.table_id, rule.column_id)]
        ):
            raise Unsupported("숫자 집계 필터는 컬럼과 입력의 단위가 같아야 합니다.")
        filters.append({"name": col["name"], "operator": rule.operator, "input": inp["name"]})
    for w in query.windows:
        col, start, end = (
            columns.get(w.column_id),
            inputs.get(w.start_field_id),
            inputs.get(w.end_field_id),
        )
        if (
            not col
            or col["data_type"] != "date"
            or not start
            or not end
            or any(f["data_type"] != "date" or not f["required"] for f in (start, end))
            or w.start_field_id == w.end_field_id
        ):
            raise Unsupported("기간 집계는 서로 다른 필수 날짜 입력과 포함·제외 경계가 필요합니다.")
        windows.append(
            {
                **w.model_dump(mode="json"),
                "name": col["name"],
                "start": start["name"],
                "end": end["name"],
            }
        )
    aggregates, known = [], {}
    for measure in query.aggregates:
        col = columns.get(measure.column_id) if measure.column_id else None
        if measure.id in known:
            raise Unsupported("집계 ID가 중복됩니다.")
        if measure.operator != "count" and (
            not col
            or col["data_type"] not in {"integer", "decimal"}
            or (query.table_id, measure.column_id) not in units
            or units[(query.table_id, measure.column_id or "")] != measure.result.unit
            or (col.get("precision") or 0) > 38
        ):
            raise Unsupported("집계 컬럼의 숫자 타입·단위·정밀도를 확인하세요.")
        known[measure.id] = numeric_meta(measure.result, measure.empty_policy != "null")
        aggregates.append({**measure.model_dump(mode="json"), "name": col["name"] if col else None})

    def resolve(value: dict[str, Any]) -> Resolved:
        if value["kind"] == "input" and value["field_id"] in inputs:
            meta = inputs[value["field_id"]]
            return {"kind": "input", "name": meta["name"]}, meta
        if value["kind"] == "aggregate" and value["aggregate_id"] in known:
            return value, known[value["aggregate_id"]]
        raise Unsupported("집계 계산이 없는 입력·행·집계 결과를 참조합니다.")

    program, calculated = compile_program(query.calculations, resolve)
    returns, response_fields = {}, []
    if set(query.returns) != {f.id for f in api.response_fields}:
        raise Unsupported("모든 집계 응답에 결과 출처가 필요합니다.")
    for f in api.response_fields:
        value = query.returns[f.id].model_dump(mode="json")
        meta = (
            calculated.get(value["calculation_id"])
            if value["kind"] == "calculated"
            else known.get(value["aggregate_id"])
        )
        if not meta or f.data_type != "decimal" or f.required != meta["required"]:
            raise Unsupported("집계 응답의 타입·null 가능성·출처가 다릅니다.")
        returns[f.name] = value
        response_fields.append({**meta, **f.model_dump(mode="json")})
    require_cases(bundle, api.id)
    return {
        **api.model_dump(mode="json"),
        "action": "calculation",
        "table_id": query.table_id,
        "table": table["table"],
        "label": use.name,
        "fields": list(inputs.values()),
        "keys": [],
        "filters": filters,
        "windows": windows,
        "aggregates": aggregates,
        "calculations": program,
        "max_rows": query.max_rows,
        "returns": returns,
        "response_metadata": response_fields,
        "guards": [],
        "transition": None,
    }
