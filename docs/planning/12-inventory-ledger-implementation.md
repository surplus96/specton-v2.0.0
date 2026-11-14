# 승인 재고 정책과 생성 앱 구현

2026-11-14. 기준정보 생성 다음 단계로, 명시적으로 승인된 재고 정책을 DB·API·화면에 연결했다. 플랫폼의 Google 로그인·프로젝트 소유권·설계 승인·명세 승인 검증을 재사용한다. 자동 작업자, 브라우저 인수, 미리보기, 후보 채택, Gmail 연동은 아직 후속 범위다.

> 후속 [자동 검증 작업자 구현](13-verification-worker-implementation.md)에서 큐·취소·복구·결과 등록을 연결했다. 아래는 재고 생성 단계의 기록이다.

## 승인 계약

기존 네 산출물과 원본 DDL을 보존한다. 원본 창고·품목 저장 연결에 다음 정책을 추가한 `spec-v0.3` 명세를 새 버전으로 저장하고 별도로 승인해야 한다. 다음은 전체 SpecBundle에 합치는 예시이며 ID는 실제 명세에 맞춰야 한다.

```json
{
  "schema_version": "spec-v0.3",
  "inventory": {
    "profile": "stock-ledger-v1",
    "storage": "generated-ledger-v1",
    "warehouse_entity_id": "ENTITY-warehouse",
    "item_entity_id": "ENTITY-item",
    "quantity_scale": 3,
    "negative_stock": false,
    "cancel_received": "require_available_stock",
    "api_ids": {
      "draft": "API-stock-draft",
      "edit": "API-stock-edit",
      "confirm": "API-stock-confirm",
      "cancel": "API-stock-cancel",
      "movement": "API-stock-movement",
      "balance": "API-stock-balance"
    }
  }
}
```

정책 필드는 생략할 수 없다. 창고와 품목은 서로 다른 엔티티이며 승인된 기준정보 저장 연결을 사용한다. 참조 기본키는 64자 이하 URL-safe 문자열이다. 다른 정밀도·음수 재고 허용·취소 정책은 거절한다. 원본 테이블의 `_specton_` 접두어는 생성기 내부 저장소와 충돌하므로 거절한다.

`generated-ledger-v1` 승인은 원본 DDL 실행 후 생성 앱 DB에 `_specton_movements`, `_specton_balances`, `_specton_ledger`를 추가하는 데 대한 명시적 계약이다. 원본 재고 테이블에 임의로 동작을 추정해 연결하지 않는다. 원본 요구 전체를 충족했다고 계산하지 않으며 합성 검증 명세는 별도 재고 요구와 제외 사유를 갖는다.

## 동작과 화면

| 동작 | API | 입력 |
|---|---|---|
| 초안 작성 | POST `/inventory/movements` | id, warehouse_id, item_id, kind, quantity |
| 초안 수정 | PATCH `/inventory/movements/{key}` | quantity |
| 확정 | POST `/inventory/movements/{key}/confirm` | 빈 JSON 객체 |
| 취소 | POST `/inventory/movements/{key}/cancel` | 빈 JSON 객체 |
| 단건 조회 | GET `/inventory/movements/{key}` | 경로 key |
| 잔량 조회 | GET `/inventory/balances` | warehouse_id, item_id 쿼리 |

작성 응답은 201, 나머지는 200이다. 변이 API는 row_lock·atomic·멱등성 계약을, 조회는 read_only 계약을 요구한다. 정확한 필드 순서·타입·필수 여부·오류 코드는 `specton/implementation/inventory_contract.py`에서 검사한다. 역할은 각 승인 API의 actor_roles를 사용한다. 취소 권한을 다른 역할에 분리할 수 있으며 서버에서 검사한다.

생성 React 앱은 명세의 화면/API 연결에 따라 작성·수정·확정·취소·조회 폼을 표시한다. 수량을 JavaScript 숫자로 변환하지 않는다. 생성 앱 인증은 기존 데모 역할 토큰 방식이며 플랫폼 Google 세션을 생성 앱 로그인으로 자동 전달하지 않는다.

한 이동은 창고 하나·품목 하나·수량 하나다. kind는 receive 또는 issue이며 초안에서는 수량만 수정할 수 있다. 다중 행 전표, 창고 간 이동, 예약 재고, 일자·로트·단위 변환, 목록·검색은 구현 범위 밖이다.

## 정밀도와 트랜잭션

수량은 양수 십진 문자열만 받으며 소수 세 자리까지 허용한다. 숫자 JSON·지수·NaN·음수·0·과도한 정밀도는 422다. DB는 numeric(18,3), 응답은 소수 세 자리 문자열을 사용한다. 최대 잔량은 999999999999999.999다.

초안은 잔량을 바꾸지 않는다. 확정은 이동 행과 해당 창고/품목 잔량 행을 잠그고 잔량·원장·상태·멱등 결과를 한 트랜잭션으로 저장한다. 동시 출고도 잔량을 음수로 만들 수 없다. 취소는 확정 상태에서만 가능하며 역방향 원장 항목을 추가한다. 입고 취소 시 가용 잔량이 부족하면 거절하고 출고 취소 시 최대 잔량을 초과하면 거절한다. 확정 후 수정·재확정·취소 후 재취소는 INVALID_STATE다.

멱등성 범위는 호출자 토큰 해시·API ID·Idempotency-Key다. 요청 해시에 대상 이동 ID와 정규화한 입력을 포함한다. 같은 요청은 최초 결과를 반환하고 다른 이동에 같은 명령 키를 재사용하면 IDEMPOTENCY_CONFLICT다. 실패 트랜잭션에는 성공 결과를 남기지 않아 같은 키로 재시도할 수 있다. 원장은 API를 통해 수정·삭제할 수 없으며 이는 DB 관리자 변조 방지 기능을 의미하지 않는다.

## 생성과 검증 흐름

1. 명세 화면에서 저장 구조를 확인하고 v0.3 정책·여섯 API·권한·화면·인수 사례를 작성한다.
2. 새 버전을 저장·승인한 후 기존 소스 생성 버튼을 사용한다. 승인 전 생성, 오래된 버전·해시, 원본 변조는 거절한다.
3. 생성 소스 상태는 `source_ready`, 플랫폼 검증 상태는 `not_run`이다.
4. 별도 신뢰한 CLI에서 내려받은 소스를 격리 Docker DB·HTTP 검증기로 확인한다. API 서버가 자동 실행하지 않는다.

템플릿 버전은 `inventory-ledger-v1`이다. 기존 spec-v0.1/v0.2 canonical hash는 유지한다. 이전 소스 ZIP 검증에는 해당 템플릿과 일치하는 검증기 릴리스를 사용해야 한다. 플랫폼 DB 스키마 HEAD는 `0004_implementation`으로 유지하며 이번 확장에 플랫폼 마이그레이션은 없다.

```bash
docker build -f docker/implementation/Dockerfile -t specton-generated-runtime:inventory-ledger-v1 .
docker image inspect specton-generated-runtime:inventory-ledger-v1 --format '{{.Id}}'
docker image inspect postgres:18 --format '{{.Id}}'
uv run python -m specton.implementation.verify source.zip \
  --expected-source-hash <다운로드한 소스의 신뢰한 SHA256> \
  --runtime-image sha256:<런타임 이미지 ID> \
  --postgres-image sha256:<PostgreSQL 이미지 ID> \
  --report verification.json
```

## 실제 검증 증거

[검증 보고서](evidence/inventory-ledger-v1-verification.json)는 실제 승인 API로 생성한 합성 소스에 대한 로컬 격리 실행 결과다. 소스·명세·검증기 해시와 이미지 ID를 기록하며 자원 정리까지 완료했다. 로컬 소스는 `var/implementation/inventory-ledger-v1/source.zip`에 있다.

- 초안 작성·수량 수정·확정·입출고 취소·실제 조회와 정밀도 검증.
- 취소 권한 거절, 입고 취소 잔량 부족 거절, 최대 잔량 초과 거절.
- 잔량 10에서 출고 7 두 건을 동시 확정하면 한 건만 성공하고 잔량 3 유지.
- 최초 잔량 행을 만드는 동시 입고 두 건의 합계 일치.
- 명령 재전송·다른 이동에 대한 명령 키 재사용 차단.
- 원장 INSERT 오류를 실제 DB 트리거로 주입하면 잔량·상태·원장이 모두 롤백. 오류 제거 후 같은 명령 키 재시도 성공.
- 원장 합계와 모든 잔량 행 일치, 음수 잔량 없음.

보고서의 `smoke_passed`는 고정된 기계 계약 검증 결과다. 자연어 업무 인수와 브라우저 자동 인수는 `not_run`으로 유지한다. 생성 프런트엔드의 npm ci·TypeScript·Vite 빌드도 통과했다.

CI에는 승인 API 테스트가 만든 기준정보/재고 소스의 프런트엔드 빌드와 재고 Docker 검증·보고서 업로드를 추가했다. 원격 CI의 실제 성공 여부는 해당 커밋 실행 결과로 별도 확인해야 한다.

## 플랫폼 회귀 결과

- Python: 2,206 통과, 17 skip, 394 deselected (194.78초).
- PostgreSQL: 373 통과, 2,244 deselected (598.78초).
- 프런트엔드: 273 통과. ESLint·OpenAPI 타입 일치·TypeScript/Vite 빌드 통과.
- Ruff·포맷·mypy 155개 소스·팩 생성 일치 통과.
- 검증기의 품목 필드 타입 처리를 보완한 뒤 생성기/재고 계약 21건과 격리 DB·HTTP 검증을 다시 통과했다.

## 다음 단계

플랫폼 작업 큐·lease·취소·복구와 검증 결과 등록을 연결하고, 실제 브라우저 인수·격리 미리보기·후보 채택을 순서대로 구현한다. 이후 Gmail API로 고객 변경 요청을 수집해 동일한 승인·재생성·회귀 검증 흐름에 연결한다.
