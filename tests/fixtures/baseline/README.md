# 결정론 기준 입력 v1

[![한국어](../../../docs/assets/lang-ko.svg)](README.md) [![English](../../../docs/assets/lang-en.svg)](README.en.md)

`inventory-v1.json`은 고객 원문을 사용하지 않은 합성 입력이다. 창고·품목·입고의 문장 세 개를 순환하며 SYN 원문 ID를 붙여 20·200·1,000개 CSV 블록을 만든다. 데이터 모델은 창고·품목·입고·입고내역 네 표와 FK 세 개로 고정한다.

측정 경로는 실제 CSV 파서 → 고정 설계 데이터 구성 → 실제 팩 기반 정리 → 기능 명세·ERD·DDL·RTM CSV/XLSX 생성이다. LLM 해석, DB 실행, PDF, API 부하, 브라우저, 생성 업무 앱 테스트는 포함하지 않는다. 큰 입력도 표 수는 네 개이므로 1,000개 엔티티 모델의 성능으로 해석하지 않는다.

`expected-v1.json`은 첫 기준 출력의 파일 바이트·모델·팩 해시와 추적 수다. 기존 생성 로직을 변경하지 않은 상태에서 만들었으며, 독립적인 정답 조건으로 표 4개·FK 3개·모든 원문 추적 연결을 검사했다. CI는 이 값을 다시 작성하지 않고 비교만 한다. 출력 계약을 의도적으로 바꿀 때는 새 fixture 버전과 독립적인 변경 근거를 추가한다.

```bash
uv run python -m specton.evaluation.baseline --repeats 30
uv run python -m specton.evaluation.baseline --repeats 1 --sizes 20
```

워밍업 1회 뒤 지정 횟수를 측정하며 `var/baseline/report.json`에 p50·p95·최대 시간, 프로세스 전체 peak RSS, 입력·코드 트리·잠금 파일 해시를 남긴다. peak RSS는 케이스별 증가량이 아니다. 실행 실패와 해시 차이는 종료 코드 1로 반환하고 기대값을 자동 갱신하지 않는다. 명령은 저장소 루트에서 실행한다.
