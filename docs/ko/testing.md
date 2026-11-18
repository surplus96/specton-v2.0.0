# 테스트와 검증 재현

[![한국어](../assets/lang-ko.svg)](../ko/testing.md) [![English](../assets/lang-en.svg)](../en/testing.md)

## 구분해야 하는 결과

| 검증 | 의미 |
|---|---|
| 단위·계약 검사 | 파서·타입·참조·생성 로직의 고정 사례 |
| SQL sandbox | 생성 DDL이 허용 범위에서 실행·롤백되는지 |
| 실행 API 인수 | 승인한 입력·기대 응답의 실제 일치 |
| Chromium 검사 | 생성 UI의 고정 브라우저 시나리오 |
| 격리 미리보기 | 사용자가 합성 데이터로 직접 확인 |
| 고객 업무 인수 | 포함 요구의 실제 업무 조건을 별도 검토 |

앞 단계 통과를 뒤 단계나 원문 전체의 완료로 확대하지 않는다. 기본 구조 검사와 자연어 인수 미실행을 분리한다. 테스트의 skip·실패·미실행도 보고한다.

## 외부 호출 없는 기본 검사

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv run python scripts/check_docs.py
uv run python -m specton.packs.build --check
uv run python -m specton.evaluation.baseline --repeats 1
npm --prefix frontend run lint
npm --prefix frontend run check:api
npm --prefix frontend test
npm --prefix frontend run build
```

기본 pytest는 `db`·`llm`을 제외한다. 일부 native/Docker 검사는 환경 조건에 따라 skip되므로 기본 검사만으로 통합 검증 완료를 주장하지 않는다. CI 기준은 [ci.yml](../../.github/workflows/ci.yml)이다. 문서 링크 검사는 한국어/영문 파일 대응과 저장소 안 링크도 확인한다.

## DB 검사

테스트는 `.env` 대신 환경 변수로 DB 연결을 받는 경로가 있다. 별도 테스트 DB에서 다음 변수를 명시한다. 운영 DB를 지정하지 않는다.

```bash
export SPECTON_APP_DATABASE_URL=postgresql://specton:specton@127.0.0.1:5432/specton_app
export SPECTON_SANDBOX_DATABASE_URL=postgresql://specton_sandbox:specton_sandbox@127.0.0.1:5432/specton_sandbox
uv run python -m specton.persistence.migrate upgrade
uv run pytest --require-db -m 'db and not native_pdf and not llm and not docker_browser'
```

위 비밀번호는 로컬 예제이며 `.env`를 변경했다면 동일하게 맞춘다. `--require-db`는 DB 접속 실패와 필수 DB 검사의 skip을 실패로 처리한다. Docker/PDF 통합은 필요한 이미지·렌더러를 준비한 뒤 선택해 실행한다.

## 생성 앱·피드백 통합 검사 예

```bash
docker build -f docker/implementation/Dockerfile -t specton-generated-runtime:calculation-v1 .
docker build -f docker/browser/Dockerfile -t specton-browser:generated-ui-v1 .
docker pull postgres:18
export SPECTON_TEST_WORKER_RUNTIME="$(docker image inspect specton-generated-runtime:calculation-v1 --format '{{.Id}}')"
export SPECTON_TEST_WORKER_POSTGRES="$(docker image inspect postgres:18 --format '{{.Id}}')"
export SPECTON_TEST_BROWSER_IMAGE="$(docker image inspect specton-browser:generated-ui-v1 --format '{{.Id}}')"
export SPECTON_TEST_FEEDBACK_CONTRACT_DOCKER=1
uv run pytest -m docker_browser tests/integration/test_feedback_contract_docker.py
```

이 검사는 고정된 재고·설비 계약의 계산 변경과 이전 기대값을 유지한 실패 대조군을 실행한다. Google/OpenAI 응답을 합성한 검사는 실제 외부 연동 검사와 구분한다. 납품 앱·플랫폼 브라우저 검사는 해당 테스트의 필수 환경 변수와 생성 ZIP 선행 조건을 확인한다. 테스트별 조건을 무시하고 모든 Docker 검사를 한 명령으로 실행하지 않는다.

## 생성·변경·납품 검사 위치

| 검사 범위 | 테스트 |
|---|---|
| 도메인 구조 생성 | [test_domain_generation.py](../../tests/unit/test_domain_generation.py) |
| 명령 컴파일·원자성 | [test_atomic_command_compilation.py](../../tests/unit/test_atomic_command_compilation.py) |
| 계산·단위·정밀도 계약 | [test_calculation_contract.py](../../tests/unit/test_calculation_contract.py) |
| 명세·설계 일치 | [test_change_consistency.py](../../tests/unit/test_change_consistency.py) |
| Gmail 명령 변경 실행 | [test_feedback_command_runtime.py](../../tests/integration/test_feedback_command_runtime.py) |
| Gmail 계산 변경·실패 대조군 | [test_feedback_contract_docker.py](../../tests/integration/test_feedback_contract_docker.py) |
| 이전 실패 롤백·재시도 | [test_data_transfer.py](../../tests/integration/test_data_transfer.py) |
| 고객 인증·납품 패키지 | [test_customer_delivery_docker.py](../../tests/integration/test_customer_delivery_docker.py) |

실제 브라우저 E2E는 [전체 처리 흐름](workflow.md)에 따라 문서 분석 → 설계 승인 → 명세 승인 → 생성·검증 → 미리보기·채택 → Gmail 수집·변경 승인 → 재생성·재검증·재채택을 수행한다. 재고와 설비는 서로 다른 프로젝트·승인 설계로 진행한다. Google 로그인·Gmail 수신·OpenAI 호출이 실제로 수행된 경로와 합성 응답을 사용한 자동 검사를 결과에 구분한다.

## 실행 인수 사례

사례별로 빈 격리 DB에서 시작한다. 명세의 API ID·역할·입력·요청 키를 사용해 준비 데이터를 넣고 후속 조회로 저장/미저장 결과를 확인한다. 성공 상태·전체 응답 본문, 실패 상태·오류 코드를 비교한다. JSON 타입과 목록 순서도 계약이다. 불일치는 후속 단계 중단으로 기록하며 알 수 없는 API나 다른 소스 결과를 통과 근거로 붙일 수 없다.

## 합성 fixture와 LLM 평가

[기준선 fixture](../../tests/fixtures/baseline/README.md)는 CSV 파싱·정리·네 문서 생성의 결정론 경로를 측정한다. LLM 의미 품질·브라우저·대규모 엔티티 성능을 측정한 것이 아니다. [명세 fixture](../../tests/fixtures/specification/README.md)는 형식 검사용이며 실제 승인 기준을 대신하지 않는다.

실제 모델 테스트는 `uv run pytest -m llm`로 명시 실행한다. 사용 권한이 있는 합성 데이터와 허용된 키를 사용하고 비용·입력·팩·프롬프트·모델·실패 분모를 기록한다. 평가 정답은 모델 입력과 few-shot에서 분리한다. 비공개 고객 원문이나 로컬 시연 결과는 저장소 배포 자료에 넣지 않는다.

새로운 결과를 보고할 때 실행 명령·환경·커밋/콘텐츠 해시와 통과/실패/skip 범위를 함께 기록한다. 과거의 고정 테스트 수를 현재 빌드의 보장으로 사용하지 않는다.

---

[문서 목록](README.md) · [프로젝트](../../README.md)
