# Testing

## Running

```sh
uv run pytest --cov=slo_burn_rate   # tests with coverage report
uv run python scripts/check.py      # every gate, as CI and the factory run it
```

## Policy

- Branch coverage of `src/slo_burn_rate` must stay at or above 80 %; the gate fails below it.
- Tests exercise the public API (`import slo_burn_rate`) and assert observable effects: return values, raised exceptions and their codes.
- Tests are deterministic: no network, no wall clock, no dependence on test order.

## Layout

`tests/test_<module>.py` mirrors each public module under `src/slo_burn_rate/`. Shared fixtures go in `tests/conftest.py`.
