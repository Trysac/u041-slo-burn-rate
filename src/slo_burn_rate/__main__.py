"""Command line interface, run with ``python -m slo_burn_rate``."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, NoReturn

from .core import evaluate
from .errors import SLOError
from .inputs import load_policy, load_samples, parse_duration, parse_timestamp
from .models import SLO, AlertResult, Evaluation
from .policy import DEFAULT_POLICY

_OBJECTIVE = re.compile(r"[0-9]{1,3}(\.[0-9]{1,20})?")


class _UsageError(Exception):
    """Raised instead of exiting when the command line is rejected."""


class _Parser(argparse.ArgumentParser):
    """Argument parser that raises instead of printing and exiting on errors."""

    def error(self, message: str) -> NoReturn:
        raise _UsageError(message)


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="slo-burn", description="SLO error budget and burn rate alerts.")
    commands = parser.add_subparsers(dest="command", required=True)
    eval_cmd = commands.add_parser("eval", help="evaluate alert rules over a data file")
    eval_cmd.add_argument("data", help="CSV (at,good,bad) or JSON file")
    eval_cmd.add_argument("--objective", required=True, help="for example 0.999")
    eval_cmd.add_argument("--now", required=True, help="ISO 8601 timestamp with timezone")
    eval_cmd.add_argument("--period", default="30d", help="SLO period such as 30d")
    eval_cmd.add_argument("--policy", help="JSON policy file replacing the default policy")
    eval_cmd.add_argument("--format", choices=("text", "json"), default="text")
    budget_cmd = commands.add_parser("budget", help="print the error budget of an SLO")
    budget_cmd.add_argument("--objective", required=True, help="for example 0.999")
    budget_cmd.add_argument("--period", default="30d", help="SLO period such as 30d")
    return parser


def _make_slo(objective_text: str, period_text: str) -> SLO:
    if _OBJECTIVE.fullmatch(objective_text) is None:
        raise SLOError("input_invalid", message="objective must be a decimal such as 0.999")
    period = parse_duration(period_text)
    if period is None:
        raise SLOError("input_invalid", message="period must look like 30d, 12h or 90m")
    return SLO(float(objective_text), period)


def _format_alert(alert: AlertResult) -> str:
    rule = alert.rule
    state = "FIRING" if alert.firing else "ok"
    long_rate = f"{alert.long_rate:.2f}"
    short_rate = f"{alert.short_rate:.2f}"
    return f"{rule.severity} {rule.name} long={long_rate} short={short_rate} {state}"


def _alert_payload(alert: AlertResult) -> dict[str, Any]:
    rule = alert.rule
    return {
        "name": rule.name,
        "severity": rule.severity,
        "burn_threshold": rule.burn_threshold,
        "long_rate": alert.long_rate,
        "short_rate": alert.short_rate,
        "firing": alert.firing,
    }


def _render_text(result: Evaluation) -> str:
    return "".join(_format_alert(alert) + "\n" for alert in result.alerts)


def _render_json(result: Evaluation) -> str:
    payload: dict[str, Any] = {
        "alerts": [_alert_payload(alert) for alert in result.alerts],
        "budget_remaining": result.budget_remaining,
        "page_firing": result.page_firing,
    }
    return json.dumps(payload, sort_keys=True) + "\n"


def _cmd_eval(args: argparse.Namespace) -> int:
    slo = _make_slo(args.objective, args.period)
    now = parse_timestamp(args.now)
    if now is None:
        raise SLOError("input_invalid", message="--now must be ISO 8601 with a timezone")
    policy = load_policy(Path(args.policy)) if args.policy is not None else DEFAULT_POLICY
    samples = load_samples(Path(args.data))
    result = evaluate(samples, slo, now, policy)
    sys.stdout.write(_render_json(result) if args.format == "json" else _render_text(result))
    return 1 if result.page_firing else 0


def _cmd_budget(args: argparse.Namespace) -> int:
    slo = _make_slo(args.objective, args.period)
    lines = [
        f"objective={slo.objective:.12g}",
        f"period_seconds={int(slo.period.total_seconds())}",
        f"budget_fraction={slo.budget_fraction:.6g}",
        f"allowed_downtime={slo.allowed_downtime}",
    ]
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def _fail(error: SLOError) -> int:
    detail = f"row {error.row}" if error.row is not None else error.message
    sys.stderr.write(f"error: {error.code}: {detail}\n")
    return 2


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return the exit code.

    0: no page alert firing; 1: a page alert is firing; 2: input or usage error.
    """
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except _UsageError as exc:
        return _fail(SLOError("input_invalid", message=str(exc)))
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    try:
        if args.command == "eval":
            return _cmd_eval(args)
        return _cmd_budget(args)
    except SLOError as exc:
        return _fail(exc)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
