# Project record

## Objective

Provide SLO error budget math and Google SRE multi-window, multi-burn-rate alert evaluation as a pure, typed, tested Python library and a CLI over timestamped good and bad counts. The problem: teams alert on raw error counts, which either pages constantly or misses slow budget burn, and the window pairing of the standard method is easy to get wrong.

## Scope

- In scope: SLO and alert rule data model with validation; `burn_rate` and `evaluate` with the default policy as data (Google SRE Workbook, chapter 5, approach 6); CSV and JSON sample input and JSON policy input with size and count limits; the `eval` and `budget` CLI commands.
- Out of scope: querying Prometheus, generating alert rule YAML, latency SLOs, runtime dependencies, and any I/O in the core functions.

## Timeline

| Date | Event |
|---|---|
| 2026 | Repository created from the factory utility template. |

## Effort metrics

Measured values only; a value that has not been measured stays "pending measurement".

| Metric | Value |
|---|---|
| Tokens (input / output) | 560022 / 92281 |
| Hours (human) | pending measurement |
| Cost (USD) | 0.8155 |

## Factory run u041 (measured from API usage)

| Phase | Model | Batch | Input | Output | Cache write | Cache read | Cost (USD) |
|---|---|---|---|---|---|---|---|
| generation | claude-sonnet-5-5 | yes | 2793 | 76633 | 0 | 4246 | 0.3864 |
| fix-1 | claude-sonnet-5-5 | no | 4 | 868 | 7135 | 25248 | 0.0291 |
| fix-2 | claude-sonnet-5-5 | no | 6 | 506 | 6365 | 40228 | 0.0250 |
| fix-3 | claude-sonnet-5-5 | no | 8 | 884 | 7651 | 56433 | 0.0336 |
| audit | claude-sonnet-5-5 | no | 14 | 4806 | 46114 | 201392 | 0.1835 |
| fix-4 | claude-sonnet-5-5 | no | 12 | 4159 | 14478 | 114482 | 0.0893 |
| docs | claude-haiku-5-5 | no | 115156 | 4425 | 0 | 0 | 0.0686 |

Total: $0.8155. Prices: Anthropic list prices.
