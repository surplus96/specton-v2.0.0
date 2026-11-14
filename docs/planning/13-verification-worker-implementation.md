# 플랫폼 자동 검증 작업자와 결과 등록

2026-11-14. 승인된 생성 소스에 대해 서비스 화면에서 검증을 요청하면, 별도 작업자가 큐를 읽어 격리 DB·HTTP 검사를 실행하고 플랫폼 DB에 결과를 저장한다. 검증기는 기존 고정 신뢰 템플릿을 사용한다. 사용자 코드 실행·브라우저 인수·미리보기·후보 채택은 이번 범위에 포함하지 않는다.

## 사용자 흐름

1. 명세 화면에서 최신 명세를 승인하고 **승인한 명세로 소스 생성·조회**를 선택한다.
2. **격리 검증 요청·재실행**을 누른다. 소유권·CSRF·명세 버전/해시·승인 산출물·소스 해시를 다시 검사한다.
3. 별도로 가동한 작업자가 queued 요청을 가져와 running으로 바꾸고 검증한다. 화면은 3초마다 최근 50개 이력을 조회한다.
4. 성공 시 smoke_passed, 실행 실패 시 failed를 표시한다. 결과 JSON·결과 SHA-256·실행 이미지·검증기 해시를 조회할 수 있다.
5. 대기 작업은 즉시 취소된다. 실행 중 취소는 cancelling으로 바뀌고 작업자가 프로세스와 자원을 정리한 뒤 cancelled로 마친다. 작업자가 없으면 요청은 큐에서 기다린다.

검증은 요청 당시 고정한 승인 소스에 대해 진행한다. 실행 중 새로운 명세가 저장돼도 이전 소스의 증거를 덮어쓰거나 새 명세의 통과 결과로 사용하지 않는다. 새로운 검증 요청은 최신 승인 명세의 소스로 제한한다. 브라우저와 자연어 업무 인수는 계속 `not_run`이다.

## API와 저장

| 경로 | 동작 |
|---|---|
| POST `/api/v1/implementations/{id}/verifications` | expected_version, spec_hash, source_hash, UUID request_key로 요청 |
| GET `/api/v1/implementations/{id}/verifications` | 소유한 소스의 최근 검증 이력·증거 |
| POST `/api/v1/implementations/{id}/verifications/{job}/cancel` | 대기/실행 작업 취소, 종료된 작업은 그대로 반환 |
| GET `/api/v1/implementations/{id}` | 최근 작업의 validation_status와 verification_id 포함 |

`implementation_verification`은 요청자·명령 키·소스/명세 해시·상태·시간·임대 토큰·만료·실행 상한·자원 키·Docker 호스트 ID·이미지 ID·검증기 해시·보고서와 보고서 해시를 보존한다. 같은 소스/명령 키는 기존 작업을 반환한다. 다른 키라도 같은 소스의 활성 작업이 있으면 409다. 종료 이후에는 새 키로 재실행할 수 있고 이전 결과를 보존한다.

외부 JSON 결과 업로드 API는 제공하지 않는다. 신뢰한 작업자가 검증 프로세스의 결과와 작업에 고정된 source_hash, spec_hash, runtime_image, postgres_image, suite_hash를 대조하고 자원 정리를 확인한 후 등록한다. `smoke_passed`는 비어 있지 않은 통과 항목 증거를 요구한다. 결과 해시는 정렬된 canonical JSON 바이트로 계산하고 조회 시에도 대조한다. 해시 불일치는 422로 거절한다. 저장소 운영 권한자를 상대로 한 전자서명·변조 방지 기능은 아니다.

## 큐·임대·복구

- PostgreSQL `FOR UPDATE SKIP LOCKED`로 여러 작업자가 같은 요청을 중복 획득하지 않는다. 소스별 활성 작업 부분 유일 인덱스도 둔다.
- 작업마다 새 임대 토큰을 발급한다. 임대는 120초이며 실행 중 약 1초마다 갱신한다. 만료된 임대나 이전 토큰은 완료 결과를 등록할 수 없다.
- 검증 자식 프로세스는 별도 프로세스 그룹에서 실행한다. 부모와 자식 모두 360초 실행 제한을 갖는다. 부모는 취소·임대 상실·시간 초과 시 그룹을 종료한다.
- 부모가 강제 종료돼도 자식 CLI의 실행 제한이 남는다. 회수는 임대 만료와 **작업 실행 상한 + 180초 유예**가 모두 지난 뒤 가능하다. 즉시 재실행해서 기존 실행과 겹치게 하지 않는다.
- 컨테이너와 네트워크에는 작업별 UUID 라벨을 붙인다. 회수 작업자는 그 라벨의 자원만 삭제하며 없는 것을 다시 확인한다. Docker daemon ID가 같은 작업자만 회수한다. 원래 호스트가 없으면 다른 호스트가 정리 완료로 오인하지 않고 작업을 활성 상태로 남긴다.
- 회수 후 원래 작업은 failed/WORKER_LOST 또는 cancelled가 된다. 자동 재시도하지 않는다. 사용자가 새 검증 요청으로 재실행한다.
- 정리 실패 시 성공 처리하거나 활성 슬롯을 해제하지 않는다. 임대가 만료된 뒤 다음 회수자가 다시 정리한다.

작업자 한 프로세스는 한 작업을 처리한다. 병렬 수는 운영자가 같은 Docker 호스트에서 가동하는 프로세스 수로 제한한다. 원격 Docker daemon 장기 정지·호스트 유실의 회복 시간까지 보장하는 분산 스케줄러는 아니다. 서비스 관리자가 작업자를 재시작하고 원래 Docker 호스트를 복구해야 한다.

## 설치와 실행

플랫폼 DB를 백업한 후 서비스 시작 전에 새 마이그레이션을 명시적으로 적용한다. 이번 작업은 테스트 DB에서만 이전했으며 사용자 운영 DB는 변경하지 않았다.

```bash
uv sync --locked
uv run python -m specton.persistence.migrate upgrade
uv run python -m specton.persistence.migrate check
# 기대 HEAD: 0005_verification

docker build -f docker/implementation/Dockerfile -t specton-generated-runtime:inventory-ledger-v1 .
docker image inspect specton-generated-runtime:inventory-ledger-v1 --format '{{.Id}}'
docker image inspect postgres:18 --format '{{.Id}}'

uv run python -m specton.implementation.worker \
  --runtime-image sha256:<위에서 확인한 런타임 ID> \
  --postgres-image sha256:<위에서 확인한 PostgreSQL ID>
```

작업자 프로세스 그룹·alarm 제어는 Linux/macOS 등 POSIX 환경을 대상으로 한다.

`--once`는 최대 한 작업을 처리하고 종료하므로 점검·CI에 사용할 수 있다. 반복 실행은 별도 서비스 관리자로 실행한다. API 서버에는 Docker socket을 주지 않는다. 작업자는 플랫폼 DB 접근과 해당 Docker 호스트의 실행 권한이 필요하다. 플랫폼 환경 변수의 DB·OAuth·LLM 비밀값은 검증 자식 프로세스 환경에 전달하지 않는다. Docker 접속을 위한 PATH/HOME/DOCKER_HOST/DOCKER_CONTEXT/DOCKER_CONFIG만 전달하며 생성 앱 컨테이너에는 기존처럼 작업 전용 DB 자격 증명과 데모 역할 토큰 해시만 전달한다.

검증기 템플릿과 이미지의 probe 버전이 다르면 실패한다. 작업자와 이미지는 같은 릴리스로 준비한다. 임의 ZIP을 요청에 첨부할 수 없으며 저장된 승인 소스만 실행한다.

## 검증 근거

[실제 작업자 등록 보고서](evidence/verification-worker-report.json)는 합성 요구의 실제 설계·명세 승인 → 소스 생성 → 플랫폼 요청 → 큐 획득 → 별도 검증 프로세스 → 격리 PostgreSQL·HTTP 검사 → DB 결과 저장 → 소유자 API 조회를 실행한 결과다. 브라우저 자동 조작으로 얻은 증거는 아니다. 같은 해시의 소스 ZIP과 보고서는 로컬 `var/implementation/verification-worker/source.zip`, `report.json`에 보관한다.

DB 통합 검사에서는 요청 중복·권한/CSRF·두 작업자 획득 경쟁·만료 임대 결과 거절·다른 호스트 회수 거절·복구 유예·취소 우선·해시 불일치·오래된 명세 거절·정리 실패 후 재회수를 확인한다. 일반 DB 회귀는 작업자 프로세스 경계만 대체하며, 별도 실제 Docker 모드와 CI 단계에서 전체 실행 경로를 다시 검사한다.

실제 [Docker 회수 검사](evidence/verification-recovery-report.json)에서 작업별 라벨 정리, 반복 정리, 다른 작업 자원 보존도 확인했다.

## 최종 회귀 결과

- Python 전체 회귀 2,206 통과, 17 skip (195.85초). 이후 추가한 증거 검증 7건과 생성기 14건도 통과했다.
- DB 전체 380건 실행에서 365 통과·15 실패였다 (646.93초). 실패 15건은 과거 DB 재현 시 새 테이블을 제거하지 않거나 테이블 기대 목록에 추가하지 않은 테스트 준비 문제였다. 준비 코드 수정 후 실패 목록 15건을 전부 재실행해 통과했다 (19.45초). 수정 후 전체 380건을 다시 실행한 것으로 표시하지 않는다.
- 추가 마이그레이션 보존·드리프트·동시 요청 검사를 포함한 최종 집중 검사 11건 통과 (38.53초). 실제 Docker 작업자 경로와 결과 해시 변조 거절도 별도로 통과했다.
- 프런트엔드 273 통과. ESLint·OpenAPI 타입 일치·TypeScript/Vite 빌드 통과.
- Ruff·포맷·mypy 159개 소스·팩 생성 일치·임시 DB 0005_verification upgrade/check 통과.
- 원격 CI에는 실제 작업자 통합 검사를 추가했으며, 실행 성공 여부는 해당 커밋의 CI 결과로 별도 확인한다.

## 다음 단계

생성 앱의 실제 브라우저 인수, 요구별 결과 연결, 격리 미리보기와 후보 비교·채택을 구현한다. Gmail API 변경 요청은 채택 기준과 동일한 승인·재검증 흐름에 연결한다.
