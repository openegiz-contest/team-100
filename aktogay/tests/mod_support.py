"""Helpers for the module tests: a Store filled like a Ditto search result (no network)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from modules.params import default  # noqa: E402
from modules.store import Store  # noqa: E402

NS = "kz.aktogay"
RUN = "test-run"

# Base case of the stand (design sections 1 and 4) per thing type; line things get "-N".
BASE = {
    "site": {"state": "RUN", "speed": 60.0, "tph": 7706.0, "cu_tph": 27.4, "power_mw": 250.0, "scenario": ""},
    "pit": {"state": "RUN", "mining_tph": 7706.0, "plan_text": "L1: B-1201 B-1203; L2: B-1202", "hard_in_plan": 0.0},
    "fleet": {"state": "NORMAL", "haul_tph": 8680.0, "mining_tph": 7706.0, "trucks_ready": 31.0, "trucks_total": 36.0},
    "exc": {"state": "DIG", "tph": 2600.0, "block": "B-1201", "bench": 12.0},
    "crusher": {"state": "RUN", "tph": 3853.0, "power_kw": 750.0, "lube_kpa": 250.0},
    "conveyor": {"state": "RUN", "tph": 3853.0, "power_kw": 3640.0},
    "stockpile": {"state": "NORMAL", "level_t": 28000.0, "in_tph": 3853.0, "out_tph": 3853.0, "hours_left": -1.0},
    "line": {"state": "RUN", "tph": 3853.0, "cu_tph": 13.7, "recovery": 87.2},
    "sag": {"state": "RUN", "power_kw": 26000.0, "power_limit_kw": 28000.0, "feed_tph": 3853.0, "speed_pct": 76.0,
            "load_pct": 25.0, "e_kwh_t": 6.748, "axb_soft": 35.0, "liner_wear_mm": 120.0},
    "pebble": {"state": "RUN", "feed_tph": 578.0, "limit_tph": 740.0, "load_pct": 78.1},
    "ball": {"state": "RUN", "power_kw": 20500.0, "e_kwh_t": 10.64},
    "cyclones": {"state": "NORMAL", "p80_um": 178.5, "pressure_kpa": 80.0, "open_count": 10.0},
    "flot": {"state": "RUN", "feed_cu": 0.41, "tail_cu": 0.053, "conc_cu": 24.3, "recovery": 87.2, "cu_tph": 13.7,
             "conc_tph": 56.4},
    "rougher": {"state": "RUN", "feed_tph": 3853.0, "stage_recovery": 89.9, "mass_pull_pct": 7.0, "rconc_cu": 5.1,
                "residence_min": 30.0, "dose_sp_gt": 25.0, "dose_meas_gt": 25.0},
    "cleaner": {"state": "RUN", "feed_tph": 270.0, "stage_recovery": 97.0, "conc_cu": 24.3, "conc_tph": 56.4,
                "tail_cu": 0.19},
    "thick": {"state": "NORMAL", "feed_tph": 56.4, "underflow_tph": 56.4, "inventory_t": 170.0, "solids_pct": 60.0,
              "overflow_m3h": 120.0, "hours_to_full": -1.0},
    "filter": {"state": "RUN", "presses_on": 2.0, "cake_tph": 56.4, "moisture_pct": 8.0, "limit_tph": 70.0},
    "conc-stock": {"state": "NORMAL", "stock_t": 9000.0, "in_tph": 122.6, "hours_to_full": -1.0},
    "water": {"state": "NORMAL", "intake_m3h": 4300.0, "recycle_m3h": 21130.0, "tails_loss_m3h": 2380.0,
              "evap_m3h": 1910.0, "pond_m3": 1.25e6, "residual_pct": 0.4, "piezo_kpa": 148.0},
    "power": {"state": "NORMAL", "grid_limit_mw": 300.0, "site_mw": 250.0, "grinding_mw": 139.6,
              "grinding_shaft_mw": 134.0, "other_mw": 102.0, "shed_mw": 0.0, "headroom_mw": 50.0},
    "crew": {"state": "FREE", "task": "", "free_at": -1.0},
    "mod-losses": {}, "mod-ore": {}, "mod-priority": {}, "journal": {"last": {}}, "control": {"scenario": {}},
}
THINGS = (["site", "pit", "fleet", "exc-1", "exc-2", "exc-3", "crusher-1", "crusher-2", "conveyor-1", "conveyor-2",
           "stockpile-1", "stockpile-2", "line-1", "line-2", "sag-1", "sag-2", "pebble-1", "pebble-2",
           "ball-1a", "ball-1b", "ball-2a", "ball-2b", "cyclones-1", "cyclones-2", "flot-1", "flot-2",
           "rougher-1", "rougher-2", "cleaner-1", "cleaner-2", "thick-1", "thick-2", "filter-1", "filter-2",
           "conc-stock", "water", "power", "crew-kip", "crew-cpd", "crew-mill", "crew-water", "mod-losses", "mod-ore",
           "mod-priority", "journal", "control"])
RESP = {"crusher": "crusher_mech", "conveyor": "crusher_mech", "sag": "grinding_operator", "flot": "shift_metallurgist",
        "cyclones": "control_operator", "pit": "mine_dispatcher", "fleet": "mine_dispatcher", "water": "tailings_engineer",
        "power": "power_engineer", "line": "plant_shift_manager", "filter": "plant_shift_manager",
        "thick": "plant_shift_manager", "conc-stock": "plant_shift_manager", "ball": "plant_mech",
        "pebble": "grinding_operator"}
ROLES = {"shift_supervisor": "Сменный руководитель ЦУП", "mine_dispatcher": "Горный диспетчер",
         "shift_geologist": "Геолог смены", "crusher_mech": "Механик ЦПД", "kip": "Дежурный КИПиА",
         "plant_shift_manager": "Начальник смены фабрики", "grinding_operator": "Оператор пульта измельчения",
         "plant_mech": "Механик фабрики", "control_operator": "Оператор пульта", "shift_metallurgist": "Металлург смены",
         "tailings_engineer": "Технолог хвостов и оборотной воды", "power_engineer": "Дежурный энергетик",
         "shift_mechanic": "Сменный механик"}


def type_of(name):
    if name in BASE:
        return name
    if name.startswith("crew-"):
        return "crew"
    return name.rsplit("-", 1)[0]


def item(name, values, t, attrs=None, run=RUN):
    typ = type_of(name)
    feats = {k: {"properties": {"value": v, "unit": ""}} for k, v in values.items()}
    feats["sim_time"] = {"properties": {"value": float(t), "unit": "min"}}
    feats["idSimulationRun"] = {"properties": {"value": run, "unit": ""}}
    a = {"type": typ, "_parents": f"{NS}:site"}
    if typ in RESP:
        a["responsible"] = {"role": RESP[typ], "name_ru": ROLES[RESP[typ]]}
    a.update(attrs or {})
    return {"thingId": f"{NS}:{name}", "attributes": a, "features": feats}


def snapshot(t, overrides=None, batches=None, run=RUN):
    """Search-like items of every stand thing at model minute t; overrides {name: {feature: value}}."""
    overrides = overrides or {}
    items = []
    for name in THINGS:
        vals = dict(BASE[type_of(name)])
        vals.update(overrides.get(name, {}))
        items.append(item(name, vals, t, run=run))
    for b in batches or []:
        items.append(batch_item(t, run=run, **b))
    return items


def batch_item(t, name, line, state, est_axb=35.0, est_cu=0.41, est_ascu=5.0, tonnes=15000.0, axb_soft=-1.0,
               block="", run=RUN, pit_t=None):
    loc = {"PLANNED": "pit", "DIG": "pit", "BELT": f"conveyor-{line}", "IN_STOCK": f"stockpile-{line}",
           "DONE": f"line-{line}"}[state]
    if pit_t is None:
        pit_t = tonnes if state == "PLANNED" else (tonnes / 2.0 if state == "DIG" else 0.0)
    attrs = {"type": "batch", "_parents": f"{NS}:{loc}",
             "passport": {"block": {"value": block or f"B-{name[-4:]}"}, "est_axb": {"value": est_axb},
                          "est_cu": {"value": est_cu}, "est_ascu": {"value": est_ascu},
                          "tonnes": {"value": tonnes}, "line": {"value": float(line)}}}
    vals = {"state": state, "location": loc, "tonnes_left": tonnes, "pit_t": pit_t, "cu_meas": -1.0,
            "axb_soft": axb_soft}
    return item(name, vals, t, attrs, run)


_MODEL = None


def items_from_plant(plant, run=RUN, things=None):
    """Search-like items of a simulator plant (measured features, attributes from things.json),
    numbers rounded as sim/publish sends them: the modules see what they would see in Ditto."""
    global _MODEL
    from sim import publish
    from sim import sensors as se
    if _MODEL is None:
        setup = os.path.join(ROOT, "setup")
        if setup not in sys.path:
            sys.path.insert(0, setup)
        import twins
        _MODEL = twins.Model()
    m = _MODEL
    st = plant.state
    t = st.clock.t_min
    out = []
    for name, vals in se.measured_features(st, plant.prm).items():
        if things is not None and name not in things:
            continue
        feats = {k: {"properties": {"value": publish.number(v) if isinstance(v, float) else v, "unit": ""}}
                 for k, v in vals.items()}
        feats["sim_time"] = {"properties": {"value": float(t), "unit": "min"}}
        feats["idSimulationRun"] = {"properties": {"value": run, "unit": ""}}
        thing = m.by_name.get(name)
        if thing is not None:
            attrs = m.attributes(thing)
            attrs["type"] = thing["type"]
        else:
            b = st.batches.get(name)
            attrs = {"type": "batch", "_parents": f"{NS}:{b.location}" if b else f"{NS}:site",
                     "passport": {"block": {"value": float(b.block_no)}, "est_axb": {"value": b.est.axb},
                                  "est_cu": {"value": b.est.cu_pct}, "est_ascu": {"value": b.est.ascu_pct},
                                  "tonnes": {"value": b.tonnes}, "line": {"value": float(b.line)}}} if b else {}
        out.append({"thingId": f"{NS}:{name}", "attributes": attrs, "features": feats})
    for name in ("mod-losses", "mod-ore", "mod-priority", "journal", "control"):
        out.append(item(name, BASE[name], t, run=run))
    return out


def make_store(t=480.0, overrides=None, batches=None, hist=None):
    """Store at model minute t; hist = [(t_i, overrides_i, batches_i)] earlier points pushed first."""
    prm = default()
    st = Store(NS, prm["hist_min"])
    for ti, ov, bt in hist or []:
        st.update_from_search(snapshot(ti, ov, bt))
    st.update_from_search(snapshot(t, overrides, batches))
    return st, prm
