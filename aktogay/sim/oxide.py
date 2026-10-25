"""Oxide chain of Aktogay: ore to the heap -> heap leach pad -> PLS pond -> solvent extraction (SX) -> electrowinning (EW) -> cathode store.

What the reports give (sim/data/kaz_oxide_quarterly.csv, 34 quarters 2018Q1-2026Q2, every row has the URL of its report): the oxide ore
placed on the leach pads (kt) and its grade (%), and the copper cathode (kt, also sim/data/kaz_quarterly.csv). What they do not give:
the solution flows, the PLS grade, the SX extraction, the tankhouse current. Those come from the EIA (raffinate 1 500 m3/h), the project
(25 kt of cathode a year) and analogs; every number is a row `ox_*` of the parameter table with its label.

Physics, one block per twin (step of the plant, any dt):

  oxfeed-1  ore placed per hour = ore of the quarter / hours of the quarter; copper placed = ore x grade
  leach-1   the pad is a set of cohorts, one per month of placing (index 0 = ore placed before 2018). A cohort holds the placed copper
            and a thermal age theta (days at 20 degC). The share of the leachable copper dissolved is
            R(theta) = 1 - exp(-theta/th); the age grows by
            f(T) x days x irrigation, f(T) = exp(Ea/R x (1/293.15 - 1/(T_pad + 273.15))), the pad temperature follows the air temperature
            (ERA5 monthly means) with a lag. The dissolved copper is the sum over the cohorts of copper x rmax x dR.
  pls-1     the dissolved copper reaches the PLS pond with a lag of the pad; the pond holds a volume and a copper mass; the SX feed
            follows the level; the raffinate pond closes the loop: raffinate copper goes back to the pad with the irrigation
  sx-1      extraction eta of the copper of the PLS (crud lowers eta and the flow the settler can take); the loaded organic strips
            into the electrolyte unless the electrolyte is full
  ew-1      tankhouse: deposition = g/Ah x I x cells x current efficiency (Faraday); the control sets the current to hold the
            copper of the electrolyte, the rectifier limit is ox_ew_overload x the design current; a rectifier trip sets I = 0
  catstore  cathode in, loads out when the store holds a batch

Calibration. The kinetics (rmax, theta, Ea, copper placed before 2018) are fitted on the cathode of the quarters
2018Q1-2024Q4 by `calibrate()`; 2025Q1-2026Q2 are a forward test. `backtest()` runs the same pad code with the weekly step and
compares the dissolved copper of each quarter with the reported cathode (the chain after the pad only delays the copper by hours).

The quarter is that of the host date (Plant.ox_date, set by akt-sim) or, without it, of the model clock; a date after 2025 takes the
same day of 2025. No random draw, no effect on the sulphide plant, the power balance or the money counters: the oxide complex is already
inside pow_other_mw (the tankhouse power is published as information).
"""
from __future__ import annotations

import csv
import datetime
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "data", "kaz_quarterly.csv")
OX_CSV_PATH = os.path.join(HERE, "data", "kaz_oxide_quarterly.csv")
WEATHER_PATH = os.path.join(HERE, "data", "weather_era5.json")
FIRST_YEAR, LAST_YEAR = 2018, 2025
FIT_LAST_QUARTER = (2025, 4)      # the fit uses the quarters up to this one; the rest (2026H1) is the forward test
STRICT_LAST_QUARTER = (2024, 4)   # the stricter test: fit up to 2024, forward 2025-2026H1
MIN_PER_DAY = 1440.0
MIN_PER_H = 60.0
KT_TO_T = 1000.0                  # unit conversion
R_GAS = 8.314462618               # J/(mol K), physics
T_REF_K = 293.15                  # 20 degC, the reference of the rate (convention)
HOURS_YEAR = 8760.0
WEEK_D = 7                        # step of the calibration run and of the spin-up, days
HEAP_UPDATE_MIN = 60.0            # the cohorts are updated once per model hour
EPS = 1e-9
D0 = datetime.date(FIRST_YEAR, 1, 1)
KIN_KEYS = ("ox_rmax", "ox_th_d", "ox_ea_app_jmol", "ox_heap_tau_d", "ox_m0_t")

_CATHODE: dict[tuple[int, int], float] | None = None
_QUARTERS: dict[tuple[int, int], tuple[float, float, float]] | None = None
_MONTHLY_T: list[float] | None = None
_TRAJ: dict[tuple, dict] = {}


# ---------------------------------------------------------------------------------------------------------------------
# Reports and the calendar
# ---------------------------------------------------------------------------------------------------------------------
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


def quarters() -> dict[tuple[int, int], tuple[float, float, float]]:
    """{(year, quarter): (oxide ore to the pads kt, grade %, cathode kt)} of the 34 quarters 2018Q1-2026Q2."""
    global _QUARTERS
    if _QUARTERS is None:
        out: dict[tuple[int, int], tuple[float, float, float]] = {}
        with open(OX_CSV_PATH, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                q = r["quarter"]
                out[(int(q[:4]), int(q[5]))] = (float(r["ore_to_pads_kt"]), float(r["grade_pct"]), float(r["cathode_kt"]))
        _QUARTERS = out
    return _QUARTERS


def quarter_of(year: int, doy0: float) -> tuple[int, int]:
    """(year, quarter 1..4) of a 0-based day of the year; the year is kept inside the reports (after 2025 -> 2025)."""
    y = min(max(int(year), FIRST_YEAR), LAST_YEAR)
    day = datetime.date(y, 1, 1) + datetime.timedelta(days=int(doy0) % 365)
    return y, (day.month - 1) // 3 + 1


def date_of(year: int, doy0: float) -> datetime.date:
    y = min(max(int(year), FIRST_YEAR), LAST_YEAR)
    return datetime.date(y, 1, 1) + datetime.timedelta(days=int(doy0) % 365)


def quarter_hours(year: int, quarter: int) -> float:
    a = datetime.date(year, 3 * (quarter - 1) + 1, 1)
    b = datetime.date(year + 1, 1, 1) if quarter == 4 else datetime.date(year, 3 * quarter + 1, 1)
    return (b - a).days * 24.0


def level_tph(year: int, quarter: int) -> float:
    """Cathode of the quarter as t/h (the reported level, for the comparison with the model)."""
    return cathode_by_quarter()[(year, quarter)] * KT_TO_T / quarter_hours(year, quarter)


def _ore_rate(year: int, quarter: int) -> tuple[float, float, float]:
    """(ore t/h, grade %, ore kt) placed on the pads in the quarter."""
    ore_kt, grade, _c = quarters()[(year, quarter)]
    return ore_kt * KT_TO_T / quarter_hours(year, quarter), grade, ore_kt


def air_t_c(d: datetime.date) -> float:
    """Air temperature of the day, degC: ERA5 monthly means of Aktogay 2018-2025, linear between the middles of the months."""
    global _MONTHLY_T
    if _MONTHLY_T is None:
        with open(WEATHER_PATH, encoding="utf-8") as f:
            w = json.load(f)
        _MONTHLY_T = [float(m["t_mean"]) for m in sorted(w["stats"]["climatology"]["monthly"], key=lambda m: m["month"])]
    mt = _MONTHLY_T
    n = (datetime.date(d.year + (d.month == 12), d.month % 12 + 1, 1) - datetime.date(d.year, d.month, 1)).days
    x = (d.day - 0.5) / n - 0.5
    m = d.month - 1
    if x >= 0.0:
        a, b, fr = m, (m + 1) % 12, x
    else:
        a, b, fr = (m - 1) % 12, m, x + 1.0
    return mt[a] * (1.0 - fr) + mt[b] * fr


def cohort_index(d: datetime.date) -> int:
    """Cohort of the month of placing: 0 = before 2018, 1 = January 2018, ..."""
    return (d.year - FIRST_YEAR) * 12 + d.month


# ---------------------------------------------------------------------------------------------------------------------
# Heap kinetics
# ---------------------------------------------------------------------------------------------------------------------
def kinetics(prm) -> tuple:
    """(rmax, theta d, Ea J/mol, lag of the pad temperature d, leachable copper placed before 2018, t)."""
    return tuple(float(prm[k]) for k in KIN_KEYS)


def _rec(th: float, th0: float) -> float:
    """Share of the leachable copper dissolved at the thermal age th (days at 20 degC)."""
    return 1.0 - math.exp(-th / th0)


def arrhenius(heap_c: float, ea: float) -> float:
    """Rate against 20 degC at the pad temperature."""
    return math.exp(ea / R_GAS * (1.0 / T_REF_K - 1.0 / (heap_c + 273.15)))


class _Heap:
    """The pad for the back-test and the spin-up: the same fields as LeachState."""
    __slots__ = ("cu_c", "th_c", "rc_c", "heap_temp_c", "k_factor")

    def __init__(self, kin: tuple, t0: float):
        self.cu_c = [kin[4] / kin[0]]
        self.th_c = [0.0]
        self.rc_c = [0.0]
        self.heap_temp_c = t0
        self.k_factor = 1.0


def heap_step(lc, kin: tuple, dd: float, t_air: float, contact: float, add_cu: float, idx: int) -> tuple[float, float]:
    """One step of the pad over dd days: temperature lag, copper placed into cohort idx (t), irrigation contact 0..1.
    Returns (copper dissolved, t; the same with full irrigation, t). Updates the cohorts in place."""
    rmax, th0, ea, tau, _m0 = kin
    lc.heap_temp_c += (t_air - lc.heap_temp_c) * (1.0 - math.exp(-dd / tau))
    f = arrhenius(lc.heap_temp_c, ea)
    lc.k_factor = f
    cu_c, th_c, rc_c = lc.cu_c, lc.th_c, lc.rc_c
    while len(cu_c) <= idx:
        cu_c.append(0.0)
        th_c.append(0.0)
        rc_c.append(0.0)
    cu_c[idx] += add_cu
    inc, incn = f * dd * contact, f * dd
    leach = nom = 0.0
    full = abs(contact - 1.0) < EPS
    for i in range(len(cu_c)):
        cu = cu_c[i]
        th = th_c[i]
        if cu > 0.0:
            r1 = _rec(th + inc, th0)
            leach += cu * rmax * (r1 - rc_c[i])
            if not full:
                nom += cu * rmax * (_rec(th + incn, th0) - rc_c[i])
            rc_c[i] = r1
        th_c[i] = th + inc
    return leach, (leach if full else nom)


def _day_cu(d: datetime.date) -> float:
    """Contained copper placed on one day, t (the ore of the quarter spread evenly over its days)."""
    y, q = d.year, (d.month - 1) // 3 + 1
    ore_tph, grade, _kt = _ore_rate(y, q)
    return ore_tph * 24.0 * grade / 100.0


def trajectory(kin: tuple) -> dict:
    """The pad from 01.01.2018 to 30.06.2026 with the weekly step. {'weeks': [(date, cu, th, rc, heap_c)], 'q': {(y, q): dissolved t}}."""
    key = tuple(kin)
    tr = _TRAJ.get(key)
    if tr is not None:
        return tr
    end = datetime.date(2026, 7, 1)
    h = _Heap(kin, air_t_c(D0))
    weeks, qsum = [], {}
    d = D0
    while d < end:
        n = min(WEEK_D, (end - d).days)
        weeks.append((d, tuple(h.cu_c), tuple(h.th_c), tuple(h.rc_c), h.heap_temp_c))
        for k in range(n):
            dk = d + datetime.timedelta(days=k)
            i = cohort_index(dk)
            while len(h.cu_c) <= i:
                h.cu_c.append(0.0)
                h.th_c.append(0.0)
                h.rc_c.append(0.0)
            h.cu_c[i] += _day_cu(dk)
        mid = d + datetime.timedelta(days=n // 2)
        leach, _nom = heap_step(h, kin, float(n), air_t_c(mid), 1.0, 0.0, cohort_index(mid))
        qk = (mid.year, (mid.month - 1) // 3 + 1)
        qsum[qk] = qsum.get(qk, 0.0) + leach
        d += datetime.timedelta(days=n)
    tr = {"weeks": weeks, "q": qsum}
    if len(_TRAJ) > 6:
        _TRAJ.clear()
    _TRAJ[key] = tr
    return tr


# ---------------------------------------------------------------------------------------------------------------------
# Back-test and calibration
# ---------------------------------------------------------------------------------------------------------------------
def _is_fit(yq: tuple[int, int], last: tuple[int, int] = FIT_LAST_QUARTER) -> bool:
    return yq <= last


def model_quarters(kin: tuple) -> dict[tuple[int, int], float]:
    """Dissolved copper of each quarter, kt (the cathode follows it with a delay of hours)."""
    return {k: v / KT_TO_T for k, v in trajectory(kin)["q"].items()}


def _stats(pairs: list[tuple[float, float]]) -> dict:
    """pairs (report, model) -> mean absolute % error, rms % error, mean signed % error."""
    if not pairs:
        return {"n": 0}
    e = [100.0 * (m / r - 1.0) for r, m in pairs]
    n = len(e)
    return {"n": n, "mape_pct": sum(abs(x) for x in e) / n, "rmse_pct": math.sqrt(sum(x * x for x in e) / n), "bias_pct": sum(e) / n,
            "worst_pct": max(e, key=abs)}


def backtest(prm, last: tuple[int, int] = FIT_LAST_QUARTER) -> dict:
    """Quarterly back-test of the pad against the cathode of the reports, with two naive baselines."""
    kin = kinetics(prm)
    mq = model_quarters(kin)
    rep = {k: v[2] for k, v in quarters().items()}
    keys = sorted(rep)
    rows = []
    for k in keys:
        rows.append({"quarter": f"{k[0]}Q{k[1]}", "report_kt": rep[k], "model_kt": round(mq[k], 3),
                     "err_pct": round(100.0 * (mq[k] / rep[k] - 1.0), 1), "period": "fit" if _is_fit(k, last) else "forward",
                     "ore_kt": quarters()[k][0], "grade_pct": quarters()[k][1]})
    fit = [(rep[k], mq[k]) for k in keys if _is_fit(k, last)]
    fwd = [(rep[k], mq[k]) for k in keys if not _is_fit(k, last)]
    mean_fit = sum(r for r, _m in fit) / len(fit)
    const = [(rep[k], mean_fit) for k in keys if not _is_fit(k, last)]
    persist = [(rep[keys[i]], rep[keys[i - 1]]) for i in range(1, len(keys)) if not _is_fit(keys[i], last)]
    ann = {}
    for y in range(FIRST_YEAR, LAST_YEAR + 1):
        r = sum(rep[(y, q)] for q in (1, 2, 3, 4))
        m = sum(mq[(y, q)] for q in (1, 2, 3, 4))
        ann[str(y)] = {"report_kt": round(r, 1), "model_kt": round(m, 1), "err_pct": round(100.0 * (m / r - 1.0), 1)}
    xs = [rep[k] for k in keys]
    ys = [mq[k] for k in keys]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    r_all = sxy / math.sqrt(sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys))
    return {"rows": rows, "fit": _stats(fit), "forward": _stats(fwd), "baseline_constant_forward": _stats(const),
            "baseline_previous_quarter_forward": _stats(persist), "annual": ann, "r_all": round(r_all, 3),
            "kinetics": dict(zip(KIN_KEYS, kin))}


def _nelder_mead(f, x0: list[float], step: list[float], iters: int) -> tuple[list[float], float]:
    n = len(x0)
    pts = [list(x0)]
    for i in range(n):
        x = list(x0)
        x[i] += step[i]
        pts.append(x)
    vals = [f(p) for p in pts]
    for _ in range(iters):
        order = sorted(range(n + 1), key=lambda i: vals[i])
        pts = [pts[i] for i in order]
        vals = [vals[i] for i in order]
        c = [sum(p[j] for p in pts[:-1]) / n for j in range(n)]
        xr = [c[j] + (c[j] - pts[-1][j]) for j in range(n)]
        fr = f(xr)
        if fr < vals[0]:
            xe = [c[j] + 2.0 * (c[j] - pts[-1][j]) for j in range(n)]
            fe = f(xe)
            pts[-1], vals[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < vals[-2]:
            pts[-1], vals[-1] = xr, fr
        else:
            xc = [c[j] + 0.5 * (pts[-1][j] - c[j]) for j in range(n)]
            fc = f(xc)
            if fc < vals[-1]:
                pts[-1], vals[-1] = xc, fc
            else:
                for i in range(1, n + 1):
                    pts[i] = [pts[0][j] + 0.5 * (pts[i][j] - pts[0][j]) for j in range(n)]
                    vals[i] = f(pts[i])
    i = min(range(n + 1), key=lambda k: vals[k])
    return pts[i], vals[i]


def calibrate(prm, iters: int = 300, last: tuple[int, int] = FIT_LAST_QUARTER) -> dict:
    """Fit rmax, theta, Ea and the copper placed before 2018 on the quarters up to `last` (default FIT_LAST_QUARTER; relative
    least squares, Nelder-Mead from the table values, deterministic). The bounds are the min..max of the table rows."""
    from .params import TABLE
    names = ("ox_rmax", "ox_th_d", "ox_ea_app_jmol", "ox_m0_t")
    kin0 = kinetics(prm)
    rep = {k: v[2] for k, v in quarters().items() if _is_fit(k, last)}

    def unpack(x):
        return [x[0], math.exp(x[1]), x[2], kin0[3], math.exp(x[3])]

    def obj(x):
        v = unpack(x)
        pen = 0.0
        for val, nm in zip((v[0], v[1], v[2], v[4]), names):
            lo, hi = TABLE[nm].min, TABLE[nm].max
            if val < lo or val > hi:
                pen += 1.0 + abs(val - min(max(val, lo), hi)) / max(abs(hi), 1.0)
        if pen:
            return 3.0 + pen
        mq = model_quarters(tuple(v))
        return math.sqrt(sum((mq[k] / rep[k] - 1.0) ** 2 for k in rep) / len(rep))

    x0 = [kin0[0], math.log(kin0[1]), kin0[2], math.log(kin0[4])]
    x, fun = _nelder_mead(obj, x0, [0.05, 0.3, 1500.0, 0.3], iters)
    _TRAJ.clear()
    v = unpack(x)
    return {"values": dict(zip(names, (v[0], v[1], v[2], v[4]))), "rel_rmse_fit": fun, "iters": iters}


# ---------------------------------------------------------------------------------------------------------------------
# Troubles of the chain (scenarios ewtrip and sxcrud): items in st.oxf, never drawn in free run
# ---------------------------------------------------------------------------------------------------------------------
FAULT_KINDS = ("ewtrip", "sxcrud")
FAULT_NODE = {"ewtrip": "ew-1", "sxcrud": "sx-1"}


def fault_start(st, kind: str, t0: float, fix_h: float | None = None) -> None:
    st.oxf[kind] = {"t0": float(t0), "fix": -1.0, "fix_h": float(fix_h) if fix_h else -1.0}


def fault_call(plant, kind: str, t: float) -> bool:
    """The person is called: the fault is cleared after the arrival and the work."""
    from . import events as ev
    item = plant.state.oxf.get(kind)
    if item is None:
        return False
    prm = plant.prm
    work = item["fix_h"] if item["fix_h"] > 0.0 else prm["ox_rect_fix_h" if kind == "ewtrip" else "ox_crud_fix_h"]
    when = t + ev.arrival_min(plant.state.seed, kind, prm) + work * MIN_PER_H
    if item["fix"] < 0.0 or when < item["fix"]:
        item["fix"] = when
    return True


def fault_clear(st) -> None:
    st.oxf.clear()


def fault_issue_at(st, node: str) -> str | None:
    for kind in st.oxf:
        if FAULT_NODE[kind] == node:
            return kind
    return None


def faults_now(st, prm, t: float) -> tuple[bool, float]:
    """(rectifier tripped, crud layer cm) at model minute t; finished items are dropped."""
    trip, crud = False, prm["ox_crud_ok_cm"]
    for kind, item in list(st.oxf.items()):
        if kind == "ewtrip":
            end = item["fix"] if item["fix"] >= 0.0 else item["t0"] + prm["ox_rect_auto_h"] * MIN_PER_H
            if t >= end - EPS:
                del st.oxf[kind]
            elif t >= item["t0"] - EPS:
                trip = True
        elif kind == "sxcrud":
            if item["fix"] >= 0.0 and t >= item["fix"] - EPS:
                del st.oxf[kind]
                continue
            h = max(0.0, (t - item["t0"]) / MIN_PER_H)
            ok, al, cr = prm["ox_crud_ok_cm"], prm["ox_crud_alert_cm"], prm["ox_crud_crit_cm"]
            if h <= prm["ox_crud_rise_h"]:
                crud = ok + (al - ok) * h / prm["ox_crud_rise_h"]
            else:
                crud = al + (cr - al) * min(1.0, (h - prm["ox_crud_rise_h"]) / prm["ox_crud_fail_h"])
    return trip, crud


# ---------------------------------------------------------------------------------------------------------------------
# The chain in the plant
# ---------------------------------------------------------------------------------------------------------------------
def _ew_consts(prm) -> tuple[float, float, float, float]:
    """(t of copper per A at 100 % efficiency x cells x efficiency, design current A, current limit A, copper of the electrolyte at the set point t)."""
    kf = prm["ox_ew_gpah"] * 1e-6
    k = kf * prm["ox_ew_cells"] * prm["ox_ew_ce"]            # t/h per A
    i_nom = prm["ox_ew_design_kty"] * KT_TO_T / HOURS_YEAR / k
    return k, i_nom, i_nom * prm["ox_ew_overload"], prm["ox_ew_el_m3"] * prm["ox_ew_el_gl"] / KT_TO_T


def design_current_ka(prm) -> float:
    return _ew_consts(prm)[1] / KT_TO_T


def design_density_am2(prm) -> float:
    """Current density on the cathode faces at the design current, A/m2."""
    return _ew_consts(prm)[1] / (prm["ox_ew_cath_n"] * 2.0 * prm["ox_ew_cath_m2"])


def _inventory(lc, rmax: float) -> None:
    """Leachable copper left in the pad and the share dissolved of everything placed (cohorts)."""
    left = sum(c * rmax * (1.0 - r) for c, r in zip(lc.cu_c, lc.rc_c))
    placed = sum(lc.cu_c) * rmax
    lc.inventory_cu_t = left
    lc.recovery_pct = 100.0 * (1.0 - left / placed) if placed > 0.0 else 0.0


def _init_chain(st, prm, date: datetime.date, key: tuple) -> None:
    """Pad cohorts at the date from the spin-up of the quarters; the chain in a steady state."""
    kin = kinetics(prm)
    lc = st.leach
    tr = trajectory(kin)
    days = (date - D0).days
    w = min(max(days // WEEK_D, 0), len(tr["weeks"]) - 1)
    d, cu, th, rc, hc = tr["weeks"][w]
    h = _Heap(kin, hc)
    h.cu_c, h.th_c, h.rc_c = list(cu), list(th), list(rc)
    rem = (date - d).days
    for k in range(rem):
        dk = d + datetime.timedelta(days=k)
        i = cohort_index(dk)
        while len(h.cu_c) <= i:
            h.cu_c.append(0.0)
            h.th_c.append(0.0)
            h.rc_c.append(0.0)
        h.cu_c[i] += _day_cu(dk)
    if rem:
        heap_step(h, kin, float(rem), air_t_c(d + datetime.timedelta(days=rem // 2)), 1.0, 0.0, cohort_index(date))
    lc.cu_c, lc.th_c, lc.rc_c, lc.heap_temp_c = h.cu_c, h.th_c, h.rc_c, h.heap_temp_c
    lc.placed_cu_t = sum(h.cu_c)
    # rate now: a probe of one hour on a copy
    probe = _Heap(kin, h.heap_temp_c)
    probe.cu_c, probe.th_c, probe.rc_c = list(h.cu_c), list(h.th_c), list(h.rc_c)
    leach, _nom = heap_step(probe, kin, 1.0 / 24.0, air_t_c(date), 1.0, 0.0, cohort_index(date))
    l0 = leach                                                       # t in one hour
    lc.k_factor = probe.k_factor
    q_irr, eta, tau = prm["ox_irr_m3h"], prm["ox_sx_eta"], prm["ox_pad_tau_h"]
    k, i_nom, i_max, e_t = _ew_consts(prm)
    gls = l0 * KT_TO_T / (eta * q_irr) if q_irr > 0.0 else 0.0
    lc.leach_cu_tph = lc.leach_exp_tph = l0
    lc.hold_cu_t = (l0 / eta) * tau
    lc.pls_gl = gls
    lc.acc_min = lc.acc_leach_t = lc.acc_contact = 0.0
    lc.init_key = key
    lc.ready = True
    _inventory(lc, kin[0])
    lc.heap_temp_c = h.heap_temp_c
    pl = st.pls
    pl.volume_m3 = prm["ox_pls_v_m3"]
    pl.cu_t = gls * pl.volume_m3 / KT_TO_T
    pl.pls_gl = gls
    pl.raff_gl = (1.0 - eta) * gls
    st.sx.raff_cu_gl = pl.raff_gl
    st.ew.electrolyte_cu_t = e_t
    st.ew.cathode_tph = min(l0, i_max * k)
    st.catstore.stock_t = prm["ox_store_t0"]


def oxide_step(st, cold: bool, dt_min: float, prm, ox_date=None, rect_trip: bool = False, crud_cm: float | None = None) -> None:
    """The chain for one step. ox_date = (year, doy0) or None for the model clock."""
    ck = st.clock
    if ox_date is None:
        year, doy0 = ck.year, ck.origin_doy + ck.t_min / MIN_PER_DAY
    else:
        year, doy0 = ox_date
    y, q = quarter_of(year, doy0)
    date = date_of(year, doy0)
    lc, pl, sx, ew, cs, of, sxew = st.leach, st.pls, st.sx, st.ew, st.catstore, st.oxfeed, st.sxew
    okey = (int(ox_date[0]), int(ox_date[1])) if ox_date is not None else ()
    if not lc.ready or (okey != lc.init_key and ck.t_min - lc.init_min < MIN_PER_DAY):
        _init_chain(st, prm, date, okey)
        lc.init_min = ck.t_min
    kin = kinetics(prm)
    dt_h = dt_min / MIN_PER_H
    if crud_cm is None:
        crud_cm = prm["ox_crud_ok_cm"]
    # ---- ore to the heap
    ore_tph, grade, ore_kt = _ore_rate(y, q)
    cu_tph = ore_tph * grade / 100.0
    of.state = "IDLE" if ore_tph < prm["ox_idle_ore_tph"] else "NORMAL"
    of.ore_tph, of.grade_pct, of.cu_tph, of.quarter_ore_kt = ore_tph, grade, cu_tph, ore_kt
    of.placed_t_total += ore_tph * dt_h
    # ---- irrigation: the cold spell freezes the lines; a spilling PLS pond cuts the irrigation to the SX flow
    q_nom = prm["ox_irr_m3h"]
    frac = prm["ox_cold_frac"] if cold else 0.0
    contact = 1.0 - frac
    if pl.volume_m3 >= prm["ox_pls_vmax_m3"] * 0.999:
        contact = min(contact, max(0.0, sx.feed_m3h) / q_nom) if q_nom > 0.0 else 0.0
    irr = q_nom * contact
    lc.state, lc.cold_frac = ("COLD" if cold else "NORMAL"), frac
    lc.quarter_cathode_kt = cathode_by_quarter()[(y, q)]
    lc.level_tph = level_tph(y, q)
    lc.irrigation_m3h, lc.irrigation_pct = irr, 100.0 * contact
    # ---- the pad: cohorts once an hour
    lc.acc_min += dt_min
    lc.acc_contact += contact * dt_min
    lc.placed_cu_t += cu_tph * dt_h
    if lc.acc_min >= HEAP_UPDATE_MIN - EPS:
        span_h = lc.acc_min / MIN_PER_H
        leach_t, nom_t = heap_step(lc, kin, lc.acc_min / MIN_PER_DAY, air_t_c(date), lc.acc_contact / lc.acc_min,
                                   cu_tph * span_h, cohort_index(date))
        lc.leach_cu_tph, lc.leach_exp_tph = leach_t / span_h, nom_t / span_h
        lc.acc_min = lc.acc_contact = 0.0
        _inventory(lc, kin[0])
    l_now = lc.leach_cu_tph
    # ---- pad drain to the PLS pond (exponential step, the drain follows the irrigation)
    tau = prm["ox_pad_tau_h"]
    src = l_now + irr * pl.raff_gl / KT_TO_T
    rate = contact / tau
    if rate > 1e-9:
        a = math.exp(-rate * dt_h)
        h_ss = src / rate
        lc.hold_cu_t = h_ss + (lc.hold_cu_t - h_ss) * a
    else:
        lc.hold_cu_t += src * dt_h
    cu_out = lc.hold_cu_t * rate
    lc.pls_gl = cu_out * KT_TO_T / irr if irr > 1e-9 else 0.0
    # ---- PLS pond and the SX feed
    vp, vmax = pl.volume_m3, prm["ox_pls_vmax_m3"]
    g_pond = pl.cu_t / vp * KT_TO_T if vp > 1e-9 else 0.0
    crud_ramp = min(1.0, max(0.0, (crud_cm - prm["ox_crud_ok_cm"]) / (prm["ox_crud_crit_cm"] - prm["ox_crud_ok_cm"])))
    q_cap = q_nom * prm["ox_sx_q_cap"] * (1.0 - (1.0 - prm["ox_crud_q_frac"]) * crud_ramp)
    q_sx = min(max(q_nom + (vp - prm["ox_pls_v_m3"]) / prm["ox_pond_tau_h"], 0.0), q_cap)
    vp = min(max(vp + (irr - q_sx) * dt_h, 0.0), vmax)
    cu_sx = q_sx * g_pond / KT_TO_T
    pl.cu_t = max(0.0, pl.cu_t + (cu_out - cu_sx) * dt_h)
    pl.volume_m3, pl.level_pct = vp, 100.0 * vp / vmax
    pl.in_m3h, pl.out_m3h, pl.pls_gl = irr, q_sx, g_pond
    pl.state = "FULL" if vp >= 0.98 * vmax else "HIGH" if vp >= 0.85 * vmax else "LOW" if vp <= 0.2 * vmax else "NORMAL"
    net = irr - q_sx
    pl.hours_to_full = (vmax - vp) / net if net > 1e-6 and vp < vmax else -1.0
    # ---- SX: extraction, strip limit by the electrolyte
    k, i_nom, i_max, e_t = _ew_consts(prm)
    e_max = prm["ox_ew_emax_frac"] * e_t
    e_hi = e_t + 0.5 * (e_max - e_t)
    strip = min(1.0, max(0.0, (e_max - ew.electrolyte_cu_t) / (e_max - e_hi)))
    eta = prm["ox_sx_eta"] * (1.0 - (1.0 - prm["ox_crud_eta_frac"]) * crud_ramp)
    transfer = eta * cu_sx * strip
    raff_flow = cu_sx - transfer
    vr = prm["ox_raff_v_m3"]
    if irr > 1e-9:
        gss = raff_flow * KT_TO_T / irr
        pl.raff_gl = gss + (pl.raff_gl - gss) * math.exp(-irr / vr * dt_h)
    else:
        pl.raff_gl += raff_flow * KT_TO_T * dt_h / vr
    sx.feed_m3h, sx.crud_cm = q_sx, crud_cm
    sx.extraction_pct = 100.0 * transfer / cu_sx if cu_sx > 1e-9 else 100.0 * eta * strip
    sx.transfer_cu_tph, sx.raff_cu_gl = transfer, pl.raff_gl
    sx.state = "CRUD" if crud_cm >= prm["ox_crud_alert_cm"] else "NORMAL"
    # ---- EW: Faraday
    want = (transfer + (ew.electrolyte_cu_t - e_t) / prm["ox_ew_tau_h"]) / k
    i_set = min(max(want, 0.0), i_max)
    i_a = 0.0 if rect_trip else i_set
    dep = k * i_a
    ew.electrolyte_cu_t += (transfer - dep) * dt_h
    if ew.electrolyte_cu_t < 0.0:
        dep = max(0.0, dep + ew.electrolyte_cu_t / dt_h)
        i_a = dep / k
        ew.electrolyte_cu_t = 0.0
    ew.state = "TRIP" if rect_trip else "LIMIT" if i_set >= i_max * 0.999 else "NORMAL"
    ew.current_ka, ew.current_set_ka = i_a / KT_TO_T, i_set / KT_TO_T
    ew.voltage_v = prm["ox_ew_v_cell"] if i_a > 0.0 else 0.0
    ew.current_density_am2 = i_a / (prm["ox_ew_cath_n"] * 2.0 * prm["ox_ew_cath_m2"])
    ew.cathode_tph = dep
    ew.cathode_exp_tph = min(lc.leach_exp_tph, i_max * k)
    ew.power_mw = i_a * prm["ox_ew_cells"] * ew.voltage_v / 1e6
    ew.kwh_t = prm["ox_ew_v_cell"] * KT_TO_T / (prm["ox_ew_gpah"] * prm["ox_ew_ce"])
    # ---- cathode store and shipping
    cs.in_tph = dep
    cs.stock_t += dep * dt_h
    batch = prm["ox_ship_batch_t"]
    while cs.stock_t >= batch:
        cs.stock_t -= batch
        cs.shipped_t_total += batch
        cs.shipments_n += 1.0
    cap = prm["ox_store_cap_t"]
    cs.state = "FULL" if cs.stock_t >= cap else "HIGH" if cs.stock_t >= prm["ox_store_high_frac"] * cap else "NORMAL"
    cs.hours_to_full = (cap - cs.stock_t) / dep if dep > 1e-9 else -1.0
    # ---- summary against the reports
    sxew.state = "LOW" if dep < ew.cathode_exp_tph * (1.0 - prm["ox_low_frac"]) else "NORMAL"
    sxew.cathode_level_tph, sxew.cathode_tph = lc.level_tph, dep
    sxew.cathode_t_total += dep * dt_h
    sxew.year, sxew.quarter = float(y), float(q)
    sxew.model_dev_pct = 100.0 * (ew.cathode_exp_tph / lc.level_tph - 1.0) if lc.level_tph > 0.0 else 0.0


def main(argv: list[str]) -> int:
    """python -I aktogay/run.py oxide [--backtest] [--calibrate] [--write PATH]"""
    from .params import default
    prm = default()
    if "--calibrate" in argv:
        last = STRICT_LAST_QUARTER if "--strict" in argv else FIT_LAST_QUARTER
        res = calibrate(prm, iters=int(argv[argv.index("--iters") + 1]) if "--iters" in argv else 400, last=last)
        print(json.dumps(res, indent=1))
        return 0
    bt = backtest(prm)
    strict_prm = default()
    sc = calibrate(strict_prm, iters=400, last=STRICT_LAST_QUARTER)
    for k, v in sc["values"].items():
        strict_prm.set(k, v)
    bt["strict"] = backtest(strict_prm, last=STRICT_LAST_QUARTER)
    bt["strict"]["values"] = sc["values"]
    bt["about"] = ("Back-test of the oxide pad against the cathode of the KAZ Minerals reports: model = copper dissolved in the pad in the quarter "
                   "(weekly step, same code as the stand); main: fit 2018Q1-2025Q4, forward test 2026Q1-2026Q2; strict: fit 2018Q1-2024Q4, "
                   "forward 2025Q1-2026Q2; baselines for the forward quarters: the mean of the fit quarters and the previous quarter")
    text = json.dumps(bt, ensure_ascii=False, indent=1) + "\n"
    if "--write" in argv:
        with open(argv[argv.index("--write") + 1], "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    else:
        print(text)
    return 0
