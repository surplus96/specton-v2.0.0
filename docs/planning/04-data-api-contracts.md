# 확장 데이터 모델과 API 계약

아래 이름과 엔드포인트는 구현을 위한 제안 계약이다. 현재 제공 중인 `/runs` API와 구분하며 확장 단계에서 OpenAPI·Pydantic·프런트 타입을 함께 구현한다.

> 현재 구현된 명세 API의 정확한 동작은 [실행 명세 구현 기록](10-specification-implementation.md)을 따른다. 아래 전체 확장 표는 후속 목표 계약도 포함한다.

## 버전과 식별 원칙

- 프로젝트가 고객 업무의 지속적인 단위다. 설계 실행, 실행 명세, 구현 실행, 검증 실행은 각각 별도 ID를 갖는다.
- `run.revision`은 기존 실행 내부 차수로 유지한다. 프로젝트에는 순차 `baseline_version`, 명세에는 `spec_version`을 둔다.
- 외부 요구 ID·기존 REQ ID·프로젝트 안정 ID는 별개다. 삭제 객체의 ID는 재사용하지 않는다.
- 최종 산출물, 실행 명세, 소스, 검증 결과는 불변 버전으로 저장한다. 현재 채택 기준 포인터만 비교 후 갱신한다.
- 변경 요청은 분석 시 `base_baseline_id`를 고정한다. 다른 변경이 먼저 채택되면 재분석·충돌 해결 없이 이어서 채택하지 않는다.

## 데이터 모델

| 표 | 주요 필드 | 무결성·보존 규칙 |
|---|---|---|
| app_user | id, identity_subject, state | 인증 제공자 subject 고유, 이메일만으로 계정 병합 금지 |
| project | id, owner_id, name, current_baseline_id, version | 모든 하위 조회에서 owner/project 권한 확인 |
| project_run | project_id, run_id, purpose | 기존 run은 명시적으로 소유 확인 후 연결 |
| design_baseline | id, project_id, version, run_id, revision, model_hash, manifest_hash, approval_id | 같은 프로젝트 버전 고유, 실제 승인 근거 참조 |
| spec_version | id, baseline_id, parent_id, schema_version, payload, spec_hash, status | 승인 이후 payload 수정 금지 |
| object_identity | project_id, stable_id, kind, retired_at | 이름 변경에도 stable_id 유지 |
| object_version_map | spec_id, stable_id, legacy_id, content_hash | 한 버전 내 매핑 고유, 모호한 매칭은 검토 필요 |
| implementation_run | id, project_id, spec_id, base_impl_id, state, row_version, budget | 시작 명세 고정, 낙관적 잠금 |
| workspace_artifact | impl_id, kind, hash, storage_ref, metadata | 소스·빌드·이미지·로그를 구분, 경로 비공개 |
| validation_run | id, impl_id, source_hash, suite_hash, env_digest, fixture_hash, state | 결과와 검증한 코드 묶음 고정 |
| test_result | validation_id, tc_id, status, evidence_ref, elapsed_ms | passed/failed/error/skipped/not_run 구분 |
| trace_link | spec_id, from_kind/id, to_kind/id, relation, provenance | 원문→요구→코드→TC 참조 유효성 |
| gmail_connection | id, owner_id, google_subject, encrypted_token_ref, scopes, state | token 원문은 DB 로그·API 응답 제외 |
| gmail_sync_state | connection_id, committed_history_id, watch_expires_at, last_success_at, lease | 계정별 cursor 직렬화 |
| inbox_notification | provider_id, subscription, connection_id, state | subscription·provider_id 고유 |
| feedback_message | id, connection_id, message_id, thread_id, content_ref/hash, collected_at | connection·message_id 고유 |
| change_request | id, project_id, message_id, base_baseline_id, payload, payload_hash, state, version | 인용 근거와 사용자 결정 보존 |
| change_impact | change_id, analysis_version, base_hash, targets, unknowns, questions | 기준 변경 시 분석 stale |
| approval_event | target_type/id, target_hash, actor_id, decision, created_at | 선언 아닌 인증 주체, 수정·삭제 금지 |
| job/outbox | id, kind, payload_ref, dedupe_key, attempts, next_at, lease | DB 변경과 enqueue를 같은 트랜잭션으로 기록 |
| audit_event | actor, action, project, target_hash, timestamp | 본문·token 제외, 접근·삭제·채택 추적 |

메일 하나에서 여러 변경 요청이 생길 수 있으므로 message_id만으로 change_request를 고유하게 제한하지 않는다. 중복 추출 방지는 `(message_id, extractor_version, candidate_key)`를 사용하고 사용자가 합치거나 분리한 기록을 남긴다.

## 상태 모델

| 대상 | 정상 흐름 | 예외 |
|---|---|---|
| 실행 명세 | draft → needs_input → ready_for_review → approved | rejected, superseded |
| 구현 작업 | queued → planning → generating → building → testing → ready_for_review → accepted | failed, cancelled, expired, superseded |
| 변경 요청 | received → triaged → analysing → awaiting_decision → approved → implementing → validating → awaiting_acceptance → applied | needs_input, rejected, failed, superseded |
| 검증 | queued → running → passed/failed/error | cancelled, not_run |

실패한 구현의 재시도는 새로운 attempt를 만들고 이전 근거를 남긴다. 취소 요청은 프로세스 종료뿐 아니라 작업자 lease, 파일 게시, 미리보기 삭제까지 추적한다. `approved`는 변경 내용의 승인이고 `applied`는 검증 후 새 기준 채택이다.

## 플랫폼 API 제안

모든 일반 API는 인증 세션과 프로젝트 권한을 요구한다. 생성·외부 동기화·build는 202와 작업 ID, 단순 저장은 201/200을 반환한다. 읽기 목록에는 cursor·limit를 제공한다.

| API | 용도 | 주요 입력 또는 결과 |
|---|---|---|
| `POST /api/v1/projects` | 프로젝트 생성 | name |
| `GET /api/v1/projects/{id}` | 채택 버전과 현황 | design/spec/implementation 요약 |
| `POST /api/v1/projects/{id}/baselines` | 승인 run 연결 | run_id, revision, manifest_hash |
| `POST /api/v1/baselines/{id}/specs` | 실행 명세 초안 | 지원 템플릿, 명시 사용자 요구 |
| `PATCH /api/v1/specs/{id}` | 질문 답·명세 편집 | expected_version, patch, 근거 |
| `POST /api/v1/specs/{id}/approve` | 명세 승인 | expected_version, spec_hash |
| `POST /api/v1/projects/{id}/implementations` | 구현 시작 | approved_spec_id, base_impl_id |
| `GET /api/v1/implementations/{id}` | 상태·단계·요약 | 고정 명세·소스·검증 ID |
| `POST /api/v1/implementations/{id}/cancel` | 취소 | expected_version |
| `GET /api/v1/implementations/{id}/events` | 진행 SSE | Last-Event-ID 재생 |
| `GET /api/v1/implementations/{id}/diff` | 파일·명세 차이 | 현재 채택본 대비 |
| `GET /api/v1/implementations/{id}/validations` | 검증 조회 | testcase·근거 링크 |
| `POST /api/v1/implementations/{id}/preview` | 제한 미리보기 | 만료 시간·접근 URL |
| `POST /api/v1/implementations/{id}/accept` | 새 기준 채택 | base_baseline_id, validation_id, source_hash |
| `POST /api/v1/integrations/gmail/connect` | OAuth 시작 | redirect 상태 |
| `GET /api/v1/integrations/gmail/callback` | OAuth 완료 | code, state; 세션 재확인 |
| `POST /api/v1/integrations/gmail/{id}/sync` | 수동 재동기화 | 작업 ID |
| `DELETE /api/v1/integrations/gmail/{id}` | 연결 해제 | 데이터 보존 선택 |
| `POST /webhooks/gmail` | Pub/Sub 알림 | 서비스 JWT, subscription 검증 |
| `GET /api/v1/feedback` | 수신함 | project·분류·처리 상태·cursor |
| `POST /api/v1/feedback/{id}/changes` | 요청 후보 추출 | project_id, base_baseline_id |
| `POST /api/v1/changes/{id}/analyse` | 영향 분석 | expected_version |
| `POST /api/v1/changes/{id}/decide` | 승인·질문·기각 | target_hash, decision, note |
| `POST /api/v1/changes/{id}/implement` | 새 명세·구현 연결 | 승인 요청·기준 버전 |

Google 로그인 단계에서 Caddy/Vite에 `/api/v1`·인증 callback 프록시를 추가했다. Gmail 단계에서는 webhook 경로를 별도로 구성해야 한다. webhook은 일반 브라우저 세션 인증과 분리한다. 원격 미리보기 경로를 관리 API 프록시에 임의 포함하지 않는다.

## 요청 예시

```json
{
  "base_baseline_id": "baseline-inventory-v1",
  "expected_version": 3,
  "target_hash": "sha256-of-reviewed-change",
  "decision": "approve",
  "note": "확정 후 수정 금지와 관리자 취소 조건 확인"
}
```

예시의 ID·해시는 설명용이며 실제 값은 서버가 발급·검증한다. 본문에 적힌 actor·owner 값으로 승인 주체를 정하지 않는다.

## 멱등성과 오류

변경 생성·구현 시작·채택 요청은 `Idempotency-Key`를 사용한다. 키 범위는 사용자·프로젝트·operation이며 정규화 request hash와 최초 결과를 함께 저장한다. 같은 키·다른 본문은 409로 거절한다. 사용 가능 기간 초기안은 24시간이고 실행이 진행 중이면 결과 연결을 유지한다.

| 코드 | HTTP | 의미 |
|---|---|---|
| `BASELINE_STALE` | 409 | 분석 후 현재 기준 변경 |
| `SPEC_INCOMPLETE` | 422 | 필수 질문·권한·수용 기준 누락 |
| `ARTIFACT_MISMATCH` | 422 | 승인·스냅샷·파일 해시 불일치 |
| `VERSION_CONFLICT` | 409 | 오래된 사용자 수정·승인 |
| `IDEMPOTENCY_CONFLICT` | 409 | 같은 키의 다른 요청 |
| `GMAIL_REAUTH_REQUIRED` | 409 | 사용자 재연결 필요 |
| `GENERATION_UNSUPPORTED` | 422 | 지원 밖 규칙·타입·화면 |
| `VALIDATION_NOT_PASSED` | 422 | 필수 검사 미통과·미실행 |
| `RESOURCE_NOT_FOUND` | 404 | 없음 또는 소유권 불일치 |
| `JOB_LIMIT_EXCEEDED` | 429 | 동시 실행·일일 자원 한도 |

SSE는 진행 요약과 대상 ID만 제공하고 긴 로그는 별도 페이지 API로 읽는다. 상태·outbox·감사 기록을 한 트랜잭션으로 저장한다. 작업자 결과 게시 시 holder·attempt·입력 해시를 검사해 취소된 작업이나 lease를 잃은 작업자의 결과를 막는다.

## 기존 데이터 이전

독립 저장소에는 운영 DB·원문을 복사하지 않았다. 후속 구현에서 기존 DB를 연결한다면 먼저 백업·읽기 검사·baseline migration을 수행한다. 과거 run의 소유권은 로그인 사용자가 기존 유효 세션을 증명할 때만 연결하며 전체 run을 일괄 소유 처리하지 않는다.

구 스냅샷은 읽기 호환을 유지한다. 새 spec/baseline은 필요할 때 생성하고 미승인 run·manifest만 있는 파일 묶음은 자동 승인하지 않는다. 과거 해시 형식을 변경하지 않고 별도 schema_version의 신규 해시를 기록한다.
