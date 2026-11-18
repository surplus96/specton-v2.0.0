"""Bind an explicit record policy and acceptance oracles to the actual design's APIs.

This is a proposal operation: no scope reduction, answers, coverage certification or approval.
Values and expected responses must be supplied, never inferred from observed app output.
"""

from typing import Annotated, Literal

from pydantic import Field

from specton.contracts.acceptance import (
    ApiScenario,
    ApiTestStep,
    ErrorResponse,
    ExactResponse,
    Record,
)
from specton.contracts.base import Contract
from specton.contracts.specification import (
    BooleanLiteral,
    Key,
    NumberLiteral,
    SpecBundle,
    TextLiteral,
)


class AllowedValues(Contract):
    field_id: Key
    values: tuple[TextLiteral | NumberLiteral | BooleanLiteral, ...] = Field(
        min_length=1, max_length=32
    )


class RecordStep(Contract):
    action: Literal["insert", "list", "update"]
    actor: Literal["allowed", "unauthenticated", "denied"] = "allowed"
    body: Record | None = None
    request_key: str | None = None
    expect: Annotated[ExactResponse | ErrorResponse, Field(discriminator="kind")]


class RecordScenario(Contract):
    id: Key
    name: str = Field(min_length=1, max_length=200)
    category: Literal["normal", "boundary", "failure"]
    steps: tuple[RecordStep, ...] = Field(min_length=1, max_length=24)


class RecordContract(Contract):
    id: Key
    entity_id: Key
    req_ids: tuple[Key, ...] = Field(min_length=1)
    rationale: str = Field(min_length=1, max_length=4000)
    allowed_values: tuple[AllowedValues, ...] = Field(default=(), max_length=16)
    setup: tuple[ApiTestStep, ...] = Field(default=(), max_length=8)
    scenarios: tuple[RecordScenario, ...] = Field(min_length=1, max_length=16)


def apply_record_contract(current: SpecBundle, contract: RecordContract) -> SpecBundle:
    if current.domain is None:
        raise ValueError("도메인 실행 초안이 필요합니다.")
    entity = next((e for e in current.entities if e.id == contract.entity_id), None)
    binding = next((b for b in current.storage_bindings if b.entity_id == contract.entity_id), None)
    if entity is None or binding is None:
        raise ValueError("실제 설계에 연결된 엔티티를 지정하세요.")
    apis = {a.id: a for a in current.apis}
    cases = {u.id: u for u in current.use_cases}
    operations = [o for o in current.domain.operations if o.table_id == binding.table_id]
    by_action = {}
    for action in ("insert", "list", "update"):
        matches = [o for o in operations if o.action == action]
        if len(matches) != 1:
            raise ValueError("등록·조회·수정 동작이 각각 하나인 엔티티만 지원합니다.")
        by_action[action] = apis[matches[0].api_id]
    insert_ids = {o.api_id for o in current.domain.operations if o.action == "insert"}
    if any(s.api_id not in insert_ids or s.actor != "allowed" for s in contract.setup):
        raise ValueError("선행 데이터는 실제 등록 API의 명시적 입력·기대값으로만 준비합니다.")
    if any(
        not set(contract.req_ids) <= set(cases[a.use_case_id].req_ids) for a in by_action.values()
    ):
        raise ValueError("요구사항과 실제 API의 출처 연결이 다릅니다.")
    fields = {f.id: f for f in entity.fields}
    data = current.model_dump(mode="json")
    data["schema_version"] = (
        current.schema_version
        if current.schema_version in {"spec-v0.8", "spec-v0.9"}
        else "spec-v0.7"
    )
    seen = {i.id for i in current.invariants} | {c.id for c in current.acceptance_cases}
    if len({v.field_id for v in contract.allowed_values}) != len(contract.allowed_values):
        raise ValueError("허용값 필드가 중복됩니다.")
    for index, policy in enumerate(contract.allowed_values):
        field = fields.get(policy.field_id)
        if field is None or not field.required:
            raise ValueError("허용값 정책은 같은 엔티티의 필수 필드만 지원합니다.")
        invariant_id = f"INV-{contract.id}-{index}"
        if invariant_id in seen:
            raise ValueError("기존 정책을 덮어쓸 수 없습니다.")
        seen.add(invariant_id)
        data["invariants"].append(
            {
                "id": invariant_id,
                "req_ids": list(contract.req_ids),
                "description": contract.rationale,
                "layers": ["api"],
                "match": "any",
                "comparisons": [
                    {
                        "operator": "eq",
                        "left": {"kind": "field", "entity_id": entity.id, "field_id": field.id},
                        "right": v.model_dump(mode="json"),
                    }
                    for v in policy.values
                ],
            }
        )
    for scenario in contract.scenarios:
        if scenario.id in seen:
            raise ValueError("기존 인수 사례·기대값을 덮어쓸 수 없습니다.")
        seen.add(scenario.id)
        steps = contract.setup + tuple(
            ApiTestStep.model_validate(
                {
                    "api_id": by_action[s.action].id,
                    **s.model_dump(exclude={"action"}),
                }
            )
            for s in scenario.steps
        )
        execution = ApiScenario(category=scenario.category, steps=steps)
        data["acceptance_cases"].append(
            {
                "id": scenario.id,
                "req_ids": list(contract.req_ids),
                "use_case_ids": sorted({apis[s.api_id].use_case_id for s in steps}),
                "tier": "api",
                "given": ["사례마다 빈 격리 DB에서 시작"],
                "when": scenario.name,
                "then": [contract.rationale],
                "fixture_ids": [contract.id],
                "execution": execution.model_dump(mode="json"),
            }
        )
    # Requirements, coverage, questions/answers, roles and baseline are untouched.
    return SpecBundle.model_validate(data)
