from __future__ import annotations

import argparse
import json
import sys

from enterprise_ai_tool_gateway.evals import format_text_report, run_suite


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic API acceptance evals.")
    parser.add_argument("--suite", default="acceptance", choices=["acceptance"])
    parser.add_argument("--format", default="text", choices=["text", "json"])
    args = parser.parse_args(argv)

    try:
        result = run_suite(args.suite)
    except Exception as exc:
        print(f"Eval runner error: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(format_text_report(result))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
