"""Offline review of a saved spec and authored contracts; never approve or run an app.

Example: .venv/bin/python scripts/review_delivery_readiness.py --spec saved.json
  --contracts var/review/contracts.json --out var/test-results/review
The output directory must not exist, so previous evidence cannot be overwritten.
"""

import argparse
import hashlib
import json
from pathlib import Path

from specton.contracts import DesignState
from specton.contracts.specification import SpecBundle
from specton.implementation.compiler import compile_contract
from specton.model_hash import model_hash
from specton.specification.contract_review import ContractReview, validate_review
from specton.specification.handoff import assess_handoff
from specton.specification.readiness import assess_readiness


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--contracts", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    spec = SpecBundle.model_validate_json(args.spec.read_bytes())
    generator_error: str | None = (
        "오프라인 명세 점검: 원본 설계 모델이 없어 엄격한 생성 검사를 실행하지 않았습니다."
    )
    if args.state:
        state = DesignState.model_validate_json(args.state.read_bytes())
        if model_hash(state) != spec.baseline.model_hash:
            raise ValueError("명세와 원본 설계 모델의 해시가 다릅니다.")
        try:
            compile_contract(spec, state)
            generator_error = None
        except ValueError as exc:
            generator_error = str(exc)
    report = assess_handoff(
        spec,
        assess_readiness(spec),
        approved=False,
        is_latest=False,
        generator_error=generator_error,
    )
    review = (
        ContractReview.model_validate_json(args.contracts.read_bytes()) if args.contracts else None
    )
    checked = validate_review(spec, review) if review else None
    files = [
        args.spec,
        *([args.state] if args.state else []),
        *([args.contracts] if args.contracts else []),
    ]
    provenance = {
        "inputs": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        "contract_review": checked,
        "external_calls": 0,
        "customer_project_mutated": False,
        "approval_checked_in_database": False,
    }
    args.out.mkdir(parents=True, exist_ok=False, mode=0o700)
    (args.out / "readiness.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    (args.out / "provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "conclusion": report.conclusion,
                "requirements": len(report.contracts),
                "extension_hint_requirements": report.extension_hint_requirements,
                "contract_review": checked,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
