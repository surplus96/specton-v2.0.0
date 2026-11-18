"""Draft gold diagnostics by source row, without semantic alignment or approval claims."""

import re
from collections import Counter
from typing import Any

from specton.contracts import DesignState
from specton.evaluation.preparation import split_counts
from specton.nodes.a01_requirements import _numbers


def alternatives(value: Any) -> list[set[str]]:
    """Comma means AND; pipe means OR (the supplied evaluation workbook convention)."""
    return [set(part.strip().split("|")) for part in str(value or "").split(",") if part.strip()]


def diagnose(state: DesignState, gold: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare observable structure only. Matching label sets do not prove preserved meaning."""
    source_ids = [r["요구사항 ID"] for r in gold]
    if len(set(source_ids)) != len(source_ids) or any(not s for s in source_ids):
        raise ValueError("Gold source IDs must be present and unique")
    rows = []
    for cells in gold:
        source = cells["요구사항 ID"]
        predicted = [r for r in state.requirements if r.source_id == source]
        labels = {r.type.value for r in predicted}
        expected = cells["기대 분류"]
        if expected not in {"FR", "NFR", "혼합"}:
            raise ValueError("Unknown gold label")
        allowed_labels = set(re.findall(r"\b(?:FR|NFR)\b", cells.get("허용 분류") or ""))
        base_labels = {"FR", "NFR"} if expected == "혼합" else {expected}
        actual = {q.kind for r in predicted for q in r.quality_issues}
        source_numbers = set().union(
            *(
                _numbers(s.source_text or "")
                for s in state.source_requirements
                if s.source_id == source
            )
        )
        retained_numbers = set().union(*(_numbers(r.text) for r in predicted))
        required = alternatives(cells.get("기대 경고(필수)"))
        allowed = set().union(*required, *alternatives(cells.get("허용 경고")))
        rows.append(
            {
                "source_id": source,
                "predicted_ids": [r.id for r in predicted],
                "covered": bool(predicted),
                "split_count": len(predicted),
                "allowed_split_counts": split_counts(cells),
                "split_compatible": len(predicted) in split_counts(cells),
                "labels": dict(Counter(r.type.value for r in predicted)),
                "label_set_compatible": bool(predicted)
                and (
                    labels == base_labels
                    or (bool(allowed_labels) and labels <= base_labels | allowed_labels)
                ),
                "warnings": sorted(actual),
                "required_warning_groups": len(required),
                "matched_warning_groups": sum(bool(actual & group) for group in required),
                "missing_warning_groups": [
                    sorted(group) for group in required if not actual & group
                ],
                "unexpected_warnings": sorted(actual - allowed),
                "source_numbers_missing": sorted(source_numbers - retained_numbers),
            }
        )
    return {
        "kind": "exploratory_source_diagnostics_v1",
        "semantic_accuracy": None,
        "independent_holdout": False,
        "source_rows": len(rows),
        "predicted_requirements": len(state.requirements),
        "covered_sources": sum(r["covered"] for r in rows),
        "split_compatible_sources": sum(r["split_compatible"] for r in rows),
        "label_set_compatible_sources": sum(r["label_set_compatible"] for r in rows),
        "required_warning_groups": sum(r["required_warning_groups"] for r in rows),
        "matched_warning_groups": sum(r["matched_warning_groups"] for r in rows),
        "unexpected_warning_sources": sum(bool(r["unexpected_warnings"]) for r in rows),
        "numeric_retention_review_sources": sum(bool(r["source_numbers_missing"]) for r in rows),
        "unknown_source_predictions": [
            r.id for r in state.requirements if r.source_id not in source_ids
        ],
        "rows": rows,
    }
