# Hermes 관제 연동

Hermes는 이 하네스의 executor·승인자·인증 저장소가 아니다. Hermes가 수행할 수 있는 일은 아래 두 가지로 제한한다.

1. `state/jobs.json` 또는 `result.json`을 읽고 요약한다.
2. 명시적으로 요청된 현재 `RUNNING` 작업에 stop 요청을 기록한다.

## 허용된 명령

```bash
python -m prd_harness --root <harness-root> status --job-id <job-id>
python -m prd_harness --root <harness-root> stop <job-id>
```

Hermes 응답에는 다음만 표시한다.

- 작업 ID와 상태
- 변경 파일 목록
- 테스트 명령과 종료 코드
- 결과 경로 및 다음 사람 조치

다음은 표시하거나 처리하지 않는다.

- 환경 변수 원문
- 인증 파일·토큰·쿠키·비밀번호
- `.env` 파일 내용
- 장문의 stdout/stderr 전문
- executor 설정이나 로그인 절차

## 승인 규칙

PRD가 `approved/` 폴더에 사용자가 직접 이동한 경우만 실행 후보가 된다. Hermes는 PRD 상태를 승인으로 바꾸거나, `approved/`로 옮기거나, 실행을 자동 재시도하지 않는다.

## 중단 규칙

`stop`은 현재 실행의 종료 요청만 저장한다. daemon은 이를 감지하면 executor를 종료하고 `INTERRUPTED` 결과를 남긴다. 중단된 PRD는 자동 재실행하지 않는다.

## 스케줄

이 하네스는 daemon 하나로 운영한다. Hermes cron은 이 프로젝트에 생성하지 않는다. 상태 알림이 필요하면 외부 운영자가 읽기 전용 상태 확인을 호출하되 daemon을 기동하거나 재실행하지 않아야 한다.
