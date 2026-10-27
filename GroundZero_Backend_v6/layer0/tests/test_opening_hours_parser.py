from datetime import datetime

from layer0.application.opening_hours_parser import OpeningHoursParser


def test_simple_daily_range():
    result = OpeningHoursParser().parse("Mo-Sa 09:00-18:00")
    assert result.parse_succeeded
    assert result.days_open == ["mon", "tue", "wed", "thu", "fri", "sat"]
    assert result.opens_at == "09:00"
    assert result.closes_at == "18:00"


def test_split_weekday_weekend_hours():
    result = OpeningHoursParser().parse("Mo-Fr 08:00-20:00; Sa 09:00-13:00; Su off")
    assert result.parse_succeeded
    assert "sun" not in result.days_open
    assert set(result.days_open) == {"mon", "tue", "wed", "thu", "fri", "sat"}


def test_24_7_regression():
    """Regression test for a real bug caught by live testing: querying
    the whole week in one intervals() call let a continuous 24/7 block
    span multiple days without being split, producing days_open=['mon']
    only and a misleading opens=00:00/closes=00:00 zero-width window."""
    result = OpeningHoursParser().parse("24/7")
    assert result.parse_succeeded
    assert result.days_open == ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    assert result.opens_at == "00:00"
    assert result.closes_at == "23:59"  # not the misleading 00:00


def test_specific_days_list():
    result = OpeningHoursParser().parse("Mo,We,Fr 10:00-14:00")
    assert result.days_open == ["mon", "wed", "fri"]
    assert result.opens_at == "10:00"
    assert result.closes_at == "14:00"


def test_overnight_hours_crossing_midnight():
    result = OpeningHoursParser().parse("Th 20:00-02:00")
    assert "thu" in result.days_open
    assert result.opens_at == "20:00"


def test_empty_string_fails_gracefully():
    result = OpeningHoursParser().parse("")
    assert not result.parse_succeeded
    assert result.days_open == []
    assert result.opens_at is None


def test_malformed_syntax_fails_gracefully_not_an_exception():
    result = OpeningHoursParser().parse("this is not valid @#$% syntax")
    assert not result.parse_succeeded


def test_is_open_at_true_during_hours():
    monday_10am = datetime(2024, 1, 1, 10, 0)  # a real Monday
    assert OpeningHoursParser().is_open_at("Mo-Sa 09:00-18:00", monday_10am) is True


def test_is_open_at_false_outside_hours():
    monday_11pm = datetime(2024, 1, 1, 23, 0)
    assert OpeningHoursParser().is_open_at("Mo-Sa 09:00-18:00", monday_11pm) is False


def test_is_open_at_false_on_closed_day():
    sunday = datetime(2024, 1, 7, 10, 0)
    assert OpeningHoursParser().is_open_at("Mo-Sa 09:00-18:00", sunday) is False


def test_is_open_at_true_for_24_7():
    sunday_2pm = datetime(2024, 1, 7, 14, 0)
    assert OpeningHoursParser().is_open_at("24/7", sunday_2pm) is True


def test_is_open_at_none_for_empty_string():
    assert OpeningHoursParser().is_open_at("", datetime(2024, 1, 1, 10, 0)) is None


def test_is_open_at_none_for_malformed_string():
    assert OpeningHoursParser().is_open_at("@#$% garbage", datetime(2024, 1, 1, 10, 0)) is None
