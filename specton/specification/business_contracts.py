"""Review worksheets anchored to a saved spec, never executable policy or approval.

Text signals select questions, not answers. Even a mapped CRUD requirement still
needs a human comparison between its business meaning and the executable contract.
"""

from typing import Literal

from specton.contracts.base import Contract
from specton.contracts.specification import Key, SpecBundle
from specton.specification.capabilities import ScopeRequirement, assess


class AcceptanceOutline(Contract):
    category: Literal["normal", "boundary", "failure", "concurrency", "security", "recovery"]
    given: str
    when: str
    expected: str
    execution: Literal["not_executable"] = "not_executable"


class ContractTopic(Contract):
    capability_id: str
    name: str
    detection: Literal["text_hint", "baseline_review"]
    matched_expressions: tuple[str, ...] = ()
    decisions_required: tuple[str, ...]
    acceptance_outline: tuple[AcceptanceOutline, ...]


def scenario(category: str, given: str, when: str, expected: str) -> AcceptanceOutline:
    return AcceptanceOutline.model_validate(
        dict(category=category, given=given, when=when, expected=expected)
    )


# These are implementation contracts to agree before extending the IR/runtime.
# They deliberately do not supply stock timing, tax, calendars, ownership columns, etc.
TOPICS: dict[str, tuple[tuple[str, ...], tuple[AcceptanceOutline, ...]]] = {
    "nonfunctional_review": (
        (
            "성능·권한·화면·보존·기술 제약 중 검증 대상을 분리한다.",
            "원문 수치·단위·측정 환경·구간·도구·판정식을 그대로 연결한다.",
            "API 사례만으로 검증할 수 없는 항목은 부하·브라우저·운영 시험으로 구분한다.",
        ),
        (
            scenario(
                "normal",
                "원문 조건을 재현한 환경",
                "대상 지표를 정해진 방법으로 측정",
                "원문 기준과 측정 근거 대조",
            ),
            scenario(
                "boundary",
                "원문 임계값의 양쪽 조건",
                "경계에서 측정",
                "합의한 포함/제외·오차 기준으로 판정",
            ),
            scenario(
                "failure",
                "기준을 의도적으로 어긴 대조 조건",
                "같은 방법으로 검사",
                "검사가 실제 위반을 발견하며 정상으로 오인하지 않음",
            ),
        ),
    ),
    "multi_record": (
        (
            "명령을 시작하는 역할·시점과 함께 변경할 테이블·행·필드를 명시한다.",
            "사전 조건과 수량 부족·누락·이미 처리된 상태의 거절/부분 처리 정책을 정한다.",
            "잠금 순서·동시 요청 충돌·중복 요청 키의 범위와 보존 기간을 정한다.",
            "취소·반대 명령의 허용 상태와 되돌릴 값·이력, 외부 부작용 보상 범위를 정한다.",
        ),
        (
            scenario(
                "normal",
                "관련 행의 초기 값을 고정",
                "한 명령을 실행",
                "변경할 모든 값과 이력 건수를 사전에 계산해 비교",
            ),
            scenario(
                "boundary",
                "가용 수량과 요청 수량이 같음/한 단위 부족",
                "경계 양쪽에서 명령 실행",
                "승인한 부족 정책에 따른 성공 또는 변경 없는 거절",
            ),
            scenario(
                "failure",
                "둘 이상의 쓰기가 있는 명령",
                "중간 쓰기에 실패 주입",
                "전체 원복 또는 명시적으로 승인한 부분 처리 결과, 잔여 부작용 없음",
            ),
            scenario(
                "concurrency",
                "동일 대상·같은 요청 키 및 서로 다른 키",
                "동시에 두 요청 후 재시도",
                "중복 효과 없음·정한 충돌 결과·최종 값과 이력 일치",
            ),
        ),
    ),
    "calculation": (
        (
            "입력 필드·산식·단위·정밀도·반올림 위치와 방식을 명시한다.",
            "집계 대상 상태·취소/삭제 포함 여부·기간 시작/끝 포함·시간대를 정한다.",
            "0 분모·빈 집합·null·음수·최댓값·늦은 입력·재계산 정책을 정한다.",
            "원본 변경과 결과 조회의 일관성 시점, 계산 결과 저장 여부를 정한다.",
        ),
        (
            scenario(
                "normal",
                "독립적으로 계산한 고정 입력과 정답",
                "계산/집계 실행",
                "단위·소수 자릿수까지 고정 정답과 일치",
            ),
            scenario(
                "boundary",
                "0·null·반올림 경계·기간 시작/끝·월말 데이터",
                "각 경계에서 계산",
                "정의된 값 또는 명시한 오류; 무한대/임의 0 대체 없음",
            ),
            scenario(
                "failure",
                "오류 입력 또는 취소된 원본",
                "계산 후 원본 수정·재계산",
                "정한 제외·오류·재계산 정책과 일치; 오래된 결과 구분",
            ),
        ),
    ),
    "scheduler": (
        (
            "실행 시간대·주기·시작/종료일·휴일·월말·서머타임·지연 실행 정책을 정한다.",
            "대상 선정 조건·수신자·채널·발송 허용 및 취소 조건을 명시한다.",
            "실행/발송 식별 키·작업 선점·재시도 횟수·간격·실패 보관과 재처리를 정한다.",
            "외부 전송과 내부 기록 사이 실패 시 중복·누락 허용 수준을 명시한다.",
        ),
        (
            scenario(
                "normal",
                "고정 시계와 승인된 대상 목록",
                "예정 시각 경과",
                "대상별 작업·발송 결과와 실행 이력 일치",
            ),
            scenario(
                "boundary",
                "시각 경계·월말·대상 없음·취소된 대상",
                "시간을 이동해 반복 실행",
                "명시한 달력·누락 실행 정책과 일치; 대상 외 처리 없음",
            ),
            scenario(
                "recovery",
                "작업 선점/전송 직후 중단",
                "작업자 재시작·재시도",
                "중복 억제·최대 재시도·실패 보관을 실제 기록으로 확인",
            ),
        ),
    ),
    "identity": (
        (
            "로그인 주체와 고객/조직/담당자 식별 필드, 소유권 근거를 명시한다.",
            "조회·검색·수정·집계·내보내기별 접근 조건과 관리자 예외를 정한다.",
            "요청 본문의 소유자 값을 신뢰하지 않고 서버에서 권한을 결정한다.",
            "배정/역할 변경·비활성화의 반영 시점과 SSO/MFA 필요 여부를 정한다.",
        ),
        (
            scenario(
                "normal",
                "서로 다른 소유자/조직의 동일 역할 계정",
                "각자 조회·변경",
                "승인한 본인/조직 데이터만 노출·변경",
            ),
            scenario(
                "security",
                "다른 소유자의 식별자·검색어·요청 본문",
                "직접 API·검색·집계·내보내기 요청",
                "우회 접근과 타인 존재 정보 노출 거절",
            ),
            scenario(
                "boundary",
                "권한 변경 전 열린 세션",
                "배정 변경/비활성화 후 재요청",
                "정한 반영 시점부터 새 권한 적용",
            ),
        ),
    ),
    "integration": (
        (
            "외부 시스템·허용 목적·전송 필드·인증·권한·비밀값 보관자를 명시한다.",
            "요청/응답 형식·타임아웃·호출 제한·재시도·중복 키와 장애 격리를 정한다.",
            "파일 형식/크기/검사 또는 웹훅 서명·재전송 방지·상태 대사 방식을 정한다.",
            "실제 외부 부작용이 없는 시험 환경과 운영 전송 승인 조건을 정한다.",
        ),
        (
            scenario(
                "normal",
                "고정한 외부 시험 응답과 요청",
                "연동 실행",
                "허용 필드·형식·수신 결과·감사 기록 일치",
            ),
            scenario(
                "failure",
                "타임아웃·429·5xx·잘못된 응답",
                "실패 후 재시도",
                "상한 준수·중복 효과 없음·오류 노출에 비밀값 없음",
            ),
            scenario(
                "security",
                "위조/중복 웹훅 또는 허용하지 않은 파일",
                "수신 처리",
                "검증 실패 거절·업무 데이터 미변경",
            ),
        ),
    ),
    "operations": (
        (
            "고객 실행 환경·데이터량·동시 사용자·성능 지표·측정 시간을 정한다.",
            "가용성·RPO/RTO·백업 주기·보존/삭제·복구 책임자를 정한다.",
            "신규 설치/같은 버전 복구/구조 변경 이전/서비스 전환을 구분한다.",
            "업무·계정·세션·요청 키·파일의 이전 범위, 실패 복귀와 구 버전 호환을 정한다.",
        ),
        (
            scenario(
                "normal",
                "고정 버전 소스·이미지·설치 환경",
                "빈 환경에 설치·계정 생성",
                "고객 환경에서 로그인·대표 업무·설치 기록 확인",
            ),
            scenario(
                "boundary",
                "합의한 최대 데이터·부하·보존 경계",
                "부하/보존 시험",
                "합의한 지표·삭제 범위 충족; 별도 수치 없는 성능 통과 금지",
            ),
            scenario(
                "recovery",
                "복구 지점과 파일/계정 포함 백업",
                "별도 빈 환경 복구·세션 폐기",
                "업무 값·건수·해시·재로그인·복구 소요 시간 확인",
            ),
            scenario(
                "failure",
                "구조 변경 이전 계획과 원본 스냅샷",
                "이전 중 실패 주입·복귀",
                "정한 복귀 지점·원본 보존·구조/계정 손실 없음",
            ),
        ),
    ),
    "record_review": (
        (
            "요구의 업무 의미가 연결된 API 동작으로 충족되는지 역할·입력·결과를 대조한다.",
            "필수값·허용값·상태·동시 수정·관계·실패 후 상태를 확정한다.",
            "정상·경계·실패 입력과 독립적인 기대 응답/후속 조회 값을 작성한다.",
        ),
        (
            scenario(
                "normal",
                "빈 DB와 명시적인 선행 데이터",
                "연결 API 실행 후 조회",
                "사전 고정한 응답·저장 값과 일치",
            ),
            scenario(
                "boundary",
                "허용 값의 양 끝·필수값 누락·키/관계 경계",
                "각 입력 실행",
                "정의된 성공/거절과 데이터 보존 확인",
            ),
            scenario(
                "failure",
                "중복 키·권한 없는 역할·없는 부모",
                "실패 요청 후 정상 재시도",
                "부분 저장 없음·정상 재시도 성공·명시적 오류",
            ),
        ),
    ),
}


class BusinessContractWorksheet(Contract):
    requirement_id: Key
    source_id: str | None
    text: str
    kind: str
    priority: str
    scope: Literal["included", "excluded"]
    rationale: str
    coverage: str
    coverage_explanation: str
    role_ids: tuple[str, ...]
    use_case_ids: tuple[str, ...]
    api_ids: tuple[str, ...]
    entity_ids: tuple[str, ...]
    table_ids: tuple[str, ...]
    invariant_ids: tuple[str, ...]
    unresolved_question_ids: tuple[str, ...]
    executable_case_ids: tuple[str, ...]
    missing_api_case_categories: tuple[str, ...]
    topics: tuple[ContractTopic, ...]
    status: Literal["draft_requires_review"] = "draft_requires_review"
    business_acceptance: Literal["not_run"] = "not_run"


def worksheets(bundle: SpecBundle) -> tuple[BusinessContractWorksheet, ...]:
    advisory = assess(
        tuple(ScopeRequirement(id=r.id, text=r.text, kind=r.kind) for r in bundle.requirements),
        bundle.spec_version,
    )
    hints = {r.requirement_id: r.hints for r in advisory.items}
    coverage = {c.requirement_id: c for c in bundle.domain.coverage} if bundle.domain else {}
    rows = []
    for req in bundle.requirements:
        uses = [u for u in bundle.use_cases if req.id in u.req_ids]
        use_ids = {u.id for u in uses}
        apis = [a for a in bundle.apis if a.use_case_id in use_ids]
        api_ids = {a.id for a in apis}
        tables = (
            {o.table_id for o in bundle.domain.operations if o.api_id in api_ids}
            if bundle.domain
            else set()
        )
        entities = {b.entity_id for b in bundle.storage_bindings if b.table_id in tables}
        if bundle.domain:
            tables.update(
                t.table_id for c in bundle.domain.commands if c.api_id in api_ids for t in c.targets
            )
            tables.update(q.table_id for q in bundle.domain.calculations if q.api_id in api_ids)
            tables.update(
                b.table_id
                for q in bundle.domain.calculations
                if q.api_id in api_ids
                for b in q.input_bindings
            )
            entities.update(b.entity_id for b in bundle.storage_bindings if b.table_id in tables)
        entities.update(o.entity_id for o in bundle.operation_bindings if o.api_id in api_ids)
        tables.update(b.table_id for b in bundle.storage_bindings if b.entity_id in entities)
        cases = [c for c in bundle.acceptance_cases if req.id in c.req_ids and c.execution]
        categories = {c.execution.category for c in cases if c.execution}
        item = coverage.get(req.id)
        topics = [
            ContractTopic(
                capability_id=h.capability_id,
                name=h.capability_name,
                detection="text_hint",
                matched_expressions=h.evidence,
                decisions_required=TOPICS[h.capability_id][0],
                acceptance_outline=TOPICS[h.capability_id][1],
            )
            for h in hints[req.id]
        ]
        # Every requirement is reviewed, including unmatched and explicitly excluded ones.
        review_topic = "nonfunctional_review" if req.kind == "NFR" else "record_review"
        topics.insert(
            0,
            ContractTopic(
                capability_id=review_topic,
                name="비기능 요구 검증 계약" if req.kind == "NFR" else "요구 의미·실행 계약 대조",
                detection="baseline_review",
                decisions_required=TOPICS[review_topic][0],
                acceptance_outline=TOPICS[review_topic][1],
            ),
        )
        rows.append(
            BusinessContractWorksheet(
                requirement_id=req.id,
                source_id=req.legacy_id,
                text=req.text,
                kind=req.kind,
                priority=req.priority,
                scope="excluded" if req.priority == "Won't" else "included",
                rationale=req.rationale,
                coverage=item.status if item else "not_declared",
                coverage_explanation=item.explanation
                if item
                else "업무 연결 상태를 별도로 확인하세요.",
                role_ids=tuple(sorted({r for a in apis for r in a.actor_roles})),
                use_case_ids=tuple(sorted(use_ids)),
                api_ids=tuple(sorted(api_ids)),
                entity_ids=tuple(sorted(entities)),
                table_ids=tuple(sorted(tables)),
                invariant_ids=tuple(i.id for i in bundle.invariants if req.id in i.req_ids),
                unresolved_question_ids=tuple(
                    q.id for q in bundle.questions if req.id in q.req_ids and q.answer is None
                ),
                executable_case_ids=tuple(c.id for c in cases),
                missing_api_case_categories=tuple(
                    c for c in ("normal", "boundary", "failure") if c not in categories
                ),
                topics=tuple(topics),
            )
        )
    return tuple(rows)
