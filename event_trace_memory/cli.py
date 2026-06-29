"""Command-line entry points for the reference implementation."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional, Sequence, TextIO

from event_trace_memory.fixture_flow import EXPECTED_COVERAGE, load_fixture_corpus, run_fixture_corpus
from event_trace_memory.rholang_deployment import (
    deploy_rholang_contracts,
    load_rholang_deployment_config,
    rholang_deployment_plan,
)


DEFAULT_FIXTURE = Path("tests/fixtures/minimum-corpus-v0.1.json")


def main(argv: Optional[Sequence[str]] = None, stdout: Optional[TextIO] = None, stderr: Optional[TextIO] = None) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "fixture-summary":
            return fixture_summary(args, stdout)
        if args.command == "run-fixture":
            return run_fixture(args, stdout)
        if args.command == "rholang-plan":
            return rholang_plan(args, stdout)
        if args.command == "rholang-deploy":
            return rholang_deploy(args, stdout)
    except Exception as exc:
        stderr.write(f"error: {exc}\n")
        return 1

    parser.print_help(stdout)
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="event-trace-memory")
    subcommands = parser.add_subparsers(dest="command", required=True)

    summary = subcommands.add_parser("fixture-summary", help="print fixture corpus metadata")
    add_fixture_argument(summary)
    summary.add_argument("--pretty", action="store_true", help="pretty-print JSON output")

    run = subcommands.add_parser("run-fixture", help="execute the minimum fixture corpus")
    add_fixture_argument(run)
    run.add_argument("--da-root", help="filesystem DA root; uses a temporary directory when omitted")
    run.add_argument(
        "--section",
        choices=["all", "patterns", "reasoning", "checks"],
        default="all",
        help="limit output to one fixture summary section",
    )
    run.add_argument("--pretty", action="store_true", help="pretty-print JSON output")

    plan = subcommands.add_parser("rholang-plan", help="print a redacted Rholang deployment plan")
    add_rholang_config_argument(plan)
    plan.add_argument("--pretty", action="store_true", help="pretty-print JSON output")

    deploy = subcommands.add_parser("rholang-deploy", help="deploy configured Rholang contracts")
    add_rholang_config_argument(deploy)
    deploy.add_argument("--pretty", action="store_true", help="pretty-print JSON output")

    return parser


def add_fixture_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--fixture",
        default=str(DEFAULT_FIXTURE),
        help=f"fixture corpus JSON path (default: {DEFAULT_FIXTURE})",
    )


def add_rholang_config_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        default="configs/rholang-local-docker.json",
        help="Rholang deployment config JSON path",
    )


def fixture_summary(args: argparse.Namespace, stdout: TextIO) -> int:
    corpus = load_fixture_corpus(args.fixture)
    write_json(
        {
            "kind": corpus["kind"],
            "schema": corpus["schema"],
            "covers": corpus["covers"],
            "expectedCoverage": EXPECTED_COVERAGE,
            "coverageComplete": corpus["covers"] == EXPECTED_COVERAGE,
        },
        stdout,
        pretty=args.pretty,
    )
    return 0


def run_fixture(args: argparse.Namespace, stdout: TextIO) -> int:
    corpus = load_fixture_corpus(args.fixture)
    if args.da_root:
        summary = run_fixture_corpus(corpus, args.da_root)
        summary["ephemeralDaRoot"] = False
        write_json(select_fixture_summary_section(summary, args.section), stdout, pretty=args.pretty)
        return 0

    with tempfile.TemporaryDirectory() as temp_dir:
        summary = run_fixture_corpus(corpus, Path(temp_dir) / "da")
        summary["ephemeralDaRoot"] = True
        write_json(select_fixture_summary_section(summary, args.section), stdout, pretty=args.pretty)
    return 0


def select_fixture_summary_section(summary: dict[str, Any], section: str) -> dict[str, Any]:
    if section == "all":
        return summary

    selected: dict[str, Any] = {
        "ok": summary["ok"],
        "section": section,
        "ephemeralDaRoot": summary["ephemeralDaRoot"],
    }
    if section == "patterns":
        selected["pattern"] = summary["pattern"]
        selected["advancedPatterns"] = summary["advancedPatterns"]
    elif section == "reasoning":
        selected["reasoning"] = summary["reasoning"]
    elif section == "checks":
        selected["checks"] = summary["checks"]
    return selected


def rholang_plan(args: argparse.Namespace, stdout: TextIO) -> int:
    config = load_rholang_deployment_config(args.config)
    write_json(rholang_deployment_plan(config), stdout, pretty=args.pretty)
    return 0


def rholang_deploy(args: argparse.Namespace, stdout: TextIO) -> int:
    config = load_rholang_deployment_config(args.config)
    result = deploy_rholang_contracts(config)
    write_json(
        {
            "ok": True,
            "deployIds": [deploy.deploy_id for deploy in result.deploys],
            "blockHash": result.propose.block_hash if result.propose else None,
        },
        stdout,
        pretty=args.pretty,
    )
    return 0


def write_json(value: dict[str, Any], stdout: TextIO, *, pretty: bool) -> None:
    if pretty:
        stdout.write(json.dumps(value, sort_keys=True, indent=2))
    else:
        stdout.write(json.dumps(value, sort_keys=True, separators=(",", ":")))
    stdout.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
