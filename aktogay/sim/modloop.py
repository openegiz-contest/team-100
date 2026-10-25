"""«Two at once» with the modules in the loop: the fact copy follows the calls of the real module code, no stand needed.

On the stand the copy «с двойником» (fact) is driven by the decisions the module akt-priority publishes in Ditto
(mod-priority.auto_call, read by akt-sim; AKT_FACT_POLICY=module, the default). This file does the same without
Mosquitto and Ditto, for the numbers computed beforehand (sim/verify.py, VALIDATION 10): the three modules
(modules/losses.py, ore.py, priority.py, the same classes as in the container akt-modules) read the points the plant
would publish (tests/mod_support.items_from_plant: the measured values rounded as sim/publish.py sends them), tact by
tact, and their auto_call books the crew on the fact copy (CopySet.call(src="module")), module_lag_min model minutes
after the tact: the time the module needs to read a point and the simulator to read the answer (about 10 model
minutes at x60 on the stand, VALIDATION 10.1). Alarm calls are not booked in the fact copy (Plant.follow_module):
the dispatcher of that copy calls when the queue of the module says «звать сейчас». The laboratory call of 14:00 stays
as the net under a silent issue the module does not find. If the module gave nothing for MODULE_MISSING_MIN (sim/plant.py) model minutes,
the fact copy would go to the order fixed beforehand (CopySet.fallback_to_offline); with the modules in the loop
this does not happen, the line is here so that the two runs (stand and file) share one rule.

  python -I -c "import sys; sys.path.insert(0, 'aktogay'); from sim import modloop; print(modloop.run_fork(kip=1)['fork'])"

The result of every run is a model estimate (the module is checked on the stand, the shift is the model's).
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

EPS = 1e-6
TACT_MIN = 5.0              # tact of akt-losses and akt-priority (sim/service.py MODULE_TACT_MIN)
ORE_TACT_MIN = 15.0         # tact of akt-ore
MODULE_LAG_MIN = 10.0       # model minutes from the tact to the booking on the fact copy [measured on the stand, VALIDATION 10.1]


def run_copies(prm=None, seed: int = 42, text: str = "", preset: str = "fork", kip: int | None = 1, safety: bool = False,
               lag_min: float = MODULE_LAG_MIN, tact_min: float = TACT_MIN, auto: bool | None = None, observe=None,
               on_step=None):
    """Run the copies of a scenario to the end of the shift; returns the CopySet.

    observe(t_min, issues): called after every tact with the open issues of the module ({name: features}).
    on_step(copyset): called after every model step (sim/verify.py notes the key moments with it).
    """
    from tests import mod_support as ms                         # a Store filled like a Ditto search result
    from modules import losses, ore, priority
    from sim.plant import CopySet
    cs = CopySet(prm, seed, text, preset=preset, kip=kip, safety=safety, auto=auto, fact_policy="module")
    fact = cs.copies["fact"]
    st, mprm = ms.make_store(fact.t_min)
    lm, om = losses.LossesModule(mprm, st, ms.ROLES), ore.OreModule(mprm, st)
    pm = priority.PriorityModule(mprm, st, lm, om, ms.ROLES, True)
    dt = cs.prm["cal_step_live_min"]
    t0, end = fact.t_min, cs.end_min()
    pending: list[tuple[float, str]] = []
    while fact.t_min < end - EPS and fact.state.site_state != "PAUSED":
        cs.step(min(dt, end - fact.t_min))
        if on_step is not None:
            on_step(cs)
        t = fact.t_min
        for item in [x for x in pending if x[0] <= t + EPS]:
            pending.remove(item)
            cs.call(item[1], src="module")
        k = (t - t0) / tact_min
        if abs(k - round(k)) < EPS:
            st.update_from_search(ms.items_from_plant(fact))
            lm.compute(t)
            if abs((t - t0) / ORE_TACT_MIN - round((t - t0) / ORE_TACT_MIN)) < EPS:
                om.compute(t)
            feats, issues = pm.compute(t, seed=seed)
            ac = feats.get("auto_call")
            if ac and ac.get("node"):
                pending.append((t + lag_min, str(ac["node"])))
            if observe is not None:
                observe(t, {k_: v for k_, v in issues.items() if v.get("status") not in ("RESOLVED", None)})
    return cs


def run_fork(prm=None, seed: int = 42, kip: int = 1, **kw) -> dict:
    """«Two at once» with the modules in the loop: {"fork": {...}, "copies": {name: {cu_t..}}, "policy": {...}}."""
    cs = run_copies(prm, seed, "", "fork", kip, **kw)
    res = cs.shift_result()
    res["policy"] = cs.policy_report()
    return res
