"""Immutable data model and validation for SLO math."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from .errors import SLOError

# Alert severity: ``page`` wakes someone up, ``ticket`` can wait.
Severity = Literal["page", "ticket"]

MAX_COUNT = 999_999_999_999_999
MAX_NAME_LENGTH = 100
DEFAULT_PERIOD = timedelta(days=30)
_ZERO = timedelta(0)


def _config_error(message: str) -> SLOError:
    return SLOError("invalid_config", message=message)


def check_aware(value: object, row: int | None = None) -> None:
    """Raise ``invalid_sample`` unless ``value`` is a timezone-aware datetime."""
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise SLOError("invalid_sample", row=row, message="timestamp must be timezone-aware")


def check_counts(good: object, bad: object, row: int | None = None) -> None:
    """Raise ``invalid_sample`` unless both counts are ints in ``0..MAX_COUNT``."""
    for value in (good, bad):
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_COUNT:
            raise SLOError("invalid_sample", row=row, message="counts must be integers >= 0")


@dataclass(frozen=True)
class SLO:
    """A service level objective over a rolling period.

    Attributes:
        objective: Target success ratio with ``0 < objective < 1``, for example ``0.999``.
        period: Length of the SLO window, strictly positive. Defaults to 30 days.
    """

    objective: float
    period: timedelta = DEFAULT_PERIOD

    def __post_init__(self) -> None:
        objective = self.objective
        if isinstance(objective, bool) or not isinstance(objective, int | float):
            raise _config_error("objective must be a number")
        if not 0 < objective < 1:
            raise _config_error("objective must satisfy 0 < objective < 1")
        if not isinstance(self.period, timedelta) or self.period <= _ZERO:
            raise _config_error("period must be a positive timedelta")

    @property
    def budget_fraction(self) -> float:
        """Fraction of events allowed to fail: ``1 - objective``."""
        return 1 - self.objective

    @property
    def allowed_downtime(self) -> timedelta:
        """Error budget expressed as time, rounded to whole microseconds."""
        return self.period * self.budget_fraction


@dataclass(frozen=True)
class AlertRule:
    """One multi-window burn rate rule.

    The rule fires when the burn rate over both ``long_window`` and ``short_window``
    is strictly greater than ``burn_threshold``.
    """

    name: str
    burn_threshold: float
    long_window: timedelta
    short_window: timedelta
    severity: Severity

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not 0 < len(self.name) <= MAX_NAME_LENGTH:
            raise _config_error("rule name must be 1 to 100 characters")
        threshold = self.burn_threshold
        if isinstance(threshold, bool) or not isinstance(threshold, int | float):
            raise _config_error("burn_threshold must be a number")
        if isinstance(threshold, float) and not math.isfinite(threshold):
            raise _config_error("burn_threshold must be finite")
        if threshold <= 0:
            raise _config_error("burn_threshold must be greater than 0")
        long_window = self.long_window
        short_window = self.short_window
        if not isinstance(long_window, timedelta) or not isinstance(short_window, timedelta):
            raise _config_error("windows must be timedelta values")
        if short_window <= _ZERO or short_window >= long_window:
            raise _config_error("windows must satisfy 0 < short_window < long_window")
        if self.severity not in ("page", "ticket"):
            raise _config_error("severity must be 'page' or 'ticket'")


@dataclass(frozen=True)
class Sample:
    """Good and bad event counts observed at a timezone-aware instant."""

    at: datetime
    good: int
    bad: int

    def __post_init__(self) -> None:
        check_aware(self.at)
        check_counts(self.good, self.bad)


@dataclass(frozen=True)
class AlertResult:
    """Outcome of one rule: burn rates over both windows and whether it fires."""

    rule: AlertRule
    long_rate: float
    short_rate: float
    firing: bool


@dataclass(frozen=True)
class Evaluation:
    """Result of evaluating a policy.

    Attributes:
        alerts: One result per rule, in policy order.
        budget_remaining: ``1 - burn_rate`` over the SLO period (1.0 untouched, < 0 overspent).
    """

    alerts: tuple[AlertResult, ...]
    budget_remaining: float

    @property
    def page_firing(self) -> bool:
        """True when at least one rule with severity ``page`` fires."""
        return any(a.firing and a.rule.severity == "page" for a in self.alerts)
