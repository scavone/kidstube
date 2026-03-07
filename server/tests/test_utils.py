"""Tests for utils.py — time parsing, formatting, and schedule checking."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import pytest
from utils import (
    parse_time_input,
    format_time_12h,
    get_today_str,
    get_day_utc_bounds,
    resolve_day_schedule,
    minutes_until_schedule_end,
    _DAY_NAMES,
)


class TestParseTimeInput:
    @pytest.mark.parametrize("raw,expected", [
        ("800", "08:00"),
        ("0800", "08:00"),
        ("8:00", "08:00"),
        ("8:00am", "08:00"),
        ("800am", "08:00"),
        ("8:00pm", "20:00"),
        ("800pm", "20:00"),
        ("2000", "20:00"),
        ("20:00", "20:00"),
        ("12:00am", "00:00"),
        ("12:00pm", "12:00"),
        ("1200", "12:00"),
        ("0:00", "00:00"),
        ("23:59", "23:59"),
    ])
    def test_valid_inputs(self, raw, expected):
        assert parse_time_input(raw) == expected

    @pytest.mark.parametrize("raw", [
        "25:00",
        "8:60",
        "13:00am",
        "13:00pm",
        "abc",
        "",
        "12345",
    ])
    def test_invalid_inputs(self, raw):
        assert parse_time_input(raw) is None

    def test_strips_whitespace(self):
        assert parse_time_input("  800  ") == "08:00"

    def test_case_insensitive(self):
        assert parse_time_input("8:00AM") == "08:00"
        assert parse_time_input("8:00PM") == "20:00"


class TestFormatTime12h:
    @pytest.mark.parametrize("hhmm,expected", [
        ("08:00", "8:00 AM"),
        ("20:00", "8:00 PM"),
        ("00:00", "12:00 AM"),
        ("12:00", "12:00 PM"),
        ("12:30", "12:30 PM"),
        ("13:45", "1:45 PM"),
        ("01:05", "1:05 AM"),
    ])
    def test_conversions(self, hhmm, expected):
        assert format_time_12h(hhmm) == expected

    def test_invalid_input_passthrough(self):
        assert format_time_12h("garbage") == "garbage"


class TestGetTodayStr:
    def test_returns_date_string(self):
        result = get_today_str()
        assert len(result) == 10
        assert result[4] == "-" and result[7] == "-"

    def test_with_timezone(self):
        result = get_today_str("America/New_York")
        assert len(result) == 10

    def test_invalid_timezone_falls_back(self):
        result = get_today_str("Invalid/TZ")
        assert len(result) == 10  # Still returns a date


class TestGetDayUtcBounds:
    def test_without_timezone(self):
        start, end = get_day_utc_bounds("2024-06-15")
        assert start == "2024-06-15"
        assert end == "2024-06-16"

    def test_with_timezone(self):
        start, end = get_day_utc_bounds("2024-06-15", "America/New_York")
        # EDT is UTC-4, so local midnight = 04:00 UTC
        assert "2024-06-15" in start
        assert "04:00:00" in start

    def test_invalid_timezone_falls_back(self):
        start, end = get_day_utc_bounds("2024-06-15", "Invalid/TZ")
        assert start == "2024-06-15"
        assert end == "2024-06-16"


class TestResolveDaySchedule:
    def test_empty_settings(self):
        start, end = resolve_day_schedule({})
        assert start == ""
        assert end == ""

    def test_legacy_fallback(self):
        settings = {"schedule_start": "08:00", "schedule_end": "20:00"}
        start, end = resolve_day_schedule(settings)
        assert start == "08:00"
        assert end == "20:00"

    def test_default_schedule(self):
        settings = {
            "schedule:default": json.dumps({"start": "09:00", "end": "21:00"}),
            "schedule_start": "08:00",
            "schedule_end": "20:00",
        }
        start, end = resolve_day_schedule(settings)
        assert start == "09:00"
        assert end == "21:00"

    def test_per_day_overrides_default(self):
        from datetime import datetime, timezone
        day_name = _DAY_NAMES[datetime.now(timezone.utc).weekday()]
        settings = {
            "schedule:default": json.dumps({"start": "09:00", "end": "21:00"}),
            f"schedule:{day_name}": json.dumps({"start": "15:00", "end": "19:00"}),
        }
        start, end = resolve_day_schedule(settings)
        assert start == "15:00"
        assert end == "19:00"

    def test_invalid_json_falls_through(self):
        from datetime import datetime, timezone
        day_name = _DAY_NAMES[datetime.now(timezone.utc).weekday()]
        settings = {
            f"schedule:{day_name}": "not-json",
            "schedule_start": "08:00",
            "schedule_end": "20:00",
        }
        start, end = resolve_day_schedule(settings)
        assert start == "08:00"
        assert end == "20:00"


class TestMinutesUntilScheduleEnd:
    def test_no_end_time(self):
        assert minutes_until_schedule_end("") == -1

    def test_invalid_format(self):
        assert minutes_until_schedule_end("garbage") == -1

    def test_returns_positive_when_before_end(self):
        # Use a far-future time that's always ahead
        result = minutes_until_schedule_end("23:59")
        assert result >= 0

    def test_wraps_around_midnight(self):
        # End time of 00:00 (midnight) — should wrap
        result = minutes_until_schedule_end("00:00")
        assert result >= 0
