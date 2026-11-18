"""Conservative intake hints. Text matches never certify business implementation."""

from typing import Literal

from specton.contracts.base import Contract

VERSION = "domain-capabilities-v6"


class Capability(Contract):
    id: str
    name: str
    status: Literal["supported", "not_supported"]
    scope: str
    signals: tuple[str, ...] = ()


CAPABILITIES = (
    Capability(
        id="api_acceptance",
        name="명시적 API 인수 테스트",
        status="supported",
        scope=(
            "spec-v0.7/0.8의 입력·기대 응답·후속 조회를 사례별 빈 격리 DB에서 실행. "
            "자연어만 있는 사례는 별도"
        ),
    ),
    Capability(
        id="field_comparison",
        name="필드 간 조건 검사",
        status="supported",
        scope=(
            "같은 엔티티의 필수 필드 비교·AND/OR 조건을 등록·수정·상태 변경 API에 적용. "
            "DB CHECK와 계산식은 별도"
        ),
    ),
    Capability(
        id="record_io",
        name="기본 데이터 등록·조회·수정",
        status="supported",
        scope=(
            "승인 테이블·키·관계 사용. v9 도메인 앱은 부분 문자열 검색·offset 페이징 지원 "
            "(요청당 최대 100행). 대용량 성능·검색 인덱스는 별도"
        ),
    ),
    Capability(
        id="customer_session",
        name="고객 앱 로그인·역할 검사",
        status="supported",
        scope=(
            "v9 납품 앱의 운영자 생성 계정·8시간 서버 세션·CSRF·API 역할 검사. "
            "본인/조직별 행 권한·SSO·MFA·셀프 비밀번호 복구는 별도"
        ),
    ),
    Capability(
        id="delivery_package",
        name="기본 설치·백업 복구 안내",
        status="supported",
        scope=(
            "v9 소스·무결성 검사·Dockerfile·계정 관리·운영 안내 제공. "
            "합성 앱 두 개의 동일 버전 복구 검증과 실제 고객 환경 인수는 별도"
        ),
    ),
    Capability(
        id="literal_guard",
        name="컬럼 값 조건 검사",
        status="supported",
        scope="한 컬럼과 고정 값의 비교",
    ),
    Capability(
        id="state_transition",
        name="단일 레코드 상태 변경",
        status="supported",
        scope="허용 이전 상태·다음 상태·역할을 명시한 전이",
    ),
    Capability(
        id="idempotent_write",
        name="중복 요청 방지",
        status="supported",
        scope="단일 동작의 요청 키·본문 일치 검사와 결과 재사용",
    ),
    Capability(
        id="atomic_command",
        name="고정된 여러 행의 원자 명령",
        status="supported",
        scope=(
            "spec-v0.8 / v10에서 전체 기본키로 지정한 2~8개 대상, 등록·수정·읽기 잠금, "
            "정수/고정소수 덧셈·뺄셈, 전후 조건, 중복 방지·전체 롤백. "
            "별도 명령 역할과 정상·경계·실패 API 사례가 필요. 가변 목록·삭제·외부 효과는 별도"
        ),
    ),
    Capability(
        id="multi_record",
        name="가변 건수·일괄 거래",
        status="not_supported",
        scope=(
            "검색 결과 전체·가변 목록·반복 처리·삭제 거래는 별도 확장. 고정 대상 원자 명령은 지원"
        ),
        signals=(
            "일괄",
            "여러 건",
            "전체 행",
            "목록 전체",
        ),
    ),
    Capability(
        id="bounded_calculation",
        name="명시적 소수 계산·범위 집계",
        status="supported",
        scope=(
            "spec-v0.9/v11의 단위·정밀도·단계별 반올림, 사칙·절댓값, "
            "단일 테이블 count/sum/average/min/max, 날짜 경계·null·빈 결과·0분모 정책. "
            "명령의 잠근 행 계산 또는 읽기 전용 집계이며 조인·그룹·일정은 별도"
        ),
    ),
    Capability(
        id="calculation",
        name="계산·집계·기간 비교",
        status="not_supported",
        scope=(
            "단위 있는 기본 사칙·절댓값·단일 테이블 집계는 v0.9에서 지원. "
            "조인·그룹·달력·기간 중첩·임의 식은 별도"
        ),
        signals=(
            "합계",
            "평균",
            "합산",
            "환산",
            "비율",
            "반올림",
            "겹칠",
            "겹치",
            "개월",
            "말일",
            "누적",
            "계산",
            "총액",
        ),
    ),
    Capability(
        id="scheduler",
        name="정기 실행·알림",
        status="not_supported",
        scope="스케줄 작업·이벤트 알림·재시도",
        signals=("매일", "매월", "정기적", "알림", "통지", "반복 간격", "주기", "자동 생성"),
    ),
    Capability(
        id="integration",
        name="생성 앱의 외부 연동",
        status="not_supported",
        scope="외부 API·파일 업로드·장비·전자결재. Specton의 Gmail 수집과 별도",
        signals=("외부", "연동", "연계", "업로드", "PDF", "계측", "바코드", "프린터"),
    ),
    Capability(
        id="identity",
        name="행별 권한·고급 인증",
        status="not_supported",
        scope="본인/조직/담당별 데이터 접근·SSO·MFA·셀프 비밀번호 복구는 추가 계약이 필요",
        signals=(
            "자기",
            "자신",
            "본인",
            "배정된",
            "담당자만",
            "조직별",
            "테넌트",
            "SSO",
            "MFA",
            "비밀번호 찾기",
            "비밀번호 복구",
        ),
    ),
    Capability(
        id="operations",
        name="운영·성능·보존",
        status="not_supported",
        scope="성능 보장·백업 복구·보존 정책·서비스 가용성",
        signals=("백업", "복구", "보존", "초당", "p95", "응답시간", "가용성", "보관"),
    ),
)


class ScopeRequirement(Contract):
    id: str
    text: str
    kind: str


class ScopeHint(Contract):
    capability_id: str
    capability_name: str
    evidence: tuple[str, ...]
    message: str


class ScopeItem(Contract):
    requirement_id: str
    text: str
    disposition: Literal["needs_review", "extension_candidate"]
    hints: tuple[ScopeHint, ...]
    next_action: str


class ScopeReport(Contract):
    catalog_version: str = VERSION
    assessment_kind: Literal["advisory"] = "advisory"
    revision: int
    items: tuple[ScopeItem, ...]
    needs_review: int
    extension_candidates: int
    business_acceptance: Literal["not_run"] = "not_run"
    notice: str = (
        "문장의 표현을 근거로 한 검토 안내입니다. 부정·제외 조건은 직접 확인하세요. "
        "표시가 없는 요구도 구현 완료가 아니며 실행 계약과 업무 인수 검증이 필요합니다."
    )


def assess(requirements: tuple[ScopeRequirement, ...], revision: int) -> ScopeReport:
    items = []
    for req in requirements:
        hints = tuple(
            ScopeHint(
                capability_id=c.id, capability_name=c.name, evidence=evidence, message=c.scope
            )
            for c in CAPABILITIES
            if c.status == "not_supported"
            if (evidence := tuple(s for s in c.signals if s.casefold() in req.text.casefold()))
        )
        extension = bool(hints)
        items.append(
            ScopeItem(
                requirement_id=req.id,
                text=req.text,
                disposition="extension_candidate" if extension else "needs_review",
                hints=hints,
                next_action="적용·제외 조건과 추가 구현 범위를 검토하세요."
                if extension
                else "역할·동작·수용 기준을 실행 계약에 연결해 확인하세요.",
            )
        )
    count = sum(i.disposition == "extension_candidate" for i in items)
    return ScopeReport(
        revision=revision,
        items=tuple(items),
        needs_review=len(items) - count,
        extension_candidates=count,
    )
