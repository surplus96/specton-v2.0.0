# 실행 명세 형식 예제

[![한국어](../../../docs/assets/lang-ko.svg)](README.md) [![English](../../../docs/assets/lang-en.svg)](README.en.md)

`item-create-v0.1.json`은 품목 등록·수량 제약을 설명하는 합성 **초기 형식** 예제다. baseline UUID와 해시는 검사용 값이며 실제 프로젝트나 승인을 가리키지 않는다. 이 파일로 실제 생성·승인을 실행할 수 없다.

```bash
uv run python -m specton.specification tests/fixtures/specification/item-create-v0.1.json
```

성공 시 `ready_for_review: true`와 명세 해시를 반환한다. 미해결 질문이나 필수 추적 누락은 종료 코드 1, 파일/계약 오류는 2다. 구문·참조 검사가 현재 생성기의 모든 기능 지원 또는 실행 인수를 뜻하지 않는다.

현재 도메인·명령·계산·실행 인수 계약은 [SDD 개발 문서](../../../docs/ko/sdd.md)와 `tests/domain_support.py`, `tests/command_support.py`, `tests/calculation_support.py`의 별도 합성 fixture를 따른다. 초기 예제를 최신 승인 명세인 것처럼 덮어쓰지 않는다.
