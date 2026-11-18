"""Freeze and run bounded, exploratory evaluation on inventory and maintenance documents.

No DB, customer approvals, gold-to-prompt injection, automatic repairs or candidate adoption.
Private output includes source text; publish only aggregate findings after review.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import unicodedata
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from openpyxl import load_workbook  # type: ignore[import-untyped]

from specton.agent_nodes import design_nodes
from specton.codegen.ddl import generate_ddl
from specton.codegen.erd import render_erd
from specton.codegen.function_spec import render_function_spec
from specton.codegen.model import Normalized
from specton.codegen.normalize_step import normalize_design
from specton.codegen.rtm import render_rtm_csv
from specton.config import Settings
from specton.contracts import DesignState
from specton.contracts.state import VersionInfo, find_trace_issues
from specton.evaluation.domain_diagnostics import diagnose
from specton.evaluation.preparation import digest, split_counts
from specton.graph import GraphState, initial_state
from specton.ingest.tabular import read_excel
from specton.llm.errors import LLMError
from specton.llm.openai_transport import openai_client
from specton.packs.loader import load_pack
from specton.packs.provenance import policy_digest
from specton.pilot import _RecordedClient
from specton.specification.capabilities import ScopeRequirement, assess

ROOT = Path(__file__).resolve().parents[2]
CONFIG_KEYS = (
    "design_model",
    "design_reasoning_effort",
    "max_output_tokens",
    "max_tokens_per_run",
    "max_structured_retries",
    "llm_timeout_seconds",
    "llm_api_retries",
    "run_timeout_seconds",
)
OVERRIDES: dict[str, Any] = {
    "max_output_tokens": 24000,
    "max_tokens_per_run": 100000,
    "max_structured_retries": 1,
    "llm_timeout_seconds": 180.0,
    "llm_api_retries": 0,
    "run_timeout_seconds": 1800,
}
BATCH_TOKEN_LIMIT = 300000


def dump(path: Path, data: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def code_digest() -> str:
    """Include dirty/untracked production files; a Git commit alone is insufficient."""
    files = [ROOT / "pyproject.toml", ROOT / "uv.lock"]
    for folder in ("specton", "domain_packs"):
        files.extend(
            p
            for p in (ROOT / folder).rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
        )
    records = [(p.relative_to(ROOT).as_posix(), digest(p)) for p in sorted(files)]
    return hashlib.sha256(json.dumps(records, ensure_ascii=True).encode()).hexdigest()


def workbook_rows(path: Path, sheet: str) -> list[dict[str, Any]]:
    workbook = load_workbook(path, read_only=True, data_only=False)
    try:
        if any(c.data_type == "f" for s in workbook for row in s for c in row):
            raise ValueError("Evaluation input/gold must not contain formulas")
        rows = iter(workbook[sheet].values)
        headers = next(rows)
        return [dict(zip(headers, row, strict=True)) for row in rows if row[0]]
    finally:
        workbook.close()


def matching_file(folder: Path, name: str) -> Path:
    matches = [p for p in folder.glob("*.xlsx") if unicodedata.normalize("NFC", p.name) == name]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one evaluation workbook: {name}")
    return matches[0]


def prepare(data: Path, out: Path, settings: Settings) -> Path:
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    frozen = out / "frozen"
    frozen.mkdir(mode=0o700)
    documents = []
    for pack_id, title in (("inventory", "재고"), ("maintenance", "설비")):
        pack = load_pack(pack_id, root=settings.pack_root)
        for number in range(1, 6):
            doc_id = f"{pack_id}-{number}"
            item: dict[str, Any] = {"id": doc_id, "pack_id": pack_id, "number": number}
            for kind, label in (("input", "입력"), ("gold", "정답")):
                folder = (
                    data
                    if pack_id == "inventory"
                    else data / "maintenance-v0.1" / ("inputs" if kind == "input" else "gold")
                )
                original = matching_file(folder, f"평가_{title}_문서{number}_{label}.xlsx")
                copied = frozen / f"{doc_id}-{kind}.xlsx"
                shutil.copyfile(original, copied)
                item[kind] = {
                    "original": str(original.resolve()),
                    "file": str(copied.relative_to(out)),
                    "sha256": digest(copied),
                }
            parsed = read_excel(out / item["input"]["file"], doc_id)
            gold = workbook_rows(out / item["gold"]["file"], "정답 기준")
            ids = [s.source_id for s in parsed.requirements]
            if (
                parsed.issues
                or parsed.skipped_sheets
                or not ids
                or len(ids) != len(set(ids))
                or set(ids) != {r["요구사항 ID"] for r in gold}
                or any(s.extraction_status.value != "pass" for s in parsed.requirements)
            ):
                raise ValueError(f"{doc_id}: extraction or source/gold correspondence failed")
            for row in gold:
                split_counts(row)
            item.update(
                {
                    "source_rows": len(ids),
                    "source_ids": ids,
                    "pack_version": pack.manifest.version,
                    "common_version": pack.common.manifest.version,
                    "policy_digest": policy_digest(settings.pack_root, pack_id),
                    "stages": ["a01", "a02", "a03", "a04", "normalize", "artifacts"]
                    if number == 1
                    else ["a01"],
                    "gold_status": "draft_author_confirmation_pending"
                    if pack_id == "inventory"
                    else "ai_reviewed_exploratory_only",
                }
            )
            documents.append(item)
    plan = {
        "kind": "multi_domain_exploration_v1",
        "created_at": datetime.now(UTC).isoformat(),
        "independent_holdout": False,
        "semantic_accuracy": None,
        "representative_selection": "document 1 of each domain selected before observations",
        "config": {key: getattr(settings, key) for key in CONFIG_KEYS},
        "batch_token_limit": BATCH_TOKEN_LIMIT,
        "budget_note": "Reported token budget; an in-flight call can exceed the input allowance."
        " SDK retries disabled. Unknown usage after API failure is not treated as zero cost.",
        "code_sha256": code_digest(),
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "documents": documents,
    }
    dump(out / "plan.json", plan)
    return out / "plan.json"


def verify_plan(path: Path, settings: Settings) -> dict[str, Any]:
    plan: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if plan["kind"] != "multi_domain_exploration_v1" or code_digest() != plan["code_sha256"]:
        raise ValueError("Frozen code changed; prepare a new, separately identified experiment")
    if plan["config"] != {key: getattr(settings, key) for key in CONFIG_KEYS}:
        raise ValueError("Model/runtime settings differ from the frozen plan")
    for doc in plan["documents"]:
        for kind in ("input", "gold"):
            for file in (path.parent / doc[kind]["file"], Path(doc[kind]["original"])):
                if digest(file) != doc[kind]["sha256"]:
                    raise ValueError("Input/gold hash differs from frozen plan")
        if policy_digest(settings.pack_root, doc["pack_id"]) != doc["policy_digest"]:
            raise ValueError("Domain policy differs from frozen plan")
    return plan


def design_for(doc: dict[str, Any], out: Path) -> DesignState:
    return DesignState(
        run_id=f"eval-{doc['id']}",
        versions=VersionInfo(
            document_hash=doc["input"]["sha256"],
            pack_id=doc["pack_id"],
            pack_version=doc["pack_version"],
            common_version=doc["common_version"],
            policy_digest=doc["policy_digest"],
        ),
        source_requirements=read_excel(out / doc["input"]["file"], doc["id"]).requirements,
    )


def downstream(state: DesignState, destination: Path, settings: Settings) -> dict[str, Any]:
    normalized = normalize_design(state, root=settings.pack_root)
    dump(destination / "normalization.json", normalized.model_dump(mode="json"))
    result: dict[str, Any] = {
        "trace_issues": [i.model_dump(mode="json") for i in find_trace_issues(state)],
        "functions": len(state.functions),
        "entities": len(state.entities),
        "relationships": len(state.relationships),
        "artifacts": "not_run",
        "sql_execution": "not_run",
        "system_generation": "not_run",
        "business_acceptance": "not_run",
    }
    if not isinstance(normalized, Normalized):
        result.update(
            normalization="failed",
            problems=dict(Counter(p.code.value for p in normalized.problems)),
        )
        return result
    state = state.evolve(normalized=normalized.model)
    dump(destination / "normalized-design.json", state.model_dump(mode="json"))
    files = {
        "functions.md": render_function_spec(state).encode(),
        "erd.mmd": render_erd(normalized.model, state.relationships).encode(),
        "schema.sql": generate_ddl(normalized.model, max_bytes=63).sql.encode(),
        "rtm.csv": render_rtm_csv(state),
    }
    for name, content in files.items():
        (destination / name).write_bytes(content)
    result.update(
        normalization="passed",
        artifacts="generated_unapproved",
        artifact_hashes={name: digest(destination / name) for name in files},
    )
    return result


def execute(path: Path, settings: Settings) -> dict[str, Any]:
    plan = verify_plan(path, settings)
    out = path.parent / "observations"
    out.mkdir(mode=0o700)  # never overwrite prior observations or silently rerun failures
    started = perf_counter()
    client = _RecordedClient(
        openai_client(settings), plan["batch_token_limit"], started + settings.run_timeout_seconds
    )
    nodes = design_nodes(lambda: client, settings)
    report: dict[str, Any] = {
        "kind": plan["kind"],
        "plan_sha256": digest(path),
        "status": "running",
        "semantic_accuracy": None,
        "independent_holdout": False,
        "business_acceptance": "not_run",
        "documents": [],
    }
    dump(out / "report.json", report)
    for doc in plan["documents"]:
        destination = out / doc["id"]
        destination.mkdir(mode=0o700)
        state = initial_state(design_for(doc, path.parent))
        record: dict[str, Any] = {
            "id": doc["id"],
            "pack_id": doc["pack_id"],
            "source_rows": doc["source_rows"],
            "stages": {},
            "business_acceptance": "not_run",
        }
        report["documents"].append(record)
        scope = assess(
            tuple(
                ScopeRequirement(
                    id=s.source_id or s.block_id, text=s.source_text or "", kind="unclassified"
                )
                for s in state["design"].source_requirements
            ),
            0,
        )
        dump(destination / "scope-advisory.json", scope.model_dump(mode="json"))
        record["scope_extension_candidates"] = scope.extension_candidates
        before = len(client.calls)
        for stage in doc["stages"]:
            if stage == "artifacts":
                continue  # included in downstream(), after normalization
            print(f"{doc['id']} {stage}: started", flush=True)
            try:
                if stage == "normalize":
                    record["downstream"] = downstream(state["design"], destination, settings)
                    record["stages"][stage] = record["downstream"]["normalization"]
                    record["stages"]["artifacts"] = record["downstream"]["artifacts"]
                else:
                    update = nodes[stage](state)
                    state = GraphState(
                        design=update["design"],
                        tokens_used=state.get("tokens_used", 0) + update["tokens_used"],
                    )
                    dump(destination / f"{stage}.json", state["design"].model_dump(mode="json"))
                    record["stages"][stage] = "passed"
                    if stage == "a01":
                        diagnostic = diagnose(
                            state["design"],
                            workbook_rows(path.parent / doc["gold"]["file"], "정답 기준"),
                        )
                        dump(destination / "a01-diagnostics.json", diagnostic)
                        record["a01_diagnostics"] = {
                            k: v for k, v in diagnostic.items() if k != "rows"
                        }
            except (LLMError, ValueError, KeyError, TypeError, OSError) as exc:
                record["stages"][stage] = "failed"
                record["error_code"] = exc.code if isinstance(exc, LLMError) else type(exc).__name__
                # Details may contain source text; keep them only in this private directory.
                (destination / "error.txt").write_text(str(exc), encoding="utf-8")
                break
            finally:
                record["calls"] = [c.model_dump(mode="json") for c in client.calls[before:]]
                report["usage"] = {
                    "input_tokens": sum(c.input_tokens for c in client.calls),
                    "output_tokens": sum(c.output_tokens for c in client.calls),
                    "calls": len(client.calls),
                    "usage_complete": all(
                        c.outcome not in {"api_error", "timeout"} for c in client.calls
                    ),
                }
                dump(out / "report.json", report)
                print(
                    f"{doc['id']} {stage}: {record['stages'].get(stage, 'interrupted')}", flush=True
                )
        for stage in doc["stages"]:
            record["stages"].setdefault(stage, "not_run")
    report["status"] = "completed"
    report["wall_time_ms"] = int((perf_counter() - started) * 1000)
    report["provenance_verified_after_run"] = bool(verify_plan(path, settings))
    dump(out / "report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    frozen = commands.add_parser("prepare")
    frozen.add_argument("--data", type=Path, required=True)
    frozen.add_argument("--out", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("plan", type=Path)
    args = parser.parse_args()
    settings = Settings(**OVERRIDES, pack_root=ROOT / "domain_packs")
    try:
        if args.command == "prepare":
            print(prepare(args.data, args.out, settings))
        else:
            report = execute(args.plan, settings)
            print(json.dumps({"status": report["status"], "usage": report["usage"]}))
    except (OSError, ValueError, KeyError, TypeError, LLMError) as exc:
        print(f"Evaluation stopped: {type(exc).__name__}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
