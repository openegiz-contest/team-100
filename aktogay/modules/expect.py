"""Expectation model of the modules: pure formulas on estimates and measurements.

Design file 17, section 4 (equations) and section 5 ("the expectation is
its own model, not a copy of the simulator: the same formulas on block-model
estimates, on measurements and without hidden causes").

Units: t/h, kW, kWh/t, um, % Cu, % (recoveries), USD/h. NO_VALUE = -1.0
marks a missing number (never None, NaN or inf in published values).
"""
from __future__ import annotations

import math

from .params import Prm

NO_VALUE = -1.0
PCT = 100.0
KW_PER_MW = 1000.0
DWI_SCALE = 100.0     # DWi = 100 rho / A*b, kWh/m3 (Morrell, SMC definition)
BOND_K = 10.0         # Bond: W = 10 Wi (1/sqrt(P80) - 1/sqrt(F80)), um


def valid(x) -> bool:
    try:
        return x is not None and x != NO_VALUE and math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


# ---------------------------------------------------------------------------
# SAG: Morrell energy, pebble limit, capacity
# ---------------------------------------------------------------------------
def dwi(axb: float, prm: Prm) -> float:
    """Drop-weight index, kWh/m3: 100 rho / A*b (A*b must be positive)."""
    if axb <= 0.0:
        raise ValueError(f"A*b must be positive, got {axb}")
    return DWI_SCALE * prm["ore_density_t_m3"] / axb


def pebble_stop_mult(axb: float, prm: Prm) -> float:
    """E_SAG multiplier while the pebble crusher stands: +6 % medium ore, +10 % hard ore, linear between."""
    a_hard, a_med = prm["ore_axb_hard"], prm["ore_axb_base"]
    m_hard, m_med = prm["peb_stop_e_hard"], prm["peb_stop_e_med"]
    if axb >= a_med:
        return m_med
    if axb <= a_hard:
        return m_hard
    return m_hard + (axb - a_hard) / (a_med - a_hard) * (m_med - m_hard)


def sag_energy_kwh_t(axb: float, prm: Prm, pebble_on: bool = True) -> float:
    """SAG specific energy, kWh/t: K F80^a DWi^b (6.748 at A*b 35); x pebble_stop_mult when pebbles stand."""
    e = prm["sag_k"] * prm["sag_f80_mm"] ** prm["sag_morrell_a"] * dwi(axb, prm) ** prm["sag_morrell_b"]
    return e * (1.0 if pebble_on else pebble_stop_mult(axb, prm))


def axb_from_energy(e_kwh_t: float, prm: Prm) -> float:
    """Soft sensor: A*b that explains a specific energy (pebbles running); NO_VALUE for e <= 0."""
    if not e_kwh_t > 0.0 or math.isinf(e_kwh_t):
        return NO_VALUE
    scale = prm["sag_k"] * prm["sag_f80_mm"] ** prm["sag_morrell_a"]
    return DWI_SCALE * prm["ore_density_t_m3"] / (e_kwh_t / scale) ** (1.0 / prm["sag_morrell_b"])


def pebble_fraction(axb: float, prm: Prm) -> float:
    """Pebbles per t of fresh feed: linear through (35, 0.15) and (27, 0.25), never below 0."""
    a0, p0 = prm["ore_axb_base"], prm["peb_frac_base"]
    a1, p1 = prm["ore_axb_hard"], prm["peb_frac_hard"]
    return max(0.0, p0 + (p1 - p0) / (a1 - a0) * (axb - a0))


def sag_capacity_tph(power_kw: float, axb: float, prm: Prm, pebble_on: bool = True,
                     limit_tph: float | None = None) -> float:
    """Throughput the mill can take, t/h: min(P / E(A*b), pebble limit / pebble fraction).

    Liner multiplier nominal (1.0): the modules do not know the campaign.
    """
    if power_kw <= 0.0:
        return 0.0
    e = sag_energy_kwh_t(axb, prm, pebble_on)
    cap = power_kw / e
    if pebble_on:
        lim = prm["peb_limit_tph"] if limit_tph is None or limit_tph <= 0.0 else limit_tph
        frac = pebble_fraction(axb, prm)
        if frac > 0.0 and frac * cap > lim:
            cap = lim / frac
    return cap


def sag_mix_energy(shares: list[tuple[float, float]], prm: Prm, pebble_on: bool = True) -> float:
    """Specific energy of a blend, kWh/t: energies add by tonnes (A*b is not averaged).

    shares: [(share, A*b)], shares sum to 1 (renormalised when they do not).
    """
    tot = sum(s for s, _ in shares if s > 0.0)
    if tot <= 0.0:
        return sag_energy_kwh_t(prm["ore_axb_base"], prm, pebble_on)
    return sum(s / tot * sag_energy_kwh_t(a, prm, pebble_on) for s, a in shares if s > 0.0)


def sag_mix_capacity_tph(power_kw: float, shares: list[tuple[float, float]], prm: Prm,
                         pebble_on: bool = True, limit_tph: float | None = None) -> float:
    """Capacity of a blend, t/h: P / E_mix, then the pebble limit on the mixed pebble fraction."""
    if power_kw <= 0.0:
        return 0.0
    cap = power_kw / sag_mix_energy(shares, prm, pebble_on)
    if pebble_on:
        tot = sum(s for s, _ in shares if s > 0.0)
        frac = (sum(s / tot * pebble_fraction(a, prm) for s, a in shares if s > 0.0) if tot > 0.0
                else pebble_fraction(prm["ore_axb_base"], prm))
        lim = prm["peb_limit_tph"] if limit_tph is None or limit_tph <= 0.0 else limit_tph
        if frac > 0.0 and frac * cap > lim:
            cap = lim / frac
    return cap


# ---------------------------------------------------------------------------
# Ball mills and cyclones: Bond
# ---------------------------------------------------------------------------
def bwi_from_axb(axb: float, prm: Prm) -> float:
    """Bond work index estimated from A*b, kWh/t: line through (35, 19.4) and (27, 20.9), clamped 17.3-22."""
    a0, w0 = prm["ore_axb_base"], prm["ore_bwi_base"]
    a1, w1 = prm["ore_axb_hard"], prm["ore_bwi_hard"]
    return clamp(w0 + (w1 - w0) / (a1 - a0) * (axb - a0), 17.3, 22.0)


def bond_p80_um(q_tph: float, ball_power_kw: float, bwi: float, prm: Prm) -> float:
    """Grind size, um: 1/sqrt(P80) = E_b / (10 BWi) + 1/sqrt(F80), E_b = P / Q capped at the overflow floor."""
    if q_tph <= 0.0 or ball_power_kw <= 0.0 or bwi <= 0.0:
        return NO_VALUE
    e_b = ball_power_kw / q_tph
    inv_f80 = 1.0 / math.sqrt(prm["ball_f80_um"])
    e_max = BOND_K * bwi * (1.0 / math.sqrt(prm["ball_p80_min_um"]) - inv_f80)
    if e_max > 0.0:
        e_b = min(e_b, e_max)
    inv_sqrt = e_b / (BOND_K * bwi) + inv_f80
    return 1.0 / (inv_sqrt * inv_sqrt)


def p80_sigma_um(q_tph: float, ball_power_kw: float, bwi: float, prm: Prm) -> float:
    """1 SD of the expected P80, um: analyser noise plus the BWi uncertainty from the block A*b error."""
    s_meas = prm["sens_p80_sigma_um"]
    p80 = bond_p80_um(q_tph, ball_power_kw, bwi, prm)
    if not valid(p80):
        return s_meas
    # dBWi from dA*b: slope of bwi_from_axb times the relative block error
    slope = (prm["ore_bwi_hard"] - prm["ore_bwi_base"]) / (prm["ore_axb_hard"] - prm["ore_axb_base"])
    d_bwi = abs(slope) * prm["blk_err_axb_sigma"] * prm["ore_axb_base"]
    e_b = ball_power_kw / q_tph
    u = e_b / (BOND_K * bwi) + 1.0 / math.sqrt(prm["ball_f80_um"])
    du = e_b / (BOND_K * bwi * bwi) * d_bwi
    s_model = p80 * 2.0 * du / u if u > 0.0 else 0.0
    return math.sqrt(s_meas * s_meas + s_model * s_model)


# ---------------------------------------------------------------------------
# Flotation chain
# ---------------------------------------------------------------------------
def _base_stage_share(prm: Prm) -> float:
    return (1.0 - math.exp(-prm["flot_ktau0"])) * prm["clean_r0_pct"] / PCT


def residence_min(q_tph: float, prm: Prm) -> float:
    """Rougher residence, min: tau0 x base t/h / Q (NO_VALUE for Q <= 0)."""
    if q_tph <= 0.0:
        return NO_VALUE
    return prm["flot_tau0_min"] * prm["line_tph_base"] / q_tph


def r_inf_pct(feed_cu: float, ascu_pct: float, p80_um: float, dose_ratio: float, prm: Prm) -> float:
    """Rougher ultimate recovery, %: grade, ASCu, grind and dose terms on R_inf0 (clamped 0-100)."""
    if feed_cu <= 0.0:
        return 0.0
    share = _base_stage_share(prm)
    r = prm["flot_rinf0_pct"]
    r += prm["flot_grade_pp_ln"] / share * math.log(feed_cu / prm["flot_grade_ref_pct"])
    r -= prm["flot_jose_ascu"] / share * (ascu_pct - prm["flot_ascu_ref_pct"])
    if valid(p80_um):
        r -= prm["flot_p80_pp_10um"] * max(0.0, p80_um - prm["p80_ref_um"]) / 10.0
    deficit = clamp(1.0 - dose_ratio, 0.0, 1.0)
    r -= prm["flot_dose_pp"] / share * deficit / prm["flot_dose_ref_deficit"]
    return clamp(r, 0.0, PCT)


def rougher_recovery_pct(r_inf: float, tau_min: float, prm: Prm) -> float:
    """First-order kinetics, %: R_inf (1 - exp(-k tau)), k = ktau0 / tau0."""
    if tau_min <= 0.0 or r_inf <= 0.0:
        return 0.0
    return r_inf * (1.0 - math.exp(-prm["flot_ktau0"] / prm["flot_tau0_min"] * tau_min))


def mass_pull_pct(feed_cu: float, prm: Prm) -> float:
    return 0.0 if feed_cu <= 0.0 else prm["flot_pull0_pct"] * feed_cu / prm["flot_grade_ref_pct"]


def cleaner_recovery_pct(pull_pct: float, prm: Prm) -> float:
    extra = max(0.0, pull_pct - prm["flot_pull0_pct"])
    return clamp(prm["clean_r0_pct"] - prm["clean_pp_10pp"] * extra / 10.0, 0.0, PCT)


def total_recovery_pct(q_tph: float, feed_cu: float, ascu_pct: float, p80_um: float, dose_ratio: float,
                       prm: Prm) -> float:
    """Expected section recovery, %: rougher x cleaner (NO_VALUE when Q or grade is missing)."""
    if q_tph <= 0.0 or feed_cu <= 0.0:
        return NO_VALUE
    tau = residence_min(q_tph, prm)
    r_r = rougher_recovery_pct(r_inf_pct(feed_cu, ascu_pct, p80_um, dose_ratio, prm), tau, prm)
    r_c = cleaner_recovery_pct(mass_pull_pct(feed_cu, prm), prm)
    return r_r * r_c / PCT


def conc_grade_pct(total_rec_pct: float, prm: Prm, feed_cu: float | None = None) -> float:
    gain = 0.0
    if feed_cu is not None and feed_cu > 0.0:
        gain = prm["flot_grade_pp_ln"] * math.log(feed_cu / prm["flot_grade_ref_pct"])
    g = prm["flot_conc0_pct"] - prm["flot_conc_slope"] * (total_rec_pct - prm["flot_rec_ref_pct"] - gain)
    return min(g, prm["flot_conc_max_pct"])


def tails_cu_pct(feed_cu: float, total_rec_pct: float, conc_cu: float) -> float:
    """Two-product tails, % Cu: g (1 - R) / (1 - y), y = g R / grade."""
    if feed_cu <= 0.0:
        return 0.0
    if conc_cu <= 0.0:
        return NO_VALUE
    r = total_rec_pct / PCT
    y = feed_cu * r / conc_cu
    if y >= 1.0:
        return NO_VALUE
    return feed_cu * (1.0 - r) / (1.0 - y)


def two_product(feed_cu: float, tail_cu: float, conc_cu: float) -> tuple[float, float]:
    """(recovery %, mass yield -) from grades; (NO_VALUE, NO_VALUE) when a grade is missing or c <= t."""
    f, t, c = feed_cu, tail_cu, conc_cu
    if not (valid(f) and valid(t) and valid(c)) or f <= 0.0 or c <= t:
        return NO_VALUE, NO_VALUE
    y = clamp((f - t) / (c - t), 0.0, 1.0)
    return clamp(PCT * c * y / f, 0.0, PCT), y


def recovery_sigma_pp(feed_cu: float, tail_cu: float, conc_cu: float, prm: Prm) -> float:
    """1 SD of the two-product recovery from analyser noise, pp (error propagation).

    dR/df = 100 c t / (f^2 (c - t)); dR/dt = -100 c (c - f) / (f (c - t)^2);
    dR/dc = -100 t (f - t) / (f (c - t)^2); sigmas relative per stream.
    """
    f, t, c = feed_cu, tail_cu, conc_cu
    if not (valid(f) and valid(t) and valid(c)) or f <= 0.0 or c <= t:
        return NO_VALUE
    d = c - t
    df = PCT * c * t / (f * f * d)
    dt = PCT * c * (c - f) / (f * d * d)
    dc = PCT * t * (f - t) / (f * d * d)
    sf = prm["sens_an_feed_sigma"] * f
    st = prm["sens_an_tail_sigma"] * t
    sc = prm["sens_an_conc_sigma"] * c
    return math.sqrt((df * sf) ** 2 + (dt * st) ** 2 + (dc * sc) ** 2)


def ascu_sigma_pp(prm: Prm) -> float:
    """1 SD of the expected total recovery from the block ASCu error, pp (slope x error)."""
    return prm["flot_jose_ascu"] * prm["blk_err_ascu_pp"]


# ---------------------------------------------------------------------------
# Copper and money
# ---------------------------------------------------------------------------
def cu_tph(q_tph: float, feed_cu: float, rec_pct: float) -> float:
    """Cu in concentrate, t/h: Q g R / 1e4."""
    if q_tph <= 0.0 or feed_cu <= 0.0 or rec_pct <= 0.0:
        return 0.0
    return q_tph * feed_cu * rec_pct / 1e4


def usd_h(cu_t_h: float, prm: Prm, price: float | None = None) -> float:
    """Gross payable value, USD/h: t Cu/h x payable share x LME price (not profit)."""
    p = prm["cu_price_usd_t"] if price is None else price
    return cu_t_h * prm["payable_frac"] * p


def usd_band(cu_t_h: float, prm: Prm) -> tuple[float, float]:
    """(low, high) USD/h over the LME band."""
    lo = usd_h(cu_t_h, prm, prm["cu_price_lo_usd_t"])
    hi = usd_h(cu_t_h, prm, prm["cu_price_hi_usd_t"])
    return (min(lo, hi), max(lo, hi))


def ore_class(axb: float, prm: Prm) -> str:
    """Ore class letter by A*b: M (soft) at or above 38, T (hard) below 30, else S."""
    if not valid(axb):
        return "С"
    if axb >= prm["ore_axb_soft_min"]:
        return "М"
    if axb < prm["ore_axb_hard_max"]:
        return "Т"
    return "С"
