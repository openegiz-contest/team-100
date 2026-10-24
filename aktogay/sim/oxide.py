"""Oxide line of Aktogay: heap leach pad -> SX-EW -> cathode. A deliberately small model.

What is known (facts of the production reports, sim/data/kaz_quarterly.csv, column cathode_kt, 32 quarters 2018Q1-2025Q4):
the cathode output of every quarter. What is not published: the ore on the pads, the irrigation, the solution grades, the
SX-EW electricity. So the twin holds one number per quarter and nothing else:

  cathode t/h = cathode of the quarter (kt) x 1000 / hours of the quarter

The reported quarters already hold the season (Q4 2024: -25 % against Q3 'due to lower volumes of ore placed on the leach
pads and colder conditions'; Q4 2025: 'a seasonally lower efficiency'), so winter is NOT cut a second time. The only
departure from the reported level is the scenario `leachcold` (a cold spell on the pad): the output falls by `ox_cold_frac`
(the size of the fall of Q4 2024) for `scen_leach_h` hours.

The quarter is that of the host date (Plant.ox_date, set by akt-sim like the season) or, without it, of the model clock; a date
after 2025 takes the same quarter of 2025. No random draw, no effect on the sulphide plant, the power balance or the money
counters: the oxide complex is already inside pow_other_mw.
"""
from __future__ import annotations

import csv
import datetime
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "data", "kaz_quarterly.csv")
FIRST_YEAR, LAST_YEAR = 2018, 2025
MIN_PER_DAY = 1440.0
MIN_PER_H = 60.0
KT_TO_T = 1000.0                  # unit conversion

_CATHODE: dict[tuple[int, int], float] | None = None


def cathode_by_quarter() -> dict[tuple[int, int], float]:
    """{(year, quarter): cathode kt} of the reports; read once."""
    global _CATHODE
    if _CATHODE is None:
        out: dict[tuple[int, int], float] = {}
        with open(CSV_PATH, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                q = r["quarter"]
                out[(int(q[:4]), int(q[5]))] = float(r["cathode_kt"])
        _CATHODE = out
    return _CATHODE


def quarter_of(year: int, doy0: float) -> tuple[int, int]:
    """(year, quarter 1..4) of a 0-based day of the year; the year is kept inside the reports (after 2025 -> 2025)."""
    y = min(max(int(year), FIRST_YEAR), LAST_YEAR)
    day = datetime.date(y, 1, 1) + datetime.timedelta(days=int(doy0) % 365)
    return y, (day.month - 1) // 3 + 1


def quarter_hours(year: int, quarter: int) -> float:
    a = datetime.date(year, 3 * (quarter - 1) + 1, 1)
    b = datetime.date(year + 1, 1, 1) if quarter == 4 else datetime.date(year, 3 * quarter + 1, 1)
    return (b - a).days * 24.0


def level_tph(year: int, quarter: int) -> float:
    """Cathode of the quarter as t/h."""
    return cathode_by_quarter()[(year, quarter)] * KT_TO_T / quarter_hours(year, quarter)


def oxide_step(st, cold: bool, dt_min: float, prm, ox_date=None) -> None:
    """Leach pad and SX-EW states for one step. ox_date = (year, doy0) or None for the model clock."""
    ck = st.clock
    if ox_date is None:
        year, doy0 = ck.year, ck.origin_doy + ck.t_min / MIN_PER_DAY
    else:
        year, doy0 = ox_date
    y, q = quarter_of(year, doy0)
    lvl = level_tph(y, q)
    frac = prm["ox_cold_frac"] if cold else 0.0
    lc, sx = st.leach, st.sxew
    lc.state, lc.cold_frac = ("COLD" if cold else "NORMAL"), frac
    lc.quarter_cathode_kt, lc.level_tph = cathode_by_quarter()[(y, q)], lvl
    sx.state = "LOW" if cold else "NORMAL"
    sx.cathode_level_tph, sx.cathode_tph = lvl, lvl * (1.0 - frac)
    sx.cathode_t_total += sx.cathode_tph * dt_min / MIN_PER_H
    sx.year, sx.quarter = float(y), float(q)
