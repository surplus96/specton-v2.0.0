# API 계약과 버전

[![한국어](../assets/lang-ko.svg)](../ko/api.md) [![English](../assets/lang-en.svg)](../en/api.md)

기계 판독 기준은 [OpenAPI](../api/openapi.json), 구현은 [API 모듈](../../specton/api/)이다. 이 문서는 경로 그룹과 불변 조건을 설명하며 요청/응답 필드를 중복 정의하지 않는다. 로컬 FastAPI `/docs`에서 상세 타입을 볼 수 있다.

| 경로 그룹 | 역할 |
|---|---|
| `/health` | 서버 상태 |
| `/runs`, `/runs/{id}` | 문서 실행 생성·목록·상태 |
| `/runs/{id}/events`, `/view`, `/resume`, `/cancel` | SSE, 현재 화면 데이터, 확인/재개, 취소 |
| `/runs/{id}/artifacts/{kind}` | revision별 설계 산출물 |
| `/api/v1/auth/*` | Google 로그인·현재 사용자·로그아웃 |
| `/api/v1/projects`, `/baselines/*` | 소유 프로젝트, 실행 연결, 승인 기준 |
| `/api/v1/specs/{spec_id}/*` | 명세 버전·보완·파생·승인·설계·준비도 |
| `/api/v1/implementations/{impl_id}/*` | 소스 ZIP·검증 작업·미리보기 |
| `/api/v1/previews/{preview_id}/*` | 소유자 중계 문서·RPC·종료 |
| `/api/v1/projects/{project_id}/candidates`, `/adoptions` | 비교·검증 근거·채택 |
| `/api/v1/integrations/gmail/*` | 별도 Gmail 동의·연결·수집 범위·동기화 |
| `/api/v1/feedback`, `/feedback-jobs`, `/changes/*` | 메일·작업·변경안·검토·재구현 |
| `/api/v1/packs`, `/capabilities` | 사용 가능한 팩과 지원 능력 |

표의 축약된 하위 경로는 실제 prefix를 그대로 이어 쓴다는 의미가 아니다. 정확한 method/path는 OpenAPI를 따른다.

## SDD·변경 처리 주요 엔드포인트

| Method | Path | 동작 |
|---|---|---|
| `POST` | `/api/v1/projects/{project_id}/baselines` | 승인 실행을 설계 기준으로 연결 |
| `POST` | `/api/v1/baselines/{baseline_id}/specs` | 실행 명세 생성 |
| `POST` | `/api/v1/specs/{spec_id}/derive` | 승인 구조의 화면·API·저장 매핑 도출 |
| `POST` | `/api/v1/specs/{spec_id}/complete` | AI 명세 보완 제안 |
| `GET` | `/api/v1/specs/{spec_id}/handoff` | 납품 준비도와 실행 근거 조회 |
| `POST` | `/api/v1/specs/{spec_id}/approve` | 최신 명세 승인 |
| `GET` | `/api/v1/specs/{spec_id}/design` | 재생성 설계 조회 |
| `POST` | `/api/v1/specs/{spec_id}/implementations` | 승인 명세의 소스 생성 |
| `POST` | `/api/v1/implementations/{impl_id}/verifications` | 격리 검증 요청 |
| `POST` | `/api/v1/implementations/{impl_id}/previews` | 검증 소스의 미리보기 요청 |
| `GET` | `/api/v1/projects/{project_id}/candidates/{candidate_id}/comparison` | 기준 대비 후보 비교 |
| `POST` | `/api/v1/projects/{project_id}/adoptions` | 검토 후보 채택 |
| `POST` | `/api/v1/feedback/{message_id}/changes` | 메일에서 변경 요청 등록 |
| `POST` | `/api/v1/changes/{change_id}/analyse` | 변경 영향 분석 |
| `PUT` | `/api/v1/changes/{change_id}/proposal` | 검토한 변경·기대값 저장 |
| `POST` | `/api/v1/changes/{change_id}/decide` | 변경안 승인·거절 |
| `POST` | `/api/v1/changes/{change_id}/implement` | 승인 변경의 생성·검증 요청 |

## 인증·경합·오류

플랫폼 세션 쿠키와 변경 요청의 `X-CSRF-Token`을 사용한다. 프로젝트·명세·메일·후보는 소유권을 검사한다. 과거 익명 실행과 로그인 사용자 프로젝트는 서로 다른 접근 경계이며 임의 실행 ID만으로 소유권을 얻을 수 없다.

수정·승인은 최신 버전·내용 해시를 확인한다. 중복 명령에는 요청 키를 사용한다. 로그인 필요, 권한/접근 실패, 잘못된 입력, 오래된 버전/해시, 검증 대기를 구별한다. 클라이언트는 실패를 빈 성공 응답으로 변환하지 않는다.

SSE는 이벤트 식별자를 사용한 재연결을 고려한다. 확인 질문과 최종 승인은 해당 실행 revision의 재개 계약을 따른다. 취소·재시도 시 이전 결과를 다른 revision의 성공 근거로 사용하지 않는다.

## 계약 변경 작업

1. Pydantic 모델, API 라우트, 저장 마이그레이션의 영향을 확인한다.
2. `docs/api/openapi.json`의 해당 계약을 갱신한다. 수동 SSE·오류·공유 매개변수 정의를 보존한다.
3. `npm --prefix frontend run gen:api`로 타입을 갱신한다.
4. `npm --prefix frontend run check:api`와 Python 계약·스키마 테스트를 실행한다.

기존 승인 명세·팩·산출물의 해시를 호환성 수정으로 덮어쓰지 않는다. 명세 형식 버전, 프로젝트 명세 버전, 설계 revision, 플랫폼 DB revision은 다른 축이다.

---

[문서 목록](README.md) · [프로젝트](../../README.md)
