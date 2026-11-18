"""Validate a review-only preparation against a saved spec and its approved design snapshot.

No database, approval, LLM or customer service calls. The output directory must be new.
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path

from specton.contracts import DesignState
from specton.contracts.specification import SpecBundle
from specton.specification.preparation import TestPreparation, validate_preparation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-spec", required=True, type=Path)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--preparation", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    base = SpecBundle.model_validate_json(args.base_spec.read_bytes())
    state = DesignState.model_validate_json(args.state.read_bytes())
    proposal = TestPreparation.model_validate_json(args.preparation.read_bytes())
    report = validate_preparation(base, proposal, state)
    report["input_hashes"] = {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (args.base_spec, args.state, args.preparation)
    }
    args.out.mkdir(parents=True, exist_ok=False, mode=0o700)
    (args.out / "validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    requirements = {r.id: r for r in proposal.bundle.requirements}
    with (args.out / "scope.csv").open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["원본 ID", "요구 ID", "원문", "첫 E2E 범위", "사유"])
        for item in proposal.scope:
            req = requirements[item.requirement_id]
            # Excel cells with customer text are data, not spreadsheet formula instructions.
            cells = [req.legacy_id or "", req.id, req.text, item.disposition, item.rationale]
            writer.writerow(
                ["'" + c if c.lstrip().startswith(("=", "+", "-", "@")) else c for c in cells]
            )
    cases = [c.model_dump(mode="json") for c in proposal.bundle.acceptance_cases if c.execution]
    (args.out / "acceptance-cases.json").write_text(
        json.dumps(cases, ensure_ascii=False, indent=2) + "\n"
    )
    (args.out / "proposed-answers.json").write_text(
        json.dumps(
            [a.model_dump(mode="json") for a in proposal.answer_proposals],
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    print(json.dumps({k: v for k, v in report.items() if k != "input_hashes"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
