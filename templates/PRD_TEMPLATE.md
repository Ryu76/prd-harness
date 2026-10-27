---
id: project-yyyymmdd-001
title: 작업 제목
status: draft
repository: C:/absolute/path/to/repository
branch: main
mode: code_and_test
risk: low
allow_commit: false
allow_push: false
allow_db_change: false
allow_network: false
github_delivery: none # none | branch (GitHub branch push requires explicit PRD approval)
allowed_paths:
  - src/example.py
tests:
  - python -m unittest tests.test_example
acceptance:
  - 관찰 가능한 완료 조건을 작성한다
---

# 작업 PRD

## 문제와 목표

- 현재 문제:
- 재현 조건:
- 목표:
- 기대하지 않는 변경:

## 수정 범위

### 수정 가능

- `allowed_paths`에 선언한 파일 또는 하위 경로만 수정한다.

### 수정 금지

- API 키, 비밀값, 인증 파일 및 `.env`
- DB 스키마·운영 데이터
- 배포 설정, git commit/push
- `allowed_paths` 밖의 모든 파일

## 구현 지시

1. 관련 코드와 기존 규칙을 먼저 확인한다.
2. 요구사항을 충족하는 최소 범위만 수정한다.
3. 불확실하거나 범위를 벗어난 항목은 변경하지 않고 사유를 남긴다.

## 검증 방법

- 자동 테스트: frontmatter `tests`에 허용 명령을 작성한다.
- 수동 확인:
- 기존 기능 영향 확인:

## 검토 메모

- 위험 요소:
- 되돌리는 방법:
- 검토자:
- 승인 일시:
