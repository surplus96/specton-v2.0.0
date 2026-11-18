"""Attribute executed API checks without treating prose acceptance as executed tests."""

from typing import Any

from specton.contracts.specification import SpecBundle
from specton.implementation.acceptance_evidence import case_results


def requirement_results(
    bundle: SpecBundle, checks: list[dict[str, Any]], scenarios: dict[str, Any] | None = None
) -> dict[str, Any]:
    results = case_results(bundle, scenarios)
    known = {a.id for a in bundle.apis}
    evidence: dict[str, list[dict[str, Any]]] = {}
    for check in checks:
        aid = check.get("api_id")
        if aid in known:
            evidence.setdefault(aid, []).append(check)
    items = []
    for req in bundle.requirements:
        uses = {u.id for u in bundle.use_cases if req.id in u.req_ids}
        aids = sorted(a.id for a in bundle.apis if a.use_case_id in uses)
        passed = [
            aid
            for aid in aids
            if evidence.get(aid) and all(c.get("status") == "passed" for c in evidence[aid])
        ]
        failed = [
            aid for aid in aids if any(c.get("status") == "failed" for c in evidence.get(aid, []))
        ]
        status = (
            "failed"
            if failed
            else "checks_passed"
            if aids and len(passed) == len(aids)
            else "partial"
            if passed
            else "not_run"
        )
        items.append(
            {
                "requirement_id": req.id,
                "text": req.text,
                "priority": req.priority,
                "api_check_status": status,
                "api_ids": aids,
                "passed_api_ids": passed,
                "failed_api_ids": failed,
                "missing_api_ids": sorted(set(aids) - set(passed) - set(failed)),
                "checks": [c for aid in aids for c in evidence.get(aid, [])],
                "invariant_ids": [i.id for i in bundle.invariants if req.id in i.req_ids],
                "acceptance_cases": [
                    {
                        "id": t.id,
                        "tier": t.tier,
                        **results[t.id],
                        "execution_kind": "api" if t.execution else "prose",
                        "category": t.execution.category if t.execution else None,
                    }
                    for t in bundle.acceptance_cases
                    if req.id in t.req_ids
                ],
                "business_acceptance": "not_run",
            }
        )
    return {
        "version": "requirement-evidence-v2",
        "notice": (
            "승인 명세의 연결을 따라 실제 API 검사 결과를 표시합니다. "
            "API 검사 통과는 요구 문장·업무 규칙 전체의 충족을 뜻하지 않습니다. "
            "실행 계약이 있는 사례는 단계별 결과를 표시하며, 자연어만 있는 사례는 미실행입니다."
        ),
        "items": items,
    }
