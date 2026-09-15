# Google AI Pro 코더 PRD

## 1. 목적

승인된 작업 PRD를 바탕으로 Gemini 기반 코딩 도구가 저장소를 분석하고, 제한된 범위에서 코드 수정과 테스트 보조를 수행하도록 정의한다.

실행 도구는 **Antigravity CLI**로 한정한다. Gemini SDK, Google AI API, Vertex AI API는 이 PRD 범위에서 사용하지 않는다.

## 2. 책임 범위

| 담당 | 내용 |
| --- | --- |
| 입력 | 승인된 Markdown PRD와 현재 저장소 상태 |
| 분석 | 요구사항 관련 코드·테스트·설정 확인 |
| 구현 | PRD에 명시된 허용 파일·모듈만 수정 |
| 검증 | PRD에 선언된 테스트와 정적 검사 수행 |
| 출력 | 코드 변경, 실행 요약, 실패 사유 |

## 3. 선행 조건

- 사용자가 Google AI Pro 계정으로 Antigravity CLI 로그인을 직접 완료했다.
- CLI 버전과 비대화형 실행 옵션은 설치 환경에서 확인됐다.
- 현재 저장소 worktree에 작업과 무관한 변경이 없다.
- 작업 PRD의 `status`가 `approved`이고 `risk`가 `low`다.
- PRD에 저장소 경로, 브랜치, 수정 범위, 테스트, 완료 조건이 적혀 있다.

## 4. 입력 계약

코더는 다음 조건이 모두 충족된 PRD만 받는다.

```yaml
status: approved
risk: low
allow_commit: false
allow_push: false
allow_db_change: false
allow_network: false
```

PRD 본문에는 아래 내용이 있어야 한다.

- 문제와 목표
- 수정 가능·수정 금지 범위
- 구현 지시
- 테스트와 수동 확인 방법
- 완료 조건

## 5. 표준 실행 지시

```text
승인된 PRD의 수정 범위 안에서만 작업한다.
수정 전 관련 코드와 기존 테스트를 읽는다.
가장 작은 수정으로 요구사항을 충족한다.
API 키, 비밀값, 인증 파일, 배포 설정, DB 스키마는 생성하거나 수정하지 않는다.
git commit, push, 배포, 패키지 전역 설치를 하지 않는다.
불확실하거나 범위를 벗어난 요구는 변경하지 않고 BLOCKED 사유를 남긴다.
구현 뒤 PRD의 테스트를 실행하고 변경 파일·테스트 결과·남은 위험을 요약한다.
```

## 6. 금지 사항

- `GEMINI_API_KEY`, `GOOGLE_API_KEY` 또는 다른 API 키를 요구·생성·주입하지 않는다.
- SDK/API fallback을 사용하지 않는다.
- OAuth 로그인·동의·결제·초과 과금 설정을 자동으로 처리하지 않는다.
- git commit/push, 배포, DB 변경, 권한 변경을 수행하지 않는다.
- PRD 범위 밖 파일을 수정하지 않는다.

## 7. 상태와 종료 기준

| 상태 | 조건 | 결과 |
| --- | --- | --- |
| `CODE_CHANGED` | 허용 범위 내 구현 완료 | 변경 파일과 요약 반환 |
| `TEST_PASSED` | 선언된 테스트 성공 | 검토 대기 가능 |
| `TEST_FAILED` | 테스트 실패 | 실패 로그와 재현 방법 반환 |
| `BLOCKED` | 요구사항 모호·범위 이탈 | 코드 변경 없이 사유 반환 |
| `AUTH_REQUIRED` | 로그인 세션 없음·만료 | 사용자 수동 로그인 필요 |
| `QUOTA_BLOCKED` | AI Pro 사용량 한도 도달 | 사용량 회복 뒤 신규 실행 |

완료 상태는 반드시 `READY_FOR_REVIEW`이며, 사람이 diff와 테스트 로그를 확인하기 전에는 완료·배포로 처리하지 않는다.

## 8. 검수 기준

- 변경 파일이 PRD의 허용 범위에만 있다.
- 테스트 결과가 남아 있다.
- 비밀값·API 키·인증 파일이 출력물과 diff에 없다.
- 자동 commit/push/deploy가 발생하지 않았다.
- 실패 시 코드 수정 여부와 막힌 이유가 분명하다.

## 9. 자동화 권한 승인 (`--dangerously-skip-permissions`) 정의 및 사용 범위

### 정의
`--dangerously-skip-permissions`는 Antigravity CLI가 파일 읽기/쓰기, 명령어 실행 등 도구(Tool)를 사용할 때 발생하는 대화형 사용자 승인 프롬프트를 묻지 않고 모두 자동으로 통과(Auto-approve)시키는 CLI 플래그다. 완전한 자동화(Headless) 환경을 위해 필수적이나, AI의 의도치 않은 파괴적 행위를 막을 수단이 해제되므로 위험성이 높다.

### 사용 범위 및 안전 통제
이 플래그는 사람의 개입을 차단하므로 **매우 엄격한 조건하에 하네스 데몬 내부의 어댑터에서만 제한적으로 사용**한다.

1. **단일 진입점 제한**: 일반 사용자의 수동 CLI 실행 시에는 절대 사용하지 않으며, 오직 `scripts/agy_executor.py` 래퍼 스크립트를 통한 데몬의 비대화형(non-interactive) 실행 시에만 제한적으로 주입한다.
2. **사전 검증(Pre-validation) 의존**: 하네스 코어(`core.py`)가 PRD의 `status: approved`, `risk: low`, 깨끗한 작업 트리(worktree), API 키 비노출 등의 사전 조건을 완벽히 통과시킨 상태에서만 이 플래그가 동반된 실행을 허용한다.
3. **사후 검증(Post-validation) 의존**: 이 플래그로 인해 AI가 `allowed_paths` 범위를 벗어난 파일을 임의로 수정하더라도, 데몬의 사후 diff 검사 로직에 의해 차단(`BLOCKED`)되므로 치명적인 시스템 변경을 막을 수 있다.
4. **자동 반영 금지**: 플래그를 사용해 실행이 성공하더라도 결과는 항상 `READY_FOR_REVIEW` 상태에 머물며, 사람의 최종 확인(diff 검토) 전에는 어떠한 자동 commit, push, 네트워크 배포도 발생하지 않는다.
