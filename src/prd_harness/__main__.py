from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path

from .core import Harness, HarnessConfig, HarnessError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Approval-gated local PRD harness")
    parser.add_argument("--root", required=True, type=Path, help="Path to .harness state directory")
    parser.add_argument("--allowed-repo", action="append", default=[], type=Path, help="Exact allowed repository path; repeatable")
    parser.add_argument("--executor", default="python scripts/agy_executor.py", help="Optional local executor command. The PRD path is appended as its final argument.")
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--max-runtime-seconds", type=int, default=1800)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("run-once")
    sub.add_parser("daemon")
    status = sub.add_parser("status")
    status.add_argument("--job-id")
    stop = sub.add_parser("stop")
    stop.add_argument("job_id")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    executor = tuple(shlex.split(args.executor)) if args.executor else None
    harness = Harness(
        HarnessConfig(
            root=args.root,
            allowed_repositories=tuple(args.allowed_repo),
            executor=executor,
            poll_seconds=args.poll_seconds,
            max_runtime_seconds=args.max_runtime_seconds,
        )
    )
    try:
        if args.command == "init":
            harness.initialize()
            print(json.dumps({"root": str(args.root.resolve()), "status": "INITIALIZED"}, ensure_ascii=False))
            return 0
        if args.command == "run-once":
            result = harness.process_once()
            print(json.dumps(result or {"status": "IDLE"}, ensure_ascii=False))
            return 0
        if args.command == "daemon":
            harness.serve()
            return 0
        if args.command == "status":
            print(json.dumps(harness.status(args.job_id), ensure_ascii=False))
            return 0
        if args.command == "stop":
            harness.request_stop(args.job_id)
            print(json.dumps({"job_id": args.job_id, "status": "STOP_REQUESTED"}, ensure_ascii=False))
            return 0
    except HarnessError as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
