"""Synthetic approved roles, not a change to a customer's approved specification."""

from domain_support import case, reviewed

from specton.contracts.specification import SpecBundle


def customer(domain="maintenance"):
    draft, state, artifacts = case(domain)
    data = reviewed(draft).model_dump(mode="json")
    data["roles"].append({"id": "ROLE-reader", "name": "조회 담당자"})
    read_ids = {op.api_id for op in draft.domain.operations if op.action == "list"}
    cases = {a["use_case_id"] for a in data["apis"] if a["id"] in read_ids}
    for api in data["apis"]:
        if api["id"] in read_ids:
            api["actor_roles"].append("ROLE-reader")
    for case_ in data["use_cases"]:
        if case_["id"] in cases:
            case_["actor_roles"].append("ROLE-reader")
    data["screens"] += [
        {
            **screen,
            "id": screen["id"] + "-read",
            "name": screen["name"] + " 조회",
            "route": screen["route"] + "/read",
            "actor_roles": ["ROLE-reader"],
            "api_ids": [aid for aid in screen["api_ids"] if aid in read_ids],
        }
        for screen in data["screens"]
        if set(screen["api_ids"]) & read_ids
    ]
    return SpecBundle.model_validate(data), state, artifacts
