"""Tier T (24.10.2026): eight slow equipment troubles with a monitored signal (scenario only, never drawn in free run).

  gmd:N    air gap of the gearless drive of SAG N closes: feed held back, then the protection trips the drive
  idler:N  bearing of a conveyor idler overheats: fire risk, then the belt is stopped (the usual belt trip)
  froth:N  the level of the flotation cells oscillates: recovery falls while it lasts
  rake:N   rake torque of the thickener grows: rakes buried, the thickener keeps about 60 % of its throughput
  cloth:N  filter cloth blinds: the cycle gets longer, the capacity of the filter falls
  slurry:N the cyclone feed pump cavitates / its impeller wears: head and feed fall
  brake    brake oil of the truck HT141 (CAT 793D) overheats: the truck is throttled, then taken off the haul
  track    track tension of the shovel EX01 (EX3600) grows: the travel stops automatically, the shovel cannot walk

Every unit has one signal that moves from its healthy value to an alert value in `rise_h`, then to a critical value in
`fail_h`. Nobody called: at the critical value the consequence comes (units without a cliff just hold the effect). A call
(Plant.call -> wear_call) books the person: after the arrival and `fix_h` the signal is healthy again. Everything here is
O(number of open items); with no item the step costs one dict test.
"""
from __future__ import annotations

from .state import MIN_PER_H, NO_VALUE

EPS = 1e-6

# kind -> (thing template, feature, signal keys ok/alert/crit, timing keys rise/fail/fix, repair key or "", node kind label)
SPEC = {
    "gmd": ("sag-{n}", "gmd_gap_mm", ("w_gmd_gap_ok_mm", "w_gmd_gap_alert_mm", "w_gmd_gap_crit_mm"),
            ("w_gmd_rise_h", "w_gmd_fail_h", "w_gmd_fix_h"), "w_gmd_repair_h"),
    "idler": ("conveyor-{n}", "idler_temp_c", ("w_idler_temp_ok_c", "w_idler_temp_alert_c", "w_idler_temp_crit_c"),
              ("w_idler_rise_h", "w_idler_fail_h", "w_idler_fix_h"), ""),
    "froth": ("flot-{n}", "level_swing_pct", ("w_froth_swing_ok_pct", "w_froth_swing_alert_pct", "w_froth_swing_alert_pct"),
              ("w_froth_rise_h", "", "w_froth_fix_h"), ""),
    "rake": ("thick-{n}", "rake_torque_pct", ("w_rake_torque_ok_pct", "w_rake_torque_alert_pct", "w_rake_torque_crit_pct"),
             ("w_rake_rise_h", "w_rake_fail_h", "w_rake_fix_h"), "w_rake_repair_h"),
    "cloth": ("filter-{n}", "cycle_pct", ("w_cloth_cycle_ok_pct", "w_cloth_cycle_alert_pct", "w_cloth_cycle_crit_pct"),
              ("w_cloth_rise_h", "w_cloth_fail_h", "w_cloth_fix_h"), ""),
    "slurry": ("cyclones-{n}", "pump_head_pct", ("w_slurry_head_ok_pct", "w_slurry_head_alert_pct", "w_slurry_head_crit_pct"),
               ("w_slurry_rise_h", "w_slurry_fail_h", "w_slurry_fix_h"), ""),
    "brake": ("fleet", "brake_oil_c", ("w_brake_oil_ok_c", "w_brake_oil_alert_c", "w_brake_oil_crit_c"),
              ("w_brake_rise_h", "w_brake_fail_h", "w_brake_fix_h"), "w_brake_repair_h"),
    "track": ("exc-1", "track_press_pct", ("w_track_press_ok_pct", "w_track_press_alert_pct", "w_track_press_crit_pct"),
              ("w_track_rise_h", "w_track_fail_h", "w_track_fix_h"), "w_track_repair_h"),
}
KINDS = tuple(SPEC)
SITE_KINDS = ("brake", "track")                      # tokens without a line number
LINE_KINDS = tuple(k for k in KINDS if k not in SITE_KINDS)
# thing type -> (kind, feature); the feature is read for every thing of the type (a healthy value without an item)
SIGNAL_TYPES = {"sag": "gmd", "conveyor": "idler", "flot": "froth", "thick": "rake", "filter": "cloth",
                "cyclones": "slurry", "fleet": "brake", "exc": "track"}
BRAKE_BORT = "HT141"
_NODE_RU = {"gmd": "sag", "idler": "conveyor", "froth": "flot", "rake": "thick", "cloth": "filter", "slurry": "cyclones",
            "brake": "fleet", "track": "exc-1"}


def key_of(kind: str, n: int) -> str:
    return kind if kind in SITE_KINDS else f"{kind}:{n}"


def node_of(kind: str, n: int) -> str:
    return SPEC[kind][0].format(n=n)


def _row(prm, key: str) -> float:
    return prm[key]


def value(prm, kind: str, item: dict, t: float) -> float:
    """Signal of an item at model minute t: ok -> alert in rise_h, alert -> crit in fail_h, then held."""
    _th, _ft, (k_ok, k_al, k_cr), (k_rise, k_fail, _kfix), _rep = SPEC[kind]
    ok, al, cr = prm[k_ok], prm[k_al], prm[k_cr]
    h = max(0.0, (t - item["t0"]) / MIN_PER_H)
    rise = prm[k_rise]
    if h <= rise:
        return ok + (al - ok) * h / rise
    fail = prm[k_fail] if k_fail else 0.0
    if fail <= 0.0 or cr == al:
        return al
    return al + (cr - al) * min(1.0, (h - rise) / fail)


def start(plant, kind: str, n: int, t0: float, fix_h: float | None = None) -> None:
    plant.state.wear[key_of(kind, n)] = {"t0": float(t0), "fix": NO_VALUE, "failed": 0.0,
                                         "fix_h": float(fix_h) if fix_h else NO_VALUE, "v": NO_VALUE}


def fix_hours(plant, kind: str, item: dict) -> float:
    return item["fix_h"] if item.get("fix_h", NO_VALUE) != NO_VALUE else plant.prm[SPEC[kind][3][2]]


def call(plant, kind: str, n: int, t: float) -> bool:
    """The person is called: the fix is done after the arrival and the work (a call after the consequence shortens its repair)."""
    from . import events as ev
    item = plant.state.wear.get(key_of(kind, n))
    if item is None:
        return False
    when = t + ev.arrival_min(plant.state.seed, kind, plant.prm) + fix_hours(plant, kind, item) * MIN_PER_H
    if kind == "idler" and item["failed"]:
        return False                                   # the belt stands: the belt crew is the one to call
    if item["fix"] == NO_VALUE or when < item["fix"]:
        item["fix"] = when
        if kind == "track" and item["failed"]:
            for ex in plant.state.excavators:
                if ex.name == node_of("track", 0) and ex.state == "DOWN":
                    ex.down_until_min = when
    return True


def issue_at(st, node: str) -> tuple[str, int] | None:
    """Open item whose node is `node`: (kind, line) for Plant._issue_at (a tripped belt is the belt crew's call, not the idler's)."""
    for key, item in st.wear.items():
        kind, _, rest = key.partition(":")
        n = int(rest) if rest else 0
        if node_of(kind, n) == node and not (item["failed"] and kind == "idler"):
            return kind, n
    return None


def active(st, kind: str, n: int) -> bool:
    return key_of(kind, n) in st.wear


def clear(plant) -> None:
    """Scenario cancel: every item is dropped, the effects are neutral again."""
    st = plant.state
    for key, item in list(st.wear.items()):
        if key.startswith("track") and item["failed"]:
            for ex in st.excavators:
                if ex.name == node_of("track", 0) and ex.state == "DOWN":
                    ex.state, ex.down_until_min = "IDLE", NO_VALUE
    st.wear.clear()
    plant._wq.clear()
    plant._wmult = 1.0


def _ramp(x: float, lo: float, hi: float) -> float:
    if hi == lo:
        return 0.0
    return min(1.0, max(0.0, (x - lo) / (hi - lo)))


def step(plant, t: float) -> None:
    """Advance the open items (called by Plant.step when there are any): signals, effects, consequences, fixes."""
    st, p = plant.state, plant.prm
    wq: dict[int, list[float]] = {}
    mult = 1.0
    for key, item in list(st.wear.items()):
        kind, _, rest = key.partition(":")
        n = int(rest) if rest else 0
        if item["fix"] != NO_VALUE and t >= item["fix"] - EPS:
            del st.wear[key]                                # the unit is whole again
            continue
        if kind == "idler" and item["failed"]:
            if not st.line(n).conveyor.fault:               # the belt crew repaired the belt: the idler is changed with it
                del st.wear[key]
            else:
                item["v"] = p[SPEC["idler"][2][2]]
            continue
        v = value(p, kind, item, t)
        item["v"] = v
        _th, _ft, (k_ok, k_al, k_cr), (k_rise, k_fail, _kf), k_rep = SPEC[kind]
        ok, al, cr = p[k_ok], p[k_al], p[k_cr]
        h = (t - item["t0"]) / MIN_PER_H
        due = k_fail != "" and h >= p[k_rise] + p[k_fail] - EPS and item["fix"] == NO_VALUE and not item["failed"]
        e = wq.setdefault(n, [1.0, 0.0, 1.0])               # [feed factor, recovery loss pp, filter capacity factor]
        if kind == "gmd":
            if due:
                item["failed"], item["fix"] = 1.0, t + p[k_rep] * MIN_PER_H
            e[0] *= 0.0 if item["failed"] else 1.0 - p["w_gmd_derate"] * _ramp(v, ok, al)
        elif kind == "idler":
            if due:
                cv = st.line(n).conveyor
                item["failed"] = 1.0
                cv.fault = "scenario"
                plant._register_loud(f"conveyor:{n}", t)
        elif kind == "froth":
            e[1] += p["w_froth_pp"] * _ramp(v, ok, al)
        elif kind == "rake":
            if due:
                item["failed"], item["fix"] = 1.0, t + p[k_rep] * MIN_PER_H
            e[0] *= p["w_rake_q_frac"] if item["failed"] else 1.0
        elif kind == "cloth":
            e[2] *= ok / v if v > 0.0 else 1.0
        elif kind == "slurry":
            e[0] *= 1.0 - p["w_slurry_q_frac"] * _ramp(v, ok, cr)
        elif kind == "brake":
            if due:
                item["failed"], item["fix"] = 1.0, t + p[k_rep] * MIN_PER_H
            share = 1.0 if item["failed"] else p["w_brake_share"] * _ramp(v, ok, al)
            mult *= 1.0 + share / max(1, st.fleet.trucks_total)
        elif kind == "track":
            if due:
                item["failed"], item["fix"] = 1.0, t + p[k_rep] * MIN_PER_H
                for ex in st.excavators:
                    if ex.name == node_of("track", 0):
                        ex.state, ex.tph, ex.block = "DOWN", 0.0, ""
                        ex.down_until_min = item["fix"]
    plant._wq = {n: tuple(v) for n, v in wq.items() if v != [1.0, 0.0, 1.0]}
    plant._wmult = mult


def _line_of(tid: str) -> int:
    tail = tid.rsplit("-", 1)[-1]
    digits = ""
    for ch in tail:
        if not ch.isdigit():
            break
        digits += ch
    return int(digits) if digits else 0


_BRAKE_THING: list[str] = []


def _brake_thing() -> str:
    """Thing id of the truck HT141 (the bort of the equipment list), cached."""
    if not _BRAKE_THING:
        from .params import default
        from .state import site
        _BRAKE_THING.append(site().fatigue_truck(default())[0])
    return _BRAKE_THING[0]


def signals(st, tid: str, typ: str) -> dict:
    """Features of tier T for a thing (healthy value when no item is open). Imported by sensors.thing."""
    from .params import TABLE
    kind = SIGNAL_TYPES[typ]
    feat = SPEC[kind][1]
    if kind == "track":
        from .state import site
        if tid not in getattr(site(), "OIL_SENSOR", ()):
            return {feat: NO_VALUE}                       # the pressure is shown for the shovel whose brochure confirms it
    n = 0 if kind in SITE_KINDS else _line_of(tid)
    item = st.wear.get(key_of(kind, n))
    ok = TABLE[SPEC[kind][2][0]].value
    v = ok if item is None or item.get("v", NO_VALUE) == NO_VALUE else item["v"]
    out = {feat: round(v, 3)}
    if kind == "brake":
        out["brake_truck"] = _brake_thing()
    return out
