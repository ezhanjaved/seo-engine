"""Command-line entry point: ``python -m skills.serp``.

Writes the collected evidence as JSON to stdout. Errors go to stderr with a
non-zero exit code: 2 for bad usage or input, 3 if the browser could not
start, 4 if the results page could not be retrieved or parsed, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys

from .collector import (
    DEFAULT_TIMEOUT,
    ENGINES,
    MAX_RESULTS_LIMIT,
    BrowserStartupError,
    SerpError,
    collect,
)
from .extractor import DEFAULT_MAX_TEXT_CHARS


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m skills.serp",
        description="Collect first-page organic results and ranking-page content as JSON.",
    )
    parser.add_argument("--query", required=True, help="Search query.")
    parser.add_argument(
        "--engine", default="google", help=f"Any of: {', '.join(ENGINES)}. Default google."
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=10,
        help=f"Organic results to collect, 1 to {MAX_RESULTS_LIMIT}. Default 10.",
    )
    parser.add_argument(
        "--max-text-chars",
        type=int,
        default=DEFAULT_MAX_TEXT_CHARS,
        help=f"Main-text characters kept per page. Default {DEFAULT_MAX_TEXT_CHARS}.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Navigation timeout per page, in seconds. Default {DEFAULT_TIMEOUT}.",
    )
    parser.add_argument(
        "--headed", action="store_true", help="Show the browser window (for local debugging)."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    try:
        result = collect(
            query=args.query,
            engine=args.engine,
            max_results=args.max_results,
            max_text_chars=args.max_text_chars,
            timeout=args.timeout,
            headless=not args.headed,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except BrowserStartupError as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3
    except SerpError as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 4
    except Exception as exc:  # Any failure must reach the caller as stderr + exit code.
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    # ASCII-only output (non-ASCII is \u-escaped) so it survives any console or pipe encoding.
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
