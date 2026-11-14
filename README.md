# Specton

[![한국어](https://img.shields.io/badge/lang-%ED%95%9C%EA%B5%AD%EC%96%B4-1f6feb)](README.md) [![English](https://img.shields.io/badge/lang-English-lightgrey)](README.en.md)

고객 요구사항 문서를 읽어 **기능 명세서·ERD·DDL·RTM** 초안을 만들고, 누락·모순을 검토하는 LangGraph 기반 에이전트 서비스.

설계 기준 문서는 [docs/](docs/README.md)에 있다. 결정 기록은 [docs/adr/](docs/adr/README.md)에 있다.

## 기술 구성

| 영역 | 사용 |
|---|---|
| 언어·패키지 | Python 3.12, uv |
| LLM·워크플로 | OpenAI API, LangGraph |
| 계약·검증 | Pydantic, pglast |
| API | FastAPI |
| DB | PostgreSQL 18 (Docker) |
| 웹 | React (`frontend/`) |
| 품질 | ruff, mypy, pytest |

입력은 Excel·CSV·HWP·HWPX를 지원합니다. PDF 입력·추출은 이번 인수 범위 밖(후속)이며 PDF 출력은 지원합니다. HWP·HWPX 엔진은 2026-11-08 채택(ADR-0004), 화면은 자체 React·CSS와 React Flow를 사용(ADR-0005)입니다. AWS 구성은 EC2 1대 + Docker Compose로 승인(ADR-0013, 2026-11-09).

## 시작하기

```bash
cp .env.example .env              # 키는 개인 환경에서만 입력
uv sync                           # 의존성 설치 (.venv)
docker compose up -d --wait db    # PostgreSQL 18 (app + sandbox)
uv run python -m specton.persistence.migrate upgrade  # API 시작 전 DB 버전 이전
uv run uvicorn specton.api.main:app --reload
curl localhost:8000/health
```

웹(`frontend/`):

```bash
cd frontend && npm install && npm run dev
```

### 첫 실행

- **API 키:** `.env`의 `SPECTON_OPENAI_API_KEY`에 키를 넣어야 실행이 된다. 키가 없어도 기동과 `/health`는 되지만, 문서를 올리면 요구사항 분석 단계에서 실패한다. 실제 호출이라 비용이 든다(아래 예시는 실행 1회에 수 센트).
- **포트:** DB는 5432, API는 8000, 웹은 5173을 쓴다. 5432를 이미 쓰는 PostgreSQL이 있으면 `docker compose up -d db`가 실패한다.
- **올릴 문서:** 저장소에는 예시 입력이 없다(개발용·평가용 자료는 비공개). 아래처럼 작은 합성 CSV를 만들어 쓴다. 첫 줄은 열 이름이다.

```bash
cat > sample_inventory.csv <<'CSV'
요구사항 ID,요구사항명,상세 내용
SFR-001,창고 관리,사용자는 창고의 코드와 이름을 등록하고 조회할 수 있다.
SFR-002,품목 관리,사용자는 품목의 코드와 이름을 등록하고 조회할 수 있다.
SFR-003,입고 등록,사용자는 창고별로 품목의 입고 수량과 입고 일자를 등록하고 조회할 수 있다.
CSV
```

브라우저에서 `http://localhost:5173`을 열어 이 파일을 올리고 팩은 `inventory`를 고른다. 확인 질문이 나오면 답하고, 최종 검토에서 승인하면 DDL·ERD·기능 명세·RTM을 내려받을 수 있다. 화면 흐름은 [docs/09](docs/09-ui-flow.md)에 있다.

## 품질 검사

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest                     # 단위 테스트 (db·llm 제외)
uv run pytest --require-db -m 'db and not native_pdf'  # 실제 격리 DB 필요
uv run pytest -m llm              # 실제 LLM 호출, 수동 실행 (이번 시범·평가 총 약 $100, ADR-0007)
```

후속 확장 구현의 현재 상태와 재현 명령은 [구현 진행 기록](docs/planning/08-implementation-progress.md)에 있다.
기준 입력은 `tests/fixtures/baseline/`의 공개 가능한 합성 자료다. 결정론 경로를 30회 측정하려면
`uv run python -m specton.evaluation.baseline`을 실행한다. DB 이전·기존 데이터 보존 절차는
[마이그레이션 결정](docs/adr/0017-platform-migrations.md)을 따른다.

Google 로그인·프로젝트·승인 설계 연결은 [설정 및 사용 흐름](docs/planning/09-google-project-implementation.md)을 따른다. 이어서 [실행 명세 보완·승인](docs/planning/10-specification-implementation.md)을 진행할 수 있다.

## 도메인 팩

`domain_packs/`는 공공데이터 공통표준 8차 기반 입력이다. 사람이 쓰는 파일과 생성 파일이 나뉘어 있다([안내](domain_packs/README.md)).

```bash
uv run python -m specton.packs.build          # 입력 수정 후 재생성
uv run python -m specton.packs.build --check  # 생성 파일 최신 여부 (CI)
```

## 폴더 구조

```text
specton/
  contracts/    단계 간 데이터 계약 (상태·LLM 입출력·Finding)
  ingest/       Excel·CSV·HWPX·HWP 추출, 원문 위치 보존
  packs/        도메인 팩 로더
  llm/          공통 LLM client·재요청·프롬프트 버전
  nodes/        에이전트 노드 A01~A09
  codegen/      ID·명명·N:M·FK, Mermaid·DDL·RTM 생성
  review/       규칙 검사·설정형 리뷰어·근거 병합
  validate/     DDL 파싱·격리 DB 실행 검사
  persistence/  플랫폼 저장·checkpointer
  export/       중간 Markdown, 최종 PDF·SQL·Excel/CSV
  api/          FastAPI
  config.py     환경 설정
domain_packs/   common · inventory(재고·자재) · maintenance(설비)
eval/           평가 데이터·정답 (origin: synthetic 표시)
frontend/       React 웹
tests/          unit · integration · e2e
```

## 개발 규칙

[개인 개발 규칙](CONTRIBUTING.md)을 따른다. 변경 근거·검증 결과를 기록하고 고객 문서·비밀값·실행 산출물은 커밋하지 않는다.

## 프로젝트 분석과 확장 계획

[프로젝트 분석](docs/planning/00-project-analysis.md)과 [개발 계획](docs/planning/README.md)에서 현재 구현, 품질 개선, SDD 구현, Gmail 피드백 반영 범위를 확인할 수 있다. 기반·로그인·프로젝트·명세 검토와 [기준정보 소스 생성·격리 검증](docs/planning/11-generated-application-implementation.md)을 구현했다. [승인 재고 정책 기반 입출고·취소·원장](docs/planning/12-inventory-ledger-implementation.md)도 구현했다. [자동 검증 작업자·플랫폼 결과 등록](docs/planning/13-verification-worker-implementation.md)을 연결했다. 브라우저 인수·미리보기·채택·Gmail 피드백은 후속 범위다.

## 라이선스

[MIT](LICENSE). `domain_packs/sources/`의 공공데이터 공통표준 CSV는 행정안전부 공개 데이터(이용허락범위 제한 없음)로, 출처는 `domain_packs/sources/sources.yaml`에 적는다.
