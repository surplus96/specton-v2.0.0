# 범용 업무 실행 계약

[![한국어](../assets/lang-ko.svg)](../ko/business-contracts.md) [![English](../assets/lang-en.svg)](../en/business-contracts.md)

생성기는 승인 설계의 식별자와 선언형 실행 계약을 컴파일한다. 도메인 이름으로 주문·반품·설비 기능을 고정 선택하지 않는다. 도메인 팩은 용어·타입·설계 해석을 지원하고, 실행 계약은 실제 저장·권한·트랜잭션·계산 동작을 정의한다.

## 계약 계층

| 계층 | 주요 모델 | 역할 |
|---|---|---|
| 승인 명세 | [SpecBundle](../../specton/contracts/specification.py) | 설계 기준, 요구, 역할, API, 화면, 저장 매핑, 인수 사례 |
| 도메인 동작 | [DomainPlan](../../specton/contracts/domain.py) | 레코드 작업, 요구별 구현 연결, 명령·계산 목록 |
| 다중 레코드 명령 | [AtomicCommand](../../specton/contracts/commands.py) | 대상 행, 잠금, 전후 조건, 쓰기, 반환값 |
| 계산·집계 | [계산 모델](../../specton/contracts/calculations.py) | 정확한 수, 단위, 연산, 필터, 집계 정책 |
| 실행 인수 | [인수 모델](../../specton/contracts/acceptance.py) | API 호출 순서와 실제 응답 기대값 |

계산·집계까지 포함하는 형식은 `spec-v0.9` / `domain-ir-v3`이며 소스 템플릿은 `executable-design-v11`이다. 구조 도출은 `spec-v0.6` 초안에서 시작할 수 있다. 이 버전들은 저장소 이름 `v2.0.0`, 프로젝트별 명세 개정 번호와 독립적이다.

## 레코드 작업과 조건

`insert`, `list`, `update`, `transition`을 지원한다. API·필드·테이블·열의 매핑과 기본 키·참조 키를 검증한 후 해당 승인 구조에서 실행한다. 비교 조건은 `eq`, `ne`, `lt`, `le`, `gt`, `ge`를 사용한다. 타입이 있는 필드 조건과 명시적 상태 전이는 업무 규칙으로 검토한다.

조회·수정 화면은 계약에서 구성되며 검색·페이지 이동·관계 선택을 지원한다. 삭제·배치 일정 실행·외부 서비스 호출은 이 레코드 작업 집합에 포함되지 않는다.

## 원자적 다중 레코드 명령

하나의 명령에 읽기·수정·삽입 대상, 입력 연결, 전후 조건, 계산, 쓰기와 반환값을 선언한다. 컴파일러는 대상과 키·컬럼·역할 연결을 검사한다. 런타임은 대상 잠금과 조건 검사를 거쳐 단일 PostgreSQL 트랜잭션으로 처리한다.

중간 단계가 실패하면 전체 쓰기와 요청 기록을 롤백한다. 성공한 요청 키의 재호출은 저장된 결과를 반환한다. 실패한 명령은 입력을 수정해 재시도할 수 있으며, 동시 요청과 멱등성 충돌은 별도 검증 대상이다. 자유 형식 SQL·Python·JavaScript와 외부 부수 효과를 명령에 삽입하지 않는다.

구현: [컴파일러](../../specton/implementation/commands.py), [런타임](../../specton/implementation/templates/runtime/commands.py.txt). 검증: [원자 명령 검사](../../tests/integration/test_atomic_commands.py), [실제 Docker 검사](../../tests/integration/test_atomic_commands_docker.py).

## 정확한 계산과 집계

| 항목 | 지원 |
|---|---|
| 연산 | 덧셈·뺄셈·곱셈·나눗셈·절댓값 |
| 수 표현 | Decimal, 정밀도·소수 자릿수, `half_even`·`half_up`·`down` 반올림 |
| 단위 | 입력·컬럼·상수·결과 단위의 호환성 검증 |
| 집계 | 단일 테이블의 `count`, `sum`, `average`, `min`, `max` |
| 범위 | 선언된 비교 필터, 시작·종료 경계, 최대 조회 행 수 |
| 예외 | null, 빈 결과, 0 나눗셈 처리 정책 |

조회 계약은 최대 10,000행, 집계 16개, 후속 계산 32개로 제한된다. 승인된 집계·계산 결과를 API 응답과 화면에 연결하며 명령의 쓰기 값에도 계산 결과를 사용할 수 있다. 임의 조인·그룹별 분석·통계 언어 실행은 현재 집계 계약에 포함되지 않는다.

구현: [컴파일러](../../specton/implementation/calculations.py), [런타임](../../specton/implementation/templates/runtime/calculations.py.txt). 검증: [계약 검사](../../tests/unit/test_calculation_contract.py), [실행 검사](../../tests/integration/test_calculation_runtime.py).

## 실행 인수와 납품 준비도

인수 사례는 API ID·역할·입력·요청 키·기대 응답을 사용한다. 성공 응답의 상태와 전체 본문, 실패 응답의 상태와 오류 코드를 비교하고 후속 조회로 저장 결과를 검사한다. 자연어 조건만 있는 사례는 자동 통과로 바꾸지 않는다.

준비도는 미해결 질문·누락 API·화면·인수 연결을 검사한다. 납품 준비도는 실행 근거와 업무 계약의 추가 검토 항목을 함께 제시한다. [테스트 준비 검증기](../../scripts/validate_test_preparation.py)는 명세와 승인 설계 스냅샷을 오프라인 비교하는 도구이며 앱 실행이나 승인을 수행하지 않는다.

## Gmail을 통한 계약 수정

기존 명령은 전후 조건·쓰기 값·계산 정책, 기존 집계 조회는 필터·기간 경계·상한·집계·계산 정책의 제한된 수정을 지원한다. 대상·입력·컬럼·계산 ID와 항목 구조를 보존하며 새 잠금 대상·테이블·API를 추가하지 않는다.

변경된 계산이 후속 조회에 영향을 줄 수 있으므로 모든 실행 인수 사례의 검토가 필요하다. AI가 기대값을 수정하지 않으며 소유자가 근거와 함께 허용된 성공 응답 값을 갱신한다. 실패·권한 검사, 응답 상태, 입력·단계, 응답 필드·행 수를 삭제하거나 완화하지 않는다. 변경 후 새 설계·소스를 만들고 실제 재검증을 수행한다.

구현: [변경 계약](../../specton/feedback/contracts.py). 검증: [Gmail 계산 변경](../../tests/integration/test_feedback_calculations.py), [다중 도메인 변경 검사](../../tests/integration/test_feedback_contract_docker.py).

---

[문서 목록](README.md) · [프로젝트](../../README.md)
