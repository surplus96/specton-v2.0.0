# 실제 브라우저 인수와 격리 미리보기

2026-11-14. 기존 자동 검증 작업자에 고정 Chromium 화면 인수와 15분 수명의 소유자 전용 미리보기를 연결했다. 자연어 인수 사례 전체의 자동 판정, 운영 배포, 후보 채택, Gmail 변경 요청은 후속 범위다.

## 실행 흐름

1. 최신 승인 명세에서 소스를 생성한다. 새 템플릿 버전은 `browser-preview-v1`이다. 기존 승인 명세 해시는 보존하며 기존 소스 기록은 덮어쓰지 않는다.
2. 브라우저 이미지를 설정한 작업자가 검증 요청을 처리한다. 기존 DB·HTTP 검사 후 생성된 React 앱을 오프라인으로 빌드하고 실제 Chromium으로 조작한다.
3. 화면에서 DB/HTTP 상태와 **고정 화면 인수** 상태를 구분해 보여 준다. 결과에는 브라우저 버전·이미지 ID·검증 코드 해시·빌드 파일 해시·API/화면/요구 ID 연결·스크린샷과 SHA-256이 들어간다.
4. 브라우저 인수까지 통과한 결과에서 **미리보기 준비**를 요청한다. 작업자는 같은 소스와 검증 이미지로 새 격리 DB·앱을 만들고 다시 검증한 뒤 ready로 전환한다.
5. **미리보기 열기**로 샌드박스 프레임을 사용한다. 검증 과정에서 만든 데모 데이터가 있으며 모든 승인 API의 데모 역할을 사용한다. 수정 내용은 운영 데이터에 반영하지 않고 종료 시 폐기한다.
6. **미리보기 종료** 또는 요청 후 15분 만료 시 API 접근을 즉시 차단한다. 작업자가 컨테이너·네트워크를 회수하고 저장한 문서·접속 토큰을 지운다.

과거의 검증된 소스도 해당 결과와 이미지가 현재 작업자 릴리스에 맞으면 미리볼 수 있다. 미리보기 결과를 최신 명세나 채택한 운영 버전으로 자동 승격하지 않는다.

## 브라우저 인수 범위

| 영역 | 실제 검사 |
|---|---|
| 기준정보 | 모든 연결 엔티티의 화면 등록·조회, 새로고침 후 저장값 재조회, 메모리 토큰 초기화 |
| 재고 | 입고 초안·수량 수정·확정·잔량 조회, 출고 확정·잔량 변화, 입고 취소 부족 거절, 취소 역할 거절, 출고/입고 취소·단건 조회 |
| 프레임 | 생성 앱을 opaque-origin 프레임에서 실행, 메시지 중계로 실제 조회, 부모 DOM·localStorage 접근 거절 |
| 증거 | 고정 시나리오 실행 API·화면·연결 요구 ID, Chromium 버전, 번들 파일별 해시, PNG 스크린샷과 해시 |

`browser_acceptance=passed`는 `generated-ui-v1` 고정 시나리오를 통과했다는 의미다. `business_acceptance`와 자연어 `acceptance_cases`는 계속 `not_run`이다. 임의 자연어 요구, 모든 오류 분기, 접근성 표준 전체, 모바일·Firefox·WebKit까지 통과했다고 계산하지 않는다.

브라우저가 선택 입력을 찾지 못한 문제를 검사 과정에서 발견해 명시적 접근성 이름을 추가했다. 샌드박스에서는 경로 변경 History API를 호출하지 않는다. 일반 생성 앱에서는 기존 화면 경로를 유지한다.

## 격리 구조

- 생성 앱·DB·브라우저 검사 컨테이너는 작업별 internal 네트워크에 연결한다. 운영 DB·Google·LLM 자격 증명, 호스트 파일·Docker socket을 전달하지 않는다.
- Chromium은 신뢰한 고정 생성 프런트엔드만 연다. frontend TSX·Vite 설정·의존성 lock·HTML도 검증기의 고정 템플릿과 대조한다. ZIP manifest를 다시 계산해도 다른 실행 코드는 거절한다.
- 브라우저 컨테이너는 비루트, read-only root, 모든 capability 제거, no-new-privileges, 1 CPU/1 GiB/256 PID, 제한된 workspace/tmp/shm을 사용한다. 의존성 설치는 이미지 준비 단계에서만 한다. Chromium 자체의 OS sandbox를 추가 보안 경계로 주장하지 않으며 임의 외부 웹사이트 실행은 지원하지 않는다.
- 미리보기에는 고정 Node API 중계 컨테이너를 추가한다. 이 컨테이너만 별도 ingress 네트워크와 internal 네트워크를 연결하고 **127.0.0.1의 임시 포트**를 연다. 생성 앱과 DB의 네트워크는 그대로 유지한다.
- 중계기는 데모 토큰을 검사하고 고정된 `http://application:8000`으로만 전달한다. 임의 외부 URL·리다이렉트 전달은 지원하지 않는다. 128 MiB/32 PID 제한과 수명 제한을 적용한다. 생성 앱에 외부 네트워크를 붙이지 않는다.
- 플랫폼 API는 매 미리보기 요청에서 Google 세션·소유권·만료·중단 상태를 확인한다. 변경/RPC 요청에는 기존 Origin·CSRF 검사를 적용한다. 승인 API의 메서드·경로만 loopback으로 전달하며 요청 16 KiB·응답 256 KiB·5초 timeout을 둔다. 사용자 URL로 upstream을 선택하지 않는다.

브라우저에는 중계 포트와 실제 데모 토큰을 반환하지 않는다. 프레임은 `sandbox="allow-scripts allow-forms"`이며 `allow-same-origin`, 팝업, 다운로드, 상위 탐색 권한을 주지 않는다. CSP는 직접 네트워크 접속·form 전송·base URL 변경을 차단한다. 폼 이벤트만 허용하고 실제 호출은 부모의 인증된 RPC를 사용한다. 부모는 메시지 발신 window·opaque origin·형식·동시 요청 수를 확인한다.

## API와 데이터

| 경로 | 동작 |
|---|---|
| POST `/api/v1/implementations/{id}/previews` | verification_id·UUID request_key로 준비 요청 |
| GET `/api/v1/implementations/{id}/previews` | 최근 20개 상태·만료·오류 이력 |
| GET `/api/v1/previews/{id}/document` | 소유권·만료·문서 해시 확인 후 프레임용 HTML을 JSON으로 반환 |
| POST `/api/v1/previews/{id}/rpc` | 승인된 메서드·경로·JSON 본문·선택적 command_key를 고정 중계기로 전달 |
| POST `/api/v1/previews/{id}/close` | 즉시 접근 차단 후 작업자 자원 회수 요청 |

플랫폼 자체 origin에서 생성 앱 HTML을 직접 문서로 서비스하지 않는다. 생성 스크립트가 플랫폼 쿠키·DOM을 읽을 수 없도록 별도 프레임 문서로만 렌더링한다.

HEAD `0006_preview`는 검증 작업에 browser_image/browser_suite_hash를 추가하고 `implementation_preview`에 소스·검증 결과·요청자·명령 키·자원 키·임대·Docker 호스트·만료·문서 해시를 저장한다. 같은 명령 키는 기존 요청을 반환하고 같은 소스의 활성 미리보기는 하나, 계정당 활성 미리보기는 두 개로 제한한다. 준비·종료·회수 대기도 한도에 포함하고 사용자 행 잠금으로 동시 요청을 직렬화한다.

소스·검증 결과·문서는 해시를 대조한다. 브라우저 통과 결과와 런타임/DB/브라우저 이미지가 맞지 않으면 미리보기를 준비하지 않는다. 내부 포트·토큰·문서는 준비 과정의 비공개 열이며 상태 목록에 포함하지 않는다. 종료 시 해당 값들을 지운다.

시작 중 작업자 중단은 기존과 같은 120초 임대, 360초 실행 제한과 180초 유예 후 같은 Docker daemon에서 회수한다. ready 작업은 만료·취소 시 회수한다. 호스트가 유실되면 다른 호스트에서 회수 완료로 표시하지 않는다. API 접근은 만료 시 차단되지만 DB·네트워크의 물리 회수에는 작업자가 필요하다. 무인 운영에는 작업자 서비스 재시작·호스트 복구 체계가 필요하다.

## 설정과 실행

API와 작업자가 같은 루프백 및 Docker 호스트를 사용하는 Linux/macOS 환경을 지원한다. 원격 작업자와 API를 다른 머신에 배치하는 미리보기 터널은 구현하지 않았다. 설정이 비어 있으면 미리보기 요청을 503으로 거절한다.

```bash
uv run python -m specton.persistence.migrate upgrade
uv run python -m specton.persistence.migrate check  # 0006_preview

docker build -f docker/implementation/Dockerfile -t specton-generated-runtime:inventory-ledger-v1 .
docker build -f docker/browser/Dockerfile -t specton-browser:generated-ui-v1 .
docker info --format '{{.ID}}'
# 위 daemon ID를 API 환경의 SPECTON_PREVIEW_WORKER_HOST에 설정

docker image inspect specton-generated-runtime:inventory-ledger-v1 --format '{{.Id}}'
docker image inspect postgres:18 --format '{{.Id}}'
docker image inspect specton-browser:generated-ui-v1 --format '{{.Id}}'
uv run python -m specton.implementation.worker \
  --runtime-image sha256:<runtime> --postgres-image sha256:<postgres> \
  --browser-image sha256:<browser>
```

이미지는 태그 대신 확인한 불변 ID를 작업자에 전달한다. Playwright 1.64.1 패키지와 공식 이미지의 동일 버전을 잠금 파일·base digest에 고정했다. 이미지에 브라우저 의존성이 포함되지만 Playwright 패키지는 별도 설치해야 하는 구조와 버전 일치는 [공식 Docker 문서](https://playwright.dev/docs/docker)를 따른다. 이전 템플릿 소스 검증에는 해당 릴리스의 검증기를 사용하고 새 기능은 새 템플릿으로 소스를 생성한다.

## 검증 기록

[실제 브라우저·미리보기 통합 보고서](evidence/browser-preview-report.json)는 실제 설계/명세 승인, 소스 생성, 작업자 Chromium 검증, 미리보기 준비, 소유자 RPC 조회, 만료 거절과 회수 확인을 연결한다. 보고서에 있는 화면 검사는 고정 생성 앱과 샌드박스 프레임의 검사다. 플랫폼의 Google OAuth 화면부터 시작하는 전체 UI 자동 시나리오로 표시하지 않는다.

동일 소스 ZIP과 보고서·스크린샷은 로컬 `var/implementation/browser-preview/`에 보관한다. CI에도 고정 브라우저 이미지 빌드와 실제 미리보기 통합 검사·증거 업로드를 추가했다. 원격 CI 성공 여부는 해당 커밋 실행 결과로 별도 확인한다.

## 최종 회귀 결과

- Python 전체 회귀 2,213 통과·17 skip (194.61초). 이후 추가한 프런트엔드 변조·브라우저 증거 경계 6건도 통과했다.
- DB 전체 389건 실행에서 388 통과·1 실패 (706.10초). 실패는 downgrade 금지 오류 문구가 기존 테스트의 “삭제” 계약과 달랐던 것으로, 금지 동작은 유지하며 문구를 맞췄다. 수정 후 해당 검사와 최종 미리보기 집중 검사 총 8건이 통과했다 (30.32초). 수정 후 전체 DB 회귀를 다시 실행한 것으로 표시하지 않는다.
- 실제 Docker·Chromium·플랫폼 미리보기·만료 회수 통합 검사 통과 (25.01초). 고정 화면 API 검사 20개와 프레임 격리 검사 4개를 기록했다.
- 프런트엔드 273 통과. ESLint·OpenAPI 타입 일치·TypeScript/Vite 빌드 통과.
- Ruff·포맷·mypy 165개 소스·팩 생성 일치·임시 DB 0006_preview upgrade/check 통과.
- 검증 중 사용한 임시 DB와 미리보기 자원은 정리했다. 재사용할 Docker 이미지와 로컬 검증 산출물은 보관한다.

## 다음 단계

검증 후보 비교·채택과 요구별 인수 범위 보완을 진행한다. 이후 Gmail API로 수신한 변경 요청의 영향 분석·승인·재생성·재검증을 채택 기준에 연결한다.
