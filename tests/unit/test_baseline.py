"""고정 합성 기준선은 의도하지 않은 정리·생성·추적 변경을 검출한다."""

import json
from pathlib import Path

import pytest

from specton.evaluation.baseline import (
    DEFAULT_EXPECTED,
    DEFAULT_FIXTURE,
    SIZES,
    digest,
    run_case,
    source_csv,
)


@pytest.mark.parametrize("size", SIZES)
def test_fixed_synthetic_input_matches_recorded_artifact_hashes(size: int) -> None:
    fixture = json.loads(DEFAULT_FIXTURE.read_bytes())
    expected = json.loads(DEFAULT_EXPECTED.read_bytes())
    assert fixture["origin"] == "synthetic"
    assert digest(DEFAULT_FIXTURE.read_bytes()) == expected["fixture_hash"]
    actual = run_case(fixture, size, pack_root=Path("domain_packs"))
    assert actual["tables"] == 4
    assert actual["foreign_keys"] == 3
    assert actual["trace_counts"]["연결"] == size
    assert actual["trace_counts"]["미연결"] == 0
    assert actual == expected["cases"][str(size)]


def test_baseline_does_not_silently_use_a_new_pack_version() -> None:
    fixture = json.loads(DEFAULT_FIXTURE.read_bytes())
    fixture["pack_version"] = "0.0.0"
    with pytest.raises(ValueError, match="pack_mismatch"):
        run_case(fixture, 20, pack_root=Path("domain_packs"))


def test_synthetic_csv_is_reproducible_and_has_no_real_customer_identifiers() -> None:
    fixture = json.loads(DEFAULT_FIXTURE.read_bytes())
    csv = source_csv(fixture, 20)
    assert csv == source_csv(fixture, 20)
    assert len(csv.decode().splitlines()) == 21
    assert "SYN-0020" in csv.decode()
