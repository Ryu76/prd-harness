# 독립 코드리뷰: 병합 차단 항목 전체 목록

- **대상 브랜치:** `ai-pro/integrated-full-implementation`
- **리뷰 기준 커밋:** `fbe2266` (`test: harden PRD closure security and browser QA`)
- **리뷰 시점:** 2026-09-18
- **판정:** `main` 병합 차단
- **범위:** Oracle 11g 호환성, 수집 원자성/정합성, P3 권한·감사, worker 배포, DB 연결 보안, 테스트 증거의 유효성

> 이 문서는 독립 코드리뷰 결과를 기록한 것이다. 단위 테스트 40개와 mocked Playwright 1개가 통과했더라도, 실제 Oracle 스키마·기존 운영 테이블·worker 프로세스·외부 연동을 재현하지 않으므로 아래 항목을 대체하지 않는다.

## 차단 항목 요약

| 번호 | 심각도 | 영역 | 병합 차단 사유 | 보정 방향 |
|---|---|---|---|---|
| B-01 | P0 | Oracle ID 생성 | `check_result_id`에 Oracle 11g 시퀀스/트리거가 없어 check 결과 포함 배치가 실패할 수 있음 | 명시적 Oracle migration에 sequence + BEFORE INSERT trigger 추가 |
| B-02 | P1 | 수집 원자성 | history 기록 실패 뒤에도 receipt/ACK가 기록되어 에이전트 spool 삭제 및 영구 데이터 유실 가능 | history 실패 시 receipt/ACK를 commit하지 않고 재시도 가능 오류 처리 |
| B-03 | P1 | 수집 정합성 | 늦게 도착한 check snapshot이 최신 process/service/port current 상태를 삭제·대체 가능 | server/snapshot watermark로 오래된 snapshot 전체 거부 |
| B-04 | P1 | Oracle 배포 | 신규 ledger/outbox/alert/P3 테이블의 명시 migration이 없어 실제 Oracle에서 즉시 실패 가능 | 모든 테이블·인덱스·sequence·trigger의 idempotent migration 제공 |
| B-05 | P1 | P3 RBAC·감사 | 인증만 된 일반 사용자도 고위험 P3 변경을 할 수 있고 요청자 identity를 body로 위조 가능 | 역할 강제, JWT actor 사용, 승인 분리, SysAuditLog 기록 |
| B-06 | P1 | Worker 배포 | API에서 worker를 분리했지만 Compose에 worker 서비스가 없어 운영 기능이 기동하지 않음 | 전용 `worker` Compose service 추가 |
| B-07 | P1 | DB URL 구성 | `@`, `:`, `/`, `%` 등을 가진 DB 비밀번호가 URL 파싱을 깨뜨릴 수 있음 | `sqlalchemy.engine.URL.create()`로 structured URL 생성 |
| B-08 | P2 | E2E 증거 | Playwright가 mock UI만 검증하며 실제 backend/history 계약 또는 통합 흐름을 증명하지 않음 | 실제 test backend/seed DB smoke 또는 정확한 contract test 추가 |

---

## B-01 — Oracle 11g check-result ID 생성기 부재

- **심각도:** P0 / 즉시 병합 차단
- **근거 위치:**
  - `backend/app/api/agent/v1/router.py:570-582`
  - `backend/app/models/process.py:17`
  - `backend/app/db_init.py:54-68`
- **문제:** 모델의 `autoincrement=True`는 기존 Oracle 11g 테이블이나 수동 DDL에 ID 생성기를 만들지 않는다. `check_result_id NUMBER NOT NULL PRIMARY KEY`만 존재하고 sequence/trigger가 없으면 PROCESS/SERVICE/PORT 결과 INSERT가 ID 없이 실행될 수 있다.
- **영향:** 첫 check-result 포함 metric batch가 Oracle에서 `ORA-01400`으로 실패하고 수집 트랜잭션 전체가 rollback될 수 있다.
- **수정 완료 기준:**
  1. Oracle 11g 호환 sequence와 BEFORE INSERT trigger를 명시 migration에 포함한다.
  2. request path에서 DDL 또는 ID 생성 추측을 하지 않는다.
  3. generated DDL과 ID 없이 INSERT되는 check-result regression test를 추가한다.

## B-02 — history 실패 이후 성공 ACK/receipt 기록

- **심각도:** P1 / 데이터 유실 위험
- **근거 위치:**
  - `backend/app/api/agent/v1/router.py:548-568, 585-596`
  - `backend/app/models/resource.py:41`
- **문제:** history INSERT 실패(파티션 미존재 등의 Oracle 오류 포함)를 nested transaction에서 경고로 처리한 뒤 receipt ledger를 저장하고 HTTP 200을 반환하는 경로가 존재한다.
- **영향:** 에이전트는 성공 ACK 뒤 spool을 삭제한다. current 값만 남고 trend/history/audit 데이터가 영구 유실될 수 있다.
- **수정 완료 기준:**
  1. history가 수신 계약이면 실패 시 ledger/ACK를 남기지 않고 retryable error를 반환한다.
  2. best-effort로 설계한다면 partial failure를 명시하고 durable recovery outbox/재처리 경로를 둔다.
  3. history write 실패 regression test에서 receipt가 없는지 확인한다.

## B-03 — 오래된 check snapshot이 최신 상태를 덮어씀

- **심각도:** P1 / current 상태 정합성
- **근거 위치:** `backend/app/api/agent/v1/router.py:498-506, 523-532`
- **문제:** 일반 metric에는 collected-at 비교가 있으나, `REPLACE_SET_METRICS`는 check metric 집합을 먼저 전체 삭제한다. 늦게 도착한 과거 PROCESS_STATUS/SERVICE_STATUS/PORT_LISTEN batch가 최신 값을 삭제한 후 자신을 current로 삽입할 수 있다.
- **영향:** spool replay, 네트워크 지연, 재시도 시 서버 current check 상태가 과거 값으로 역행한다.
- **수정 완료 기준:** snapshot-level `collected_at` watermark를 저장하고, 기존 snapshot보다 오래된 배치는 삭제 이전에 거부한다.

## B-04 — 신규 Oracle 운영 객체 migration 부재 및 request-path DDL

- **심각도:** P1 / 실제 Oracle 배포 차단
- **근거 위치:**
  - `backend/app/db_init.py:11-24`
  - `backend/app/api/agent/v1/router.py:449-461`
  - `backend/app/api/web/v1/extension.py:26-98`
  - `backend/app/alert_worker.py:45-64`
- **문제:** `ensure_operational_tables()`는 일부 check 대상/result만 다루며 `mon_metric_receipt_ledger`, `mon_alert_outbox`, `mon_alert_hist`, `ext_*` 등의 객체를 완전하게 생성하지 않는다. ledger는 HTTP request 중 임시 DDL을 시도하는 경로가 있다.
- **영향:** 운영 앱 계정에 DDL 권한이 없으면 첫 요청에서 실패한다. P3/outbox/alert worker는 `table or view does not exist`가 될 수 있다.
- **수정 완료 기준:** 버전 추적이 가능한 idempotent migration에 테이블·제약·인덱스·sequence·trigger를 모두 포함하고, request-path DDL을 제거한다.

## B-05 — P3 mutation RBAC 및 위조 방지 감사 부재

- **심각도:** P1 / 권한 상승·감사 신뢰성
- **근거 위치:** `backend/app/api/web/v1/extension.py:23, 40-67, 70-98`
- **문제:** route가 로그인 여부만 확인하고 P3 POST/PUT에 `require_roles`를 강제하지 않는다. `requested_by`를 본문에서 받아 audit event에 남기는 구조는 JWT 실제 주체 위조를 허용한다.
- **영향:** VIEWER도 allowlist된 원격 명령을 생성·승인하거나 config/HA 상태를 바꿀 수 있다. 감사 로그의 actor 신뢰성이 무너진다.
- **수정 완료 기준:**
  1. command/config/HA mutation에 OPERATOR 또는 ADMIN을 강제한다.
  2. command approval은 ADMIN 전용이며 요청자와 승인자가 달라야 한다.
  3. actor는 항상 current JWT user에서 서버 측으로 결정한다.
  4. 요청·승인·상태전이를 `SysAuditLog`에 트랜잭션으로 기록한다.

## B-06 — Compose에 전용 worker service 부재

- **심각도:** P1 / 운영 기능 미기동
- **근거 위치:**
  - `backend/app/main.py:18-27`
  - `docker-compose.yml:23-54`
- **문제:** API lifespan에서 worker/scheduler/alert/aggregator 시작을 제거한 뒤 `worker_main.py`를 추가했으나, Compose에는 그것을 실행하는 service가 없다.
- **영향:** Compose 배포에서 event 판정, heartbeat offline 감지, aggregation, alert outbox 처리가 실행되지 않는다.
- **수정 완료 기준:** backend image와 동일한 secret contract를 사용하는 `worker` service를 `python -m app.worker_main` command로 추가하고 API와 worker lifecycle을 분리한다.

## B-07 — 예약 문자를 처리하지 않는 Oracle URL 조립

- **심각도:** P1 / DB 기동·preflight 실패
- **근거 위치:**
  - `backend/app/core/config.py:64-68`
  - `backend/preflight.py:59`
- **문제:** username/password/host를 f-string URL로 연결한다. password에 `@`, `:`, `/`, `%`가 있으면 SQLAlchemy URL parser가 host/port를 잘못 해석할 수 있다.
- **영향:** 안전한 강한 비밀번호 사용 시 application startup과 preflight가 실패할 수 있다.
- **수정 완료 기준:** `sqlalchemy.engine.URL.create()` 등 구조화된 API로 URL을 만들고 reserved-character regression test를 통과시킨다. preflight 출력에는 URL·username·password를 노출하지 않는다.

## B-08 — mocked Playwright는 실제 backend/history 통합 증거가 아님

- **심각도:** P2 / 품질 증거 보정 필요
- **근거 위치:** `frontend/tests/e2e.spec.ts:86-96, 125-175`
- **문제:** 모든 API 요청을 `page.route()`로 모킹한다. 실제 history endpoint (`/api/v1/servers/{server_id}/metrics/{metric_code}/history`) 호출과 응답 계약을 유발·검증하지 않고 server-info 렌더링만 확인한다.
- **영향:** UI route와 기본 DOM은 확인하지만 backend RBAC, ingestion, Oracle, history 통합 정상성을 주장할 수 없다.
- **수정 완료 기준:**
  1. mock 테스트는 `UI mocked contract E2E`로 명확히 명명한다.
  2. 실제 test backend + seeded DB를 대상으로 최소 1개 browser smoke를 추가한다.
  3. server history URL과 history UI rendering을 명시적으로 호출·assert한다.

---

## 검증 현황과 외부 차단 조건

| 검증 | 관측 결과 | 증명 범위 |
|---|---|---|
| Backend pytest | `40 passed` | SQLite/mock 기반 단위·회귀 범위 |
| Python compile | 통과 | Python 문법/bytecode 범위 |
| Frontend production build | 통과 | TypeScript/Vite build 범위 |
| Playwright Chromium | `1 passed` | mocked API 기반 UI 흐름 범위 |
| DPAPI preflight (현재 로컬) | `.env.enc`, `env.key.dpapi` 부재로 fail-closed | 실제 Oracle 접속/DDL/partition 검증은 아직 불가 |
| Docker | CLI/Compose는 존재하나 daemon 미기동 | Oracle Free container 기반 통합 검증 불가 |

## 현재 보정 작업

이 문서의 B-01~B-07을 우선 보정하는 AI Pro 작업이 실행 중이다.

- **PRD:** `monitoring-full-implementation-phase-09-production-correctness-20260918`
- **범위:** Oracle 11g additive migration, ingestion 원자성/watermark, P3 RBAC/audit, structured DB URL, Compose worker, regression tests
- **제한:** 실제 운영 Oracle, 외부 알림, 원격 명령은 실행하지 않는다. 실제 Oracle 검증은 암호화된 개발 환경 설정과 실행 가능한 DB가 제공된 뒤에만 수행한다.