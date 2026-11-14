# 승인 명세 기반 소스 생성과 격리 DB·HTTP 검증

2026-11-14. [실행 명세 검토·승인](10-specification-implementation.md) 다음 단계의 **기준정보 등록·단건 조회 수직 구현**이다. 전체 재고 업무 시스템 완성이나 운영 배포로 표시하지 않는다.

> 후속 [재고 정책 구현](12-inventory-ledger-implementation.md)에서 입출고·취소·원장을 추가했다. 아래는 기준정보 단계 당시의 구현 기록이다.

## 이번에 실행되는 흐름

1. 명세 화면에서 **승인 설계의 테이블·컬럼 확인**으로 원본 정규화 모델의 ID·타입·키를 확인한다.
2. `spec-v0.2`의 저장·동작 연결을 작성한다. 기존 요구·역할·유스케이스·API·화면·인수 사례 계약도 함께 보완한다.
3. 새 명세 버전을 저장하고 승인한다. 기존 `spec-v0.1`의 저장 해시와 승인 기록은 유지된다.
4. **승인한 명세로 소스 생성·조회**를 선택한다. 실제 설계 승인 파일·명세 승인·현재 버전·해시를 다시 검사하고 결정론 소스 ZIP을 만든다.
5. 소스 SHA-256과 ZIP을 내려받는다. 서버 상태는 `source_ready`, `validation_status=not_run`이다. 소스 생성만으로 테스트 통과·채택을 선언하지 않는다.
6. 별도 운영자 CLI에서 신뢰한 소스 해시와 준비된 이미지 ID를 지정해 격리 DB·실제 HTTP smoke 검증을 실행한다. API 서버에 Docker socket이나 실행 권한을 주지 않는다.

## 지원 계약과 거절 조건

| 항목 | 현재 지원 |
|---|---|
| 업무 | 재고 팩의 독립 기준정보 등록·단건 조회. 입출고 확정·취소·원장은 미지원 |
| 저장 | 승인된 원본 DDL을 그대로 사용. 엔티티 legacy ID와 정규화 테이블·컬럼 ID를 대조 |
| 키·관계 | 단일 기본키, 대상 테이블에서 나가는 외래키 없음. 원본 DDL의 다른 표·관계는 보존 |
| 필드 | PostgreSQL varchar/integer/boolean ↔ string/integer/boolean. 타입·NULL 허용·전체 컬럼 연결 일치 |
| 문자열 키 | 명세에 `key_format=url-safe-segment` 명시. 비어 있지 않은 영문·숫자·밑줄·하이픈, 원본 길이 이하 |
| 정수 | PostgreSQL integer 범위, 문자열·불리언으로의 암묵 변환 거절 |
| 등록 | POST, 201, 전체 엔티티 입력·응답, optimistic·atomic·idempotency key. 오류 DUPLICATE_KEY/IDEMPOTENCY_CONFLICT |
| 조회 | GET `/경로/{key}`, 200, PK 입력·전체 엔티티 응답, read_only. 오류 NOT_FOUND |
| API·화면 | 엔티티마다 등록·조회 하나씩, 최대 20 엔티티·40 API. 모든 API가 정적 경로 화면에 연결 |
| 규칙 | 사용자 불변식 AST, decimal/날짜, 복합키, 대상 FK, 목록·수정·삭제 등은 추측 구현하지 않고 거절 |

필드에 DTO 예약 메서드 이름을 쓰는 경우도 거절한다. 자유 설명·자연어 테스트를 Python/SQL로 실행하지 않는다. 명세 승인과 생성기 지원 여부 검사는 별개여서, 검토 가능한 명세라도 생성 범위를 벗어나면 422로 중단한다.

연결 예시는 다음과 같다. `TBL-*`, `COL-*` 등은 **실제 조회한 원본 ID**로 바꾼다. 표·컬럼 물리명을 직접 받아 실행하지 않는다.

```json
{
  "schema_version": "spec-v0.2",
  "storage_bindings": [{
    "entity_id": "ENTITY-item", "table_id": "TBL-actual",
    "columns": {"FIELD-code": "COL-actual-code", "FIELD-name": "COL-actual-name"}
  }],
  "operation_bindings": [
    {"api_id": "API-create", "entity_id": "ENTITY-item", "action": "insert", "key_field_id": "FIELD-code", "key_format": "url-safe-segment"},
    {"api_id": "API-get", "entity_id": "ENTITY-item", "action": "get", "key_field_id": "FIELD-code", "key_format": "url-safe-segment"}
  ]
}
```

이는 전체 SpecBundle에 합칠 일부 필드다. 생성기용 신규 연결은 새 버전으로 승인해야 한다. v0.1의 새 필드 기본값은 기존 canonical bytes에서 제외해 이전 해시를 바꾸지 않는다. v0.2는 별도 해시 prefix와 연결 필드를 사용한다.

## 소스 결과와 재현성

ZIP에는 원본 기능 명세·ERD·DDL·RTM·manifest, 승인 명세, 설계 스냅샷, FastAPI/Pydantic/psycopg 서버, React/TypeScript/Vite 화면, 의존성 lock, 실행 README, 추적 연결, 파일별 해시 manifest를 포함한다. 고정 경로·정렬·ZIP 시간·파일 모드로 같은 입력과 템플릿의 바이트를 동일하게 만든다.

등록은 별도 명령 표와 업무 데이터를 한 DB 트랜잭션으로 저장한다. 사용자 토큰 해시·API·Idempotency-Key 범위로 잠그고 동일 입력 재요청은 최초 결과를 반환한다. 같은 키의 다른 입력과 PK 중복은 409다. DB 값은 매 요청 실제 조회하며 화면에 샘플 데이터를 넣지 않는다.

생성 앱은 플랫폼 로그인과 분리된 **데모 역할 토큰**을 사용한다. 서버에는 토큰 해시→허용 역할만 전달하고 브라우저는 입력한 토큰을 메모리에만 보관한다. 운영 사용자 로그인·토큰 수명 관리 구현으로 간주하지 않는다. 역할은 API에서 검사하며 현재 화면은 서버 거절을 표시한다.

소스 저장은 `0004_implementation`의 `implementation_source`에 승인 명세·버전·해시와 연결한다. 같은 명세/템플릿 재요청은 같은 소스 ID를 반환한다. 저장된 소스를 바꾸거나 같은 템플릿 버전에서 출력이 달라지면 거절한다. ZIP 최대 크기는 10 MiB다.

## 플랫폼 API

| 경로 | 동작 |
|---|---|
| `GET /api/v1/specs/{id}/storage-catalog` | 소유권·원본 승인 검증 후 정규화 저장 구조 조회 |
| `POST /api/v1/specs/{id}/implementations` | expected_version/spec_hash로 최신 승인 명세의 소스 생성·중복 조회 |
| `GET /api/v1/implementations/{id}` | 소유한 소스의 해시·명세 버전·생성 상태 |
| `GET /api/v1/implementations/{id}/source` | 해시를 다시 검사한 ZIP 다운로드 |

변경 요청은 기존 Google 세션·Origin·CSRF 검사를 재사용한다. 이 API들은 검증 작업을 자동 실행하거나 후보를 채택하지 않는다.

## 격리 작업자

준비 단계에서만 검토한 lock의 패키지를 설치한다. 런타임 이미지는 저장소에 고정한 Python base digest와 pip 해시 lock을 사용한다.

```bash
docker build -f docker/implementation/Dockerfile -t specton-generated-runtime:master-data-v1 .
docker image inspect specton-generated-runtime:master-data-v1 --format '{{.Id}}'
docker image inspect postgres:18 --format '{{.Id}}'
uv run python -m specton.implementation.verify source.zip \
  --expected-source-hash <서비스에서 확인한 SHA256> \
  --runtime-image sha256:<준비한 런타임 이미지 ID> \
  --postgres-image sha256:<준비한 PostgreSQL 18 이미지 ID> \
  --report verification.json
```

작업자는 변동 태그를 받지 않는다. ZIP 해시·정확한 경로 목록·중복/링크/크기·파일 manifest·고정 서버 템플릿과 검증 이미지의 probe 해시를 확인한다. 임의 Python 코드가 포함된 ZIP은 실행하지 않는다.

실행에는 다음 제한을 적용한다.

- 작업별 `--internal` 네트워크, 호스트 공개 포트·호스트 디렉터리·Docker socket 마운트 없음.
- 비루트 사용자, 읽기 전용 루트, 제한된 tmpfs, capabilities 전체 제거, no-new-privileges, 기본 seccomp.
- DB 1 CPU/512 MiB/128 PID, 앱 1 CPU/256 MiB/64 PID. 앱은 별도 비슈퍼유저 DB 계정 사용.
- 플랫폼 DB 주소·OAuth·LLM 키는 전달하지 않는다. 작업별 생성 비밀값은 보고서·소스·명령 오류 응답에 포함하지 않는다.
- Docker 명령별 timeout, DB/HTTP 준비 대기 상한, 앱 컨테이너 수명 상한. 성공·일반 실패·예외의 finally에서 생성한 컨테이너 ID와 네트워크 ID만 정리한다.

개발용 Docker 경계이며 별도 운영 VM/호스트의 작업 큐·lease·취소·강제 종료 후 회수 작업은 아직 없다. SIGKILL/호스트 장애에서는 finally를 보장하지 못하므로 장기 운영 작업자로 배포하지 않는다. 미리보기 호스팅·사용자 채택·검증 보고서의 플랫폼 등록도 후속 범위다. 외부에서 제출한 JSON 보고서를 통과 근거로 받아들이는 API는 만들지 않았다.

## 실제 검증 결과와 범위

실제 설계 승인·명세 승인 API를 통과한 합성 기준정보 소스를 생성했다. 원래 합성 요구의 입출고 업무는 명세에서 명시적으로 제외하고 별도 기준정보 요구를 추가했으며, 전체 재고 요구가 충족됐다고 계산하지 않는다.

[격리 검증 보고서](evidence/master-data-v1-verification.json)는 다음의 실제 HTTP·DB 결과를 소스 해시·명세 해시·검증기 해시·이미지 ID에 묶는다.

- 비인증 401, 권한 없는 토큰 403, 모르는 입력·조회 불가능한 문자열 키 422.
- 동일 등록 명령의 동시 재요청 4건 모두 같은 결과, DB 행 1개.
- PK 중복과 같은 명령 키의 다른 입력은 각각 지정한 409 오류 코드.
- 등록 후 실제 HTTP 재조회 결과와 DB 직접 SELECT 결과 일치, 없는 키 404.
- DB 사용자 비슈퍼유저, Docker socket 미노출, 외부 egress 차단, 자원 정리 완료.

생성된 React 앱도 자체 package-lock으로 `npm ci`, TypeScript 검사와 Vite 빌드를 통과했다. 이는 브라우저 자동 조작 통과와 다르다. 자연어 인수 사례와 브라우저 인수는 `not_run`으로 보존한다.

현재 작업 공간의 합성 소스와 결과는 `var/implementation/master-data-v1/source.zip`, `verification.json`에 있으며 고객 자료가 아닌 테스트 결과다. 저장소의 `tests/fixtures/implementation/`은 단위 검사용 별도 고정 합성 입력이다.

플랫폼 검증 결과:

- Python 전체 회귀 **2,198 통과**, 17 skip, 393 deselected (195.02초). 최종 경로 경계·생성기·명세·API 계약 집중 검사 **51건**도 통과했다.
- PostgreSQL 전체 회귀 **372 통과**, 2,236 deselected (592.36초). 최종 템플릿의 실제 승인→생성·권한·변조 검사도 별도 재실행해 통과했다.
- 플랫폼 프런트엔드 **273 통과**, ESLint·OpenAPI 타입 일치·TypeScript/Vite 빌드 통과.
- 생성 앱 자체의 잠금 파일 설치·TypeScript/Vite 빌드와 PostgreSQL 18·실제 HTTP smoke 검증 통과.
- Ruff·포맷, mypy 154개 소스, 팩 생성 일치, `0004_implementation` upgrade/check 통과.
- CI DB job에 실제 승인 API 테스트가 출력한 생성 프런트엔드의 npm ci/build를 추가했다. 격리 Docker smoke는 이번 로컬 실행 증거이며 CI에서 자동 실행한 것으로 표시하지 않는다.

원본 프로젝트·운영 DB·Google OAuth 설정·Gmail 연결은 변경하지 않았다.

## 다음 구현

1. 재고 명령·상태 전이·수량 정밀도·원장·취소 정책의 기계 계약과 생성기.
2. 작업 큐/lease·취소·복구·작업별 결과 등록과 소스/검증 해시 연결.
3. 실제 브라우저 인수·요구별 고정 테스트·격리 미리보기.
4. 검증 후보의 비교·채택. 그 후 Gmail 변경 요청을 연결한다.
