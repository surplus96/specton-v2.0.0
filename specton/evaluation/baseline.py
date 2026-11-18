"""합성 입력의 결정론 경로 측정. LLM·DB·PDF·업무 앱 인수와 구분한다."""

import argparse
import csv
import hashlib
import io
import json
import math
import platform
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from specton.codegen.ddl import generate_ddl
from specton.codegen.erd import render_erd
from specton.codegen.function_spec import render_function_spec
from specton.codegen.naming import load_naming_rules
from specton.codegen.normalize_step import normalize_design
from specton.codegen.rtm import build_rtm, counts, render_rtm_csv, render_rtm_xlsx
from specton.contracts import DesignState, Entity, Function, Relationship, Requirement, VersionInfo
from specton.contracts.normalized import Normalized
from specton.contracts.state import find_trace_issues
from specton.ingest.tabular import read_csv
from specton.model_hash import model_hash

DEFAULT_FIXTURE = Path("tests/fixtures/baseline/inventory-v1.json")
DEFAULT_EXPECTED = Path("tests/fixtures/baseline/expected-v1.json")
SIZES = (20, 200, 1000)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_tree_hash() -> str:
    return digest(
        b"".join(
            str(path).encode() + b"\0" + digest(path.read_bytes()).encode() + b"\n"
            for path in sorted(Path("specton").rglob("*.py"))
        )
    )


def process_peak_rss_bytes() -> int | None:
    try:
        import resource
    except ImportError:
        return None  # Windows에서는 미측정으로 기록한다.
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024


def source_csv(fixture: dict[str, Any], size: int) -> bytes:
    if size not in SIZES:
        raise ValueError(f"지원하는 기준 크기: {SIZES}")
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("요구사항 ID", "요구사항명", "상세 내용"))
    scenarios = fixture["scenarios"]
    for index in range(size):
        name, description = scenarios[index % len(scenarios)]
        writer.writerow((f"SYN-{index + 1:04}", name, description))
    return output.getvalue().encode()


def run_case(fixture: dict[str, Any], size: int, *, pack_root: Path) -> dict[str, Any]:
    """실제 파서·정리·네 생성기를 실행하고 승인되지 않은 결과의 해시를 반환한다."""
    source = source_csv(fixture, size)
    with TemporaryDirectory(prefix="specton-baseline-") as directory:
        path = Path(directory) / "requirements.csv"
        path.write_bytes(source)
        parsed = read_csv(path, "synthetic-inventory-v1")
    sources = parsed.requirements
    if len(sources) != size or any(s.extraction_status != "pass" for s in sources):
        raise ValueError("합성 입력 추출 결과가 기준과 다릅니다")
    requirements = tuple(
        Requirement(
            id=f"REQ-{index:02}",
            source_id=block.source_id,
            source_ref=block.source_ref,
            text=block.source_text,
            draft_text=block.source_text,
            type="FR",
            analysis_version=1,
        )
        for index, block in enumerate(sources, 1)
    )
    design = DesignState(
        run_id="00000000-0000-4000-8000-000000000001",
        revision=1,
        versions=VersionInfo(
            document_hash=digest(source),
            pack_id=fixture["pack"],
            pack_version=fixture["pack_version"],
        ),
        source_requirements=sources,
        requirements=requirements,
        functions=tuple(
            Function(
                id=f"FUNC-{index:02}",
                name=f"합성 기능 {index}",
                description=req.text,
                req_ids=(req.id,),
            )
            for index, req in enumerate(requirements, 1)
        ),
        entities=tuple(Entity.model_validate(e) for e in fixture["entities"]),
        relationships=tuple(Relationship.model_validate(r) for r in fixture["relationships"]),
    )
    if find_trace_issues(design):
        raise ValueError("합성 설계의 원문 추적이 유효하지 않습니다")
    normalized = normalize_design(design, root=pack_root)
    if not isinstance(normalized, Normalized):
        raise ValueError(f"합성 설계 정리 실패: {normalized.problems}")
    design = design.evolve(normalized=normalized.model)
    contents = {
        "functions.md": render_function_spec(design).encode(),
        "erd.mmd": render_erd(normalized.model, design.relationships).encode(),
        "ddl.sql": generate_ddl(
            normalized.model, max_bytes=load_naming_rules(pack_root).max_bytes
        ).sql.encode(),
        "rtm.csv": render_rtm_csv(design),
        "rtm.xlsx": render_rtm_xlsx(design),
    }
    return {
        "source_blocks": len(sources),
        "requirements": len(requirements),
        "tables": len(normalized.model.tables),
        "foreign_keys": len(normalized.model.foreign_keys),
        "source_hash": digest(source),
        "model_hash": model_hash(design),
        "policy_digest": normalized.model.policy_digest,
        "lexicon_digest": normalized.model.lexicon_digest,
        "trace_counts": counts(build_rtm(design)),
        "artifacts": {
            name: {"sha256": digest(data), "bytes": len(data)} for name, data in contents.items()
        },
    }


def measure(fixture_path: Path, pack_root: Path, sizes: list[int], repeats: int) -> dict[str, Any]:
    code_hash = source_tree_hash()
    measured_at = datetime.now(UTC).isoformat()
    fixture = json.loads(fixture_path.read_bytes())
    if fixture.get("origin") != "synthetic":
        raise ValueError("기준선에는 synthetic 입력만 사용합니다")
    cases = {}
    for size in sizes:
        expected = run_case(fixture, size, pack_root=pack_root)  # 워밍업 1회
        durations = []
        for _ in range(repeats):
            start = time.perf_counter()
            actual = run_case(fixture, size, pack_root=pack_root)
            durations.append((time.perf_counter() - start) * 1000)
            if actual != expected:
                raise ValueError(f"{size} 블록 결과가 반복 실행에서 달라졌습니다")
        ordered = sorted(durations)
        cases[str(size)] = {
            "output": expected,
            "timing_ms": {
                "p50": statistics.median(ordered),
                "p95": ordered[math.ceil(len(ordered) * 0.95) - 1],
                "max": max(ordered),
            },
            "successful_repeats": repeats,
        }
    if source_tree_hash() != code_hash:
        raise ValueError("측정 중 코드가 변경되었습니다. 코드 고정 후 다시 실행하세요")
    return {
        "schema_version": "baseline-v1",
        "origin": "synthetic",
        "fixture_hash": digest(fixture_path.read_bytes()),
        "lock_hash": digest(Path("uv.lock").read_bytes()),
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "scope": "parse-normalize-generate; no LLM, DB, PDF, application acceptance",
        "prompt_versions": {},
        "failures": 0,
        "measured_at": measured_at,
        "warmup_repeats": 1,
        "process_peak_rss_bytes": process_peak_rss_bytes(),
        "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "working_tree_dirty": bool(
            subprocess.check_output(
                ["git", "status", "--porcelain", "--untracked-files=all", "--", "specton"]
            ).strip()
        ),
        "source_tree_hash": code_hash,
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--pack-root", type=Path, default=Path("domain_packs"))
    parser.add_argument("--sizes", type=int, nargs="+", choices=SIZES, default=list(SIZES))
    parser.add_argument("--repeats", type=int, default=30)
    parser.add_argument("--output", type=Path, default=Path("var/baseline/report.json"))
    parser.add_argument("--check", type=Path, default=DEFAULT_EXPECTED)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 1000:
        parser.error("repeats는 1~1000 사이여야 합니다")
    try:
        report = measure(args.fixture, args.pack_root, args.sizes, args.repeats)
        expected = json.loads(args.check.read_bytes())
        if report["fixture_hash"] != expected["fixture_hash"]:
            raise ValueError("기준 fixture 해시가 변경되었습니다")
        for size, case in report["cases"].items():
            if case["output"] != expected["cases"][size]:
                raise ValueError(f"{size} 블록 산출물 해시/추적 결과가 기준과 다릅니다")
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"기준선 검사 실패: {exc}\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"기준선 검사 통과: {args.output}")


if __name__ == "__main__":
    main()
