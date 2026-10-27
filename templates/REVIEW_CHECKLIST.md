# PRD 검토 체크리스트

## 요구사항

- [ ] 문제와 목표가 분리돼 있다.
- [ ] 완료 조건이 관찰 가능한 결과다.
- [ ] 기대하지 않는 변경이 적혀 있다.

## 범위와 안전

- [ ] `allowed_paths`가 구체적이고 최소 범위다.
- [ ] 수정 금지 대상이 명시돼 있다.
- [ ] API 키, 인증 정보, DB 스키마, 배포 설정 변경이 없다.
- [ ] `allow_commit`, `allow_push`, `allow_db_change`, `allow_network`가 모두 `false`다.
- [ ] GitHub 업로드가 필요하면 `github_delivery: branch`와 대상 저장소/branch 정책이 명시돼 있다. 필요 없으면 `none`이다.
- [ ] `risk: low`다.

## 검증과 승인

- [ ] 테스트 명령이 허용 목록에 포함된다.
- [ ] 수동 확인과 되돌리는 방법이 있다.
- [ ] 현재 worktree가 깨끗한지 확인했다.
- [ ] PRD ID가 중복되지 않는다.
- [ ] 사람이 검토한 뒤에만 `approved/` 폴더로 이동한다.
