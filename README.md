# Specton v2.0.0
[![한국어](https://img.shields.io/badge/lang-%ED%95%9C%EA%B5%AD%EC%96%B4-1f6feb)](README.md) [![English](https://img.shields.io/badge/lang-English-lightgrey)](README.en.md)

고객 요구사항 문서를 읽어 **기능 명세서·ERD·DDL·RTM** 초안을 만들고, 누락·모순을 검토하는 LangGraph 기반 에이전트 서비스.

설계 기준 문서는 [docs/](docs/README.md)에 있다. 결정 기록은 [docs/adr/](docs/adr/README.md)에 있다.

## 시연 영상

요구사항 분석부터 고객 앱 생성과 Gmail 변경 반영까지 네 편으로 확인할 수 있습니다. 총 재생 시간은 약 **8분 10초**입니다.

| 영상 | 내용 | 재생 시간 |
|---|---|---|
| [part_01](docs/ko/demo.md#part_01) | 초기 설계도 생성 | 02:17 |
| [part_02](docs/ko/demo.md#part_02) | AI Workspace | 00:33 |
| [part_03](docs/ko/demo.md#part_03) | 승인 설계 검증과 고객 앱 생성 | 02:47 |
| [part_04](docs/ko/demo.md#part_04) | Gmail 고객 변경 요청 반영 | 02:33 |

[한국어 시연 가이드](docs/ko/demo.md) · [English demo guide](docs/en/demo.md)

<details>
<summary>영상 펼쳐 보기 — part_01 → part_04</summary>

### part_01

**초기 설계도 생성 · 02:17**

요구사항 문서를 등록하고 분석·검토·승인을 거쳐 기능 명세서·ERD·DDL·RTM을 생성하는 흐름입니다.

https://github.com/user-attachments/assets/a1f762ea-d0cb-4ba6-859c-3d469e324044

### part_02

**AI Workspace · 00:33**

분석·설계 단계별 결과, 테이블 관계와 요구사항의 연결을 AI Workspace에서 확인합니다.

https://github.com/user-attachments/assets/07aaf18c-73c0-4353-98bc-02764b9bd99e

### part_03

**승인 설계 검증과 고객 앱 생성 · 02:47**

승인 설계를 기준으로 실행 명세를 검토하고 소스를 생성·검증한 뒤, 실제 고객이 사용할 앱의 화면과 동작을 확인합니다.

https://github.com/user-attachments/assets/82a5424c-db7e-4776-9238-20fead78588f

### part_04

**Gmail 고객 변경 요청 반영 · 02:33**

Gmail로 받은 수정 요청을 수집하고 영향 분석·검토·승인을 거쳐 변경을 반영한 뒤 결과를 확인합니다.

https://github.com/user-attachments/assets/a2f50cdf-c712-4be7-87f6-919c8fbe890a

</details>

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
docker compose up -d db           # PostgreSQL 18 (app + sandbox)
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
uv run pytest -m db               # 격리 DB 필요
uv run pytest -m llm              # 실제 LLM 호출, 수동 실행 (이번 시범·평가 총 약 $100, ADR-0007)
```

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

## 라이선스

[MIT](LICENSE). `domain_packs/sources/`의 공공데이터 공통표준 CSV는 행정안전부 공개 데이터(이용허락범위 제한 없음)로, 출처는 `domain_packs/sources/sources.yaml`에 적는다.
