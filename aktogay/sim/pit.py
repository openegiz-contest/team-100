"""Pit twins on top of the aggregated ore path: trucks, faces, haul roads, stripping.

Keep it light (no truck physics): ore.fleet_step decides which trucks are
ready and gives the ore haul in t/h from the ready ore trucks; this module only
names what each truck, face and road is doing, so the twins of the pit show
the same picture as the aggregated rates.

Truck cycle (sim/haul.py: load + haul loaded + queue + dump + return from the map distance of the route, x
pit_road_detour on a closed ramp), phases in order:
  LOADING fleet_load_min at the face, HAUL_FULL on the road, QUEUE fleet_queue_min
  and DUMP (body raise + lower + positioning) at the crusher (ore) or the dump end of the waste road,
  RETURN on the road; haul and return share the rest of the cycle in the proportion of the route (loaded_share).
  A truck not ready this hour is DOWN; an ore truck whose line digs nothing
  (pit.target_tph 0: crusher stopped, stockpile full) waits in QUEUE at its crusher.
Faces: ACTIVE while their excavator digs, block and block-model grade and
  hardness of the batch being dug (estimates, visible to modules).
Stripping excavators dig waste at pit_exc_waste_tph, held to the haul of the
  ready waste trucks (shared equally).
Roads: CLOSED while a road scenario holds them; trucks_on counts trucks hauling
  or returning on them.

Drill rigs and dozers (bort numbers of the company list of 29.02.2024): see drill_step.

Units: minutes, t, t/h. Randomness: truck readiness comes from ore.fleet_step; drill rigs and
dozers have their own hourly draws (streams "drill", "dozer"), so no other draw changes.
"""
from __future__ import annotations

from . import haul
from .params import ParamSet
from .state import MIN_PER_H, NO_VALUE, PlantState, u01
from .ore import route_mult

_EPS = 1e-9

PHASES = ("LOADING", "HAUL_FULL", "QUEUE", "DUMP", "RETURN")


def truck_phase(t_min: float, phase_min: float, cycle_min: float, prm: ParamSet, loaded_share: float = 0.5) -> str:
    """Phase of a running truck at t_min in a cycle of cycle_min minutes starting at -phase_min.

    loaded_share: part of the driving time spent loaded (0.5: both ways equal, the former rule)."""
    load, queue, dump = prm["fleet_load_min"], prm["fleet_queue_min"], haul.dump_min(prm)
    road = max(0.0, cycle_min - load - queue - dump)
    x = (t_min + phase_min) % cycle_min if cycle_min > 0.0 else 0.0
    for name, length in zip(PHASES, (load, road * loaded_share, queue, dump, road * (1.0 - loaded_share))):
        if x < length - _EPS:
            return name
        x -= length
    return "RETURN"


def _road_of(st: PlantState, line: int) -> str:
    for rd in st.roads.values():
        if rd.line == line:
            return rd.name
    return ""


def _face_of_line(st: PlantState, line: int) -> str:
    """Face that loads the trucks of a crusher line: the face of the excavator digging for it."""
    best, best_tph = "", -1.0
    for e in st.excavators:
        if e.line == line and e.state == "DIG" and e.tph > best_tph:
            best, best_tph = e.name, e.tph
    for f in st.faces.values():
        if f.excavator == best:
            return f.name
    return next((f.name for f in st.faces.values() if f.kind == "ore"), "")


def pit_step(st: PlantState, prm: ParamSet, t_min: float) -> None:
    """Trucks, stripping excavators, faces and roads at t_min (after ore.dig_step)."""
    # roads: a closure ends by itself
    for rd in st.roads.values():
        if rd.state == "CLOSED" and rd.closed_until_min != NO_VALUE and t_min >= rd.closed_until_min - _EPS:
            rd.state = "OPEN"
            rd.closed_until_min = NO_VALUE
        rd.trucks_on = 0
    waste_faces = [f.name for f in st.faces.values() if f.kind == "waste"]
    ore_face = {n: _face_of_line(st, n) for n in (ln.n for ln in st.lines)}
    roads = {n: _road_of(st, n) for n in list(ore_face) + [0]}
    waste_haul = 0.0
    wi = 0
    rm = {n: route_mult(st, n, prm) for n in set(tr.line for tr in st.trucks)}      # once per step, not per truck
    base = {n: haul.cycle_min(prm, n) for n in rm}
    share = {n: haul.loaded_share(prm, n) for n in rm}
    for tr in st.trucks:
        cycle = base[tr.line] * rm[tr.line]
        tr.cycle_min = cycle
        if not tr.ready:
            tr.state, tr.location, tr.load_t = "DOWN", "", 0.0
            continue
        if tr.duty == "waste":
            waste_haul += tr.payload_t * MIN_PER_H / cycle
            face = waste_faces[wi % len(waste_faces)] if waste_faces else ""
            wi += 1
            end = roads.get(0, "")
        else:
            face = ore_face.get(tr.line, "")
            end = f"crusher-{tr.line}"
            if st.pit.target_tph.get(tr.line, 0.0) <= 0.0:
                tr.state, tr.location, tr.load_t = "QUEUE", end, 0.0
                continue
        ph = truck_phase(t_min, tr.phase_min, cycle, prm, share[tr.line])
        tr.state = ph
        road = roads.get(tr.line if tr.duty == "ore" else 0, "")
        if ph == "LOADING":
            tr.location, tr.load_t = face, 0.0
        elif ph in ("HAUL_FULL", "RETURN"):
            tr.location = road
            tr.load_t = tr.payload_t if ph == "HAUL_FULL" else 0.0
            if road in st.roads:
                st.roads[road].trucks_on += 1
        else:                                   # QUEUE, DUMP at the crusher or the dump end of the road
            tr.location, tr.load_t = end, tr.payload_t
    # stripping excavators share the waste haul
    wex = [e for e in st.waste_excavators if e.state != "DOWN"]
    share = waste_haul / len(wex) if wex else 0.0
    for e in st.waste_excavators:
        if e.state == "DOWN":
            e.tph = 0.0
            continue
        e.tph = min(prm["pit_exc_waste_tph"], share)
        e.state = "DIG" if e.tph > 0.0 else "IDLE"
        e.block = ""
    # faces follow their excavator; the excavator takes blasted rock
    dt = st.clock.dt_min
    exc = {e.name: e for e in st.excavators + st.waste_excavators}
    for f in st.faces.values():
        e = exc.get(f.excavator)
        if e is None:
            f.state, f.block, f.tph = "IDLE", "", 0.0
            continue
        f.state = "DOWN" if e.state == "DOWN" else ("ACTIVE" if e.state == "DIG" and e.tph > 0.0 else "IDLE")
        f.tph = e.tph if f.state == "ACTIVE" else 0.0
        f.block = e.block if f.kind == "ore" else ""
        f.blasted_t = max(0.0, f.blasted_t - f.tph * dt / MIN_PER_H)
    drill_step(st, prm, t_min, dt)


def drill_step(st: PlantState, prm: ParamSet, t_min: float, dt_min: float) -> None:
    """Drill rigs and dozers. The blasted stock of a face limits the dig only in the scenario drill:N (sim/ore.py);
    the dozer of the waste dump lengthens the waste truck cycle only in the scenario dozer (sim/ore.py, route_mult).

    A rig is ready when u01(seed, model hour, "drill", k) < pit_drill_kio; a ready rig drills
    pit_drill_holes_shift holes per shift on its face, each hole a cycle of shift / holes minutes that
    starts with pit_drill_move_min of MOVING; every hole adds pit_drill_t_hole of blasted rock to the
    face. IDLE while the face holds pit_face_blasted_max_t. Dozers: ready (stream "dozer", same share)
    -> WORK at their place, else DOWN.
    """
    if not st.drills and not st.dozers:
        return
    hour = int(t_min // MIN_PER_H)
    kio = prm["pit_drill_kio"]
    shift_min = prm["cal_shift_h"] * MIN_PER_H
    s_idx = int((t_min - prm["cal_shift_start_h"] * MIN_PER_H) // shift_min)
    holes = prm["pit_drill_holes_shift"]
    cycle = shift_min / holes if holes > 0 else shift_min
    for d in st.drills:
        if d.ready_hour != hour:                  # the draw is hourly: same value for every step of the hour
            d.ready, d.ready_hour = u01(st.seed, hour, "drill", d.k) < kio, hour
        if d.shift_idx != s_idx:
            d.shift_idx, d.holes_shift = s_idx, 0.0
        face = st.faces.get(d.face)
        until = st.flags.get("drill_until", NO_VALUE)
        held = until != NO_VALUE and t_min < until and d.face == f"face-{int(st.flags.get('drill_line', 0))}"
        if not d.ready or held:
            d.state = "DOWN"
        elif face is not None and face.blasted_t >= prm["pit_face_blasted_max_t"]:
            d.state = "IDLE"
        else:
            x = (t_min + prm["pit_drill_move_min"] * d.k) % cycle      # rigs out of step with each other
            d.state = "MOVING" if x < prm["pit_drill_move_min"] else "DRILLING"
            rate = dt_min / cycle                                    # holes in this step
            d.holes_shift += rate
            if face is not None:
                face.blasted_t += rate * prm["pit_drill_t_hole"]
    until = st.flags.get("dozer_until", NO_VALUE)
    dozer_held = until != NO_VALUE and t_min < until
    for z in st.dozers:
        if z.ready_hour != hour:
            z.ready, z.ready_hour = u01(st.seed, hour, "dozer", z.k) < kio, hour
        z.state = "DOWN" if dozer_held and z.place == "road-dump" else ("WORK" if z.ready else "DOWN")


def waste_tph(st: PlantState) -> float:
    """Stripping rate now, t/h."""
    return sum(e.tph for e in st.waste_excavators)


def stop_drills(st: PlantState, line: int, until_min: float, left_t: float) -> str:
    """Scenario drill:N: the rigs of the ore face of `line` stand until until_min, the face keeps at most left_t of
    blasted rock, and while the scenario holds its excavator digs only blasted rock (sim/ore.py, dig step)."""
    face = f"face-{line}"
    if face not in st.faces:
        return ""
    st.faces[face].blasted_t = min(st.faces[face].blasted_t, left_t)
    st.flags["drill_line"] = float(line)
    st.flags["drill_until"] = float(until_min)
    return face


def blast_limited(st: PlantState, exc_name: str) -> bool:
    """True when the excavator stands on the face of the scenario drill:N and its blasted rock is used up."""
    until = st.flags.get("drill_until", NO_VALUE)
    if until == NO_VALUE or st.clock.t_min >= until:
        return False
    f = st.faces.get(f"face-{int(st.flags.get('drill_line', 0))}")
    return f is not None and f.excavator == exc_name and f.blasted_t <= _EPS


def close_road(st: PlantState, line: int, until_min: float) -> str:
    """Close the road of a crusher line (scenario road:N) until until_min; returns its id or ""."""
    name = _road_of(st, line)
    if name:
        rd = st.roads[name]
        rd.state = "CLOSED"
        rd.closed_until_min = float(until_min)
    return name
