# 기능 명세와 구현 추적

[![한국어](../assets/lang-ko.svg)](../ko/requirements.md) [![English](../assets/lang-en.svg)](../en/requirements.md)

이 표의 `REQ-01`~`REQ-27`은 플랫폼 기능의 참조 번호이며 고객 문서에서 생성하는 실행별 요구 ID와 다르다. 현재 구현 위치와 범위를 정리하며 이 목록 자체를 전체 인수 통과 보고서로 사용하지 않는다.

| ID | 기능 | 계약/범위 | 구현 |
|---|---|---|---|
| REQ-01 | Excel·CSV 표 입력 | 원문 ID·열·시트·행 보존 | [코드](../../specton/ingest/) |
| REQ-02 | PDF 입력·OCR | 미지원; 업로드 거절 | [코드](../../specton/ingest/) |
| REQ-03 | 도메인 팩 선택 | 승인·형식·해시 검사 | [코드](../../specton/packs/) |
| REQ-04 | 요구사항 분석 | FR/NFR·분할·확인 질문 | [코드](../../specton/nodes/a01_requirements.py) |
| REQ-05 | 사용자 확인 | 유지·수정·분할과 revision 재개 | [코드](../../specton/graph.py) |
| REQ-06 | 기능 도출 | 요구 추적·우선순위 근거 | [코드](../../specton/nodes/) |
| REQ-07 | 엔티티·속성·CRUD | 유효 참조와 원문 근거 | [코드](../../specton/nodes/a03_entities.py) |
| REQ-08 | 관계 설계 | 방향·카디널리티·선택 여부 | [코드](../../specton/nodes/) |
| REQ-09 | 모델 정리 | ID·명명·N:M·FK를 코드로 파생 | [코드](../../specton/codegen/) |
| REQ-10 | ERD | 고정 모델의 Mermaid 출력 | [코드](../../specton/codegen/) |
| REQ-11 | DDL | 파싱·허용 문법·격리 실행·롤백 | [코드](../../specton/validate/) |
| REQ-12 | RTM | 요구-기능-엔티티/관계 조인 | [코드](../../specton/codegen/rtm.py) |
| REQ-13 | 규칙 검사 | 참조·명명·키·CRUD·DDL | [코드](../../specton/review/) |
| REQ-14 | 관점 검토 | A05~A08, combined/parallel 선택 | [코드](../../specton/review/) |
| REQ-15 | 지적 검증·병합 | 대상·인용 검증, 중복 지문 | [코드](../../specton/review/) |
| REQ-16 | 재작업 | 결정론 라우팅·조건부 A09·상한 | [코드](../../specton/graph.py) |
| REQ-17 | 최종 승인 | 차단 지적·SQL 결과·승인 근거 | [코드](../../specton/api/) |
| REQ-18 | 내보내기 | 네 산출물과 선택적 PDF | [코드](../../specton/export/) |
| REQ-19 | 웹 UI | 진행·검토·결과·Workspace | [코드](../../specton/api/) |
| REQ-20 | 이력·재개 | 체크포인트·lease·버전 보존 | [코드](../../specton/persistence/) |
| REQ-21 | 추적 무결성 | 실재하는 요구 ID와 출처 | [코드](../../specton/contracts/) |
| REQ-22 | 출력·오류 통제 | 구조화 검증·한정 재시도 | [코드](../../specton/llm/) |
| REQ-23 | 보호 경계 | 소유권·비밀·파일·SQL 범위 | [코드](../../specton/api/) |
| REQ-24 | 재현성 | 입력·팩·모델·코드·보고서 해시 | [코드](../../specton/evaluation/) |
| REQ-25 | 자원·취소 | 업로드·원문 수·시간·토큰 한도 | [코드](../../specton/runner.py) |
| REQ-26 | 팩/코드 분리 | 도메인 공통 파이프라인 | [코드](../../specton/packs/) |
| REQ-27 | HWP/HWPX | 지원 요구사항 표와 원문 위치 | [코드](../../specton/ingest/) |

## 명세 기반 생성·검증·고객 변경

| ID | 내용 | 기준 문서 |
|---|---|---|
| SDD-01 | 소유 프로젝트와 실제 승인 설계 연결 | [아키텍처](architecture.md) |
| SDD-02 | 실행 명세 작성·질문·포함/유예·승인 | [SDD](sdd.md) |
| SDD-03 | 도메인 계약 기반 DB·API·기본 UI·고객 계정 | [SDD](sdd.md) |
| SDD-04 | 실제 API 인수·브라우저·격리 미리보기 | [테스트](testing.md) |
| SDD-05 | 비교 해시·검증 근거를 확인한 후보 채택 | [API](api.md) |
| FB-01 | 별도 Gmail 동의·읽기 수집·중복 억제 | [Gmail](gmail-feedback.md) |
| FB-02 | 원문 인용·영향 분석·승인 변경·재검증 | [Gmail](gmail-feedback.md) |
| OPS-01 | 납품 ZIP·별도 고객 로그인·백업/복구 | [납품](deployment.md) |

### 실행 엔진과 납품 기능의 구현 근거

아래 경로는 구현과 재현 가능한 검사 위치를 연결한다. 검사 파일의 존재가 현재 환경에서의 통과를 뜻하지는 않는다.

| ID | 기능 | 구현 | 검사 |
|---|---|---|---|
| SDD-06 | 범용 다중 레코드 명령·전체 롤백·멱등성 | [Code](../../specton/implementation/commands.py) | [Test](../../tests/integration/test_atomic_commands.py) |
| SDD-07 | 단위·정밀도 정책을 가진 계산·집계 | [Code](../../specton/implementation/calculations.py) | [Test](../../tests/unit/test_calculation_contract.py) |
| SDD-08 | 요구별 실행 인수·미실행 결과 분리 | [Code](../../specton/implementation/requirement_results.py) | [Test](../../tests/unit/test_requirement_results.py) |
| SDD-09 | 기능·ERD·DDL·RTM 재생성과 명세 일치 | [Code](../../specton/specification/documents.py) | [Test](../../tests/unit/test_change_consistency.py) |
| SDD-10 | 명세·업무 계약·납품 준비도 검사 | [Code](../../specton/specification/handoff.py) | [Test](../../tests/unit/test_handoff_readiness.py) |
| FB-03 | Gmail의 기존 명령·계산 정책 변경 | [Code](../../specton/feedback/contracts.py) | [Test](../../tests/integration/test_feedback_calculations.py) |
| OPS-02 | 동일 구조 데이터 이전·중간 실패 롤백 | [Code](../../specton/implementation/data_transfer.py) | [Test](../../tests/integration/test_data_transfer.py) |
| OPS-03 | 고객 로그인·계정·납품 패키지 검사 | [Code](../../specton/implementation/delivery.py) | [Test](../../tests/integration/test_customer_delivery.py) |

## 공통 수용 조건

원문 누락·추출 실패·리뷰 실패를 정상으로 바꾸지 않는다. 원문에 없는 우선순위·업무 규칙을 확정하지 않는다. 오래된 답변·승인 해시를 거절하며 승인한 파일을 같은 버전에서 재현한다. 기술 검증과 업무 인수를 구분하고, 미지원 요구의 유예 사유를 남긴다. 기능별 실제 검사는 `tests/unit/`, `tests/integration/`, `tests/browser/`와 [테스트 안내](testing.md)를 따른다.

---

[문서 목록](README.md) · [프로젝트](../../README.md)
