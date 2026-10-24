"""Ore path: pit block queue, block-model error, excavators, fleet, haul,
crusher pocket, belt, stockpile (draw column + sides) and ore batches.

Design: section 3 rows 2, 3, 4, 6, 7, 16, "Ore batches", "Stockpile is not
FIFO"; section 4 rows "pit, conveyor", "fleet", "block-model error";
section 7 C1 (stockpile 3 h 00 min), C3 (hard block, 50/50 blend),
C4 (stockpile fills while the SAG is down).

Material moves as Parcel(batch_id, tonnes, t_ready_min):
  dig -> pit.haul[line] (ready after pit_haul_min) -> crusher.pocket
  -> conveyor.belt (ready after conv_transit_min) -> stockpile column/sides
  -> SAG feed (reclaim_step).
Mass is conserved at every node; tests check it.

Randomness only through sim.state.u01 / normal / rng_at with stream names
"blk-est", "blk-err", "fleet"; step argument = block number or model hour.

Plant call order per step and line (see sim.plant):
  plan_step, fleet_step, mining_targets, dig_step, pocket_avail_tph,
  [comminution.crusher_step], convey_step, feed_props,
  [comminution.sag_step], reclaim_step; batches_step once per step.

Batch state follows the trailing edge of its ore, so a batch is where its
last tonne is: DIG from the first dug tonne while any of it is still in the
pit, BELT when all of it is dug and some is still on the haul road, in the
crusher pocket or on the belt, IN_STOCK when all of it has reached the
stockpile, DONE by weigher accounting (cum_out_t >= stock_mark_t, the batch
fully dug and nothing of it in transit). States never go back. The first
tonnes of a batch reach the stockpile and the SAG while the excavator still
digs it; the published pit_t (t still in the pit) and tonnes_left (t not
yet fed, weigher accounting) tell the split.

Stockpile column and sides are dicts batch id -> t. When a DONE batch is
deleted (batches_step) its ore usually still lies in the pile (ideal
mixing never empties a batch); that ore is kept under a key
"rest|cu|ascu|axb|bwi" whose name carries the true props of the merged
remainder, so mass and props survive without the batch thing.
"""
from __future__ import annotations

import math

from . import haul
from .params import ParamSet
from .state import (MIN_PER_H, NO_VALUE, Batch, OreProps, Parcel, PlantState, StockpileState,
                    base_ore, batch_name, normal, u01)

# Numerical tolerances, not model parameters.
_EPS_T = 1e-9        # t: smaller masses are treated as zero
_EPS_TPH = 1e-6      # t/h: smaller flows are treated as zero

REST_PREFIX = "rest|"   # stockpile key of ore left by deleted batches

_STATE_ORDER = {"PLANNED": 0, "DIG": 1, "BELT": 2, "IN_STOCK": 3, "DONE": 4}


# ---------------------------------------------------------------------------
# Ore properties
# ---------------------------------------------------------------------------
def bwi_from_axb(axb: float, prm: ParamSet) -> float:
    """Bond work index from A*b, kWh/t: linear through (ore_axb_base, ore_bwi_base)
    and (ore_axb_hard, ore_bwi_hard), never below 0."""
    a0, w0 = prm["ore_axb_base"], prm["ore_bwi_base"]
    a1, w1 = prm["ore_axb_hard"], prm["ore_bwi_hard"]
    if a1 == a0:
        return max(0.0, w0)
    return max(0.0, w0 + (w1 - w0) * (axb - a0) / (a1 - a0))


def blend(parts: list[tuple[float, OreProps]]) -> OreProps:
    """Mass-weighted blend of (tonnes, props).

    cu_pct, ascu_pct (weighted by Cu tonnes for ASCu), bwi: mass-weighted
    mean; axb: mass-weighted harmonic mean (averages DWi). Zero total mass
    -> OreProps() with zeros. Parts with tonnes <= 0 are ignored; the blend
    is associative, so blends of blends give the same result.
    """
    m = cu_t = ascu_cu = ascu_m = bwi_m = 0.0
    m_axb = inv_axb = 0.0
    for t, p in parts:
        if t <= 0.0:
            continue
        m += t
        cu_t += t * p.cu_pct
        ascu_cu += t * p.cu_pct * p.ascu_pct
        ascu_m += t * p.ascu_pct
        bwi_m += t * p.bwi
        if p.axb > 0.0:
            m_axb += t
            inv_axb += t / p.axb
    if m <= 0.0:
        return OreProps()
    ascu = ascu_cu / cu_t if cu_t > 0.0 else ascu_m / m
    axb = m_axb / inv_axb if inv_axb > 0.0 else 0.0
    return OreProps(cu_t / m, ascu, axb, bwi_m / m)


def plan_walk(seed: int, block_no: int, prm: ParamSet) -> tuple[float, float, float]:
    """Slow mine-plan noise at a block: three unit-variance values (Cu, A*b, ASCu), smooth between knots
    blk_plan_len_blocks apart (smoothstep between normal draws of stream "blk-plan"), so neighbouring blocks share them."""
    length = max(1.0, prm["blk_plan_len_blocks"])
    k = int(block_no // length)
    f = (block_no % length) / length
    w = f * f * (3.0 - 2.0 * f)
    norm = math.sqrt((1.0 - w) ** 2 + w ** 2)
    return tuple(((1.0 - w) * normal(seed, k, "blk-plan", j) + w * normal(seed, k + 1, "blk-plan", j)) / norm
                 for j in range(3))


def draw_block(seed: int, block_no: int, prm: ParamSet) -> tuple[OreProps, OreProps]:
    """Block-model estimate and truth for block block_no; returns (est, true).

    Lognormal factors have mean 1: LN1(s) = exp(s z - s^2 / 2), so the mean of
    the draws is the table mean (only the clamps shift it, by < 0.1 %).
    est: axb = blk_axb_mean * LN1(blk_axb_cv) clamped to [blk_axb_lo, blk_axb_hi];
         cu = blk_cu_mean_pct * LN1(blk_cu_cv) clamped to blk_cu_mean_pct * [blk_cu_lo_frac,
              blk_cu_hi_frac] (0.33-0.50 % Cu at 0.41 %; the band follows the year grade);
         ascu = blk_ascu_mean_pct + blk_ascu_sd_pp * N, >= 0; bwi = bwi_from_axb(axb).
    true: axb = est.axb * LN1(blk_err_axb_sigma); cu = est.cu * LN1(blk_err_cu_sigma);
          ascu = est.ascu + blk_err_ascu_pp * N (>= 0); bwi = bwi_from_axb(true.axb).
    Streams "blk-est" and "blk-err" with step = block_no; k = 0 axb, 1 cu, 2 ascu.
    Units: cu % Cu, ascu % of total Cu, axb -, bwi kWh/t.
    """
    def z(stream: str, k: int) -> float:
        return normal(seed, block_no, stream, k)

    def ln1(sigma: float, stream: str, k: int) -> float:
        return math.exp(sigma * z(stream, k) - 0.5 * sigma * sigma)

    f_axb = f_cu = 1.0
    d_ascu = 0.0
    if prm["blk_plan_on"] > 0.5:                       # mine-plan variability: slow, shared by neighbouring blocks
        x = plan_walk(seed, block_no, prm)
        s_cu, s_axb = prm["blk_plan_sigma_cu"], prm["blk_plan_sigma_axb"]
        f_cu = math.exp(s_cu * x[0] - 0.5 * s_cu * s_cu)
        f_axb = math.exp(s_axb * x[1] - 0.5 * s_axb * s_axb)
        d_ascu = prm["blk_plan_sigma_ascu_pp"] * x[2]
    axb = _clamp(prm["blk_axb_mean"] * f_axb * ln1(prm["blk_axb_cv"], "blk-est", 0),
                 prm["blk_axb_lo"], prm["blk_axb_hi"])
    cu_mean = prm["blk_cu_mean_pct"]
    cu = _clamp(cu_mean * f_cu * ln1(prm["blk_cu_cv"], "blk-est", 1),
                cu_mean * prm["blk_cu_lo_frac"], cu_mean * prm["blk_cu_hi_frac"])
    ascu = max(0.0, prm["blk_ascu_mean_pct"] + d_ascu + prm["blk_ascu_sd_pp"] * z("blk-est", 2))
    est = OreProps(cu, ascu, axb, bwi_from_axb(axb, prm))

    t_axb = axb * ln1(prm["blk_err_axb_sigma"], "blk-err", 0)
    t_cu = cu * ln1(prm["blk_err_cu_sigma"], "blk-err", 1)
    t_ascu = max(0.0, ascu + prm["blk_err_ascu_pp"] * z("blk-err", 2))
    true = OreProps(t_cu, t_ascu, t_axb, bwi_from_axb(t_axb, prm))
    return est, true


# ---------------------------------------------------------------------------
# Pit, fleet, batches
# ---------------------------------------------------------------------------
def new_batch(st: PlantState, line: int, est: OreProps, true: OreProps, prm: ParamSet,
              tag: str = "") -> Batch:
    """Create batch-NNNN (PLANNED, location "pit", tonnes pit_block_t), register it
    in st.batches, append to st.pit.plan[line], advance counters
    (st.next_batch_no and st.pit.next_block_no)."""
    b = _make_batch(st, line, est, true, prm["pit_block_t"], tag, st.pit.next_block_no)
    st.pit.next_block_no += 1
    st.pit.plan[line].append(b.batch_id)
    return b


def plan_step(st: PlantState, prm: ParamSet) -> list[Batch]:
    """Keep pit_plan_h hours of blocks per line in the plan at the current target rate.

    Rate = pit.target_tph[line], t/h, or cal_line_tph while the target is 0
    (the plan is not dropped when a crusher stops). At the run start (no
    block drawn yet) an empty plan begins with the face being dug at the
    snapshot: one pit_block_t block of base ore (state.base_ore, estimate =
    truth, tag "initial", block number 0), like the stockpile, haul road and
    belt of initial_state. New blocks from draw_block(st.seed,
    st.pit.next_block_no), line 1 first. Updates pit.plan_text (e.g.
    "L1: 0012 M, 0013 T; L2: ..."; M soft, S medium, T hard by est A*b and
    ui_axb_soft / ui_axb_hard), pit.hard_in_plan (est axb < ui_axb_hard).
    Returns new batches.
    """
    new: list[Batch] = []
    fresh = st.pit.next_block_no == 1
    for n in _lines(st):
        if fresh and not st.pit.plan[n]:
            face = base_ore(prm)
            b = _make_batch(st, n, face, face, prm["pit_block_t"], "initial", 0)
            st.pit.plan[n].append(b.batch_id)
            new.append(b)
        need = prm["pit_plan_h"] * _plan_rate(st, n, prm)
        have = _plan_tonnes(st, n)
        while have < need:
            est, true = draw_block(st.seed, st.pit.next_block_no, prm)
            b = new_batch(st, n, est, true, prm)
            new.append(b)
            have += b.tonnes
    _refresh_plan(st, prm)
    return new


def inject_block(st: PlantState, line: int, est: OreProps, true: OreProps, lead_h: float,
                 prm: ParamSet, tag: str = "hard") -> Batch:
    """Scenario block: insert into the plan of `line` so that digging starts
    about lead_h hours from now at the current target rate.

    Tonnes ahead = lead_h * rate (rate as in plan_step). When that point
    falls inside a planned block, the block is cut there: the excavator
    leaves the face, digs the scenario block and comes back; the rest of
    the cut block becomes a continuation batch (same block number and
    props) right after the scenario block. The scenario block (pit_block_t,
    block number 0) does not use a block number, so the random block
    sequence stays the same as in a copy without the scenario.
    """
    plan = st.pit.plan[line]
    ahead = max(0.0, lead_h) * _plan_rate(st, line, prm)
    hb = _make_batch(st, line, est, true, prm["pit_block_t"], tag, 0)
    idx = len(plan)
    cum = 0.0
    for i, bid in enumerate(plan):
        x = st.batches[bid]
        rem = _remaining(x)
        if cum + rem > ahead + _EPS_T:
            cut = ahead - cum
            if cut <= _EPS_T:
                idx = i
            else:
                old = x.tonnes
                x.tonnes = x.dug_t + cut
                if x.stock_mark_t != NO_VALUE:
                    x.stock_mark_t -= old - x.tonnes
                if x.state == "PLANNED" or x.stock_mark_t == NO_VALUE:
                    x.tonnes_left = x.tonnes
                _settle(st, x)
                c = _make_batch(st, line, x.est, x.true, old - x.tonnes, x.tag, x.block_no)
                plan.insert(i + 1, c.batch_id)
                idx = i + 1
            break
        cum += rem
    plan.insert(idx, hb.batch_id)
    _refresh_plan(st, prm)
    return hb


def fleet_step(st: PlantState, prm: ParamSet) -> None:
    """Fleet once per model hour (fleet_redraw_h): which trucks are ready, and the ore haul.

    Each truck is ready when u01(seed, model hour, "fleet", k) < fleet_kio (k = truck index),
    so every plant copy sees the same trucks. With a truck roster (st.trucks, site file):
    haul_tph = sum over ready ore trucks of payload * 60 / cycle, cycle = haul.cycle_min of the truck's route
    (load + haul loaded + queue + dump + return from the map distance, sim/haul.py; x pit_road_detour while the
    ramp of the truck's line is CLOSED); without a roster the aggregate trucks_ready * fleet_payload_t * 60 / the
    mean ore cycle of fleet_trucks trucks.
    exc_total / exc_ready count ore and stripping excavators; truck_kio_shift = shift mean
    of the ready share (shifts start cal_shift_start_h, length cal_shift_h);
    SHORT when haul_tph < sum of pit.target_tph, else NORMAL.
    """
    fl = st.fleet
    period_min = prm["fleet_redraw_h"] * MIN_PER_H
    period = int(math.floor(st.clock.t_min / period_min))
    trucks = st.trucks
    fl.trucks_total = len(trucks) if trucks else int(prm["fleet_trucks"])
    all_exc = st.excavators + st.waste_excavators
    fl.exc_total = len(all_exc)
    fl.exc_ready = sum(1 for e in all_exc if e.state != "DOWN")
    if period != fl.last_draw_h:
        kio = prm["fleet_kio"]
        if trucks:
            for tr in trucks:
                tr.ready = u01(st.seed, period, "fleet", tr.k) < kio
            ready = sum(1 for tr in trucks if tr.ready)
        else:
            ready = sum(1 for k in range(fl.trucks_total) if u01(st.seed, period, "fleet", k) < kio)
        shift_now = _shift_index(period * period_min, prm)
        if fl.last_draw_h < 0 or _shift_index(fl.last_draw_h * period_min, prm) != shift_now:
            fl.kio_sum = 0.0
            fl.kio_n = 0
        fl.kio_sum += ready / fl.trucks_total if fl.trucks_total > 0 else 0.0
        fl.kio_n += 1
        fl.truck_kio_shift = fl.kio_sum / fl.kio_n
        fl.trucks_ready = ready
        fl.last_draw_h = period
    if trucks:
        trip = {n: haul.cycle_min(prm, n) for n in set(tr.line for tr in trucks if tr.duty == "ore")}
        total = 0.0
        rm = {n: route_mult(st, n, prm) for n in trip}
        for tr in trucks:
            if tr.ready and tr.duty == "ore":
                total += tr.payload_t * MIN_PER_H / (trip[tr.line] * rm[tr.line])
        fl.haul_tph = total
    else:
        fl.haul_tph = fl.trucks_ready * prm["fleet_payload_t"] * MIN_PER_H / haul.mean_ore_cycle_min(prm)
    fl.state = "SHORT" if fl.haul_tph < sum(st.pit.target_tph.values()) - _EPS_TPH else "NORMAL"


def route_mult(st: PlantState, line: int, prm: ParamSet) -> float:
    """Cycle multiplier of the route to the crusher of `line` (0: waste dump): pit_road_detour while
    a road of that route is CLOSED, else 1; times the weather / restriction multiplier of the haul roads (st.pit.cycle_mult)."""
    for rd in st.roads.values():
        if rd.line == line and rd.state == "CLOSED":
            return prm["pit_road_detour"] * st.pit.cycle_mult
    return st.pit.cycle_mult


def mining_targets(st: PlantState, prm: ParamSet) -> dict[int, float]:
    """Stockpile regulator: target dig rate per line, t/h; stores st.pit.target_tph.

    base = cal_line_tph (pit plan rate; the dispatcher does not follow
    short SAG changes, so in C4 the stockpile fills and in C2 it rises);
    level < stock_reg_low_frac * live -> excavator maximum for that line,
    max(base, pit_exc_max_tph * excavators not DOWN / number of lines);
    level > stock_reg_high_frac * live -> base scaled linearly to 0 at full
    (stock_full_frac, the FULL state, so excavators are IDLE while FULL);
    crusher STOP or crusher fault -> 0 (excavators of that line go IDLE).
    """
    base = prm["cal_line_tph"]
    live = prm["stock_live_t"]
    lo, hi = prm["stock_reg_low_frac"], prm["stock_reg_high_frac"]
    full = prm["stock_full_frac"]
    ready = sum(1 for e in st.excavators if e.state != "DOWN")
    top = max(base, prm["pit_exc_max_tph"] * ready / max(1, len(st.lines)))
    out: dict[int, float] = {}
    for ln in st.lines:
        cr = ln.crusher
        if cr is not None and (cr.state == "STOP" or cr.fault or ln.conveyor.fault):
            t = 0.0
        else:
            frac = ln.stockpile.level_t / live if live > 0 else 1.0
            if frac < lo:
                t = top
            elif frac > hi:
                t = base * max(0.0, (full - frac) / (full - hi)) if hi < full else 0.0
            else:
                t = base
        out[ln.n] = t
    st.pit.target_tph = dict(out)
    return out


def dig_step(st: PlantState, targets: dict[int, float], dt_min: float, prm: ParamSet) -> dict[int, float]:
    """Dig ore; returns dug t/h per line.

    exc-1 serves line 1, exc-2 line 2 (each up to pit_exc_max_tph); exc-3
    (and any further excavator) time-shares the unmet targets of both lines
    in proportion (its `line` = the larger share, kept on a tie); excavators
    with nothing to dig are IDLE, DOWN ones dig 0 (DOWN ends at
    down_until_min); total <= fleet.haul_tph (cut pro rata). Tonnes come
    from the first plan batch of the line (state DIG, t_dig_min); a fully
    dug batch leaves the plan. With pit.blend[line] the hard batch (est
    A*b < ui_axb_hard) is dug together with a soft partner (tag "blend",
    est/true axb = ore_axb_blend, Cu and ASCu at the block means, block
    number 0) in shares ore_blend_frac / (1 - ore_blend_frac). Parcels go
    to pit.haul[line] with t_ready = now + pit_haul_min. Sets excavator
    state/tph/block/line, fleet.mining_tph, fleet.state and pit.mining_tph,
    pit.state.
    """
    now = st.clock.t_min
    lines = _lines(st)
    cap = prm["pit_exc_max_tph"]
    for e in st.excavators:
        if e.state == "DOWN" and e.down_until_min != NO_VALUE and now >= e.down_until_min:
            e.state = "IDLE"
            e.down_until_min = NO_VALUE

    want: dict[int, float] = {}
    for n in lines:
        w = max(0.0, float(targets.get(n, 0.0)))
        want[n] = min(w, _plan_tonnes(st, n) * MIN_PER_H / dt_min) if dt_min > 0 else 0.0

    rate: dict[str, dict[int, float]] = {e.name: {} for e in st.excavators}
    got = {n: 0.0 for n in lines}
    swing = []
    for e in st.excavators:
        if e.state == "DOWN":
            continue
        home = _home_line(e, lines)
        if home is None:
            swing.append(e)
            continue
        r = max(0.0, min(cap, want[home] - got[home]))
        rate[e.name][home] = r
        got[home] += r
    if swing:
        unmet = {n: max(0.0, want[n] - got[n]) for n in lines}
        u_tot = sum(unmet.values())
        if u_tot > 0.0:
            k = min(1.0, cap * len(swing) / u_tot)
            for n in lines:
                part = unmet[n] * k
                got[n] += part
                for e in swing:
                    rate[e.name][n] = rate[e.name].get(n, 0.0) + part / len(swing)

    total = sum(got.values())
    haul = st.fleet.haul_tph
    if total > haul:
        f = haul / total if total > 0.0 else 0.0
        got = {n: v * f for n, v in got.items()}
        for r in rate.values():
            for n in r:
                r[n] *= f

    last: dict[int, str] = {n: "" for n in lines}
    for n in lines:
        if got[n] > 0.0 and dt_min > 0:
            dug, last[n] = _dig_line(st, n, got[n] * dt_min / MIN_PER_H, now, prm)
            got[n] = dug * MIN_PER_H / dt_min
    total = sum(got.values())

    for e in st.excavators:
        if e.state == "DOWN":
            e.tph = 0.0
            e.block = ""
            continue
        r = rate[e.name]
        home = _home_line(e, lines)
        if home is not None:
            e.line = home
        elif r:
            best = max(lines, key=lambda n: r.get(n, 0.0))
            if r.get(best, 0.0) > r.get(e.line, 0.0):
                e.line = best
        e.tph = sum(r.values())
        if e.tph > _EPS_TPH:
            e.state = "DIG"
            e.block = last.get(e.line, "") or (st.pit.plan[e.line][0] if st.pit.plan.get(e.line) else "")
        else:
            e.tph = 0.0
            e.state = "IDLE"
            e.block = ""

    st.pit.mining_tph = total
    st.pit.state = "RUN" if total > _EPS_TPH else "STOP"
    st.fleet.mining_tph = total
    need = sum(max(0.0, float(v)) for v in targets.values())
    st.fleet.state = "SHORT" if haul < need - _EPS_TPH else "NORMAL"
    return got


def pocket_avail_tph(st: PlantState, line: int, dt_min: float) -> float:
    """Move arrived haul parcels (t_ready <= now) to the crusher pocket;
    returns pocket tonnes * 60 / dt, t/h."""
    now = st.clock.t_min
    haul = st.pit.haul[line]
    pocket = st.line(line).crusher.pocket
    if haul:
        keep = []
        for p in haul:
            if p.t_ready_min <= now:
                _append_parcel(pocket, p.batch_id, p.tonnes, p.t_ready_min, merge_any_time=True)
            else:
                keep.append(p)
        haul[:] = keep
    if dt_min <= 0:
        return 0.0
    return sum(p.tonnes for p in pocket) * MIN_PER_H / dt_min


def stock_room_tph(st: PlantState, line: int, dt_min: float, prm: ParamSet) -> float:
    """Room left in the stockpile this step, t/h:
    (stock_live_t - level - ore on the belt) * 60 / dt + current out_tph, never below 0.
    Ore already on the belt lands on the pile anyway, so it is counted here;
    then the level never runs above stock_live_t while the SAG draw holds."""
    if dt_min <= 0:
        return 0.0
    ln = st.line(line)
    sp = ln.stockpile
    on_belt = sum(p.tonnes for p in ln.conveyor.belt)
    return max(0.0, (prm["stock_live_t"] - sp.level_t - on_belt) * MIN_PER_H / dt_min + sp.out_tph)


def convey_step(st: PlantState, line: int, crusher_tph: float, dt_min: float, prm: ParamSet) -> float:
    """Crusher pocket -> belt -> stockpile; returns t/h delivered to the stockpile.

    Takes crusher_tph * dt / 60 from the pocket (FIFO) onto the belt with
    t_ready = now + conv_transit_min; parcels with t_ready <= now go to the
    stockpile: new ore enters the column first (column limit
    stock_column_frac * stock_live_t); when the column is over its size the
    mixed excess spills to the sides. Sets stockpile.in_tph (delivered),
    cum_in_t, level_t, state. Conveyor: tph = crusher_tph, RUN with conv_power_mw
    when crusher_tph > 0; else STOP with 0 kW and the belt does not move
    (every belt parcel t_ready += dt, nothing delivered), so in C1 the
    stockpile inflow is 0 at once and hours_left reads 3 h 00 min.
    Batch states DIG / BELT / IN_STOCK and locations by _settle (the last
    tonne of the batch, see the module docstring); stock_mark_t set on first arrival (cum_in_t before arrival + batch
    tonnes, weigher accounting) and never below cum_in_t after its latest
    parcel (batches dug side by side in a blend).
    """
    ln = st.line(line)
    cv, sp = ln.conveyor, ln.stockpile
    now = st.clock.t_min
    if dt_min <= 0:
        return 0.0
    if crusher_tph <= 0.0:
        cv.state = "STOP"
        cv.tph = 0.0
        cv.power_kw = 0.0
        for p in cv.belt:
            p.t_ready_min += dt_min
        sp.in_tph = 0.0
        _update_level(sp, prm)
        return 0.0

    loaded = _take_fifo(ln.crusher.pocket, crusher_tph * dt_min / MIN_PER_H)
    t_ready = now + prm["conv_transit_min"]
    for p in loaded:
        _append_parcel(cv.belt, p.batch_id, p.tonnes, t_ready)
        b = st.batches.get(p.batch_id)
        if b is not None and b.t_belt_min == NO_VALUE:
            b.t_belt_min = now
    cv.state = "RUN"
    cv.tph = sum(p.tonnes for p in loaded) * MIN_PER_H / dt_min
    cv.power_kw = prm["conv_power_mw"] * 1000.0

    delivered = 0.0
    if cv.belt:
        keep = []
        for p in cv.belt:
            if p.t_ready_min <= now:
                _arrive(st, sp, p, now)
                delivered += p.tonnes
            else:
                keep.append(p)
        cv.belt[:] = keep
    for b in st.batches.values():
        if b.line == line and b.state in ("DIG", "BELT"):
            _settle(st, b)
    size = _column_size(prm)
    excess = _total(sp.column) - size
    if excess > _EPS_T:
        _add(sp.sides, _take(sp.column, excess))
    sp.in_tph = delivered * MIN_PER_H / dt_min
    _update_level(sp, prm)
    return sp.in_tph


def feed_props(st: PlantState, line: int) -> OreProps:
    """True ore blend the SAG draws now: the column (whole pile when level is below
    the column size). Zero level -> props of the last feed (sag.feed_ore)."""
    ln = st.line(line)
    sp = ln.stockpile
    src = sp.column if _total(sp.column) > _EPS_T else sp.sides
    if _total(src) > _EPS_T:
        return blend([(t, _props_of(st, k)) for k, t in src.items()])
    return ln.sag.feed_ore.copy() if ln.sag is not None else OreProps()


def stock_available_tph(st: PlantState, line: int, dt_min: float) -> float:
    """Ore the stockpile can deliver this step, t/h: level * 60 / dt."""
    if dt_min <= 0:
        return 0.0
    return max(0.0, st.line(line).stockpile.level_t) * MIN_PER_H / dt_min


def reclaim_step(st: PlantState, line: int, out_tph: float, dt_min: float, prm: ParamSet) -> OreProps:
    """Draw SAG feed from the column and exchange column <-> sides; returns true props drawn.

    Draw = min(out_tph * dt / 60, level), t, from the ideally mixed column
    (the sides only when the column is short). Exchange: sides and column
    swap m = (1 - exp(-dt / tau)) * C * S / (C + S) tonnes, tau =
    stock_exchange_tau_h, so the composition difference decays with time
    constant tau and neither mass changes; then the column is refilled from
    the sides up to its size. Updates level_t, out_tph, cum_out_t,
    hours_left (level / (out - in) when falling, else NO_VALUE), state
    (EMPTY <= stock_empty_t, LOW < stock_low_frac, FULL >= stock_full_frac).
    Batch accounting by weigher: tonnes_left falls FIFO by arrival; DONE when
    cum_out_t >= stock_mark_t (t_done_min, location line-N); t_sag_min when
    a batch first appears in the feed; axb_soft of the largest batch in the
    draw = sag.axb_soft. Zero draw returns feed_props.
    """
    ln = st.line(line)
    sp = ln.stockpile
    now = st.clock.t_min
    if dt_min <= 0:
        return feed_props(st, line)
    level = _total(sp.column) + _total(sp.sides)
    want = min(max(0.0, out_tph) * dt_min / MIN_PER_H, level)
    drawn: dict[str, float] = {}
    if want > 0.0:
        c = _total(sp.column)
        drawn = _take(sp.column, min(want, c))
        if want - c > _EPS_T:
            _add(drawn, _take(sp.sides, want - c))
    drawn_t = _total(drawn)
    props = blend([(t, _props_of(st, k)) for k, t in drawn.items()]) if drawn_t > 0.0 \
        else feed_props(st, line)
    sp.cum_out_t += drawn_t
    sp.out_tph = drawn_t * MIN_PER_H / dt_min

    c, s = _total(sp.column), _total(sp.sides)
    if c > _EPS_T and s > _EPS_T:
        m = (1.0 - math.exp(-dt_min / (prm["stock_exchange_tau_h"] * MIN_PER_H))) * c * s / (c + s)
        to_sides = _take(sp.column, m)
        to_column = _take(sp.sides, m)
        _add(sp.column, to_column)
        _add(sp.sides, to_sides)
    gap = _column_size(prm) - _total(sp.column)
    if gap > _EPS_T and _total(sp.sides) > _EPS_T:
        _add(sp.column, _take(sp.sides, min(gap, _total(sp.sides))))

    _update_level(sp, prm)
    net = sp.out_tph - sp.in_tph
    sp.hours_left = sp.level_t / net if net > _EPS_TPH else NO_VALUE

    if drawn_t > 0.0:
        top_id, top_t = "", 0.0
        for k, t in drawn.items():
            b = st.batches.get(k)
            if b is None:
                continue
            if b.t_sag_min == NO_VALUE and t > _EPS_T:
                b.t_sag_min = now
            if t > top_t:
                top_id, top_t = k, t
        if top_id:
            sp.feed_batch = top_id               # the laboratory sample of the feed is booked to it
        if top_id and ln.sag is not None and ln.sag.axb_soft != NO_VALUE:
            st.batches[top_id].axb_soft = ln.sag.axb_soft
    _weigher(st, line, now)
    return props


def stockpile_label(sp: StockpileState, prm: ParamSet) -> str:
    """State label from level: EMPTY (<= stock_empty_t), FULL (>= stock_full_frac * live),
    LOW (< stock_low_frac * live), NORMAL."""
    live = prm["stock_live_t"]
    if sp.level_t <= prm["stock_empty_t"]:
        return "EMPTY"
    if sp.level_t >= prm["stock_full_frac"] * live:
        return "FULL"
    if sp.level_t < prm["stock_low_frac"] * live:
        return "LOW"
    return "NORMAL"


def batches_step(st: PlantState, prm: ParamSet) -> list[Batch]:
    """Remove DONE batches older than cal_batch_keep_h; returns removed batches.

    Ore of a removed batch still in its stockpile moves to the "rest|..."
    key of that column / sides (props merged with blend), so the pile keeps
    its mass and true props.
    """
    keep_min = prm["cal_batch_keep_h"] * MIN_PER_H
    now = st.clock.t_min
    # a laboratory result arrives sens_lab_delay_h after its sample: the batch it belongs to stays
    # until then and cal_batch_keep_h after it, so its cu_meas is seen at all
    pending = {r.batch_id for ln in st.lines if getattr(ln, "lab", None) is not None for r in ln.lab.pending}
    gone = [b for b in st.batches.values()
            if b.state == "DONE" and b.t_done_min != NO_VALUE and now - b.t_done_min >= keep_min
            and b.batch_id not in pending and (b.t_lab_min == NO_VALUE or now - b.t_lab_min >= keep_min)]
    for b in gone:
        sp = st.line(b.line).stockpile if 1 <= b.line <= len(st.lines) else None
        if sp is not None:
            for d in (sp.column, sp.sides):
                if b.batch_id in d:
                    _fold_rest(d, b.batch_id, b.true)
        for plan in st.pit.plan.values():
            if b.batch_id in plan:
                plan.remove(b.batch_id)
        del st.batches[b.batch_id]
    return gone


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _lines(st: PlantState) -> list[int]:
    return [ln.n for ln in st.lines]


def _shift_index(t_min: float, prm: ParamSet) -> int:
    return int(math.floor((t_min - prm["cal_shift_start_h"] * MIN_PER_H) / (prm["cal_shift_h"] * MIN_PER_H)))


def _column_size(prm: ParamSet) -> float:
    """Draw column above the feeders, t."""
    return prm["stock_column_frac"] * prm["stock_live_t"]


def _remaining(b: Batch) -> float:
    return max(0.0, b.tonnes - b.dug_t)


def _plan_tonnes(st: PlantState, line: int) -> float:
    return sum(_remaining(st.batches[bid]) for bid in st.pit.plan[line])


def _plan_rate(st: PlantState, line: int, prm: ParamSet) -> float:
    r = st.pit.target_tph.get(line, 0.0)
    return r if r > 0.0 else prm["cal_line_tph"]


def _is_hard(b: Batch, prm: ParamSet) -> bool:
    return b.est.axb < prm["ui_axb_hard"]


def _ore_class(axb: float, prm: ParamSet) -> str:
    if axb < prm["ui_axb_hard"]:
        return "T"
    if axb >= prm["ui_axb_soft"]:
        return "M"
    return "S"


def _refresh_plan(st: PlantState, prm: ParamSet) -> None:
    parts = []
    hard = False
    for n in sorted(st.pit.plan):
        items = []
        for bid in st.pit.plan[n]:
            b = st.batches[bid]
            cls = _ore_class(b.est.axb, prm)
            hard = hard or cls == "T"
            items.append(f"{bid.rsplit('-', 1)[-1]} {cls}")
        parts.append(f"L{n}: " + ", ".join(items))
    st.pit.plan_text = "; ".join(parts)
    st.pit.hard_in_plan = hard


def _make_batch(st: PlantState, line: int, est: OreProps, true: OreProps, tonnes: float,
                tag: str, block_no: int) -> Batch:
    """Register a PLANNED batch (not put into the plan)."""
    bid = batch_name(st.next_batch_no)
    st.next_batch_no += 1
    b = Batch(bid, int(block_no), line, float(tonnes), est.copy(), true.copy(),
              tonnes_left=float(tonnes), t_created_min=st.clock.t_min, tag=tag)
    st.batches[bid] = b
    return b


def _advance(b: Batch, state: str) -> bool:
    """Move the batch forward to `state`; False when it is already there or further."""
    if _STATE_ORDER[state] > _STATE_ORDER.get(b.state, 0):
        b.state = state
        return True
    return False


def _settle(st: PlantState, b: Batch) -> None:
    """State and location of a batch from its last tonne (see the module docstring); DONE is the weigher's."""
    if b.state == "DONE" or b.dug_t <= _EPS_T:
        return
    if b.dug_t < b.tonnes - _EPS_T:
        target, where = "DIG", "pit"
    elif _in_transit(st, b.line, b.batch_id) or b.stock_mark_t == NO_VALUE:
        target, where = "BELT", f"conveyor-{b.line}"
    else:
        target, where = "IN_STOCK", f"stockpile-{b.line}"
    if _advance(b, target):
        b.location = where


def _home_line(e, lines: list[int]) -> int | None:
    """Line an excavator is dedicated to (exc-N -> line N), None for swing units."""
    try:
        k = int(e.name.rsplit("-", 1)[-1])
    except ValueError:
        return None
    return k if k in lines else None


def _append_parcel(queue: list[Parcel], bid: str, tonnes: float, t_ready: float,
                   merge_any_time: bool = False) -> None:
    if tonnes <= 0.0:
        return
    if queue and queue[-1].batch_id == bid and (merge_any_time or queue[-1].t_ready_min == t_ready):
        queue[-1].tonnes += tonnes
        return
    queue.append(Parcel(bid, tonnes, t_ready))


def _take_fifo(queue: list[Parcel], amount: float) -> list[Parcel]:
    """Remove `amount` t from the front of a parcel queue; returns the removed parcels."""
    out: list[Parcel] = []
    left = amount
    while queue and left > _EPS_T:
        p = queue[0]
        if p.tonnes <= left + _EPS_T:
            out.append(queue.pop(0))
            left -= p.tonnes
        else:
            out.append(Parcel(p.batch_id, left, p.t_ready_min))
            p.tonnes -= left
            left = 0.0
    return out


def _dig_batch(st: PlantState, line: int, b: Batch, tonnes: float, now: float, prm: ParamSet) -> None:
    if tonnes <= 0.0:
        return
    b.dug_t += tonnes
    if _advance(b, "DIG"):
        b.location = "pit"
        if b.t_dig_min == NO_VALUE:
            b.t_dig_min = now
    _append_parcel(st.pit.haul[line], b.batch_id, tonnes, now + prm["pit_haul_min"])
    _settle(st, b)


def _partner(st: PlantState, line: int, hard: Batch, prm: ParamSet) -> Batch:
    """Soft partner dug together with a hard batch (plan position right after it)."""
    plan = st.pit.plan[line]
    if len(plan) > 1:
        q = st.batches[plan[1]]
        if q.tag == "blend" and _remaining(q) > _EPS_T:
            return q
    f = prm["ore_blend_frac"]
    axb = prm["ore_axb_blend"]
    props = OreProps(prm["blk_cu_mean_pct"], prm["blk_ascu_mean_pct"], axb, bwi_from_axb(axb, prm))
    q = _make_batch(st, line, props, props, _remaining(hard) * (1.0 - f) / f, "blend", 0)
    plan.insert(1, q.batch_id)
    _refresh_plan(st, prm)
    return q


def _dig_line(st: PlantState, line: int, tonnes: float, now: float, prm: ParamSet) -> tuple[float, str]:
    """Dig `tonnes` t from the plan of a line; returns (dug t, id of the main batch dug)."""
    plan = st.pit.plan[line]
    f = prm["ore_blend_frac"]
    use_blend = bool(st.pit.blend.get(line)) and 0.0 < f < 1.0
    left = tonnes
    last = ""
    changed = False
    while left > _EPS_T and plan:
        b = st.batches[plan[0]]
        if _remaining(b) <= _EPS_T:
            plan.pop(0)
            changed = True
            continue
        if use_blend and _is_hard(b, prm):
            q = _partner(st, line, b, prm)
            th = min(_remaining(b), left * f)
            tq = min(_remaining(q), left * (1.0 - f))
            _dig_batch(st, line, b, th, now, prm)
            _dig_batch(st, line, q, tq, now, prm)
            left -= th + tq
            last = b.batch_id
            if _remaining(q) <= _EPS_T:
                plan.remove(q.batch_id)
                changed = True
            if _remaining(b) <= _EPS_T:
                plan.remove(b.batch_id)
                changed = True
            if th + tq <= _EPS_T:
                break
        else:
            t = min(_remaining(b), left)
            _dig_batch(st, line, b, t, now, prm)
            left -= t
            last = b.batch_id
            if _remaining(b) <= _EPS_T:
                plan.pop(0)
                changed = True
    if changed:
        _refresh_plan(st, prm)
    return tonnes - left, last


def _total(d: dict[str, float]) -> float:
    return sum(d.values())


def _add(d: dict[str, float], parts: dict[str, float]) -> None:
    for k, v in parts.items():
        if v > 0.0:
            d[k] = d.get(k, 0.0) + v


def _take(d: dict[str, float], amount: float) -> dict[str, float]:
    """Remove `amount` t from an ideally mixed node in proportion to its content;
    returns the removed parts. Remainders below _EPS_T go with the removed parts."""
    tot = _total(d)
    if amount <= 0.0 or tot <= 0.0:
        return {}
    if amount >= tot:
        out = dict(d)
        d.clear()
        return out
    f = amount / tot
    out: dict[str, float] = {}
    for k in list(d):
        v = d[k]
        x = v * f
        rest = v - x
        if rest > _EPS_T:
            d[k] = rest
            out[k] = x
        else:
            out[k] = v
            del d[k]
    return out


def _rest_key(p: OreProps) -> str:
    return REST_PREFIX + "|".join(repr(float(x)) for x in (p.cu_pct, p.ascu_pct, p.axb, p.bwi))


def _rest_props(key: str) -> OreProps:
    cu, ascu, axb, bwi = (float(x) for x in key[len(REST_PREFIX):].split("|"))
    return OreProps(cu, ascu, axb, bwi)


def _props_of(st: PlantState, key: str) -> OreProps:
    """True props of a stockpile entry (live batch or merged remainder)."""
    b = st.batches.get(key)
    if b is not None:
        return b.true
    if key.startswith(REST_PREFIX):
        return _rest_props(key)
    raise KeyError("stockpile entry without props: " + key)


def _fold_rest(d: dict[str, float], bid: str, props: OreProps) -> None:
    """Merge the ore of batch `bid` and earlier remainders of node `d` into one rest entry."""
    parts = [(d.pop(bid), props)]
    for k in [k for k in d if k.startswith(REST_PREFIX)]:
        parts.append((d.pop(k), _rest_props(k)))
    tot = sum(t for t, _ in parts)
    if tot > 0.0:
        key = _rest_key(blend(parts))
        d[key] = d.get(key, 0.0) + tot


def _arrive(st: PlantState, sp: StockpileState, p: Parcel, now: float) -> None:
    """Belt parcel lands on top of the draw column; weigher counts it."""
    cum0 = sp.cum_in_t
    sp.column[p.batch_id] = sp.column.get(p.batch_id, 0.0) + p.tonnes
    sp.cum_in_t += p.tonnes
    b = st.batches.get(p.batch_id)
    if b is None:
        return
    if b.stock_mark_t == NO_VALUE:
        b.stock_mark_t = cum0 + b.tonnes
    else:
        b.stock_mark_t = max(b.stock_mark_t, sp.cum_in_t)
    if b.t_stock_min == NO_VALUE:
        b.t_stock_min = now


def _update_level(sp: StockpileState, prm: ParamSet) -> None:
    sp.level_t = _total(sp.column) + _total(sp.sides)
    sp.state = stockpile_label(sp, prm)


def _in_transit(st: PlantState, line: int, bid: str) -> bool:
    ln = st.line(line)
    for q in (st.pit.haul[line], ln.crusher.pocket, ln.conveyor.belt):
        for p in q:
            if p.batch_id == bid:
                return True
    return False


def _weigher(st: PlantState, line: int, now: float) -> None:
    """Weigher (FIFO) accounting of batches on one stockpile: tonnes_left and DONE."""
    sp = st.line(line).stockpile
    out = sp.cum_out_t
    for b in st.batches.values():
        if b.line != line or b.state == "DONE" or b.stock_mark_t == NO_VALUE:
            continue
        fed = _clamp(out - (b.stock_mark_t - b.tonnes), 0.0, b.tonnes)
        b.tonnes_left = b.tonnes - fed
        if (out >= b.stock_mark_t - _EPS_T and b.dug_t >= b.tonnes - _EPS_T
                and not _in_transit(st, line, b.batch_id)):
            b.state = "DONE"
            b.location = f"line-{line}"
            b.tonnes_left = 0.0
            b.t_done_min = now
