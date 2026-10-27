# AI Pro 전역 작업 정책

이 문서는 PRD Harness에서 실행되는 모든 AI Pro(Antigravity CLI) 코딩 작업의 기본 정책이다. 개별 승인 PRD가 더 좁은 범위를 지정하면 PRD가 우선한다.

## 1. 기본 승인 권한

AI Pro는 승인된 전용 worktree 안에서 다음을 별도 승인 없이 수행할 수 있다.

- PRD `allowed_paths` 안의 파일 읽기·생성·수정·삭제
- 관련 소스와 테스트 읽기, formatter/linter/test/build 실행
- 작업에 필요한 **프로젝트 범위 의존성** 설치·갱신
  - Python은 PRD가 지정한 Conda 환경만 사용한다. 시스템 Python, 전역 pip, 전역 Conda base는 사용하지 않는다.
  - JavaScript는 저장소의 lockfile과 기존 package manager를 따른다.
  - 전역 CLI, 드라이버, OS 패키지, 브라우저 확장, credential helper 설치는 기본 권한에 포함되지 않는다.
- 위 프로젝트 의존성 설치에 한정된 package registry 접근

의존성 설치는 최소 항목이어야 하며, manifest/lockfile을 함께 갱신하고 정확한 설치 명령과 버전을 결과에 남긴다. 비밀값, `.env`, 인증 파일은 읽거나 출력하거나 생성하지 않는다.

## 2. 추가 권한 요청

아래 중 하나가 필요하면 실행하지 말고, stdout에 정확히 `[PERMISSION_REQUIRED]`를 포함해 이유·명령·대상·영향을 요약한다. Harness는 이를 `PERMISSION_REQUIRED`로 기록하며 사용자의 새 승인을 기다린다.

- `allowed_paths` 밖 파일 변경
- 프로젝트 범위를 벗어난 package/OS/전역 CLI 설치
- 실제 credential 입력·조회·생성 또는 `.env`/인증 파일 접근
- DB 연결·DDL·운영 데이터 변경
- 배포, 외부 API 호출, 알림 전송, 프로젝트 의존성 설치 외 네트워크 접근
- destructive command, 권한/계정/시스템 설정 변경
- 명시되지 않은 GitHub organization/repository visibility 또는 외부 collaborator 설정

권한 요청 전에는 우회 구현, 임시 helper 파일 생성, commit/push를 하지 않는다.

## 3. GitHub 업로드 정책

Git 업로드가 개별 PRD에서 명시적으로 요청·승인된 경우에만 적용한다.

1. **기존 Git 프로젝트**: 현재 브랜치·원격·worktree 상태를 확인하고, 기존 사용자 브랜치나 `main`/기본 브랜치에는 직접 작업하지 않는다. 작업 ID 기반 새 브랜치 `ai-pro/<job-id>`를 생성해 commit/push한다.
2. **원격 저장소가 없는 신규 프로젝트**: 프로젝트 디렉터리 이름을 저장소 이름으로 사용하여 GitHub 계정 `Ryu76`에 **private** 저장소를 생성하고, `ai-pro/<job-id>` 브랜치만 push한다. 동일 이름 저장소가 이미 있으면 생성하지 말고 권한을 다시 요청한다.
3. commit 전에는 staged file list, `git diff --cached --check`, secret/credential artifact exclusion, 선언된 tests를 확인한다.
4. push 후에는 원격 branch ref와 URL을 다시 확인한다. 자동 merge, default-branch 변경, release, collaborator 변경은 금지한다.

Git 업로드가 PRD에 없으면 결과는 `READY_FOR_REVIEW`로 남기며 자동 commit/push하지 않는다.

## 4. 공통 안전 규칙

- 전용 clean worktree 한 곳만 쓰고, 병렬 writer는 허용하지 않는다.
- `git diff --check`와 PRD tests를 모두 통과하기 전 성공을 주장하지 않는다.
- agent summary는 증거가 아니다. Harness 로그와 독립 검증이 우선한다.
- 권한 우회 executor는 사용자 명시 승인이 있을 때만 사용하며, sandbox와 Harness의 scope/diff/test gate는 계속 유지한다.
