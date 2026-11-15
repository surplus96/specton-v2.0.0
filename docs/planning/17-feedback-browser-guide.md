# Gmail 피드백 브라우저 직접 테스트

2026-11-15. 이 안내는 로컬 개발 환경과 고정 재고 템플릿을 기준으로 한다. 구현 범위와 남은 항목은 [구현 기록](16-gmail-feedback-implementation.md)을 따른다.

## Google 콘솔 준비

Google Auth Platform의 **웹 애플리케이션** 클라이언트에 아래 값을 등록한다.

| 항목 | 값 |
|---|---|
| 승인된 JavaScript 원본 | http://localhost:5173 |
| 로그인 리디렉션 URI | http://localhost:5173/api/v1/auth/google/callback |
| Gmail 리디렉션 URI | http://localhost:5173/api/v1/integrations/gmail/callback |

동일 Cloud 프로젝트에서 Gmail API를 활성화하고 데이터 액세스에 https://www.googleapis.com/auth/gmail.readonly를 추가한다. 외부 앱 Testing 상태에서는 사용할 Gmail 주소를 테스트 사용자로 등록한다. Specton에 로그인한 Google 계정과 같은 계정으로 Gmail을 연결한다. 고객 메일을 보내는 계정은 앱을 연결하지 않는 한 테스트 사용자일 필요가 없다.

Testing 상태의 제한된 권한 refresh token은 만료될 수 있으므로 reauth_required이면 다시 연결한다. 공개 고객 서비스의 OAuth 검증·제한 scope 보안 요건은 실제 공개 전에 별도로 확인한다.

## 로컬 설정과 실행

.env에는 기존 SPECTON_GOOGLE_CLIENT_ID, SPECTON_GOOGLE_CLIENT_SECRET, SPECTON_PUBLIC_ORIGIN=http://localhost:5173 외에 아래 설정을 둔다.

- SPECTON_GMAIL_TOKEN_KEY: 한 번 생성한 Fernet 키. 재시작마다 새로 만들지 않는다.
- SPECTON_FEEDBACK_ANALYSIS_ENABLED=true: 외부 분석 사용. 실제 호출은 화면 동의 후에만 발생한다.
- SPECTON_OPENAI_API_KEY: 실제 모델 호출용 서버 키.
- SPECTON_PREVIEW_WORKER_HOST: API와 검증 작업자가 공유하는 Docker daemon ID.
- SPECTON_GMAIL_POLL_SECONDS=300, SPECTON_FEEDBACK_DAILY_ANALYSIS_LIMIT=10.

비밀값은 .env 또는 서버 비밀 저장소에만 보관한다. 채팅·Git·VITE_ 변수에 넣지 않는다.

```bash
# specton-personal 디렉터리
docker compose -p specton-personal -f docker-compose.yml up -d db
uv run python -m specton.persistence.migrate upgrade
uv run python -m specton.persistence.migrate check

# 해당 이미지가 없다면 먼저 빌드
docker build -f docker/implementation/Dockerfile -t specton-generated-runtime:inventory-ledger-v1 .
docker build -f docker/browser/Dockerfile -t specton-browser:generated-ui-v1 .

uv run python scripts/feedback_dev.py start
uv run python scripts/feedback_dev.py status
# 테스트가 끝나면 애플리케이션 프로세스 종료
uv run python scripts/feedback_dev.py stop
```

개발 도우미는 API 8000, 웹 5173, 피드백 작업자, 검증·미리보기 작업자를 실행한다. 기존 프로세스가 포트를 차지하면 강제 종료하지 않고 멈춘다. 로그는 var/feedback-dev/에 저장한다. DB 컨테이너는 stop 명령에서 지우지 않는다.

이 로컬 DB는 기존 specton-deploy 서비스의 DB와 별도다. 기존 배포 프로젝트가 자동으로 복사되지 않는다.

## 메일 수신 확인

1. http://localhost:5173/projects 에서 Google 로그인한다.
2. **Gmail 연결·고객 변경 요청**을 연다.
3. **Gmail 연결**을 누르고 같은 Google 계정의 읽기 권한에 동의한다.
4. 돌아오면 연결 상태 active와 계정을 확인한다.
5. 검색 조건을 입력하고 **수집 범위 저장**을 누른다. 예: subject:Specton-test newer_than:7d -in:drafts.
6. 다른 계정에서 테스트 Gmail로 제목에 Specton-test를 포함한 합성 요청을 보낸다.
7. **지금 동기화**를 누른다. 작업 상태 succeeded 후 **수신함 새로고침**으로 본문을 확인한다.

처음에는 수동 동기화로 검증한다. 정상 수신 후 주기적 동기화를 켠다. 500건을 초과하면 제목·발신자·기간으로 범위를 좁힌다.

## 변경·재검증·채택 확인

선행 조건: 프로젝트에 실제 승인된 설계·실행 명세와 **채택한 구현 후보**가 있어야 한다. 새 DB라면 기존 설계 생성 → 설계 승인 → 프로젝트 연결 → 실행 명세 보완/승인 → 후보 생성/검증 → 최초 채택을 먼저 진행한다. 성공 보고서를 임의로 삽입해 이 조건을 우회하지 않는다.

화면 이름 변경부터 테스트하면 범위를 명확히 확인할 수 있다.

메일 예:

> 재고 조회 화면의 이름을 “고객 재고 현황”으로 바꿔주세요. 조회 기능과 데이터 구조는 유지해주세요.

1. 수집한 메일을 열고 대상 프로젝트를 선택한다.
2. 본문 문장을 그대로 **요청 원문 인용**에 복사하고 요청을 등록한다.
3. 선택 원문·설명의 외부 전송에 동의하고 **에이전트 영향 분석**을 누른다.
4. 대상 화면 ID·수정 이름·사유를 확인한다. 모델이 대상을 특정하지 못하면 추가 질문에 답변을 저장하고 다시 분석한다.
5. 필요하면 변경 항목을 직접 수정한 뒤 **검토한 변경안 저장**을 누른다.
6. 검토 사유와 업무 인수 확인을 입력하고 **변경안·실행 명세 승인**을 누른다.
7. **승인 변경으로 후보 생성·검증 요청**을 누른다.
8. smoke_passed와 browser_acceptance=passed를 확인한다. 실패 시 검증 상세를 확인하며 채택으로 우회하지 않는다.
9. **검증 상세·격리 미리보기**에서 준비 → 열기를 눌러 새 화면 이름을 확인하고 종료한다.
10. **기존 후보와 비교·채택**에서 변경·검증 비교를 실행한다.
11. 변경 파일·명세·미검증 인수 조건을 확인하고 사유를 입력해 채택한다.
12. 변경 요청으로 돌아가 상태 applied와 처리 이력을 확인한다.

AI 없이도 제한된 변경안을 직접 작성해 나머지 흐름을 시험할 수 있다. 이는 실제 AI 분석 성공과 구분한다. 새로운 DB 테이블·기능·업무 정책 요청은 추가 설계 대상으로 남는 것이 현재 정상 동작이다.

## 오류 확인

| 증상 | 확인 |
|---|---|
| redirect_uri_mismatch | Gmail 전용 callback까지 정확히 등록했는지 |
| Gmail 연결 failed | 로그인과 연결 계정 일치, 테스트 사용자·scope·키 설정 |
| gmail_reauth_required | Gmail 다시 연결 |
| gmail_filter_too_broad | 검색 범위 500건 이하로 축소 |
| 작업이 queued에 머묾 | 피드백/검증 작업자 상태와 로그 |
| 분석 버튼 비활성 | 서버 분석 설정·OpenAI 키·화면 동의 |
| needs_input | 추가 질문 또는 지원 밖 변경 확인 |
| 기준 변경 409 | 새 채택 기준에서 요청 재등록 |
| 검증 실패 | 생성 소스 검증 상세 확인; 기준은 이전 채택 유지 |
| 미리보기 요청 실패 | 동일 Docker 호스트 설정·브라우저 검증 결과 확인 |

연결 해제와 수집 원문 삭제는 별개다. 원문 삭제는 Gmail 원본을 삭제하지 않으며, 이미 승인한 명세·소스는 별도 이력으로 남는다.
