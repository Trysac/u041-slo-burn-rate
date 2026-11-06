# Pure evaluation core with validated immutable models and a thin, hardened CLI

Status: accepted (generated, pending human review)

## Context

Teams alert on raw error counts. The Google SRE Workbook multi-window, multi-burn-rate method fixes that, but the window pairing and the burn rate arithmetic are easy to get wrong. The library must be deterministic and testable, with time always passed in, and must be safe to run on untrusted CSV, JSON and policy files.

## Decision

Keep the core pure: frozen dataclasses (SLO, AlertRule, Sample, AlertResult, Evaluation) validate on construction and evaluate() performs no I/O and never reads a clock. Windows are the half-open interval now - w < at <= now, summed in a single pass over the samples, and a rule fires only when both burn rates are strictly greater than the threshold. The default policy is data in policy.py citing the SRE Workbook. All parsing of untrusted input (durations, ISO 8601 subset, CSV, JSON, policy files) lives in inputs.py with named limits (50 MB data, 1 MB policy, 1,000,000 samples, 1,000 rules) and raises the single SLOError type with a stable code. The CLI in __main__.py maps errors to exit code 2 and never lets argparse exit the process.

## Consequences

The math is easy to test exhaustively and reuse. Invalid objects cannot exist, but callers building objects by bypassing the constructors are still re-validated inside evaluate(). Strict input formats reject some inputs other tools would accept (for example naive timestamps, float counts, 'z' in lower case). Evaluation costs O(samples x windows) with a hard cap on samples. Registering a slo-burn console script needs a pyproject.toml change by a human; until then the CLI runs as python -m slo_burn_rate.
