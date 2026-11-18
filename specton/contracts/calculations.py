"""Bounded decimal programs and single-table aggregate queries; no executable text."""

from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from specton.contracts.base import Contract

Ref = Annotated[str, StringConstraints(min_length=1, max_length=100)]
UnitName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,23}$")]
Unit = Annotated[
    dict[UnitName, Annotated[int, Field(ge=-8, le=8, strict=True)]], Field(max_length=4)
]


class NumericPolicy(Contract):
    precision: int = Field(ge=1, le=38)
    scale: int = Field(ge=0, le=18)
    rounding: Literal["half_even", "half_up", "down"]
    unit: Unit

    @model_validator(mode="after")
    def valid_scale(self) -> Self:
        if self.scale > self.precision or any(v == 0 for v in self.unit.values()):
            raise ValueError("소수 자릿수는 정밀도 이하이며 단위 지수 0은 생략해야 합니다.")
        return self


class ColumnUnit(Contract):
    table_id: Ref
    column_id: Ref
    unit: Unit


class NumericInput(Contract):
    kind: Literal["input"] = "input"
    field_id: Ref


class NumericRow(Contract):
    kind: Literal["row"] = "row"
    target: Ref
    column_id: Ref


class AggregateValue(Contract):
    kind: Literal["aggregate"] = "aggregate"
    aggregate_id: Ref


class CalculatedValue(Contract):
    kind: Literal["calculated"] = "calculated"
    calculation_id: Ref


class NumericLiteral(Contract):
    kind: Literal["number"] = "number"
    value: Annotated[str, StringConstraints(pattern=r"^-?(0|[1-9][0-9]{0,37})(\.[0-9]{1,18})?$")]
    unit: Unit

    @model_validator(mode="after")
    def bounded_precision(self) -> Self:
        if len(Decimal(self.value).as_tuple().digits) > 38:
            raise ValueError("계산 상수의 전체 유효 자릿수는 최대 38입니다.")
        return self


NumericValue = Annotated[
    NumericInput | NumericRow | AggregateValue | CalculatedValue | NumericLiteral,
    Field(discriminator="kind"),
]


class CalculationStep(Contract):
    id: Ref
    operator: Literal["add", "subtract", "multiply", "divide", "absolute"]
    left: NumericValue
    right: NumericValue | None = None
    result: NumericPolicy
    null_policy: Literal["error", "propagate"]
    zero_division: Literal["error", "zero", "null"] = "error"

    @model_validator(mode="after")
    def arity(self) -> Self:
        if (self.operator == "absolute") != (self.right is None):
            raise ValueError("절댓값은 피연산자 1개, 다른 계산은 2개가 필요합니다.")
        if self.operator != "divide" and self.zero_division != "error":
            raise ValueError("0분모 정책은 나눗셈에만 지정합니다.")
        return self


class QueryBinding(Contract):
    field_id: Ref
    table_id: Ref
    column_id: Ref


class QueryFilter(Contract):
    column_id: Ref
    operator: Literal["eq", "ne", "lt", "le", "gt", "ge"]
    input_field_id: Ref


class QueryWindow(Contract):
    column_id: Ref
    start_field_id: Ref
    end_field_id: Ref
    start_inclusive: bool
    end_inclusive: bool


class AggregateMeasure(Contract):
    id: Ref
    operator: Literal["count", "sum", "average", "min", "max"]
    column_id: Ref | None = None
    null_policy: Literal["ignore", "error"]
    empty_policy: Literal["zero", "null", "error"]
    result: NumericPolicy

    @model_validator(mode="after")
    def count_column(self) -> Self:
        if (self.operator == "count") != (self.column_id is None):
            raise ValueError("count는 행 수이며 컬럼 없이, 다른 집계는 컬럼을 지정합니다.")
        if self.operator == "count" and (self.result.scale != 0 or self.result.unit):
            raise ValueError("행 수는 소수 자릿수 0의 무차원 값입니다.")
        return self


class CalculationQuery(Contract):
    api_id: Ref
    table_id: Ref
    input_bindings: tuple[QueryBinding, ...] = Field(min_length=1, max_length=32)
    column_units: tuple[ColumnUnit, ...] = Field(max_length=64)
    filters: tuple[QueryFilter, ...] = Field(max_length=16)
    windows: tuple[QueryWindow, ...] = Field(max_length=2)
    max_rows: int = Field(ge=1, le=10000)
    aggregates: tuple[AggregateMeasure, ...] = Field(min_length=1, max_length=16)
    calculations: tuple[CalculationStep, ...] = Field(max_length=32)
    returns: Annotated[
        dict[Ref, AggregateValue | CalculatedValue], Field(min_length=1, max_length=32)
    ]
