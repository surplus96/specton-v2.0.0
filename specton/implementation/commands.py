"""Compile atomic commands against approved columns and explicitly reviewed API roles."""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from specton.contracts.acceptance import ErrorResponse, ExactResponse
from specton.contracts.calculations import CalculatedValue
from specton.contracts.commands import (
    AtomicCommand,
    CommandArithmetic,
    CommandInput,
    CommandLiteral,
    CommandRowValue,
)
from specton.contracts.specification import SpecBundle
from specton.implementation.calculations import compile_program, units_for
from specton.implementation.compiler import Unsupported

COMMAND_ERRORS = {
    "NOT_FOUND",
    "DUPLICATE_KEY",
    "REFERENCE_NOT_FOUND",
    "RULE_VIOLATION",
    "CONSTRAINT_VIOLATION",
    "IDEMPOTENCY_CONFLICT",
    "CONCURRENT_MODIFICATION",
    "COMMAND_TIMEOUT",
    "TRANSACTION_FAILED",
}


def checked_literal(value: Any, field: dict[str, Any]) -> Any:
    kind = field["data_type"]
    try:
        if value is None:
            if field["required"]:
                raise ValueError()
        elif kind == "integer":
            bits = {"smallint": 16, "integer": 32, "bigint": 64}[field["sql_type"]]
            if type(value) is not int or not -(2 ** (bits - 1)) <= value < 2 ** (bits - 1):
                raise ValueError()
        elif kind == "decimal":
            if not isinstance(value, str) or not re.fullmatch(
                r"-?(0|[1-9][0-9]*)(\.[0-9]+)?", value
            ):
                raise ValueError()
            with localcontext() as context:
                context.prec = 128
                number = Decimal(value)
                if (
                    not number.is_finite()
                    or number != number.quantize(Decimal(1).scaleb(-field["scale"]))
                    or abs(number) >= Decimal(10) ** (field["precision"] - field["scale"])
                ):
                    raise ValueError()
        elif kind == "boolean":
            if type(value) is not bool:
                raise ValueError()
        else:
            if not isinstance(value, str):
                raise ValueError()
            if kind == "string" and len(value) > (field["length"] or 20000):
                raise ValueError()
            if kind == "date":
                date.fromisoformat(value)
            if kind == "datetime":
                datetime.fromisoformat(value)
            if kind == "uuid":
                UUID(value)
    except (ValueError, TypeError, InvalidOperation, KeyError):
        raise Unsupported("명령 상수의 자료형·정밀도·길이가 승인 컬럼과 다릅니다.") from None
    return value


def compile_commands(bundle: SpecBundle, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    assert bundle.domain is not None
    return [_compile_command(bundle, records, command) for command in bundle.domain.commands]


def _compile_command(
    bundle: SpecBundle, records: list[dict[str, Any]], command: AtomicCommand
) -> dict[str, Any]:
    by_table = {op["table_id"]: op for op in records}
    apis = {a.id: a for a in bundle.apis}
    uses = {u.id: u for u in bundle.use_cases}
    api = apis[command.api_id]
    use = uses[api.use_case_id]
    if any(hasattr(BaseModel, f.name) for f in (*api.request_fields, *api.response_fields)):
        raise Unsupported("명령 DTO에는 예약 이름을 사용할 수 없습니다.")
    if (
        api.method != "POST"
        or api.success_status != 200
        or api.pagination != "none"
        or api.concurrency != "row_lock"
        or use.transaction != "atomic"
        or use.idempotency != "key"
        or set(api.error_codes)
        != COMMAND_ERRORS | ({"CALCULATION_ERROR"} if command.calculations else set())
        or not re.fullmatch(r"/commands/[a-z0-9_-]+", api.path)
    ):
        raise Unsupported(
            "명령은 POST /commands/...·원자성·행 잠금·중복 키·오류 계약이 필요합니다."
        )
    units = units_for(command.column_units, records)
    bindings = {b.field_id: b for b in command.input_bindings}
    if len(bindings) != len(command.input_bindings) or set(bindings) != {
        f.id for f in api.request_fields
    }:
        raise Unsupported("명령의 모든 입력을 승인 컬럼에 한 번씩 연결하세요.")

    def column(table_id: str, column_id: str) -> dict[str, Any]:
        table = by_table.get(table_id)
        if table:
            for f in table["fields"]:
                if f["column_id"] == column_id:
                    if f["data_type"] == "decimal" and (
                        f["precision"] is None or f["precision"] > 38
                    ):
                        raise Unsupported("명령의 고정소수 계산은 최대 정밀도 38까지 지원합니다.")
                    meta = dict(f)
                    if (table_id, column_id) in units:
                        meta["unit"] = units[(table_id, column_id)]
                    return meta
        raise Unsupported("명령이 승인 설계에 없는 테이블·컬럼을 참조합니다.")

    inputs = {}
    for f in api.request_fields:
        binding = bindings[f.id]
        meta = column(binding.table_id, binding.column_id)
        if f.data_type != meta["data_type"] or f.required != meta["required"]:
            raise Unsupported("명령 입력의 자료형·필수 여부와 승인 컬럼이 다릅니다.")
        inputs[f.id] = {**meta, **f.model_dump(mode="json"), "label": f.name, "primary": False}
    targets = {t.id: t for t in command.targets}
    if len(targets) != len(command.targets):
        raise Unsupported("명령 대상 별칭이 중복됩니다.")
    writes = {w.target for w in command.writes}
    if len(writes) != len(command.writes) or writes != {
        t.id for t in command.targets if t.mode != "read"
    }:
        raise Unsupported("각 변경 대상은 정확히 한 번 쓰며 읽기 대상에는 쓸 수 없습니다.")
    available = {t.id for t in command.targets if t.mode != "insert"}
    calculated: dict[str, dict[str, Any]] = {}

    def expression(
        value: Any, expected: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if isinstance(value, CommandLiteral):
            if expected is None:
                raise Unsupported("상수는 비교·대입할 컬럼의 자료형이 필요합니다.")
            return {
                "kind": "literal",
                "value": checked_literal(value.value, expected),
                "data_type": expected["data_type"],
            }, expected
        if isinstance(value, CalculatedValue):
            if value.calculation_id not in calculated:
                raise Unsupported("없는 계산 결과를 참조합니다.")
            meta = calculated[value.calculation_id]
            if expected and meta["unit"] != expected.get("unit"):
                raise Unsupported("계산 결과와 저장·비교 컬럼의 단위가 다릅니다.")
            result = value.model_dump(mode="json")
        elif isinstance(value, CommandInput):
            if value.field_id not in inputs:
                raise Unsupported("명령 입력 참조가 없습니다.")
            meta = inputs[value.field_id]
            result = {"kind": "input", "name": meta["name"]}
        elif isinstance(value, CommandRowValue):
            if value.target not in available:
                raise Unsupported("아직 존재하지 않는 명령 행을 참조합니다.")
            target = targets[value.target]
            meta = column(target.table_id, value.column_id)
            result = {"kind": "row", "target": value.target, "name": meta["name"]}
        elif isinstance(value, CommandArithmetic):
            if expected is None or expected["data_type"] not in {"integer", "decimal"}:
                raise Unsupported("명령의 덧셈·뺄셈은 정수·고정소수 컬럼에만 적용합니다.")
            left, lm = expression(value.left, expected)
            right, rm = expression(value.right, expected)
            if not lm["required"] or not rm["required"]:
                raise Unsupported("명령 산술의 null 처리 정책은 지원하지 않습니다.")
            return {
                "kind": "arithmetic",
                "operator": value.operator,
                "left": left,
                "right": right,
            }, expected
        else:
            raise Unsupported("지원하지 않는 명령 값 표현입니다.")
        if expected and (
            meta["data_type"] != expected["data_type"]
            or (expected["required"] and not meta["required"])
            or ("unit" in expected and meta.get("unit") != expected["unit"])
        ):
            raise Unsupported("명령 참조 값의 자료형·null 가능성이 대상과 다릅니다.")
        return result, meta

    def conditions(values: Any) -> list[dict[str, Any]]:
        result = []
        for c in values:
            if isinstance(c.left, CommandLiteral):
                right, meta = expression(c.right)
                left, _ = expression(c.left, meta)
            else:
                left, meta = expression(c.left)
                right, _other = expression(c.right, meta)
            if c.operator not in {"eq", "ne"} and (
                not meta["required"] or meta["data_type"] == "boolean"
            ):
                raise Unsupported("명령 순서 비교에는 null 없는 정렬 가능한 값이 필요합니다.")
            result.append({"left": left, "operator": c.operator, "right": right})
        return result

    def numeric_operand(value: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        if value["kind"] == "input":
            return expression(CommandInput.model_validate(value))
        if value["kind"] == "row":
            return expression(CommandRowValue.model_validate(value))
        raise Unsupported("변경 명령 계산에는 입력·잠근 행만 사용할 수 있습니다.")

    program, calculated = compile_program(command.calculations, numeric_operand)
    bound_targets = []
    for t in command.targets:
        if t.table_id not in by_table:
            raise Unsupported("명령 대상 테이블이 없습니다.")
        table = by_table[t.table_id]
        if set(t.keys) != {k["column_id"] for k in table["keys"]}:
            raise Unsupported("명령은 전체 기본키로 한 행을 지정해야 합니다.")
        key_values = {}
        for key in table["keys"]:
            key_values[key["name"]] = expression(t.keys[key["column_id"]], key)[0]
        # A caller must not bypass command guards through generated record APIs.
        if t.mode != "read" and any(
            o["table_id"] == t.table_id
            and o["action"] != "list"
            and set(o["actor_roles"]) & set(api.actor_roles)
            for o in records
        ):
            raise Unsupported("명령 역할과 대상 테이블의 직접 쓰기 역할을 분리하세요.")
        invariants = {
            i["id"]: i
            for o in records
            if o["table_id"] == t.table_id
            for i in o.get("invariants", [])
        }
        bound_targets.append(
            {
                "id": t.id,
                "mode": t.mode,
                "table_id": t.table_id,
                "table": table["table"],
                "fields": table["fields"],
                "keys": key_values,
                "invariants": list(invariants.values()),
            }
        )
    before = conditions(command.before)
    bound_writes = []
    for write in command.writes:
        target = targets[write.target]
        table = by_table[target.table_id]
        mutable = {f["column_id"] for f in table["fields"] if not f["primary"]}
        if not set(write.values) <= mutable or (
            target.mode == "insert" and set(write.values) != mutable
        ):
            raise Unsupported("기본키는 변경할 수 없으며 등록은 모든 비키 컬럼의 값이 필요합니다.")
        controlled = {
            o["transition"]["column_id"]
            for o in records
            if o["table_id"] == target.table_id and o.get("transition")
        }
        if controlled & set(write.values):
            raise Unsupported("전용 상태 전이로 통제하는 컬럼은 명령에서 우회 변경할 수 없습니다.")
        values = {
            column(target.table_id, cid)["name"]: expression(v, column(target.table_id, cid))[0]
            for cid, v in write.values.items()
        }
        bound_writes.append({"target": target.id, "values": values})
        available.add(target.id)
    after = conditions(command.after)
    if set(command.returns) != {f.id for f in api.response_fields}:
        raise Unsupported("명령의 모든 응답 필드에 값 출처를 연결하세요.")
    returns, response_fields = {}, []
    for f in api.response_fields:
        value = command.returns[f.id]
        if isinstance(value, CommandLiteral):
            raise Unsupported("명령 응답은 실제 행 또는 입력 값에서 가져와야 합니다.")
        bound, meta = expression(value)
        if f.data_type != meta["data_type"] or f.required != meta["required"]:
            raise Unsupported("명령 응답 자료형·필수 여부가 출처와 다릅니다.")
        returns[f.name] = bound
        response_fields.append({**meta, **f.model_dump(mode="json")})
    categories = {
        t.execution.category
        for t in bundle.acceptance_cases
        if t.execution
        and any(
            s.api_id == api.id
            and s.actor == "allowed"
            and (
                isinstance(s.expect, ErrorResponse)
                if t.execution.category == "failure"
                else isinstance(s.expect, ExactResponse)
            )
            for s in t.execution.steps
        )
        and set(use.req_ids) <= set(t.req_ids)
    }
    if not {"normal", "boundary", "failure"} <= categories:
        raise Unsupported("명령의 요구에 연결된 정상·경계·실패 API 인수 사례가 필요합니다.")
    result = {
        **api.model_dump(mode="json"),
        "action": "command",
        "table_id": None,
        "label": use.name,
        "fields": list(inputs.values()),
        "keys": [],
        "response_metadata": response_fields,
        "targets": bound_targets,
        "before": before,
        "writes": bound_writes,
        "after": after,
        "returns": returns,
        "guards": [],
        "transition": None,
    }
    if program:
        result["calculations"] = program
    return result
