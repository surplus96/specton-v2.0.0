# 구현 진행 기록

2026-11-14, 작업 브랜치 `feat/implementation-foundation`. 원본 `specton`에는 변경하지 않고 독립 저장소 `specton-personal`에서 구현한다.

> 후속 상태: [실행 명세 보완·승인](10-specification-implementation.md)까지 이어졌다. Google 지속 로그인·프로젝트 소유권·실제 승인 기준 연결은 [후속 구현 기록](09-google-project-implementation.md)에 정리했다. 이 문서의 상태와 측정값은 기반 구현 시점의 기록이다.

## 이번 구현

| 작업 | 상태 | 현재 코드와 범위 |
|---|---|---|
| DEV-001 기준 입력·검증 자동화 | 결정론 기준선 구현 | 합성 20·200·1,000 블록, 실제 파싱·정리·네 산출물 해시, 반복 측정 CLI |
| DEV-002 DB·프런트 CI | 구현 | PostgreSQL 서비스, 앱·SQL sandbox 분리, 필수 DB 실패 처리, 프런트 Vitest·OpenAPI 검사 |
| DEV-003 플랫폼 migration | 구현 | Alembic 기준 revision, 기존 구조 검증, 호환 이전·실패 롤백, 동시 실행 직렬화, API 시작의 버전 검사 |
| DEV-007 실행 계약 | 계약 스파이크 | `SpecBundle` v0.1, 출처·역할·API·화면·규칙·인수 사례·질문 참조 검사, 내용 해시와 검토 준비 CLI |

P0 전체 완료 또는 P1 전체 완료로 표시하지 않는다. 실제 LLM 성능, API 부하, 브라우저 기준선과 지속 로그인·프로젝트는 남아 있다. DEV-007은 생성기에 바로 넣을 완성 명세가 아니라 후속 구현을 위한 검증 가능한 첫 계약이다.

## 달라진 동작

API는 시작할 때 전체 `schema.sql`을 다시 실행하지 않는다. 먼저 명시적 migration을 실행해야 하며 미이전·알 수 없는 버전은 실행기 시작 전에 차단된다. 기존 승인·산출물·스냅샷·팩 해시의 형식은 바꾸지 않았다. 운영 명령과 복구 기준은 [ADR-0017](../adr/0017-platform-migrations.md)에 있다.

CI의 DB 테스트는 DB가 없거나 필수 검사가 skip이면 실패한다. 별도 PDF 도구가 필요한 테스트는 `native_pdf`로 표시해 기본 DB job에서 제외한다. 테스트를 켜며 발견한 공통 팩 기대값 `0.1.7`은 저장소의 실제 고정 manifest `0.1.8`에 맞췄다. 승인·다운로드·해시 일치 판정은 유지했다.

실행 명세는 네 산출물의 종류·해시, 객체 ID·참조, API/유스케이스 권한·입출력·오류, 규칙의 필드·비교 타입, Must 요구의 API·화면·인수 사례와 미해결 질문을 검사한다. 자유 코드 실행은 허용하지 않는다. `ready_for_review`는 형식·연결 검토 준비 상태이며 실제 승인이나 구현 완료가 아니다.

## 재현 명령

```bash
uv sync --locked
docker compose up -d --wait db
uv run python -m specton.persistence.migrate upgrade
uv run python -m specton.persistence.migrate check
uv run uvicorn specton.api.main:app --reload
```

다른 DB가 포트를 사용 중이면 기존 서비스를 중단하지 말고 별도 테스트 DB와 `SPECTON_APP_DATABASE_URL`·`SPECTON_SANDBOX_DATABASE_URL`을 지정한다.

```bash
uv run python -m specton.evaluation.baseline --repeats 30
uv run python -m specton.specification tests/fixtures/specification/item-create-v0.1.json
uv run pytest
uv run pytest --require-db -m 'db and not native_pdf and not llm'
cd frontend && npm run lint && npm run check:api && npm test && npm run build
```

기준 입력과 한계는 [baseline fixture 설명](../../tests/fixtures/baseline/README.md), 명세 예제는 [계약 예제 설명](../../tests/fixtures/specification/README.md)에 있다. 예제의 UUID·해시는 합성 값이며 실제 승인 증거로 쓰지 않는다.

## 검증 기록

로컬 Python 기본 회귀는 **2,173 passed, 17 skipped, 378 deselected**로 완료했다. 프런트는 **25개 파일·273개 테스트**, 린트·API 타입 검사·production build를 통과했다. Ruff, mypy 131개 소스, 팩 재생성 검사도 통과했다.

실제 PostgreSQL 18의 별도 임시 컨테이너에서 전체 DB 회귀와 migration은 **357 passed, 2,211 deselected**, 약 524초로 완료했다. 최초 실행에서 확인한 오래된 팩 입력·native PDF 분류를 수정한 뒤 전체 재검사에서 실패·skip은 없었다. 빈 schema와 기존 합성 데이터, 승인 산출물 보존, 임의 구조 변경 거절, 별도 프로세스의 동시 migration을 포함한다.

고의로 API 생성 타입을 바꾼 검사는 종료 코드 1로 실패했고 원래 파일을 복구했다. 필수 DB를 없는 포트로 지정한 검사는 종료 코드 4로 실패했다. 미해결 질문을 넣은 명세 CLI는 종료 코드 1로 검토 준비를 차단했다. Compose 설정 검증과 임시 DB의 public schema `upgrade/check`도 통과했다. wheel을 빌드하고 migration SQL·revision·환경·템플릿 파일이 포함됐는지 확인했다.

실제 LLM 호출, 고객 Gmail OAuth·메일 수집, 생성 앱의 DB·API·브라우저 인수, AWS 배포, 운영 DB 이전은 이번 범위에서 수행하지 않았다. 기본 테스트의 skipped·deselected를 통과로 합산하지 않는다.


## 결정론 기준선 실측

입력 크기별 워밍업 1회 뒤 30회를 측정했다. 실제 LLM·DB·PDF·브라우저는 이 측정에 포함하지 않는다. 각 반복에서 정리 모델과 네 산출물의 바이트 해시가 고정 기대값과 같았다.

| 원문 블록 | p50 (ms) | p95 (ms) | 최대 (ms) | 성공 반복 |
|---:|---:|---:|---:|---:|
| 20 | 157.91 | 167.09 | 168.19 | 30 |
| 200 | 224.68 | 251.88 | 252.63 | 30 |
| 1000 | 1144.01 | 1290.93 | 1412.16 | 30 |

프로세스 전체 peak RSS는 92.05 MiB였다. 실행 환경은 Python 3.12.12·macOS-27.0.1-arm64-arm-64bit이며 다른 머신과의 절대 비교나 최적화 개선율로 해석하지 않는다.

[원본 측정 JSON](evidence/baseline-2026-11-14.json)에 입력·잠금 파일·Python 소스 트리 해시를 보관했다. 구현 중 측정이므로 code_commit은 부모 커밋이고 working_tree_dirty가 true다. 측정 전후 소스 트리 불변을 확인했고 실제 코드 기준은 source_tree_hash로 식별한다.

## 다음 구현 순서

1. DEV-004: 지속 사용자와 프로젝트 소유권, 로그인·재로그인·기존 세션의 명시적 소유 이전.
2. DEV-005~006: DB의 실제 승인과 네 산출물을 검증해 baseline을 고정하고 안정 ID·버전 매핑을 저장.
3. DEV-007~008: 상태 전이·화면 바인딩·질문 편집을 보강하고 명세 승인 API/UI를 연결.
4. DEV-009~014: 결정론 재고 앱 생성, 격리 작업자, 실제 DB/API/브라우저 인수와 후보 채택.
5. DEV-016~022: Gmail API 직접 연결·수신함·변경 분석·승인·재구현·전체 회귀.

지속 로그인 전에는 Gmail 토큰을 현재 임시 세션에 연결하지 않는다. 생성·미리보기·자동 수정은 실제 승인 저장과 격리 실행 경계를 갖춘 뒤 연결한다.
