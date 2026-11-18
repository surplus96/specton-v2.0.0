"""Bounded, declarative API scenarios. No URLs, code, SQL or external credentials."""

from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictInt, StringConstraints

from specton.contracts.base import Contract

Scalar = Annotated[str, StringConstraints(max_length=2000)] | StrictInt | StrictBool | None
Record = Annotated[dict[str, Scalar], Field(max_length=100)]
Key = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{1,15}-[A-Za-z0-9_-]{1,64}$")]


class ExactResponse(Contract):
    kind: Literal["exact"] = "exact"
    status: Literal[200] = 200
    body: Record | Annotated[list[Record], Field(max_length=100)]


class ErrorResponse(Contract):
    kind: Literal["error"] = "error"
    status: Literal[401, 403, 404, 409, 422]
    code: Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")]


class ApiTestStep(Contract):
    api_id: Key
    actor: Literal["allowed", "unauthenticated", "denied"] = "allowed"
    body: Record | None = None
    request_key: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")] | None = None
    expect: Annotated[ExactResponse | ErrorResponse, Field(discriminator="kind")]


class ApiScenario(Contract):
    version: Literal["api-scenario-v1"] = "api-scenario-v1"
    category: Literal["normal", "boundary", "failure"]
    initial_state: Literal["empty_database"] = "empty_database"
    steps: tuple[ApiTestStep, ...] = Field(min_length=1, max_length=24)
