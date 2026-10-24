"""Truck cycle from a calculation: load + haul loaded + queue + dump + return, per route.

Until 24.10.2026 the cycle was one constant (fleet_trip_min = 30 min). Now it is built from parts:

  load    fleet_load_min at the shovel (assumption; EX3600-6 bucket 21-23 m3, 2 700-3 700 t/h of the press tour)
  haul    loaded, up the ramp: distance from the stand's map (plan.json: face -> ramp polyline -> crusher,
          OSM quarry and crusher, our drawn ramp; label "расчёт по карте") divided by the loaded speed
  queue   fleet_queue_min at the crusher or the dump (assumption)
  dump    body raise + lower of the CAT 793D (Specalog AEHQ5600-01 p. 20: 20.25 s and 17.51 s, vendor) + fleet_spot_min
  return  empty, distance / fleet_v_empty_kmh (assumption)

Loaded speed on the ramp is power limited: v = eta P / (m g (grade + rolling resistance)) with P = 1 801 kW gross and
the loaded mass = (gross machine weight 383.7 t - nominal payload 218 t) + payload (CAT 793D Specalog p. 1 and 20, vendor).
eta (drive train) is an assumption: 0.89 reproduces the 12.9 km/h on 10 % that the 793F brochure prints. The grade is
the rise (bench number x 10 m, assumption) over the measured length. The retarding and rimpull charts of the Specalog are
images (pp. 23-24): they were not read as numbers, so the speed on grade is calculated, not read. Everything the formula
leaves out (curves, acceleration, speed limits, dust, dispatch waiting) is one factor fleet_speed_eff, the ONE assumption
that is calibrated: its value makes the mean cycle of the two ore routes equal to the 30 min that kept the 2025 throughput
fit (python -I aktogay/run.py haul --calibrate). The 785 and 777 trucks use the cycle of the 793D (same power-to-weight
class, assumption).

  fleet capacity, t/h = ready ore trucks x payload x 60 / cycle (sim/ore.fleet_step)
"""
from __future__ import annotations

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sim.params import ParamSet, default  # noqa: E402

G = 9.80665
KMH = 3.6
REF_CYCLE_MIN = 30.0                 # the 2025 fit was made with this cycle: the target of the calibration
ROUTES = (1, 2, 0)                   # ore line 1, ore line 2, waste dump


def _route_keys(line: int) -> tuple[str, str]:
    if line == 1:
        return "fleet_ramp_km_1", "fleet_rise_m_1"
    if line == 2:
        return "fleet_ramp_km_2", "fleet_rise_m_2"
    return "fleet_waste_km", "fleet_rise_m_w"


def grade(prm: ParamSet, line: int) -> float:
    """Mean grade of the loaded haul, rise over length (fraction)."""
    km, rise = _route_keys(line)
    return prm[rise] / (prm[km] * 1000.0)


def loaded_mass_t(prm: ParamSet) -> float:
    """Loaded mass of the reference truck (CAT 793D), t: empty (gross machine weight - nominal payload) + payload."""
    return prm["fleet_gmw_793_t"] - prm["fleet_nom_payload_793_t"] + prm["fleet_payload_793_t"]


def v_loaded_kmh(prm: ParamSet, line: int) -> float:
    """Power-limited loaded speed on the ramp of a route, km/h, before the operating factor, capped at the top speed."""
    g = grade(prm, line)
    p_w = prm["fleet_eta_drive"] * prm["fleet_power_793_kw"] * 1000.0
    f_n = loaded_mass_t(prm) * 1000.0 * G * (g + prm["fleet_rr"])
    return min(p_w / f_n * KMH, prm["fleet_vmax_kmh"])


def legs(prm: ParamSet, line: int) -> dict[str, float]:
    """Parts of the cycle of a route, min: load, haul, queue, dump, back (+ total); kept in the ParamSet until a value changes
    (the cycle is asked for every step by the pit and by the fleet)."""
    return prm.memo(("haul-legs", line), lambda: _legs(prm, line))


def _legs(prm: ParamSet, line: int) -> dict[str, float]:
    km_key, _ = _route_keys(line)
    km = prm[km_key]
    eff = prm["fleet_speed_eff"]
    haul = km / (v_loaded_kmh(prm, line) * eff) * 60.0
    back = km / (min(prm["fleet_v_empty_kmh"], prm["fleet_vmax_kmh"]) * eff) * 60.0
    dump = dump_min(prm)
    out = {"load": prm["fleet_load_min"], "haul": haul, "queue": prm["fleet_queue_min"], "dump": dump, "back": back}
    out["total"] = sum(out.values())
    return out


def dump_min(prm: ParamSet) -> float:
    """Dump time, min: body raise + body lower (Specalog p. 20) + positioning (fleet_spot_min)."""
    return (prm["fleet_body_raise_s"] + prm["fleet_body_lower_s"]) / 60.0 + prm["fleet_spot_min"]


def cycle_min(prm: ParamSet, line: int) -> float:
    """Round trip of a route, min (line 0 = waste dump)."""
    return legs(prm, line)["total"]


def loaded_share(prm: ParamSet, line: int) -> float:
    """Share of the driving time spent loaded (haul / (haul + back))."""
    lg = legs(prm, line)
    return lg["haul"] / (lg["haul"] + lg["back"])


def mean_ore_cycle_min(prm: ParamSet) -> float:
    return 0.5 * (cycle_min(prm, 1) + cycle_min(prm, 2))


def calibrate(prm: ParamSet | None = None) -> float:
    """fleet_speed_eff that makes the mean cycle of the two ore routes REF_CYCLE_MIN (bisection)."""
    p = default() if prm is None else prm
    lo, hi = 0.05, 1.5
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if mean_ore_cycle_min(p.copy(fleet_speed_eff=mid)) > REF_CYCLE_MIN:
            lo = mid                      # slower than the target: speed factor must grow
        else:
            hi = mid
    return 0.5 * (lo + hi)


def measure_map(plan: dict) -> dict[str, float]:
    """Haul lengths in km from plan.json (anchors: face, ramp path, crusher; waste: face-4 + road-dump path)."""
    a = plan["anchors"]

    def length(pts):
        return sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    out = {}
    for n in (1, 2):
        pts = [a[f"face-{n}"]["xy"]] + a[f"ramp-{n}"]["path"] + [a[f"crusher-{n}"]["xy"]]
        out[n] = length(pts) / 1000.0
    out[0] = length([a["face-4"]["xy"]] + a["road-dump"]["path"]) / 1000.0
    return out


def table(prm: ParamSet | None = None) -> list[dict]:
    """Rows for the documents: the parts of every route."""
    p = default() if prm is None else prm
    rows = []
    for line, name in ((1, "руда → ЦПД-1"), (2, "руда → ЦПД-2"), (0, "вскрыша → отвал")):
        lg = legs(p, line)
        km_key, rise_key = _route_keys(line)
        rows.append({"route": name, "km": p[km_key], "rise_m": p[rise_key], "grade_pct": 100.0 * grade(p, line),
                     "v_loaded_kmh": v_loaded_kmh(p, line), "v_eff_loaded_kmh": v_loaded_kmh(p, line) * p["fleet_speed_eff"],
                     **{k: round(v, 2) for k, v in lg.items()}})
    return rows


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = default()
    if "--calibrate" in argv:
        print(f"fleet_speed_eff = {calibrate(p):.4f}  (table value {p['fleet_speed_eff']})")
    for r in table(p):
        print(f"{r['route']:<18} {r['km']:.3f} km rise {r['rise_m']:.0f} m grade {r['grade_pct']:.1f} % "
              f"v loaded {r['v_loaded_kmh']:.1f} (x eff {r['v_eff_loaded_kmh']:.1f}) km/h  load {r['load']} haul {r['haul']} "
              f"queue {r['queue']} dump {r['dump']} back {r['back']}  cycle {r['total']} min")
    print(f"mean ore cycle {mean_ore_cycle_min(p):.2f} min (target {REF_CYCLE_MIN})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
