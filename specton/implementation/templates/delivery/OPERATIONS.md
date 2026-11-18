# 고객 앱 설치·계정·운영 인수

이 묶음은 승인 실행 명세에서 생성한 기본 앱이다. `design/revised/`가 실행 설계이고 `design/`은 승인 원본이다. 실행 명세의 미검증 업무·제외 범위를 먼저 확인한다. 생성기는 도메인의 테이블·관계·역할을 사용하며 별도 주문·설비 기본 테이블로 대체하지 않는다.

## 설치

Python 3.12 이상, Node 22 이상, PostgreSQL 18을 준비한다. 플랫폼 DB와 분리된 **빈 전용 DB와 비관리자 소유 계정**을 사용한다. 계정에는 해당 DB의 스키마 생성·테이블 생성 권한만 부여하며 다른 DB·슈퍼유저·역할 생성 권한은 주지 않는다. DB 연결 문자열·비밀번호를 Git 또는 이 납품 ZIP에 저장하지 않는다.

1. 내려받은 ZIP의 SHA-256을 Specton의 소스 해시와 독립적으로 비교한 뒤 압축을 해제한다.
2. `python verify_delivery.py`로 개별 파일 해시를 확인한다. 내부 manifest 확인만으로 출처의 진위를 증명하지 않는다.
3. `.env.example`을 참고해 별도 비밀 환경 파일(권한 600)을 준비한다. 자동으로 읽지 않으므로 쉘·실행 관리자의 환경에 명시적으로 주입한다. 운영은 HTTPS `APP_ORIGIN`과 `APP_COOKIE_SECURE=true`를 사용한다. 로컬 테스트만 `http://localhost:8080`과 `false`를 사용한다.
4. 아래 명령을 실행한다. 초기화는 **빈 DB에서 한 번만** 실행한다. 이미 초기화된 DB에서는 실패하고 트랜잭션을 되돌린다.

```bash
python -m venv .venv
.venv/bin/pip install --require-hashes -r backend/requirements.txt
npm --prefix frontend ci --ignore-scripts --no-audit --no-fund
npm --prefix frontend run build
.venv/bin/python backend/manage.py init-db
.venv/bin/python backend/manage.py roles
# 위 목록에서 실제 역할 ID를 선택한다. 복수 역할은 --role을 반복한다.
.venv/bin/python backend/manage.py set-user operator --role ROLE_FROM_APPROVED_SPEC
# 비밀번호는 화면 입력이며 명령 인수·파일에 남기지 않는다.
.venv/bin/uvicorn serve:app --app-dir backend --host 127.0.0.1 --port 8080 --no-access-log
```

`http://localhost:8080`에서 생성한 고객 계정으로 로그인한다. 개발 시 Vite를 별도로 실행한다면 실제 Vite 주소로 `APP_ORIGIN`을 맞추고 API는 기존 프록시 대상 8000에서 실행한다. Specton Google 로그인·Gmail 계정과 고객 앱 계정은 별개다.

Docker로 설치할 때는 `docker build -t customer-app:reviewed .`로 빌드한다. 같은 이미지에서 `python manage.py init-db`, `python manage.py roles`, `python manage.py set-user ...`를 실행한 뒤 기본 CMD로 서버를 실행한다. 예: `docker run --rm -it --env-file /private/path/customer.env customer-app:reviewed python manage.py set-user operator --role ROLE_FROM_APPROVED_SPEC`. 서버는 `-p 127.0.0.1:8080:8080`으로 로컬에 바인딩한다. 컨테이너에서 접근할 수 있는 DB 주소를 환경 파일에 넣는다. DB를 시작하거나 운영 인터넷에 공개하는 작업은 이 패키지가 자동 수행하지 않는다.

## 고객 계정과 접근

- 기본 비밀번호·공개 회원가입은 없다. 관리자 CLI가 승인 명세의 역할만 부여한다. 같은 `set-user` 명령으로 비밀번호·역할을 바꾸면 이전 세션을 모두 폐기한다.
- `python backend/manage.py disable-user operator`는 계정을 비활성화하고 세션을 폐기한다.
- 비밀번호는 무작위 salt를 사용하는 scrypt 해시로 저장한다. 로그인 세션은 8시간이며 HttpOnly·SameSite=Strict 쿠키를 사용한다. 로그아웃·만료·비활성 계정은 재사용할 수 없다. 변경 요청에는 지정 Origin과 CSRF 토큰을 확인한다.
- 로그인은 직접 연결 IP당 분당 10회로 제한한다. 프록시 뒤에서는 공유 IP 제한이 될 수 있으므로 납품 환경의 신뢰 프록시·접근량 설정을 별도 검토한다. 임의 Forwarded 헤더를 인증 근거로 사용하지 않는다.
- 역할 검사는 API별이다. 행별 테넌트·고객별 접근, 외부 SSO·MFA·셀프 비밀번호 복구는 별도 범위다. 플랫폼 격리 검증·미리보기의 역할 토큰 모드는 고객 로그인과 별개다.
- `_specton_users`, `_specton_sessions`, `_specton_login_attempts`, `_specton_commands`는 인증·요청 재시도용 기술 테이블이다. 승인 업무 ERD에 고객 업무 테이블로 삽입하지 않는다. 기존 업무 데이터 이전 검증기는 인증 테이블을 포함한 운영 DB를 자동 이전하지 않는다.

## 기본 화면 확인

도메인 명세의 화면·필드·API·관계를 따른다. 목록은 기본키 순서로 20행씩 표시하며 검색은 컬럼 값의 대소문자 무시 부분 문자열이다. `%`·`_`도 일반 검색 문자다. 연결 데이터는 조회 권한이 있는 부모 테이블에서 검색·선택한다. 복합 외래키는 한 행의 값 전체를 함께 연결한다. 조회 권한이 없는 테이블을 관계 선택으로 우회해서 읽을 수 없다.

목록의 **수정할 행 선택**으로 전체 값을 불러오며 기존 기본키를 잠근다. 잘못된 형식·필수값·참조·업무 조건은 API에서도 거절한다. 결과 없음·로딩·실패 후 수정 재시도를 확인한다. 검색은 인덱스 최적화된 대용량 검색이 아니며 offset 페이징은 동시 수정 중 일관된 스냅샷을 보장하지 않는다. 기존 전용 재고·주문 데모 화면의 조회 계약은 유지한다. 완성형 시각 디자인 명세는 별도 확장이다.

## 백업·복구와 업데이트

PostgreSQL 18 `pg_dump`·`pg_restore`를 사용한다. 자격 증명은 권한 600의 libpq 서비스 파일에 두고 `PGSERVICE`로 선택한다. 서비스 이름은 운영자가 설정한다. 백업에는 업무 데이터와 비밀번호 해시가 있으므로 접근을 제한한다.

```bash
umask 077
PGSERVICE=customer_source pg_dump --format=custom --no-owner --no-acl --file customer.dump
# 별도 빈 DB에만 복구한다. 복구 전에 init-db를 실행하지 않는다.
PGSERVICE=customer_restore pg_restore --no-owner --no-acl --exit-on-error --single-transaction --dbname service=customer_restore customer.dump
# 복구 후 기존 로그인 세션을 폐기한다.
PGSERVICE=customer_restore psql --set ON_ERROR_STOP=1 --command 'DELETE FROM _specton_sessions; DELETE FROM _specton_login_attempts;'
```

복구된 별도 DB를 환경에 연결해 로그인·행 수·주요 값·권한·수정 동작을 확인한 뒤 운영자가 전환을 결정한다. 실패하면 원본 DB와 이전 앱을 유지한다. 백업 파일만으로 앱 버전이 바뀌지 않으며 소스 SHA·명세 SHA·이미지 ID를 함께 보관한다. 테이블·컬럼·타입 변경이 있는 업데이트는 별도 이전 계약이 필요하다. 새 소스의 init-db를 기존 DB에 실행하지 않는다.

## 납품 인수 기록

실행 OS·DB 버전, 소스/명세/이미지 해시, 역할별 계정, 설치 결과, 로그인·로그아웃·만료·권한 거절, 관계 선택·검색·다음/이전 페이지, 저장·실패 후 재시도, 백업·별도 DB 복구 결과를 기록한다. 이 문서와 소스 생성 자체는 인수 테스트 통과 보고서가 아니다. 실제 검증 보고서는 Specton에서 해당 소스 해시에 연결해 확인한다.
