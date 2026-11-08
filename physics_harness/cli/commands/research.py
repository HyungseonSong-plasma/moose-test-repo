"""Thin CLI for opt-in Research Mode v0.1 human goal clarification."""
from __future__ import annotations

import argparse
import json
import sys

from physics_harness.application import research_session as research
from physics_harness.specification.research_objective import EVALUATION_SCOPES

ADMITTED_ANALYSIS_COMMANDS = frozenset({"default-plot", "oxygen-profile", "temporal-csv"})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="physics research")
    subs = parser.add_subparsers(dest="action", required=True)

    p = subs.add_parser("start", help="register a dataset and ask the research objective")
    p.add_argument("data")
    p.add_argument("--session", required=True)
    p.add_argument("--reuse-from", help="propose (not auto-approve) a previous confirmed goal")

    p = subs.add_parser("goal", help="record operator goal; ask about evaluation scope if missing")
    p.add_argument("session")
    p.add_argument("--objective", required=True)
    p.add_argument("--scope", choices=sorted(EVALUATION_SCOPES))
    p.add_argument("--scope-detail")

    p = subs.add_parser("scope", help="clarify evaluation boundary before explicit approval")
    p.add_argument("session")
    p.add_argument("--scope", required=True, choices=sorted(EVALUATION_SCOPES))
    p.add_argument("--scope-detail")

    p = subs.add_parser("confirm", help="explicitly accept or reject a proposed research goal")
    p.add_argument("session")
    choices = p.add_mutually_exclusive_group(required=True)
    choices.add_argument("--approve", action="store_true")
    choices.add_argument("--reject", action="store_true")

    p = subs.add_parser("status", help="show status, provenance and next human question")
    p.add_argument("session")

    p = subs.add_parser("check", help="fail closed unless goal is confirmed and dataset unchanged")
    p.add_argument("session")

    p = subs.add_parser("execute", help="execute an explicitly selected analysis only after approval")
    p.add_argument("session")
    p.add_argument("command", choices=sorted(ADMITTED_ANALYSIS_COMMANDS))
    p.add_argument("arguments", nargs=argparse.REMAINDER)

    args = parser.parse_args(argv)
    try:
        if args.action == "start":
            result = research.start(args.data, args.session, reuse_from=args.reuse_from)
        elif args.action == "goal":
            result = research.submit_goal(
                args.session, args.objective, scope=args.scope, scope_detail=args.scope_detail
            )
        elif args.action == "scope":
            result = research.clarify_scope(
                args.session, args.scope, scope_detail=args.scope_detail
            )
        elif args.action == "confirm":
            result = research.confirm(args.session, approve=args.approve)
        elif args.action == "status":
            result = research.status(args.session)
        else:
            result = research.require_analysis_ready(args.session)
    except (research.ResearchModeError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"RESEARCH_MODE_BLOCKED: {exc}", file=sys.stderr)
        return 3 if args.action in {"check", "execute"} else 2
    if args.action == "execute":
        # The command-specific numerical pipeline retains ownership of analysis.
        # Do not run arbitrary shell, other Physics commands, or local solver fallback.
        from physics_harness.cli.app import main as physics_main

        return physics_main([args.command, *args.arguments])
    print(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False))
    return 0


__all__ = ["main", "ADMITTED_ANALYSIS_COMMANDS"]
