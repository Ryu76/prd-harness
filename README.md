# PRD Harness

승인된 저위험 PRD를 하나씩 처리하고, 실행 상태·diff·테스트 기록을 보관하는 **로컬 제어 하네스**입니다.

이 프로젝트는 특정 AI 공급자, SDK, API 키, 인증 자동화, 결제 설정을 포함하지 않습니다. 기본값은 executor 미구성이며, 승인 PRD도 코드 변경 없이 `BLOCKED`로 종료합니다. 실제 executor 연결은 사용자가 별도 검토·승인해야 합니다.

## 보장하는 경계

- `.harness/approved/`로 이동한 PRD만 실행 대상으로 인식
- `draft`/`inbox` PRD는 실행하지 않음
- `risk: low`, 모든 `allow_*: false`, allowlisted 저장소·브랜치·깨끗한 worktree만 통과
- PRD마다 `allowed_paths`를 검사하고, 실행 후 범위 밖 diff는 `BLOCKED`
- 자동 commit, push, deploy, DB 변경, 네트워크 허용 없음
- 작업당 최대 30분, 단일 파일 잠금, 중복 ID+내용 해시 차단
- 중단·재시작 뒤 `running/` PRD는 `INTERRUPTED`; 자동 재개하지 않음
- 결과는 `runs/<job-id>/result.json`, `diff.patch`, `test.log`에 보관
- 상태 조회와 중단은 CLI로만 제공하며, Hermes는 이 명령을 읽기/중단 관제로만 사용

> OS 파일 권한은 별도 운영 통제입니다. 실제 executor를 연결할 때는 전용 로컬 계정과 allowlisted 저장소 외 쓰기 권한 제거가 필요합니다.

## 초기화

```bash
cd /e/python/prd-harness
python -m prd_harness --root /e/work/myrepo/.harness --allowed-repo /e/work/myrepo init
```

## 승인 흐름

```text
inbox/ PRD 작성
  → 사람 검토
  → approved/로 이동
  → daemon 또는 run-once
  → running/
  → done/ (READY_FOR_REVIEW) 또는 failed/
```

`templates/PRD_TEMPLATE.md`와 `templates/REVIEW_CHECKLIST.md`를 사용합니다. `approved/` 이동은 승인 행위이며 Hermes 메시지나 파일 내용만으로 승인 상태가 바뀌지 않습니다.

## 상태·중단 관제

```bash
# 작업 목록 또는 한 작업의 축약 상태
python -m prd_harness --root /e/work/myrepo/.harness status
python -m prd_harness --root /e/work/myrepo/.harness status --job-id project-20260914-001

# 현재 RUNNING 작업 하나에만 중단 요청
python -m prd_harness --root /e/work/myrepo/.harness stop project-20260914-001
```

출력은 `job_id`, 상태, 변경 파일, 테스트 종료 코드, 다음 조치만 포함합니다. 로그·인증 정보·환경 변수 원문은 관제 응답에 포함하지 않습니다.

## 단발 실행과 데몬

```bash
# approved/의 첫 PRD 한 건만 처리
python -m prd_harness \
  --root /e/work/myrepo/.harness \
  --allowed-repo /e/work/myrepo \
  run-once

# 30초 polling. 실제 운영은 OS 서비스 관리자로 한 인스턴스만 기동.
python -m prd_harness \
  --root /e/work/myrepo/.harness \
  --allowed-repo /e/work/myrepo \
  daemon
```

현재 호스트가 Windows이므로 systemd user service 대신 작업 스케줄러 또는 사용자 세션의 서비스 관리자를 사용해야 합니다. `scripts/run-daemon.cmd`는 수동 시작용 예시이며, 자동 등록을 수행하지 않습니다.

## AI Pro (Antigravity CLI) 연동

Google AI Pro 코더(Antigravity CLI)를 executor로 사용하려면 래퍼 스크립트를 지정합니다. 모든 AI Pro 작업에는 [`docs/AI_PRO_GLOBAL_WORK_POLICY.md`](docs/AI_PRO_GLOBAL_WORK_POLICY.md)가 executor prompt로 주입됩니다. 이 정책은 PRD 범위 안 파일 수정과 프로젝트 범위 의존성 설치를 기본 승인하고, 추가 권한은 `PERMISSION_REQUIRED`로 사용자에게 재요청하도록 정합니다. GitHub 업로드가 PRD에서 명시적으로 승인된 경우 기존 프로젝트는 `ai-pro/<job-id>` 새 브랜치를, 신규 프로젝트는 검증 뒤 private 저장소를 사용합니다.

```bash
python -m prd_harness \
  --root /e/work/myrepo/.harness \
  --allowed-repo /e/work/myrepo \
  --executor "python scripts/agy_executor.py" \
  run-once
```

`agy_executor.py`는 PRD 프롬프트를 `agy` 비대화형 모드로 실행하며, 인증 만료나 사용량 한도 초과 시 `AUTH_REQUIRED`, `QUOTA_BLOCKED` 상태로 자동 매핑합니다.

## 검증

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python -m compileall -q src tests
```
