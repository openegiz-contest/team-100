"""Independent audit of the balances: every catalog scenario and the plain shift, 08:00-20:00, copy «факт».

The audit does not call any balance or accounting function of the model. After every step it reads only the state the
plant publishes (stockpile levels and in/out rates, the copper of the flotation feed and concentrate, the site power, the
water intake, the cumulative totals) and integrates the rates itself (rate x step). It then compares:

  ore        stockpile of each line: change of level  vs  sum (in_tph - out_tph) x dt
  copper     copper of the sulphide feed  vs  copper in concentrate + copper in tails (totals of the shift)
  copper_rt  sum over lines of concentrate Cu rate x dt  vs  change of the shift total of concentrate Cu
  energy     sum site_mw x dt  vs  change of the shift total of energy
  water      sum intake_m3h x dt  vs  change of the shift total of fresh water
  limits     no negative level, stockpile not above its live capacity, recovery 0..100 %, SAG power not above its limit
  empty      a stoppage that cuts the inflow: hours to an empty stockpile by the hand formula level / (out - in) at the
             start, against the minute the model shows the stockpile EMPTY (crusher:1, conveyor:1, pitstop)

Residuals are relative to the flow of the shift (%); tolerances are fixed here before the run (TOL). A model estimate.

  python -I aktogay/run.py audit [--jobs 4] [--write aktogay/web/static/audit.json]
"""
from __future__ import annotations

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

COMMAND = "python -I aktogay/run.py audit --write aktogay/web/static/audit.json"
TOL = {"ore": 0.5, "copper": 0.5, "copper_rt": 1.0, "energy": 1.0, "water": 1.0, "empty": 15.0}   # %, set before the run
EMPTY_IDS = ("crusher:1", "conveyor:1", "pitstop")
EPS = 1e-9


def _pct(diff: float, scale: float) -> float:
    return 0.0 if abs(scale) < EPS else 100.0 * abs(diff) / abs(scale)


def audit_one(sid: str, seed: int = 42) -> dict:
    from sim.plant import CopySet
    cs = CopySet(None, seed, sid, preset="", kip=1)
    f = cs.copies["fact"]
    st = f.state
    end = cs.end_min()
    dt_step = cs.prm["cal_step_live_min"]
    n = len(st.lines)
    lvl0 = [ln.stockpile.level_t for ln in st.lines]
    tot0 = {k: getattr(st.total, k) for k in ("cu_feed_t", "cu_conc_t", "tails_cu_t", "energy_mwh", "water_intake_m3", "ore_t")}
    flow = [0.0] * n                     # integrated in - out per line
    through = [0.0] * n                  # integrated out (the scale of the residual)
    cu_rate_sum = 0.0
    e_sum = 0.0
    w_sum = 0.0
    viol = []
    t_start = f.t_min
    empty_pred_h = None
    empty_seen_h = None
    first = True
    while f.t_min < end - EPS:
        t_before = f.t_min
        cs.step(min(dt_step, end - f.t_min))
        dt_h = (f.t_min - t_before) / 60.0
        st = f.state
        for i, ln in enumerate(st.lines):
            sp = ln.stockpile
            flow[i] += (sp.in_tph - sp.out_tph) * dt_h
            through[i] += sp.out_tph * dt_h
            if sp.level_t < -1e-6:
                viol.append(f"{sid}: stockpile-{i + 1} below 0 at {f.t_min:.0f}")
            fr = ln.flot.recovery
            if fr == fr and fr not in (-1.0,) and not (-1e-6 <= fr <= 100.0 + 1e-6):
                viol.append(f"{sid}: recovery of line {i + 1} {fr} at {f.t_min:.0f}")
            lim = ln.sag.power_limit_kw
            if lim and lim > 0 and ln.sag.power_kw > lim * 1.001:
                viol.append(f"{sid}: SAG-{i + 1} power {ln.sag.power_kw:.0f} kW above limit {lim:.0f} at {f.t_min:.0f}")
        cu_rate_sum += sum(ln.cu_tph for ln in st.lines) * dt_h
        e_sum += st.power.site_mw * dt_h
        w_sum += st.water.intake_m3h * dt_h
        if sid in EMPTY_IDS and first and st.lines[0].stockpile.in_tph <= EPS:
            sp = st.lines[0].stockpile
            if sp.out_tph > EPS:
                empty_pred_h = sp.level_t / sp.out_tph + (f.t_min - t_start) / 60.0
                first = False
        if sid in EMPTY_IDS and empty_seen_h is None and st.lines[0].stockpile.state == "EMPTY":
            empty_seen_h = (f.t_min - t_start) / 60.0
    tot = st.total
    rows = {}
    rows["ore"] = max(_pct((st.lines[i].stockpile.level_t - lvl0[i]) - flow[i], through[i]) for i in range(n))
    feed = tot.cu_feed_t - tot0["cu_feed_t"]
    out = (tot.cu_conc_t - tot0["cu_conc_t"]) + (tot.tails_cu_t - tot0["tails_cu_t"])
    rows["copper"] = _pct(feed - out, feed)
    rows["copper_rt"] = _pct(cu_rate_sum - (tot.cu_conc_t - tot0["cu_conc_t"]), tot.cu_conc_t - tot0["cu_conc_t"])
    rows["energy"] = _pct(e_sum - (tot.energy_mwh - tot0["energy_mwh"]), tot.energy_mwh - tot0["energy_mwh"])
    rows["water"] = _pct(w_sum - (tot.water_intake_m3 - tot0["water_intake_m3"]), tot.water_intake_m3 - tot0["water_intake_m3"])
    out_row = {"id": sid or "обычная смена", "residual_pct": {k: round(v, 4) for k, v in rows.items()}, "violations": viol[:5],
               "n_violations": len(viol)}
    if sid in EMPTY_IDS:
        out_row["empty_h"] = {"hand": None if empty_pred_h is None else round(empty_pred_h, 2),
                              "model": None if empty_seen_h is None else round(empty_seen_h, 2)}
        if empty_pred_h and empty_seen_h:
            out_row["residual_pct"]["empty"] = round(_pct(empty_pred_h - empty_seen_h, empty_seen_h), 2)
    return out_row


def build(jobs: int = 1) -> dict:
    from modules import scenarios
    ids = [""] + [s["id"] for s in scenarios.catalog() if s["id"] != "fork"]
    t0 = time.time()
    if jobs > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(jobs) as ex:
            res = list(ex.map(audit_one, ids))
    else:
        res = [audit_one(i) for i in ids]
    worst = {k: max((r["residual_pct"].get(k, 0.0) for r in res), default=0.0) for k in TOL}
    ok = {k: worst[k] <= TOL[k] for k in TOL}
    return {"kind": "akt-audit", "seed": 42, "command": COMMAND, "tolerance_pct": TOL, "worst_pct": worst, "ok": ok,
            "violations": sum(r["n_violations"] for r in res), "runs": res, "seconds": round(time.time() - t0)}


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--only", default="")
    ap.add_argument("--write", default="")
    a = ap.parse_args(argv)
    if a.only:
        print(json.dumps(audit_one(a.only if a.only != "plain" else ""), ensure_ascii=False))
        return 0
    d = build(a.jobs)
    txt = json.dumps(d, ensure_ascii=False, indent=1) + "\n"
    if a.write:
        open(a.write, "w", encoding="utf-8", newline="\n").write(txt)
    print(json.dumps({k: d[k] for k in ("worst_pct", "ok", "violations", "seconds")}, ensure_ascii=False))
    return 0 if all(d["ok"].values()) and d["violations"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
