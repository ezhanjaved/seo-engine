"""Command-line entry point: ``python -m skills.gsc``.

Writes the query result as JSON to stdout. Errors go to stderr with a
non-zero exit code (1 for a failed query, 2 for bad command-line usage).
"""

from __future__ import annotations

import argparse
import json
import sys

from .client import VALID_DIMENSIONS, VALID_FILTER_OPERATORS, query_search_analytics


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m skills.gsc",
        description="Retrieve Google Search Console performance data as JSON.",
    )
    parser.add_argument(
        "--site", required=True, help="Site alias from config/sites.yaml, or an exact GSC property."
    )
    parser.add_argument("--start-date", required=True, help="Inclusive start date, YYYY-MM-DD.")
    parser.add_argument("--end-date", required=True, help="Inclusive end date, YYYY-MM-DD.")
    parser.add_argument(
        "--dimensions",
        nargs="*",
        default=[],
        metavar="DIMENSION",
        help=f"Space- or comma-separated. Any of: {', '.join(VALID_DIMENSIONS)}.",
    )
    parser.add_argument(
        "--filter",
        nargs=3,
        action="append",
        default=[],
        dest="filters",
        metavar=("DIMENSION", "OPERATOR", "EXPRESSION"),
        help=f"Repeatable; all filters must match. Operators: {', '.join(VALID_FILTER_OPERATORS)}.",
    )
    parser.add_argument("--row-limit", type=int, default=1000, help="1 to 25000. Default 1000.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    dimensions = [d for value in args.dimensions for d in value.split(",") if d]
    filters = [
        {"dimension": dimension, "operator": operator, "expression": expression}
        for dimension, operator, expression in args.filters
    ]

    try:
        result = query_search_analytics(
            site=args.site,
            start_date=args.start_date,
            end_date=args.end_date,
            dimensions=dimensions,
            filters=filters,
            row_limit=args.row_limit,
        )
    except Exception as exc:  # Any failure must reach the caller as stderr + exit code.
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    # ASCII-only output (non-ASCII is \u-escaped) so it survives any console or pipe encoding.
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
