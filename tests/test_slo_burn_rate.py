"""Tests for the pure SLO math and the alert evaluation."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest

import slo_burn_rate
from slo_burn_rate import DEFAULT_POLICY, SLO, AlertRule, Sample, burn_rate, evaluate
from slo_burn_rate.errors import SLOError


def test_many_rules_many_samples_is_fast() -> None:
    import time

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    samples = [Sample(now - timedelta(seconds=i), good=1, bad=0) for i in range(200_000)]
    rules = [
        AlertRule(f"r{i}", 1.0, timedelta(minutes=i + 2), timedelta(minutes=1), "ticket")
        for i in range(1000)
    ]
    start = time.monotonic()
    result = evaluate(samples, SLO(0.99), now, rules)
    assert len(result.alerts) == 1000
    assert time.monotonic() - start < 5


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)
FIVE_MINUTES = timedelta(minutes=5)


def _alert(result, name):
    for alert in result.alerts:
        if alert.rule.name == name:
            return alert
    raise AssertionError(name)


def _raw_sample(at, good, bad):
    sample = object.__new__(Sample)
    object.__setattr__(sample, "at", at)
    object.__setattr__(sample, "good", good)
    object.__setattr__(sample, "bad", bad)
    return sample


def test_public_api_and_null_handler() -> None:
    assert slo_burn_rate.__version__ == "0.1.0"
    for name in slo_burn_rate.__all__:
        assert hasattr(slo_burn_rate, name)
    handlers = logging.getLogger("slo_burn_rate").handlers
    assert any(isinstance(handler, logging.NullHandler) for handler in handlers)


def test_error_carries_code_row_and_truncated_message() -> None:
    error = SLOError("invalid_sample", row=4, message="x" * 500)
    assert error.code == "invalid_sample"
    assert error.row == 4
    assert len(error.message) == 200
    assert str(error) == error.message
    assert SLOError("input_invalid").message == "input_invalid"
    assert SLOError("input_invalid").row is None


def test_slo_budget_fraction_and_allowed_downtime() -> None:
    slo = SLO(0.999, timedelta(days=30))
    assert slo.budget_fraction == pytest.approx(0.001, rel=1e-12)
    assert slo.allowed_downtime == timedelta(minutes=43, seconds=12)
    assert SLO(0.99999).allowed_downtime == timedelta(seconds=25, microseconds=920000)
    assert SLO(0.99).period == timedelta(days=30)


@pytest.mark.parametrize("objective", [1.0, 0.0, -0.5, 1.5, float("nan"), True, "0.9"])
def test_slo_rejects_invalid_objective(objective: object) -> None:
    with pytest.raises(SLOError) as info:
        SLO(objective)
    assert info.value.code == "invalid_config"


@pytest.mark.parametrize("period", [timedelta(0), timedelta(days=-1), 30])
def test_slo_rejects_invalid_period(period: object) -> None:
    with pytest.raises(SLOError) as info:
        SLO(0.99, period)
    assert info.value.code == "invalid_config"


def test_burn_rate_values() -> None:
    assert burn_rate(990, 10, SLO(0.99)) == pytest.approx(1.0, rel=1e-12)
    assert burn_rate(0, 0, SLO(0.99)) == 0.0
    assert burn_rate(0, 5, SLO(0.99)) == pytest.approx(100.0)


@pytest.mark.parametrize(
    ("good", "bad"),
    [(-1, 0), (0, -1), (1.5, 0), (0, 2.5), (True, 0), ("1", 0), (10**15, 0)],
)
def test_invalid_counts_are_rejected(good: object, bad: object) -> None:
    with pytest.raises(SLOError) as info:
        burn_rate(good, bad, SLO(0.99))
    assert info.value.code == "invalid_sample"
    with pytest.raises(SLOError) as info:
        Sample(NOW, good, bad)
    assert info.value.code == "invalid_sample"


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(SLOError) as info:
        Sample(datetime(2026, 1, 1), good=1, bad=1)
    assert info.value.code == "invalid_sample"
    with pytest.raises(SLOError) as info:
        Sample("2026-01-01", good=1, bad=1)
    assert info.value.code == "invalid_sample"
    with pytest.raises(SLOError) as info:
        evaluate([], SLO(0.99), datetime(2026, 1, 1))
    assert info.value.code == "invalid_sample"


def test_negative_count_literal() -> None:
    with pytest.raises(SLOError) as info:
        Sample(NOW, good=-1, bad=0)
    assert info.value.code == "invalid_sample"


def test_default_policy_matches_the_sre_workbook() -> None:
    expected = (
        AlertRule("page-fast", 14.4, timedelta(hours=1), timedelta(minutes=5), "page"),
        AlertRule("page-slow", 6.0, timedelta(hours=6), timedelta(minutes=30), "page"),
        AlertRule("ticket", 1.0, timedelta(days=3), timedelta(hours=6), "ticket"),
    )
    assert expected == DEFAULT_POLICY


def test_fast_burn_fires_and_long_window_dilutes_it() -> None:
    slo = SLO(0.999)
    fast = Sample(NOW - timedelta(minutes=2), good=98, bad=2)
    alert = _alert(evaluate([fast], slo, NOW), "page-fast")
    assert alert.firing
    assert alert.long_rate == pytest.approx(20.0)
    assert alert.short_rate == pytest.approx(20.0)
    healthy = Sample(NOW - timedelta(minutes=30), good=10_000, bad=0)
    diluted = _alert(evaluate([fast, healthy], slo, NOW), "page-fast")
    assert diluted.long_rate == pytest.approx(0.198, rel=1e-3)
    assert diluted.short_rate == pytest.approx(20.0)
    assert not diluted.firing


def test_both_windows_are_required_when_only_the_long_one_burns() -> None:
    slo = SLO(0.999)
    old = Sample(NOW - timedelta(minutes=10), good=98, bad=2)
    alert = _alert(evaluate([old], slo, NOW), "page-fast")
    assert alert.long_rate == pytest.approx(20.0)
    assert alert.short_rate == 0.0
    assert not alert.firing


def test_rate_equal_to_threshold_does_not_fire() -> None:
    rule = AlertRule("edge", 2.0, HOUR, FIVE_MINUTES, "page")
    sample = Sample(NOW - timedelta(minutes=1), good=1, bad=1)
    alert = evaluate([sample], SLO(0.75), NOW, [rule]).alerts[0]
    assert alert.long_rate == 2.0
    assert alert.short_rate == 2.0
    assert not alert.firing


def test_window_boundaries() -> None:
    slo = SLO(0.99)
    rule = AlertRule("w", 0.5, HOUR, FIVE_MINUTES, "page")
    outside = Sample(NOW - HOUR, good=0, bad=1)
    inside = Sample(NOW, good=0, bad=1)
    future = Sample(NOW + timedelta(seconds=1), good=0, bad=1)
    only_outside = evaluate([outside], slo, NOW, [rule]).alerts[0]
    assert only_outside.long_rate == 0.0
    assert not only_outside.firing
    only_future = evaluate([future], slo, NOW, [rule]).alerts[0]
    assert only_future.long_rate == 0.0
    both = evaluate([future, outside, inside], slo, NOW, [rule]).alerts[0]
    assert both.long_rate == pytest.approx(100.0)
    assert both.short_rate == pytest.approx(100.0)
    assert both.firing
    edge = Sample(NOW - FIVE_MINUTES, good=0, bad=1)
    short_edge = evaluate([edge], slo, NOW, [rule]).alerts[0]
    assert short_edge.long_rate == pytest.approx(100.0)
    assert short_edge.short_rate == 0.0
    assert not short_edge.firing


def test_samples_need_not_be_sorted() -> None:
    slo = SLO(0.99)
    samples = [Sample(NOW - timedelta(minutes=i), good=9, bad=1) for i in (4, 1, 3, 2, 0)]
    forward = evaluate(samples, slo, NOW)
    backward = evaluate(list(reversed(samples)), slo, NOW)
    assert forward == backward
    assert _alert(forward, "page-fast").long_rate == pytest.approx(10.0)


def test_many_samples_are_summed() -> None:
    samples = [Sample(NOW - timedelta(seconds=i), 99, 1) for i in range(1000)]
    alert = _alert(evaluate(samples, SLO(0.99), NOW), "ticket")
    assert alert.long_rate == pytest.approx(1.0)


def test_empty_windows_do_not_fire() -> None:
    result = evaluate([], SLO(0.999), NOW)
    assert result.budget_remaining == 1.0
    assert not result.page_firing
    assert len(result.alerts) == 3
    for alert in result.alerts:
        assert alert.long_rate == 0.0
        assert alert.short_rate == 0.0
        assert not alert.firing
    assert evaluate([], SLO(0.999), NOW, []).alerts == ()


def test_page_firing_ignores_ticket_rules() -> None:
    rule = AlertRule("only-ticket", 1.0, HOUR, FIVE_MINUTES, "ticket")
    sample = Sample(NOW, good=0, bad=1)
    result = evaluate([sample], SLO(0.99), NOW, [rule])
    assert result.alerts[0].firing
    assert not result.page_firing


def test_budget_remaining_over_the_period() -> None:
    slo = SLO(0.99)
    mixed = evaluate([Sample(NOW, good=995, bad=5)], slo, NOW)
    assert mixed.budget_remaining == pytest.approx(0.5)
    assert evaluate([], slo, NOW).budget_remaining == 1.0
    overspent = evaluate([Sample(NOW, good=0, bad=10)], slo, NOW)
    assert overspent.budget_remaining == pytest.approx(-99.0)


def test_budget_ignores_samples_outside_the_period() -> None:
    slo = SLO(0.99, timedelta(days=1))
    old = Sample(NOW - timedelta(days=2), good=0, bad=10)
    assert evaluate([old], slo, NOW).budget_remaining == 1.0
    recent = Sample(NOW - timedelta(hours=23), good=0, bad=10)
    assert evaluate([old, recent], slo, NOW).budget_remaining == pytest.approx(-99.0)


@pytest.mark.parametrize(
    ("name", "threshold", "long_window", "short_window", "severity"),
    [
        ("r", 1.0, HOUR, HOUR, "page"),
        ("r", 1.0, HOUR, timedelta(hours=2), "page"),
        ("r", 1.0, HOUR, timedelta(0), "page"),
        ("r", 0, HOUR, FIVE_MINUTES, "page"),
        ("r", -1.0, HOUR, FIVE_MINUTES, "page"),
        ("r", float("nan"), HOUR, FIVE_MINUTES, "page"),
        ("r", float("inf"), HOUR, FIVE_MINUTES, "page"),
        ("r", True, HOUR, FIVE_MINUTES, "page"),
        ("r", "1", HOUR, FIVE_MINUTES, "page"),
        ("", 1.0, HOUR, FIVE_MINUTES, "page"),
        ("x" * 101, 1.0, HOUR, FIVE_MINUTES, "page"),
        (5, 1.0, HOUR, FIVE_MINUTES, "page"),
        ("r", 1.0, 3600, 300, "page"),
        ("r", 1.0, HOUR, FIVE_MINUTES, "sms"),
    ],
)
def test_invalid_rules_are_rejected(
    name: object,
    threshold: object,
    long_window: object,
    short_window: object,
    severity: object,
) -> None:
    with pytest.raises(SLOError) as info:
        AlertRule(name, threshold, long_window, short_window, severity)
    assert info.value.code == "invalid_config"


def test_duplicate_rule_names_are_rejected() -> None:
    rule = AlertRule("same", 1.0, HOUR, FIVE_MINUTES, "page")
    with pytest.raises(SLOError) as info:
        evaluate([], SLO(0.99), NOW, [rule, rule])
    assert info.value.code == "invalid_config"


def test_policy_entries_and_size_are_checked() -> None:
    with pytest.raises(SLOError) as info:
        evaluate([], SLO(0.99), NOW, [object()])
    assert info.value.code == "invalid_config"
    rules = [AlertRule(f"r{i}", 1.0, HOUR, FIVE_MINUTES, "page") for i in range(1001)]
    with pytest.raises(SLOError) as info:
        evaluate([], SLO(0.99), NOW, rules)
    assert info.value.code == "invalid_config"
    assert len(evaluate([], SLO(0.99), NOW, rules[:1000]).alerts) == 1000


def test_too_many_samples() -> None:
    samples = [Sample(NOW, good=1, bad=0)] * 1_000_001
    with pytest.raises(SLOError) as info:
        evaluate(samples, SLO(0.999), NOW)
    assert info.value.code == "too_many_samples"


def test_evaluate_revalidates_samples() -> None:
    good = Sample(NOW, good=1, bad=0)
    with pytest.raises(SLOError) as info:
        evaluate([good, object()], SLO(0.99), NOW)
    assert (info.value.code, info.value.row) == ("invalid_sample", 2)
    with pytest.raises(SLOError) as info:
        evaluate([good, _raw_sample(datetime(2026, 1, 1), 1, 1)], SLO(0.99), NOW)
    assert (info.value.code, info.value.row) == ("invalid_sample", 2)
    with pytest.raises(SLOError) as info:
        evaluate([_raw_sample(NOW, -1, 1)], SLO(0.99), NOW)
    assert (info.value.code, info.value.row) == ("invalid_sample", 1)
