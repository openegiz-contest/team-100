"""Comminution: primary crusher, SAG mill, pebble crushing, ball mills, cyclones.

Design: section 3 rows 5 (crusher), 9 (SAG), 10 (ball), 11 (cyclones),
17 (pebble); section 4 rows "SAG specific energy", "SAG power",
"SAG tonnage", "pebble crushing", "ball mills", "cyclones", "agreement";
section 7 C2 (one ball mill, 1925 t/h) and C3 (pebble limit, 2960 t/h).

Rules for this file:
  - read numbers only from prm (sim.params.ParamSet), never literals;
    the named constants below are unit conversions and fixed parts of
    published formulas, not model parameters;
  - no randomness inside: noise arrives as z ~ N(0, 1) arguments;
  - unit-step functions mutate only the unit state passed in.

Reference values (base ore A*b 35, BWi 19.4, 2 ball mills):
  E_SAG 6.748 kWh/t, Q 3853 t/h at 26.0 MW, load 25 %, pebbles 578 t/h,
  P80 178.5 um; hard ore A*b 27 / BWi 20.9: Q 2960 t/h (pebble limit),
  P80 134 um; one ball mill at 2650 t/h: P80 279 um.
  Ground-out mill (no feed): ball charge 12 % draws 17.8 MW (69 % of P0);
  one ball mill at 1937 t/h needs 13.1 MW: the mill is slowed to 54 % crit.
  Small fresh feed: P80 not below 120 um (cyclone overflow, not Bond).
"""
from __future__ import annotations

import math

from .params import ParamSet
from .state import (MIN_PER_H, NO_VALUE, BallState, CauseEffects, CrusherState, CycloneState,
                    OreProps, PebbleState, SagState, base_ore, feed_end_wear_mm)

# Unit conversions and fixed parts of the published formulas.
KW_PER_MW = 1000.0
T_PER_MT = 1.0e6
PCT = 100.0              # fraction -> %
DWI_SCALE = 100.0        # DWi = 100 rho / A*b, kWh/m3 (Morrell, SMC definition)
BOND_K = 10.0            # Bond law: W = 10 Wi (1/sqrt(P80) - 1/sqrt(F80)), kWh/t with um
ETA_REF = 1.0            # liner multiplier at the end of the new-liner ramp (reference)
LOAD_MAX_FRAC = 1.0      # mill filling cannot exceed the mill volume
BISECT_STEPS = 60        # halvings of the speed root (below 1e-17 of the range)
INF = math.inf

# Unit states (design section 3).
CR_RUN, CR_SLOW, CR_STOP = "RUN", "SLOW", "STOP"
SAG_RUN, SAG_STARVED, SAG_GRID = "RUN", "STARVED", "LIMITED_GRID"
SAG_RELINE = "RELINE"
SAG_DOWN = (SAG_RELINE, "STOP")        # set by the plant only
PEB_RUN, PEB_LIMIT, PEB_STOP = "RUN", "LIMIT", "STOP"
BALL_RUN = "RUN"
CY_NORMAL, CY_UPSET = "NORMAL", "UPSET"
FAULT_LUBE = "lube_trip"


# ---------------------------------------------------------------------------
# Pure formulas
# ---------------------------------------------------------------------------
def dwi(axb: float, prm: ParamSet) -> float:
    """Drop-weight index, kWh/m3: DWi = 100 * ore_density_t_m3 / A*b.

    A*b <= 0 is not an ore property -> ValueError.
    """
    if axb <= 0.0:
        raise ValueError(f"A*b must be positive, got {axb}")
    return DWI_SCALE * prm["ore_density_t_m3"] / axb


def _morrell_kwh_t(axb: float, prm: ParamSet) -> float:
    """E = sag_k * F80^a * DWi^b, kWh/t (pebble crushing running)."""
    return (prm["sag_k"] * prm["sag_f80_mm"] ** prm["sag_morrell_a"]
            * dwi(axb, prm) ** prm["sag_morrell_b"])


def pebble_stop_mult(axb: float, prm: ParamSet) -> float:
    """E_SAG multiplier while the pebble crusher is stopped, -.

    peb_stop_e_med at A*b >= ore_axb_base, peb_stop_e_hard at A*b <= ore_axb_hard,
    linear in A*b between (Lihir analog: +6 % medium, +10 % hard ore).
    """
    a_hard, a_med = prm["ore_axb_hard"], prm["ore_axb_base"]
    m_hard, m_med = prm["peb_stop_e_hard"], prm["peb_stop_e_med"]
    if axb >= a_med:
        return m_med
    if axb <= a_hard:
        return m_hard
    w = (axb - a_hard) / (a_med - a_hard)
    return m_hard + w * (m_med - m_hard)


def sag_specific_energy(ore: OreProps, prm: ParamSet, pebble_running: bool = True) -> float:
    """SAG specific energy, kWh/t (Morrell form).

    E = sag_k * sag_f80_mm ** sag_morrell_a * dwi(ore.axb) ** sag_morrell_b.
    Pebble crusher stopped: E *= peb_stop_e_med at A*b >= ore_axb_base,
    peb_stop_e_hard at A*b <= ore_axb_hard, linear in A*b between.
    Base ore gives sag_e_base_kwh_t (6.748).
    """
    e = _morrell_kwh_t(ore.axb, prm)
    if not pebble_running:
        e *= pebble_stop_mult(ore.axb, prm)
    return e


def _f_load(j: float, prm: ParamSet) -> float:
    """Austin load term f(J) = J (1 - sag_austin_j J), J as a fraction."""
    return j * (1.0 - prm["sag_austin_j"] * j)


def _g_speed(phi: float, prm: ParamSet) -> float:
    """Austin speed term g(phi) = phi (1 - a / 2^(b - c phi)), phi as a fraction of critical."""
    return phi * (1.0 - prm["sag_austin_a"] / 2.0 ** (prm["sag_austin_b"] - prm["sag_austin_c"] * phi))


def _ref_terms(prm: ParamSet) -> tuple[float, float]:
    """f(J0) and g(phi0) of the reference point (sag_load0_pct, sag_speed_pct)."""
    return _f_load(prm["sag_load0_pct"] / PCT, prm), _g_speed(prm["sag_speed_pct"] / PCT, prm)


def austin_power_ratio(load_pct: float, speed_pct: float, prm: ParamSet) -> float:
    """SAG power relative to reference, P / P0, - (Austin form).

    f(J) = J (1 - sag_austin_j J); g(phi) = phi (1 - sag_austin_a / 2 ** (sag_austin_b - sag_austin_c phi));
    ratio = f(J) / f(J0) * g(phi) / g(phi0); J, phi as fractions;
    J0 = sag_load0_pct, phi0 = sag_speed_pct. 1.0 at reference, 0 at J = 0.
    J is clipped to [0, 1] (mill volume); the result is never negative.
    """
    j = min(max(load_pct / PCT, 0.0), LOAD_MAX_FRAC)
    phi = max(speed_pct / PCT, 0.0)
    f0, g0 = _ref_terms(prm)
    return max(0.0, _f_load(j, prm) / f0 * _g_speed(phi, prm) / g0)


def ball_floor_ratio(speed_pct: float, prm: ParamSet) -> float:
    """Power of a turning mill whose ore is ground out, P / P0, - (ball charge only).

    sag_ball_dens_mult * austin_power_ratio(sag_ball_load_pct, speed): the
    ball charge (Bradken 12 %) stays in the mill and is denser than the mixed
    charge; about 0.69 at the setpoint speed.
    """
    return prm["sag_ball_dens_mult"] * austin_power_ratio(prm["sag_ball_load_pct"], speed_pct, prm)


def sag_power_ratio(load_pct: float, speed_pct: float, prm: ParamSet) -> float:
    """SAG power with its ball charge, P / P0, -: max(austin_power_ratio, ball_floor_ratio).

    Equal to austin_power_ratio above the equivalent load of the ball
    charge (about 15 % at J0 25 %), flat at the ball-charge draw below it.
    """
    return max(austin_power_ratio(load_pct, speed_pct, prm), ball_floor_ratio(speed_pct, prm))


def speed_for_speed_ratio(ratio: float, prm: ParamSet) -> float:
    """Speed, % crit, at which g(phi) / g(phi0) = ratio (0 <= ratio <= 1), phi0 = sag_speed_pct.

    g rises on [0, phi0], so the root is found by bisection (fixed 60 halvings,
    deterministic). ratio >= 1 gives phi0, ratio <= 0 gives 0.
    """
    phi0 = prm["sag_speed_pct"] / PCT
    if ratio >= 1.0:
        return PCT * phi0
    if ratio <= 0.0:
        return 0.0
    target = ratio * _g_speed(phi0, prm)
    lo, hi = 0.0, phi0
    for _ in range(BISECT_STEPS):
        mid = 0.5 * (lo + hi)
        if _g_speed(mid, prm) < target:
            lo = mid
        else:
            hi = mid
    return PCT * 0.5 * (lo + hi)


def load_for_power_ratio(ratio: float, speed_pct: float, prm: ParamSet) -> float:
    """Inverse of austin_power_ratio in load at given speed, % volume.

    Root of f(J) = ratio f(J0) g(phi0) / g(phi) on [0, 50 / sag_austin_j] (rising branch);
    ratio is clamped to [0, ratio at the top of the branch].
    Closed form: J = 2 y / (1 + sqrt(1 - 4 k y)), y = f target, k = sag_austin_j.
    """
    k = prm["sag_austin_j"]
    j_top = 1.0 / (2.0 * k)                 # peak of f(J), fraction
    f_top = _f_load(j_top, prm)
    if ratio <= 0.0:
        return 0.0
    g = _g_speed(max(speed_pct / PCT, 0.0), prm)
    if g <= 0.0:                            # mill not turning: no load draws the power
        return PCT * j_top
    f0, g0 = _ref_terms(prm)
    y = min(ratio * f0 * g0 / g, f_top)
    return PCT * 2.0 * y / (1.0 + math.sqrt(max(0.0, 1.0 - 4.0 * k * y)))


def liner_eta(liner_x: float, prm: ParamSet) -> float:
    """Liner campaign multiplier on SAG capacity, - (Powell form).

    Piecewise linear through (0, liner_eta_new), (liner_x_ramp, 1.0),
    (liner_x_peak, liner_eta_peak), (1.0, liner_eta_end); constant outside [0, 1].
    liner_x is the share of the campaign tonnage (liner_life_mt) already ground.
    """
    pts = ((0.0, prm["liner_eta_new"]), (prm["liner_x_ramp"], ETA_REF),
           (prm["liner_x_peak"], prm["liner_eta_peak"]), (1.0, prm["liner_eta_end"]))
    if liner_x <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if liner_x <= x1:
            if x1 <= x0:
                return y1
            return y0 + (y1 - y0) * (liner_x - x0) / (x1 - x0)
    return pts[-1][1]


def pebble_fraction(axb: float, prm: ParamSet) -> float:
    """Pebble recycle per t of fresh SAG feed, -.

    Linear through (ore_axb_base, peb_frac_base) and (ore_axb_hard, peb_frac_hard),
    extrapolated outside, never below 0. A*b 35 -> 0.15, A*b 27 -> 0.25.
    """
    a0, p0 = prm["ore_axb_base"], prm["peb_frac_base"]
    a1, p1 = prm["ore_axb_hard"], prm["peb_frac_hard"]
    slope = (p1 - p0) / (a1 - a0)
    return max(0.0, p0 + slope * (axb - a0))


def sag_capacity_tph(power_kw: float, e_kwh_t: float, eta: float) -> float:
    """Throughput the SAG can grind, t/h: Q = eta * P / E (0 when P <= 0 or eta <= 0).

    power_kw: shaft power, kW; e_kwh_t: specific energy, kWh/t (> 0); eta: liner multiplier, -.
    """
    if power_kw <= 0.0 or eta <= 0.0:
        return 0.0
    if e_kwh_t <= 0.0:
        raise ValueError(f"specific energy must be positive, got {e_kwh_t}")
    return eta * power_kw / e_kwh_t


def sag_power_for_tph(q_tph: float, e_kwh_t: float, eta: float) -> float:
    """Shaft power needed for a throughput, kW: P = Q * E / eta (0 when Q <= 0).

    q_tph: t/h (float("inf") gives inf); e_kwh_t: kWh/t; eta: liner multiplier, - (> 0).
    """
    if q_tph <= 0.0:
        return 0.0
    if eta <= 0.0:
        raise ValueError(f"liner multiplier must be positive, got {eta}")
    return q_tph * e_kwh_t / eta


def axb_from_energy(e_kwh_t: float, prm: ParamSet) -> float:
    """Soft sensor: A*b that explains an observed P/Q, - (inverse of sag_specific_energy, pebbles running).

    It cannot tell liner wear from harder ore; that is intended. NO_VALUE for e <= 0.
    A*b = 100 rho / (E / (sag_k F80^a)) ** (1 / b).
    """
    if not e_kwh_t > 0.0 or math.isinf(e_kwh_t):
        return NO_VALUE
    scale = prm["sag_k"] * prm["sag_f80_mm"] ** prm["sag_morrell_a"]
    dwi_kwh_m3 = (e_kwh_t / scale) ** (1.0 / prm["sag_morrell_b"])
    return DWI_SCALE * prm["ore_density_t_m3"] / dwi_kwh_m3


def ball_p80_um(q_tph: float, ball_power_kw: float, bwi: float, prm: ParamSet) -> float:
    """Bond grind size, um.

    E_b = min(ball_power_kw / q_tph, E_max) (kWh/t); 1/sqrt(P80) = E_b / (10 BWi) + 1/sqrt(ball_f80_um).
    E_max = 10 BWi (1/sqrt(ball_p80_min_um) - 1/sqrt(ball_f80_um)): with little fresh
    feed the cyclones, not the mill energy, set the overflow, so P80 does not
    fall below ball_p80_min_um (Bond at 41 MW over 1000 t/h would give 19 um).
    NO_VALUE when q_tph <= 0 or ball_power_kw <= 0.
    41 000 kW, 3853 t/h, BWi 19.4 -> 178.5 um; 20 500 kW, 2650 t/h -> 279 um.
    """
    if q_tph <= 0.0 or ball_power_kw <= 0.0:
        return NO_VALUE
    if bwi <= 0.0:
        raise ValueError(f"Bond work index must be positive, got {bwi}")
    e_b = ball_power_kw / q_tph
    inv_f80 = 1.0 / math.sqrt(prm["ball_f80_um"])
    e_max = BOND_K * bwi * (1.0 / math.sqrt(prm["ball_p80_min_um"]) - inv_f80)
    if e_max > 0.0:
        e_b = min(e_b, e_max)
    inv_sqrt = e_b / (BOND_K * bwi) + inv_f80
    return 1.0 / (inv_sqrt * inv_sqrt)


def ball_q_for_p80(ball_power_kw: float, bwi: float, p80_um: float, prm: ParamSet) -> float:
    """Inverse Bond, t/h: Q = P / (10 BWi (1/sqrt(P80) - 1/sqrt(ball_f80_um))).

    20 500 kW, BWi 19.4, 179 um -> about 1930 t/h. 0 when P <= 0;
    inf when P80 >= F80 (no grinding needed).
    """
    if ball_power_kw <= 0.0:
        return 0.0
    if bwi <= 0.0 or p80_um <= 0.0:
        raise ValueError(f"BWi and P80 must be positive, got {bwi}, {p80_um}")
    w = BOND_K * bwi * (1.0 / math.sqrt(p80_um) - 1.0 / math.sqrt(prm["ball_f80_um"]))
    if w <= 0.0:
        return INF
    return ball_power_kw / w


def _running(balls: list[BallState]) -> int:
    return sum(1 for b in balls if b.state == BALL_RUN)


def line_feed_cap_tph(balls: list[BallState], bwi: float, prm: ParamSet) -> float:
    """Line control rule: fresh-feed cap so running ball mills hold ball_p80_target_um, t/h.

    All ball_per_line mills running -> float("inf"); none running -> 0.
    Otherwise ball_q_for_p80(sum of running mill power, bwi, ball_p80_target_um),
    mill power = ball_power_mw (load-driven, not the last published value).
    C2: one mill, BWi 19.4 -> 1937 t/h.
    """
    n_run = _running(balls)
    if n_run >= int(round(prm["ball_per_line"])):
        return INF
    if n_run == 0:
        return 0.0
    power_kw = n_run * prm["ball_power_mw"] * KW_PER_MW
    return ball_q_for_p80(power_kw, bwi, prm["ball_p80_target_um"], prm)


# ---------------------------------------------------------------------------
# Unit steps
# ---------------------------------------------------------------------------
def crusher_step(cr: CrusherState, avail_tph: float, room_tph: float, prm: ParamSet,
                 z_lube: float) -> float:
    """Advance the primary crusher one step; returns crushed t/h.

    avail_tph: ore in the dump pocket this step, t/h; room_tph: what the
    stockpile can still accept, t/h.
    lube_kpa = crush_lube_kpa + cr.lube_bias_kpa + crush_lube_noise_kpa * z_lube;
    below crush_lube_trip_kpa the protection sets cr.fault = "lube_trip".
    cr.fault != "" -> STOP, tph 0, power 0 (fault is cleared by the plant).
    Else tph = min(avail_tph, room_tph, crush_cap_tph); SLOW when room_tph
    is the binding limit and below min(avail, cap); RUN otherwise.
    power_kw = crush_power_mw * 1000 unless STOP.
    """
    cr.lube_kpa = prm["crush_lube_kpa"] + cr.lube_bias_kpa + prm["crush_lube_noise_kpa"] * z_lube
    if not cr.fault and cr.lube_kpa < prm["crush_lube_trip_kpa"]:
        cr.fault = FAULT_LUBE
    if cr.fault:
        cr.state, cr.tph, cr.power_kw = CR_STOP, 0.0, 0.0
        return 0.0
    supply = min(max(avail_tph, 0.0), prm["crush_cap_tph"])
    room = max(room_tph, 0.0)
    cr.tph = min(supply, room)
    cr.state = CR_SLOW if room < supply else CR_RUN
    cr.power_kw = prm["crush_power_mw"] * KW_PER_MW
    return cr.tph


def _pebble_update(peb: PebbleState, feed_tph: float, limit_tph: float, prm: ParamSet) -> None:
    """Pebble crusher features; LIMIT at peb_warn_frac of the limit, STOP kept as set by the plant."""
    peb.feed_tph = feed_tph
    peb.limit_tph = limit_tph
    peb.load_pct = PCT * feed_tph / limit_tph if limit_tph > 0.0 else 0.0
    if peb.state != PEB_STOP:
        peb.state = PEB_LIMIT if peb.load_pct >= PCT * prm["peb_warn_frac"] else PEB_RUN


def sag_step(sag: SagState, peb: PebbleState, feed_avail_tph: float, ore: OreProps,
             power_cap_kw: float, fx: CauseEffects, dt_min: float, prm: ParamSet,
             z_power: float) -> float:
    """Advance the SAG mill and pebble loop one step; returns fresh feed drawn, t/h.

    feed_avail_tph: what the stockpile can deliver this step, t/h;
    ore: true blend of the feed (A*b <= 0 -> last feed blend is kept);
    power_cap_kw: shaft cap from grid or line control, kW (float("inf") for none);
    fx: hidden-cause effects; dt_min: step, min; z_power ~ N(0, 1).

    Rules:
      state STOP (set by plant): feed 0, power 0, the charge stays (load_pct kept);
      state RELINE: feed 0, power 0, the mill is ground out: load decays with
      sag_tau_min towards the ball charge sag_ball_load_pct.
      P_sp = min(sag.power_sp_kw, power_cap_kw, sag_rated_mw * 1000);
      LIMITED_GRID when power_cap_kw < sag.power_sp_kw.
      E = sag_specific_energy(ore, prm, peb.state != "STOP") * fx.sag_e_mult;
      eta = liner_eta(sag.liner_x, prm) * fx.sag_eta_mult; sag.eta = eta.
      cap = sag_capacity_tph(P_sp, E, eta); with pebbles running and
      pebble_fraction(ore.axb) * cap > peb.limit_tph: cap = limit / fraction.
      Q = min(feed_avail_tph, cap); STARVED when Q < sag_starved_frac * cap
      (STARVED wins over LIMITED_GRID: missing feed is the binding limit).
      Target power ratio r = sag_power_for_tph(Q, E, eta) / P0, P0 = sag_power_sp_mw * 1000.
      Speed = sag_speed_pct; LIMITED_GRID with r below ball_floor_ratio: the
      control slows the mill until the ball charge draws r
      (speed_for_speed_ratio(r / floor)); sag.speed_pct shows it.
      Target load = load_for_power_ratio(r, speed) when r is above the
      ball-charge draw, else the ball charge; never below sag_ball_load_pct.
      load_pct follows with first-order lag sag_tau_min, exact for any dt:
      J += (J_t - J) (1 - exp(-dt / tau)); power_kw = P0 * sag_power_ratio(load, speed)
      * (1 + sag_power_sigma * z_power), within [0, rated]. A STARVED mill
      keeps its ball charge and draws about 69 % of P0.
      e_kwh_t = power_kw / Q (NO_VALUE when Q = 0); axb_soft = axb_from_energy(e_kwh_t)
      while Q > 0 and not STARVED (a draining mill gives no ore signal), else NO_VALUE.
      liner_wear_mm = feed_end_wear_mm(liner_wear_mm + liner_wear_mm_mt * Q * dt / 60 / 1e6)
      (counter by norm; restarts when the feed end is changed at an intermediate reline);
      liner_x += fx.liner_wear_mult * Q * dt / 60 / 1e6 / liner_life_mt (truth).
      Pebble: feed_tph = fraction * Q when running, else 0; load_pct = 100 * feed / limit;
      LIMIT when load_pct >= 100 * peb_warn_frac; STOP is kept as set by the plant.
      Sets sag.feed_tph, power_kw, power_limit_kw, speed_pct, load_pct, e_kwh_t, axb_soft,
      eta, feed_ore, state, liner_wear_mm, liner_x.
    """
    dt = max(dt_min, 0.0)
    rated_kw = prm["sag_rated_mw"] * KW_PER_MW
    p0_kw = prm["sag_power_sp_mw"] * KW_PER_MW          # Austin reference power at (J0, phi0)
    speed = prm["sag_speed_pct"]                         # setpoint; lowered below under a power cap
    j_ball = prm["sag_ball_load_pct"]
    keep = math.exp(-dt / prm["sag_tau_min"])            # share of the load gap left after dt
    limit_tph = peb.limit_tph if peb.limit_tph > 0.0 else prm["peb_limit_tph"]
    sag.power_limit_kw = min(rated_kw, power_cap_kw)
    sag.eta = liner_eta(sag.liner_x, prm) * fx.sag_eta_mult

    if ore.axb > 0.0:
        feed = ore
    elif sag.feed_ore.axb > 0.0:
        feed = sag.feed_ore
    else:
        feed = base_ore(prm)

    if sag.state in SAG_DOWN:
        if sag.state == SAG_RELINE:                      # ground out for relining: the balls stay
            sag.load_pct = j_ball + (sag.load_pct - j_ball) * keep
        sag.speed_pct = speed
        sag.power_kw = 0.0
        sag.feed_tph = 0.0
        sag.e_kwh_t = NO_VALUE
        sag.axb_soft = NO_VALUE
        _pebble_update(peb, 0.0, limit_tph, prm)
        return 0.0

    sp_kw = sag.power_sp_kw if sag.power_sp_kw > 0.0 else p0_kw
    p_sp = max(0.0, min(sp_kw, power_cap_kw, rated_kw))
    peb_on = peb.state != PEB_STOP
    e = sag_specific_energy(feed, prm, peb_on) * fx.sag_e_mult      # silent cause "energy": more kWh/t
    eta = sag.eta
    cap = sag_capacity_tph(p_sp, e, eta)
    frac = pebble_fraction(feed.axb, prm)
    if peb_on and frac * cap > limit_tph:
        cap = limit_tph / frac
    q = min(max(feed_avail_tph, 0.0), cap)

    if q < prm["sag_starved_frac"] * cap:
        state = SAG_STARVED
    elif power_cap_kw < sp_kw:
        state = SAG_GRID
    else:
        state = SAG_RUN

    ratio = sag_power_for_tph(q, e, eta) / p0_kw
    floor = ball_floor_ratio(speed, prm)
    if ratio > floor:
        j_target = max(load_for_power_ratio(ratio, speed, prm), j_ball)
    else:
        j_target = j_ball                                # the rock grinds out, the balls stay
        if state == SAG_GRID:
            # a power cap below the ball-charge draw: the control slows the mill
            speed = speed_for_speed_ratio(ratio / floor, prm)
    sag.speed_pct = speed
    sag.load_pct = j_target + (sag.load_pct - j_target) * keep
    power = p0_kw * sag_power_ratio(sag.load_pct, speed, prm) * (1.0 + prm["sag_power_sigma"] * z_power)
    sag.power_kw = min(max(power, 0.0), rated_kw)
    sag.feed_tph = q
    sag.e_kwh_t = sag.power_kw / q if q > 0.0 else NO_VALUE
    sag.axb_soft = axb_from_energy(sag.e_kwh_t, prm) if q > 0.0 and state != SAG_STARVED else NO_VALUE

    ground_mt = q * dt / MIN_PER_H / T_PER_MT
    sag.liner_wear_mm = feed_end_wear_mm(sag.liner_wear_mm + prm["liner_wear_mm_mt"] * ground_mt, prm)
    sag.liner_x += fx.liner_wear_mult * ground_mt / prm["liner_life_mt"]
    sag.feed_ore = feed.copy()
    sag.state = state

    _pebble_update(peb, frac * q if peb_on else 0.0, limit_tph, prm)
    return q


def ball_step(balls: list[BallState], q_tph: float, bwi: float, prm: ParamSet) -> float:
    """Ball mills of one line; returns Bond P80 before cyclone effects, um.

    RUN mill: power_kw = ball_power_mw * 1000 (load-driven, independent of feed);
    STOP mill: 0. Each running mill grinds Q / n_running, so
    e_kwh_t = power_kw * n_running / Q (2 mills at 3853 t/h: 10.6 kWh/t, the
    Bond energy of the line); STOP mill 0; NO_VALUE when Q = 0.
    Returns ball_p80_um(Q, total power, bwi) or NO_VALUE.
    """
    q = max(q_tph, 0.0)
    n_run = _running(balls)
    total_kw = 0.0
    for b in balls:
        b.power_kw = prm["ball_power_mw"] * KW_PER_MW if b.state == BALL_RUN else 0.0
        b.e_kwh_t = b.power_kw * n_run / q if q > 0.0 else NO_VALUE
        total_kw += b.power_kw
    return ball_p80_um(q, total_kw, bwi, prm)


def cyclone_open_for(q_tph: float, prm: ParamSet) -> int:
    """Cyclones the cluster control keeps open for a flow, -.

    Holds pressure near cyc_pressure_kpa: round(cyc_open * Q / cal_line_tph)
    within [1, cyc_total]. A clogged unit is still counted as open.
    """
    x = prm["cyc_open"] * q_tph / prm["cal_line_tph"]
    n = int(math.floor(x + 0.5))
    return min(max(n, 1), int(round(prm["cyc_total"])))


def cyclone_step(cy: CycloneState, q_tph: float, p80_grind_um: float, prm: ParamSet) -> float:
    """Cyclone cluster; returns flotation feed P80, um.

    open_count = cyclone_open_for(Q) (cluster control; clogging does not change it);
    p80_um = p80_grind + cyc_clog_p80_um * cy.clogged (clogged units stay counted as open);
    pressure_kpa = cyc_pressure_kpa * (Q / cal_line_tph * cyc_open / open_count) ** 2
                   * (1 + cyc_clog_dp_frac * cy.clogged);
    UPSET when Q > 0 and |pressure / cyc_pressure_kpa - 1| > cyc_upset_frac.
    Q = 0: pressure 0, p80 and open_count keep their last values, NORMAL.
    p80_grind_um <= 0 (no grind result): p80 keeps its last value.
    """
    p0 = prm["cyc_pressure_kpa"]
    if q_tph <= 0.0:
        cy.pressure_kpa = 0.0
        cy.state = CY_NORMAL
        return cy.p80_um
    clogged = max(cy.clogged, 0)
    cy.open_count = cyclone_open_for(q_tph, prm)
    if p80_grind_um > 0.0:
        cy.p80_grind_um = p80_grind_um
        cy.p80_um = p80_grind_um + prm["cyc_clog_p80_um"] * clogged
    rel = q_tph / prm["cal_line_tph"] * prm["cyc_open"] / cy.open_count
    cy.pressure_kpa = p0 * rel * rel * (1.0 + prm["cyc_clog_dp_frac"] * clogged)
    cy.state = CY_UPSET if abs(cy.pressure_kpa / p0 - 1.0) > prm["cyc_upset_frac"] else CY_NORMAL
    return cy.p80_um
