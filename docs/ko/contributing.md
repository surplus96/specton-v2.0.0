# 개발 환경과 계약 변경

[![한국어](../assets/lang-ko.svg)](../ko/contributing.md) [![English](../assets/lang-en.svg)](../en/contributing.md)

## 로컬 개발

환경 설치와 서비스 실행은 [설치 안내](getting-started.md), 검사는 [테스트 안내](testing.md)를 따른다. 의존성은 `uv.lock`과 `frontend/package-lock.json`으로 고정한다.

## 변경 대상별 연관 파일

| 변경 | 함께 확인할 대상 |
|---|---|
| API 요청·응답 | Pydantic 모델, 라우트, OpenAPI, 프런트 API 타입과 계약 검사 |
| 플랫폼 DB | 새 Alembic revision, 이전·스키마 검사, 읽기/쓰기 경로 |
| 실행 계약·생성기 | 컴파일러, 런타임·UI 템플릿, 패키지 manifest, 인수·호환 검사 |
| 도메인 팩 | 원본·입력 파일, 버전·출처·lock, 생성 파일과 팩 검사 |
| 화면 | API 상태·오류 처리, 사용자 흐름, Vitest·빌드·브라우저 검사 |
| 개발 문서 | 한국어·영문 대응 문서와 상대 링크 |

기존 승인 자료의 해시와 고정 템플릿은 버전 호환성의 일부다. 실행 계약이 바뀌면 명세·소스·검증 근거를 새 버전으로 연결한다. 업무 용어는 팩, 실행 연산은 계약과 생성기로 관리한다.

## API 타입 갱신

```bash
npm --prefix frontend run gen:api
npm --prefix frontend run check:api
```

`docs/api/openapi.json`을 갱신한 뒤 타입을 생성한다. `frontend/src/api/schema.d.ts`는 직접 편집하지 않는다. 계약 변경 절차는 [API 가이드](api.md)를 따른다.

## 문서 및 변경 검증

```bash
uv run python scripts/check_docs.py
git diff --check
```

`docs/ko/`와 `docs/en/`은 같은 파일명과 기능 범위를 유지한다. 실행 파일·계약이 바뀌면 해당 단위·통합 검사를 추가로 실행한다. 변경 설명에는 동작 변화, 호환성·데이터 영향, 실제 실행한 검사와 결과를 기록한다.

환경 설정은 `.env.example`을 사용하며 실제 키·고객 문서·실행 데이터는 Git 제외 경로에서 관리한다. 설계상 선택과 제약은 [설계 결정](decisions.md)에 정리한다.

---

[문서 목록](README.md) · [프로젝트](../../README.md)
