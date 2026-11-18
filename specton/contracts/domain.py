"""Domain-independent executable operations; no application-specific profiles or SQL."""

from typing import Literal

from pydantic import Field

from specton.contracts.base import Contract
from specton.contracts.calculations import CalculationQuery
from specton.contracts.commands import AtomicCommand

Scalar = str | int | bool | None


class Guard(Contract):
    column_id: str
    operator: Literal["eq", "ne", "lt", "le", "gt", "ge"]
    value: Scalar


class Transition(Contract):
    column_id: str
    from_values: list[Scalar] = Field(min_length=1, max_length=32)
    to_value: Scalar


class DomainOperation(Contract):
    api_id: str
    table_id: str
    action: Literal["insert", "list", "update", "transition"]
    guards: list[Guard] = Field(default_factory=list, max_length=32)
    transition: Transition | None = None


class Coverage(Contract):
    requirement_id: str
    status: Literal["needs_review", "mapped", "unsupported"]
    api_ids: list[str] = Field(default_factory=list)
    explanation: str = Field(min_length=1, max_length=4000)


class DomainPlan(Contract):
    version: Literal["domain-ir-v1", "domain-ir-v2", "domain-ir-v3"] = "domain-ir-v1"
    operations: list[DomainOperation] = Field(min_length=1, max_length=200)
    coverage: list[Coverage] = Field(min_length=1, max_length=500)
    commands: tuple[AtomicCommand, ...] = Field(default=(), max_length=32)
    calculations: tuple[CalculationQuery, ...] = Field(default=(), max_length=32)
