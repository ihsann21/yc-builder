import datetime as dt
import re

import pytest

from builder.lib import calc, embed
from builder.lib.runtime import dates
from dev.practice import PRACTICE_CAL, PRACTICE_DATES, PRACTICE_WINDOW, kit_code, run_kit

D = dt.date
# A made-up calendar: Monday to Friday, two holidays. Nothing here comes from a brief.
CAL = {"workdays": [0, 1, 2, 3, 4], "holidays": ["2030-01-07", "2030-01-15"]}


def test_parse_now_and_spoken():
    assert dates.parse_day("2030-01-02T09:30") == D(2030, 1, 2)
    assert dates.parse_day("2030-01-02 09:30:00+03:00") == D(2030, 1, 2)
    assert dates.parse_day("02/01/2030") is None and dates.parse_day(None) is None
    assert dates.parse_clock("2030-01-02T9:05") == "09:05"
    assert dates.parse_clock("2030-01-02") == ""
    assert dates.spoken(D(2030, 1, 2)) == "Wednesday 2 January 2030"


def test_business_days():
    assert dates.is_business_day(D(2030, 1, 4), CAL)          # Friday
    assert not dates.is_business_day(D(2030, 1, 5), CAL)      # Saturday
    assert not dates.is_business_day(D(2030, 1, 7), CAL)      # holiday
    assert dates.nth_business_day_after(D(2030, 1, 4), 1, CAL) == D(2030, 1, 8)   # skips weekend and holiday
    assert dates.nth_business_day_after(D(2030, 1, 2), 5, CAL) == D(2030, 1, 10)
    assert dates.on_or_after(D(2030, 1, 5), CAL) == D(2030, 1, 8)
    assert dates.on_or_before(D(2030, 1, 7), CAL) == D(2030, 1, 4)


def test_business_days_count_today_and_empty_calendar():
    assert dates.nth_business_day_after(D(2030, 1, 2), 1, CAL, count_today=True) == D(2030, 1, 2)
    assert dates.nth_business_day_after(D(2030, 1, 2), 0, CAL) == D(2030, 1, 2)
    assert dates.nth_business_day_after(D(2030, 1, 5), 0, CAL) == D(2030, 1, 8)
    assert dates.nth_business_day_after(D(2030, 1, 2), 3, {"workdays": [], "holidays": []}) is None


def test_week_rules():
    wed = D(2030, 1, 2)
    assert dates.last_business_day_of_week(wed, CAL, 0) == D(2030, 1, 4)
    # a week whose Friday is a holiday ends on Thursday
    cal = {"workdays": [0, 1, 2, 3, 4], "holidays": ["2030-01-04"]}
    assert dates.last_business_day_of_week(wed, cal, 0) == D(2030, 1, 3)
    # weeks can start on Sunday
    assert dates.week_start_of(D(2030, 1, 5), 6) == D(2029, 12, 30)


@pytest.mark.parametrize("rule,expected", [
    ({"rule": "today"}, D(2030, 1, 4)),
    ({"rule": "next_business_day"}, D(2030, 1, 8)),
    ({"rule": "business_days_after", "n": 2}, D(2030, 1, 9)),
    ({"rule": "calendar_days_after", "n": 1}, D(2030, 1, 5)),
    ({"rule": "calendar_days_after", "n": 1, "roll": "forward"}, D(2030, 1, 8)),
    ({"rule": "calendar_days_after", "n": 1, "roll": "backward"}, D(2030, 1, 4)),
    ({"rule": "end_of_month"}, D(2030, 1, 31)),
    ({"rule": "end_of_month", "months_ahead": 1}, D(2030, 2, 28)),
    ({"rule": "end_of_month", "months_ahead": 2, "roll": "backward"}, D(2030, 3, 29)),
    ({"rule": "last_business_day_of_week"}, D(2030, 1, 4)),
    ({"rule": "last_business_day_of_week", "after_today": True}, D(2030, 1, 11)),
    ({"rule": "last_business_day_of_week", "weeks_ahead": 1}, D(2030, 1, 11)),
    ({"rule": "no_such_rule"}, None),
])
def test_resolve_rules_on_a_friday(rule, expected):
    assert dates.resolve(rule, D(2030, 1, 4), CAL) == expected


def test_weekday_modes():
    wed = D(2030, 1, 2)
    this, nxt = dates.weekday_table(wed, "following_week", 0)
    assert this[4] == ("Friday", D(2030, 1, 4)) and nxt[4] == ("Friday", D(2030, 1, 11))
    assert this[0] == ("Monday", D(2029, 12, 31))
    this, nxt = dates.weekday_table(wed, "first_after_today", 0)
    assert nxt[4] == ("Friday", D(2030, 1, 4)) and nxt[2] == ("Wednesday", D(2030, 1, 9))


def test_window_slots_respect_now_and_end():
    spec = {"days": [{"rule": "today"}, {"rule": "next_business_day"}], "from": "10:00", "to": "19:00", "after_now": True}
    assert dates.window_slots(D(2030, 1, 4), "11:00", spec, CAL) == [["2030-01-04", "11:01", "19:00"], ["2030-01-08", "10:00", "19:00"]]
    assert dates.window_slots(D(2030, 1, 4), "08:00", spec, CAL)[0] == ["2030-01-04", "10:00", "19:00"]
    assert dates.window_slots(D(2030, 1, 4), "19:00", spec, CAL) == [["2030-01-08", "10:00", "19:00"]]


def run_setup(now: str, **cfg) -> dict:
    code = calc.dates_code(calendar=CAL, **cfg)
    return embed.run(code, state={"now": now})


def test_dates_code_writes_state_and_facts():
    state = run_setup(
        "2030-01-04T11:00",
        dates=[{"name": "limit", "rule": "business_days_after", "n": 2, "label": "LATEST DATE"}],
        windows=[{"name": "slot", "days": [{"rule": "today"}], "from": "10:00", "to": "12:00", "after_now": True,
                  "var": "slot_facts", "label": "CALL WINDOW"}],
        weekday_mode="following_week",
    )
    assert state["bb_dates_state"] == "ok"
    assert state["bb_today"] == "2030-01-04" and state["bb_time"] == "11:00"
    assert state["bb_date__limit"] == "2030-01-09"
    assert state["bb_date__limit__spoken"] == "Wednesday 9 January 2030"
    facts = state["date_facts"]
    assert "TODAY: Friday 4 January 2030 (2030-01-04), time now 11:00. Today is a business day." in facts
    assert "LATEST DATE: Wednesday 9 January 2030 (2030-01-09)." in facts
    assert "next Friday = 2030-01-11" in facts
    assert "  2030-01-07 Monday X holiday" in facts and "  2030-01-05 Saturday X weekend" in facts
    assert state["bb_window__slot"] == "2030-01-04 11:01-12:00"
    assert state["slot_facts"].startswith("CALL WINDOW: Friday 4 January 2030 (2030-01-04) from 11:01 to 12:00.")


def test_calendar_covers_the_farthest_named_date():
    state = run_setup("2030-01-04T11:00", calendar_days=5,
                      dates=[{"name": "far", "rule": "calendar_days_after", "n": 30}])
    assert "  2030-02-03 Sunday X weekend" in state["date_facts"]


def test_dates_code_falls_back_when_now_is_unreadable():
    state = run_setup("yesterday", windows=[{"name": "w", "days": [{"rule": "today"}], "from": "10:00",
                                             "to": "12:00", "var": "w_facts", "label": "W"}],
                      fallback="NO DATES")
    assert state["bb_dates_state"] == "error" and state["date_facts"] == "NO DATES"
    assert state["w_facts"] == "NO DATES" and "bb_dates_error" in state


@pytest.mark.parametrize("bad", [
    {"calendar": {"workdays": [7], "holidays": []}},
    {"calendar": {"workdays": [0], "holidays": ["2030-1-7"]}},
    {"calendar": CAL, "dates": [{"name": "x", "rule": "business_days_after"}]},
    {"calendar": CAL, "dates": [{"name": "x", "rule": "fortnight"}]},
    {"calendar": CAL, "dates": [{"name": "bad name", "rule": "today"}]},
    {"calendar": CAL, "weekday_mode": "sometimes"},
    {"calendar": CAL, "windows": [{"name": "w", "days": [], "from": "10:00", "to": "12:00", "var": "v", "label": "L"}]},
    {"calendar": CAL, "windows": [{"name": "w", "days": [{"rule": "today"}], "from": "25:00", "to": "12:00", "var": "v", "label": "L"}]},
    {"calendar": CAL, "fallback": "{{x}}"},
])
def test_dates_code_rejects_bad_config(bad):
    with pytest.raises(ValueError):
        calc.dates_code(**bad)


# --- the kit's working builder computed the same facts by hand; our code must agree with it -----


def kit_next_business_day(callback_facts: str) -> str:
    return re.search(r"next business day,? .*?\((\d{4}-\d{2}-\d{2})\)", callback_facts).group(1)


def test_same_dates_as_the_kit_setup_code(kit):
    kit_setup = kit_code(kit, "a", "setup")
    ours = calc.dates_code(calendar=PRACTICE_CAL, dates=PRACTICE_DATES, windows=[PRACTICE_WINDOW],
                           weekday_mode="following_week", calendar_days=40)
    day = D(2026, 9, 1)
    while day <= D(2027, 2, 28):
        for clock in ("08:00", "11:00", "18:59"):
            now = day.isoformat() + "T" + clock
            k = run_kit(kit_setup, state={"now": now})
            o = embed.run(ours, state={"now": now})
            assert (o["bb_today"], o["bb_date__deadline_early"], o["bb_date__deadline_late"], o["bb_date__attempt1"]) == \
                   (k["today_iso"], k["deadline_early"], k["deadline_late"], k["attempt1_iso"]), now
            assert o["bb_date__attempt1__spoken"] == k["attempt1_spoken"], now
            kit_lines = [x for x in k["date_facts"].split("\n") if x.startswith(("this ", "next ", "  2"))]
            our_lines = [x for x in o["date_facts"].split("\n") if x.startswith(("this ", "next ", "  2"))]
            assert our_lines == kit_lines, now
            slots = o["bb_window__callback"].split(";")
            assert slots[-1].startswith(kit_next_business_day(k["callback_facts"])), now
        day += dt.timedelta(days=1)
