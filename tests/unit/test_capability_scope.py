from specton.specification.capabilities import ScopeRequirement, assess


def test_plain_crud_is_not_certified_as_business_complete():
    report = assess((ScopeRequirement(id="R1", text="설비를 등록한다", kind="FR"),), 3)
    assert report.items[0].disposition == "needs_review"
    assert report.business_acceptance == "not_run"
    assert report.assessment_kind == "advisory"
    assert report.revision == 3


def test_extension_hints_preserve_evidence_and_all_requirements():
    requirements = (
        ScopeRequirement(
            id="R1", text="재고를 일괄 차감하고 이력을 함께 저장하며 모두 되돌린다", kind="FR"
        ),
        ScopeRequirement(id="R2", text="매월 평균 금액을 계산하여 알림을 보낸다", kind="FR"),
        ScopeRequirement(id="R3", text="백업은 이번 범위에서 제외한다", kind="NFR"),
    )
    report = assess(requirements, 1)
    assert len(report.items) == 3 and report.extension_candidates == 3
    assert report.items[0].hints[0].capability_id == "multi_record"
    assert set(report.items[0].hints[0].evidence) == {"일괄"}
    assert "제외" in report.notice
    assert report.items[2].disposition == "extension_candidate"
    assert report.items[2].text == requirements[2].text


def test_empty_analysis_is_not_reported_as_supported():
    report = assess((), 0)
    assert not report.items and report.business_acceptance == "not_run"


def test_customer_login_is_supported_but_row_scope_and_sso_still_need_contracts():
    from specton.specification.capabilities import CAPABILITIES, VERSION

    assert VERSION == "domain-capabilities-v6"
    report = assess(
        (
            ScopeRequirement(
                id="R1", text="아이디 비밀번호로 로그인하고 세션을 유지한다", kind="FR"
            ),
            ScopeRequirement(
                id="R2", text="SSO로 로그인하고 본인에게 배정된 작업만 변경한다", kind="FR"
            ),
        ),
        1,
    )
    assert not report.items[0].hints
    assert "identity" in {h.capability_id for h in report.items[1].hints}
    assert next(c for c in CAPABILITIES if c.id == "customer_session").status == "supported"
    assert "검색·페이징은 미지원" not in next(c for c in CAPABILITIES if c.id == "record_io").scope
