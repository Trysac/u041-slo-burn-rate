# slo-burn-rate

[![PyPI version](https://img.shields.io/pypi/v/trysac-slo-burn-rate)](https://pypi.org/project/trysac-slo-burn-rate/)
[![License: MIT](https://img.shields.io/pypi/l/trysac-slo-burn-rate)](LICENSE)
[![CI](https://github.com/Trysac/u041-slo-burn-rate/actions/workflows/ci.yml/badge.svg)](https://github.com/Trysac/u041-slo-burn-rate/actions/workflows/ci.yml)

SLO error budget math and Google SRE multi-window multi-burn-rate alert evaluation as a pure library and a CLI over timestamped good and bad counts

## Problem

Describe in two or three sentences the concrete problem this utility solves, who hits it, and what
they do today without it. Replace this paragraph when the first real feature lands.

## Install

```sh
pip install trysac-slo-burn-rate
# or
uv add trysac-slo-burn-rate
```

Requires Python 3.10 or newer. No runtime dependencies.

## Usage

```python
import slo_burn_rate

# normalize() trims surrounding whitespace and lower-cases the text.
print(slo_burn_rate.normalize("  Hello World "))  # -> "hello world"

# Blank input is rejected explicitly instead of returning an empty string.
try:
    slo_burn_rate.normalize("   ")
except ValueError as exc:
    print(f"rejected: {exc}")
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) and [decisions](docs/decisions/)
- [Testing](docs/TESTING.md) and [security](docs/SECURITY.md)
- [Project record](docs/PROJECT.md) and [stack](docs/STACK.md)
- [Changelog](CHANGELOG.md) and [contributing guide](CONTRIBUTING.md)

## License

[MIT](LICENSE) (c) 2026 Miguel Gomez
