"""Russian text helpers for the module outputs (labels, numbers, times).

Every computed number shown to a person carries the label EST
("[оценка на модели]") or ASSUME ("[допущение]"); measurements carry none.
"""
from __future__ import annotations

EST = "[оценка на модели]"
ASSUME = "[допущение]"
LIT = "[литература]"           # a published number of another plant, shown for scale only
ANALOG = "[аналог]"            # a similar plant's practice, a reference, not our value
NBSP = " "   # narrow no-break space as the thousands separator


def num(x: float, digits: int = 1) -> str:
    """Number with a comma decimal and thin-space thousands: 7706.4 -> '7 706,4'."""
    s = f"{x:,.{digits}f}"
    return s.replace(",", "\u0001").replace(".", ",").replace("\u0001", NBSP)


def signed(x: float, digits: int = 2) -> str:
    return ("+" if x > 0 else "−" if x < 0 else "") + num(abs(x), digits)


def cu_tph(x: float, digits: int = 2) -> str:
    return f"{signed(x, digits)} т Cu/ч"


def usd_h(x: float) -> str:
    """USD per hour: '$7,6 тыс./ч' or '$0,38 млн/ч'."""
    a = abs(x)
    sign = "−" if x < 0 else ""
    if a >= 1e6:
        return f"{sign}${num(a / 1e6, 2)} млн/ч"
    if a >= 1e3:
        return f"{sign}${num(a / 1e3, 1)} тыс./ч"
    return f"{sign}${num(a, 0)}/ч"


def usd(x: float) -> str:
    a = abs(x)
    sign = "−" if x < 0 else ""
    if a >= 1e6:
        return f"{sign}${num(a / 1e6, 2)} млн"
    if a >= 1e3:
        return f"{sign}${num(a / 1e3, 1)} тыс."
    return f"{sign}${num(a, 0)}"


def hhmm(t_min: float) -> str:
    m = int(round(t_min)) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def hhmm_day(t_min: float, now_min: float) -> str:
    """'HH:MM' of model minute t_min, with the day when it is not the day of now_min:
    '01:23 завтра', '23:40 вчера', '06:00 через 2 сут.'."""
    if t_min is None or t_min < 0:
        return "—"
    d = int(round(t_min)) // 1440 - int(round(now_min)) // 1440 if now_min is not None and now_min >= 0 else 0
    tail = {0: "", 1: " завтра", -1: " вчера"}.get(d, f" через {d} сут." if d > 0 else f" {-d} сут. назад")
    return hhmm(t_min) + tail


def batch_ru(block: str, batch: str) -> str:
    """Name of an ore batch for a person: the block when known, else 'партия 13' (batch-0013)."""
    if block:
        return block
    digits = "".join(ch for ch in str(batch) if ch.isdigit())
    return f"партия {int(digits)}" if digits else str(batch)


def dur(h: float) -> str:
    """Hours as 'N ч MM мин'."""
    m = int(round(h * 60))
    if m < 60:
        return f"{m} мин"
    return f"{m // 60} ч {m % 60:02d} мин"
