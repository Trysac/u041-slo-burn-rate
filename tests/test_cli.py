"""Tests for the input parsers and the command line interface."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from slo_burn_rate import inputs
from slo_burn_rate.__main__ import main
from slo_burn_rate.inputs import parse_duration, parse_timestamp

NOW_TEXT = "2026-01-01T00:00:00Z"
ROW_FAST = "2025-12-31T23:58:00Z,98,2"
ROW_SLOW = "2025-12-31T23:30:00Z,10000,0"
ROW_TICKET = "2025-12-31T22:00:00Z,9980,20"
JSON_ROW = {"at": "2025-12-31T23:58:00Z", "good": 98, "bad": 2}
OK_LINES = (
    "page page-fast long=0.20 short=20.00 ok\n"
    "page page-slow long=0.20 short=20.00 ok\n"
    "ticket ticket long=0.20 short=0.20 ok\n"
)
FIRING_LINES = (
    "page page-fast long=20.00 short=20.00 FIRING\n"
    "page page-slow long=20.00 short=20.00 FIRING\n"
    "ticket ticket long=20.00 short=20.00 FIRING\n"
)


def _csv(*rows: str) -> str:
    return "\n".join(["at,good,bad", *rows]) + "\n"


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def _run(args, capsys):
    code = main(args)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _eval(path: Path, capsys, *extra: str):
    args = ["eval", str(path), "--objective", "0.999", "--now", NOW_TEXT, *extra]
    return _run(args, capsys)


def _rule(**overrides):
    rule = {
        "name": "custom",
        "burn_threshold": 2,
        "long_window": "1h",
        "short_window": "5m",
        "severity": "page",
    }
    rule.update(overrides)
    return rule


def test_documented_command_line(tmp_path: Path, capsys, monkeypatch) -> None:
    command = "slo-burn eval data.csv --objective 0.999 --now 2026-01-01T00:00:00Z"
    _write(tmp_path, "data.csv", _csv(ROW_FAST, ROW_SLOW))
    monkeypatch.chdir(tmp_path)
    code, out, _ = _run(command.split()[1:], capsys)
    assert code == 0
    assert out.splitlines()[0] == "page page-fast long=0.20 short=20.00 ok"


# --- parsers -----------------------------------------------------------------------


def test_parse_timestamp_accepts_iso8601() -> None:
    assert parse_timestamp("2026-01-01T00:00:00Z") == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert parse_timestamp("2026-01-01 00:00Z") == datetime(2026, 1, 1, tzinfo=timezone.utc)
    parsed = parse_timestamp("2026-01-01T01:30:00.5-05:30")
    assert parsed == datetime(2026, 1, 1, 7, 0, 0, 500000, tzinfo=timezone.utc)
    truncated = parse_timestamp("2026-01-01T00:00:00.123456789Z")
    assert truncated is not None
    assert truncated.microsecond == 123456


@pytest.mark.parametrize(
    "text",
    [
        "2026-01-01",
        "2026-01-01T00:00:00",
        "2026-13-01T00:00:00Z",
        "2026-02-30T00:00:00Z",
        "2026-01-01T24:00:00Z",
        "2026-01-01T00:00:60Z",
        "2026-01-01T00:00:00+24:00",
        "2026-01-01T00:00:00+01:75",
        "2026-01-01T00:00:00.Z",
        "2026-01-01T00:00:00.1234567890Z",
        "2026-01-01T00:00:00z",
        "2026-01-01t00:00:00Z",
        "",
        " 2026-01-01T00:00:00Z",
        "2026-01-01T00:00:00Z\n",
        "2026-01-01T00:00:00Z" + " " * 30,
    ],
)
def test_parse_timestamp_rejects(text: str) -> None:
    assert parse_timestamp(text) is None


def test_parse_duration() -> None:
    assert parse_duration("90m").total_seconds() == 5400
    assert parse_duration("12h").total_seconds() == 43200
    assert parse_duration("30d").total_seconds() == 2592000
    assert parse_duration("999999d") is not None


@pytest.mark.parametrize(
    "text",
    ["0d", "01d", "1000000d", "30", "d", "30w", "-1d", "1 d", "30d\n", "", "1.5h"],
)
def test_parse_duration_rejects(text: str) -> None:
    assert parse_duration(text) is None


# --- eval: happy paths -------------------------------------------------------------


def test_eval_prints_one_line_per_rule_and_exits_zero(tmp_path: Path, capsys) -> None:
    path = _write(tmp_path, "data.csv", _csv(ROW_FAST, ROW_SLOW))
    code, out, err = _eval(path, capsys)
    assert (code, err) == (0, "")
    assert out == OK_LINES
    assert "page page-fast long=0.20 short=20.00 ok" in out


def test_eval_exits_one_when_a_page_rule_fires(tmp_path: Path, capsys) -> None:
    path = _write(tmp_path, "data.csv", _csv(ROW_FAST))
    code, out, err = _eval(path, capsys)
    assert (code, out, err) == (1, FIRING_LINES, "")


def test_eval_ticket_only_firing_exits_zero(tmp_path: Path, capsys) -> None:
    path = _write(tmp_path, "data.csv", _csv(ROW_TICKET))
    code, out, _ = _eval(path, capsys)
    assert code == 0
    assert out.splitlines() == [
        "page page-fast long=0.00 short=0.00 ok",
        "page page-slow long=2.00 short=0.00 ok",
        "ticket ticket long=2.00 short=2.00 FIRING",
    ]


def test_eval_accepts_bom_crlf_and_no_trailing_newline(tmp_path: Path, capsys) -> None:
    content = "\ufeffat,good,bad\r\n" + ROW_FAST + "\r\n" + ROW_SLOW
    path = tmp_path / "data.csv"
    path.write_bytes(content.encode("utf-8"))
    code, out, _ = _eval(path, capsys)
    assert (code, out) == (0, OK_LINES)


def test_eval_json_data_and_extension_case(tmp_path: Path, capsys) -> None:
    rows = [JSON_ROW, {"at": "2025-12-31T23:30:00Z", "good": 10000, "bad": 0}]
    path = _write(tmp_path, "data.JSON", json.dumps(rows))
    code, out, _ = _eval(path, capsys)
    assert (code, out) == (0, OK_LINES)


def test_eval_json_format(tmp_path: Path, capsys) -> None:
    path = _write(tmp_path, "data.csv", _csv(ROW_FAST, ROW_SLOW))
    code, out, _ = _eval(path, capsys, "--period", "1d", "--format", "json")
    assert code == 0
    payload = json.loads(out)
    assert payload["page_firing"] is False
    assert payload["budget_remaining"] == pytest.approx(0.802, rel=1e-3)
    first = payload["alerts"][0]
    assert first["name"] == "page-fast"
    assert first["severity"] == "page"
    assert first["burn_threshold"] == 14.4
    assert first["short_rate"] == pytest.approx(20.0)
    assert first["firing"] is False


def test_eval_with_custom_policy(tmp_path: Path, capsys) -> None:
    data = _write(tmp_path, "data.csv", _csv(ROW_FAST))
    policy = _write(tmp_path, "policy.json", json.dumps([_rule()]))
    code, out, _ = _eval(data, capsys, "--policy", str(policy))
    assert (code, out) == (1, "page custom long=20.00 short=20.00 FIRING\n")


def test_eval_custom_ticket_policy_does_not_page(tmp_path: Path, capsys) -> None:
    data = _write(tmp_path, "data.csv", _csv(ROW_FAST))
    policy = _write(tmp_path, "policy.json", json.dumps([_rule(severity="ticket")]))
    code, out, _ = _eval(data, capsys, "--policy", str(policy))
    assert (code, out) == (0, "ticket custom long=20.00 short=20.00 FIRING\n")


def test_eval_empty_policy_prints_nothing(tmp_path: Path, capsys) -> None:
    data = _write(tmp_path, "data.csv", _csv(ROW_FAST))
    policy = _write(tmp_path, "policy.json", "[]")
    assert _eval(data, capsys, "--policy", str(policy)) == (0, "", "")


def test_eval_header_only_csv_is_empty_data(tmp_path: Path, capsys) -> None:
    path = _write(tmp_path, "data.csv", _csv())
    code, out, _ = _eval(path, capsys)
    assert code == 0
    assert "long=0.00 short=0.00 ok" in out


# --- eval: bad CSV rows ------------------------------------------------------------


def test_eval_reports_the_file_line_of_a_bad_row(tmp_path: Path, capsys) -> None:
    path = _write(tmp_path, "data.csv", _csv(ROW_FAST, "2025-12-31T23:59:00Z,1.5,0"))
    assert _eval(path, capsys) == (2, "", "error: invalid_sample: row 3\n")


def test_eval_reports_crlf_line_numbers(tmp_path: Path, capsys) -> None:
    path = tmp_path / "data.csv"
    path.write_bytes(b"at,good,bad\r\n" + ROW_FAST.encode() + b"\r\nbroken\r\n")
    assert _eval(path, capsys) == (2, "", "error: invalid_sample: row 3\n")


BAD_CSV_ROWS = [
    "2025-12-31T23:58:00Z,1.5,0",
    "2025-12-31T23:58:00Z,1,2,3",
    "2025-12-31T23:58:00Z,1",
    "2025-12-31T23:58:00Z,-1,0",
    "2025-12-31T23:58:00Z,1234567890123456,0",
    "2025-12-31T23:58:00Z,\u0661,0",
    "2025-12-31T23:58:00Z, 1,0",
    "2025-12-31T23:58:00Z,+1,0",
    "2025-12-31T23:58:00Z,1,0x",
    "2025-12-31T23:58:00,1,0",
    "yesterday,1,0",
    ",1,0",
    "",
    '"abc"x,1,1',
    "x" * 200_000 + ",1,1",
]


@pytest.mark.parametrize("row", BAD_CSV_ROWS)
def test_eval_rejects_bad_csv_rows(tmp_path: Path, capsys, row: str) -> None:
    path = _write(tmp_path, "data.csv", _csv(row))
    assert _eval(path, capsys) == (2, "", "error: invalid_sample: row 2\n")


@pytest.mark.parametrize("content", ["", "at,good\n", "AT,good,bad\n", "at,good,bad,extra\n"])
def test_eval_rejects_bad_csv_header(tmp_path: Path, capsys, content: str) -> None:
    path = _write(tmp_path, "data.csv", content)
    code, out, err = _eval(path, capsys)
    assert (code, out) == (2, "")
    assert err.startswith("error: input_invalid:")


# --- eval: bad JSON data -----------------------------------------------------------


@pytest.mark.parametrize(
    "item",
    [
        {**JSON_ROW, "good": 1.5},
        {**JSON_ROW, "good": 1.0},
        {**JSON_ROW, "good": True},
        {**JSON_ROW, "bad": "1"},
        {**JSON_ROW, "bad": -1},
        {**JSON_ROW, "good": 10**15},
        {**JSON_ROW, "extra": 1},
        {**JSON_ROW, "at": 5},
        {**JSON_ROW, "at": "2025-12-31T23:58:00"},
        {"at": JSON_ROW["at"], "good": 1},
        5,
        None,
    ],
)
def test_eval_rejects_bad_json_items(tmp_path: Path, capsys, item: object) -> None:
    path = _write(tmp_path, "data.json", json.dumps([JSON_ROW, item]))
    assert _eval(path, capsys) == (2, "", "error: invalid_sample: row 2\n")


@pytest.mark.parametrize("content", ["{}", "not json", "", "[" * 100_000, "1"])
def test_eval_rejects_bad_json_documents(tmp_path: Path, capsys, content: str) -> None:
    path = _write(tmp_path, "data.json", content)
    code, _, err = _eval(path, capsys)
    assert code == 2
    assert err.startswith("error: input_invalid:")


# --- eval: files and limits --------------------------------------------------------


def test_eval_rejects_unreadable_or_unknown_data_files(tmp_path: Path, capsys) -> None:
    for path in (tmp_path / "missing.csv", tmp_path / "data.txt", tmp_path):
        code, _, err = _eval(path, capsys)
        assert code == 2
        assert err.startswith("error: input_invalid:")
    directory = tmp_path / "dir.csv"
    directory.mkdir()
    code, _, err = _eval(directory, capsys)
    assert code == 2
    assert err.startswith("error: input_invalid:")


def test_eval_rejects_non_utf8_data(tmp_path: Path, capsys) -> None:
    path = tmp_path / "data.csv"
    path.write_bytes(b"at,good,bad\n\xff\xfe,1,1\n")
    code, _, err = _eval(path, capsys)
    assert code == 2
    assert err.startswith("error: input_invalid:")


def test_eval_enforces_the_file_size_limit(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setattr(inputs, "MAX_FILE_BYTES", 10)
    path = _write(tmp_path, "data.csv", _csv(ROW_FAST))
    code, _, err = _eval(path, capsys)
    assert code == 2
    assert err.startswith("error: input_invalid:")


def test_eval_enforces_the_sample_limit(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setattr(inputs, "MAX_SAMPLES", 2)
    csv_path = _write(tmp_path, "data.csv", _csv(ROW_FAST, ROW_FAST, ROW_FAST))
    code, _, err = _eval(csv_path, capsys)
    assert code == 2
    assert err.startswith("error: too_many_samples:")
    json_path = _write(tmp_path, "data.json", json.dumps([JSON_ROW] * 3))
    code, _, err = _eval(json_path, capsys)
    assert code == 2
    assert err.startswith("error: too_many_samples:")
    ok_path = _write(tmp_path, "ok.csv", _csv(ROW_FAST, ROW_FAST))
    assert _eval(ok_path, capsys)[0] == 1


# --- eval: policy files ------------------------------------------------------------


BAD_POLICIES = [
    {},
    [1],
    [{"name": "x"}],
    [_rule(name="bad name")],
    [_rule(name="")],
    [_rule(name=5)],
    [_rule(long_window="1w")],
    [_rule(long_window=3600)],
    [_rule(short_window="2h")],
    [_rule(burn_threshold=True)],
    [_rule(burn_threshold="2")],
    [_rule(burn_threshold=0)],
    [_rule(burn_threshold=10**400)],
    [_rule(severity="sms")],
    [_rule(), _rule()],
]


@pytest.mark.parametrize("policy", BAD_POLICIES)
def test_eval_rejects_bad_policies(tmp_path: Path, capsys, policy: object) -> None:
    data = _write(tmp_path, "data.csv", _csv(ROW_FAST))
    path = _write(tmp_path, "policy.json", json.dumps(policy))
    code, out, err = _eval(data, capsys, "--policy", str(path))
    assert (code, out) == (2, "")
    assert err.startswith("error: invalid_config:")


def test_eval_rejects_infinite_threshold(tmp_path: Path, capsys) -> None:
    data = _write(tmp_path, "data.csv", _csv(ROW_FAST))
    text = json.dumps([_rule(burn_threshold=0)]).replace(
        '"burn_threshold": 0', '"burn_threshold": 1e999'
    )
    path = _write(tmp_path, "policy.json", text)
    code, _, err = _eval(data, capsys, "--policy", str(path))
    assert code == 2
    assert err.startswith("error: invalid_config:")


def test_eval_rejects_unreadable_policies(tmp_path: Path, capsys) -> None:
    data = _write(tmp_path, "data.csv", _csv(ROW_FAST))
    broken = _write(tmp_path, "broken.json", "{")
    binary = tmp_path / "binary.json"
    binary.write_bytes(b"\xff\xfe")
    for path in (broken, binary, tmp_path / "missing.json"):
        code, _, err = _eval(data, capsys, "--policy", str(path))
        assert code == 2
        assert err.startswith("error: input_invalid:")


def test_eval_enforces_policy_limits(tmp_path: Path, capsys, monkeypatch) -> None:
    data = _write(tmp_path, "data.csv", _csv(ROW_FAST))
    two_rules = _write(tmp_path, "two.json", json.dumps([_rule(), _rule(name="other")]))
    monkeypatch.setattr(inputs, "MAX_RULES", 1)
    code, _, err = _eval(data, capsys, "--policy", str(two_rules))
    assert code == 2
    assert err.startswith("error: invalid_config:")
    monkeypatch.setattr(inputs, "MAX_POLICY_BYTES", 5)
    code, _, err = _eval(data, capsys, "--policy", str(two_rules))
    assert code == 2
    assert err.startswith("error: input_invalid:")


# --- arguments and the budget command ----------------------------------------------


def test_budget_command(capsys) -> None:
    code, out, err = _run(["budget", "--objective", "0.999"], capsys)
    assert (code, err) == (0, "")
    assert out == (
        "objective=0.999\nperiod_seconds=2592000\nbudget_fraction=0.001\nallowed_downtime=0:43:12\n"
    )
    code, out, _ = _run(["budget", "--objective", "0.99", "--period", "1d"], capsys)
    assert code == 0
    assert "allowed_downtime=0:14:24" in out


@pytest.mark.parametrize("objective", ["abc", "0.999x", "1e-3", "0.9_9", "-0.5", "", "0."])
def test_budget_rejects_malformed_objective(capsys, objective: str) -> None:
    code, out, err = _run(["budget", "--objective", objective], capsys)
    assert (code, out) == (2, "")
    assert err.startswith("error: input_invalid:")


@pytest.mark.parametrize("objective", ["0", "1", "1.0", "5", "0.0"])
def test_budget_rejects_out_of_range_objective(capsys, objective: str) -> None:
    code, out, err = _run(["budget", "--objective", objective], capsys)
    assert (code, out) == (2, "")
    assert err.startswith("error: invalid_config:")


@pytest.mark.parametrize("period", ["0d", "30w", "30", "1000000d", ""])
def test_budget_rejects_bad_period(capsys, period: str) -> None:
    code, _, err = _run(["budget", "--objective", "0.999", "--period", period], capsys)
    assert code == 2
    assert err.startswith("error: input_invalid:")


@pytest.mark.parametrize("now", ["2026-01-01", "2026-01-01T00:00:00", "not a time", ""])
def test_eval_rejects_bad_now(tmp_path: Path, capsys, now: str) -> None:
    data = _write(tmp_path, "data.csv", _csv(ROW_FAST))
    args = ["eval", str(data), "--objective", "0.999", "--now", now]
    code, _, err = _run(args, capsys)
    assert code == 2
    assert err.startswith("error: input_invalid:")


def test_usage_errors_exit_two(tmp_path: Path, capsys) -> None:
    data = str(_write(tmp_path, "data.csv", _csv(ROW_FAST)))
    bad_calls = [
        [],
        ["bogus"],
        ["eval"],
        ["eval", data],
        ["eval", data, "--objective", "0.999"],
        ["eval", data, "--objective", "0.999", "--now", NOW_TEXT, "--format", "xml"],
        ["budget"],
        ["budget", "--objective", "0.999", "--unknown"],
    ]
    for args in bad_calls:
        code, out, err = _run(args, capsys)
        assert (code, out) == (2, "")
        assert err.startswith("error: input_invalid:")


def test_usage_error_message_is_truncated(capsys) -> None:
    code, _, err = _run(["x" * 1000], capsys)
    assert code == 2
    assert len(err) <= len("error: input_invalid: ") + 200 + 1


def test_help_exits_zero(capsys) -> None:
    code, out, _ = _run(["--help"], capsys)
    assert code == 0
    assert "slo-burn" in out
