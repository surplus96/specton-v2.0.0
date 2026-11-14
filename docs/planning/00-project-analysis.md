# 현재 프로젝트 구조와 확장 가능성 분석

## 분석 기준

기준 소스는 커밋 `07efbf193eeea1b62e7c70a25b14758b00b00ef3`의 추적 파일 523개다. 원본은 변경하지 않고 현재 파일을 독립 저장소로 복사했다. 원격 이슈·비공개 평가 원문·실제 AWS 환경은 이 분석의 실행 근거에 포함하지 않는다.

전체 추적 파일을 분류하고 Python 모듈의 계약·진입점·의존 관계, 핵심 실행·저장·검증 코드, 프런트 경로, 개발문서·CI·테스트 구성을 대조했다. 모든 파일의 위치는 [파일 지도](06-module-map.md)에 있다. 기존 문서에 적힌 과거 측정과 이번 세션의 검증은 [별도 기록](07-repository-verification.md)으로 구분한다.

## 현재 시스템의 역할

현재 `codegen`은 업무 애플리케이션 소스 생성기가 아니다. 요구사항에서 만든 설계 모델을 정리하고 SQL·Mermaid·Markdown·RTM을 생성한다. `validate/sandbox.py`는 생성 DDL을 제한된 DB에서 실행·롤백·정리 검사하며, 업무 트랜잭션이나 화면 동작을 검증하지 않는다.

이 구분이 확장의 출발점이다. 기존 산출물·원문 추적·승인·파일 해시를 재사용하되 업무 실행 계약, 애플리케이션 생성, 실행 격리와 인수 증거를 추가해야 한다.

## 기술과 배포

| 영역 | 코드에서 확인한 구성 | 의미 |
|---|---|---|
| Python | `pyproject.toml`: 3.12 이상 3.14 미만, uv 잠금 파일 | 초기 생성 앱은 3.12로 고정해 재현 범위를 제한 |
| 서버 | FastAPI, Pydantic, 동기 psycopg 풀 | API와 저장 계층을 재사용 가능 |
| 실행 | LangGraph, PostgreSQL checkpointer, 전용 스레드 풀·lease | 장기 실행과 사람 확인 기반 존재 |
| LLM | 공통 client, Responses API, structured output, stub | 확장 노드에 동일 오류·재시도 규칙 적용 가능 |
| 설계 검증 | pglast AST, 규칙·표준 검사, 격리 PostgreSQL | 업무 로직 검증은 추가 필요 |
| 문서 | Excel·CSV·HWP·HWPX, WeasyPrint·Mermaid CLI 출력 | PDF 입력은 현재 미지원 |
| 화면 | React 19, TypeScript, Vite, React Router, Mermaid, React Flow | 기존 자체 UI와 작업공간을 확장 |
| 배포 | Docker Compose, PostgreSQL 18, Caddy, 로컬 파일 볼륨 | 현재 단일 API 프로세스 가정, 작업자 분리 필요 |

실제 의존성 판은 `uv.lock`·`frontend/package-lock.json`이 기준이다. 특정 LLM 모델의 가용성·가격은 코드 기본값만으로 보장하지 않는다.

## 입력부터 승인까지

| 단계 | 구현 위치 | 핵심 동작 |
|---|---|---|
| 업로드 | `api/runs.py`, `api/uploads.py` | 형식·크기·압축 제한, 파일 해시, run 생성 |
| 추출 | `parse_node.py`, `ingest/` | 원문 블록과 위치 보존, 필요 시 사용자 제외·확인 |
| 요구 분석 | `nodes/a01_requirements.py` | FR/NFR, 문장 분리, 질문, 추적 ID |
| 설계 | `nodes/a02_functions.py`~`a04_relationships.py` | 기능, 엔티티·속성·CRUD, 관계·FK 재사용 |
| 정리 | `codegen/normalize.py`, `naming.py` | PK·FK·UNIQUE·물리명·연결 테이블, 지원 불가 진단 |
| 생성 | `document_node.py`, `erd_node.py`, `ddl_node.py` | 같은 모델에서 산출물 생성, SQL 검증 |
| 검토 | `design_rules_node.py`, `review/`, `agent_nodes.py` | 규칙 검사, A05~A08, 근거 확인·중복 병합 |
| 재작업 | `review/rework.py`, A09, `graph.py` | 명확한 복귀는 코드, 미매핑만 LLM, 반복·상한 통제 |
| 승인·게시 | `persistence/runs.py`, `export_node.py` | critical·SQL·파일 해시 확인 후 동일 파일 게시 |

`api/main.py:create_graph`가 실제 노드를 연결한다. `graph.py`의 일부 초기 설명에 있는 stub 표현은 현재 앱 실행의 전체 상태를 나타내지 않는다.

## 네 최종 산출물의 실제 의미

| 산출물 | 현재 내용 | 실제 시스템 구현에 부족한 정보 |
|---|---|---|
| 기능 명세서 | 기능 ID·설명·우선순위 근거·req_ids·CRUD, 확인 조건·질문 | API 계약·권한·업무 상태 전이·정확한 수용 기준 |
| ERD | 정리된 엔티티·키·관계, Mermaid·PDF | 화면·사용 행위·트랜잭션 경계, 복잡한 업무 불변식 |
| DDL | PostgreSQL 테이블·PK·FK·UNIQUE와 타입 | 업무 명령·인증·동시성 처리, 버전 간 데이터 이전 |
| RTM | 원문 → 요구 → 기능 → 엔티티·관계, 미연결·제외 | 코드 심볼·API·화면·테스트 결과와의 연결 |

추가 manifest는 실행·revision·model_hash·팩·프롬프트·파일 해시를 기록한다. manifest의 `approved=true`는 승인 후 공개할 후보 내용이며, 단독 JSON 값으로 승인 여부를 믿으면 안 된다. 실제 DB의 `approval`·`approval_basis`·artifact 승인 상태와 교차 확인해야 한다.

SDD 입력은 PDF를 다시 읽어 복원하지 않는다. 승인 산출물 네 종류를 근거로 고정하고 동일 스냅샷의 구조화 데이터를 함께 사용한다. 외부에서 네 파일만 제공되면 별도 import·정합성 확인·사람 검토를 거친다.

## 저장과 버전

`persistence/schema.sql`의 플랫폼 표는 `run`, `document`, `source_block`, `model_snapshot`, `finding`, `approval`, `artifact`, `artifact_validation`, `approval_basis`, `run_event`, `job_lease`다. LangGraph의 체크포인트 표는 라이브러리가 별도 준비한다.

현재 `run.revision`은 한 설계 실행의 수정 차수다. 장기 고객 프로젝트·고객사·메일 연결·업무 구현·채택 버전 개념은 없다. 완성된 실행에 메일을 직접 resume하는 방식은 적합하지 않다. `project` 아래 불변 설계 기준과 새 변경 실행을 별도로 추가해야 한다.

모델 해시는 `specton/model_hash.py`의 요구사항·기능·엔티티·관계·정리 결과에서 계산한다. 일부 선택 필드가 없는 기존 기록의 해시를 보존하는 호환 코드가 있다. 실행 명세·화면·테스트 계약을 이 기존 해시에 무조건 넣으면 과거 승인 근거가 달라지므로 새 `spec_hash`로 확장한다.

현재 엔티티·속성은 이름 기반 안정 ID를 사용하지만, 기능·관계의 일부 ID는 순서에 영향을 받는다. 변경 분석에서 번호가 같다는 이유만으로 같은 업무 객체라고 확정할 수 없다. 별도의 프로젝트 안정 ID와 구버전 ID 매핑이 필요하다.

## 화면과 API

기존 경로는 `/`의 실행·문서 결과, `/history`, `/about`, `/workspace`다. `/runs` API는 생성·목록·상태·resume·cancel·view·파일 다운로드·SSE를 제공한다. 이력은 현재 최대 100개 limit 방식이며 cursor는 없다.

`api/session.py`는 무작위 쿠키를 run 소유 키로 사용한다. 로그인·계정 복구·프로젝트 권한은 없다. 현재 IP 제한 배포 전제와 별도로, 장기 Gmail refresh token을 연결하기 전에 지속적인 사용자 인증과 프로젝트 접근 권한을 추가해야 한다.

`useRunStatus.ts`는 수신 이벤트와 시각을 배열·객체로 누적한다. `useRuns.ts`는 15초 주기 조회와 변경 이벤트를 함께 사용한다. 새 구현·테스트 로그는 훨씬 커질 수 있어 페이징·상한·로그 분리가 필요하다.

## 테스트와 문서의 상태

Python은 단위·통합·실제 LLM 테스트를 갖추고 기본 pytest는 `db`·`llm`을 제외한다. 프런트에는 Vitest 테스트가 있으며 CI는 Python 검사·팩 최신 검사, 프런트 lint·build를 수행한다. 프런트 test·OpenAPI 타입 검사와 DB 통합 검사는 현재 CI 단계에 없다. `tests/e2e/`는 자리표시자이며 자동 브라우저 인수 체계가 필요하다.

이전 평가 기록에는 대표 문서 5건의 미완료·DDL 미생성 관측과 합성 시범 성공이 함께 있다. 뒤의 성공을 앞의 대표 입력 성공으로 바꾸거나 현재 HEAD의 성능으로 일반화하지 않는다. 품질 개선은 공개 가능한 합성 기준 입력부터 재측정한다.

## 재사용과 추가 구현의 경계

| 재사용 | 추가 구현 |
|---|---|
| 원문 위치·req_ids·Finding·버전 근거 | 프로젝트 안정 ID·변경 이력·영향 그래프 |
| 사용자 중단·재개·승인 검증 | 실행 명세 확인·후보 채택 상태 |
| SQL AST·제한 DB 계정 | 업무 DB·API·UI·통합 테스트 환경 |
| 저장 스냅샷·파일 해시·SSE | 소스 트리·빌드·테스트·미리보기 근거 |
| LLM client·stub·관점 검토 | 명세 보완·구현 계획·변경 분석 어댑터 |
| React 작업공간 | 프로젝트·피드백·명세 차이·테스트 결과 화면 |

전면 재작성보다 기존 설계 경로 옆에 독립된 구현 경로를 추가한다. 기존 문서 생성의 승인·재개·다운로드 회귀가 깨지면 새 확장 기능의 인수를 진행하지 않는다.
