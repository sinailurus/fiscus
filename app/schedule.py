# -*- coding: utf-8 -*-
"""周期重复引擎。

产品定位说明：Fiscus 不内置任何银行规则、不做业务推算。
本模块只负责一件事：用户录入的「每月 X 号」「每年 X 月 X 日」这类
重复规则在时间轴上的滚动（含 31 号在 2 月自动夹到月末），与 SubDeck
的订阅周期滚动是同一性质的通用日历计算。
"""
import calendar
import datetime


def today() -> datetime.date:
    """实时获取今天（容器跨天运行不能冻结日期）。"""
    return datetime.date.today()


def add_months(d: datetime.date, months: int) -> datetime.date:
    """按日历月推算，保持「几号」不变；超出月末自动夹到最后一天。"""
    total = d.year * 12 + (d.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    return datetime.date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def add_years(d: datetime.date, years: int) -> datetime.date:
    return add_months(d, years * 12)


def parse(s: str) -> datetime.date | None:
    """解析 YYYY-MM-DD，空串/非法返回 None。"""
    if not s:
        return None
    try:
        return datetime.date.fromisoformat(s[:10])
    except ValueError:
        return None


def next_monthly(day: int, from_date: datetime.date | None = None) -> datetime.date:
    """「每月 day 号」在 from_date（默认今天）当天或之后的最近一次日期。

    day 取 1~31；2 月等小月自动夹到月末。
    """
    base = from_date or today()
    day = max(1, min(31, int(day)))
    candidate = datetime.date(
        base.year, base.month, min(day, calendar.monthrange(base.year, base.month)[1])
    )
    if candidate >= base:
        return candidate
    nm = add_months(datetime.date(base.year, base.month, 1), 1)
    return datetime.date(nm.year, nm.month, min(day, calendar.monthrange(nm.year, nm.month)[1]))


def roll_next(next_date: str, cycle: str) -> str:
    """把已过期的周期日期滚动到未来（monthly/quarterly/semiannual/yearly）。

    非周期（expire_type=date）不过期滚动，返回原值。
    """
    d = parse(next_date)
    if not d:
        return next_date
    months = {"monthly": 1, "quarterly": 3, "semiannual": 6, "yearly": 12}.get(cycle)
    if not months:
        return next_date
    base = today()
    while d < base:
        d = add_months(d, months)
    return d.isoformat()


def days_until(d: str | datetime.date, from_date: datetime.date | None = None) -> int | None:
    """距目标日还剩几天；目标日为空/非法返回 None。"""
    target = d if isinstance(d, datetime.date) else parse(str(d))
    if not target:
        return None
    return (target - (from_date or today())).days
