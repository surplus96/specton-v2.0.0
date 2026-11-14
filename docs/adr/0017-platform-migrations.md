# ADR-0017: 명시적 플랫폼 DB 마이그레이션

- 날짜: 2026-11-14
- 상태: 구현
- 관련: Q-03, DEV-003, [개발 기획서](../planning/README.md)

## 문제

API 시작 시 전체 `schema.sql`을 재실행하면 실행 중 스키마 변경이 일어나고, 일부 임의 변경은 감지되지 않는다. SDD·프로젝트·피드백 표가 추가되기 전에 현재 플랫폼 구조를 버전으로 고정해야 한다.

## 결정

Alembic을 이전 도구로 사용한다. 업무 저장 계층의 psycopg 코드는 유지하고 SQLAlchemy는 마이그레이션 연결·구조 검사에 사용한다. 프로그램에서 연결과 트랜잭션을 관리하는 방식은 [Alembic 연결 공유 설명](https://alembic.sqlalchemy.org/en/latest/cookbook.html#sharing-a-connection-across-one-or-more-programmatic-migration-commands)을 따른다.

첫 revision은 `0001_platform`이다. `specton/persistence/schema.sql`은 이 revision의 동결된 초기 SQL이며 앞으로 수정하지 않는다. 새 열·표·인덱스는 새 revision으로 추가한다. LangGraph의 checkpoint 표는 라이브러리 소유로 유지한다.

1. 빈 schema에는 기존 플랫폼 표를 만든다.
2. 버전 없는 기존 DB는 별도 임시 schema의 기준 구조와 비교한다. 표·열 타입·NULL·기본값·identity·PK·FK·UNIQUE·CHECK·인덱스를 검사하고, 추가 trigger·rule·RLS·비표준 관계 형식을 거절한다.
3. 알려진 과거 차이인 run 상태 열, source_block 확인 열/NULL, document의 hwp 형식, artifact의 manifest/json 형식만 허용한다. 더 오래된 부분 스키마와 임의 수정은 자동 복구하지 않는다.
4. 실제 구조 검증·호환 변경·Alembic 버전 등록을 같은 트랜잭션으로 처리한다. 실패하면 버전과 DDL을 함께 롤백한다. 데이터 행·승인 해시·체크포인트는 다시 작성하지 않는다.
5. 같은 DB·schema의 migration을 PostgreSQL advisory lock으로 직렬화한다. 같은 프로세스의 Alembic context도 잠근다.
6. API 시작은 버전 확인만 한다. 미이전·알 수 없는 미래 버전은 실행기를 시작하기 전에 거절한다. 구조 비교는 명시적 `upgrade` 때 수행하며, 시작 검사에 모든 스키마 drift 검사가 포함된다고 주장하지 않는다.

## 실행

```bash
uv run python -m specton.persistence.migrate current
uv run python -m specton.persistence.migrate upgrade
uv run python -m specton.persistence.migrate check
```

대상 DB는 `SPECTON_APP_DATABASE_URL`로만 정한다. 테스트의 별도 schema는 `--schema test_example`로 지정하며 빈 schema는 먼저 준비한다. CLI의 `current/check`는 구조를 바꾸지 않는다. `upgrade`에는 임시 비교 schema를 만들 권한이 필요하다.

Compose 배포에서는 실행 이미지를 준비하고 기존 API를 멈춘 뒤 다음을 실행한다. `migrate`는 별도 tools 프로필의 일회성 서비스이며 API 키·업로드 저장소를 받지 않는다.

```bash
docker compose -f compose.deploy.yml --env-file .env.deploy stop api
docker compose -f compose.deploy.yml --env-file .env.deploy run --rm migrate
docker compose -f compose.deploy.yml --env-file .env.deploy up -d --no-build api web
```

기존 운영 DB에는 백업 사본의 이전·복구 검증을 먼저 수행한다. 구조 불일치를 해결하려고 버전 표를 직접 고치거나 검증 없이 stamp하지 않는다. 이번 구현 검증 대상은 합성 데이터의 격리 PostgreSQL이며 운영 DB에 이전을 실행하지 않았다.

## 복구와 제한

`0001_platform`은 기존 표를 삭제하지 않으므로 이전 애플리케이션도 기존 표를 읽을 수 있다. 기준 revision 아래로의 downgrade는 실행·승인 데이터 삭제를 초래하므로 거절한다. 이후 revision의 downgrade는 변경별 가역성을 검토하고, 데이터 손실 위험이 있으면 백업 복원 절차를 명시한다.

알 수 없는 변경 시에는 전체 이전 트랜잭션이 실패하고 원래 버전·데이터를 보존한다. 새 revision을 추가할 때는 버전별 구조 검증과 `HEAD`도 함께 갱신한다. 현재 비교기는 PostgreSQL 18 기준이며 다른 DB 제품은 지원하지 않는다.

## 검증

빈 DB 초기화, 반복 적용, 기존 데이터·checkpoint 보존, 알려진 이전 열/제약 변경, 알 수 없는 타입·FK·CHECK·RLS·인덱스 변경 거절, 미래 버전 거절, 별도 프로세스의 동시 이전, 파괴적 downgrade 거절을 실제 PostgreSQL에서 검사한다. 기존 승인 산출물 보존 검사는 기존 document pipeline 회귀에 포함한다.
