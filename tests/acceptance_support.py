"""Independently written synthetic examples, not customer approval or generated oracles."""

from copy import deepcopy

from domain_support import reviewed
from invariant_support import quantity_bounds

from specton.contracts.specification import SpecBundle


def scenarios(draft):
    data = quantity_bounds(reviewed(draft)).model_dump(mode="json")
    data["schema_version"] = "spec-v0.7"
    parent, child = [b["table_id"] for b in data["storage_bindings"]]
    ops = {(o["table_id"], o["action"]): o["api_id"] for o in data["domain"]["operations"]}
    p = {"id": "test-parent", "name": "Synthetic"}
    base = {
        "parent_id": p["id"],
        "sequence": 1,
        "scheduled": "2030-01-01",
        "status": "open",
        "amount": "0.50",
    }

    def step(table, action, body=None, key=None, expected=None, error=None, actor="allowed"):
        return dict(
            api_id=ops[table, action],
            body=body,
            request_key=key,
            actor=actor,
            expect=dict(kind="error", status=error[0], code=error[1])
            if error
            else dict(kind="exact", status=200, body=expected if expected is not None else body),
        )

    seed = [step(parent, "insert", p, "parent"), step(child, "insert", base, "child")]
    definitions = [
        (
            "normal",
            [
                *seed,
                step(child, "list", expected=[base]),
                step(child, "update", {**base, "amount": "0.75"}, "edit"),
                step(child, "update", {**base, "amount": "0.75"}, "edit"),
                step(child, "list", expected=[{**base, "amount": "0.75"}]),
            ],
        ),
        (
            "boundary",
            [
                *seed,
                step(child, "update", {**base, "amount": "1.00"}, "upper"),
                step(child, "list", expected=[{**base, "amount": "1.00"}]),
                step(child, "update", {**base, "amount": "0.00"}, "lower"),
                step(child, "list", expected=[{**base, "amount": "0.00"}]),
            ],
        ),
        (
            "failure",
            [
                *seed,
                step(
                    child,
                    "update",
                    {**base, "amount": "1.01"},
                    "retry",
                    error=(409, "RULE_VIOLATION"),
                ),
                step(child, "list", expected=[base]),
                step(child, "update", {**base, "amount": "0.70"}, "retry"),
                step(child, "list", expected=[{**base, "amount": "0.70"}]),
            ],
        ),
        (
            "failure",
            [
                *seed,
                step(child, "list", error=(401, "AUTH_REQUIRED"), actor="unauthenticated"),
                step(child, "list", error=(403, "FORBIDDEN"), actor="denied"),
            ],
        ),
    ]
    for i, (category, steps) in enumerate(definitions):
        refs = {s["api_id"] for s in steps}
        data["acceptance_cases"].append(
            dict(
                id=f"TC-executable-{i}",
                req_ids=[data["requirements"][0]["id"]],
                use_case_ids=[a["use_case_id"] for a in data["apis"] if a["id"] in refs],
                tier="api",
                given=["빈 격리 DB"],
                when="명시한 합성 API 요청 수행",
                then=["명시한 응답과 저장 결과가 일치"],
                fixture_ids=["explicit-synthetic"],
                execution=dict(
                    category=category, initial_state="empty_database", steps=deepcopy(steps)
                ),
            )
        )
    return SpecBundle.model_validate(data)
