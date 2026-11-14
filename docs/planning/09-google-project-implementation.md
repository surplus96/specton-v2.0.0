# Google 로그인·프로젝트·승인 기준 연결

2026-11-14 구현 기록. [ADR-0018](../adr/0018-google-project-baseline.md)에 결정과 검증 경계를 기록했다.

## 사용 흐름

1. 왼쪽 메뉴의 **내 프로젝트**에서 Google 계정으로 로그인한다.
2. 프로젝트를 만들거나 기존 프로젝트를 선택한다.
3. 기존 실행 화면의 **이 실행을 프로젝트에 연결**을 선택한다. 로그인 이동 후에도 선택한 실행 ID와 버전이 유지된다.
4. 프로젝트에서 **실행 소유권 확인 후 연결**을 선택한다. 이 계정 또는 해당 브라우저가 소유한 실행만 연결된다.
5. 완료·승인된 실행에서 **승인 설계를 기준 버전으로 연결**을 선택한다. 파일·승인·검증이 일치할 때만 기준 ID를 발급한다.
6. 로그아웃 후 같은 Google 계정으로 로그인하면 프로젝트와 이전에 가져온 실행을 다시 조회할 수 있다.

코드 생성·실행 명세 편집 화면·Gmail 수집은 이번 단계에 포함하지 않는다. 이 기능은 다음 명세 생성/승인 단계의 신뢰할 수 있는 입력을 만든다.

## 환경 설정

Google Cloud에서 **웹 애플리케이션 OAuth 클라이언트**를 준비하고 다음 redirect URI를 등록한다.

```text
http://localhost:5173/api/v1/auth/google/callback
```

설정은 `.env`에 보관한다. 클라이언트 비밀값은 저장소나 채팅에 올리지 않는다.

```dotenv
SPECTON_GOOGLE_CLIENT_ID=<웹 OAuth 클라이언트 ID>
SPECTON_GOOGLE_CLIENT_SECRET=<클라이언트 비밀값>
SPECTON_PUBLIC_ORIGIN=http://localhost:5173
```

운영에서는 public origin과 등록 redirect URI를 실제 HTTPS 도메인으로 맞추고 `SPECTON_SESSION_COOKIE_SECURE=true`를 설정한다. Vite와 Caddy에 `/api/v1` 프록시를 추가했다. Gmail API 권한은 별도 단계에서 동의받는다.

```bash
uv sync --locked
uv run python -m specton.persistence.migrate upgrade
uv run python -m specton.persistence.migrate check
uv run uvicorn specton.api.main:app --reload
```

새 DB 버전은 `0002_identity`다. 기존 운영 DB에는 백업 사본에서 이전을 검증한 뒤 적용한다. 이번 작업은 별도 임시 PostgreSQL에서 검증한다.

## API

| 경로 | 동작 |
|---|---|
| `GET /api/v1/auth/google` | Google 로그인 시작 |
| `GET /api/v1/auth/google/callback` | 요청·ID 토큰 검증, 플랫폼 세션 발급 |
| `GET /api/v1/auth/me` | 현재 사용자 |
| `POST /api/v1/auth/logout` | 현재 세션 폐기 |
| `GET/POST /api/v1/projects` | 소유 프로젝트 조회/생성 |
| `GET /api/v1/projects/{id}` | 프로젝트와 기준 버전 조회 |
| `POST /api/v1/projects/{id}/runs/{run_id}/claim` | 명시적 실행 소유권 확인·연결 |
| `POST /api/v1/projects/{id}/baselines` | 실제 승인 설계 기준 연결 |

변경 요청은 로그인 쿠키, 정확한 `Origin`, `specton_csrf` 쿠키 값의 `X-CSRF-Token` 헤더를 요구한다. 기존 프런트 API 클라이언트도 로그인 후 변경 요청에 이를 전달한다.

## 검증 경계

Google 코드 교환은 테스트에서 고정 응답을 주입한다. ID 토큰 검증은 독립 RSA 키의 정상·위조 서명, 잘못된 issuer/audience/nonce/azp, 만료·미검증 이메일을 검사한다. DB 검사는 실제 PostgreSQL에서 세션 수명·재로그인·재사용 거절·소유자 분리·명시적 이전·승인 파이프라인·변조 거절을 검사한다.

실제 Google OAuth는 사용자의 클라이언트 설정이 필요하며 아직 실증하지 않았다. 브라우저 수동 인수·Gmail 실연동·운영 배포도 미실행이다. 현재 환경에는 Google 클라이언트 ID·비밀값이 설정되지 않았다.

## 로컬 검증 결과

- Python 기본 회귀: 2,182 통과, 17 skip (DB·LLM 384 deselected). 이후 추가한 접근 로그 검사 2건과 Google ID 토큰 검사 9건은 별도 실행해 11건 모두 통과했다.
- 프런트엔드: 25개 파일 273건 통과, ESLint·OpenAPI 타입 일치·TypeScript/Vite 빌드 통과.
- Ruff 검사·포맷, mypy 139개 소스, 팩 생성 일치, 결정론 기준선 통과.
- 배포 Compose 구성 문법, 임시 DB의 migration upgrade/check (`0002_identity`) 통과.
- 전체 PostgreSQL 회귀: 363 통과, 2,222 deselected (524.30초). 세션·프로젝트·실제 승인 연결 검사 6건을 포함한다.

처음의 임시 PostgreSQL은 768 MiB tmpfs가 WAL로 가득 차 회귀 검사가 중단됐다. 해당 임시 컨테이너만 교체하고 2 GiB tmpfs 및 제한된 WAL 설정으로 재검증했다. 사용자 DB와 원본 프로젝트에는 변경하지 않았다.
