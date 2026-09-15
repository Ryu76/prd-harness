from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from prd_harness.core import Harness, HarnessConfig


class HarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.repo = self.base / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-b", "main"], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "Harness Test"], cwd=self.repo, check=True)
        (self.repo / "src").mkdir()
        (self.repo / "tests").mkdir()
        (self.repo / "tests" / "__init__.py").write_text("", encoding="utf-8")
        (self.repo / "tests" / "test_smoke.py").write_text(
            "import unittest\n\nclass Smoke(unittest.TestCase):\n    def test_ok(self): self.assertTrue(True)\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=self.repo, check=True, capture_output=True)
        self.harness_root = self.base / ".harness"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _prd(self, *, status: str = "approved", allowed: str = "src/changed.txt") -> str:
        return f"""---
id: sample-20260914-001
title: sample
status: {status}
repository: {self.repo.as_posix()}
branch: main
mode: code_and_test
risk: low
allow_commit: false
allow_push: false
allow_db_change: false
allow_network: false
allowed_paths:
  - {allowed}
tests:
  - python -m unittest tests.test_smoke
acceptance:
  - smoke test passes
---

# 작업 PRD

## 문제와 목표

- 안전한 테스트 변경
"""

    def _harness(self, script: str) -> Harness:
        executor = self.base / "executor.py"
        executor.write_text(script, encoding="utf-8")
        return Harness(
            HarnessConfig(
                root=self.harness_root,
                allowed_repositories=(self.repo,),
                executor=(sys.executable, str(executor)),
                max_runtime_seconds=10,
            )
        )

    def _approve(self, content: str) -> Path:
        approved = self.harness_root / "approved"
        approved.mkdir(parents=True, exist_ok=True)
        path = approved / "sample.md"
        path.write_text(content, encoding="utf-8")
        return path

    def _environment_without_api_keys(self):
        return {key: value for key, value in os.environ.items() if not key.endswith("_API_KEY")}

    def test_draft_prd_is_blocked_without_executor(self) -> None:
        harness = self._harness("raise SystemExit('must not run')")
        self._approve(self._prd(status="draft"))
        with patch.dict(os.environ, self._environment_without_api_keys(), clear=True):
            result = harness.process_once()
        assert result is not None
        self.assertEqual("BLOCKED", result["status"])
        self.assertIn("status must be approved", result["reason"])
        self.assertTrue((self.harness_root / "failed" / "sample.md").exists())

    def test_allowed_change_tests_and_result_are_retained(self) -> None:
        harness = self._harness(
            "from pathlib import Path\nPath('src/changed.txt').write_text('ok', encoding='utf-8')\nprint('changed')\n"
        )
        self._approve(self._prd())
        with patch.dict(os.environ, self._environment_without_api_keys(), clear=True):
            result = harness.process_once()
        assert result is not None
        self.assertEqual("READY_FOR_REVIEW", result["status"])
        self.assertEqual(["src/changed.txt"], result["changed_files"])
        self.assertEqual(0, result["tests"][0]["exit_code"])
        run_dir = self.harness_root / "runs" / "sample-20260914-001"
        self.assertTrue((run_dir / "diff.patch").exists())
        self.assertIn("src/changed.txt", (run_dir / "diff.patch").read_text(encoding="utf-8"))
        self.assertTrue((run_dir / "test.log").exists())
        self.assertTrue((self.harness_root / "done" / "sample.md").exists())

    def test_out_of_scope_change_is_blocked_and_diff_is_retained(self) -> None:
        harness = self._harness("from pathlib import Path\nPath('notes.txt').write_text('outside', encoding='utf-8')\n")
        self._approve(self._prd())
        with patch.dict(os.environ, self._environment_without_api_keys(), clear=True):
            result = harness.process_once()
        assert result is not None
        self.assertEqual("BLOCKED", result["status"])
        self.assertIn("notes.txt", result["reason"])
        self.assertTrue((self.harness_root / "runs" / "sample-20260914-001" / "diff.patch").exists())
        self.assertTrue((self.harness_root / "failed" / "sample.md").exists())

    def test_recovery_marks_running_prd_interrupted_without_rerun(self) -> None:
        harness = self._harness("raise SystemExit('must not run')")
        running = self.harness_root / "running"
        running.mkdir(parents=True, exist_ok=True)
        (running / "sample.md").write_text(self._prd(), encoding="utf-8")
        recovered = harness.recover_interrupted()
        self.assertEqual(["sample-20260914-001"], recovered)
        status = harness.status("sample-20260914-001")
        self.assertEqual("INTERRUPTED", status["status"])
        self.assertTrue((self.harness_root / "failed" / "sample.md").exists())

    def test_auth_required_from_exit_code_3(self) -> None:
        harness = self._harness("raise SystemExit(3)")
        self._approve(self._prd())
        with patch.dict(os.environ, self._environment_without_api_keys(), clear=True):
            result = harness.process_once()
        assert result is not None
        self.assertEqual("AUTH_REQUIRED", result["status"])
        self.assertTrue((self.harness_root / "failed" / "sample.md").exists())

    def test_quota_blocked_from_exit_code_4(self) -> None:
        harness = self._harness("raise SystemExit(4)")
        self._approve(self._prd())
        with patch.dict(os.environ, self._environment_without_api_keys(), clear=True):
            result = harness.process_once()
        assert result is not None
        self.assertEqual("QUOTA_BLOCKED", result["status"])
        self.assertTrue((self.harness_root / "failed" / "sample.md").exists())


if __name__ == "__main__":
    unittest.main()
