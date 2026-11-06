# slo-burn-rate

[![PyPI version](https://img.shields.io/pypi/v/trysac-slo-burn-rate)](https://pypi.org/project/trysac-slo-burn-rate/)
[![License: MIT](https://img.shields.io/pypi/l/trysac-slo-burn-rate)](LICENSE)
[![CI](https://github.com/Trysac/u041-slo-burn-rate/actions/workflows/ci.yml/badge.svg)](https://github.com/Trysac/u041-slo-burn-rate/actions/workflows/ci.yml)

SLO error budget math and Google SRE multi-window, multi-burn-rate alert evaluation as a pure library and a CLI over timestamped good and bad counts.

## Problem

Teams define availability SLOs but alert on raw error counts, which either pages constantly or misses slow budget burn. The multi-window, multi-burn-rate method from the Google SRE Workbook (chapter 5) fixes that, but the arithmetic and window pairing are easy to get wrong. This library computes budgets and burn rates and evaluates the standard policy deterministically; time is always passed in.

## Install

```sh
pip install trysac-slo-burn-rate
# or
uv add trysac-slo-burn-rate
```

Requires Python 3.10 or newer. No runtime dependencies.

## Usage

```python
from datetime import datetime, timedelta, timezone

from slo_burn_rate import SLO, Sample, evaluate

now = datetime(2026, 1, 1, tzinfo=timezone.utc)
samples = [Sample(now - timedelta(minutes=2), good=98, bad=2)]
result = evaluate(samples, SLO(0.999), now)
for alert in result.alerts:
    print(alert.rule.name, round(alert.long_rate, 2), alert.firing)
```

## API summary

- `SLO(objective, period=timedelta(days=30))`: frozen dataclass; `objective` must satisfy `0 < objective < 1`, `period` must be positive. Properties `budget_fraction` (`1 - objective`) and `allowed_downtime`.
- `AlertRule(name, burn_threshold, long_window, short_window, severity)`: `severity` is `'page'` or `'ticket'`; `short_window` must be shorter than `long_window`; names must be 1 to 100 characters.
- `Sample(at, good, bad)`: `at` must be timezone-aware; counts are non-negative integers.
- `burn_rate(good, bad, slo)`: `(bad / (good + bad)) / budget_fraction`, `0.0` when there are no events.
- `evaluate(samples, slo, now, policy=DEFAULT_POLICY)`: returns `Evaluation(alerts, budget_remaining)`. A rule fires when both the long and short burn rates are strictly greater than its threshold. A sample belongs to window `w` when `now - w < at <= now`; samples after `now` are ignored.
- `DEFAULT_POLICY`: the Google SRE Workbook rules `page-fast` (14.4, 1 h / 5 min), `page-slow` (6, 6 h / 30 min) and `ticket` (1, 3 d / 6 h).
- `SLOError(code, row=None, message='')`: `code` is one of `invalid_config`, `invalid_sample`, `too_many_samples`, `input_invalid`. Evaluation accepts at most 1,000,000 samples and policies at most 1000 rules.

## CLI

```sh
python -m slo_burn_rate eval data.csv --objective 0.999 --now 2026-01-01T00:00:00Z [--period 30d] [--policy policy.json] [--format text|json]
python -m slo_burn_rate budget --objective 0.999 [--period 30d]
```

Each rule prints `<severity> <name> long=<rate> short=<rate> FIRING|ok`.

Exit codes: `0` no page alert firing, `1` a page alert firing, `2` input or usage error (for example `error: invalid_sample: row 3`).

- Data: CSV with header `at,good,bad`, or JSON `[{"at": ..., "good": 1, "bad": 0}]` with integer counts, chosen by file extension (at most 50 MB). Timestamps must be timezone-aware ISO 8601 (`Z` or a numeric offset).
- Durations match `<n>m|h|d`, e.g. `30d`.
- Policy: JSON list of `{name, burn_threshold, long_window, short_window, severity}`.

## Why not Sloth or Pyrra

Sloth and Pyrra generate Prometheus alerting rules. This library is the testable math behind the same method and does not query Prometheus or emit rule YAML.

## Security

See [docs/SECURITY.md](docs/SECURITY.md).

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Testing](docs/TESTING.md) and [security](docs/SECURITY.md)
- [Project record](docs/PROJECT.md) and [stack](docs/STACK.md)

## License

[MIT](LICENSE) (c) 2026 Miguel Gomez
