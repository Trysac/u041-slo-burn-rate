"""Pure burn rate arithmetic and multi-window, multi-burn-rate alert evaluation."""

from __future__ import annotations

import logging
from bisect import bisect_left
from collections.abc import Sequence
from datetime import datetime, timedelta

from .errors import SLOError
from .models import SLO, AlertResult, AlertRule, Evaluation, Sample, check_aware, check_counts
from .policy import DEFAULT_POLICY

MAX_SAMPLES = 1_000_000
MAX_RULES = 1000

_ZERO = timedelta(0)

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


def _rate(good: int, bad: int, slo: SLO) -> float:
    total = good + bad
    if total == 0:
        return 0.0
    return (bad / total) / slo.budget_fraction


def burn_rate(good: int, bad: int, slo: SLO) -> float:
    """Return how many times faster than allowed the error budget is being spent.

    ``(bad / (good + bad)) / budget_fraction``; ``0.0`` when there are no events.

    Raises:
        SLOError: ``invalid_sample`` if a count is negative, not an int or too large.
    """
    check_counts(good, bad)
    return _rate(good, bad, slo)


def _check_policy(policy: Sequence[AlertRule]) -> None:
    if len(policy) > MAX_RULES:
        raise SLOError("invalid_config", message="policy has too many rules")
    names: set[str] = set()
    for rule in policy:
        if not isinstance(rule, AlertRule):
            raise SLOError("invalid_config", message="policy entries must be AlertRule objects")
        if rule.name in names:
            raise SLOError("invalid_config", message="rule names must be unique")
        names.add(rule.name)


def evaluate(
    samples: Sequence[Sample],
    slo: SLO,
    now: datetime,
    policy: Sequence[AlertRule] = DEFAULT_POLICY,
) -> Evaluation:
    """Evaluate ``policy`` over ``samples`` as of ``now``.

    A sample belongs to a window ``w`` when ``now - w < at <= now``; samples may be
    unsorted and samples after ``now`` are ignored. A rule fires when the burn rate over
    both of its windows is strictly greater than its threshold. ``budget_remaining`` is
    ``1 - burn_rate`` over the SLO period. Time only comes from ``now``.

    Raises:
        SLOError: ``too_many_samples`` above 1_000_000 samples, ``invalid_sample`` for a
            naive timestamp or bad counts, ``invalid_config`` for an invalid policy.
    """
    if len(samples) > MAX_SAMPLES:
        raise SLOError("too_many_samples", message="too many samples")
    check_aware(now)
    _check_policy(policy)
    entries: list[tuple[timedelta, int, int]] = []
    for index, sample in enumerate(samples, start=1):
        if not isinstance(sample, Sample):
            raise SLOError("invalid_sample", row=index, message="samples must be Sample objects")
        check_aware(sample.at, row=index)
        check_counts(sample.good, sample.bad, row=index)
        age = now - sample.at
        if age < _ZERO:
            continue
        entries.append((age, sample.good, sample.bad))
    entries.sort(key=lambda entry: entry[0])
    ages = [entry[0] for entry in entries]
    good_prefix = [0]
    bad_prefix = [0]
    for _, g, b in entries:
        good_prefix.append(good_prefix[-1] + g)
        bad_prefix.append(bad_prefix[-1] + b)

    def window_rate(window: timedelta) -> float:
        count = bisect_left(ages, window)
        return _rate(good_prefix[count], bad_prefix[count], slo)

    results: list[AlertResult] = []
    for rule in policy:
        long_rate = window_rate(rule.long_window)
        short_rate = window_rate(rule.short_window)
        firing = long_rate > rule.burn_threshold and short_rate > rule.burn_threshold
        results.append(AlertResult(rule, long_rate, short_rate, firing))
    remaining = 1.0 - window_rate(slo.period)
    logger.debug("evaluated %d samples against %d rules", len(samples), len(policy))
    return Evaluation(tuple(results), remaining)
