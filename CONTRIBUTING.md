# 개인 개발 규칙

이 저장소는 Specton의 개인 유지보수와 확장을 위한 독립 저장소다. 작업의 근거, 변경 범위, 검증 결과를 저장소 안에 기록한다.

## 작업 흐름

1. 요구사항과 완료 조건을 정하고 관련 문서·테스트를 연결한다. 원격 이슈는 원격 저장소를 연결한 뒤 선택적으로 사용한다.
2. `feat/<요약>`, `fix/<요약>`, `docs/<요약>` 같은 짧은 작업 브랜치를 만든다.
3. 변경 내용을 검토하고 필요한 품질 검사를 실행한다. 계약 변경에는 호환성·데이터 이전·영향 범위를 기록한다.
4. 실행한 검사와 미실행 검사를 구분해 커밋 또는 PR에 남긴다. 기본 브랜치 반영 전 diff를 확인한다.

GitHub의 리뷰 승인 수·보호 규칙·자동 병합은 원격 저장소를 만들 때 별도로 설정한다. 로컬 문서만으로 원격 설정이 적용되지는 않는다.

## 설계 기준

- LLM은 해석·판단을 수행한다. ID·SQL·Mermaid·RTM 조인은 코드가 생성한다.
- `codegen/`·`validate/`는 LLM client를 import하지 않는다.
- 도메인 값은 `domain_packs/`에서 읽는다. `GENERATED` 파일은 입력을 수정한 뒤 재생성한다.
- 계약 변경 시 `docs/05-data-contracts.md`, `docs/06-api.md`, OpenAPI와 프런트 타입의 영향을 함께 확인한다.
- 원문·평가 정답·키·토큰·실행 산출물은 커밋하지 않는다. 라이선스와 외부 데이터 출처 고지는 보존한다.
- 테스트 기대값이나 평가 정답을 수정할 때는 구현과 독립된 근거를 기록한다.

## 검증 명령

```text
이슈 배정 → 브랜치 → 커밋·push → PR (Closes #이슈) → CI 통과 + 리뷰 승인 → 병합 담당자가 Squash 병합 → 이슈 자동 종료
보드:  Backlog → Todo → In Progress → In Review(자동) → Done(자동)
```

프런트 변경 시 `frontend/`에서 실행한다.

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest
uv run python -m specton.packs.build --check
cd frontend && npm run lint && npm run build   # frontend를 바꾼 경우
```

DB 검사는 격리 환경에서 `uv run pytest -m db`로 실행한다. 실제 LLM 검사는 호출 범위와 비용 한도를 정한 뒤 `uv run pytest -m llm`로 별도 실행한다. 기본 pytest는 두 마커를 제외한다. 현재 CI의 실행 항목은 `.github/workflows/ci.yml`을 기준으로 확인한다.

## 변경 점검

| 영역 | 확인 사항 |
|---|---|
| 범위 | 요청한 결과·수용 기준과 일치하는가 |
| 계약 | 기존 입력·저장 상태·API와의 호환성 및 이전 경로가 있는가 |
| 오류 | 실패·미실행을 성공이나 빈 결과로 표시하지 않는가 |
| 검증 | 정상·오류·경계에 필요한 검사와 실제 결과가 있는가 |
| 데이터 | 모델·팩·산출물·승인 해시가 같은 버전을 가리키는가 |
| 보안 | 비밀값·원문 노출, 파일 경로 이탈, SQL 실행 범위를 확인했는가 |
| 문서 | 변경 이유와 실행 가능한 사용법이 저장소 안에 있는가 |

설계 결정은 [ADR](docs/adr/README.md)에, 실행 순서와 의존성은 [개발 운영](docs/08-roles.md)에 기록한다.
