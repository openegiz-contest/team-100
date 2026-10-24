"""Flotation (rougher/scavenger and cleaner), thickener, filter, concentrate stock.

Design: section 3 rows 12, 12a, 12b, 18, 19, 20; section 4 rows
"flotation: rougher", "flotation: cleaner and section", "thickener and
filter", "concentrate stock", "noise and delays" (flotation lag); section 7
("Two at once": dose drift; C2: one ball mill).

Rules for this file: numbers only from prm; noise arrives as z ~ N(0, 1);
randomness only from state.u01; unit functions mutate only the states passed in.
Water is taken at 1 t/m3, so t/h of water = m3/h.

Reference values (Q 3853 t/h, 0.41 % Cu, ASCu 5 %, P80 <= 180 um, full dose):
  rougher 89.9 %, cleaner 97 %, total 87.2 %, concentrate 24.3 % Cu,
  tails 0.053 % Cu, concentrate 56.7 t/h per line.
  Dose 40 % short: total 83.7 %, tails 0.068 %, Cu loss 0.55 t/h.
  One ball mill, 2650 t/h, P80 279 um: total about 86.5 %.
  Hard ore at 2960 t/h, P80 134 um: total about 89.0 % (+1.8 pp).
  Feed grade: total R moves by 4.093 pp per ln(g / g0) (Josemaria, total
  recovery); 0.43 % Cu: 87.4 %; tails follow the feed grade (0.046 % Cu at
  0.33, 0.061 % at 0.50). The concentrate grade line uses R without that
  feed-grade gain, so rich ore keeps 24.3 % Cu. ASCu: total R -1.043 pp per pp.
  Dose drift on rich ore (0.50 %): tails about 0.079 %, above the 0.075 %
  alarm (design section 4 allows it on rich ore).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .params import ParamSet
from .state import (MIN_PER_DAY, MIN_PER_H, NO_VALUE, CleanerState, ConcStockState, FilterState,
                    FlotState, OreProps, RougherState, ThickenerState, u01)


@dataclass
class FlotResult:
    r_inf_pct: float          # rougher ultimate recovery, %
    rougher_rec_pct: float    # rougher stage recovery, %
    cleaner_rec_pct: float    # cleaner stage recovery, %
    total_rec_pct: float      # %
    mass_pull_pct: float      # rougher mass pull, % of feed
    rconc_cu_pct: float       # rougher concentrate grade, % Cu
    conc_cu_pct: float        # final concentrate grade, % Cu
    tail_cu_pct: float        # combined tails, % Cu
    conc_tph: float           # concentrate solids, t/h
    cu_tph: float             # Cu in concentrate, t/h
    residence_min: float      # rougher residence, min


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _no_flow_result() -> FlotResult:
    """Result of a section with no feed: zero flows, no grades or recoveries."""
    return FlotResult(NO_VALUE, NO_VALUE, NO_VALUE, NO_VALUE, NO_VALUE, NO_VALUE, NO_VALUE,
                      NO_VALUE, 0.0, 0.0, NO_VALUE)


# ---------------------------------------------------------------------------
# Pure formulas
# ---------------------------------------------------------------------------
def residence_min(q_tph: float, prm: ParamSet) -> float:
    """Rougher residence time, min: tau = flot_tau0_min * cal_line_tph / Q (NO_VALUE for Q <= 0).

    Fixed cell volume, so residence is inversely proportional to the solids rate Q (t/h).
    """
    if q_tph <= 0.0:
        return NO_VALUE
    return prm["flot_tau0_min"] * prm["cal_line_tph"] / q_tph


def _base_stage_share(prm: ParamSet) -> float:
    """k_base * c_base: share of an R_inf change that reaches total R at base residence and pull."""
    return (1.0 - math.exp(-prm["flot_ktau0"])) * prm["clean_r0_pct"] / 100.0


def dose_penalty_pp(dose_ratio: float, prm: ParamSet) -> float:
    """Collector under-dose loss on R_inf, pp (0 at full dose or above).

    Linear in the deficit (1 - true / setpoint); scaled by the base rougher
    kinetics and cleaner recovery so that the total recovery falls by
    flot_dose_pp at a deficit of flot_dose_ref_deficit.
    """
    deficit = _clamp(1.0 - dose_ratio, 0.0, 1.0)
    return prm["flot_dose_pp"] / _base_stage_share(prm) * deficit / prm["flot_dose_ref_deficit"]


def grade_gain_pp(feed_cu: float, prm: ParamSet) -> float:
    """Feed-grade term on R_inf, pp: flot_grade_pp_ln / (k_base c_base) * ln(g / flot_grade_ref_pct).

    Scaled so that total R moves by flot_grade_pp_ln per unit of ln(g / g0)
    at base residence and pull (Josemaria 4.093 is a total-recovery slope).
    0.41 -> 0.43 % Cu: about +0.2 pp on total R. feed_cu must be positive.
    """
    return prm["flot_grade_pp_ln"] / _base_stage_share(prm) * math.log(feed_cu / prm["flot_grade_ref_pct"])


def grade_gain_total_pp(feed_cu: float, prm: ParamSet) -> float:
    """Feed-grade part of the total recovery at base residence and pull, pp:
    flot_grade_pp_ln * ln(g / flot_grade_ref_pct) (0 for g <= 0)."""
    if feed_cu <= 0.0:
        return 0.0
    return prm["flot_grade_pp_ln"] * math.log(feed_cu / prm["flot_grade_ref_pct"])


def r_inf_pct(feed_cu: float, ascu_pct: float, p80_um: float, dose_ratio: float,
              prm: ParamSet, loss_pp: float = 0.0) -> float:
    """Rougher ultimate recovery R_inf, %.

    feed_cu % Cu, ascu_pct % of total Cu, p80_um flotation feed P80 (um),
    dose_ratio true / setpoint collector dose (-).
    R_inf = flot_rinf0_pct + flot_grade_pp_ln / (k_base * c_base) * ln(g / flot_grade_ref_pct)
            - flot_jose_ascu / (k_base * c_base) * (ASCu - flot_ascu_ref_pct)
            - flot_p80_pp_10um * max(0, P80 - flot_p80_ref_um) / 10
            - flot_dose_pp / (k_base * c_base) * max(0, 1 - dose_ratio) / flot_dose_ref_deficit,
    k_base = 1 - exp(-flot_ktau0), c_base = clean_r0_pct / 100, so that at
    base residence and pull the total recovery moves by flot_grade_pp_ln per
    ln of grade and by -flot_jose_ascu per pp of ASCu (both Josemaria slopes
    are on total recovery), and falls by flot_dose_pp (3.5 pp, 0.55 t Cu/h)
    at 40 % under-dose.
    Clamped to [0, 100]; 0 for feed_cu <= 0. Unknown P80 (NO_VALUE) gives no grind loss.
    """
    if feed_cu <= 0.0:
        return 0.0
    r = prm["flot_rinf0_pct"]
    r += grade_gain_pp(feed_cu, prm)
    r -= prm["flot_jose_ascu"] / _base_stage_share(prm) * (ascu_pct - prm["flot_ascu_ref_pct"])
    r -= prm["flot_p80_pp_10um"] * max(0.0, p80_um - prm["flot_p80_ref_um"]) / 10.0
    r -= dose_penalty_pp(dose_ratio, prm)
    r -= loss_pp / _base_stage_share(prm)     # extra recovery loss on total recovery: pH above setpoint, a rougher line stopped
    return _clamp(r, 0.0, 100.0)


def rougher_recovery_pct(r_inf: float, tau_min: float, prm: ParamSet) -> float:
    """First-order kinetics, %: R = R_inf (1 - exp(-k tau)), k = flot_ktau0 / flot_tau0_min (1/min).

    0 for tau <= 0 (no residence).
    """
    if tau_min <= 0.0 or r_inf <= 0.0:
        return 0.0
    k = prm["flot_ktau0"] / prm["flot_tau0_min"]
    return r_inf * (1.0 - math.exp(-k * tau_min))


def mass_pull_pct(feed_cu: float, prm: ParamSet) -> float:
    """Rougher mass pull, % of feed: flot_pull0_pct * g / flot_grade_ref_pct (0 for g <= 0)."""
    if feed_cu <= 0.0:
        return 0.0
    return prm["flot_pull0_pct"] * feed_cu / prm["flot_grade_ref_pct"]


def cleaner_recovery_pct(pull_pct: float, prm: ParamSet) -> float:
    """Cleaner stage recovery, %.

    clean_r0_pct - clean_pp_10pp * max(0, pull - flot_pull0_pct) / 10 (pull in % of feed,
    so 1 pp per 10 pp of extra pull). Grade 0.43 % gives pull 7.34 % and -0.03 pp.
    Clamped to [0, 100].
    """
    extra = max(0.0, pull_pct - prm["flot_pull0_pct"])
    return _clamp(prm["clean_r0_pct"] - prm["clean_pp_10pp"] * extra / 10.0, 0.0, 100.0)


def conc_grade_pct(total_rec_pct: float, prm: ParamSet, feed_cu: float | None = None) -> float:
    """Concentrate grade, % Cu: flot_conc0_pct - flot_conc_slope * (R - flot_rec_ref_pct - G).

    Grade-recovery line: it trades grade for recovery gained by pull, residence,
    grind or dose; G = grade_gain_total_pp(feed_cu), the recovery a richer feed
    gives by itself, is not traded (G = 0 when feed_cu is None).
    Capped at flot_conc_max_pct (pure chalcopyrite).
    """
    gain = grade_gain_total_pp(feed_cu, prm) if feed_cu is not None else 0.0
    g = prm["flot_conc0_pct"] - prm["flot_conc_slope"] * (total_rec_pct - prm["flot_rec_ref_pct"] - gain)
    return min(g, prm["flot_conc_max_pct"])


def tails_cu_pct(feed_cu: float, total_rec_pct: float, conc_cu: float) -> float:
    """Two-product tails grade, % Cu: g (1 - R) / (1 - y), y = g R / grade.

    Grades in % Cu, R in %. y is the concentrate mass yield (share of feed).
    NO_VALUE when the concentrate grade is not positive or y >= 1.
    """
    if feed_cu <= 0.0:
        return 0.0
    if conc_cu <= 0.0:
        return NO_VALUE
    r = total_rec_pct / 100.0
    y = feed_cu * r / conc_cu
    if y >= 1.0:
        return NO_VALUE
    return feed_cu * (1.0 - r) / (1.0 - y)


def flotation_steady(q_tph: float, ore: OreProps, p80_um: float, dose_ratio: float,
                     prm: ParamSet, loss_pp: float = 0.0) -> FlotResult:
    """Instant (no lag) flotation result for one line.

    q_tph fresh feed, t/h; ore true feed properties; p80_um flotation feed
    P80, um; dose_ratio true / setpoint collector dose, -.
    Chain: residence -> r_inf -> rougher -> pull -> cleaner -> total = R_r R_c
    -> grade -> tails. conc_tph = Q g R / grade; cu_tph = Q g R / 1e4.
    Concentrate grade is not below the feed grade (no negative upgrading).
    Q <= 0 returns zeros for flows and NO_VALUE for grades and recoveries.
    """
    if q_tph <= 0.0:
        return _no_flow_result()
    g = ore.cu_pct
    tau = residence_min(q_tph, prm)
    rinf = r_inf_pct(g, ore.ascu_pct, p80_um, dose_ratio, prm, loss_pp)
    r_r = rougher_recovery_pct(rinf, tau, prm)
    pull = mass_pull_pct(g, prm)
    r_c = cleaner_recovery_pct(pull, prm)
    total = r_r * r_c / 100.0
    grade = max(conc_grade_pct(total, prm, g), g)
    rconc = g * r_r / pull if pull > 0.0 else NO_VALUE
    cu_tph = q_tph * g * total / 1e4
    conc_tph = cu_tph * 100.0 / grade if grade > 0.0 else 0.0
    return FlotResult(r_inf_pct=rinf, rougher_rec_pct=r_r, cleaner_rec_pct=r_c, total_rec_pct=total,
                      mass_pull_pct=pull, rconc_cu_pct=rconc, conc_cu_pct=grade,
                      tail_cu_pct=tails_cu_pct(g, total, grade), conc_tph=conc_tph, cu_tph=cu_tph,
                      residence_min=tau)


# ---------------------------------------------------------------------------
# Unit steps
# ---------------------------------------------------------------------------
def _delay_lag(fl: FlotState, rec_now: float, grade_now: float, t_min: float, dt_min: float,
               prm: ParamSet) -> None:
    """Pass (R, grade) through transport delay and first-order lag; updates fl in place.

    fl.history holds (t_min, R, grade) samples, each held until the next
    sample (piecewise constant). The lag is integrated exactly over the
    delayed input window [t - delay, t + dt - delay], so any step dt gives
    the same response. An empty history starts from the lag state (the
    plant was steady before the first step).
    """
    delay = prm["flot_delay_min"]
    tau = prm["flot_tau_min"]
    h = fl.history
    while h and h[-1][0] >= t_min:
        h.pop()                               # re-stepped time: the new sample wins
    if not h:
        if fl.grade_lag <= 0.0:               # never run: start at steady state
            fl.rec_lag, fl.grade_lag = rec_now, grade_now
        h.append((t_min - delay - dt_min, fl.rec_lag, fl.grade_lag))
    h.append((t_min, rec_now, grade_now))
    a = t_min - delay
    b = a + dt_min
    x_r, x_g = fl.rec_lag, fl.grade_lag
    n = len(h)
    for i in range(n):
        s = a if i == 0 else max(h[i][0], a)
        e = h[i + 1][0] if i + 1 < n else b
        e = min(e, b)
        if e <= s:
            continue
        f = math.exp(-(e - s) / tau) if tau > 0.0 else 0.0
        x_r = h[i][1] + (x_r - h[i][1]) * f
        x_g = h[i][2] + (x_g - h[i][2]) * f
    fl.rec_lag, fl.grade_lag = x_r, x_g
    keep = 0
    for i in range(n):                        # drop samples the next window will not reach
        if h[i][0] <= b:
            keep = i
        else:
            break
    if keep:
        del h[:keep]


def flotation_step(fl: FlotState, rough: RougherState, clean: CleanerState, q_tph: float,
                   ore: OreProps, p80_um: float, dose_ratio: float, dose_meas_gt: float,
                   t_min: float, dt_min: float, prm: ParamSet, conc_drop_pp: float = 0.0,
                   rec_loss_pp: float = 0.0) -> FlotResult:
    """Advance flotation of one line; returns the lagged result used for accounting.

    q_tph t/h; ore true feed; p80_um um; dose_ratio true / setpoint dose;
    dose_meas_gt flowmeter reading, g/t; t_min model minute at step start;
    dt_min step, min.
    Steady result from flotation_steady(); total recovery and concentrate
    grade pass a transport delay flot_delay_min (fl.history) and a
    first-order lag flot_tau_min (fl.rec_lag, fl.grade_lag). Mass flows use
    current Q and feed grade with the lagged recovery and grade (Cu in =
    Cu in concentrate + Cu in tails, no hold-up term); tails from
    tails_cu_pct with lagged values.
    Fills rougher (feed_tph, stage_recovery, mass_pull_pct, rconc_cu,
    residence_min, dose_sp_gt, dose_meas_gt, dose_true_gt = sp * dose_ratio),
    cleaner (feed_tph, stage_recovery, conc_cu, conc_tph, tail_cu) and the
    section fl (feed_cu, tail_cu, conc_cu, recovery, cu_tph, conc_tph).
    The lagged total is split as rougher = total / cleaner stage, so the
    published stage recoveries multiply to the section recovery.
    States (section, rougher, cleaner): STOP when Q = 0; UPSET when
    tail_cu > acs_tail_sp_pct; else RUN.
    Q = 0: flows 0, grades and recoveries NO_VALUE, delay and lag hold
    (cells stand full; the froth restarts from the held values).
    """
    sp = prm["flot_dose_sp_gt"]
    rough.dose_sp_gt = sp
    rough.dose_meas_gt = dose_meas_gt
    rough.dose_true_gt = sp * max(0.0, dose_ratio)
    if q_tph <= 0.0:
        res = _no_flow_result()
        for unit in (fl, rough, clean):
            unit.state = "STOP"
        rough.feed_tph = 0.0
        rough.stage_recovery = rough.mass_pull_pct = rough.rconc_cu = rough.residence_min = NO_VALUE
        clean.feed_tph = clean.conc_tph = 0.0
        clean.stage_recovery = clean.conc_cu = clean.tail_cu = NO_VALUE
        fl.feed_cu = fl.tail_cu = fl.conc_cu = fl.recovery = NO_VALUE
        fl.cu_tph = fl.conc_tph = 0.0
        return res

    ss = flotation_steady(q_tph, ore, p80_um, dose_ratio, prm, rec_loss_pp)
    _delay_lag(fl, ss.total_rec_pct, ss.conc_cu_pct, t_min, dt_min, prm)
    g = ore.cu_pct
    rec = fl.rec_lag
    grade = fl.grade_lag
    if conc_drop_pp > 0.0:
        grade = max(grade - conc_drop_pp, g)        # dilution of the cleaner froth: same copper, more mass
    cu_tph = q_tph * g * rec / 1e4
    conc_tph = cu_tph * 100.0 / grade if grade > 0.0 else 0.0
    tail = tails_cu_pct(g, rec, grade)
    r_c = ss.cleaner_rec_pct
    r_r = min(100.0, 100.0 * rec / r_c) if r_c > 0.0 else NO_VALUE
    pull = ss.mass_pull_pct
    rconc = g * r_r / pull if pull > 0.0 and r_r >= 0.0 else NO_VALUE

    # cleaner tails: rougher concentrate minus final concentrate
    clean_feed = q_tph * pull / 100.0
    cu_rconc = q_tph * g / 100.0 * max(r_r, 0.0) / 100.0
    clean_tail = (100.0 * (cu_rconc - cu_tph) / (clean_feed - conc_tph)
                  if clean_feed > conc_tph else NO_VALUE)

    state = "UPSET" if tail > prm["acs_tail_sp_pct"] else "RUN"
    for unit in (fl, rough, clean):
        unit.state = state
    rough.feed_tph = q_tph
    rough.stage_recovery = r_r
    rough.mass_pull_pct = pull
    rough.rconc_cu = rconc
    rough.residence_min = ss.residence_min
    clean.feed_tph = clean_feed
    clean.stage_recovery = r_c
    clean.conc_cu = grade
    clean.conc_tph = conc_tph
    clean.tail_cu = clean_tail
    fl.feed_cu = g
    fl.tail_cu = tail
    fl.conc_cu = grade
    fl.recovery = rec
    fl.cu_tph = cu_tph
    fl.conc_tph = conc_tph
    return FlotResult(r_inf_pct=ss.r_inf_pct, rougher_rec_pct=r_r, cleaner_rec_pct=r_c,
                      total_rec_pct=rec, mass_pull_pct=pull, rconc_cu_pct=rconc, conc_cu_pct=grade,
                      tail_cu_pct=tail, conc_tph=conc_tph, cu_tph=cu_tph,
                      residence_min=ss.residence_min)


def cloth_window_min(line: int, t_min: float, seed: int, prm: ParamSet) -> tuple[float, float]:
    """Cloth change window (start, end), model min, of the period that contains t_min.

    Periods of filt_cloth_every_h start at cal_shift_start_h (one per shift
    at 12 h); start in the period = u01(seed, period index, "cloth-<line>")
    * (filt_cloth_every_h - filt_cloth_h) h. Depends on seed and time only,
    so every copy of the plant sees the same window.
    """
    period = prm["filt_cloth_every_h"] * MIN_PER_H
    origin = prm["cal_shift_start_h"] * MIN_PER_H
    k = math.floor((t_min - origin) / period)
    room_h = max(0.0, prm["filt_cloth_every_h"] - prm["filt_cloth_h"])
    start = origin + k * period + u01(seed, k, f"cloth-{line}") * room_h * MIN_PER_H
    return start, start + prm["filt_cloth_h"] * MIN_PER_H


def filter_capacity_tph(fi: FilterState, t_min: float, stock_full: bool, seed: int,
                        prm: ParamSet) -> float:
    """Filter capacity this step, t/h dry; sets presses_on, limit_tph, state.

    One press is out for filt_cloth_h once per filt_cloth_every_h (12 h =
    one shift); its start in the shift = u01(seed, shift_index, "cloth-<line>")
    * (filt_cloth_every_h - filt_cloth_h) hours after the shift start (see
    cloth_window_min). Same in all copies. stock_full -> 0 presses (STOP).
    The window is sampled at t_min (step start).
    ONE when one press is out, RUN when all run.
    limit_tph = presses_on * filt_press_tph.
    """
    total = int(prm["filt_presses"])
    if stock_full:
        on = 0
    else:
        start, end = cloth_window_min(fi.line, t_min, seed, prm)
        on = total - 1 if start <= t_min < end else total
        on = max(0, on)
    fi.presses_on = on
    fi.limit_tph = on * prm["filt_press_tph"]
    fi.state = "STOP" if on == 0 else "ONE" if on < total else "RUN"
    return fi.limit_tph


def thickener_step(th: ThickenerState, in_tph: float, cap_tph: float, dt_min: float,
                   prm: ParamSet) -> float:
    """Concentrate thickener; returns underflow to the filter, t/h dry.

    out = min(in + inventory * 60 / dt, cap); inventory += (in - out) * dt / 60
    (not clamped: above thick_cap_t the state is FULL).
    Water (1 t/m3): the bed is held at thick_uf_solids_pct, so solids that
    stay in the bed keep their bed water. Overflow = feed water - underflow
    water - change of bed water, which reduces to
    overflow_m3h = in * ((100 - thick_feed_solids_pct) / thick_feed_solids_pct
                         - (100 - thick_uf_solids_pct) / thick_uf_solids_pct) (>= 0);
    at steady state (in = out) this is feed water - underflow water.
    hours_to_full = (thick_cap_t - inventory) / (in - out) when rising, else NO_VALUE;
    HIGH at >= thick_high_frac * cap, FULL at >= cap.
    """
    in_tph = max(0.0, in_tph)
    avail = in_tph + (th.inventory_t * MIN_PER_H / dt_min if dt_min > 0.0 else 0.0)
    out = max(0.0, min(avail, cap_tph))
    if dt_min > 0.0:
        th.inventory_t = max(0.0, th.inventory_t + (in_tph - out) * dt_min / MIN_PER_H)
    fs, us = prm["thick_feed_solids_pct"], prm["thick_uf_solids_pct"]
    w_feed = (100.0 - fs) / fs               # m3 water per t solids in feed
    w_uf = (100.0 - us) / us                 # m3 water per t solids in underflow and bed
    cap = prm["thick_cap_t"]
    th.feed_tph = in_tph
    th.underflow_tph = out
    th.solids_pct = us
    th.overflow_m3h = max(0.0, in_tph * (w_feed - w_uf))
    if th.inventory_t >= cap:
        th.state = "FULL"
        th.hours_to_full = 0.0
    else:
        th.state = "HIGH" if th.inventory_t >= prm["thick_high_frac"] * cap else "NORMAL"
        th.hours_to_full = (cap - th.inventory_t) / (in_tph - out) if in_tph > out else NO_VALUE
    return out


def filter_step(fi: FilterState, underflow_tph: float, prm: ParamSet, z_moist: float) -> float:
    """Filter presses; returns wet cake to the concentrate stock, t/h.

    cake_tph (dry) = underflow_tph; moisture_pct = filt_moist_pct + filt_moist_sigma_pp * z
    (not below 0); wet = dry / (1 - moisture / 100).
    """
    dry = max(0.0, underflow_tph)
    m = max(0.0, prm["filt_moist_pct"] + prm["filt_moist_sigma_pp"] * z_moist)
    fi.cake_tph = dry
    fi.moisture_pct = m
    return dry / (1.0 - m / 100.0)


def _trains_per_day(prm: ParamSet) -> int:
    return len({prm["cstock_train1_h"], prm["cstock_train2_h"]})


def conc_stock_step(cs: ConcStockState, wet_in_tph: float, t_min: float, dt_min: float,
                    prm: ParamSet) -> float:
    """Shared concentrate stock and rail loading; returns tonnes shipped this step (wet).

    stock += wet_in * dt / 60. A train of cstock_train_wagons x cstock_wagon_t
    loads once at cstock_train1_h and once at cstock_train2_h each day
    (train times in [t, t + dt); cs.last_train_h, the absolute model hour of
    the last train, guards repeats), shipping min(stock, train size);
    wagons = loaded wagons (the last one may be part-filled);
    shipped_t_shift and wagons_shift accumulate (the plant resets them at
    shift change). HIGH at >= cstock_high_frac * cap, FULL at >= cstock_cap_t.
    hours_to_full = (cap - stock) / net in, net in = wet_in - mean train
    shipping (trains per day x train size / 24 h), when net in > 0, else NO_VALUE.
    """
    wet_in_tph = max(0.0, wet_in_tph)
    cs.in_tph = wet_in_tph
    if dt_min > 0.0:
        cs.stock_t += wet_in_tph * dt_min / MIN_PER_H
    wagon_t = prm["cstock_wagon_t"]
    train_t = prm["cstock_train_wagons"] * wagon_t
    hours = sorted({prm["cstock_train1_h"], prm["cstock_train2_h"]})
    t_end = t_min + max(0.0, dt_min)
    shipped = 0.0
    day = math.floor(t_min / MIN_PER_DAY)
    while day * MIN_PER_DAY < t_end:
        for h in hours:
            t_train = day * MIN_PER_DAY + h * MIN_PER_H
            abs_h = int(math.floor(t_train / MIN_PER_H))
            if t_min <= t_train < t_end and abs_h > cs.last_train_h:
                load = min(cs.stock_t, train_t)
                cs.last_train_h = abs_h
                if load > 0.0:
                    cs.stock_t -= load
                    shipped += load
                    cs.wagons_shift += min(int(prm["cstock_train_wagons"]), int(math.ceil(load / wagon_t)))
        day += 1
    cs.shipped_t_shift += shipped
    cap = prm["cstock_cap_t"]
    if cs.stock_t >= cap:
        cs.state = "FULL"
    elif cs.stock_t >= prm["cstock_high_frac"] * cap:
        cs.state = "HIGH"
    else:
        cs.state = "NORMAL"
    net = wet_in_tph - _trains_per_day(prm) * train_t / (MIN_PER_DAY / MIN_PER_H)
    if cs.stock_t >= cap:
        cs.hours_to_full = 0.0
    else:
        cs.hours_to_full = (cap - cs.stock_t) / net if net > 0.0 else NO_VALUE
    return shipped
