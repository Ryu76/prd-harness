# Harness Daemon PRD

## 1. 목적

승인된 PRD 파일을 감지하고, 사전 검증 후 코딩 CLI를 **한 번에 하나씩** 실행하며, 로그·상태·diff·테스트 결과를 보관하는 로컬 데몬을 정의한다.

데몬은 판단·설계·결제를 하지 않는다. PRD 집행과 안전 통제만 담당한다.

## 2. 관리 경로

```text
.harness/
├─ inbox/       # 작성 중. 실행하지 않음
├─ approved/    # 실행 승인된 PRD
├─ running/     # 실행 중 PRD
├─ done/        # 검토 대기 PRD
├─ failed/      # 차단·실패 PRD
├─ runs/<job-id>/
│  ├─ input.md
│  ├─ prompt.md
│  ├─ stdout.log
│  ├─ stderr.log
│  ├─ test.log
│  ├─ diff.patch
│  └─ result.json
└─ state/
   ├─ capabilities.json
   ├─ jobs.json
   └─ lock.json
```

`approved/`로의 이동만 실행 승인으로 인정한다. `inbox/`의 파일은 절대 실행하지 않는다.

## 3. 기능 요구사항

### 3.1 PRD 감지와 잠금

- 30~60초 polling으로 `approved/`를 확인한다.
- OS 수준 파일 잠금과 `lock.json`으로 동시 실행을 막는다.
- 발견한 PRD는 `running/`으로 원자적 이동한 뒤 처리한다.
- 같은 PRD ID와 내용 해시를 중복 실행하지 않는다.
- 데몬 재시작 뒤 `running/`에 남은 작업은 `INTERRUPTED`로 기록하고 자동 재개하지 않는다.

### 3.2 사전 검증

- PRD 형식, 고유 ID, 승인 상태, 허용 저장소 경로를 확인한다.
- 현재 branch가 PRD의 branch와 같은지 확인한다. 자동 checkout은 하지 않는다.
- worktree가 깨끗한지 확인한다.
- `allow_commit`, `allow_push`, `allow_db_change`, `allow_network`가 모두 `false`인지 확인한다.
- `risk: low`만 자동 실행한다.
- 코드 CLI의 로그인 가능 상태와 실행 옵션을 확인한다.

### 3.3 실행과 결과 보관

1. PRD 원문과 정규화 프롬프트를 run 폴더에 저장한다.
2. 확인된 CLI 옵션으로 코딩 작업을 한 번 실행한다.
3. 표준 출력·오류 출력·종료 코드를 저장한다.
4. 변경 파일과 `git diff --binary`를 저장한다.
5. 선언된 테스트 allowlist만 실행하고 결과를 저장한다.
6. `result.json`을 작성하고 PRD를 `done/` 또는 `failed/`로 이동한다.

## 4. 과금·인증 차단

- API 키 환경 변수나 API 키 파일을 발견하면 값을 노출하지 않고 중단한다.
- `OPENAI_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`를 사용하지 않는다.
- CLI 로그인 세션 외의 인증 경로는 허용하지 않는다.
- 초과 과금 방지 설정을 확인할 수 없거나 quota 소진을 감지하면 `QUOTA_BLOCKED`로 종료한다.
- 인증 만료는 `AUTH_REQUIRED`로 종료하며, 자동 로그인·재시도하지 않는다.

## 5. 상태 모델

| 상태 | 의미 |
| --- | --- |
| `QUEUED` | 승인 PRD를 감지함 |
| `RUNNING` | CLI 또는 테스트 실행 중 |
| `READY_FOR_REVIEW` | diff와 테스트 결과 생성됨 |
| `TEST_FAILED` | 테스트가 실패함 |
| `BLOCKED` | PRD·환경·범위 조건 미충족 |
| `AUTH_REQUIRED` | 사용자 로그인 필요 |
| `QUOTA_BLOCKED` | 사용량 한도 도달 |
| `INTERRUPTED` | 데몬/PC 중단으로 작업 종료 |

## 6. 비기능 요구사항

- 작업당 최대 실행 시간은 30분으로 제한한다.
- CLI·테스트의 자동 재시도는 하지 않는다. 일시적 실행 오류만 최대 1회 재시도할 수 있다.
- 비밀값, 토큰, 쿠키, `.env` 내용은 로그에 기록하지 않는다.
- 데몬 계정은 허용 프로젝트 경로 외에는 쓰기 권한을 갖지 않는다.
- 실행 결과는 사람이 검토하기 전 자동 commit/push/deploy로 넘어가지 않는다.

## 7. 완료 기준

- 정상 PRD 한 건이 정확히 한 번만 처리된다.
- 차단 조건에서는 코드 변경 없이 실패 사유가 남는다.
- 정상 작업에는 입력·로그·diff·테스트·상태 파일이 남는다.
- 비정상 종료 뒤 중복 실행이나 자동 재개가 일어나지 않는다.
