"""Which parameters can change the conclusions: reachability and a one-at-a-time screening of every label, both edges.

The honest count of «71 % assumptions» is not the whole story: a number that the experiment never reads cannot change its
result. Two steps, both on the model:

  reach     the on/off experiment (library tier S, all copies of the shift, a few shifts) runs with a counter on every
            read of the two parameter tables (sim/params.py and modules/params.py). A row that is never read is
            «не влияет на вывод опыта» (display, other scenarios, calibration, service).
  screen    EVERY row of the model table that is read and has a range (max > min) - whatever its label: fact, vendor, project,
            analog, calculation or assumption - is moved to each end of its range that differs from the value (one at a time, five
            shifts that carry all eleven kinds of trouble, same seeds) and the gain of the twin over «as now» (t Cu per shift, symmetric
            people / twin base of VALIDATION 8.17) is recomputed. A row whose range moves the gain by at least INFLUENCE_T t Cu per
            shift at either end is «влияет на вывод»; the others are «читается, но вывод не меняет». Sourced rows were not moved in
            the first screen of 24.10.2026 (only assumptions, only the far end): «the facts do not matter» was never measured.
            The rows of the modules table are only counted by reach (they cannot be set from the trial), and the rows that
            the experiment sets itself (the tornado of VALIDATION 8.8) keep their measured effect.
  refit     the recovery rows (ASCu, kinetics, cleaner) at an edge change the base recovery that the 2025 report fixes at 87.2 %. They are
            run a second time with the limit recovery flot_rinf0_pct re-solved so that the base recovery stays 87.2 %: what the screen can
            say about them once the data is respected. The mechanism (the far edges push the tails of the base copy to the set point of
            the control-system tails alarm, so «as now» catches the drifts by the alarm) is measured in `mechanism`.

Result: sim/data/influence.json -> web/static/influence.json (page «Калибровка», VALIDATION.md 9.4).

  python -I aktogay/run.py influence [--reach-n 5] [--screen-n 5] [--jobs 4] [--limit N]
  python -I aktogay/run.py influence --refresh-labels      labels of the file from the current tables, no run (after a relabel)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from modules import params as mparams  # noqa: E402
from sim import params as sparams  # noqa: E402
from sim import trial  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(HERE, "data", "influence.json")
INFLUENCE_T = 0.10                  # t Cu per shift: the threshold of the first screen (a tenth of the headline then, +1.07); kept, not tuned after the base change
COPIES = ["base", "by_value", "by_loud", "no_twin", "novice", "value_nd"]
SEED0 = 1001
# five shifts of the experiment seeds that together carry all eleven kinds of trouble of the library (greedy cover of 1001-1100)
SEEDS = [1001, 1012, 1020, 1041, 1005]
LABELS = ("assumption", "fact", "vendor", "analog", "project", "calc")
CLASSES = ("matters", "read_small", "read", "read_fixed", "not_read")
RECOVERY_FAMILY = ("blk_ascu_mean_pct", "flot_ktau0", "clean_r0_pct")      # act on the base recovery that the report fixes
R_INF = "flot_rinf0_pct"
ACS_SP = "acs_tail_sp_pct"


def _cfg(n: int, extra: dict | None = None) -> dict:
    c = dict(trial.DEFAULTS, library="tier_s", n=n, jobs=1, copies=["by_value", "no_twin"], boot=200, seed0=SEED0,
             seeds=SEEDS[:n])
    c.update(extra or {})
    return c


def gain(doc: dict) -> float:
    """Mean gain of the twin over «as now», t Cu per shift at 20:00: Cu(by_value) - Cu(no_twin), same shifts."""
    xs = [r["cu_t_2000"]["by_value"] - r["cu_t_2000"]["no_twin"] for r in doc["shifts"]]
    return sum(xs) / len(xs)


def reach(n: int = 4) -> dict:
    """Keys of both tables that the experiment reads (all copies, library tier S)."""
    seen_s: set[str] = set()
    seen_m: set[str] = set()
    orig_s = sparams.ParamSet.__getitem__
    orig_m = mparams.Prm.__getitem__

    def get_s(self, key):
        seen_s.add(key)
        return orig_s(self, key)

    def get_m(self, key):
        seen_m.add(key)
        return orig_m(self, key)

    sparams.ParamSet.__getitem__ = get_s
    mparams.Prm.__getitem__ = get_m
    try:
        cfg = _cfg(n, {"copies": COPIES, "alarms": ["no_twin", "by_value"]})
        trial.run_trial(cfg)
    finally:
        sparams.ParamSet.__getitem__ = orig_s
        mparams.Prm.__getitem__ = orig_m
    return {"sim": sorted(seen_s), "modules": sorted(seen_m)}


def edges(row) -> list[float]:
    """The ends of the range of a row that differ from its value (a value at an end of its range has one edge to test)."""
    return [x for x in (row.min, row.max) if abs(x - row.value) > 1e-12 * max(1.0, abs(row.value))]


def _far(row) -> float:
    return row.min if abs(row.min - row.value) >= abs(row.max - row.value) else row.max       # the end farther from the value


def _share(ktau: float, clean: float) -> float:
    return (1.0 - math.exp(-ktau)) * clean / 100.0


def refit_rinf(key: str, x: float) -> float:
    """flot_rinf0_pct that keeps the base recovery (grade, ASCu, P80, dose as in the table) when `key` is set to x.

    kinetics:  R0 (1 - exp(-k)) / (1 - exp(-k'));  cleaner:  R0 c / c';  ASCu:  R0 + d / ((1 - exp(-k)) c) (x - x0), d = flot_jose_ascu per pp."""
    t = sparams.TABLE
    r0, kt, cl = t[R_INF].value, t["flot_ktau0"].value, t["clean_r0_pct"].value
    if key == "flot_ktau0":
        return r0 * (1.0 - math.exp(-kt)) / (1.0 - math.exp(-x))
    if key == "clean_r0_pct":
        return r0 * cl / x
    if key == "blk_ascu_mean_pct":
        return r0 + t["flot_jose_ascu"].value / _share(kt, cl) * (x - t["blk_ascu_mean_pct"].value)
    raise KeyError(key)


def compatible_edge(key: str) -> float | None:
    """The value of `key` at which the refitted R_inf reaches the end of its own range (the highest the table allows): beyond it the row cannot
    be moved without breaking the 87.2 % of the report; None when the whole range of `key` stays inside."""
    t = sparams.TABLE
    hi = t[R_INF].max
    r0, kt, cl = t[R_INF].value, t["flot_ktau0"].value, t["clean_r0_pct"].value
    if key == "flot_ktau0":
        x = -math.log(1.0 - r0 * (1.0 - math.exp(-kt)) / hi)
        return x if t[key].min <= x <= t[key].max else None
    if key == "clean_r0_pct":
        x = r0 * cl / hi
        return x if t[key].min <= x <= t[key].max else None
    if key == "blk_ascu_mean_pct":
        x = t[key].value + (hi - r0) * _share(kt, cl) / t["flot_jose_ascu"].value
        return x if t[key].min <= x <= t[key].max else None
    raise KeyError(key)


def _run(args: tuple[dict, int]) -> float:
    s, n = args
    return gain(trial.run_trial(_cfg(n, {"set": s})))


def _tasks_for(keys: list[str]) -> list[tuple[str, str, float, dict]]:
    """(kind, key, edge, ParamSet overrides) for the screen, then the refit runs of the recovery family."""
    out = []
    for k in keys:
        for x in edges(sparams.TABLE[k]):
            out.append(("edge", k, x, {k: x}))
    for k in RECOVERY_FAMILY:
        if k in keys:
            for x in edges(sparams.TABLE[k]):
                out.append(("refit", k, x, {k: x, R_INF: refit_rinf(k, x)}))
    return out


def screen(keys: list[str], n: int, jobs: int) -> dict:
    base = gain(trial.run_trial(_cfg(n)))
    tasks = _tasks_for(keys)
    if jobs > 1:
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            gains = list(ex.map(_run, [(t[3], n) for t in tasks], chunksize=2))
    else:
        gains = [_run((t[3], n)) for t in tasks]
    rows: dict[str, dict] = {}
    for (kind, k, x, s), g in zip(tasks, gains):
        r = rows.setdefault(k, {"edges": [], "refit_edges": []})
        e = {"value": x, "gain": g, "dev": abs(g - base)}
        if kind == "refit":
            e["rinf0"] = s[R_INF]
            r["refit_edges"].append(e)
        else:
            r["edges"].append(e)
    for k, r in rows.items():
        r["dev"] = max(e["dev"] for e in r["edges"])
        far = _far(sparams.TABLE[k])
        r["value_tested"] = far if any(e["value"] == far for e in r["edges"]) else r["edges"][0]["value"]
        r["gain"] = next(e["gain"] for e in r["edges"] if e["value"] == r["value_tested"])
        if r["refit_edges"]:
            r["dev_refit"] = max(e["dev"] for e in r["refit_edges"])
    return {"base_gain": base, "rows": rows}


def _tails(set_: dict) -> float:
    """Copper in the flotation tails of line 1 (%, truth) of the base copy after the warm-up: what the control-system alarm is compared with."""
    from sim.plant import Plant
    pl = Plant(sparams.default().copy(**set_), SEED0, mode="scenario")
    pl.warmup()
    pl.run_until(pl.t_min + 120.0)
    return float(pl.state.lines[0].flot.tail_cu)


def mechanism(n: int, jobs: int) -> dict:
    """Why the far edges of the recovery rows remove the gain (VALIDATION 9.4): the tails of the base copy against the set point of the alarm,
    and the gain with the set point moved by the margin the base has (set point - tails of the base)."""
    sp = sparams.TABLE[ACS_SP].value
    t0 = _tails({})
    rows = [{"name": "base", "set": {}, "tails_pct": t0}]
    for k in RECOVERY_FAMILY:
        x = _far(sparams.TABLE[k])
        rows.append({"name": f"{k}@{x:g}", "key": k, "value": x, "set": {k: x}, "tails_pct": _tails({k: x})})
    shifted = []
    for r in rows[1:]:
        s2 = {**r["set"], ACS_SP: r["tails_pct"] + (sp - t0)}
        shifted.append(s2)
        r["shifted_sp"] = s2[ACS_SP]
    runs = [{}, *[r["set"] for r in rows[1:]], *shifted]
    if jobs > 1:
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            g = list(ex.map(_run, [(s, n) for s in runs], chunksize=1))
    else:
        g = [_run((s, n)) for s in runs]
    rows[0]["gain"] = g[0]
    for r, gx, gs in zip(rows[1:], g[1:4], g[4:7]):
        r["gain"] = gx
        r["gain_shifted_sp"] = gs
    return {"set_point_pct": sp, "rows": rows,
            "compatible_with_the_report": {k: compatible_edge(k) for k in RECOVERY_FAMILY},
            "note": "compatible_with_the_report: the value of the row at which the re-solved flot_rinf0_pct reaches the top of its own range; "
                    "beyond it the row cannot be moved without the base recovery leaving the 87.2 % of the report (None: the whole range stays inside)"}


def classify(r: dict, scr: dict | None) -> dict:
    """Class of every row of both tables: matters / read_small (screened) / read (modules table: cannot be set from the trial) /
    read_fixed (model row without a range) / not_read."""
    s_read, m_read = set(r["sim"]), set(r["modules"])
    sim_rows = list(sparams.TABLE.values())
    mod_rows = list(mparams.PARAMS)
    rows = []
    for tab, items, read in (("model", sim_rows, s_read), ("modules", mod_rows, m_read)):
        for p in items:
            cls = "not_read"
            span = None
            extra: dict = {}
            if p.key in read:
                cls = "read"
                if tab == "model":
                    if scr and p.key in scr["rows"]:
                        span = scr["rows"][p.key]["dev"]
                        cls = "matters" if span >= INFLUENCE_T else "read_small"
                        if "dev_refit" in scr["rows"][p.key]:
                            extra = {"dev_refit": scr["rows"][p.key]["dev_refit"],
                                     "matters_refit": scr["rows"][p.key]["dev_refit"] >= INFLUENCE_T}
                    elif p.max <= p.min:
                        cls = "read_fixed"
            rows.append({"table": tab, "key": p.key, "label": p.label, "cls": cls, "dev": span, **extra})
    return {"rows": rows}


def summary(rows: list[dict]) -> dict:
    out: dict = {"total": len(rows)}
    for lab in LABELS:
        sub = [r for r in rows if r["label"] == lab]
        out[lab] = {"n": len(sub), **{c: sum(1 for r in sub if r["cls"] == c) for c in CLASSES}}
    for c in CLASSES:
        out[c] = sum(1 for r in rows if r["cls"] == c)
    out["assumptions_total"] = sum(1 for r in rows if r["label"] == "assumption")
    out["screened"] = out["matters"] + out["read_small"]
    # the recovery rows that matter at an edge and stop mattering once the limit recovery is re-solved to keep the 87.2 % of the report
    out["refit_removes"] = sorted(r["key"] for r in rows if r.get("matters_refit") is False and r["cls"] == "matters")
    return out


def refresh_labels(doc: dict) -> dict:
    """Labels of the rows from the current tables and the summary recomputed from them. A relabel changes no value, so the run itself stays;
    this is how the analyser rows, relabelled as vendor after the run of 24.10.2026, got their label in the file."""
    lab = {("model", p.key): p.label for p in sparams.TABLE.values()}
    lab.update({("modules", p.key): p.label for p in mparams.PARAMS})
    for r in doc["rows"]:
        r["label"] = lab[(r["table"], r["key"])]
    # rows added after the run: the oxide chain (ox_*, 25.10.2026) does not enter the copper, ore, energy, water or money of the sulphide plant
    # (tests/test_oxide.py: the shift summary is equal with the whole oxide step removed), so its model rows move the gain by 0.0 by construction;
    # the new rows of the modules table are read by modules/oxide.py
    have = {(r["table"], r["key"]) for r in doc["rows"]}
    for p in sparams.TABLE.values():
        if ("model", p.key) not in have:
            fixed = p.max <= p.min
            doc["rows"].append({"table": "model", "key": p.key, "label": p.label, "cls": "read_fixed" if fixed else "read_small",
                                "dev": None if fixed else 0.0})
    for p in mparams.PARAMS:
        if ("modules", p.key) not in have:
            doc["rows"].append({"table": "modules", "key": p.key, "label": p.label, "cls": "read", "dev": None})
    doc["summary"] = summary(doc["rows"])
    doc["top"] = sorted([x for x in doc["rows"] if x["dev"] is not None], key=lambda x: -x["dev"])[:30]
    return doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Which parameters can change the conclusions")
    ap.add_argument("--reach-n", type=int, default=5)
    ap.add_argument("--screen-n", type=int, default=5)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0, help="screen only the first N rows (test)")
    ap.add_argument("--no-screen", action="store_true")
    ap.add_argument("--out", default=OUT_PATH)
    ap.add_argument("--refresh-labels", action="store_true", help="take the labels from the current tables into the file --out (no run)")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    if a.refresh_labels:
        with open(a.out, encoding="utf-8") as f:
            doc = refresh_labels(json.load(f))
        with open(a.out, "w", encoding="utf-8", newline="\n") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
            f.write("\n")
        print(json.dumps(doc["summary"], ensure_ascii=False))
        return 0
    t0 = time.perf_counter()
    r = reach(a.reach_n)
    print(f"reach: model {len(r['sim'])} of {len(sparams.TABLE)} rows, modules {len(r['modules'])} of {len(mparams.PARAMS)}")
    scr = None
    mech = None
    if not a.no_screen:
        keys = [k for k in r["sim"] if sparams.TABLE[k].max > sparams.TABLE[k].min]
        if a.limit:
            keys = keys[:a.limit]
        by_label = {lab: sum(1 for k in keys if sparams.TABLE[k].label == lab) for lab in LABELS}
        print(f"screening {len(keys)} rows of the model that are read and have a range {by_label}, both edges, {a.screen_n} shifts, {a.jobs} jobs")
        scr = screen(keys, a.screen_n, a.jobs)
        print(f"base gain {scr['base_gain']:+.3f} t Cu per shift")
        mech = mechanism(a.screen_n, a.jobs)
    cl = classify(r, scr)
    doc = {"kind": "akt-influence", "version": 2, "generated": time.strftime("%Y-%m-%d"),
           "threshold_t_cu": INFLUENCE_T, "reach_n": a.reach_n, "screen_n": a.screen_n, "screen_seeds": SEEDS[:a.screen_n],
           "base": "twin_human same, asis_hard dig (VALIDATION 8.17)",
           "base_gain": scr["base_gain"] if scr else None, "summary": summary(cl["rows"]),
           "top": sorted([x for x in cl["rows"] if x["dev"] is not None], key=lambda x: -x["dev"])[:30],
           "mechanism": mech, "recovery_family": {k: scr["rows"].get(k) for k in RECOVERY_FAMILY} if scr else None,
           "rows": cl["rows"], "seconds": round(time.perf_counter() - t0, 1)}
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(json.dumps(doc["summary"], ensure_ascii=False))
    print("wrote", a.out, doc["seconds"], "s")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
