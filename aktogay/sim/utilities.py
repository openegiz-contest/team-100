"""Utilities: power balance with grid limit and load shedding, water balance
with tailings pond and recycle regulator, money and CO2.

Design: section 3 rows 1, 13, 14; section 4 rows "water", "energy";
section 5 "money"; section 7 C2 (grid limit, load-shedding list).

Reference values (base, both lines):
  mills on shaft 134 MW, from grid 139.6 MW; crushers + conveyors 8.78 MW;
  other 54.6 MW site part (table value from 2024) + 2 x 28.5 MW line part
  (flotation, pebble crushing, regrind, pumps; off when the line stops);
  site 260.0 of 300 MW.
  C2: limit 218 MW -> shed ball-2b (21.4 MW grid) and 15 MW feeder; line
  control cuts SAG-2 to the one-ball rate (-13.6 MW) -> 210 MW, headroom 8 MW.
  Water: process 3.3 m3/t, tails pore water 0.31 m3/t (settled tails; the
  rest of the discharge water bleeds back to the pond), evaporation and
  seepage of the pond fitted on 2024, intake about 0.6 m3/t.

Units: power MW in balances (kW in PowerLoads), water m3/h and m3, time
model minutes, money USD, CO2 t. All numbers come from the ParamSet.
"""
from __future__ import annotations

import math

from .params import ParamSet
from .state import MIN_PER_H, PowerLoads, PowerState, ShedPlan, WaterFlows, WaterState, normal

# Load-shedding order (design section 7, C2): whole connections, first to last.
# "other_cat2" is the category-2 feeder of the other load (pow_shed_other_mw).
SAON_ORDER = ("ball-2b", "other_cat2", "ball-1b")
OTHER_FEEDER = "other_cat2"
BALL_PREFIX = "ball-"

KW_PER_MW = 1000.0


# ---------------------------------------------------------------------------
# Power
# ---------------------------------------------------------------------------
def to_grid_mw(shaft_mw: float, prm: ParamSet) -> float:
    """Grid-side MW of a mill drive for a shaft power in MW (shaft / pow_motor_eff)."""
    return shaft_mw / prm["pow_motor_eff"]


def _shed_list(pw: PowerState) -> list[str]:
    """pw.shed without duplicates, order kept; unknown names raise ValueError."""
    out = list(dict.fromkeys(pw.shed))
    for name in out:
        if name != OTHER_FEEDER and not name.startswith(BALL_PREFIX):
            raise ValueError("unknown shed connection: " + str(name))
    return out


def _kw_sum(values) -> float:
    """Sum of non-negative kW values (a unit never feeds power back)."""
    return sum(max(0.0, float(v)) for v in values)


def power_balance(pw: PowerState, loads: PowerLoads, prm: ParamSet) -> None:
    """Site power balance for one step; fills pw (all MW).

    grinding_shaft_mw = (sum sag_kw + sum ball_kw) / 1000, shed ball mills
      excluded (a disconnected drive draws nothing);
    grinding_mw = grinding_shaft_mw / pow_motor_eff (grid side);
    cc_mw = (sum crusher_kw + sum conveyor_kw) / 1000 (grid side);
    line_aux_mw = pow_line_aux_mw x lines whose SAG draws power (flotation, pebble
      crushing, regrind and pumps stop with the line: SAG STOP or RELINE draws 0);
    other_mw = pow_other_mw - (pow_shed_other_mw if "other_cat2" in pw.shed) + line_aux_mw;
    site_mw = grinding_mw + cc_mw + other_mw;
    shed_mw = grid MW of shed connections: ball mills at ball_power_mw / eff,
      the feeder at pow_shed_other_mw;
    headroom_mw = grid_limit_mw - site_mw;
    LIMITED when grid_limit_mw < pow_grid_limit_mw, pw.shed is not empty or
    headroom_mw < 0; else NORMAL.
    grid_limit_mw <= 0 means "not set": the normal limit pow_grid_limit_mw
    is written into pw.
    """
    if pw.grid_limit_mw <= 0.0:
        pw.grid_limit_mw = prm["pow_grid_limit_mw"]
    shed = _shed_list(pw)

    sag_kw = _kw_sum(loads.sag_kw.values())
    ball_kw = _kw_sum(v for k, v in loads.ball_kw.items() if k not in shed)
    pw.grinding_shaft_mw = (sag_kw + ball_kw) / KW_PER_MW
    pw.grinding_mw = to_grid_mw(pw.grinding_shaft_mw, prm)
    pw.cc_mw = (_kw_sum(loads.crusher_kw.values()) + _kw_sum(loads.conveyor_kw.values())) / KW_PER_MW

    feeder_mw = prm["pow_shed_other_mw"] if OTHER_FEEDER in shed else 0.0
    lines_on = sum(1 for v in loads.sag_kw.values() if v > 0.0)
    pw.line_aux_mw = lines_on * prm["pow_line_aux_mw"]
    pw.other_mw = max(0.0, prm["pow_other_mw"] - feeder_mw) + pw.line_aux_mw
    pw.site_mw = pw.grinding_mw + pw.cc_mw + pw.other_mw

    ball_grid_mw = to_grid_mw(prm["ball_power_mw"], prm)
    n_balls = sum(1 for name in shed if name.startswith(BALL_PREFIX))
    pw.shed_mw = n_balls * ball_grid_mw + feeder_mw
    pw.headroom_mw = pw.grid_limit_mw - pw.site_mw

    limited = pw.grid_limit_mw < prm["pow_grid_limit_mw"] or bool(shed) or pw.headroom_mw < 0.0
    pw.state = "LIMITED" if limited else "NORMAL"


def shed_plan(site_mw: float, grid_limit_mw: float, relief_mw: dict[str, float],
              prm: ParamSet) -> ShedPlan:
    """Load shedding for a grid limit, whole connections in SAON_ORDER.

    site_mw, grid_limit_mw: MW before shedding and the new limit.
    relief_mw: grid MW each candidate frees, computed by the plant: for a
    ball mill its own grid power plus the SAG cut that the line rule
    (comminution.line_feed_cap_tph) then makes; for "other_cat2"
    pow_shed_other_mw. Candidates missing from relief_mw, or freeing
    nothing (relief <= 0, e.g. the mill is already stopped), are skipped.
    Sheds in order until site_mw - sum(relief) <= grid_limit_mw or the
    list ends. Base C2: ball-2b frees 21.4 + 13.6, feeder 15 -> 200.5 MW.
    balls_off lists shed ball mills; other_shed_mw the feeder MW (its relief);
    sag_cap_kw stays empty (the plant caps a SAG only if headroom is
    still negative). Limit >= site_mw -> empty plan.
    prm is not read: the relief values already carry the parameters.
    """
    plan = ShedPlan()
    load = float(site_mw)
    for name in SAON_ORDER:
        if load <= grid_limit_mw:
            break
        r = relief_mw.get(name)
        if r is None or r <= 0.0:
            continue
        load -= r
        if name == OTHER_FEEDER:
            plan.other_shed_mw = float(r)
        else:
            plan.balls_off.append(name)
    return plan


def shed_names(plan: ShedPlan) -> list[str]:
    """Connections of a plan in SAON_ORDER, ready for PowerState.shed."""
    on = set(plan.balls_off)
    if plan.other_shed_mw > 0.0:
        on.add(OTHER_FEEDER)
    names = [n for n in SAON_ORDER if n in on]
    names += [n for n in plan.balls_off if n not in names]
    return names


def power_parts_text(pw: PowerState) -> str:
    """Site power by parts, MW, e.g. 'mills 139.6 + crushers and conveyors 8.8 + other 111.6 = 260.0 of 300 MW'."""
    return (f"mills {pw.grinding_mw:.1f} + crushers and conveyors {pw.cc_mw:.1f} + "
            f"other {pw.other_mw:.1f} = {pw.site_mw:.1f} of {pw.grid_limit_mw:.0f} MW")


# ---------------------------------------------------------------------------
# Water
# ---------------------------------------------------------------------------
def water_step(w: WaterState, fl: WaterFlows, dt_min: float, prm: ParamSet, z_piezo: float) -> None:
    """Water balance for one step of dt_min model minutes; fills w (m3/h, m3, kPa, %).

    proc = water_proc_m3_t * ore_tph (water to process, m3/h);
    tails_loss = water_tails_m3_t * tails_tph (pore water locked in settled tails);
    conc_moist = cake_tph * m / (100 - m) (leaves with the concentrate);
    thick_overflow from fl goes back to process (up to proc; any excess
      spills to the pond);
    pond_in = max(0, proc - overflow_used - conc_moist - tails_loss) + spill
      (free water of the tails; filtrate joins the tails stream);
    pond_return = regulator: pond_in - evap + (pond - mid) / pond_reg_h,
      mid = (pond_lo_m3 + pond_hi_m3) / 2, clamped to [0, proc - overflow_used],
      with a floor while the pond holds water: at least proc - overflow_used - water_intake_cap_m3h
      (what the fresh-water cap cannot supply), never more than the pond holds plus pond_in minus evaporation;
    evap = water_evap_m3h (fitted, includes seepage);
    pond water limits the step: evap and then pond_return never take more
      than the pond holds plus pond_in;
    leak = fl.leak_frac * pond_return (lost from the return pipeline, scenario water);
    recycle = pond_return - leak + overflow_used; demand = proc - recycle;
    intake = min(demand, water_intake_cap_m3h); short = demand - intake (process water
      missing: less water reaches the tails, pond_in falls by it; the plant cuts the ore;
      a short below 1e-6 m3/h is rounding and is set to 0);
    pond_m3 += (pond_in - pond_return - evap) * dt / 60;
    residual_pct = 100 * (intake - tails_loss - conc_moist - evap - leak - d(pond)/dt) / intake
      (0 when intake is 0); non-zero only when the inputs are not consistent;
    piezo_kpa = pond_piezo_kpa0 + pond_piezo_kpa_mm3 * (pond - pond_m3_0) / 1e6
                + pond_piezo_noise_kpa * z_piezo;
    state ALARM when piezo_kpa >= pond_piezo_sp_kpa, SHORT when short > 0, LOW when
    pond < pond_lo_m3, else NORMAL.
    """
    if dt_min < 0.0:
        raise ValueError("dt_min must be >= 0")
    m = float(fl.cake_moist_pct)
    if not 0.0 <= m < 100.0:
        raise ValueError("cake_moist_pct must be in [0, 100)")

    proc = prm["water_proc_m3_t"] * max(0.0, fl.ore_tph)
    tails_loss = prm["water_tails_m3_t"] * max(0.0, fl.tails_tph)
    conc_moist = max(0.0, fl.cake_tph) * m / (100.0 - m)
    overflow = max(0.0, fl.thick_overflow_m3h)
    overflow_used = min(overflow, proc)
    spill = overflow - overflow_used

    pond_in = max(0.0, proc - overflow_used - conc_moist - tails_loss) + spill

    # Recycle regulator: return what comes in net of evaporation, plus a
    # proportional term that pulls the pond to the middle of its band.
    evap_sp = prm["water_evap_m3h"]
    mid = 0.5 * (prm["pond_lo_m3"] + prm["pond_hi_m3"])
    cap = proc - overflow_used
    ret = pond_in - evap_sp + (w.pond_m3 - mid) / prm["pond_reg_h"]
    ret = min(max(ret, 0.0), cap)

    # Water present in the pond over this step limits evaporation, then pumping.
    if dt_min > 0.0:
        avail = pond_in + max(0.0, w.pond_m3) * MIN_PER_H / dt_min
    else:
        avail = math.inf if w.pond_m3 > 0.0 else pond_in
    evap = min(evap_sp, avail)
    ret = min(ret, max(0.0, avail - evap))
    # Floor of the regulator: while the pond holds water the plant is not left short of process water by the band logic. The fresh
    # water cap forces at least `cap - water_intake_cap_m3h` of return; without the floor a pond below the middle of its band (1 Mm3
    # in a 1.0-1.5 Mm3 band) made the regulator hold the water back and the plant cut the ore by 76 % (VALIDATION 9.4).
    if w.pond_m3 > 0.0:
        ret = max(ret, min(max(0.0, cap - prm["water_intake_cap_m3h"]), max(0.0, avail - evap)))

    # winter: part of the pond return does not reach the process (ice, frozen sections); it stays in the pond
    ret = ret * (1.0 - min(max(0.0, fl.winter_frac), 1.0))
    leak = min(max(0.0, fl.leak_frac), 1.0) * ret
    demand = max(0.0, cap - (ret - leak))
    intake_cap = prm["water_intake_cap_m3h"]
    intake = min(demand, intake_cap)
    short = demand - intake
    if short < 1e-6:                                 # rounding of the sums, not a deficit: the state must not read SHORT (E18)
        short = 0.0
    pond_in = max(0.0, pond_in - short)              # water the process did not get does not reach the tails
    rate = pond_in - ret - evap                      # d(pond)/dt, m3/h
    w.pond_m3 = max(0.0, w.pond_m3 + rate * dt_min / MIN_PER_H)

    residual = intake - tails_loss - conc_moist - evap - leak - rate
    w.proc_m3h = proc
    w.tails_loss_m3h = tails_loss
    w.conc_moist_m3h = conc_moist
    w.thick_overflow_m3h = overflow
    w.pond_in_m3h = pond_in
    w.pond_return_m3h = ret
    w.evap_m3h = evap
    w.recycle_m3h = ret - leak + overflow_used
    w.intake_m3h = intake
    w.leak_m3h = leak
    w.short_m3h = short
    w.demand_m3h = demand
    w.intake_cap_m3h = intake_cap
    w.residual_pct = 100.0 * residual / intake if intake > 0.0 else 0.0

    w.piezo_kpa = (prm["pond_piezo_kpa0"]
                   + prm["pond_piezo_kpa_mm3"] * (w.pond_m3 - prm["pond_m3_0"]) / 1e6
                   + prm["pond_piezo_noise_kpa"] * z_piezo)
    if w.piezo_kpa >= prm["pond_piezo_sp_kpa"]:
        w.state = "ALARM"
    elif short > 0.0:
        w.state = "SHORT"
    elif w.pond_m3 < prm["pond_lo_m3"]:
        w.state = "LOW"
    else:
        w.state = "NORMAL"


def is_winter(doy: float, prm: ParamSet) -> bool:
    """Winter by day of year (0-based): from season_winter_from_doy through the new year to season_winter_to_doy."""
    d = doy % 365.0
    return d >= prm["season_winter_from_doy"] or d <= prm["season_winter_to_doy"]


def weather(t_min: float, seed: int, winter: bool, dust: bool, prm: ParamSet,
            icy: bool = False) -> tuple[float, float, float]:
    """(air temperature degC, wind m/s, dry beach %) at model minute t_min: season mean and daily swing,
    hourly wind draw, dry beach by season; a dust spell sets wind and dry beach to the scenario values."""
    hour = (t_min % 1440.0) / 60.0
    mean = prm["wx_temp_winter_c"] if winter else prm["wx_temp_summer_c"]
    temp = mean + prm["wx_temp_amp_c"] * math.sin(2.0 * math.pi * (hour - 9.0) / 24.0)
    k = int(t_min // 60.0)
    wind = max(0.0, prm["wx_wind_mean_ms"] + prm["wx_wind_sigma_ms"] * normal(seed, k, "wind"))
    dry = prm["beach_dry_winter_pct"] if winter else prm["beach_dry_summer_pct"]
    if dust:
        wind = max(wind, prm["scen_dust_wind_ms"])
        dry = max(dry, prm["scen_dust_dry_pct"])
    if icy:                       # scenario icy: snowstorm spell on the haul roads (frost, strong wind)
        wind = max(wind, prm["scen_icy_wind_ms"])
        temp = min(temp, prm["scen_icy_temp_c"])
    return temp, wind, dry


# ---------------------------------------------------------------------------
# Money and CO2 (all values marked "model estimate" on screen)
# ---------------------------------------------------------------------------
def cu_value_usd(cu_t: float, prm: ParamSet) -> float:
    """Gross payable value of Cu in concentrate, USD: t * econ_payable_frac * econ_cu_price_usd_t."""
    return cu_t * prm["econ_payable_frac"] * prm["econ_cu_price_usd_t"]


def energy_cost_usd(mwh: float, prm: ParamSet) -> float:
    """Electricity cost, USD: MWh * 1000 * econ_power_kzt_kwh / econ_kzt_per_usd."""
    return mwh * KW_PER_MW * prm["econ_power_kzt_kwh"] / prm["econ_kzt_per_usd"]


def water_cost_usd(m3: float, prm: ParamSet) -> float:
    """Water intake cost, USD: m3 * econ_water_usd_m3."""
    return m3 * prm["econ_water_usd_m3"]


def co2_t(mwh: float, prm: ParamSet) -> float:
    """Grid CO2, t: MWh * econ_co2_t_mwh."""
    return mwh * prm["econ_co2_t_mwh"]


def value_usd(cu_t: float, mwh: float, m3: float, prm: ParamSet) -> float:
    """Value used in counters cum_usd, USD: Cu value - energy cost - water cost.

    Linear in all inputs, so differences of counters (fact - base) may be negative.
    """
    return cu_value_usd(cu_t, prm) - energy_cost_usd(mwh, prm) - water_cost_usd(m3, prm)
