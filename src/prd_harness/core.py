from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import timezone, datetime
from pathlib import Path
from typing import Any, Iterable

TERMINAL_STATES = {
    "READY_FOR_REVIEW",
    "TEST_FAILED",
    "BLOCKED",
    "AUTH_REQUIRED",
    "QUOTA_BLOCKED",
    "INTERRUPTED",
}
REQUIRED_FALSE = ("allow_commit", "allow_push", "allow_db_change", "allow_network")
TEST_PREFIXES = ("python -m unittest", "python -m pytest", "pytest ", "npm test", "cargo test")
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,80}$")


class HarnessError(RuntimeError):
    pass


@dataclass(frozen=True)
class HarnessConfig:
    root: Path
    allowed_repositories: tuple[Path, ...]
    executor: tuple[str, ...] | None = None
    poll_seconds: int = 30
    max_runtime_seconds: int = 30 * 60
    test_prefixes: tuple[str, ...] = TEST_PREFIXES

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", self.root.resolve())
        object.__setattr__(
            self,
            "allowed_repositories",
            tuple(path.resolve() for path in self.allowed_repositories),
        )
        if self.poll_seconds < 1 or self.max_runtime_seconds < 1:
            raise ValueError("poll_seconds and max_runtime_seconds must be positive")


@dataclass
class Validation:
    metadata: dict[str, Any]
    repository: Path | None
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and self.repository is not None


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"true", "false"}:
        return value == "true"
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    return value


def parse_prd(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        raise HarnessError("PRD frontmatter is required")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise HarnessError("PRD frontmatter closing delimiter is required")
    metadata: dict[str, Any] = {}
    active_list: str | None = None
    for line in text[4:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("  - "):
            if active_list is None:
                raise HarnessError("list item without a frontmatter key")
            metadata.setdefault(active_list, []).append(parse_scalar(line[4:]))
            continue
        if ":" not in line:
            raise HarnessError(f"invalid frontmatter line: {line}")
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        active_list = key if value == "" else None
        metadata[key] = [] if value == "" else parse_scalar(value)
    return metadata, text[end + 5 :]


def redact(text: str) -> str:
    patterns = (
        r"(?im)^\s*[^\n=]*(?:token|secret|password|api[_-]?key)[^\n=]*=\s*[^\s]+",
        r"(?i)bearer\s+[a-z0-9._~+\-/=]+",
    )
    for pattern in patterns:
        text = re.sub(pattern, "[REDACTED]", text)
    return text


class Harness:
    def __init__(self, config: HarnessConfig):
        self.config = config
        self.paths = {
            name: config.root / name
            for name in ("inbox", "approved", "running", "done", "failed", "runs", "state")
        }
        self.jobs_path = self.paths["state"] / "jobs.json"
        self.lock_path = self.paths["state"] / "lock.json"

    def initialize(self) -> None:
        for path in self.paths.values():
            path.mkdir(parents=True, exist_ok=True)
        if not self.jobs_path.exists():
            write_json(self.jobs_path, {"jobs": {}, "processed": {}})
        capabilities = {
            "executor_configured": self.config.executor is not None,
            "max_runtime_seconds": self.config.max_runtime_seconds,
            "allowed_repositories": [str(p) for p in self.config.allowed_repositories],
            "network_execution": False,
            "automatic_commit": False,
            "automatic_push": False,
        }
        write_json(self.paths["state"] / "capabilities.json", capabilities)

    def _acquire_lock(self) -> None:
        self.initialize()
        try:
            fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise HarnessError("another harness instance owns the lock") from exc
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"pid": os.getpid(), "acquired_at": utc_now()}, handle)

    def _release_lock(self) -> None:
        self.lock_path.unlink(missing_ok=True)

    def _update_job(self, job_id: str, payload: dict[str, Any]) -> None:
        state = safe_json(self.jobs_path, {"jobs": {}, "processed": {}})
        state.setdefault("jobs", {})[job_id] = payload
        write_json(self.jobs_path, state)

    def status(self, job_id: str | None = None) -> dict[str, Any]:
        state = safe_json(self.jobs_path, {"jobs": {}, "processed": {}})
        jobs = state.get("jobs", {})
        if job_id is not None:
            if job_id not in jobs:
                raise HarnessError(f"unknown job: {job_id}")
            return jobs[job_id]
        return {"jobs": jobs}

    def request_stop(self, job_id: str) -> None:
        job = self.status(job_id)
        if job.get("status") != "RUNNING":
            raise HarnessError(f"job is not running: {job_id}")
        job["stop_requested_at"] = utc_now()
        self._update_job(job_id, job)

    def recover_interrupted(self) -> list[str]:
        self.initialize()
        recovered: list[str] = []
        for prd_path in sorted(self.paths["running"].glob("*.md")):
            try:
                metadata, _ = parse_prd(prd_path.read_text(encoding="utf-8"))
                job_id = str(metadata.get("id", prd_path.stem))
            except (OSError, HarnessError):
                job_id = prd_path.stem
            result = {
                "job_id": job_id,
                "status": "INTERRUPTED",
                "finished_at": utc_now(),
                "changed_files": [],
                "tests": [],
                "next_action": "사람이 diff와 작업 상태를 검토한 뒤 새 PRD로 다시 승인",
            }
            run_dir = self.paths["runs"] / job_id
            run_dir.mkdir(parents=True, exist_ok=True)
            write_json(run_dir / "result.json", result)
            self._update_job(job_id, result)
            os.replace(prd_path, self.paths["failed"] / prd_path.name)
            recovered.append(job_id)
        return recovered

    def _environment_errors(self, repository: Path) -> list[str]:
        errors: list[str] = []
        if any(name.endswith("_API_KEY") for name in os.environ):
            errors.append("API-key environment variable detected; executor is blocked")
        if (repository / ".env").exists():
            errors.append(".env file detected; executor is blocked")
        return errors

    def validate(self, prd_path: Path) -> Validation:
        try:
            metadata, _ = parse_prd(prd_path.read_text(encoding="utf-8"))
        except (OSError, HarnessError) as exc:
            return Validation({}, None, [str(exc)])
        errors: list[str] = []
        job_id = str(metadata.get("id", ""))
        if not ID_PATTERN.fullmatch(job_id):
            errors.append("id must be a lowercase unique slug")
        if metadata.get("status") != "approved":
            errors.append("status must be approved")
        if metadata.get("risk") != "low":
            errors.append("risk must be low")
        for key in REQUIRED_FALSE:
            if metadata.get(key) is not False:
                errors.append(f"{key} must be false")
        allowed_paths = metadata.get("allowed_paths")
        if not isinstance(allowed_paths, list) or not allowed_paths or not all(isinstance(x, str) and x for x in allowed_paths):
            errors.append("allowed_paths must be a non-empty list")
        tests = metadata.get("tests")
        if not isinstance(tests, list) or not tests:
            errors.append("tests must be a non-empty list")
        elif any(not isinstance(command, str) or not command.startswith(self.config.test_prefixes) for command in tests):
            errors.append("a test command is not in the configured allowlist")
        repository: Path | None = None
        try:
            candidate = Path(str(metadata.get("repository", ""))).resolve()
            if candidate not in self.config.allowed_repositories:
                errors.append("repository is not allowlisted")
            elif not (candidate / ".git").exists():
                errors.append("repository is not a git worktree")
            else:
                repository = candidate
                branch = subprocess.run(
                    ["git", "-C", str(candidate), "branch", "--show-current"],
                    capture_output=True, text=True, check=False,
                ).stdout.strip()
                if branch != metadata.get("branch"):
                    errors.append("current branch does not match PRD branch")
                dirty = subprocess.run(
                    ["git", "-C", str(candidate), "status", "--porcelain"],
                    capture_output=True, text=True, check=False,
                ).stdout.strip()
                if dirty:
                    errors.append("worktree must be clean before execution")
                errors.extend(self._environment_errors(candidate))
        except OSError as exc:
            errors.append(f"repository validation failed: {exc}")
        return Validation(metadata, repository, errors)

    def _result(self, job_id: str, status: str, *, run_dir: Path, started_at: str, changed_files: list[str] | None = None, tests: list[dict[str, Any]] | None = None, next_action: str, reason: str | None = None) -> dict[str, Any]:
        result = {
            "job_id": job_id,
            "status": status,
            "started_at": started_at,
            "finished_at": utc_now(),
            "changed_files": changed_files or [],
            "tests": tests or [],
            "next_action": next_action,
        }
        if reason:
            result["reason"] = reason
        write_json(run_dir / "result.json", result)
        self._update_job(job_id, result)
        return result

    def _is_stop_requested(self, job_id: str) -> bool:
        return bool(self.status(job_id).get("stop_requested_at"))

    def _run_command(self, command: Iterable[str], *, cwd: Path, timeout: int, job_id: str) -> tuple[int, str, str, bool]:
        safe_env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
        process = subprocess.Popen(
            list(command), cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=safe_env,
        )
        deadline = time.monotonic() + timeout
        while True:
            try:
                stdout, stderr = process.communicate(timeout=0.25)
                return process.returncode, redact(stdout), redact(stderr), False
            except subprocess.TimeoutExpired:
                if self._is_stop_requested(job_id) or time.monotonic() >= deadline:
                    process.terminate()
                    try:
                        stdout, stderr = process.communicate(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        stdout, stderr = process.communicate()
                    return process.returncode or 1, redact(stdout), redact(stderr), True

    def _allowed_change(self, path: str, allowed_paths: list[str]) -> bool:
        normalized = path.replace("\\", "/").lstrip("./")
        for allowed in allowed_paths:
            prefix = allowed.replace("\\", "/").strip("/")
            if normalized == prefix or normalized.startswith(prefix + "/"):
                return True
        return False

    def process(self, approved_prd: Path) -> dict[str, Any]:
        self.initialize()
        validation = self.validate(approved_prd)
        job_id = str(validation.metadata.get("id", approved_prd.stem))
        started_at = utc_now()
        run_dir = self.paths["runs"] / job_id
        run_dir.mkdir(parents=True, exist_ok=True)
        if not validation.ok:
            shutil.copy2(approved_prd, run_dir / "input.md")
            result = self._result(
                job_id, "BLOCKED", run_dir=run_dir, started_at=started_at,
                next_action="PRD와 실행 환경을 수정한 뒤 사람이 다시 승인",
                reason="; ".join(validation.errors),
            )
            os.replace(approved_prd, self.paths["failed"] / approved_prd.name)
            return result
        assert validation.repository is not None
        state = safe_json(self.jobs_path, {"jobs": {}, "processed": {}})
        raw = approved_prd.read_bytes()
        content_hash = hashlib.sha256(raw).hexdigest()
        processed = state.setdefault("processed", {})
        if processed.get(job_id) == content_hash:
            result = self._result(
                job_id, "BLOCKED", run_dir=run_dir, started_at=started_at,
                next_action="중복 실행하지 않음. 새 ID와 검토를 거친 PRD가 필요",
                reason="duplicate PRD id and content hash",
            )
            os.replace(approved_prd, self.paths["failed"] / approved_prd.name)
            return result
        running_prd = self.paths["running"] / approved_prd.name
        os.replace(approved_prd, running_prd)
        shutil.copy2(running_prd, run_dir / "input.md")
        _, body = parse_prd(running_prd.read_text(encoding="utf-8"))
        prompt = (
            "Execute only this approved local PRD. Do not commit, push, deploy, change database state, "
            "enable network access, or read/write credentials. Stay within allowed_paths. "
            "Return a concise summary and test result.\n\n" + body
        )
        prompt_path = run_dir / "prompt.md"
        prompt_path.write_text(prompt, encoding="utf-8")
        running_state = {
            "job_id": job_id, "status": "RUNNING", "started_at": started_at,
            "changed_files": [], "tests": [], "next_action": "executor running",
        }
        self._update_job(job_id, running_state)
        if self.config.executor is None:
            result = self._result(
                job_id, "BLOCKED", run_dir=run_dir, started_at=started_at,
                next_action="명시적으로 허용된 로컬 executor를 구성한 뒤 새 PRD로 승인",
                reason="executor is not configured",
            )
            os.replace(running_prd, self.paths["failed"] / running_prd.name)
            return result
        exit_code, stdout, stderr, stopped = self._run_command(
            (*self.config.executor, str(prompt_path)), cwd=validation.repository,
            timeout=self.config.max_runtime_seconds, job_id=job_id,
        )
        (run_dir / "stdout.log").write_text(stdout, encoding="utf-8")
        (run_dir / "stderr.log").write_text(stderr, encoding="utf-8")
        if stopped:
            result = self._result(
                job_id, "INTERRUPTED", run_dir=run_dir, started_at=started_at,
                next_action="사람이 diff와 중단된 실행을 검토한 뒤 새 PRD로 다시 승인",
                reason="stop requested or maximum runtime exceeded",
            )
            os.replace(running_prd, self.paths["failed"] / running_prd.name)
            return result
        unstaged = subprocess.run(
            ["git", "-C", str(validation.repository), "diff", "--name-only"],
            capture_output=True, text=True, check=False,
        )
        staged = subprocess.run(
            ["git", "-C", str(validation.repository), "diff", "--cached", "--name-only"],
            capture_output=True, text=True, check=False,
        )
        untracked = subprocess.run(
            ["git", "-C", str(validation.repository), "ls-files", "--others", "--exclude-standard"],
            capture_output=True, text=True, check=False,
        )
        changed = sorted(set(unstaged.stdout.splitlines() + staged.stdout.splitlines() + untracked.stdout.splitlines()))
        diff = subprocess.run(
            ["git", "-C", str(validation.repository), "diff", "--binary"],
            capture_output=True, text=True, check=False,
        ).stdout
        diff += subprocess.run(
            ["git", "-C", str(validation.repository), "diff", "--cached", "--binary"],
            capture_output=True, text=True, check=False,
        ).stdout
        for relative_path in untracked.stdout.splitlines():
            created = subprocess.run(
                ["git", "-C", str(validation.repository), "diff", "--no-index", "--binary", "--", "/dev/null", relative_path],
                capture_output=True, text=True, check=False,
            )
            diff += created.stdout
        (run_dir / "diff.patch").write_text(redact(diff), encoding="utf-8")
        if exit_code != 0:
            if exit_code == 3:
                status = "AUTH_REQUIRED"
                next_action = "사용자가 직접 로그인"
            elif exit_code == 4:
                status = "QUOTA_BLOCKED"
                next_action = "사용량 회복 뒤 새 작업 승인"
            else:
                status = "BLOCKED"
                next_action = "executor 오류를 사람이 검토하고 새 PRD로 재승인"

            result = self._result(
                job_id, status, run_dir=run_dir, started_at=started_at, changed_files=changed,
                next_action=next_action,
                reason=f"executor exit code {exit_code}",
            )
            os.replace(running_prd, self.paths["failed"] / running_prd.name)
            return result
        outside = [path for path in changed if not self._allowed_change(path, validation.metadata["allowed_paths"])]
        if outside:
            result = self._result(
                job_id, "BLOCKED", run_dir=run_dir, started_at=started_at, changed_files=changed,
                next_action="허용 범위 밖 diff를 사람이 검토하고 되돌린 뒤 새 PRD로 재승인",
                reason="out-of-scope changes: " + ", ".join(outside),
            )
            os.replace(running_prd, self.paths["failed"] / running_prd.name)
            return result
        test_results: list[dict[str, Any]] = []
        test_log: list[str] = []
        for command in validation.metadata["tests"]:
            completed = subprocess.run(command, cwd=validation.repository, shell=True, text=True, capture_output=True, timeout=self.config.max_runtime_seconds)
            test_results.append({"command": command, "exit_code": completed.returncode})
            test_log.append(f"$ {command}\n{redact(completed.stdout)}\n{redact(completed.stderr)}")
            if completed.returncode != 0:
                (run_dir / "test.log").write_text("\n".join(test_log), encoding="utf-8")
                result = self._result(
                    job_id, "TEST_FAILED", run_dir=run_dir, started_at=started_at,
                    changed_files=changed, tests=test_results,
                    next_action="실패 로그와 diff를 검토한 뒤 후속 PRD 작성",
                    reason=f"test command failed: {command}",
                )
                os.replace(running_prd, self.paths["failed"] / running_prd.name)
                return result
        (run_dir / "test.log").write_text("\n".join(test_log), encoding="utf-8")
        processed[job_id] = content_hash
        write_json(self.jobs_path, state)
        result = self._result(
            job_id, "READY_FOR_REVIEW", run_dir=run_dir, started_at=started_at,
            changed_files=changed, tests=test_results,
            next_action="사람이 diff.patch와 test.log를 검토. 자동 commit/push/deploy 없음",
        )
        os.replace(running_prd, self.paths["done"] / running_prd.name)
        return result

    def process_once(self) -> dict[str, Any] | None:
        self._acquire_lock()
        try:
            self.recover_interrupted()
            candidates = sorted(self.paths["approved"].glob("*.md"))
            return self.process(candidates[0]) if candidates else None
        finally:
            self._release_lock()

    def serve(self) -> None:
        self.initialize()
        self.recover_interrupted()
        while True:
            self.process_once()
            time.sleep(self.config.poll_seconds)
