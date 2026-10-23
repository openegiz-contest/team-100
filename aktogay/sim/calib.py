"""Calibration and checks without refit: annual runs against KAZ Minerals reports.

Design: section 4 "calibration (fit)", "check without refit" table and its
notes, section 8 (VALIDATION.md contents), section 9/12 (make akt-calib
under 4 min), section 10 (calib row: 7 model days, balances < 0.5 %).

Order (run_all):
  1. fit_2025: cal_avail (-> 62.1 Mt), sag_k (-> mean P/Q = sag_e_base_kwh_t,
     i.e. 26.0 MW at 3853 t/h), flot_rinf0_pct (-> 87.2 %) at the feed grade
     tgt_2025_feed_pct = 220.3 kt / (62.1 Mt x 87.2 %) = 0.4068 % (report
     grade 0.41 % is rounded). The three numbers are fitted together, one
     annual run per iteration; Cu in concentrate then follows (check row).
  2. fit_2024: pow_other_mw (-> 2033 GWh) and water_evap_m3h (-> 34.852 Mm3)
     on 2024, the year with ore, electricity and water all published;
     availability matched to 58.3 Mt (an input). K and R0 from step 1.
  3. check_2024 without refit (same fitted 2024 run): recovery 87.9 % +-0.5
     pp and Cu 221.0 kt +-2 % at the report grade 0.43 %. K, R0, the grade
     term and the other load do not use 2024 recovery or Cu.
  4. check_2023 without refit: 2023 ore is not in the sources, so it is
     taken from the 2023 electricity with the 2024 fit (electricity is
     linear in ore); then water intake 32.8 Mm3 +-5 % and recovery 87.7 %
     +-0.5 pp at the report grade 0.50 %.
  5. check_2025_site with the final parameters (2025 run after both fits):
     feed grade, site electricity and water. 2025 energy and water are not
     published; totals are shown against 2024 without tolerance (ore
     differs), per tonne rows carry the 2024 tolerances.
  6. check_reline_quarter: line 2, Q3 vs Q2 2025 tonnes, report -4.7 %, +-1.5 pp
     (from the final 2025 run, no extra run). The August 2025 reline is the
     one SAG reline the reports name (Q3 2025 report, p. 3); October 2024 is
     "planned SAG maintenance" (Q4 2024 report, p. 3).
  7. check_quarters: Q3 2025 recovery from a quarter run at its grade 0.40 %
     vs report 86.1 %, tolerance = error of the constant 87.2 % (the model is
     useful only when its error is smaller). Other quarters: grades not in
     sources yet.
  8. check_balances 2025 and 2024 with the final parameters (cached runs):
     Cu feed = concentrate + tails, concentrate chain, ore stockpile, water
     with pond, peaks of site, SAG and ball mill power within their limits.
  9. week_check: 7 model days of free run: stockpiles within 10-90 %, pond in
     its band, balance residuals < tol_balance_pct, shift counters reset,
     site power within the grid limit, ACS false alarms.
Prints "model / report / deviation / tolerance / ok" and writes JSON.
Exit code is always 0; failures and errors are reported in the table.

Annual run (mode "calib", from 1 January 00:00, step cal_step_calib_min):
  - feed grade blk_cu_mean_pct = tgt_<year>_feed_pct when the table has it
    (2025), else tgt_<year>_grade_pct (year_params);
  - SAG stops from params.RELINE_CALENDAR (kind "reline", "sag_service" or
    "stop": every kind is modelled as a reline of liner_reline_h with a new
    liner after it; for "sag_service" and "stop" that is an assumption),
    starting at the shift start; the liner campaign at the run start is
    estimated from the last calendar stop before it, else liner_x0;
  - line downtime: availability is the share of calendar time a line runs,
    relines included. The rest of the stopped share is drawn as stops of
    U(cal_stop_h_lo, cal_stop_h_hi) hours, spread month by month in
    proportion to month length, so every quarter gets its calendar share of
    random stops and the reline quarter differs by the reline itself.
Accounting is integrated from the unit states after each step (t, t/h, kW,
m3/h x step): ore = SAG fresh feed, Cu = flotation Cu in concentrate, feed Cu
= feed x flotation feed grade, energy = site MW, water = intake m3/h.

Uses only sim.plant.Plant, sim.params and sim.state; --publish adds
sim.calib_report (Ditto HTTP, thing validation-calib, with the on/off trial
summary sim/data/trial_n100.json).
Run: python -I run.py calib [--seed 42] [--dt 10] [--out calib.json] [--quick] [--publish] [--trial FILE]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field

from . import calib_report
from .params import RELINE_CALENDAR, TABLE, ParamSet, default
from .plant import Plant
from .state import MIN_PER_DAY, MIN_PER_H, NO_VALUE, PlantHooks, feed_end_wear_mm, u01

# Unit conversions and fixed calendar facts (not model parameters).
PCT = 100.0
KW_PER_MW = 1.0e3
T_PER_KT = 1.0e3
T_PER_MT = 1.0e6
MWH_PER_GWH = 1.0e3
M3_PER_MM3 = 1.0e6
EPS_MIN = 1.0e-6                 # time comparison slack, model minutes
LINES = (1, 2)
QUARTERS = ("Q1", "Q2", "Q3", "Q4")
SAG_DOWN = ("RELINE", "STOP")
_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

FIT_2025_KEYS = ("cal_avail", "sag_k", "flot_rinf0_pct")
FIT_2024_KEYS = ("pow_other_mw", "water_evap_m3h")
BALANCE_KEYS = ("cu_residual_pct", "water_residual_pct", "conc_residual_pct")
AVAIL_2023_NAME = "availability 2023 (matched to ore from electricity)"
AVAIL_2024_NAME = "availability 2024 (matched to ore)"


@dataclass
class YearResult:
    year: int
    ore_mt: float             # both lines
    grade_pct: float          # mean feed grade, % Cu
    cu_conc_kt: float         # Cu in concentrate
    recovery_pct: float       # Cu in concentrate / Cu in feed
    energy_gwh: float         # site electricity
    water_mm3: float          # intake
    run_hours: float          # mean SAG running hours per line
    sag_e_kwh_t: float        # mean P/Q while running
    quarters: dict[str, dict[str, float]] = field(default_factory=dict)
    # "Q1".."Q4" -> {"ore_kt", "ore_kt_l1", "ore_kt_l2", "cu_kt", "rec_pct", "grade_pct", "hours",
    #               "hours_l1", "hours_l2", "energy_gwh", "water_mm3", "sag_e_kwh_t", ...}
    extra: dict[str, float] = field(default_factory=dict)
    # per line ore and hours, availability, planned stop hours, liner start, other GWh,
    # evaporation Mm3, starved hours, max balance residuals (-1 when not available),
    # run balances from unit states (_balances: cu/water/stock/reclaim %, tails Cu, power peaks)


@dataclass
class CheckRow:
    group: str                # "fit 2025" | "fit 2023" | "check 2024" | "reline" | "quarters" | "week" | "fit params"
    name: str
    model: float
    report: float
    unit: str
    tol: float                # absolute tolerance in `unit`; -1 when none
    ok: bool | None           # None when no tolerance
    note: str = ""


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------
def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _month_days(year: int, month: int) -> int:
    return 29 if month == 2 and _is_leap(year) else _MONTH_DAYS[month - 1]


def _days_from_civil(year: int, month: int, day: int) -> int:
    """Days since 1970-01-01 in the proleptic Gregorian calendar (Hinnant's algorithm)."""
    y = year - (1 if month <= 2 else 0)
    era = (y if y >= 0 else y - 399) // 400
    yoe = y - era * 400
    doy = (153 * (month - 3 if month > 2 else month + 9) + 2) // 5 + day - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def year_days(year: int) -> int:
    """Calendar days in `year`."""
    return 366 if _is_leap(year) else 365


def year_min(year: int) -> float:
    """Model minutes in `year`."""
    return year_days(year) * MIN_PER_DAY


def calendar_min(year: int, month: int, day: int, hour: float = 0.0) -> float:
    """Model minute from 1 January 00:00 of `year` (Gregorian calendar).

    month 1..12, day 1..days of month, hour 0..24 (fractional allowed); else ValueError.
    """
    if not 1 <= month <= 12:
        raise ValueError(f"month must be 1..12, got {month}")
    if not 1 <= day <= _month_days(year, month):
        raise ValueError(f"day {day} not in {year}-{month:02d}")
    if not 0.0 <= hour <= 24.0:
        raise ValueError(f"hour must be 0..24, got {hour}")
    days = _days_from_civil(year, month, day) - _days_from_civil(year, 1, 1)
    return float(days * MIN_PER_DAY + hour * MIN_PER_H)


def _abs_min(year: int, t_min: float) -> float:
    """Minute since 1970-01-01 of model minute t_min of `year` (to compare across years)."""
    return _days_from_civil(year, 1, 1) * MIN_PER_DAY + t_min


def _quarter_bounds(year: int) -> list[tuple[str, float, float]]:
    """(name, start_min, end_min) of the four quarters of `year`."""
    starts = [calendar_min(year, m, 1) for m in (1, 4, 7, 10)] + [year_min(year)]
    return [(QUARTERS[i], starts[i], starts[i + 1]) for i in range(4)]


def reline_windows(year: int, prm: ParamSet) -> list[tuple[int, float, float]]:
    """(line, start_min, end_min) for RELINE_CALENDAR entries of `year`, length liner_reline_h.

    Every calendar kind (reline, planned SAG maintenance, planned plant stop)
    is a SAG RELINE window; it starts at the shift start (cal_shift_start_h)
    of its calendar day.
    """
    dur = prm["liner_reline_h"] * MIN_PER_H
    out = []
    for r in RELINE_CALENDAR:
        if r.year == year:
            start = calendar_min(year, r.month, r.day, prm["cal_shift_start_h"])
            out.append((r.line, start, start + dur))
    return sorted(out, key=lambda w: (w[1], w[0]))


def feed_key(year: int) -> str | None:
    """Table key of the feed grade of `year`: tgt_<year>_feed_pct (calc from the report balance)
    when present, else tgt_<year>_grade_pct (report), else None."""
    for key in (f"tgt_{year}_feed_pct", f"tgt_{year}_grade_pct"):
        if key in TABLE:
            return key
    return None


def year_params(prm: ParamSet, year: int) -> ParamSet:
    """Copy of prm with blk_cu_mean_pct = the feed grade of `year` (feed_key) when the table has one."""
    p = prm.copy()
    key = feed_key(year)
    if key is not None:
        p.set("blk_cu_mean_pct", prm[key])
    return p


# ---------------------------------------------------------------------------
# Planned line stops and liner state
# ---------------------------------------------------------------------------
def _merge(windows: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Sorted union of windows (start, end)."""
    out: list[tuple[float, float]] = []
    for a, b in sorted(windows):
        if b <= a:
            continue
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _complement(windows: list[tuple[float, float]], t0: float, t1: float) -> list[tuple[float, float]]:
    """Parts of [t0, t1) outside the sorted, disjoint windows."""
    out = []
    t = t0
    for a, b in windows:
        if b <= t0 or a >= t1:
            continue
        if a > t:
            out.append((t, a))
        t = max(t, b)
    if t < t1:
        out.append((t, t1))
    return out


def _map_free(free: list[tuple[float, float]], xa: float, xb: float) -> list[tuple[float, float]]:
    """Map [xa, xb) on the joined free-time axis back to model time (split at gaps)."""
    out = []
    cum = 0.0
    for a, b in free:
        length = b - a
        lo, hi = max(xa, cum), min(xb, cum + length)
        if hi > lo:
            out.append((a + lo - cum, a + hi - cum))
        cum += length
        if cum >= xb:
            break
    return out


def _spread_stops(seed: int, stream: str, free: list[tuple[float, float]], total_min: float,
                  prm: ParamSet) -> list[tuple[float, float]]:
    """Stops covering total_min minutes of the free intervals, model minutes.

    Durations U(cal_stop_h_lo, cal_stop_h_hi) are drawn until they cover the
    total, then scaled by one factor so the total is exact; gaps are
    exponential spacings normalised to the slack. Draws from (seed, k, stream).
    """
    free_len = sum(b - a for a, b in free)
    total = min(total_min, free_len)
    if total <= EPS_MIN:
        return []
    lo = prm["cal_stop_h_lo"] * MIN_PER_H
    hi = max(prm["cal_stop_h_hi"] * MIN_PER_H, lo)
    durs: list[float] = []
    covered = 0.0
    while covered < total:
        d = max(lo + (hi - lo) * u01(seed, len(durs), stream, 0), EPS_MIN)
        durs.append(d)
        covered += d
    scale = total / covered
    weights = [-math.log(u01(seed, k, stream, 1)) for k in range(len(durs) + 1)]
    wsum = sum(weights)
    slack = free_len - total
    out: list[tuple[float, float]] = []
    x = slack * weights[0] / wsum
    for i, d in enumerate(durs):
        d *= scale
        out.extend(_map_free(free, x, x + d))
        x += d + slack * weights[i + 1] / wsum
    return out


def line_stops(year: int, prm: ParamSet, seed: int = 42,
               availability: float | None = None) -> dict[int, list[tuple[float, float]]]:
    """Planned random stops per line for a calib year, {line: [(start_min, end_min)]}.

    Stopped share of the year per line = 1 - availability (cal_avail when
    None), relines (reline_windows) included; the rest is spread month by
    month in proportion to month length (time a month cannot hold moves to
    the next month), never over a reline. Reline windows are not returned.
    Draws from (seed, k, "down-<year>-<line>-<month>").
    """
    a = prm["cal_avail"] if availability is None else availability
    a = min(1.0, max(0.0, float(a)))
    t_year = year_min(year)
    rel = reline_windows(year, prm)
    out: dict[int, list[tuple[float, float]]] = {}
    for line in LINES:
        fixed = _merge([(max(0.0, s), min(t_year, e)) for n, s, e in rel if n == line])
        fixed_len = sum(b - a0 for a0, b in fixed)
        extra = max(0.0, (1.0 - a) * t_year - fixed_len)
        stops: list[tuple[float, float]] = []
        carry = 0.0
        for month in range(1, 13):
            m0 = calendar_min(year, month, 1)
            m1 = calendar_min(year, month + 1, 1) if month < 12 else t_year
            free = _complement(fixed, m0, m1)
            free_len = sum(b - a0 for a0, b in free)
            need = extra * (m1 - m0) / t_year + carry
            take = min(need, free_len)
            carry = need - take
            stops += _spread_stops(seed, f"down-{year}-{line}-{month}", free, take, prm)
        out[line] = sorted(stops)
    return out


def liner_x_at(prm: ParamSet, year: int, t_min: float, line: int,
               availability: float | None = None) -> float | None:
    """Liner campaign share used on `line` at model minute t_min of `year`, -.

    Ore ground since the end of the last calendar reline before t_min
    (ground_since_reline_mt) over liner_life_mt; capped at 1. None when the
    calendar has no earlier reline of the line (the plant keeps liner_x0).
    """
    ground_mt = ground_since_reline_mt(prm, year, t_min, line, availability)
    if ground_mt is None:
        return None
    return min(1.0, max(0.0, ground_mt / prm["liner_life_mt"]))


def ground_since_reline_mt(prm: ParamSet, year: int, t_min: float, line: int,
                           availability: float | None = None) -> float | None:
    """Ore ground on `line` since the end of the last calendar reline before t_min of `year`, Mt.

    Estimated as hours x cal_line_tph x availability (cal_avail when None);
    None when the calendar has no earlier reline of the line.
    """
    t_abs = _abs_min(year, t_min)
    dur = prm["liner_reline_h"] * MIN_PER_H
    last_end = None
    for r in RELINE_CALENDAR:
        if r.line != line:
            continue
        end = _abs_min(r.year, calendar_min(r.year, r.month, r.day, prm["cal_shift_start_h"])) + dur
        if end <= t_abs and (last_end is None or end > last_end):
            last_end = end
    if last_end is None:
        return None
    a = prm["cal_avail"] if availability is None else availability
    return max(0.0, (t_abs - last_end) / MIN_PER_H * prm["cal_line_tph"] * a / T_PER_MT)


# ---------------------------------------------------------------------------
# Simulation and accounting
# ---------------------------------------------------------------------------
# Accumulator slots (per bin): t, kWh, h, MWh, m3. _OTHER is the site part of the other load
# (pow_other_mw, fitted), _AUX the line part (pow_line_aux_mw of running lines).
(_ORE1, _ORE2, _CUF, _CU, _KWH, _SAGT, _RUN1, _RUN2, _STARV,
 _MWH, _OTHER, _WATER, _EVAP, _HOURS, _CUT, _TLOSS, _CMOIST, _RECYC, _AUX) = range(19)
_NACC = 19

_CACHE: dict[tuple, object] = {}
_CACHE_MAX = 24


def clear_cache() -> None:
    """Forget cached annual and quarter runs."""
    _CACHE.clear()


def _cache_key(prm: ParamSet, *parts) -> tuple:
    return (Plant,) + parts + tuple(sorted(prm.as_dict().items()))


def _cache_put(key: tuple, value: object) -> None:
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = value


def _dt(prm: ParamSet, dt_min: float | None) -> float:
    dt = prm["cal_step_calib_min"] if dt_min is None else float(dt_min)
    if not dt > 0.0:
        raise ValueError(f"step must be positive, got {dt}")
    return dt


def _avail(prm: ParamSet, availability: float | None) -> float:
    return float(prm["cal_avail"] if availability is None else availability)


def _set_liner(plant, prm: ParamSet, year: int, t0: float, availability: float) -> dict[int, float]:
    """Set the SAG liner campaign and the feed-end wear counter at the run start from the reline
    calendar; returns liner_x per line."""
    out = {}
    for ln in plant.state.lines:
        ground_mt = ground_since_reline_mt(prm, year, t0, ln.n, availability)
        if ground_mt is not None:
            ln.sag.liner_x = min(1.0, ground_mt / prm["liner_life_mt"])
            ln.sag.liner_wear_mm = feed_end_wear_mm(ground_mt * prm["liner_wear_mm_mt"], prm)
        out[ln.n] = ln.sag.liner_x
    return out


def _simulate(prm: ParamSet, year: int, t_start: float, t_end: float,
              bins: list[tuple[str, float, float]], seed: int, dt: float,
              availability: float) -> tuple[dict[str, list[float]], dict]:
    """Run Plant(mode "calib") over [t_start, t_end) of `year`; returns per-bin accumulators and info.

    bins: (name, start_min, end_min); steps are shortened to land on bin
    edges and each step counts in every bin that contains it.
    """
    plant = Plant(prm, seed, mode="calib", t0_min=t_start, year=year, origin_doy=0)
    st = plant.state
    liner0 = _set_liner(plant, prm, year, t_start, availability)
    rel = [w for w in reline_windows(year, prm) if w[2] > t_start and w[1] < t_end]
    plant.set_relines(rel)
    stops = line_stops(year, prm, seed, availability)
    for line in LINES:
        plant.set_downtime(line, [(a, b) for a, b in stops[line] if b > t_start and a < t_end])

    accs = {name: [0.0] * _NACC for name, _, _ in bins}
    edges = sorted({t_start, t_end} | {x for _, a, b in bins for x in (a, b) if t_start < x < t_end})
    lines = st.lines
    bal_max = {k: 0.0 for k in BALANCE_KEYS}
    bal_err = ""
    next_bal = t_start + MIN_PER_DAY
    counter0 = st.total.ore_t
    steps = 0
    # stock and pond at the start (ore balance: crusher -> stockpile -> SAG; water: pond change)
    stock0 = {ln.n: (ln.stockpile.cum_in_t, ln.stockpile.cum_out_t, ln.stockpile.level_t) for ln in lines}
    pond0 = st.water.pond_m3
    site_max = sag_max = ball_max = 0.0
    wear_max = max(ln.sag.liner_wear_mm for ln in lines)
    grid_min = math.inf

    def sample_balances() -> None:
        nonlocal bal_err
        if bal_err:
            return
        try:
            b = plant.balances()
            for k in BALANCE_KEYS:
                v = b.get(k, 0.0)
                if isinstance(v, (int, float)) and math.isfinite(v):
                    bal_max[k] = max(bal_max[k], abs(v))
        except Exception as e:  # balances are a check, the run goes on
            bal_err = f"{type(e).__name__}: {e}"

    for s0, s1 in zip(edges, edges[1:]):
        active = [accs[name] for name, a, b in bins if a <= s0 + EPS_MIN and s1 <= b + EPS_MIN]
        while True:
            t = plant.t_min
            if t >= s1 - EPS_MIN:
                break
            plant.step(min(dt, s1 - t))
            t2 = plant.t_min
            if not t2 > t:
                raise RuntimeError(f"Plant.step did not advance the clock at minute {t}")
            steps += 1
            hh = (t2 - t) / MIN_PER_H
            ore = [0.0, 0.0]
            run = [0.0, 0.0]
            cuf = cu = cut = kwh = sagt = starved = 0.0
            for i, ln in enumerate(lines):
                sag = ln.sag
                sag_max = max(sag_max, sag.power_kw)
                wear_max = max(wear_max, sag.liner_wear_mm)
                for b in ln.balls:
                    ball_max = max(ball_max, b.power_kw)
                q = sag.feed_tph
                if q > 0.0 and sag.state not in SAG_DOWN:
                    ore[i] = q * hh
                    run[i] = hh
                    kwh += sag.power_kw * hh
                    sagt += q * hh
                    if sag.state == "STARVED":
                        starved += hh
                    fl = ln.flot
                    if fl.feed_cu > 0.0:
                        cuf += q * fl.feed_cu / PCT * hh
                    cu += max(0.0, fl.cu_tph) * hh
                    if fl.tail_cu > 0.0:
                        cut += max(0.0, q - fl.conc_tph) * fl.tail_cu / PCT * hh
            pw, wa = st.power, st.water
            site_max = max(site_max, pw.site_mw)
            if pw.grid_limit_mw > 0.0:
                grid_min = min(grid_min, pw.grid_limit_mw)
            vals = (ore[0], ore[1], cuf, cu, kwh, sagt, run[0], run[1], starved,
                    pw.site_mw * hh, (pw.other_mw - pw.line_aux_mw) * hh, wa.intake_m3h * hh, wa.evap_m3h * hh,
                    hh, cut, wa.tails_loss_m3h * hh, wa.conc_moist_m3h * hh, wa.recycle_m3h * hh,
                    pw.line_aux_mw * hh)
            for acc in active:
                for k in range(_NACC):
                    acc[k] += vals[k]
            if t2 >= next_bal:
                next_bal += MIN_PER_DAY
                sample_balances()
    sample_balances()                     # cumulative residuals at the run end
    stock = {}
    for ln in lines:
        in0, out0, lv0 = stock0[ln.n]
        sp = ln.stockpile
        stock[ln.n] = (sp.cum_in_t - in0, sp.cum_out_t - out0, sp.level_t - lv0)
    info = {
        "steps": steps,
        "avail": availability,
        "liner_x0": liner0,
        "stop_h": {n: sum(min(b, t_end) - max(a, t_start) for a, b in stops[n]
                          if b > t_start and a < t_end) / MIN_PER_H for n in LINES},
        "reline_h": {n: sum(min(e, t_end) - max(s, t_start) for m, s, e in rel if m == n) / MIN_PER_H
                     for n in LINES},
        "bal_max": bal_max if not bal_err else {k: NO_VALUE for k in BALANCE_KEYS},
        "bal_err": bal_err,
        "counter_ore_mt": (st.total.ore_t - counter0) / T_PER_MT,
        "stock": stock,                   # line -> (stockpile in, out, level change), t
        "pond_change_m3": st.water.pond_m3 - pond0,
        "site_mw_max": site_max,
        "grid_limit_mw": grid_min if math.isfinite(grid_min) else NO_VALUE,
        "sag_mw_max": sag_max / KW_PER_MW,
        "ball_mw_max": ball_max / KW_PER_MW,
        "liner_wear_mm_max": wear_max,
    }
    return accs, info


def _pct_of(residual: float, base: float) -> float:
    """100 x residual / base; NO_VALUE when base is not positive."""
    return PCT * residual / base if base > 0.0 else NO_VALUE


def _balances(acc: list[float], info: dict) -> dict[str, float]:
    """Run totals closed independently of Plant.balances (from unit states), %.

    cu: feed Cu - concentrate Cu - tails Cu (flotation holds no Cu);
    water: intake - tails pores - concentrate moisture - evaporation - pond change;
    stock: stockpile in - out - level change (both lines);
    reclaim: SAG feed - stockpile out (both lines).
    """
    din = sum(v[0] for v in info["stock"].values())
    dout = sum(v[1] for v in info["stock"].values())
    dlev = sum(v[2] for v in info["stock"].values())
    water_out = acc[_TLOSS] + acc[_CMOIST] + acc[_EVAP] + info["pond_change_m3"]
    return {
        "cu_tails_kt": acc[_CUT] / T_PER_KT,
        "cu_bal_pct": _pct_of(acc[_CUF] - acc[_CU] - acc[_CUT], acc[_CUF]),
        "water_bal_pct": _pct_of(acc[_WATER] - water_out, acc[_WATER]),
        "stock_bal_pct": _pct_of(din - dout - dlev, din),
        "reclaim_bal_pct": _pct_of(acc[_ORE1] + acc[_ORE2] - dout, dout),
        "stock_change_kt": dlev / T_PER_KT,
        "recycle_mm3": acc[_RECYC] / M3_PER_MM3,
        "tails_loss_mm3": acc[_TLOSS] / M3_PER_MM3,
        "conc_moist_mm3": acc[_CMOIST] / M3_PER_MM3,
        "pond_change_mm3": info["pond_change_m3"] / M3_PER_MM3,
        "site_mw_max": info["site_mw_max"],
        "grid_limit_mw": info["grid_limit_mw"],
        "sag_mw_max": info["sag_mw_max"],
        "ball_mw_max": info["ball_mw_max"],
        "liner_wear_mm_max": info.get("liner_wear_mm_max", NO_VALUE),
    }


def _summary(acc: list[float]) -> dict[str, float]:
    """Totals of one bin: kt, %, h (mean per line), GWh, Mm3, kWh/t."""
    ore_t = acc[_ORE1] + acc[_ORE2]
    return {
        "ore_kt": ore_t / T_PER_KT,
        "ore_kt_l1": acc[_ORE1] / T_PER_KT,
        "ore_kt_l2": acc[_ORE2] / T_PER_KT,
        "cu_kt": acc[_CU] / T_PER_KT,
        "cu_feed_kt": acc[_CUF] / T_PER_KT,
        "rec_pct": PCT * acc[_CU] / acc[_CUF] if acc[_CUF] > 0.0 else NO_VALUE,
        "grade_pct": PCT * acc[_CUF] / ore_t if ore_t > 0.0 else NO_VALUE,
        "hours": 0.5 * (acc[_RUN1] + acc[_RUN2]),
        "hours_l1": acc[_RUN1],
        "hours_l2": acc[_RUN2],
        "starved_h": acc[_STARV],
        "sag_e_kwh_t": acc[_KWH] / acc[_SAGT] if acc[_SAGT] > 0.0 else NO_VALUE,
        "energy_gwh": acc[_MWH] / MWH_PER_GWH,
        "other_gwh": acc[_OTHER] / MWH_PER_GWH,
        "line_aux_gwh": acc[_AUX] / MWH_PER_GWH,
        "water_mm3": acc[_WATER] / M3_PER_MM3,
        "evap_mm3": acc[_EVAP] / M3_PER_MM3,
        "period_h": acc[_HOURS],
    }


def run_year(prm: ParamSet, year: int, seed: int = 42, dt_min: float | None = None,
             availability: float | None = None) -> YearResult:
    """One calendar year in mode "calib" from 1 January 00:00.

    Plant(prm, seed, mode="calib", t0_min=0, year=year); relines from
    reline_windows; line downtime from availability (cal_avail unless
    `availability` is given) via line_stops and Plant.set_downtime;
    dt_min default cal_step_calib_min. Aggregates totals and quarters.
    Results are cached by (parameters, year, seed, step, availability);
    do not mutate the returned object.
    """
    p = year_params(prm, year)
    dt = _dt(p, dt_min)
    a = _avail(p, availability)
    key = _cache_key(p, "year", year, seed, dt, a)
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    t_year = year_min(year)
    bins = [("year", 0.0, t_year)] + _quarter_bounds(year)
    accs, info = _simulate(p, year, 0.0, t_year, bins, seed, dt, a)
    y = _summary(accs["year"])
    if y["sag_e_kwh_t"] == NO_VALUE or y["rec_pct"] == NO_VALUE:
        raise RuntimeError(f"{year}: no ore processed in the annual run")
    extra = {
        "avail": a,
        "ore_mt_l1": y["ore_kt_l1"] / T_PER_KT,
        "ore_mt_l2": y["ore_kt_l2"] / T_PER_KT,
        "run_h_l1": y["hours_l1"],
        "run_h_l2": y["hours_l2"],
        "starved_h": y["starved_h"],
        "cu_feed_kt": y["cu_feed_kt"],
        "other_gwh": y["other_gwh"],
        "line_aux_gwh": y["line_aux_gwh"],
        "evap_mm3": y["evap_mm3"],
        "stop_h_l1": info["stop_h"][1],
        "stop_h_l2": info["stop_h"][2],
        "reline_h_l1": info["reline_h"][1],
        "reline_h_l2": info["reline_h"][2],
        "liner_x0_l1": info["liner_x0"].get(1, NO_VALUE),
        "liner_x0_l2": info["liner_x0"].get(2, NO_VALUE),
        "counter_ore_mt": info["counter_ore_mt"],
        "steps": float(info["steps"]),
    }
    for k in BALANCE_KEYS:
        extra["max_" + k] = info["bal_max"][k]
    extra.update(_balances(accs["year"], info))
    res = YearResult(
        year=year, ore_mt=y["ore_kt"] / T_PER_KT, grade_pct=y["grade_pct"], cu_conc_kt=y["cu_kt"],
        recovery_pct=y["rec_pct"], energy_gwh=y["energy_gwh"], water_mm3=y["water_mm3"],
        run_hours=y["hours"], sag_e_kwh_t=y["sag_e_kwh_t"],
        quarters={name: _summary(accs[name]) for name in QUARTERS}, extra=extra)
    _cache_put(key, res)
    return res


def run_quarter(prm: ParamSet, year: int, quarter: int, seed: int = 42, dt_min: float | None = None,
                availability: float | None = None, grade: float | None = None) -> dict[str, float]:
    """One quarter (1..4) of `year` in mode "calib", optionally at its own feed grade (% Cu).

    The run starts cal_q_warmup_d days before the quarter (not before
    1 January) so stockpiles, flotation lags and the block pipeline carry the
    quarter grade; relines and stops are the annual ones (same draws);
    liner campaign at the start from the calendar. Returns the quarter
    summary (keys as YearResult.quarters) plus "start_min".
    """
    p = year_params(prm, year)
    if grade is not None:
        p = p.copy(blk_cu_mean_pct=grade)
    dt = _dt(p, dt_min)
    a = _avail(p, availability)
    key = _cache_key(p, "quarter", year, quarter, seed, dt, a)
    hit = _CACHE.get(key)
    if hit is not None:
        return dict(hit)
    name, q0, q1 = _quarter_bounds(year)[quarter - 1]
    start = max(0.0, q0 - p["cal_q_warmup_d"] * MIN_PER_DAY)
    accs, _info = _simulate(p, year, start, q1, [(name, q0, q1)], seed, dt, a)
    res = _summary(accs[name])
    res["start_min"] = start
    _cache_put(key, dict(res))
    return res


def _cached_year(prm: ParamSet, year: int, seed: int, dt_min: float | None,
                 availability: float | None = None) -> YearResult | None:
    """Annual result if it is already in the cache (no run)."""
    p = year_params(prm, year)
    return _CACHE.get(_cache_key(p, "year", year, seed, _dt(p, dt_min), _avail(p, availability)))


# ---------------------------------------------------------------------------
# Rows and fits
# ---------------------------------------------------------------------------
def _row(group: str, name: str, model: float, report: float, unit: str, tol: float = -1.0,
         note: str = "", ok: bool | None = None) -> CheckRow:
    """CheckRow with ok = |model - report| <= tol when tol >= 0 (unless ok is given)."""
    model, report, tol = float(model), float(report), float(tol)
    if not math.isfinite(model):
        note = (note + "; " if note else "") + "model value not finite"
        model = NO_VALUE
        ok = False if tol >= 0.0 else None
    if tol < 0.0:
        ok = None
    elif ok is None:
        ok = abs(model - report) <= tol
    return CheckRow(group, name, model, report, unit, tol, ok, note)


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _next_x(xs: list[float], ys: list[float], target: float, slope0: float,
            lo: float, hi: float, trust: float) -> float:
    """Next x for y(x) = target: secant through the last two points, else the structural slope.

    The secant slope is used only when it has the sign of slope0 and lies
    within [slope0 / trust, slope0 * trust]. Result clamped to [lo, hi].
    """
    x1, y1 = xs[-1], ys[-1]
    s = slope0
    if len(xs) >= 2:
        x0, y0 = xs[-2], ys[-2]
        if abs(x1 - x0) > 1e-9 * max(1.0, abs(x1)):
            s_sec = (y1 - y0) / (x1 - x0)
            if slope0 != 0.0 and 1.0 / trust <= s_sec / slope0 <= trust:
                s = s_sec
    if s == 0.0 or not math.isfinite(s):
        return _clamp(x1, lo, hi)
    return _clamp(x1 + (target - y1) / s, lo, hi)


def _bounds(key: str) -> tuple[float, float]:
    return TABLE[key].min, TABLE[key].max


def _avail_guess(prm: ParamSet, year: int, target_mt: float) -> float:
    """Availability for `year` that gives target_mt at the 2025 fitted rate: a25 x Mt ratio x days ratio."""
    a = prm["cal_avail"] * target_mt / prm["tgt_2025_ore_mt"] * year_days(2025) / year_days(year)
    return _clamp(a, EPS_MIN, 1.0)


def _fit_score(errs: list[tuple[float, float]]) -> float:
    """Largest |error| / tolerance."""
    return max(abs(e) / t if t > 0.0 else math.inf for e, t in errs)


def fit_2025(prm: ParamSet, seed: int = 42, dt_min: float | None = None) -> tuple[ParamSet, list[CheckRow]]:
    """Fit cal_avail, sag_k, flot_rinf0_pct on 2025 (secant, <= cal_fit_runs runs); returns fitted copy and rows.

    Joint iteration, one annual run each: structural first step, then a
    secant per number on responses normalised by the known couplings:
      P/Q ~ K                      -> sag_k on mean P/Q (kWh/t);
      ore ~ availability / K       -> cal_avail on ore x K (Mt);
      residence ~ 1 / Q ~ K        -> flot_rinf0_pct on R - G ln K,
      G = R kt e^-kt / (1 - e^-kt) (pp), first slope (1 - e^-kt) R_c.
    The best run (smallest error / tolerance) is returned.
    """
    t_ore, t_e, t_rec = prm["tgt_2025_ore_mt"], prm["sag_e_base_kwh_t"], prm["tgt_2025_rec_pct"]
    tol_ore, tol_e = prm["tol_fit_frac"] * t_ore, prm["tol_fit_frac"] * t_e
    tol_rec = prm["tol_fit_rec_pp"]
    trust = prm["cal_secant_trust"]
    kt = prm["flot_ktau0"]
    s_rec0 = (1.0 - math.exp(-kt)) * prm["clean_r0_pct"] / PCT
    gain = t_rec * kt * math.exp(-kt) / (1.0 - math.exp(-kt))
    n_max = max(1, int(round(prm["cal_fit_runs"])))
    p = prm.copy()
    hist: list[tuple[ParamSet, YearResult, float]] = []
    for i in range(n_max):
        yr = run_year(p, 2025, seed, dt_min)
        score = _fit_score([(yr.ore_mt - t_ore, tol_ore), (yr.sag_e_kwh_t - t_e, tol_e),
                            (yr.recovery_pct - t_rec, tol_rec)])
        hist.append((p, yr, score))
        if score <= 1.0 or i == n_max - 1:
            break
        ks = [h[0]["sag_k"] for h in hist]
        k_next = _next_x(ks, [h[1].sag_e_kwh_t for h in hist], t_e, yr.sag_e_kwh_t / p["sag_k"],
                         *_bounds("sag_k"), trust)
        avs = [h[0]["cal_avail"] for h in hist]
        y_a = [h[1].ore_mt * h[0]["sag_k"] for h in hist]
        a_next = _next_x(avs, y_a, t_ore * k_next, y_a[-1] / avs[-1], *_bounds("cal_avail"), trust)
        rs = [h[0]["flot_rinf0_pct"] for h in hist]
        y_r = [h[1].recovery_pct - gain * math.log(h[0]["sag_k"]) for h in hist]
        r_next = _next_x(rs, y_r, t_rec - gain * math.log(k_next), s_rec0, *_bounds("flot_rinf0_pct"), trust)
        p = p.copy(cal_avail=a_next, sag_k=k_next, flot_rinf0_pct=r_next)
    best_i = min(range(len(hist)), key=lambda j: hist[j][2])
    p, yr, _score = hist[best_i]
    run_note = f"run {best_i + 1} of {len(hist)}"
    rows = [
        _row("fit 2025", "ore processed", yr.ore_mt, t_ore, "Mt", tol_ore,
             f"cal_avail {p['cal_avail']:.4f} (table {TABLE['cal_avail'].value:.4f}); {run_note}"),
        _row("fit 2025", "SAG mean P/Q while running", yr.sag_e_kwh_t, t_e, "kWh/t", tol_e,
             f"sag_k {p['sag_k']:.4f} (table {TABLE['sag_k'].value:.4f}); 26.0 MW at 3853 t/h"),
        _row("fit 2025", "recovery", yr.recovery_pct, t_rec, "%", tol_rec,
             f"flot_rinf0_pct {p['flot_rinf0_pct']:.3f} (table {TABLE['flot_rinf0_pct'].value:.3f}); "
             f"model feed {yr.grade_pct:.4f} % Cu"),
        _row("fit 2025", "Cu in concentrate", yr.cu_conc_kt, prm["tgt_2025_cu_kt"], "kt",
             prm["tol_cu_frac"] * prm["tgt_2025_cu_kt"],
             f"not fitted: ore x model feed x recovery; feed target {prm['tgt_2025_feed_pct']:.4f} % "
             f"= {prm['tgt_2025_cu_kt']:.1f} / ({t_ore:.1f} x {t_rec / PCT:.3f}), report grade "
             f"{prm['tgt_2025_grade_pct']:.2f} % is rounded"),
    ]
    return p, rows


def _fit_linear_parts(p: ParamSet, yr: YearResult, t_e: float, t_w: float, r: float) -> dict[str, float]:
    """Next pow_other_mw and water_evap_m3h from one run: E = E_rest + E_other, W = W_rest + W_evap,
    E_rest and W_rest proportional to ore; r = target ore / model ore."""
    upd = {}
    e_other = yr.extra["other_gwh"]
    w_evap = yr.extra["evap_mm3"]
    if e_other > 0.0:
        upd["pow_other_mw"] = _clamp(p["pow_other_mw"] * (t_e - (yr.energy_gwh - e_other) * r) / e_other,
                                     *_bounds("pow_other_mw"))
    if w_evap > 0.0:
        upd["water_evap_m3h"] = _clamp(p["water_evap_m3h"] * (t_w - (yr.water_mm3 - w_evap) * r) / w_evap,
                                       *_bounds("water_evap_m3h"))
    return upd


def fit_2024(prm: ParamSet, seed: int = 42, dt_min: float | None = None,
             avail_guess: float | None = None) -> tuple[ParamSet, float, YearResult, list[CheckRow]]:
    """Fit pow_other_mw and water_evap_m3h on 2024 (58.3 Mt, 2033 GWh, 34.852 Mm3, all published).

    Availability of 2024 is matched to tgt_2024_ore_mt (an input; secant
    from avail_guess, else from the 2025 rate). Each run measures the
    parts: E = E_rest + E_other, W = W_rest + W_evap, with E_rest and
    W_rest proportional to ore; the next values are other x (E_t - E_rest r)
    / E_other and evap x (W_t - W_rest r) / W_evap, r = target ore / model
    ore. K, R0 and cal_avail stay as given (2025 fit); grade 0.43 % (report).
    Returns (fitted copy, 2024 availability, best 2024 run, rows).
    """
    t_ore, t_e, t_w = prm["tgt_2024_ore_mt"], prm["tgt_2024_energy_gwh"], prm["tgt_2024_water_mm3"]
    tol_ore, tol_e, tol_w = (prm["tol_fit_frac"] * t_ore, prm["tol_fit_frac"] * t_e,
                             prm["tol_fit_frac"] * t_w)
    trust = prm["cal_secant_trust"]
    n_max = max(1, int(round(prm["cal_fit_runs"])))
    p = prm.copy()
    a = _avail_guess(prm, 2024, t_ore) if avail_guess is None else _clamp(avail_guess, EPS_MIN, 1.0)
    hist: list[tuple[ParamSet, float, YearResult, float]] = []
    for i in range(n_max):
        yr = run_year(p, 2024, seed, dt_min, availability=a)
        score = _fit_score([(yr.ore_mt - t_ore, tol_ore), (yr.energy_gwh - t_e, tol_e),
                            (yr.water_mm3 - t_w, tol_w)])
        hist.append((p, a, yr, score))
        if score <= 1.0 or i == n_max - 1:
            break
        avs = [h[1] for h in hist]
        ores = [h[2].ore_mt for h in hist]
        a_next = _next_x(avs, ores, t_ore, ores[-1] / avs[-1], EPS_MIN, 1.0, trust)
        p = p.copy(**_fit_linear_parts(p, yr, t_e, t_w, t_ore / yr.ore_mt))
        a = a_next
    best_i = min(range(len(hist)), key=lambda j: hist[j][3])
    p, a, yr, _score = hist[best_i]
    run_note = f"run {best_i + 1} of {len(hist)}"
    rows = [
        _row("fit 2024", "electricity", yr.energy_gwh, t_e, "GWh", tol_e,
             f"pow_other_mw {p['pow_other_mw']:.2f} (table {TABLE['pow_other_mw'].value:.2f}); "
             f"site part {yr.extra['other_gwh']:.0f} GWh over {year_days(2024)} d, line part "
             f"{yr.extra.get('line_aux_gwh', NO_VALUE):.0f} GWh; {run_note}"),
        _row("fit 2024", "water intake", yr.water_mm3, t_w, "Mm3", tol_w,
             f"water_evap_m3h {p['water_evap_m3h']:.1f} (table {TABLE['water_evap_m3h'].value:.1f}); "
             f"evaporation and seepage {yr.extra['evap_mm3']:.2f} Mm3, tails pores "
             f"{yr.extra.get('tails_loss_mm3', NO_VALUE):.2f} Mm3"),
        _row("fit 2024", "ore processed (input)", yr.ore_mt, t_ore, "Mt", tol_ore,
             "availability matched to the report tonnes"),
        _row("fit 2024", AVAIL_2024_NAME, a, prm["cal_avail"], "-", -1.0,
             "report column: fitted 2025 availability"),
    ]
    return p, a, yr, rows


def check_2024(prm: ParamSet, seed: int = 42, dt_min: float | None = None,
               availability: float | None = None) -> list[CheckRow]:
    """2024 without refit: recovery and Cu in concentrate at the report grade 0.43 %.

    availability: the one fit_2024 matched to 58.3 Mt (its run is cached);
    None: matched here by secant on ore (from the 2025 rate). The 2024
    electricity and water are fit targets (fit_2024), not checks here.
    """
    t_ore = prm["tgt_2024_ore_mt"]
    tol_ore = prm["tol_fit_frac"] * t_ore
    if availability is None:
        trust = prm["cal_secant_trust"]
        n_max = max(1, int(round(prm["cal_fit_runs"])))
        a = _avail_guess(prm, 2024, t_ore)
        avs: list[float] = []
        ores: list[float] = []
        for i in range(n_max):
            yr = run_year(prm, 2024, seed, dt_min, availability=a)
            avs.append(a)
            ores.append(yr.ore_mt)
            if abs(yr.ore_mt - t_ore) <= tol_ore or i == n_max - 1:
                break
            a = _next_x(avs, ores, t_ore, ores[-1] / avs[-1], EPS_MIN, 1.0, trust)
        how = f"availability {a:.4f} matched here, {len(avs)} run(s)"
    else:
        a = availability
        yr = run_year(prm, 2024, seed, dt_min, availability=a)
        how = f"availability {a:.4f} from the 2024 fit (same run)"
    t_rec, t_cu, t_g = prm["tgt_2024_rec_pct"], prm["tgt_2024_cu_kt"], prm["tgt_2024_grade_pct"]
    const_err = prm["flot_rec_ref_pct"] - t_rec
    implied = t_cu * T_PER_KT / (t_ore * T_PER_MT * t_rec / PCT) * PCT
    return [
        _row("check 2024", "ore processed (input)", yr.ore_mt, t_ore, "Mt", -1.0, how),
        _row("check 2024", "feed grade (input)", yr.grade_pct, t_g, "% Cu", prm["tol_grade_round_pct"],
             f"blk_cu_mean_pct = report grade; report balance {t_cu:.1f} / ({t_ore:.1f} x {t_rec / PCT:.3f}) "
             f"gives {implied:.4f} %"),
        _row("check 2024", "recovery", yr.recovery_pct, t_rec, "%", prm["tol_rec_pp"],
             f"model feed {yr.grade_pct:.4f} %; constant {prm['flot_rec_ref_pct']:.1f} % would be off "
             f"by {const_err:+.1f} pp"),
        _row("check 2024", "Cu in concentrate", yr.cu_conc_kt, t_cu, "kt", prm["tol_cu_frac"] * t_cu,
             "ore x model feed x recovery"),
    ]


def check_2023(prm: ParamSet, seed: int = 42, dt_min: float | None = None,
               ref: tuple[YearResult, float] | None = None) -> tuple[float, list[CheckRow]]:
    """2023 without refit: water intake and recovery at the report grade 0.50 %.

    2023 ore is not in the sources (TODO: KAZ FY2023 production report), so
    it is taken from the 2023 electricity: E = e x ore + site part, with e (GWh
    per Mt of mills, crushers, conveyors and the line part pow_line_aux_mw,
    which stops with the line) and the ore rate per available
    minute from the fitted 2024 run `ref` = (YearResult, availability); when
    None, from a 2024 run at the availability guess. One 2023 run at the
    availability that gives that ore. Ore and electricity are inputs; water
    and recovery are checks. Returns (2023 availability, rows).
    """
    if ref is None:
        a24 = _avail_guess(prm, 2024, prm["tgt_2024_ore_mt"])
        yr24 = run_year(prm, 2024, seed, dt_min, availability=a24)
    else:
        yr24, a24 = ref
    other24 = yr24.extra["other_gwh"]
    e_mt = (yr24.energy_gwh - other24) / yr24.ore_mt                      # GWh per Mt
    other23 = other24 * year_min(2023) / year_min(2024)
    t_e, t_w = prm["tgt_2023_energy_gwh"], prm["tgt_2023_water_mm3"]
    ore23 = (t_e - other23) / e_mt
    rate = yr24.ore_mt / (a24 * year_min(2024))                          # Mt per available minute
    a = _clamp(ore23 / (rate * year_min(2023)), EPS_MIN, 1.0)
    yr = run_year(prm, 2023, seed, dt_min, availability=a)
    t_rec, t_g = prm["tgt_2023_rec_pct"], prm["tgt_2023_grade_pct"]
    const_err = prm["flot_rec_ref_pct"] - t_rec
    rows = [
        _row("check 2023", "ore processed (input)", yr.ore_mt, ore23, "Mt", -1.0,
             f"report column: ore implied by {t_e:.0f} GWh with the 2024 fit ({e_mt:.2f} kWh/t for mills, "
             f"crushers, conveyors and line loads that stop with the line; site part {other23:.0f} GWh); "
             f"2023 ore not in sources yet"),
        _row("check 2023", AVAIL_2023_NAME, a, prm["cal_avail"], "-", -1.0,
             "report column: fitted 2025 availability; no reline of 2023 in the calendar"),
        _row("check 2023", "electricity (input)", yr.energy_gwh, t_e, "GWh", -1.0,
             "gives the ore above, not a check"),
        _row("check 2023", "feed grade (input)", yr.grade_pct, t_g, "% Cu", prm["tol_grade_round_pct"],
             "blk_cu_mean_pct = report grade"),
        _row("check 2023", "water intake", yr.water_mm3, t_w, "Mm3", prm["tol_water_frac"] * t_w,
             f"evaporation and seepage {yr.extra['evap_mm3']:.2f} Mm3 (2024 fit), tails pores "
             f"{yr.extra.get('tails_loss_mm3', NO_VALUE):.2f} Mm3"),
        _row("check 2023", "recovery", yr.recovery_pct, t_rec, "%", prm["tol_rec_pp"],
             f"model feed {yr.grade_pct:.4f} %; constant {prm['flot_rec_ref_pct']:.1f} % would be off "
             f"by {const_err:+.1f} pp"),
    ]
    return a, rows


def check_2025_site(prm: ParamSet, seed: int = 42, dt_min: float | None = None) -> list[CheckRow]:
    """2025 feed grade, site electricity and water of a 2025 run with the given (final) parameters.

    Electricity and water of 2025 are not published. Totals are shown
    against the 2024 report without tolerance (ore differs: 62.1 vs 58.3
    Mt); the per tonne rows carry the 2024 tolerances. The other load and
    the evaporation come from the 2024 fit.
    """
    yr = run_year(prm, 2025, seed, dt_min)
    g = "check 2025"
    ore = yr.ore_mt
    e24, w24, o24 = prm["tgt_2024_energy_gwh"], prm["tgt_2024_water_mm3"], prm["tgt_2024_ore_mt"]
    kwh_t = yr.energy_gwh / ore if ore > 0.0 else NO_VALUE          # GWh / Mt = kWh/t
    m3_t = yr.water_mm3 / ore if ore > 0.0 else NO_VALUE            # Mm3 / Mt = m3/t
    rec = yr.extra.get("recycle_mm3", NO_VALUE)
    rec_t = rec / ore if ore > 0.0 and rec >= 0.0 else NO_VALUE
    ref = "2025 not published, report column: 2024"
    e24_t, w24_t = e24 / o24, w24 / o24
    return [
        _row(g, "feed grade (input)", yr.grade_pct, prm["tgt_2025_grade_pct"], "% Cu", prm["tol_grade_round_pct"],
             f"blk_cu_mean_pct = tgt_2025_feed_pct {prm['tgt_2025_feed_pct']:.4f} % (report Cu / (ore x "
             f"recovery)); block model and stockpile give the model feed"),
        _row(g, "electricity, site", yr.energy_gwh, e24, "GWh", -1.0,
             f"{ref} at {o24:.1f} Mt, model {ore:.1f} Mt; other {yr.extra.get('other_gwh', NO_VALUE):.0f} GWh "
             f"(2024 fit)"),
        _row(g, "electricity per t ore", kwh_t, e24_t, "kWh/t", prm["tol_energy_frac"] * e24_t,
             "2024 report per t; the constant other load spreads over more ore in 2025"),
        _row(g, "water intake", yr.water_mm3, w24, "Mm3", -1.0,
             f"{ref} at {o24:.1f} Mt; evaporation and seepage {yr.extra.get('evap_mm3', NO_VALUE):.2f} Mm3 "
             f"(2024 fit)"),
        _row(g, "water intake per t ore", m3_t, w24_t, "m3/t", prm["tol_water_frac"] * w24_t,
             f"2024 report per t; OVOS fresh water {prm['water_fresh_lo_m3_t']:.2f}-"
             f"{prm['water_fresh_hi_m3_t']:.2f} m3/t"),
        _row(g, "water recycle per t ore", rec_t, prm["water_recycle_m3_t"], "m3/t", -1.0, "OVOS"),
    ]


def check_balances(prm: ParamSet, year: int, seed: int = 42, dt_min: float | None = None,
                   availability: float | None = None) -> list[CheckRow]:
    """Balances of an annual run (cached, no extra run): Cu, concentrate, ore stock, water, power peaks.

    Residuals are % of the inflow, tolerance tol_balance_pct. Run totals are
    closed from unit states (_balances); "largest" rows are Plant.balances
    sampled daily and at the run end. Power peaks must stay in 0..limit
    (grid limit, rated SAG and ball mill drives); the SAG feed-end wear
    counter in 0..liner_feed_end_mm.
    """
    yr = run_year(prm, year, seed, dt_min, availability)
    x = yr.extra
    g = f"balance {year}"
    tol = prm["tol_balance_pct"]

    def res(name: str, key: str, note: str) -> CheckRow:
        v = x.get(key, NO_VALUE)
        if v == NO_VALUE:
            return _row(g, name, NO_VALUE, 0.0, "%", -1.0, note + "; not available")
        return _row(g, name, v, 0.0, "%", tol, note)

    def peak(name: str, v: float, limit: float, note: str) -> CheckRow:
        return _row(g, name, v, 0.5 * limit, "MW", 0.5 * limit, f"band 0-{limit:.0f} MW ({note})")

    grid = x.get("grid_limit_mw", NO_VALUE)
    if grid <= 0.0:
        grid = prm["pow_grid_limit_mw"]
    mean_mw = yr.energy_gwh * MWH_PER_GWH / (year_min(year) / MIN_PER_H)
    wear_cap = prm["liner_feed_end_mm"]
    return [
        res("Cu: feed - concentrate - tails", "cu_bal_pct",
            f"feed {x.get('cu_feed_kt', NO_VALUE):.1f} = concentrate {yr.cu_conc_kt:.1f} + tails "
            f"{x.get('cu_tails_kt', NO_VALUE):.1f} kt; flotation holds no Cu"),
        res("Cu: largest |residual|, plant counters", "max_cu_residual_pct", "Plant.balances, daily and at the end"),
        res("concentrate: cleaner = thickener + filter = stock + shipped", "max_conc_residual_pct",
            "largest |residual|, Plant.balances"),
        res("ore: stockpile in - out - level change", "stock_bal_pct",
            f"level change {x.get('stock_change_kt', NO_VALUE):+.1f} kt over the run"),
        res("ore: SAG feed - stockpile out", "reclaim_bal_pct", "SAG feed is drawn from the stockpile only"),
        res("water: intake - losses - pond change", "water_bal_pct",
            f"intake {yr.water_mm3:.2f} = tails {x.get('tails_loss_mm3', NO_VALUE):.2f} + concentrate "
            f"{x.get('conc_moist_mm3', NO_VALUE):.3f} + evaporation {x.get('evap_mm3', NO_VALUE):.2f} + pond "
            f"{x.get('pond_change_mm3', NO_VALUE):+.3f} Mm3"),
        res("water: largest |residual| of water_step", "max_water_residual_pct", "Plant.balances, daily and at the end"),
        peak("site power highest", x.get("site_mw_max", NO_VALUE), grid, f"grid limit; mean {mean_mw:.1f} MW"),
        peak("SAG power highest", x.get("sag_mw_max", NO_VALUE), prm["sag_rated_mw"], "rated drive, shaft"),
        peak("ball mill power highest", x.get("ball_mw_max", NO_VALUE), prm["ball_rated_mw"], "rated drive, shaft"),
        _row(g, "SAG feed-end wear counter highest", x.get("liner_wear_mm_max", NO_VALUE),
             0.5 * wear_cap, "mm", 0.5 * wear_cap,
             f"band 0-{wear_cap:.0f} mm: feed end changed at intermediate relines (liner_feed_end_mm)"),
    ]


def check_reline_quarter(prm: ParamSet, seed: int = 42, dt_min: float | None = None) -> list[CheckRow]:
    """Line 2 Q3 vs Q2 2025 tonnes change, model vs tgt_reline_q_pct, tolerance tol_reline_pp.

    The August 2025 SAG reline of line 2 is named in the Q3 2025 report
    (p. 3); its length liner_reline_h is an assumption, so the row is a
    check and not a fit.
    """
    yr = run_year(prm, 2025, seed, dt_min)
    q2, q3 = yr.quarters["Q2"], yr.quarters["Q3"]
    l2_q2, l2_q3 = q2["ore_kt_l2"], q3["ore_kt_l2"]
    pct = (l2_q3 / l2_q2 - 1.0) * PCT if l2_q2 > 0.0 else NO_VALUE
    h2, h3 = prm["tgt_q2_2025_hours"], prm["tgt_q3_2025_hours"]
    hours_only = ((h3 - prm["liner_reline_h"]) / h2 - 1.0) * PCT
    return [
        _row("reline", "line 2 tonnes Q3 vs Q2 2025", pct, prm["tgt_reline_q_pct"], "%", prm["tol_reline_pp"],
             f"SAG reline of line 2 in August 2025 named in the Q3 2025 report (p. 3); its length "
             f"{prm['liner_reline_h']:.0f} h is an assumption, not taken from this quarter; hours alone "
             f"give {hours_only:+.1f} %; model adds stockpile, stops and the liner campaign (peak before, "
             f"new-liner ramp after); run hours Q2 {q2['hours_l2']:.0f} h, Q3 {q3['hours_l2']:.0f} h"),
        _row("reline", "line 2 ore Q2 2025", l2_q2, prm["tgt_q2_2025_l2_kt"], "kt", -1.0, "annual 2025 run"),
        _row("reline", "line 2 ore Q3 2025", l2_q3, prm["tgt_q3_2025_l2_kt"], "kt", -1.0, "annual 2025 run"),
    ]


def check_quarters(prm: ParamSet, seed: int = 42, dt_min: float | None = None) -> list[CheckRow]:
    """Quarter recovery: model from quarter grade vs report, and constant flot_rec_ref_pct vs report.

    Q3 2025 (grade in sources): quarter run at its grade; its tolerance is
    the error of the constant, so ok means the model beats the constant.
    Q2 2025: grade not in sources yet, shown at the annual grade without
    tolerance. Other quarters 2023-2025: TODO (grades not in sources).
    """
    yr = run_year(prm, 2025, seed, dt_min)
    g3, r3 = prm["tgt_q3_2025_grade_pct"], prm["tgt_q3_2025_rec_pct"]
    q = run_quarter(prm, 2025, 3, seed, dt_min, grade=g3)
    const = prm["flot_rec_ref_pct"]
    const_err = abs(const - r3)
    start_day = int(q["start_min"] // MIN_PER_DAY) + 1
    rows = [
        _row("quarters", "Q3 2025 recovery, model at quarter grade", q["rec_pct"], r3, "%", const_err,
             f"tolerance = error of the constant {const:.1f} %; grade {g3:.2f} % "
             f"(model feed {q['grade_pct']:.4f} %); run from day {start_day}",
             ok=abs(q["rec_pct"] - r3) < const_err),
        _row("quarters", "Q3 2025 recovery, constant", const, r3, "%", -1.0, "flot_rec_ref_pct, reference error"),
        _row("quarters", "Q3 2025 recovery, model at annual grade", yr.quarters["Q3"]["rec_pct"], r3, "%", -1.0,
             f"annual run, grade {yr.quarters['Q3']['grade_pct']:.4f} %"),
        _row("quarters", "Q2 2025 recovery, model at annual grade", yr.quarters["Q2"]["rec_pct"],
             prm["tgt_q2_2025_rec_pct"], "%", -1.0, "Q2 grade not in sources yet"),
        _row("quarters", "Q3 2025 ore processed", yr.quarters["Q3"]["ore_kt"], prm["tgt_q3_2025_ore_kt"], "kt",
             -1.0, "annual run; quarterly tonnes are not fitted"),
    ]
    return rows


# ---------------------------------------------------------------------------
# Free-run week
# ---------------------------------------------------------------------------
class _ShiftCount(PlantHooks):
    """Counts shift ends reported by the plant."""

    def __init__(self) -> None:
        self.ends = 0

    def on_shift_end(self, st, summary) -> None:
        self.ends += 1


def week_check(prm: ParamSet, seed: int = 42) -> list[CheckRow]:
    """7 model days of free run at cal_week_step_min: drift and balance rows.

    Plant(mode "free") warmed up 06:00 -> 08:00, then cal_week_days days.
    Bands (row report = band centre, tolerance = half width): stockpiles
    tol_week_stock_lo_pct..hi_pct of stock_live_t, pond pond_lo_m3..pond_hi_m3,
    site power 0..pow_grid_limit_mw. Balance residuals sampled hourly,
    |max| <= tol_balance_pct. Shift counters: resets = days x 24 / cal_shift_h
    (+- tol_week_resets) and no counter longer than a shift (+ one step).
    ACS false alarms: rising edges of analyzer.alarm with no hidden cause on
    that line (from its start to its end + flot_delay_min + cal_alarm_lags x
    flot_tau_min + acs_cycles x sens_an_cycle_min), <= tol_week_false_alarms.
    """
    days, dt = prm["cal_week_days"], prm["cal_week_step_min"]
    hooks = _ShiftCount()
    plant = Plant(prm, seed, mode="free", hooks=hooks)
    plant.warmup()
    st = plant.state
    t0 = plant.t_min
    t_end = t0 + days * MIN_PER_DAY
    live = prm["stock_live_t"]
    lv_min = {ln.n: math.inf for ln in st.lines}
    lv_max = {ln.n: -math.inf for ln in st.lines}
    lv_first = {ln.n: PCT * ln.stockpile.level_t / live for ln in st.lines}
    ore_t = {ln.n: 0.0 for ln in st.lines}
    pond_min, pond_max, site_max = math.inf, -math.inf, -math.inf
    bal_max = {k: 0.0 for k in BALANCE_KEYS}
    bal_n, bal_err = 0, ""
    resets, prev_min = 0, st.shift.minutes
    max_shift = prev_min
    prev_alarm = {ln.n: bool(ln.analyzer.alarm) for ln in st.lines}
    edges: list[tuple[int, float]] = []
    causes: dict[tuple, object] = {}
    next_bal = t0 + MIN_PER_H
    while plant.t_min < t_end - EPS_MIN:
        t = plant.t_min
        plant.step(min(dt, t_end - t))
        t2 = plant.t_min
        if not t2 > t:
            raise RuntimeError(f"Plant.step did not advance the clock at minute {t}")
        hh = (t2 - t) / MIN_PER_H
        for ln in st.lines:
            lv = PCT * ln.stockpile.level_t / live
            lv_min[ln.n] = min(lv_min[ln.n], lv)
            lv_max[ln.n] = max(lv_max[ln.n], lv)
            ore_t[ln.n] += max(0.0, ln.sag.feed_tph) * hh
            alarm = bool(ln.analyzer.alarm)
            if alarm and not prev_alarm[ln.n]:
                edges.append((ln.n, t2))
            prev_alarm[ln.n] = alarm
        pond_min = min(pond_min, st.water.pond_m3)
        pond_max = max(pond_max, st.water.pond_m3)
        site_max = max(site_max, st.power.site_mw)
        m = st.shift.minutes
        if m < prev_min - EPS_MIN:
            resets += 1
        max_shift = max(max_shift, m)
        prev_min = m
        for c in st.causes:
            causes[(c.kind, c.line, c.t_start_min)] = c
        if t2 >= next_bal - EPS_MIN:
            next_bal += MIN_PER_H
            if not bal_err:
                try:
                    b = plant.balances()
                    bal_n += 1
                    for k in BALANCE_KEYS:
                        v = b.get(k, 0.0)
                        if isinstance(v, (int, float)) and math.isfinite(v):
                            bal_max[k] = max(bal_max[k], abs(v))
                except Exception as e:  # reported in the rows
                    bal_err = f"{type(e).__name__}: {e}"
    lag = (prm["flot_delay_min"] + prm["cal_alarm_lags"] * prm["flot_tau_min"]
           + prm["acs_cycles"] * prm["sens_an_cycle_min"])

    def explained(line: int, t: float) -> bool:
        for c in causes.values():
            if c.line == line and c.t_start_min <= t and (c.t_end_min < 0.0 or t <= c.t_end_min + lag):
                return True
        return False

    false_alarms = sum(1 for n, t in edges if not explained(n, t))
    lo, hi = prm["tol_week_stock_lo_pct"], prm["tol_week_stock_hi_pct"]
    s_mid, s_half = 0.5 * (lo + hi), 0.5 * (hi - lo)
    p_lo, p_hi = prm["pond_lo_m3"] / M3_PER_MM3, prm["pond_hi_m3"] / M3_PER_MM3
    grid = prm["pow_grid_limit_mw"]
    shift_min = prm["cal_shift_h"] * MIN_PER_H
    expect_resets = round(days * MIN_PER_DAY / shift_min)
    band = f"band {lo:.0f}-{hi:.0f} %"
    rows = []
    for n in sorted(lv_min):
        rows.append(_row("week", f"stockpile-{n} lowest level", lv_min[n], s_mid, "%", s_half,
                         f"{band}; start {lv_first[n]:.0f} %"))
        rows.append(_row("week", f"stockpile-{n} highest level", lv_max[n], s_mid, "%", s_half, band))
    p_mid, p_half = 0.5 * (p_lo + p_hi), 0.5 * (p_hi - p_lo)
    pond_band = f"band {p_lo:.2f}-{p_hi:.2f} Mm3"
    rows.append(_row("week", "pond lowest", pond_min / M3_PER_MM3, p_mid, "Mm3", p_half, pond_band))
    rows.append(_row("week", "pond highest", pond_max / M3_PER_MM3, p_mid, "Mm3", p_half, pond_band))
    for k in BALANCE_KEYS:
        if bal_err:
            rows.append(_row("week", f"max |{k}|", NO_VALUE, 0.0, "%", prm["tol_balance_pct"],
                             "balances: " + bal_err, ok=False))
        else:
            rows.append(_row("week", f"max |{k}|", bal_max[k], 0.0, "%", prm["tol_balance_pct"],
                             f"{bal_n} hourly samples"))
    rows.append(_row("week", "site power highest", site_max, 0.5 * grid, "MW", 0.5 * grid,
                     f"band 0-{grid:.0f} MW (grid limit)"))
    rows.append(_row("week", "shift counter resets", resets, expect_resets, "-", prm["tol_week_resets"],
                     f"on_shift_end calls {hooks.ends}"))
    rows.append(_row("week", "longest shift counter", max_shift, shift_min, "min", dt,
                     "shift counters must restart every shift"))
    rows.append(_row("week", "ACS false alarms", false_alarms, 0.0, "1/week", prm["tol_week_false_alarms"],
                     f"tails setpoint {prm['acs_tail_sp_pct']:.3f} % Cu; {len(edges)} alarms, "
                     f"{len(causes)} hidden causes"))
    for n in sorted(ore_t):
        rows.append(_row("week", f"line {n} mean t/h", ore_t[n] / (days * 24.0), prm["cal_line_tph"], "t/h", -1.0,
                         "free run: no planned stops; pebble stops and hidden causes on"))
    return rows


# ---------------------------------------------------------------------------
# Whole calibration and output
# ---------------------------------------------------------------------------
def _err_text(stage: str, e: BaseException) -> str:
    tb = traceback.extract_tb(e.__traceback__)
    where = f" (at {os.path.basename(tb[-1].filename)}:{tb[-1].lineno} {tb[-1].name})" if tb else ""
    msg = str(e) or ("not implemented yet" if isinstance(e, NotImplementedError) else "")
    return f"{stage}: {type(e).__name__}: {msg}{where}"


def _avail_from_rows(rows: list[CheckRow], name: str) -> float | None:
    for r in rows:
        if r.name == name:
            return r.model
    return None


def run_all(seed: int = 42, dt_min: float | None = None, quick: bool = False) -> dict:
    """Full calibration; returns {"seed", "dt_min", "fitted": {key: value}, "rows": [CheckRow as dict],
    "errors": [text]}. quick=True: dt 30 min, no week check (for tests).

    Also "quick", "year_avail" {year: availability}, "years" {year: YearResult
    as dict} and "seconds" {stage: wall s}. A failing stage adds an error and
    the next stages go on with the parameters fitted so far. Every check and
    balance runs with the final parameters (2025 fit plus 2024 fit).
    """
    wall0 = time.perf_counter()
    prm0 = default()
    if dt_min is None:
        dt = prm0["cal_quick_step_min"] if quick else prm0["cal_step_calib_min"]
    else:
        dt = float(dt_min)
    rows: list[CheckRow] = []
    errors: list[str] = []
    seconds: dict[str, float] = {}

    def stage(name, fn):
        t = time.perf_counter()
        try:
            return fn()
        except Exception as e:  # one stage failing must not stop the others
            errors.append(_err_text(name, e))
            return None
        finally:
            seconds[name] = round(time.perf_counter() - t, 2)

    p25 = prm0
    res = stage("fit 2025", lambda: fit_2025(prm0, seed, dt))
    if res:
        p25, r = res
        rows += r
    p_fin, a24, yr24 = p25, None, None
    res = stage("fit 2024", lambda: fit_2024(p25, seed, dt))
    if res:
        p_fin, a24, yr24, r = res
        rows += r
    rows += stage("check 2024", lambda: check_2024(p_fin, seed, dt, availability=a24)) or []
    a23 = None
    ref = (yr24, a24) if (yr24 is not None and a24 is not None) else None
    res = stage("check 2023", lambda: check_2023(p_fin, seed, dt, ref))
    if res:
        a23, r = res
        rows += r
    rows += stage("check 2025", lambda: check_2025_site(p_fin, seed, dt)) or []
    rows += stage("reline", lambda: check_reline_quarter(p_fin, seed, dt)) or []
    rows += stage("quarters", lambda: check_quarters(p_fin, seed, dt)) or []
    rows += stage("balance 2025", lambda: check_balances(p_fin, 2025, seed, dt)) or []
    if a24 is not None:
        rows += stage("balance 2024", lambda: check_balances(p_fin, 2024, seed, dt, a24)) or []
    if not quick:
        rows += stage("week", lambda: week_check(p_fin, seed)) or []

    fit_keys = [k for k, prow in TABLE.items() if prow.fit]
    fitted = {k: p_fin[k] for k in fit_keys}
    for k in fit_keys:
        rows.append(_row("fit params", k, p_fin[k], TABLE[k].value, TABLE[k].unit, -1.0,
                         "report column: table value"))
    year_avail = {"2025": p_fin["cal_avail"]}
    years = {}
    for year, a in ((2025, None), (2024, a24), (2023, a23)):
        if year != 2025 and a is None:
            continue
        if a is not None:
            year_avail[str(year)] = a
        yr = _cached_year(p_fin, year, seed, dt, a)
        if yr is not None:
            years[str(year)] = asdict(yr)
            if yr.run_hours > 0.0:
                rows.append(_row("fit params", f"SAG running hours per line {year}", yr.run_hours,
                                 prm0["cal_hours_run"], "h", -1.0, "report column: OVOS design hours"))
    total = time.perf_counter() - wall0
    seconds["total"] = round(total, 2)
    if total > prm0["cal_budget_s"]:
        errors.append(f"calibration took {total:.0f} s, limit {prm0['cal_budget_s']:.0f} s (design section 9)")
    return {"seed": seed, "dt_min": dt, "quick": quick, "fitted": fitted,
            "rows": [asdict(r) for r in rows], "errors": errors,
            "year_avail": year_avail, "years": years, "seconds": seconds}


def _num(x: float) -> str:
    """Short fixed-point text: 4 significant digits, at least 1 decimal for numbers >= 1000."""
    if not math.isfinite(x):
        return str(x)
    ax = abs(x)
    if ax >= 1000.0:
        return f"{x:.1f}"
    if ax >= 100.0:
        return f"{x:.2f}"
    if ax >= 1.0:
        return f"{x:.3f}"
    return f"{x:.4f}"


def format_table(rows: list[CheckRow]) -> str:
    """Plain text table: group | name | model | report | deviation | tolerance | ok."""
    head = ("group", "name", "model", "report", "unit", "deviation", "tolerance", "ok", "note")
    if not rows:
        return " | ".join(head) + "\n(no rows)"
    body = []
    n_ok = n_bad = n_info = 0
    for r in rows:
        dev = r.model - r.report
        dev_s = f"{dev:+.4g}"
        if r.report != 0.0 and r.unit not in ("%", "pp"):
            dev_s += f" ({PCT * dev / abs(r.report):+.1f} %)"
        tol_s = f"+-{_num(r.tol)}" if r.tol >= 0.0 else "-"
        if r.ok is True:
            ok_s, n_ok = "ok", n_ok + 1
        elif r.ok is False:
            ok_s, n_bad = "NO", n_bad + 1
        else:
            ok_s, n_info = "-", n_info + 1
        body.append((r.group, r.name, _num(r.model), _num(r.report), r.unit, dev_s, tol_s, ok_s, r.note))
    widths = [max(len(head[i]), *(len(b[i]) for b in body)) for i in range(len(head) - 1)]

    def line(cells) -> str:
        parts = [str(c).ljust(widths[i]) if i < len(widths) else str(c) for i, c in enumerate(cells)]
        return " | ".join(parts).rstrip()

    out = [line(head), "-+-".join("-" * w for w in widths) + "-+-" + "-" * len(head[-1])]
    out += [line(b) for b in body]
    out.append(f"{len(rows)} rows: {n_ok} ok, {n_bad} not ok, {n_info} without tolerance")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    """CLI. Prints the table, writes JSON (--out, default calib.json). Always returns 0."""
    ap = argparse.ArgumentParser(description="Aktogay model calibration and checks")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--dt", type=float, default=None, help="step, model minutes")
    ap.add_argument("--out", default="calib.json")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--publish", action="store_true",
                    help="write state and report_json to the Ditto thing validation-calib (sim/calib_report.py)")
    ap.add_argument("--trial", default=calib_report.TRIAL_DEFAULT,
                    help="on/off trial summary shown next to the table ('' = none)")
    a = ap.parse_args(argv)
    trial = calib_report.load_trial(a.trial) if a.publish else None
    writer = calib_report.DittoWriter.from_env() if a.publish else None
    if writer is not None:
        calib_report.publish_start(writer, trial)
    try:
        report = run_all(seed=a.seed, dt_min=a.dt, quick=a.quick)
    except NotImplementedError as e:
        report = {"errors": ["not implemented yet: " + (str(e) or "run_all")]}
    except Exception as e:  # the table must still be printed, exit code stays 0
        report = {"errors": [f"{type(e).__name__}: {e}"]}
    report.setdefault("seed", a.seed)
    report.setdefault("dt_min", a.dt)
    report.setdefault("fitted", {})
    report.setdefault("rows", [])
    report.setdefault("errors", [])
    try:
        print(format_table([CheckRow(**r) for r in report["rows"]]))
    except NotImplementedError:
        pass
    for err in report["errors"]:
        print("error:", err)
    try:
        with open(a.out, "w", encoding="utf-8", newline="\n") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
        print("wrote", a.out)
    except OSError as e:
        print("error: cannot write", a.out, e)
    if writer is not None:
        try:
            calib_report.publish_done(writer, report, trial)
        except Exception as e:  # noqa: BLE001 - the table is printed, exit code stays 0
            print(f"validation-calib not written: {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
