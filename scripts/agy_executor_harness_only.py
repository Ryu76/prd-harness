"""Privileged AI Pro executor restricted to an approved local PRD Harness run.

This adapter exists only because agy print-mode offers no granular command allow rule.
It must be selected explicitly for a dedicated harness worktree after user approval.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

AI_PRO_WORK_POLICY = """
AI PRO GLOBAL WORK POLICY:
- You may directly read/create/edit/delete files only inside approved PRD allowed_paths and run declared checks.
- You may install only necessary project-scoped dependencies: Python only in the PRD's Conda environment; JavaScript only through the repository's existing package manager and lockfile. Never install globally or alter OS/system tooling.
- If any additional permission is needed (scope expansion, credential/.env access, DB/DDL, deployment, non-package network access, global/system install, destructive command, system settings), do not act. Output [PERMISSION_REQUIRED] with reason, exact command, target, and impact.
- When the approved PRD explicitly requests GitHub upload: existing repositories must use a new ai-pro/<job-id> branch, never main or a user branch. A project with no remote may create a private Ryu76/<project-directory> repository only after confirming its name is unused. Verify the remote branch after push. Never auto-merge.
- If GitHub upload is not explicitly requested in the PRD, do not commit or push.
"""


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: agy_executor_harness_only.py <harness-prompt-file>", file=sys.stderr)
        raise SystemExit(1)

    prompt_file = Path(sys.argv[1]).resolve()
    workspace = Path.cwd().resolve()
    expected_runs = workspace / ".harness" / "runs"
    if not expected_runs in prompt_file.parents or prompt_file.name != "prompt.md":
        print("Refusing prompt outside this worktree's harness run directory", file=sys.stderr)
        raise SystemExit(1)

    prompt = prompt_file.read_text(encoding="utf-8")
    if "PROJECT_TOP_LEVEL_AUTONOMY" in prompt:
        agent_prompt = """PROJECT_TOP_LEVEL_AUTONOMY: The user explicitly authorizes all necessary project-local actions without further questions, including file edits, package installation, network access, database work, and Git operations. Work only in the supplied dedicated worktree. Do not delete the project/worktree, delete .git, or run destructive bulk-delete commands. Preserve a working, testable project; choose reversible changes and record all actions in PROGRESS.md.\n\n""" + prompt
    else:
        agent_prompt = AI_PRO_WORK_POLICY + "\n\n" + prompt
    command = [
        "agy",
        "--add-dir", str(workspace),
        "--model", "gemini-3.1-pro-high",
        "--mode", "accept-edits",
        "--sandbox",
        "--dangerously-skip-permissions",
        "--print-timeout", "28m",
        f"--print={agent_prompt}",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, shell=False)
    print(completed.stdout)
    if completed.stderr:
        print(completed.stderr, file=sys.stderr)

    if "[PERMISSION_REQUIRED]" in completed.stdout:
        raise SystemExit(5)

    if completed.returncode:
        stderr = completed.stderr.lower()
        if any(term in stderr for term in ("quota", "rate limit", "429", "too many requests")):
            raise SystemExit(4)
        if any(term in stderr for term in ("auth", "login", "unauthenticated", "401", "credentials")):
            raise SystemExit(3)
    raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
