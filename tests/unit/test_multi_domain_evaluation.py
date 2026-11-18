"""Exploratory diagnostics must preserve provenance and never manufacture acceptance."""

import json
from pathlib import Path

import pytest
from openpyxl import Workbook

from specton.config import Settings
from specton.contracts import DesignState, Requirement, SourceRequirement
from specton.evaluation import multi_domain as md
from specton.evaluation.domain_diagnostics import diagnose
from specton.llm.errors import LLMAPIError


def gold(source="S-1", **changes):
    return {
        "요구사항 ID": source,
        "기대 분류": "FR",
        "기대 분할 수": 1,
        "허용 분할 수": "1\u223c2",
        **changes,
    }


def requirement(source="S-1", req_id="REQ-01", kind="FR", warnings=()):
    return Requirement.model_validate(
        {
            "id": req_id,
            "source_id": source,
            "source_ref": {"file_format": "xlsx", "sheet": "test", "row": 2},
            "text": "시험 요구",
            "draft_text": "시험 요구",
            "type": kind,
            "nfr_category": "other" if kind == "NFR" else None,
            "analysis_version": 1,
            "quality_issues": [{"kind": q, "message": "검토"} for q in warnings],
        }
    )


def test_missing_unknown_and_split_mismatch_are_visible():
    state = DesignState(
        run_id="test", requirements=(requirement(), requirement("unknown", "REQ-02"))
    )
    report = diagnose(state, [gold(), gold("S-2")])
    assert report["covered_sources"] == report["split_compatible_sources"] == 1
    assert report["unknown_source_predictions"] == ["REQ-02"]
    assert report["semantic_accuracy"] is None
    assert report["independent_holdout"] is False


def test_warning_or_and_groups_are_checked_once_per_source():
    state = DesignState(
        run_id="test",
        requirements=(
            requirement(warnings=("ambiguous", "missing_target")),
            requirement(req_id="REQ-02", warnings=("ambiguous", "added_number")),
        ),
    )
    report = diagnose(
        state, [gold(**{"기대 경고(필수)": "missing_value|ambiguous, missing_target"})]
    )
    assert report["matched_warning_groups"] == report["required_warning_groups"] == 2
    assert report["rows"][0]["unexpected_warnings"] == ["added_number"]
    assert report["split_compatible_sources"] == 1


def test_mixed_labels_need_both_but_never_claim_semantic_accuracy():
    state = DesignState(run_id="test", requirements=(requirement(),))
    assert diagnose(state, [gold(**{"기대 분류": "혼합"})])["label_set_compatible_sources"] == 0
    state = state.evolve(
        requirements=(*state.requirements, requirement(req_id="REQ-02", kind="NFR"))
    )
    report = diagnose(state, [gold(**{"기대 분류": "혼합"})])
    assert report["label_set_compatible_sources"] == 1
    assert report["semantic_accuracy"] is None


def test_duplicate_gold_ids_fail():
    with pytest.raises(ValueError, match="unique"):
        diagnose(DesignState(run_id="test"), [gold(), gold()])


def test_merging_requirements_does_not_hide_missing_numeric_conditions():
    source = SourceRequirement(
        document_id="test",
        block_id="B-1",
        source_id="S-1",
        source_ref={"file_format": "xlsx", "sheet": "test", "row": 2},
        source_text="최대 1,000건을 조회하고 이력을 7일 보존한다.",
        extraction_status="pass",
    )
    predicted = requirement().evolve(text="최대 1000건을 조회한다.")
    state = DesignState(run_id="test", source_requirements=(source,), requirements=(predicted,))
    result = diagnose(state, [gold()])
    assert result["covered_sources"] == 1
    assert result["numeric_retention_review_sources"] == 1
    assert result["rows"][0]["source_numbers_missing"] == ["7"]
    preserved = predicted.evolve(text=source.source_text)
    assert (
        diagnose(state.evolve(requirements=(preserved,)), [gold()])[
            "numeric_retention_review_sources"
        ]
        == 0
    )


@pytest.fixture
def frozen(tmp_path):
    data = tmp_path / "data"
    for pack, title in (("inventory", "재고"), ("maintenance", "설비")):
        for number in range(1, 6):
            for kind, label in (("input", "입력"), ("gold", "정답")):
                folder = (
                    data
                    if pack == "inventory"
                    else data / "maintenance-v0.1" / ("inputs" if kind == "input" else "gold")
                )
                folder.mkdir(parents=True, exist_ok=True)
                workbook = Workbook()
                sheet = workbook.active
                sheet.title = "요구사항 정의서" if kind == "input" else "정답 기준"
                if kind == "input":
                    sheet.append(["요구사항 ID", "상세 설명"])
                    sheet.append(["S-1", "설비번호를 등록한다."])
                else:
                    sheet.append(list(gold()))
                    sheet.append(list(gold().values()))
                workbook.save(folder / f"평가_{title}_문서{number}_{label}.xlsx")
    settings = Settings(**md.OVERRIDES, pack_root=md.ROOT / "domain_packs")
    plan = md.prepare(data, tmp_path / "experiment", settings)
    return plan, settings


def test_freeze_selects_representatives_before_observation_and_no_secrets(frozen):
    path, settings = frozen
    plan = md.verify_plan(path, settings)
    assert len(plan["documents"]) == 10
    assert [d["id"] for d in plan["documents"] if "a04" in d["stages"]] == [
        "inventory-1",
        "maintenance-1",
    ]
    assert "openai_api_key" not in plan["config"]
    assert "app_database_url" not in plan["config"]
    assert not (path.parent / "observations").exists()


@pytest.mark.parametrize("target", ["input", "gold"])
def test_changed_original_or_frozen_hash_rejected(frozen, target):
    path, settings = frozen
    plan = md.verify_plan(path, settings)
    filename = (
        path.parent / plan["documents"][0][target]["file"]
        if target == "gold"
        else Path(plan["documents"][0][target]["original"])
    )
    filename.write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash"):
        md.verify_plan(path, settings)


def test_changed_code_or_model_rejected(frozen, monkeypatch):
    path, settings = frozen
    with pytest.raises(ValueError, match="settings"):
        md.verify_plan(path, settings.model_copy(update={"design_model": "different"}))
    monkeypatch.setattr(md, "code_digest", lambda: "changed")
    with pytest.raises(ValueError, match="code"):
        md.verify_plan(path, settings)


def test_failed_stage_never_becomes_pass_or_overwrites_observations(frozen, monkeypatch):
    path, settings = frozen
    monkeypatch.setattr(md, "openai_client", lambda settings: object())

    def fail(state):
        raise LLMAPIError("injected failure")

    monkeypatch.setattr(md, "design_nodes", lambda get_client, settings: {"a01": fail})
    report = md.execute(path, settings)
    assert len(report["documents"]) == 10
    assert report["documents"][0]["stages"] == {
        "a01": "failed",
        "a02": "not_run",
        "a03": "not_run",
        "a04": "not_run",
        "normalize": "not_run",
        "artifacts": "not_run",
    }
    assert report["business_acceptance"] == "not_run"
    assert "a01_diagnostics" not in report["documents"][0]
    assert (
        json.loads((path.parent / "observations/report.json").read_text())["status"] == "completed"
    )
    with pytest.raises(FileExistsError):
        md.execute(path, settings)
