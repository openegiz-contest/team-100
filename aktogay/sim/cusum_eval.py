"""False alarms of the CUSUM detector of «Где теряется медь»: the stated ≈ 0.95 per week against what is measured (VALIDATION 8.15).

modules/cusum.py: S = max(0, S + z - k), alarm at S >= h or z >= fast; k 0.5, h 6.5, fast 3.5 (`cusum_h` is labelled «calc»:
≈ 1 false alarm a week on 6 nodes). That holds only for independent z ~ N(0, 1). Three checks without changing a parameter:

  1. Monte Carlo on N(0, 1): 6 monitors x 2016 tacts of 5 min a week; the average run length to a false alarm against the
     Siegmund approximation ARL0 = (exp(2 k b) - 2 k b - 1) / (2 k^2), b = h + 1.166 (the fast threshold added).
  2. The same detectors on the residuals of the twin: 7 days of a free run without hidden causes, planned stops and pebble stops
     (hc_per_shift = hc_silent_per_shift = 0, peb_kio = 1), through `LossesModule.compute` every 5 min; false «потеря» episodes
     per node; the autocorrelation of z at lags 1-3.
  3. The curve «false alarms a week - median delay» for h in {4, 5, 6.5, 8} and fast in {3, 3.5, 4}: the z series of the free
     run replayed through the detector for the false alarms, the z series of the node of a hidden cause (4 causes x 10 seeds,
     line 1, the table size) for the delay. The working point 6.5 / 3.5 is marked.

  python -I aktogay/run.py cusum_eval --write aktogay/web/static/cusum_eval.json --jobs 4

Nothing is read from the stand. Every number is a model estimate.
"""
from __future__ import annotations

import json
import math
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

WEEK_TACTS = 2016
NODES = ("sag-1", "cyclones-1", "flot-1", "sag-2", "cyclones-2", "flot-2")
H_GRID = (4.0, 5.0, 6.5, 8.0)
FAST_GRID = (3.0, 3.5, 4.0)
WORK = (6.5, 3.5)
SEEDS_WEEK = (1001, 1002, 1003, 1004)
SEEDS_DELAY = tuple(range(1001, 1011))
CAUSES = ("dose", "cyclone", "liner", "oxide")
COMMAND = "python -I aktogay/run.py cusum_eval --write aktogay/web/static/cusum_eval.json --jobs 4"


def episodes(zs, k, h, fast) -> int:
    """Number of alarm episodes of the detector on a series of z (alarm latched until S falls to 0)."""
    from modules.cusum import OneSidedCusum
    c = OneSidedCusum(k, h, fast)
    n, was = 0, False
    for z in zs:
        a = c.update(z)
        if a and not was:
            n += 1
        was = a
    return n


def first_alarm(zs, k, h, fast, start: int) -> int | None:
    """Index (>= start) of the first alarm of a detector started at 0, or None."""
    from modules.cusum import OneSidedCusum
    c = OneSidedCusum(k, h, fast)
    for i, z in enumerate(zs):
        a = c.update(z)
        if a and i >= start:
            return i
        if a and i < start:
            c.reset()                       # an alarm before the cause is a false alarm: the detector is cleared for the test
    return None


def siegmund(k: float, h: float) -> float:
    b = h + 1.166
    return (math.exp(2 * k * b) - 2 * k * b - 1) / (2 * k * k)


def monte_carlo(weeks: int, k: float, h: float, fast: float, seed: int = 7) -> dict:
    import random
    rnd = random.Random(seed)
    total = 0
    for _ in range(weeks):
        for _m in range(len(NODES)):
            total += episodes((rnd.gauss(0.0, 1.0) for _ in range(WEEK_TACTS)), k, h, fast)
    per_week = total / weeks
    return {"weeks": weeks, "alarms_per_week_6_monitors": round(per_week, 3),
            "arl0_tacts_per_monitor": round(weeks * len(NODES) * WEEK_TACTS / total, 0) if total else None}


def run_week(seed: int) -> dict:
    """A week of the free run without hidden causes through the module; the z series each monitor was fed with."""
    from sim.params import default
    from sim.plant import Plant
    from tests import mod_support as ms
    from modules import losses
    prm = default().copy(hc_per_shift=0.0, hc_silent_per_shift=0.0, peb_kio=1.0)
    plant = Plant(prm, seed, mode="free")
    plant.warmup()
    st, mprm = ms.make_store(plant.t_min)
    mod = losses.LossesModule(mprm, st, ms.ROLES)
    zs = {n: [] for n in NODES}
    for n in NODES:
        c = mod.cusum[n]
        orig = c.update

        def rec(z, _o=orig, _n=n):
            zs[_n].append(float(z))
            return _o(z)
        c.update = rec
    loss_ep = {n: 0 for n in NODES}
    unsure_ep = {n: 0 for n in NODES}
    prev = {n: "noise" for n in NODES}
    for i in range(WEEK_TACTS):
        for _ in range(5):
            plant.step()
        st.update_from_search(ms.items_from_plant(plant))
        f = mod.compute(plant.t_min)
        for n in NODES:
            s = f[n + "_status"]
            if s == "loss" and prev[n] != "loss":
                loss_ep[n] += 1
            if s == "unsure" and prev[n] not in ("unsure", "loss"):
                unsure_ep[n] += 1
            prev[n] = s
    return {"seed": seed, "z": {n: [round(v, 3) for v in zs[n]] for n in NODES}, "loss_episodes": loss_ep, "unsure_episodes": unsure_ep}


def run_delay(case: tuple) -> dict:
    """z series of the node of one hidden cause (the detector started one hour before the cause)."""
    from sim.plant import CopySet
    from tests import mod_support as ms
    from modules import losses
    cause, seed = case
    line = 1
    kind = {"dose": "flot", "cyclone": "cyclones", "liner": "sag", "oxide": "flot"}[cause]
    node = "%s-%d" % (kind, line)
    cs = CopySet(None, seed, "%s:%d@60" % (cause, line))
    fact = cs.copies["fact"]
    st, mprm = ms.make_store(fact.t_min)
    mod = losses.LossesModule(mprm, st, ms.ROLES)
    zs, at = [], []
    c = mod.cusum[node]
    orig = c.update

    def rec(z):
        zs.append(float(z))
        at.append(fact.t_min)
        return orig(z)
    c.update = rec
    for _ in range(144):
        for _ in range(5):
            fact.step()
        st.update_from_search(ms.items_from_plant(fact))
        mod.compute(fact.t_min)
    t0 = at[0] if at else fact.t_min
    return {"cause": cause, "seed": seed, "node": node, "z": [round(v, 3) for v in zs], "t_min": [round(v - 480.0, 1) for v in at]}


def _lowprio():
    try:
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
        else:
            os.nice(10)
    except Exception:
        pass


def autocorr(x, lag):
    n = len(x)
    if n <= lag + 2:
        return None
    m = sum(x) / n
    num = sum((x[i] - m) * (x[i + lag] - m) for i in range(n - lag))
    den = sum((v - m) ** 2 for v in x)
    return round(num / den, 3) if den > 0 else None


def build(jobs: int = 4, mc_weeks: int = 300) -> dict:
    import multiprocessing as mp
    ctx = mp.get_context("spawn")
    with ctx.Pool(jobs, initializer=_lowprio) as pool:
        weeks = pool.map(run_week, SEEDS_WEEK, chunksize=1)
        delay_runs = pool.map(run_delay, [(c, s) for c in CAUSES for s in SEEDS_DELAY], chunksize=2)
    k = 0.5
    mc = {"%s/%s" % (h, f): monte_carlo(mc_weeks, k, h, f) for h, f in ((6.5, 99.0), (6.5, 3.5))}
    sieg = siegmund(k, 6.5)
    n_weeks = len(weeks)
    free_loss = sum(sum(w["loss_episodes"].values()) for w in weeks)
    free_unsure = sum(sum(w["unsure_episodes"].values()) for w in weeks)
    acf = {n: [round(statistics.fmean([a for a in (autocorr(w["z"][n], lag) for w in weeks) if a is not None]), 3) for lag in (1, 2, 3)] for n in NODES}
    sd = {n: round(statistics.pstdev([v for w in weeks for v in w["z"][n]]), 3) for n in NODES}
    mean = {n: round(statistics.fmean([v for w in weeks for v in w["z"][n]]), 3) for n in NODES}
    n_upd = {n: round(statistics.fmean([len(w["z"][n]) for w in weeks])) for n in NODES}
    curve = []
    for h in H_GRID:
        for f in FAST_GRID:
            fa = sum(episodes(w["z"][n], k, h, f) for w in weeks for n in NODES) / n_weeks
            lat = []
            miss = 0
            for r in delay_runs:
                idx = [i for i, t in enumerate(r["t_min"]) if t >= 60.0]
                start = idx[0] if idx else 0
                i = first_alarm(r["z"], k, h, f, start)
                if i is None:
                    miss += 1
                else:
                    lat.append(r["t_min"][i] - 60.0)
            curve.append({"h": h, "fast": f, "false_alarms_per_week_free_run": round(fa, 2),
                          "delay_median_min": round(statistics.median(lat), 1) if lat else None,
                          "delay_p90_min": round(sorted(lat)[int(0.9 * (len(lat) - 1))], 1) if lat else None,
                          "detected_share": round(1.0 - miss / len(delay_runs), 3), "work_point": (h, f) == WORK})
    return {"command": COMMAND, "k": k, "h": WORK[0], "fast": WORK[1], "stated_false_alarms_per_week": 0.95,
            "monte_carlo_n01": mc, "siegmund_arl0_tacts_cusum_only": round(sieg, 0),
            "siegmund_alarms_per_week_6_monitors_cusum_only": round(6 * WEEK_TACTS / sieg, 2),
            "fast_threshold_only_alarms_per_week_6_monitors": round(6 * WEEK_TACTS * 0.5 * math.erfc(3.5 / math.sqrt(2)), 2),
            "free_run": {"weeks": n_weeks, "seeds": list(SEEDS_WEEK), "hidden_causes": 0, "planned_stops": 0,
                         "loss_episodes_total": free_loss, "loss_episodes_per_week": round(free_loss / n_weeks, 2),
                         "unsure_episodes_per_week": round(free_unsure / n_weeks, 2),
                         "loss_episodes_per_week_by_node": {n: round(sum(w["loss_episodes"][n] for w in weeks) / n_weeks, 2) for n in NODES},
                         "z_mean": mean, "z_sd": sd, "z_autocorr_lag1_2_3": acf, "updates_per_week": n_upd},
            "curve": curve, "delay_runs": len(delay_runs), "causes": list(CAUSES),
            "note": "оценка на модели; свободный прогон без скрытых причин; задержка — от начала причины (линия 1, размер по таблице параметров)"}


def main(argv: list[str]) -> int:
    path, jobs = None, 4
    i = 0
    while i < len(argv):
        if argv[i] == "--write":
            path = argv[i + 1]
            i += 1
        elif argv[i] == "--jobs":
            jobs = min(4, int(argv[i + 1]))
            i += 1
        i += 1
    _lowprio()
    text = json.dumps(build(jobs), ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if path:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print("written", path)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
