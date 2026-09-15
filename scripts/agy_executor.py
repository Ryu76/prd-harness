import sys
import subprocess
from pathlib import Path

def main():
    if len(sys.argv) < 2:
        print("Usage: python agy_executor.py <prompt_file>")
        sys.exit(1)

    prompt_file = Path(sys.argv[1])
    if not prompt_file.exists():
        print(f"Error: Prompt file not found: {prompt_file}")
        sys.exit(1)

    prompt_content = prompt_file.read_text(encoding="utf-8")

    command = [
        "agy",
        "--model", "gemini-3.1-pro-low",
        "--mode", "accept-edits",
        "--dangerously-skip-permissions",
        f"--print={prompt_content}"
    ]

    try:
        result = subprocess.run(command, capture_output=True, text=True, shell=False)
    except Exception as e:
        print(f"Failed to execute agy: {e}", file=sys.stderr)
        sys.exit(1)

    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

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
