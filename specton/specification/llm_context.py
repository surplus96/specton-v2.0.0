"""A read-only projection: repeated schemas and protected test bodies stay on the server."""

import hashlib
from typing import Any

from specton.contracts.specification import SpecBundle


def specification_context(bundle: SpecBundle, *, api_fields: bool = True) -> dict[str, Any]:
    data = bundle.model_dump(mode="json")
    for use in data["use_cases"]:
        use.pop("inputs", None)
        use.pop("outputs", None)
    if not api_fields:
        data["apis"] = [
            {k: a[k] for k in ("id", "use_case_id", "method", "path", "actor_roles")}
            for a in data["apis"]
        ]
        data["use_cases"] = [
            {k: u[k] for k in ("id", "name", "req_ids", "actor_roles")} for u in data["use_cases"]
        ]
    data["acceptance_cases"] = [
        {
            "id": case.id,
            "req_ids": list(case.req_ids) if case.execution else [],
            "use_case_ids": list(case.use_case_ids) if case.execution else [],
            "tier": case.tier,
            "category": case.execution.category if case.execution else None,
            "api_ids": sorted({s.api_id for s in case.execution.steps}) if case.execution else [],
            "protected": case.execution is not None,
            "sha256": hashlib.sha256(case.model_dump_json().encode()).hexdigest(),
        }
        for case in bundle.acceptance_cases
    ]
    return {
        "projection": "specification-context-v1",
        "notes": (
            "This is a read-only projection, not a complete SpecBundle. Use-case input/output "
            "schemas repeat APIs and are omitted. Acceptance bodies and exact expectations "
            "remain unchanged on the server; summaries are not evidence of test passage. "
            + (
                "API field schemas are included."
                if api_fields
                else "API field schemas are omitted; existing contracts remain on the server."
            )
        ),
        "specification": data,
        "source_sha256": hashlib.sha256(bundle.model_dump_json().encode()).hexdigest(),
    }
