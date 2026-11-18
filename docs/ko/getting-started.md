# 설치와 로컬 실행

[![한국어](../assets/lang-ko.svg)](../ko/getting-started.md) [![English](../assets/lang-en.svg)](../en/getting-started.md)

## 실행 환경

Python 3.12 또는 3.13, uv, Node.js 22.13.0 이상, npm, Docker의 PostgreSQL 18을 사용한다. 저장소 루트에서 명령을 실행한다. `uv.lock`과 `frontend/package-lock.json`을 그대로 사용한다. 문서 분석에는 사용 가능한 OpenAI 모델과 API 키가 필요하다. 키가 없어도 서버 상태 확인과 외부 호출 없는 테스트는 가능하다.

## 기본 설치

```bash
cp .env.example .env
uv sync --locked
npm --prefix frontend ci
docker compose up -d --wait db
uv run python -m specton.persistence.migrate upgrade
uv run python -m specton.persistence.migrate check
```

`.env`에서 `SPECTON_OPENAI_API_KEY`를 설정한다. 모델 기본값과 한도는 [config.py](../../specton/config.py)에 있으며 계정에서 사용할 수 있는 모델로 재정의할 수 있다. 실제 문서 분석에는 API 사용 비용이 발생한다.

각 터미널에서 API와 웹을 시작한다.

```bash
uv run uvicorn specton.api.main:app --host 127.0.0.1 --port 8000 --reload
```

```bash
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

웹 주소는 `http://localhost:5173`, 상태 확인은 `http://localhost:8000/health`다. Vite가 API를 같은 출처로 프록시한다. Google 설정과 브라우저 주소의 `localhost`를 일치시킨다. DB 기본 포트는 5432이며 다른 PostgreSQL이 사용 중이면 시작 전에 충돌을 해결한다.

## 로그인과 첫 설계

프로젝트·실행 명세·변경 요청 기능에는 Google 로그인이 필요하다. [Google/Gmail 설정](gmail-feedback.md)의 로그인 콜백을 등록하고 `.env`에 OAuth 클라이언트 ID와 비밀값을 설정한다. Gmail 메일 접근 동의는 로그인과 별도로 진행한다.

1. `내 프로젝트`에서 로그인하고 프로젝트를 만든다.
2. `새 작업`에서 [재고 합성 CSV](../../examples/requirements/inventory.csv) 또는 [설비 합성 CSV](../../examples/requirements/maintenance.csv)를 올리고 해당 팩을 선택한다.
3. 추출·분석 확인이 필요하면 답변한다. 지적과 설계를 검토하고 최종 승인한다.
4. 기능 명세·ERD·DDL·RTM을 내려받는다. 프로젝트에 승인 실행을 연결한다.
5. 앱 생성을 이어가려면 [SDD 흐름](sdd.md)에 따라 실행 명세와 인수 기대값을 검토·승인한다.

예시는 고객 문서가 아닌 작은 합성 입력이다. AI 응답에 따라 확인 질문과 설계가 달라질 수 있고, 문서를 올리는 것만으로 앱 생성·업무 인수가 완료되지는 않는다.

## 피드백·검증·미리보기까지 실행

기본 API·웹 구성만으로는 별도 검증 작업자가 시작되지 않는다. [Gmail 설정](gmail-feedback.md)의 토큰 암호화 키를 준비하고 다음 이미지를 빌드한다. 이미지 태그는 로컬 실행 도우미가 참조하는 이름이며 지원 도메인을 재고로 한정하지 않는다.

```bash
docker build -f docker/implementation/Dockerfile -t specton-generated-runtime:inventory-ledger-v1 .
docker build -f docker/browser/Dockerfile -t specton-browser:generated-ui-v1 .
docker pull postgres:18
docker info --format '{{.ID}}'
```

마지막 명령의 Docker daemon ID를 `.env`의 `SPECTON_PREVIEW_WORKER_HOST`에 넣는다. API와 작업자는 같은 호스트의 Docker·루프백을 사용해야 한다. 직접 띄운 API·Vite 프로세스를 정상 종료한 다음 실행한다.

```bash
uv run python scripts/feedback_dev.py start
uv run python scripts/feedback_dev.py status
# 이 도우미가 시작한 프로세스만 종료
uv run python scripts/feedback_dev.py stop
```

도우미는 API·웹·피드백 작업자·검증 작업자를 시작하며 이미 점유된 포트의 다른 프로세스를 강제 종료하지 않는다. 로그와 프로세스 기록은 Git에서 제외한 `var/feedback-dev/`에 둔다. DB와 설정·이미지는 미리 준비해야 한다. 이 도우미는 로컬 개발용이며 운영 배포 관리자가 아니다.

## 입력·렌더링 제한

Excel/CSV 및 요구사항 표가 있는 HWP/HWPX를 지원한다. PDF 업로드·OCR은 지원하지 않는다. PDF **출력**에는 Pango·한글 폰트·WeasyPrint와 ERD용 Mermaid CLI·Chromium이 필요하다. 로컬 PDF 출력은 기본 비활성이며 [컨테이너 구성](deployment.md)에는 렌더링 도구가 포함된다.

## 문제 확인

| 증상 | 확인 |
|---|---|
| `/health`는 성공하지만 분석 실패 | API 키, 모델 접근, 호출 한도와 네트워크 |
| 로그인 콜백 오류 | 공개 origin, 승인된 redirect URI 두 종류, 쿠키 설정 |
| DB 버전 불일치 | `migrate check`, 백업 후 `migrate upgrade` |
| 검증·분석 작업이 대기 | 해당 작업자 실행 상태와 `var/feedback-dev/` 로그 |
| 미리보기 비활성 | 브라우저 검증 통과, Docker daemon ID, 동일 호스트 |
| 메일 0건 | 연결 상태, 저장한 검색식, Gmail에서 실제 일치하는 메일 |

---

[문서 목록](README.md) · [프로젝트](../../README.md)
