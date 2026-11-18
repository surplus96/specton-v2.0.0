# 의존성 보안 관리

[![한국어](../assets/lang-ko.svg)](../ko/dependency-security.md) [![English](../assets/lang-en.svg)](../en/dependency-security.md)

## 검토 범위

2026-11-18 기준 플랫폼 웹, API의 ERD 렌더러, 생성 고객 앱의 웹 빌드 도구, 브라우저 검증 작업자를 구분해 검사했다. 감사 결과의 패키지 수에는 같은 권고가 상위 패키지로 전파된 항목이 포함된다. 패키지 수와 서로 다른 취약점 수를 구분한다. 이 검토는 OS 패키지 검사나 침투 테스트를 대신하지 않는다.

## 반영한 보안 갱신

| 대상 | 조치 | 근거 |
|---|---|---|
| 플랫폼 Python | OpenTelemetry API 1.45.2로 고정 | [OpenTelemetry 권고](https://github.com/advisories/GHSA-mf5v-w3w3-f6cg) |
| TypeScript 정적 검사 | typescript-eslint 8.73 계열의 공식 의존성으로 수정된 minimatch 11 계열 사용 | [minimatch 권고](https://github.com/advisories/GHSA-g3hv-75wg-m249) |
| 웹·PDF ERD | Mermaid 12.3.0, CLI 12.2.0, KaTeX 0.18.10을 잠금 파일로 고정 | [KaTeX 권고](https://github.com/advisories/GHSA-238p-pmpm-9mq7) |

Mermaid의 major 버전 변경은 웹 타입 검사·테스트·빌드와 실제 PDF·ERD 렌더링으로 검증한다. 웹과 PDF의 버전을 함께 갱신하며, 제3자 의존성 범위를 강제 override하지 않는다. Node.js 22.13.0 이상을 사용한다.

## 남은 picomatch 권고

[GHSA-fc5q-39xc-vjpf](https://github.com/advisories/GHSA-fc5q-39xc-vjpf)는 4.0.7 이하에서 공격자가 지정한 extglob 패턴으로 과도한 정규식 연산을 유발할 수 있는 High 권고다. 검토 시점에는 공식 수정 버전이 없다. 플랫폼 개발 도구와 생성 고객 앱의 Vite 빌드 의존성에 남아 있으므로 전체 npm 감사가 경고 없이 끝나지는 않는다.

현재 서비스에서는 요구사항 문서·고객 메일·실행 명세를 glob 패턴으로 전달하지 않는다. 플랫폼의 배포 웹은 정적 번들이며 Vite 개발 서버를 제공하지 않는다. 생성 앱은 고정된 프런트엔드 템플릿을 빌드하고, 승인 설계의 설정 데이터는 고정 경로의 `contract.json`으로 포함한다. 검증 작업자는 고정 명령과 제한된 컨테이너 자원으로 실행한다. CI에도 작업 시간 제한을 둔다.

이 경계에서 검토를 완료했으며, 패키지 자체가 수정됐거나 모든 공격 경로가 제거됐다고 판단한 것은 아니다. 사용자 제공 glob, Vite 설정, 플러그인 또는 임의 프런트엔드 소스를 받는 기능을 추가하면 이 판단은 적용되지 않는다. 신뢰하지 않는 저장소의 개발 서버를 운영 서버에서 실행하지 않는다.

담당 유지보수자는 다음 의존성 갱신 또는 2026-12-18 중 먼저 도래하는 시점에 이 권고를 재검토한다. 수정판이 나오면 플랫폼 및 생성 템플릿을 각각 검증한다. 이미 승인된 납품 ZIP의 파일·해시를 소급 변경하지 않으며 템플릿 변경은 새 버전으로 관리한다.

## 재검증

```bash
npm --prefix frontend audit --json
npm --prefix frontend audit --omit=dev --audit-level=low
npm --prefix specton/implementation/templates/frontend audit --package-lock-only --json
npm --prefix docker/browser audit --package-lock-only --json
docker build --target check .
```

렌더러 감사는 `docker/api/mermaid-package.json`·`mermaid-package-lock.json`을 임시 폴더의 `package.json`·`package-lock.json`으로 복사한 뒤 `npm audit --package-lock-only --omit=dev`로 실행한다. CI는 플랫폼 웹의 운영 의존성과 렌더러 운영 의존성의 보안 권고를 실패로 처리한다. 개발 의존성과 생성 템플릿의 picomatch 예외는 위 범위에만 해당하며, 새로운 권고까지 포괄적으로 허용하지 않는다.

---

[문서 목록](README.md) · [프로젝트](../../README.md)
