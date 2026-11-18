"""Fixed delivery files and explicit operational scope for generated customer apps."""

from pathlib import Path
from typing import Any

from specton.contracts.specification import SpecBundle
from specton.specification.readiness import spec_hash

ROOT = Path(__file__).parent / "templates"
EXTRA_TEMPLATES = {
    **{f"backend/{name}.py": f"runtime/{name}.py.txt" for name in ("auth", "manage", "serve")},
    **{
        f"frontend/src/{name}": f"frontend/src/{name}"
        for name in ("customer.tsx", "records.tsx", "style.css")
    },
    **{
        name: f"delivery/{name}"
        for name in (
            "OPERATIONS.md",
            "Dockerfile",
            ".dockerignore",
            ".env.example",
            "verify_delivery.py",
            "LICENSE",
        )
    },
}


def manifest(bundle: SpecBundle) -> dict[str, Any]:
    return {
        "version": "customer-delivery-v1",
        "spec_hash": spec_hash(bundle),
        "roles": [role.model_dump(mode="json") for role in bundle.roles],
        "authentication": "local_accounts_with_server_sessions",
        "session_hours": 8,
        "default_accounts": [],
        "domain_ui": ["relation_selection", "substring_search", "offset_paging", "row_edit"]
        if bundle.domain
        else [],
        "technical_tables": [
            "_specton_commands",
            "_specton_users",
            "_specton_sessions",
            "_specton_login_attempts",
        ],
        "business_schema": "backend/approved.sql",
        "operations_guide": "OPERATIONS.md",
        "business_acceptance": "not_run",
        "deployment": "not_run",
        "authentication_data_migration": "separate_contract_required",
    }
