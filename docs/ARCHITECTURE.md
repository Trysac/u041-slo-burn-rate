# Architecture

## Purpose

`trysac-slo-burn-rate` is a small, dependency-free Python package: SLO error budget math and Google SRE multi-window, multi-burn-rate alert evaluation, as a pure library and a CLI over timestamped good and bad counts.

## Shape

```text
caller code --> slo_burn_rate (public API in __init__.py)
                    |
                    +-- core.py: burn_rate, evaluate (pure, no I/O)
                    +-- models.py: SLO, AlertRule, Sample, results (frozen dataclasses)
                    +-- policy.py: DEFAULT_POLICY (data)
                    +-- inputs.py: durations, timestamps, CSV/JSON/policy file parsing
                    +-- __main__.py: CLI (eval, budget)
```

- **Public API**: the names listed in `__all__` of `src/slo_burn_rate/__init__.py`: `DEFAULT_POLICY`, `SLO`, `AlertResult`, `AlertRule`, `Evaluation`, `SLOError`, `Sample`, `burn_rate`, `evaluate`, `__version__`.
- **Errors**: invalid input raises `SLOError` with a stable `code`. The library core never prints or exits.
- **Side effects**: the core has none. File reading lives only in `inputs.py` (`load_samples`, `load_policy`) and the CLI writes to stdout and stderr. The library logs through `logging.getLogger(__name__)` with a `NullHandler` and never configures logging.
- **Time**: only the `now` argument is used; the code never reads the wall clock.

## Decisions

Architecture decisions are recorded in `docs/decisions/` as numbered ADRs.
