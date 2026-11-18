"""Bounded multi-record commands: data references, no SQL, code, loops or remote effects."""

from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictInt, StringConstraints

from specton.contracts.base import Contract
from specton.contracts.calculations import CalculatedValue, CalculationStep, ColumnUnit

Identifier = Annotated[str, StringConstraints(min_length=1, max_length=100)]
Alias = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,31}$")]


class CommandInput(Contract):
    kind: Literal["input"] = "input"
    field_id: Identifier


class CommandRowValue(Contract):
    kind: Literal["row"] = "row"
    target: Alias
    column_id: Identifier


class CommandLiteral(Contract):
    kind: Literal["literal"] = "literal"
    value: Annotated[str, StringConstraints(max_length=2000)] | StrictInt | StrictBool | None


KeyValue = Annotated[CommandInput | CommandLiteral, Field(discriminator="kind")]
Operand = Annotated[
    CommandInput | CommandRowValue | CommandLiteral | CalculatedValue, Field(discriminator="kind")
]


class CommandArithmetic(Contract):
    kind: Literal["arithmetic"] = "arithmetic"
    operator: Literal["add", "subtract"]
    left: Operand
    right: Operand


CommandValue = Annotated[
    CommandInput | CommandRowValue | CommandLiteral | CommandArithmetic | CalculatedValue,
    Field(discriminator="kind"),
]


class CommandBinding(Contract):
    field_id: Identifier
    table_id: Identifier
    column_id: Identifier


class CommandTarget(Contract):
    id: Alias
    table_id: Identifier
    mode: Literal["read", "update", "insert"]
    keys: Annotated[dict[Identifier, KeyValue], Field(min_length=1, max_length=16)]


class CommandCondition(Contract):
    left: Operand
    operator: Literal["eq", "ne", "lt", "le", "gt", "ge"]
    right: Operand


class CommandWrite(Contract):
    target: Alias
    values: Annotated[dict[Identifier, CommandValue], Field(min_length=1, max_length=64)]


class AtomicCommand(Contract):
    api_id: Identifier
    input_bindings: tuple[CommandBinding, ...] = Field(min_length=1, max_length=64)
    targets: tuple[CommandTarget, ...] = Field(min_length=2, max_length=8)
    before: tuple[CommandCondition, ...] = Field(default=(), max_length=32)
    writes: tuple[CommandWrite, ...] = Field(min_length=2, max_length=8)
    after: tuple[CommandCondition, ...] = Field(default=(), max_length=32)
    returns: Annotated[dict[Identifier, Operand], Field(min_length=1, max_length=64)]
    column_units: tuple[ColumnUnit, ...] = Field(default=(), max_length=64)
    calculations: tuple[CalculationStep, ...] = Field(default=(), max_length=32)
