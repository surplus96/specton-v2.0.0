"""Check that scenario evidence covers the exact approved steps, in order."""

from typing import Any

from specton.contracts.specification import SpecBundle


def case_results(bundle: SpecBundle, evidence: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    rows = (evidence or {}).get("cases", [])
    if not isinstance(rows, list):
        rows = []
    results = {}
    for case in bundle.acceptance_cases:
        result: dict[str, Any] = {"status": "not_run", "steps": []}
        if case.execution:
            matches = [r for r in rows if isinstance(r, dict) and r.get("id") == case.id]
            if len(matches) == 1:
                row = matches[0]
                steps = row.get("steps", [])
                same = (
                    row.get("req_ids") == list(case.req_ids)
                    and row.get("category") == case.execution.category
                )
                if same and row.get("status") == "failed":
                    result = {"status": "failed", "steps": steps, "reason": row.get("reason")}
                elif (
                    same
                    and row.get("status") == "passed"
                    and isinstance(steps, list)
                    and len(steps) == len(case.execution.steps)
                    and all(
                        isinstance(actual, dict)
                        and actual.get("status") == "passed"
                        and actual.get("index") == index
                        and actual.get("api_id") == planned.api_id
                        for index, (actual, planned) in enumerate(
                            zip(steps, case.execution.steps, strict=True), 1
                        )
                    )
                ):
                    result = {"status": "passed", "steps": steps}
        results[case.id] = result
    return results


def require_passed(bundle: SpecBundle, evidence: dict[str, Any] | None) -> None:
    planned = [t for t in bundle.acceptance_cases if t.execution]
    if not planned:
        return
    results = case_results(bundle, evidence)
    if (evidence or {}).get("status") != "passed" or any(
        results[t.id]["status"] != "passed" for t in planned
    ):
        raise ValueError("승인된 실행 인수 사례의 통과 근거가 없거나 단계가 다릅니다")
    if len((evidence or {}).get("cases", [])) != len(planned):
        raise ValueError("승인된 실행 인수 사례 목록과 검증 결과가 다릅니다")
