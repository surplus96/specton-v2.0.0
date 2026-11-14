# 전체 파일과 모듈 지도

원본 추적 파일 523개를 기준으로 분류했다. 원본 경로·SHA-256 전체 목록은 [소스 목록](source-inventory.json)에 있다. 해시는 원본 파일의 값이며 정리 후 파일의 해시가 아니다. 런타임 비밀값·DB·고객 원문·Git 이력은 이 목록의 복제 대상에 포함하지 않는다.

## 디렉터리 구성

| 경로 | 원본 파일 수 | 책임 |
|---|---:|---|
| `.github` | 11 | CI·이슈 양식·개발 자동화 |
| `docker` | 4 | 컨테이너 설정·초기 DB |
| `docs` | 45 | 설계·계약·평가·ADR |
| `domain_packs` | 49 | 표준 사전·업무 팩·원본 출처 |
| `eval` | 1 | 비공개 평가 자료 위치의 자리표시자 |
| `frontend` | 137 | React 화면·API client·mock·테스트 |
| `root` | 17 | 실행·의존성·라이선스·개발 안내 |
| `specton` | 125 | 서버·설계·생성·검증·평가 |
| `tests` | 134 | 단위·통합·LLM 검사 |

## Python 전체 모듈

모듈 설명은 파일의 계약과 진입점 기준이다. 구현 상태·현재 한계는 [프로젝트 분석](00-project-analysis.md)을 함께 본다.

| 파일 | 줄 수 | 책임 |
|---|---:|---|
| [specton/__init__.py](../../specton/__init__.py) | 3 | Specton: 고객 요구사항 기반 기능·데이터 모델 자동 설계 Agent |
| [specton/agent_nodes.py](../../specton/agent_nodes.py) | 319 | 에이전트(A01~A09)를 그래프 노드로 잇는다 |
| [specton/api/__init__.py](../../specton/api/__init__.py) | 1 | FastAPI 실행 제어 API (06 문서) |
| [specton/api/deps.py](../../specton/api/deps.py) | 34 | 요청마다 쓰는 의존성: 설정, DB 연결 |
| [specton/api/errors.py](../../specton/api/errors.py) | 154 | 오류 응답을 `code`/`message`/`run_id`/`retryable` 형식으로 통일한다 (06 문서 "오류 형식") |
| [specton/api/main.py](../../specton/api/main.py) | 123 | FastAPI 앱 진입점 |
| [specton/api/runs.py](../../specton/api/runs.py) | 297 | 실행 제어 API: 등록·조회·SSE·재개·취소 (06 문서) |
| [specton/api/session.py](../../specton/api/session.py) | 38 | 세션 발급: 모든 run 접근의 소유자(`owner_ref`)를 정한다 (ADR-0011) |
| [specton/api/uploads.py](../../specton/api/uploads.py) | 209 | 업로드 원문 저장: 확장자·크기 확인, 해시 계산, run별 저장 (06·11 문서) |
| [specton/artifacts.py](../../specton/artifacts.py) | 106 | 생성 노드의 공통 파일 저장과 체크포인트용 인계 정보. DB에는 실행기가 기록한다 |
| [specton/codegen/__init__.py](../../specton/codegen/__init__.py) | 1 | 코드 생성: ID·명명·N:M·FK 파생, Mermaid·DDL·RTM 생성 |
| [specton/codegen/ddl.py](../../specton/codegen/ddl.py) | 282 | DDL 생성: 정리 결과(`NormalizedModel`) → PostgreSQL DDL 문자열 |
| [specton/codegen/erd.py](../../specton/codegen/erd.py) | 208 | ERD: 정리된 모델 → Mermaid `erDiagram` |
| [specton/codegen/erd_areas.py](../../specton/codegen/erd_areas.py) | 208 | ERD 업무 영역 나누기: 테이블을 이름에 든 낱말로 영역에 넣는다 |
| [specton/codegen/function_spec.py](../../specton/codegen/function_spec.py) | 175 | 기능 명세서: 설계 상태 → Markdown |
| [specton/codegen/key_constraints.py](../../specton/codegen/key_constraints.py) | 71 | 명시적 FK 재사용의 키·타입·NULL 검증. 의미는 관계 선언으로 받고 이름으로 추론하지 않는다 |
| [specton/codegen/manifest.py](../../specton/codegen/manifest.py) | 60 | 출력 manifest: 한 revision의 산출물이 어느 실행·모델·버전에서 나왔는지 |
| [specton/codegen/model.py](../../specton/codegen/model.py) | 46 | 모델 정리 코드가 쓰는 결과 모델과 줄임 함수 |
| [specton/codegen/naming.py](../../specton/codegen/naming.py) | 366 | 물리명 만들기와 이름 검사 |
| [specton/codegen/normalize.py](../../specton/codegen/normalize.py) | 830 | 모델 정리: 엔티티·속성·관계 → 테이블·컬럼·PK·FK·연결 테이블 |
| [specton/codegen/normalize_step.py](../../specton/codegen/normalize_step.py) | 84 | 그래프 상태에서 모델 정리를 부르는 연결 함수 |
| [specton/codegen/rtm.py](../../specton/codegen/rtm.py) | 212 | RTM(요구사항 추적표): 원문 → 요구사항 → 기능 → 엔티티·관계 |
| [specton/config.py](../../specton/config.py) | 91 | 실행 설정. 값은 환경 변수(.env)에서 읽고 코드에 비밀값을 두지 않는다 |
| [specton/contracts/__init__.py](../../specton/contracts/__init__.py) | 176 | 단계 간 데이터 계약: 상태·LLM 입출력·Finding (05 문서) |
| [specton/contracts/api.py](../../specton/contracts/api.py) | 261 | 실행 제어 API 계약: run 상태·resume 응답·SSE 이벤트·오류 (06 문서) |
| [specton/contracts/base.py](../../specton/contracts/base.py) | 192 | 계약 공통 요소: 기본 모델, 열거형, ID 형식, 원문 위치 (05 문서) |
| [specton/contracts/design.py](../../specton/contracts/design.py) | 252 | 설계 모델: 기능·엔티티·속성·관계 (A02~A04 출력과 저장 모델, 05 문서) |
| [specton/contracts/findings.py](../../specton/contracts/findings.py) | 89 | 검토 지적: LLM 출력(FindingDraft)과 저장 모델(Finding) (04·05 문서) |
| [specton/contracts/normalized.py](../../specton/contracts/normalized.py) | 138 | 모델 정리 결과: 테이블·컬럼·PK·FK (05 문서, ADR-0016) |
| [specton/contracts/requirements.py](../../specton/contracts/requirements.py) | 130 | 입력 원문과 요구사항 (A01 출력, 05 문서) |
| [specton/contracts/state.py](../../specton/contracts/state.py) | 193 | 실행 상태와 추적 무결성 검사 (03·05 문서, REQ-20·21) |
| [specton/contracts/validation.py](../../specton/contracts/validation.py) | 147 | SQL 검증 결과 |
| [specton/ddl_adapter.py](../../specton/ddl_adapter.py) | 75 | 정리된 설계 → DDL 바이트 → 사전 SQL 검사 |
| [specton/ddl_node.py](../../specton/ddl_node.py) | 48 | 실제 DDL 생성·5단계 SQL 검증의 API 그래프 가지 |
| [specton/design_rules_node.py](../../specton/design_rules_node.py) | 119 | 최종 설계의 RULE·SC를 API 그래프에 연결한다. DB 저장·재작업 판단은 기존 경로를 쓴다 |
| [specton/document_node.py](../../specton/document_node.py) | 60 | 문서 생성 가지: 같은 고정 모델의 기능 명세·RTM을 공통 저장 경로에 인계한다 |
| [specton/erd_node.py](../../specton/erd_node.py) | 50 | 저장된 정리 결과 → Mermaid 초안·선택적 PDF 후보 → 공통 산출물 인계 |
| [specton/evaluation/__init__.py](../../specton/evaluation/__init__.py) | 1 | 승인 정답·매칭과 저장된 실행 결과를 채점하는 오프라인 도구. LLM·DB를 호출하지 않는다 |
| [specton/evaluation/__main__.py](../../specton/evaluation/__main__.py) | 34 | python -m specton.evaluation input.json --out report.json (네트워크 호출 없음) |
| [specton/evaluation/compose_lexicon.py](../../specton/evaluation/compose_lexicon.py) | 43 | python -m specton.evaluation.compose_lexicon: 네트워크 없이 별도 탐색 사본 준비 |
| [specton/evaluation/lexicon_overlay.py](../../specton/evaluation/lexicon_overlay.py) | 380 | A08 탐색 사전의 오프라인 사본·출처·승인 검증. 운영 팩은 변경하지 않는다 |
| [specton/evaluation/metrics.py](../../specton/evaluation/metrics.py) | 120 | 분모를 보존하는 순수 채점 함수. 허용 경고를 오탐·정탐으로 바꿔 세지 않는다 |
| [specton/evaluation/models.py](../../specton/evaluation/models.py) | 240 | 통합 채점 입력. 정답·허용 매칭은 사람이 승인한 자료를 변환해 제공한다 |
| [specton/evaluation/observations.py](../../specton/evaluation/observations.py) | 38 | 저장된 DesignState에서 채점 대상만 꺼낸다. 원문·정답·매칭을 생성하지 않는다 |
| [specton/evaluation/pipeline.py](../../specton/evaluation/pipeline.py) | 354 | 승인된 탐색 조건을 기존 API 그래프 전체에 연결한다. 운영 API는 이 도구를 켜지 않는다 |
| [specton/evaluation/preparation.py](../../specton/evaluation/preparation.py) | 205 | 비공개 승인 정답 목록을 선택 대기 입력으로 바꾼다. 실행·채점하지 않는다 |
| [specton/evaluation/report.py](../../specton/evaluation/report.py) | 180 | 오프라인 통합 보고. 미실행·실패와 측정하지 않은 값을 따로 보존한다 |
| [specton/evaluation/run_pipeline.py](../../specton/evaluation/run_pipeline.py) | 449 | python -m specton.evaluation.run_pipeline: 고정 조건으로 실제 API 전체 실행·기록 |
| [specton/export/__init__.py](../../specton/export/__init__.py) | 1 | 산출물 내보내기: 중간 Markdown, 최종 PDF·SQL·Excel/CSV |
| [specton/export/markdown.py](../../specton/export/markdown.py) | 184 | 합의한 Markdown 문법만 HTML로 바꾼다 |
| [specton/export/pdf.py](../../specton/export/pdf.py) | 664 | PDF 출력 엔진 |
| [specton/export_node.py](../../specton/export_node.py) | 37 | 검증·사람 승인한 현재 산출물을 같은 바이트의 승인본으로 인계한다 |
| [specton/function_spec_node.py](../../specton/function_spec_node.py) | 30 | 설계 상태 → 기능 명세서 Markdown 초안 파일 → 공통 산출물 인계 |
| [specton/graph.py](../../specton/graph.py) | 622 | 설계 그래프 |
| [specton/ids.py](../../specton/ids.py) | 21 | 설계 객체의 내부 ID 계산 (ADR-0016). A03 노드와 모델 정리(`codegen/`)가 함께 쓴다 |
| [specton/ingest/__init__.py](../../specton/ingest/__init__.py) | 1 | 요구사항 문서 입력: Excel·CSV·PDF·HWPX 추출과 원문 위치 보존 (08 문서) |
| [specton/ingest/hangul.py](../../specton/ingest/hangul.py) | 409 | 한글(.hwp·.hwpx) 요구사항 상세표를 원문 한 건씩(`SourceRequirement`)으로 읽는다 |
| [specton/ingest/hangul_engine.py](../../specton/ingest/hangul_engine.py) | 167 | 한글 문서(.hwp·.hwpx) 읽기 엔진 연결부. 저장소에서 `import rhwp`는 이 파일에만 둔다 |
| [specton/ingest/tabular.py](../../specton/ingest/tabular.py) | 545 | 엑셀·CSV 요구사항 표를 원문 한 건씩(`SourceRequirement`)으로 읽는다 (ADR-0003, docs/10) |
| [specton/llm/__init__.py](../../specton/llm/__init__.py) | 1 | 공통 LLM client: 호출·구조화 출력 재요청·프롬프트 버전 기록 |
| [specton/llm/client.py](../../specton/llm/client.py) | 163 | 공통 LLM client. 모든 노드는 이 client를 주입받아 LLM을 호출한다 |
| [specton/llm/errors.py](../../specton/llm/errors.py) | 49 | LLM 호출 실패 종류. 실패를 빈 성공 응답으로 바꾸지 않고 종류별 예외로 알린다 |
| [specton/llm/openai_transport.py](../../specton/llm/openai_transport.py) | 79 | 실제 OpenAI 호출. 구조화 출력(JSON schema)으로 요청하고, 검증·재요청은 LLMClient가 한다 |
| [specton/llm/stub.py](../../specton/llm/stub.py) | 50 | 테스트용 stub. 준비한 응답·오류를 순서대로 돌려주고, 실제 API는 호출하지 않는다 |
| [specton/llm/types.py](../../specton/llm/types.py) | 54 | LLM 호출의 요청·결과 모델. 모두 불변(frozen)이다 |
| [specton/manifest_node.py](../../specton/manifest_node.py) | 43 | 최종 검토 직전 manifest 승인 후보를 저장한다. 앱 DB 게시·승인은 실행기 책임이다 |
| [specton/model_hash.py](../../specton/model_hash.py) | 35 | 생성기와 모델 스냅샷이 공유하는 설계 해시. 파일 해시와는 별개다 |
| [specton/node_progress.py](../../specton/node_progress.py) | 74 | 실행기가 공개하는 노드 메타데이터. 그래프 입력·출력 원문은 공개하지 않는다 |
| [specton/nodes/__init__.py](../../specton/nodes/__init__.py) | 1 | 에이전트 노드 어댑터 A01~A09 (04 문서) |
| [specton/nodes/a01_requirements.py](../../specton/nodes/a01_requirements.py) | 215 | A01 요구사항 분석 노드 (04 문서, REQ-04, TC-A01) |
| [specton/nodes/a02_functions.py](../../specton/nodes/a02_functions.py) | 213 | A02 기능 설계 노드 (04 문서, REQ-06, TC-A02) |
| [specton/nodes/a03_entities.py](../../specton/nodes/a03_entities.py) | 609 | A03 엔티티·속성·CRUD 설계 (04 문서, REQ-07, TC-A03) |
| [specton/nodes/a04_relationships.py](../../specton/nodes/a04_relationships.py) | 290 | A04 관계 설계 (04 문서, REQ-08) |
| [specton/nodes/a09_rework_router.py](../../specton/nodes/a09_rework_router.py) | 101 | A09 조건부 재작업 판단 (04 문서, REQ-16) |
| [specton/nodes/common.py](../../specton/nodes/common.py) | 132 | 에이전트 노드의 공통 부분 (04 문서 "노드 작성 규칙") |
| [specton/normalization_node.py](../../specton/normalization_node.py) | 74 | 실제 모델 정리 → 그래프 상태. 문제 분류 정책은  어댑터를 주입한다 |
| [specton/packs/__init__.py](../../specton/packs/__init__.py) | 1 | 도메인 팩 로더: 버전이 지정된 YAML 팩 (08 문서) |
| [specton/packs/build.py](../../specton/packs/build.py) | 352 | 도메인 팩 생성기 |
| [specton/packs/examples.py](../../specton/packs/examples.py) | 81 | few-shot 예시 로더 (04 문서 "노드 작성 규칙") |
| [specton/packs/lexicon_sources.py](../../specton/packs/lexicon_sources.py) | 260 | 운영 팩 확장 어휘의 출처·선정 근거를 오프라인으로 검증한다 |
| [specton/packs/loader.py](../../specton/packs/loader.py) | 461 | 도메인 팩 로더 |
| [specton/packs/provenance.py](../../specton/packs/provenance.py) | 43 | 팩 고정 근거. 경로·줄바꿈에 독립적인 내용 해시를 정리 결과에 보존한다 |
| [specton/packs/selection.py](../../specton/packs/selection.py) | 58 | 공식 이음동의어·금칙어를 팩 낱말로 선택한 예외를 명시적으로 검증한다 |
| [specton/packs/term_names.py](../../specton/packs/term_names.py) | 77 | 한 팩 안에서 NFC로 같아지는 용어 이름을 찾는다 |
| [specton/parse_node.py](../../specton/parse_node.py) | 90 | 문서 읽기(parse) 노드 |
| [specton/pdf_adapter.py](../../specton/pdf_adapter.py) | 128 | PDF 후보: 승인본용 바이트를 비공개로 준비하고 같은 해시로 승인·게시한다 |
| [specton/persistence/__init__.py](../../specton/persistence/__init__.py) | 1 | 플랫폼 저장소와 LangGraph checkpointer |
| [specton/persistence/artifacts.py](../../specton/persistence/artifacts.py) | 89 | 체크포인트의 생성 결과를 앱 조회·다운로드와 이벤트에 함께 게시한다 |
| [specton/persistence/db.py](../../specton/persistence/db.py) | 96 | DB 연결 풀·표 생성·LangGraph checkpointer (ADR-0012) |
| [specton/persistence/errors.py](../../specton/persistence/errors.py) | 57 | 저장 계층 오류. API가 `ErrorCode`로 바꿔 응답한다 (06 문서) |
| [specton/persistence/lease.py](../../specton/persistence/lease.py) | 108 | 작업 lease: run당 실행자를 1개로 제한한다 (ADR-0012) |
| [specton/persistence/runs.py](../../specton/persistence/runs.py) | 626 | run 저장: 생성·조회·진행 기록·재개·취소 (05 문서 "플랫폼 저장", ADR-0012) |
| [specton/persistence/snapshots.py](../../specton/persistence/snapshots.py) | 302 | 설계 모델·지적·산출물 저장과 화면용 조회 (05 문서 "플랫폼 저장", 06 문서 `view`·`artifacts`) |
| [specton/persistence/validation_attempts.py](../../specton/persistence/validation_attempts.py) | 45 | 체크포인트의 SQL 검증 시도를 산출물 게시와 같은 트랜잭션에 기록한다 |
| [specton/persistence/validations.py](../../specton/persistence/validations.py) | 189 | SQL 검증 기록 저장·조회 |
| [specton/pilot.py](../../specton/pilot.py) | 152 | 수동 시범 실행: 실제 설계 노드 A01~A04와 검토를 호출하고 사용량만 돌려준다 |
| [specton/review/__init__.py](../../specton/review/__init__.py) | 1 | 검토: 규칙 검사·리뷰어(설정형)·근거 필터·병합 |
| [specton/review/comparison.py](../../specton/review/comparison.py) | 99 | 같은 고정 설계를 실제 그래프 검토 가지로 실행한다. 정답은 받지 않는다 |
| [specton/review/ddl_findings.py](../../specton/review/ddl_findings.py) | 74 | SQL 검증 실패를 원래 설계 객체의 RULE-07 지적으로 바꾼다. 지문이 같은 문제는 하나로 합친다 |
| [specton/review/design_rules.py](../../specton/review/design_rules.py) | 108 | 최종 설계의 FR 연결과 CRUD 정합성 검사. 그래프 연결은 호출자가 담당한다 |
| [specton/review/eval_fixtures.py](../../specton/review/eval_fixtures.py) | 586 | 검토 관점 평가용 고정 설계 |
| [specton/review/eval_normalization.py](../../specton/review/eval_normalization.py) | 45 | 평가 설계에 실제 정리를 적용한다. 사전을 보완하거나 실패를 미탐으로 바꾸지 않는다 |
| [specton/review/fingerprint.py](../../specton/review/fingerprint.py) | 22 | 지적 지문 (04 문서 "지적 확정 절차"). 리뷰어와 규칙 검사가 같은 함수를 쓴다 |
| [specton/review/fixture_audit.py](../../specton/review/fixture_audit.py) | 122 | 고정 평가 자료의 오프라인 검토 목록. 의미 정답·승인·독립성을 판정하지 않는다 |
| [specton/review/merge.py](../../specton/review/merge.py) | 171 | 리뷰 합류·근거 확인·지적 병합 |
| [specton/review/normalization_findings.py](../../specton/review/normalization_findings.py) | 411 | 모델 정리 실패 → 규칙 지적. 정리 문제(`Problem`)를 검토 단계의 `Finding`으로 바꾼다 |
| [specton/review/normalized_view.py](../../specton/review/normalized_view.py) | 89 | 리뷰어에게 보여 줄 정리 결과 요약 |
| [specton/review/perspective.py](../../specton/review/perspective.py) | 56 | 설정형 리뷰어의 관점 설정 (04 문서, ADR-0008) |
| [specton/review/reviewer.py](../../specton/review/reviewer.py) | 423 | 설정형 리뷰어 노드 (04 문서, ADR-0008) |
| [specton/review/rework.py](../../specton/review/rework.py) | 83 | 재작업 판단 (03·04 문서, REQ-16, ADR-0010). LLM을 쓰지 않는 순수 함수다 |
| [specton/review/rule_policy.py](../../specton/review/rule_policy.py) | 35 | 팩의 처리 정책을 실제 지적에 적용한다. 동적 복귀는 검사기가 계산한 경로를 보존한다 |
| [specton/review/standard_compliance.py](../../specton/review/standard_compliance.py) | 699 | 표준 준수 검사 SC-01~06. 정리에 성공한 설계의 칸을 공통표준 원본과 비교한다 |
| [specton/rtm_node.py](../../specton/rtm_node.py) | 32 | 설계 상태 → RTM 엑셀·CSV 초안 파일 → 공통 산출물 인계 |
| [specton/runner.py](../../specton/runner.py) | 674 | 실행기: 전용 스레드 풀에서 설계 그래프를 돌리고 앱 상태를 저장한다 |
| [specton/type_limits.py](../../specton/type_limits.py) | 25 | PostgreSQL 18 타입 매개변수 상한. DDL 생성기와 A03 출력 검사가 함께 쓴다 |
| [specton/validate/__init__.py](../../specton/validate/__init__.py) | 1 | 검증: DDL 파싱·격리 DB 실행·출력 형식 검사 |
| [specton/validate/allowed_sql.py](../../specton/validate/allowed_sql.py) | 371 | SQL 검증 앞 두 단계: 파싱 → 허용 SQL 검사. DB에 접속하지 않는다 |
| [specton/validate/sandbox.py](../../specton/validate/sandbox.py) | 435 | SQL 검증 뒤 세 단계: 격리 DB 실행 → 롤백 → 잔여 객체 확인 |
| [specton/validation_attempts.py](../../specton/validation_attempts.py) | 117 | 검증 호출의 ID·산출물 문맥·공용 결과를 체크포인트에 함께 보존한다 |

## 프런트 주요 경계

| 경로 | 책임 |
|---|---|
| `frontend/src/App.tsx`, `layout/` | 라우트·내비게이션·단계·공용 레이아웃 |
| `pages/start/`, `upload/`, `StartPage.tsx` | 실행 생성·입력 제약·최근 이력 |
| `pages/run/`, `RunPage.tsx` | SSE·상태 추적·재개·취소·시간 표시 |
| `pages/extraction/`, `requirements/` | 원문·분석 결과 확인·사용자 응답 |
| `pages/review/` | 규칙·검토 지적·SQL 검증·최종 승인 |
| `pages/workspace/` | 문서·ERD·RTM·다운로드·manifest |
| `pages/ai-workspace/` | 파이프라인·정리 결과·추적 그래프 |
| `api/` | OpenAPI 타입·HTTP·SSE·오류·표시 데이터 |
| `mocks/` | MSW·합성 응답·UI 시험 |
| `ui/`, `index.css`, `theme.ts` | 공용 컴포넌트·테마·스타일 |

## 테스트 분류

| 경로 | 검사 범위 |
|---|---|
| `tests/unit/` | 계약·노드·정규화·생성·보안·팩·평가·문서 검사 |
| `tests/integration/` | 그래프와 DB·API·lease·checkpoint·승인·파일 연결 |
| `tests/llm/` | 실제 모델 시범·검토 방식 비교, 수동 실행 |
| `tests/e2e/` | 현재 자리표시자, 후속 브라우저 인수 대상 |
| `frontend/src/**/*.test.ts*` | UI 규칙·client·SSE·ERD·RTM·다운로드 검사 |

## 전체 경로 탐색

아래 목록은 원본 파일 경로 전체다. 제거된 개발 자동화 파일도 복제 기준을 설명하기 위해 경로만 기록한다.

```text
.dockerignore
.env.deploy.example
.env.example
.gitattributes
.github/CODEOWNERS
.github/ISSUE_TEMPLATE/bug.yml
.github/ISSUE_TEMPLATE/change.yml
.github/ISSUE_TEMPLATE/config.yml
.github/ISSUE_TEMPLATE/task.yml
.github/pull_request_template.md
.github/scripts/board-status.sh
.github/scripts/pr-activity.sh
.github/workflows/board-status.yml
.github/workflows/ci.yml
.github/workflows/pr-activity.yml
.gitignore
.python-version
CLAUDE.md
CONTRIBUTING.md
Dockerfile
LICENSE
README.en.md
README.md
compose.deploy.yml
compose.local.yml
docker-compose.yml
docker/api/puppeteer.json
docker/postgres/init/01_sandbox.sh
docker/web/Caddyfile
docker/web/Caddyfile.local
docs/01-overview.md
docs/02-requirements.md
docs/03-architecture.md
docs/04-agents.md
docs/05-data-contracts.md
docs/06-api.md
docs/07-testing-eval.md
docs/08-roles.md
docs/09-ui-flow.md
docs/10-io-and-packs.md
docs/11-deployment-security.md
docs/12-test-cases.md
docs/13-risks-changes.md
docs/14-extensions.md
docs/20-evaluation-lexicon.md
docs/23-acceptance-runbook.md
docs/README.md
docs/adr/0001-role-assignment.md
docs/adr/0002-mvp-scope.md
docs/adr/0003-input-format.md
docs/adr/0004-document-engines.md
docs/adr/0005-ui-library.md
docs/adr/0006-priority-unspecified.md
docs/adr/0007-llm-usage.md
docs/adr/0008-configurable-reviewer.md
docs/adr/0009-contracts-api-packs.md
docs/adr/0010-review-severity.md
docs/adr/0011-auth-retention.md
docs/adr/0012-runner.md
docs/adr/0013-aws-deployment.md
docs/adr/0014-evaluation.md
docs/adr/0015-conditional-check.md
docs/adr/0016-model-ids-and-keys.md
docs/adr/README.md
docs/adr/template.md
docs/api/openapi.json
docs/evidence/18-review-comparison-20261111.json
docs/evidence/20-controlled-evaluation-20261111.json
docs/evidence/20-curated-review-diagnostic-20261111.json
docs/evidence/20-diagnostic-dataset-audit-20261111.json
docs/evidence/20-fixed-review-diagnosis-20261111.json
docs/evidence/20-post-fix-evaluation-20261111.json
docs/evidence/22-a06-context-regression-20261111.json
docs/evidence/23-local-browser-acceptance-20261111.json
docs/evidence/49-synthetic-pilot-20261111.json
domain_packs/README.md
domain_packs/common/RATIONALE.md
domain_packs/common/domains.yaml
domain_packs/common/manifest.yaml
domain_packs/common/naming.yaml
domain_packs/common/pack.lock
domain_packs/common/rules.yaml
domain_packs/common/words.yaml
domain_packs/inventory/erd_areas.yaml
domain_packs/inventory/examples/A01.yaml
domain_packs/inventory/examples/A02.yaml
domain_packs/inventory/examples/A03.yaml
domain_packs/inventory/examples/A04.yaml
domain_packs/inventory/examples/A05.yaml
domain_packs/inventory/examples/A06.yaml
domain_packs/inventory/examples/A07.yaml
domain_packs/inventory/examples/A08.yaml
domain_packs/inventory/examples/A09.yaml
domain_packs/inventory/lexicon_sources.yaml
domain_packs/inventory/manifest.yaml
domain_packs/inventory/pack.lock
domain_packs/inventory/patterns.yaml
domain_packs/inventory/sources/hf_20260727.csv
domain_packs/inventory/sources/knps_20240911.csv
domain_packs/inventory/sources/words_0.1.21.yaml
domain_packs/inventory/standard_selection.yaml
domain_packs/inventory/term_specs.yaml
domain_packs/inventory/terms.yaml
domain_packs/inventory/words.yaml
domain_packs/maintenance/RATIONALE.md
domain_packs/maintenance/examples/A01.yaml
domain_packs/maintenance/examples/A02.yaml
domain_packs/maintenance/examples/A03.yaml
domain_packs/maintenance/examples/A04.yaml
domain_packs/maintenance/examples/A05.yaml
domain_packs/maintenance/examples/A06.yaml
domain_packs/maintenance/examples/A07.yaml
domain_packs/maintenance/examples/A08.yaml
domain_packs/maintenance/examples/A09.yaml
domain_packs/maintenance/manifest.yaml
domain_packs/maintenance/pack.lock
domain_packs/maintenance/patterns.yaml
domain_packs/maintenance/term_specs.yaml
domain_packs/maintenance/terms.yaml
domain_packs/maintenance/words.yaml
domain_packs/sources/common_standard_domains_20251101.csv
domain_packs/sources/common_standard_terms_20251101.csv
domain_packs/sources/common_standard_words_20251101.csv
domain_packs/sources/sources.yaml
eval/.gitkeep
frontend/.dockerignore
frontend/.env.example
frontend/.gitignore
frontend/Dockerfile
frontend/README.md
frontend/eslint.config.js
frontend/index.html
frontend/package-lock.json
frontend/package.json
frontend/public/apple-touch-icon.png
frontend/public/favicon-32.png
frontend/public/favicon.ico
frontend/public/fonts/OFL.txt
frontend/public/fonts/PretendardVariable.woff2
frontend/public/mockServiceWorker.js
frontend/src/App.tsx
frontend/src/api/client.test.ts
frontend/src/api/client.ts
frontend/src/api/errors.ts
frontend/src/api/events.ts
frontend/src/api/runNames.test.ts
frontend/src/api/runNames.ts
frontend/src/api/schema.d.ts
frontend/src/api/types.ts
frontend/src/api/viewItems.ts
frontend/src/index.css
frontend/src/layout/AppLayout.tsx
frontend/src/layout/Icon.tsx
frontend/src/layout/LazyBoundary.tsx
frontend/src/layout/StageSteps.tsx
frontend/src/layout/StatusTag.tsx
frontend/src/layout/stageSteps.test.ts
frontend/src/layout/stageSteps.ts
frontend/src/main.tsx
frontend/src/mocks/backend.ts
frontend/src/mocks/browser.ts
frontend/src/mocks/data.ts
frontend/src/mocks/rtm.ts
frontend/src/pages/AboutPage.tsx
frontend/src/pages/NotFoundPage.tsx
frontend/src/pages/RunPage.tsx
frontend/src/pages/RunsPage.tsx
frontend/src/pages/StartPage.tsx
frontend/src/pages/ai-workspace/AiWorkspacePage.tsx
frontend/src/pages/ai-workspace/DetailPanel.tsx
frontend/src/pages/ai-workspace/ErdCanvas.tsx
frontend/src/pages/ai-workspace/PipelineGraph.tsx
frontend/src/pages/ai-workspace/TraceCanvas.tsx
frontend/src/pages/ai-workspace/aiWorkspace.css
frontend/src/pages/ai-workspace/erd.test.ts
frontend/src/pages/ai-workspace/erd.ts
frontend/src/pages/ai-workspace/flowText.ts
frontend/src/pages/ai-workspace/nodeEvents.ts
frontend/src/pages/ai-workspace/pipeline.test.ts
frontend/src/pages/ai-workspace/pipeline.ts
frontend/src/pages/ai-workspace/select.test.ts
frontend/src/pages/ai-workspace/select.ts
frontend/src/pages/ai-workspace/stepDetail.test.ts
frontend/src/pages/ai-workspace/stepDetail.ts
frontend/src/pages/ai-workspace/trace.test.ts
frontend/src/pages/ai-workspace/trace.ts
frontend/src/pages/extraction/ExtractionPanel.tsx
frontend/src/pages/extraction/rules.test.ts
frontend/src/pages/extraction/rules.ts
frontend/src/pages/requirements/RequirementsPanel.tsx
frontend/src/pages/requirements/rules.test.ts
frontend/src/pages/requirements/rules.ts
frontend/src/pages/review/DesignTables.tsx
frontend/src/pages/review/FindingsTable.tsx
frontend/src/pages/review/ReviewPanel.tsx
frontend/src/pages/review/ReviewSummary.tsx
frontend/src/pages/review/SqlValidationPanel.tsx
frontend/src/pages/review/checklist.test.ts
frontend/src/pages/review/checklist.ts
frontend/src/pages/review/design.ts
frontend/src/pages/review/rules.test.ts
frontend/src/pages/review/rules.ts
frontend/src/pages/review/sqlValidation.test.ts
frontend/src/pages/review/sqlValidation.ts
frontend/src/pages/run/Elapsed.tsx
frontend/src/pages/run/ProgressPanel.tsx
frontend/src/pages/run/RunEyebrow.tsx
frontend/src/pages/run/activity.test.ts
frontend/src/pages/run/activity.ts
frontend/src/pages/run/followRun.test.ts
frontend/src/pages/run/followRun.ts
frontend/src/pages/run/run.test.ts
frontend/src/pages/run/runHeader.test.ts
frontend/src/pages/run/runHeader.ts
frontend/src/pages/run/screens.ts
frontend/src/pages/run/useResume.ts
frontend/src/pages/run/useRunStatus.ts
frontend/src/pages/runMeta.test.ts
frontend/src/pages/runMeta.ts
frontend/src/pages/start/FourSteps.tsx
frontend/src/pages/start/HowItWorks.tsx
frontend/src/pages/start/RunCards.tsx
frontend/src/pages/start/UploadPanel.tsx
frontend/src/pages/upload/rules.test.ts
frontend/src/pages/upload/rules.ts
frontend/src/pages/useRuns.ts
frontend/src/pages/useViewSection.ts
frontend/src/pages/workspace/DownloadButton.tsx
frontend/src/pages/workspace/DownloadCard.test.tsx
frontend/src/pages/workspace/DownloadCard.tsx
frontend/src/pages/workspace/DownloadPanel.tsx
frontend/src/pages/workspace/ErdView.tsx
frontend/src/pages/workspace/Pipeline.tsx
frontend/src/pages/workspace/ResultSummary.tsx
frontend/src/pages/workspace/WorkspacePanel.tsx
frontend/src/pages/workspace/files.ts
frontend/src/pages/workspace/manifest.test.ts
frontend/src/pages/workspace/pipeline.test.ts
frontend/src/pages/workspace/pipeline.ts
frontend/src/pages/workspace/rtm.test.ts
frontend/src/pages/workspace/rtm.ts
frontend/src/pages/workspace/rules.test.ts
frontend/src/pages/workspace/rules.ts
frontend/src/pages/workspace/summary.test.ts
frontend/src/pages/workspace/summary.ts
frontend/src/theme.ts
frontend/src/ui/Button.tsx
frontend/src/ui/ConfirmButton.tsx
frontend/src/ui/DataTable.tsx
frontend/src/ui/Lines.tsx
frontend/src/ui/Loading.tsx
frontend/src/ui/Notice.tsx
frontend/src/ui/ScreenHead.tsx
frontend/src/ui/SectionState.tsx
frontend/src/ui/Segmented.tsx
frontend/src/ui/Tabs.tsx
frontend/src/ui/particle.ts
frontend/src/vite-env.d.ts
frontend/tsconfig.app.json
frontend/tsconfig.json
frontend/tsconfig.node.json
frontend/vite.config.ts
pyproject.toml
specton/__init__.py
specton/agent_nodes.py
specton/api/__init__.py
specton/api/deps.py
specton/api/errors.py
specton/api/main.py
specton/api/runs.py
specton/api/session.py
specton/api/uploads.py
specton/artifacts.py
specton/codegen/__init__.py
specton/codegen/ddl.py
specton/codegen/erd.py
specton/codegen/erd_areas.py
specton/codegen/function_spec.py
specton/codegen/key_constraints.py
specton/codegen/manifest.py
specton/codegen/model.py
specton/codegen/naming.py
specton/codegen/normalize.py
specton/codegen/normalize_step.py
specton/codegen/rtm.py
specton/config.py
specton/contracts/__init__.py
specton/contracts/api.py
specton/contracts/base.py
specton/contracts/design.py
specton/contracts/findings.py
specton/contracts/normalized.py
specton/contracts/requirements.py
specton/contracts/state.py
specton/contracts/validation.py
specton/ddl_adapter.py
specton/ddl_node.py
specton/design_rules_node.py
specton/document_node.py
specton/erd_node.py
specton/evaluation/__init__.py
specton/evaluation/__main__.py
specton/evaluation/compose_lexicon.py
specton/evaluation/lexicon_overlay.py
specton/evaluation/metrics.py
specton/evaluation/models.py
specton/evaluation/observations.py
specton/evaluation/pipeline.py
specton/evaluation/preparation.py
specton/evaluation/report.py
specton/evaluation/run_pipeline.py
specton/export/__init__.py
specton/export/markdown.py
specton/export/pdf.py
specton/export_node.py
specton/function_spec_node.py
specton/graph.py
specton/ids.py
specton/ingest/__init__.py
specton/ingest/column_map.yaml
specton/ingest/hangul.py
specton/ingest/hangul_engine.py
specton/ingest/tabular.py
specton/llm/__init__.py
specton/llm/client.py
specton/llm/errors.py
specton/llm/openai_transport.py
specton/llm/stub.py
specton/llm/types.py
specton/manifest_node.py
specton/model_hash.py
specton/node_progress.py
specton/nodes/__init__.py
specton/nodes/a01_requirements.py
specton/nodes/a02_functions.py
specton/nodes/a03_entities.py
specton/nodes/a04_relationships.py
specton/nodes/a09_rework_router.py
specton/nodes/common.py
specton/normalization_node.py
specton/packs/__init__.py
specton/packs/build.py
specton/packs/examples.py
specton/packs/lexicon_sources.py
specton/packs/loader.py
specton/packs/provenance.py
specton/packs/selection.py
specton/packs/term_names.py
specton/parse_node.py
specton/pdf_adapter.py
specton/persistence/__init__.py
specton/persistence/artifacts.py
specton/persistence/db.py
specton/persistence/errors.py
specton/persistence/lease.py
specton/persistence/runs.py
specton/persistence/schema.sql
specton/persistence/snapshots.py
specton/persistence/validation_attempts.py
specton/persistence/validations.py
specton/pilot.py
specton/review/__init__.py
specton/review/comparison.py
specton/review/ddl_findings.py
specton/review/design_rules.py
specton/review/eval_fixtures.py
specton/review/eval_normalization.py
specton/review/fingerprint.py
specton/review/fixture_audit.py
specton/review/merge.py
specton/review/normalization_findings.py
specton/review/normalized_view.py
specton/review/perspective.py
specton/review/perspectives/A05.yaml
specton/review/perspectives/A06.yaml
specton/review/perspectives/A07.yaml
specton/review/perspectives/A08.yaml
specton/review/reviewer.py
specton/review/rework.py
specton/review/rule_policy.py
specton/review/standard_compliance.py
specton/rtm_node.py
specton/runner.py
specton/type_limits.py
specton/validate/__init__.py
specton/validate/allowed_sql.py
specton/validate/sandbox.py
specton/validation_attempts.py
tests/data/optional_composite_fk.json
tests/e2e/.gitkeep
tests/integration/.gitkeep
tests/integration/conftest.py
tests/integration/dual_pdf_support.py
tests/integration/scripted_llm.py
tests/integration/test_api_runs.py
tests/integration/test_artifact_pipeline.py
tests/integration/test_business_keys_db.py
tests/integration/test_ddl_pipeline.py
tests/integration/test_design_rules_pipeline.py
tests/integration/test_document_pipeline.py
tests/integration/test_dual_pdf_pipeline.py
tests/integration/test_error_detail_pipeline.py
tests/integration/test_evaluation_pipeline.py
tests/integration/test_function_spec_pdf_flow.py
tests/integration/test_ingest_db.py
tests/integration/test_input_block_limit.py
tests/integration/test_lease_race.py
tests/integration/test_lexicon_sources_pipeline.py
tests/integration/test_normalization_pipeline.py
tests/integration/test_optional_composite_fk_db.py
tests/integration/test_pdf_pipeline.py
tests/integration/test_persistence.py
tests/integration/test_runner.py
tests/integration/test_sandbox_db.py
tests/integration/test_scripted_flow.py
tests/integration/test_snapshots.py
tests/integration/test_validation_attempt_checkpoint.py
tests/integration/test_validations.py
tests/llm/test_openai_pilot.py
tests/llm/test_openai_review_comparison.py
tests/unit/data/review_comparison_synthetic.json
tests/unit/data/review_eval_sample.yaml
tests/unit/erd_scale_model.py
tests/unit/test_a01_requirements.py
tests/unit/test_a02_functions.py
tests/unit/test_a03_entities.py
tests/unit/test_a04_relationships.py
tests/unit/test_a09_rework_router.py
tests/unit/test_agent_nodes.py
tests/unit/test_agent_pack_root.py
tests/unit/test_allowed_sql.py
tests/unit/test_api_normalization.py
tests/unit/test_artifacts.py
tests/unit/test_business_keys.py
tests/unit/test_checkpoint_serde.py
tests/unit/test_codegen_naming.py
tests/unit/test_config.py
tests/unit/test_contracts.py
tests/unit/test_contracts_api.py
tests/unit/test_ddl.py
tests/unit/test_ddl_adapter.py
tests/unit/test_ddl_findings.py
tests/unit/test_design_chain.py
tests/unit/test_design_rules.py
tests/unit/test_design_rules_node.py
tests/unit/test_docs_self_contained.py
tests/unit/test_document_node.py
tests/unit/test_erd.py
tests/unit/test_erd_areas.py
tests/unit/test_erd_areas_pack.py
tests/unit/test_erd_node.py
tests/unit/test_eval_a08.py
tests/unit/test_eval_fixtures.py
tests/unit/test_evaluation_observations.py
tests/unit/test_evaluation_permitted.py
tests/unit/test_evaluation_pipeline_context.py
tests/unit/test_evaluation_preparation.py
tests/unit/test_evaluation_scoring.py
tests/unit/test_extraction_check.py
tests/unit/test_fingerprint.py
tests/unit/test_fixture_audit.py
tests/unit/test_function_spec.py
tests/unit/test_function_spec_pdf.py
tests/unit/test_graph.py
tests/unit/test_hangul_engine_lazy_import.py
tests/unit/test_hangul_input.py
tests/unit/test_health.py
tests/unit/test_ids.py
tests/unit/test_ingest_hangul.py
tests/unit/test_ingest_tabular.py
tests/unit/test_inventory_words.py
tests/unit/test_lexicon_overlay.py
tests/unit/test_lexicon_sources.py
tests/unit/test_llm_client.py
tests/unit/test_node_common.py
tests/unit/test_normalization_findings.py
tests/unit/test_normalization_node.py
tests/unit/test_normalization_routing.py
tests/unit/test_normalize.py
tests/unit/test_normalize_graph.py
tests/unit/test_normalize_step.py
tests/unit/test_openai_transport.py
tests/unit/test_optional_composite_fk.py
tests/unit/test_pack_build.py
tests/unit/test_pack_examples.py
tests/unit/test_pack_loader.py
tests/unit/test_pack_provenance.py
tests/unit/test_pack_selection.py
tests/unit/test_pack_term_names.py
tests/unit/test_pack_yaml_safety.py
tests/unit/test_parse_node.py
tests/unit/test_pdf_adapter.py
tests/unit/test_pdf_engine.py
tests/unit/test_pdf_scale.py
tests/unit/test_pilot.py
tests/unit/test_required_reference_cycles.py
tests/unit/test_requirements_answer.py
tests/unit/test_requirements_check.py
tests/unit/test_review_a05.py
tests/unit/test_review_a06.py
tests/unit/test_review_a07.py
tests/unit/test_review_a08.py
tests/unit/test_review_comparison.py
tests/unit/test_review_merge.py
tests/unit/test_review_nodes.py
tests/unit/test_review_normalized_input.py
tests/unit/test_review_perspective.py
tests/unit/test_reviewer.py
tests/unit/test_rework.py
tests/unit/test_rtm.py
tests/unit/test_rule_policy.py
tests/unit/test_rules_config.py
tests/unit/test_run_budget.py
tests/unit/test_run_notes.py
tests/unit/test_run_transitions.py
tests/unit/test_sandbox.py
tests/unit/test_schema_contracts.py
tests/unit/test_session.py
tests/unit/test_standard_compliance.py
tests/unit/test_uploads.py
tests/unit/test_validation_attempts.py
tests/unit/test_validation_contract.py
uv.lock
```
