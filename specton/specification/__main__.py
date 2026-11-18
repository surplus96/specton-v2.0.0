"""실행 명세를 검토할 준비가 됐는지 검사한다. 이 명령은 승인·생성을 수행하지 않는다."""

import argparse
from pathlib import Path

from pydantic import ValidationError

from specton.contracts.specification import SpecBundle
from specton.specification.readiness import assess_readiness


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    args = parser.parse_args()
    try:
        report = assess_readiness(SpecBundle.model_validate_json(args.spec.read_bytes()))
    except (OSError, ValidationError) as exc:
        # 고객 명세 본문·경로를 오류 로그에 덤프하지 않는다.
        message = (
            "명세 파일을 읽을 수 없습니다"
            if isinstance(exc, OSError)
            else "명세 계약이 유효하지 않습니다"
        )
        parser.exit(2, message + "\n")
    print(report.model_dump_json(indent=2))
    if not report.ready_for_review:
        parser.exit(1)


if __name__ == "__main__":
    main()
