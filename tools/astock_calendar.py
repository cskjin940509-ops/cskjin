"""Exchange calendar. Weekday make-up workdays are never exchange sessions.

Source: https://www.sse.com.cn/disclosure/dealinstruc/closed/c/c_20251222_10802510.shtml
Unknown years fail closed until the exchange's annual calendar is installed.
"""
from datetime import date, datetime, timedelta

_RANGES = {2026: [('01-01', '01-03'), ('02-15', '02-23'), ('04-04', '04-06'),
                  ('05-01', '05-05'), ('06-19', '06-21'), ('09-25', '09-27'),
                  ('10-01', '10-07')]}


def is_trading_day(day):
    if isinstance(day, datetime):
        day = day.date()
    if isinstance(day, str):
        day = date.fromisoformat(day)
    if day.weekday() >= 5:
        return False
    if day.year not in _RANGES:
        raise RuntimeError(f'Exchange calendar unavailable for {day.year}; refusing to assume an open session')
    return not any(date.fromisoformat(f'{day.year}-{start}') <= day <=
                   date.fromisoformat(f'{day.year}-{end}') for start, end in _RANGES[day.year])
