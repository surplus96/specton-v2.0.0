# 프런트엔드 개발

[![한국어](../assets/lang-ko.svg)](../ko/frontend.md) [![English](../assets/lang-en.svg)](../en/frontend.md)

React 19·TypeScript·Vite, 자체 CSS, React Flow와 Mermaid를 사용한다. 화면은 API만 호출하고 DB·LangGraph를 직접 실행하지 않는다. 기본 색상·간격·타이포그래피는 `frontend/src/index.css`, 공통 요소는 `frontend/src/ui/`, 화면은 `frontend/src/pages/`에서 관리한다.

```bash
npm --prefix frontend ci
npm --prefix frontend run dev
npm --prefix frontend run dev:mock
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run check:api
npm --prefix frontend run build
```

`dev:mock`은 UI 시험용 합성 응답이며 실제 설계·Gmail·생성 앱 검증을 수행한 증거가 아니다. `dev`는 기본 FastAPI 8000을 프록시한다. `VITE_DEV_API_ORIGIN`으로 개발 프록시 대상을 바꿀 수 있다.

## 구현 화면

| 경로 | 기능 | 구현 |
|---|---|---|
| `/projects` | 프로젝트·승인 설계 연결 | [Page](../../frontend/src/pages/ProjectsPage.tsx) |
| `/specifications/:specId` | 명세·업무 계약·인수·소스·검증·미리보기 | [Page](../../frontend/src/pages/SpecificationPage.tsx) |
| `/projects/:projectId/candidates` | 후보 비교·채택 | [Page](../../frontend/src/pages/CandidatesPage.tsx) |
| `/feedback` | Gmail 연결·동기화·메일·변경 요청 | [Page](../../frontend/src/pages/FeedbackPage.tsx) |
| `/changes/:changeId` | 영향 분석·검토·계약 변경·승인·재검증 | [Page](../../frontend/src/pages/ChangePage.tsx) |

고객 앱의 기본 UI는 승인 화면·API·역할 계약에서 구성한다. 플랫폼의 실행 명세·변경 요청 화면과 고객 앱의 업무 화면은 별도 프런트엔드다. 고객 앱은 등록·조회·수정·상태 전이, 관계 선택, 다중 레코드 명령, 계산 결과와 별도 로그인을 제공한다. 시각 디자인 명세 해석은 [지원 범위](roadmap.md) 밖이다.

## 화면과 상태

프로젝트 → 새 문서 작업 → 분석/검토 → 승인 설계 → 실행 명세 → 검증/미리보기 → 후보 채택과 고객 메일 → 변경 요청 흐름을 제공한다. 준비·대기·실행·실패·미검증·통과 상태를 구분하고 API 실패를 성공처럼 숨기지 않는다. 실행 revision과 명세 version을 UI에 유지하며 다른 버전의 결과를 섞지 않는다.

`src/api/client.ts`는 세션 쿠키·CSRF와 오류를 처리하고 OpenAPI 타입은 `src/api/schema.d.ts`에 생성한다. 스키마를 직접 편집하지 않고 루트 OpenAPI를 갱신한 뒤 `gen:api`를 실행한다. HTTP와 SSE 모두 같은 출처 배포가 기본이다. 별도 출처 배포에는 서버 CORS·쿠키 정책이 추가로 필요하다.

생성 고객 앱은 `specton/implementation/templates/frontend/`의 별도 코드다. 플랫폼 UI를 바꾼다고 이미 생성된 고객 앱 ZIP이 변경되지 않는다. 템플릿 변경은 새 패키지·실제 브라우저 검증과 이전 호환성을 확인한다.

Pretendard는 저장소 폰트를 로컬 제공하며 [OFL 고지](../../frontend/public/fonts/OFL.txt)를 보존한다. 한국어·영문 문서 전환은 Markdown 링크이며 제품 UI 전체의 언어 전환 기능을 의미하지 않는다.

---

[문서 목록](README.md) · [프로젝트](../../README.md)
