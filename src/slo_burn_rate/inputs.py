"""Parsing of untrusted inputs: durations, timestamps, data files and policy files."""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .core import MAX_RULES, MAX_SAMPLES
from .errors import SLOError
from .models import MAX_COUNT, AlertRule, Sample

MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_POLICY_BYTES = 1024 * 1024
MAX_TIMESTAMP_LENGTH = 40

_DURATION = re.compile(r"([1-9][0-9]{0,5})(m|h|d)")
_COUNT = re.compile(r"[0-9]{1,15}")
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
_DATE = r"([0-9]{4})-([0-9]{2})-([0-9]{2})"
_TIME = r"([0-9]{2}):([0-9]{2})(?::([0-9]{2})(?:\.([0-9]{1,9}))?)?"
_ZONE = r"(Z|[+-][0-9]{2}:[0-9]{2})"
_TIMESTAMP = re.compile(_DATE + "[T ]" + _TIME + _ZONE)
_RULE_KEYS = frozenset({"name", "burn_threshold", "long_window", "short_window", "severity"})
_SAMPLE_KEYS = frozenset({"at", "good", "bad"})


def parse_duration(text: str) -> timedelta | None:
    """Parse ``<n>m``, ``<n>h`` or ``<n>d`` (1 to 999999, no leading zero); ``None`` if invalid."""
    match = _DURATION.fullmatch(text)
    if match is None:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "h":
        return timedelta(hours=amount)
    return timedelta(days=amount)


def parse_timestamp(text: str) -> datetime | None:
    """Parse an ISO 8601 timestamp that carries ``Z`` or a numeric UTC offset.

    Returns ``None`` for anything else, including naive timestamps and impossible dates.
    Fractional seconds beyond microseconds are truncated.
    """
    if len(text) > MAX_TIMESTAMP_LENGTH:
        return None
    match = _TIMESTAMP.fullmatch(text)
    if match is None:
        return None
    year, month, day, hour, minute, second, fraction, zone = match.groups()
    micro = int((fraction or "")[:6].ljust(6, "0"))
    offset = timedelta(0)
    if zone != "Z":
        if int(zone[4:6]) > 59:
            return None
        sign = -1 if zone[0] == "-" else 1
        offset = sign * timedelta(hours=int(zone[1:3]), minutes=int(zone[4:6]))
    try:
        return datetime(
            int(year),
            int(month),
            int(day),
            int(hour),
            int(minute),
            int(second or 0),
            micro,
            tzinfo=timezone(offset),
        )
    except ValueError:
        return None


def _read_limited(path: Path, limit: int) -> bytes:
    try:
        with path.open("rb") as handle:
            data = handle.read(limit + 1)
    except OSError as exc:
        raise SLOError("input_invalid", message="cannot read input file") from exc
    if len(data) > limit:
        raise SLOError("input_invalid", message="input file exceeds the size limit")
    return data


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SLOError("input_invalid", message="input is not valid UTF-8") from exc


def _row_error(row: int) -> SLOError:
    return SLOError("invalid_sample", row=row, message=f"row {row} is invalid")


def _csv_sample(fields: list[str], row: int) -> Sample:
    if len(fields) != 3:
        raise _row_error(row)
    at_text, good_text, bad_text = fields
    at = parse_timestamp(at_text)
    if at is None or not _COUNT.fullmatch(good_text) or not _COUNT.fullmatch(bad_text):
        raise _row_error(row)
    return Sample(at, int(good_text), int(bad_text))


def parse_csv(text: str) -> list[Sample]:
    """Parse CSV text with the exact header ``at,good,bad`` into samples.

    Raises:
        SLOError: ``input_invalid`` for a bad header, ``invalid_sample`` (with the 1-based
            file line as ``row``) for a bad row, ``too_many_samples`` above the limit.
    """
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    samples: list[Sample] = []
    try:
        header = next(reader, None)
        if header != ["at", "good", "bad"]:
            raise SLOError("input_invalid", message="CSV header must be exactly at,good,bad")
        for fields in reader:
            samples.append(_csv_sample(fields, reader.line_num))
            if len(samples) > MAX_SAMPLES:
                raise SLOError("too_many_samples", message="too many samples")
    except csv.Error as exc:
        raise _row_error(reader.line_num) from exc
    return samples


def _is_count(value: Any) -> bool:
    return type(value) is int and 0 <= value <= MAX_COUNT


def _json_sample(item: Any, row: int) -> Sample:
    if not isinstance(item, dict) or set(item) != _SAMPLE_KEYS:
        raise _row_error(row)
    at_text = item["at"]
    at = parse_timestamp(at_text) if isinstance(at_text, str) else None
    if at is None or not _is_count(item["good"]) or not _is_count(item["bad"]):
        raise _row_error(row)
    return Sample(at, item["good"], item["bad"])


def _loads(text: str) -> Any:
    try:
        return json.loads(text)
    except (ValueError, RecursionError) as exc:
        raise SLOError("input_invalid", message="input is not valid JSON") from exc


def parse_json(text: str) -> list[Sample]:
    """Parse a JSON array of ``{at, good, bad}`` objects with integer counts.

    The ``row`` of an ``invalid_sample`` error is the 1-based array index.
    """
    payload = _loads(text)
    if not isinstance(payload, list):
        raise SLOError("input_invalid", message="JSON data must be an array of objects")
    if len(payload) > MAX_SAMPLES:
        raise SLOError("too_many_samples", message="too many samples")
    return [_json_sample(item, row) for row, item in enumerate(payload, start=1)]


def load_samples(path: Path) -> list[Sample]:
    """Load samples from a ``.csv`` or ``.json`` file (at most 50 MB), chosen by extension."""
    suffix = path.suffix.lower()
    if suffix not in (".csv", ".json"):
        raise SLOError("input_invalid", message="data file must end in .csv or .json")
    text = _decode(_read_limited(path, MAX_FILE_BYTES))
    if suffix == ".csv":
        return parse_csv(text)
    return parse_json(text)


def _window(value: Any) -> timedelta:
    parsed = parse_duration(value) if isinstance(value, str) else None
    if parsed is None:
        raise SLOError("invalid_config", message="windows must look like 5m, 6h or 3d")
    return parsed


def _json_rule(item: Any) -> AlertRule:
    if not isinstance(item, dict) or set(item) != _RULE_KEYS:
        raise SLOError("invalid_config", message="rules need exactly the five rule fields")
    name = item["name"]
    threshold = item["burn_threshold"]
    long_window = _window(item["long_window"])
    short_window = _window(item["short_window"])
    if not isinstance(name, str) or _NAME.fullmatch(name) is None:
        raise SLOError("invalid_config", message="rule name has invalid characters or length")
    if type(threshold) not in (int, float):
        raise SLOError("invalid_config", message="burn_threshold must be a JSON number")
    try:
        value = float(threshold)
    except OverflowError as exc:
        raise SLOError("invalid_config", message="burn_threshold is out of range") from exc
    return AlertRule(name, value, long_window, short_window, item["severity"])


def load_policy(path: Path) -> tuple[AlertRule, ...]:
    """Load a custom policy from a JSON array of rule objects (at most 1 MB, 1000 rules).

    Each rule has ``name``, ``burn_threshold``, ``long_window``, ``short_window`` (duration
    strings such as ``1h``) and ``severity``.
    """
    payload = _loads(_decode(_read_limited(path, MAX_POLICY_BYTES)))
    if not isinstance(payload, list) or len(payload) > MAX_RULES:
        raise SLOError("invalid_config", message="policy must be an array of at most 1000 rules")
    return tuple(_json_rule(item) for item in payload)
