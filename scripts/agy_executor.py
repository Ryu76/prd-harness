import sys
import subprocess
from pathlib import Path

AI_PRO_WORK_POLICY = """
AI PRO GLOBAL WORK POLICY:
- You may directly read/create/edit/delete files only inside the approved PRD allowed_paths and run declared checks.
- You may install only necessary project-scoped dependencies: Python only in the PRD's Conda environment; JavaScript only through the repository's existing package manager and lockfile. Never install globally or alter OS/system tooling.
- If any additional permission is needed (scope expansion, credential/.env access, DB/DDL, deployment, non-package network access, global/system install, destructive command, system settings), do not act. Output [PERMISSION_REQUIRED] with reason, exact command, target, and impact.
- When the approved PRD explicitly requests GitHub upload: existing repositories must use a new ai-pro/<job-id> branch, never main or a user branch. A project with no remote may create a private Ryu76/<project-directory> repository only after confirming its name is unused. Verify the remote branch after push. Never auto-merge.
- If GitHub upload is not explicitly requested in the PRD, do not commit or push.
"""

def main():
    if len(sys.argv) < 2:
        print("Usage: python agy_executor.py <prompt_file>")
        sys.exit(1)

    prompt_file = Path(sys.argv[1])
    if not prompt_file.exists():
        print(f"Error: Prompt file not found: {prompt_file}")
        sys.exit(1)

    prompt_content = prompt_file.read_text(encoding="utf-8")
    agent_prompt = AI_PRO_WORK_POLICY + "\n\n" + prompt_content
    workspace = Path.cwd().resolve()

    command = [
        "agy",
        "--add-dir", str(workspace),
        "--model", "gemini-3.1-pro-low",
        "--mode", "accept-edits",
        "--sandbox",
        "--print-timeout", "28m",
        f"--print={agent_prompt}"
    ]

    try:
        result = subprocess.run(command, capture_output=True, text=True, shell=False)
    except Exception as e:
        print(f"Failed to execute agy: {e}", file=sys.stderr)
        sys.exit(1)

    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    if "[PERMISSION_REQUIRED]" in result.stdout:
        sys.exit(5)

    if result.returncode != 0:
        stderr_lower = result.stderr.lower()
        
        # Check for Quota Blocked
        if any(term in stderr_lower for term in ["quota", "rate limit", "429", "too many requests"]):
            sys.exit(4)
        
        # Check for Auth Required
        if any(term in stderr_lower for term in ["auth", "login", "unauthenticated", "401", "credentials"]):
            sys.exit(3)

    sys.exit(result.returncode)

if __name__ == "__main__":
    main()
