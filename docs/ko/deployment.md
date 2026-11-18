# 배포·보안·고객 앱 납품

[![한국어](../assets/lang-ko.svg)](../ko/deployment.md) [![English](../assets/lang-en.svg)](../en/deployment.md)

## 제공하는 플랫폼 구성

로컬 HTTP override는 Docker Compose 2.24.4 이상을 사용한다. `compose.local.yml`은 운영 포트 목록을 대체해 `80`, `5194`, `5196`을 `127.0.0.1`에만 바인딩하며 운영용 `443` 포트를 노출하지 않는다.

`docker-compose.yml`은 개발용 DB, `compose.deploy.yml`은 DB·API·웹·마이그레이션 도구, `compose.local.yml`은 로컬 HTTP 확인용 override다. 배포 이미지에는 PDF 렌더러가 포함된다. **현재 배포 Compose는 피드백·생성 앱 검증 작업자를 자동 배치하지 않는다.** 전체 SDD/Gmail 경로의 검증된 로컬 실행은 [설치 안내](getting-started.md)를 따른다. 운영에서는 작업자와 Docker 호스트·네트워크·비밀 설정을 별도로 설계해야 한다.

```bash
cp .env.deploy.example .env.deploy
# 실제 비밀값, 공개 origin, 이미지 태그를 로컬 파일에 입력한 뒤 실행
# 로컬 HTTP 확인 시 compose.local.yml을 함께 사용

docker compose -f compose.deploy.yml --env-file .env.deploy build
docker compose -f compose.deploy.yml --env-file .env.deploy up -d --wait db
docker compose -f compose.deploy.yml --env-file .env.deploy run --rm migrate
docker compose -f compose.deploy.yml --env-file .env.deploy up -d --no-build api web
```

실제 서버는 검증한 이미지 digest를 보관하고 같은 이미지를 배포한다. HTTPS origin에는 Secure 세션 쿠키를 적용한다. 로컬 HTTP에서만 해당 설정을 끈다. API·DB는 내부 네트워크에 두고 Caddy가 웹과 API를 같은 출처로 제공한다. `docker compose down -v`는 DB/파일 볼륨을 삭제하므로 일반 재시작 명령으로 사용하지 않는다.

API 이미지의 ERD 렌더러는 `docker/api/mermaid-package.json`과 `mermaid-package-lock.json`으로 고정한다. CLI·Mermaid·Puppeteer를 명시하고 공식 npm 패키지를 잠금 파일대로 설치한다. 갱신 후 `docker build --target check .`로 실제 PDF·ERD 렌더링을 검증하며, Mermaid 버전은 프런트엔드와 일치시킨다. 남은 권고와 적용 경계는 [의존성 보안 관리](dependency-security.md)를 따른다.

## 데이터·비밀·실행 경계

- `.env*` 실제 비밀 파일, 고객 업로드, Gmail 토큰·본문, 세션·로그·DB 덤프는 커밋하지 않는다. 배포에는 예제 환경 파일만 포함한다.
- 플랫폼 DB와 SQL sandbox는 계정과 데이터베이스를 분리한다. 허용 AST 검사·제한 권한·시간 제한·롤백으로 설계 DDL을 검증한다.
- 생성 앱은 별도 작업자가 고정 이미지와 제한된 컨테이너·네트워크·자원으로 시험한다. 생성 앱 컨테이너에 Docker 소켓을 넘기지 않는다.
- 미리보기는 소유자 검사와 만료를 적용한 제한된 프록시다. 운영 데이터로 시험하지 않는다.
- 입력 문서·메일·모델 출력은 비신뢰 데이터다. 실행 코드로 바로 평가하지 않는다.

## 플랫폼 DB 변경

새 Alembic revision을 추가하고 `upgrade`·`check`를 실행한다. 기존 revision을 수정하거나 불일치 DB를 `stamp`로 정상처럼 처리하지 않는다. 백업 사본에서 이전을 검증한 뒤 적용하고 실패 시 이전 이미지와 백업을 복구할 절차를 둔다. 자동 다운그레이드가 항상 데이터를 보존하는 것은 아니다.

## 납품 패키지 구성

| 경로 | 내용 |
|---|---|
| `spec/` | 승인 명세와 기준 설계 스냅샷 |
| `design/` | 원본 승인 기능 명세·ERD·DDL·RTM |
| `design/revised/` | 현재 명세의 실행 설계와 추적 문서 |
| `backend/`, `frontend/` | 실행 계약·서버·고객 화면 |
| `delivery.json`, `build-manifest.json` | 납품 범위·역할·파일 해시·템플릿 버전 |
| `verify_delivery.py`, `backend/manage.py` | 파일 무결성·DB 초기화·계정 관리 |
| `OPERATIONS.md`, `ATOMIC_COMMANDS.md`, `CALCULATIONS.md` | 운영·명령·계산 계약 안내 |

## 생성 고객 앱 설치

소스 ZIP은 플랫폼과 독립적인 기본 앱이다. 원본 승인 설계는 `design/`, 실행 설계는 `design/revised/`에 있다. 파일 출처의 소스 SHA-256을 확인하고 `verify_delivery.py`를 실행한다. 플랫폼 DB와 다른 빈 DB 및 제한된 계정을 준비한다.

```bash
# 생성 ZIP을 푼 폴더에서 실행
python -m venv .venv
.venv/bin/pip install --require-hashes -r backend/requirements.txt
npm --prefix frontend ci --ignore-scripts --no-audit --no-fund
npm --prefix frontend run build
.venv/bin/python backend/manage.py init-db
.venv/bin/python backend/manage.py roles
.venv/bin/python backend/manage.py set-user operator --role ROLE_FROM_APPROVED_SPEC
.venv/bin/uvicorn serve:app --app-dir backend --host 127.0.0.1 --port 8080 --no-access-log
```

먼저 패키지 `.env.example`의 DB·origin 설정을 프로세스 환경에 넣는다. 고객 앱 도구는 해당 파일을 자동 읽지 않는다. `set-user`의 역할은 실제 명세의 역할 ID이며 비밀번호는 대화형으로 입력한다. 기본 계정이나 공개 회원가입은 없다. Google/Gmail 계정과 고객 계정은 별개다.

생성 패키지의 `OPERATIONS.md`·`ATOMIC_COMMANDS.md`·`CALCULATIONS.md`는 해당 템플릿의 납품 문서다. 이전 패키지 검증을 위해 템플릿 원본은 버전과 함께 보존한다. 현재 저장소의 한국어·영문 개발 가이드와 고객 ZIP의 문서 언어/제품 UI 현지화는 별도 범위다.

## 백업·이전·인수

`pg_dump`와 별도 빈 DB에 대한 `pg_restore --single-transaction`으로 같은 앱·구조의 복구를 검증한다. 복구 후 세션을 폐기하고 로그인·권한·행 수·핵심 값을 다시 확인한다. 백업에는 계정 해시도 있으므로 접근을 제한한다.

`specton/implementation/data_transfer.py`는 같은 저장 구조에서만 사용하는 격리 이전 검증 모듈이다. 임의 컬럼·타입 변경, 인증 테이블을 포함한 운영 DB 이전, 서비스 전환을 자동 수행하지 않는다. 채택 버튼은 배포 버튼이 아니다. 실제 납품은 설치·계정·권한·업무 조건·실패·복구·운영 환경을 별도로 인수한다.

---

[문서 목록](README.md) · [프로젝트](../../README.md)
