"""Summary of the symmetric people / twin base (VALIDATION.md 8.17): the runs of `sim/data/exp24/*.json` -> `sim/data/experiment_24.json`.

The runs are written by `sim/data/exp24/run_exp24.py` (the rows of `sim/trial.py`, one per shift). Nothing is simulated here. For every run the
contrast "twin minus as now" (copy «по $» minus copy «как сейчас», t Cu per shift to 20:00) is printed the way the brief of 24.10.2026
asks: mean with the 95 % BCa interval (10 000 resamples), median, trim1 (one top and one bottom shift dropped), P10 / P90, the shares of shifts
worse / better than +-0.05 t, the shift that sets the mean (seed 1066: the reorder artefact of 8.8), the mean without it. The mean stays the
primary statistic of the pre-registered plan (8.6); the change of the base is a deviation written after the run (8.17).

  python -I aktogay/run.py exp24 --write aktogay/sim/data/experiment_24.json
"""
from __future__ import annotations

import json
import os
import random
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sim import trial  # noqa: E402

DIR = os.path.join(HERE, "data", "exp24")
OUT = os.path.join(HERE, "data", "experiment_24.json")
BOOT = 10000
ARTEFACT_SEED = 1066                     # two protection trips on one I&C crew in the same minute: the twin reorders them (VALIDATION 8.8)
LINE_HOUR_CU_T = 13.78                   # t Cu per line-hour of the twin (VALIDATION 8.2 / C4), for the equivalent in minutes of a full line stop
# name -> (file, role). The role says how the headline uses the run.
RUNS = {
    "R1": ("R1_same_dig_s1001", "symmetric base, hard ore seen by «как сейчас» at the start of digging; seeds 1001-1100"),
    "R2": ("R2_same_dig_s2001", "the same on new seeds 2001-2100"),
    "R3": ("R3_same_sag_s1001", "symmetric base, hard ore seen by «как сейчас» only at the SAG; seeds 1001-1100"),
    "R4": ("R4_same_sag_s2001", "the same on new seeds 2001-2100"),
    "R5": ("R5_none_dig_s1001", "control, --twin-human none (the base of 8.8) on the merged code; seeds 1001-1100"),
    "R5b": ("R5b_none_dig_s2001", "control, --twin-human none; seeds 2001-2100"),
    "R6": ("R6_same_dig_stockB_s1001", "R1 under the other reading of the PEK stockpile sentence (live 163 kt), seeds 1001-1100"),
    "R6b": ("R6b_same_dig_stockB_s2001", "R2 under the same reading, seeds 2001-2100"),
    "R7": ("R7_same_sag_stockB_s1001", "R3 under the same reading, seeds 1001-1100"),
    "R7b": ("R7b_same_sag_stockB_s2001", "R4 under the same reading, seeds 2001-2100"),
}


def _load(name: str, directory: str = DIR):
    path = os.path.join(directory, name + ".json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _block(xs: list[float], rng: random.Random, boot: int = BOOT) -> dict:
    """The statistics asked for in the brief for one contrast."""
    s = trial.summarize(xs, boot, rng)
    srt = sorted(xs)
    n = len(xs)
    trim1 = statistics.fmean(srt[1:-1]) if n > 2 else s["mean"]
    return {"n": n, "mean": s["mean"], "ci95": list(s["ci95_mean_bca"]), "median": s["median"], "median_ci95": list(s["ci95_median"]),
            "trim1": trim1, "p10": s["p10"], "p90": s["p90"], "sd": s["sd"],
            "share_worse": s["p_minus"], "share_worse_ci95": list(s["p_minus_ci95_wilson"]),
            "share_better": s["p_plus"], "share_none": s["p0"], "wilcoxon_p": s["wilcoxon"]["p"],
            "min": srt[0], "max": srt[-1]}


def _metric(rows: list[dict], a: str, b: str, metric: str, rng: random.Random, zero: float, boot: int) -> dict:
    xs = trial._lin(rows, {a: 1.0, b: -1.0}, metric)
    return trial._brief(xs, boot, rng, zero=zero)


def _diffs(doc: dict) -> dict:
    """seed -> twin minus as now of one run."""
    return {r["seed"]: float(r["cu_t_2000"]["by_value"]) - float(r["cu_t_2000"]["no_twin"]) for r in doc["shifts"]}


def summarize_run(doc: dict, rng: random.Random, boot: int = BOOT) -> dict:
    rows = doc["shifts"]
    cfg = doc["config"]
    d = [float(r["cu_t_2000"]["by_value"]) - float(r["cu_t_2000"]["no_twin"]) for r in rows]
    top = max(range(len(d)), key=lambda i: d[i])
    rest = [x for i, x in enumerate(d) if i != top]
    out: dict = {
        "n": len(rows), "seeds": doc["seeds"],
        "config": {k: cfg.get(k) for k in ("twin_human", "asis_hard", "library", "set", "copies", "tact_min", "fine_tact_min")},
        "troubles_per_shift": sum(r["n_troubles"] for r in rows) / len(rows),
        "twin_minus_asis": _block(d, rng, boot),
        "detection": _block([float(r["cu_t_2000"]["by_loud"]) - float(r["cu_t_2000"]["no_twin"]) for r in rows], rng, boot),
        "order": _block([float(r["cu_t_2000"]["by_value"]) - float(r["cu_t_2000"]["by_loud"]) for r in rows], rng, boot),
        "order_without_detection": _block([float(r["cu_t_2000"]["value_nd"]) - float(r["cu_t_2000"]["no_twin"]) for r in rows], rng, boot),
        "top_shift": {"seed": rows[top]["seed"], "d_cu_t": d[top], "text": rows[top]["text"]},
        "without_top_shift": _block(rest, rng, boot),
        "seed_1066": next((x for r, x in zip(rows, d) if r["seed"] == ARTEFACT_SEED), None),
        "means_cu_t": {c: sum(float(r["cu_t_2000"][c]) for r in rows) / len(rows) for c in rows[0]["cu_t_2000"]},
        "loss_vs_base_cu_t": {c: sum(float(r["loss_cu_t_2000"][c]) for r in rows) / len(rows) for c in rows[0]["loss_cu_t_2000"]},
    }
    # the metrics of 8.6 for the main contrast
    out["metrics"] = {
        "usd": _metric(rows, "by_value", "no_twin", "usd", rng, 1e-9, boot),
        "kwh_per_t_cu": _metric(rows, "by_value", "no_twin", "kwh_per_t_cu", rng, 1e-9, boot),
        "down_min": _metric(rows, "by_value", "no_twin", "down_min", rng, 1e-9, boot),
        "recovery_pp": _metric(rows, "by_value", "no_twin", "recovery_pp", rng, 1e-9, boot),
    }
    out["cu_no_troubles_t"] = sum(float(r["cu_t_2000"]["base"]) for r in rows) / len(rows)
    # the shifts where the twin is worse than "as now" by more than the threshold: seed, size, troubles and the calls of both copies
    worse = []
    for r, x in zip(rows, d):
        if x >= -trial.ZERO_T:
            continue
        calls = {}
        for tr in r["troubles"]:
            tw, ex = r["bookings"]["by_value"].get(tr["issue"]), r["bookings"]["no_twin"].get(tr["issue"])
            calls[tr["issue"]] = {"start": round(tr["t_start_min"], 1), "call_twin": None if tw is None else round(tw["t_call_min"], 1),
                                  "call_as_now": None if ex is None else round(ex["t_call_min"], 1)}
        worse.append({"seed": r["seed"], "d_cu": x, "text": r["text"], "kinds": sorted({t["kind"] for t in r["troubles"]}),
                      "shared_crew": r["shared_crew"], "calls": calls})
    out["worse_shifts"] = sorted(worse, key=lambda w: w["d_cu"])
    # by kind: the mean over the shifts where the kind is present (a shift has two or three troubles: not a share of the kind)
    kinds: dict[str, list[float]] = {}
    for r, x in zip(rows, d):
        for k in {t["kind"] for t in r["troubles"]}:
            kinds.setdefault(k, []).append(x)
    out["by_kind"] = {k: {"mean": statistics.fmean(v), "n": len(v)} for k, v in sorted(kinds.items())}
    # where the gain sits (exclusive groups): shifts with a hidden loss found by the module (dose, cyclone), then shifts with hard ore, then the rest
    def group(r):
        kinds = {t["kind"] for t in r["troubles"]}
        return "dose_or_cyclone" if kinds & {"dose", "cyclone"} else "hard_ore" if "hard" in kinds else "other"

    sit: dict = {}
    for r, x in zip(rows, d):
        sit.setdefault(group(r), []).append((r["seed"], x))
    out["gain_sits_in"] = {g: {"n": len(v), "mean": statistics.fmean(x for _, x in v),
                               "mean_without_top_shift": statistics.fmean(x for sd, x in v if sd != rows[top]["seed"]) if any(sd != rows[top]["seed"] for sd, _ in v) else None,
                               "share_of_total_without_top": (sum(x for sd, x in v if sd != rows[top]["seed"]) / sum(rest)) if sum(rest) else None}
                           for g, v in sorted(sit.items())}
    # decomposition of the main contrast (the method of C26): copper through more ore to the flotation and through recovery
    a, b = "by_value", "no_twin"
    if "cu_feed_t_2000" in rows[0] and "rec_pct_2000" in rows[0]:
        mean = statistics.fmean
        dfeed = mean(float(r["cu_feed_t_2000"][a]) - float(r["cu_feed_t_2000"][b]) for r in rows)
        rec_b = mean(float(r["rec_pct_2000"][b]) for r in rows)
        drec = mean(float(r["rec_pct_2000"][a]) - float(r["rec_pct_2000"][b]) for r in rows)
        feed_b = mean(float(r["cu_feed_t_2000"][b]) for r in rows)
        dstop = mean(float(r["down_min_2000"][a]["line_stop"]) - float(r["down_min_2000"][b]["line_stop"]) for r in rows)
        dlim = mean(float(r["down_min_2000"][a]["line_limited"]) - float(r["down_min_2000"][b]["line_limited"]) for r in rows)
        out["decomposition"] = {
            "d_cu_t": mean(d), "via_more_ore_t": dfeed * rec_b / 100.0, "via_recovery_t": drec / 100.0 * feed_b,
            "d_recovery_pp": drec, "d_line_stop_min": dstop, "d_line_limited_min": dlim,
            "line_stop_part_t": -dstop / 60.0 * LINE_HOUR_CU_T,
            "equivalent_full_line_stop_min": mean(d) / LINE_HOUR_CU_T * 60.0,
            "note": "метод C26 (benefit_split.py): медь через больший расход руды = разность меди в питании флотации × извлечение; через извлечение = разность "
                    "извлечения × медь в питании; полный простой линии = разность минут × 13,78 т Cu/ч; эквивалент — доля тонн от цены минуты полной остановки",
        }
    return out


# paired contrasts between runs of the same seeds: (name, a, b) is the mean over the shifts of (twin - as now) of run a minus run b
PAIRED = (("hard_ore_at_sag_vs_dig_s1001", "R3", "R1"), ("hard_ore_at_sag_vs_dig_s2001", "R4", "R2"),
          ("stock_b_vs_a_dig_s1001", "R6", "R1"), ("stock_b_vs_a_dig_s2001", "R6b", "R2"),
          ("stock_b_vs_a_sag_s1001", "R7", "R3"), ("stock_b_vs_a_sag_s2001", "R7b", "R4"),
          ("symmetric_vs_none_s1001", "R1", "R5"), ("symmetric_vs_none_s2001", "R2", "R5b"))
LADDER = ("S1_s1001", "S3_s1001", "S5_s1001", "S1_s2001", "S3_s2001")      # exp24/ladder/<name>.json, written by exp24/ladder.py
NOVICE_RUNS = ("nov_main", "nov_rep", "nov_lo", "nov_hi")                  # exp24/nov24/<name>.json, written by exp24/run_nov24.py


def _ladder(directory: str, rng: random.Random, boot: int) -> dict:
    """The steps between the base of 8.8 and the symmetric base (VALIDATION 8.17): the same statistics as the runs."""
    out = {}
    for name in LADDER:
        path = os.path.join(directory, "ladder", name + ".json")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        blk = _block([r["d"] for r in doc["rows"]], rng, boot)
        blk.update({"stage": doc["stage"], "opts": doc["opts"], "seed0": doc["seed0"]})
        out[name] = blk
    return out


def _novice(directory: str):
    """The novice runs of 8.9-8.10 on the symmetric base: the aggregation of `trial.aggregate` (block `novice_data`)."""
    ndir = os.path.join(directory, "nov24")
    docs = {}
    for name in NOVICE_RUNS:
        path = os.path.join(ndir, name + ".json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                docs[name] = json.load(f)
    if "nov_main" not in docs:
        return None
    return trial._novice_block(lambda tag: docs.get(tag))


def build(directory: str = DIR, boot: int = BOOT) -> dict:
    rng = random.Random("exp24-summary")
    runs: dict = {}
    for key, (fname, role) in RUNS.items():
        doc = _load(fname, directory)
        if doc is None:
            continue
        r = summarize_run(doc, rng, boot)
        r["file"] = f"exp24/{fname}.json"
        r["role"] = role
        if key == "R1":
            # energy and CO2 of the main run, by the method of 8.8 (trial._energy_block reads the rows of "main_full")
            r["energy_co2"] = trial._energy_block(lambda name, d=doc: d if name == "main_full" else None)
        runs[key] = r
    out: dict = {"plan": "VALIDATION.md 8.6 (primary statistic: the mean, unchanged); deviation of the base: 8.17", "dir": "exp24", "boot": boot,
                 "unit": "t Cu per shift to 20:00, copy «по $» minus copy «как сейчас»", "artefact_seed": ARTEFACT_SEED, "runs": runs}
    paired = {}
    for name, a, b in PAIRED:
        if a in runs and b in runs:
            da = _diffs(_load(RUNS[a][0], directory))
            db = _diffs(_load(RUNS[b][0], directory))
            if da.keys() == db.keys():
                paired[name] = {"a": a, "b": b, **_block([da[k] - db[k] for k in sorted(da)], rng, boot)}
    out["paired"] = paired
    ladder = _ladder(directory, rng, boot)
    if ladder:
        out["ladder"] = ladder
    nov = _novice(directory)
    if nov:
        out["novice_data"] = nov
    return out


def json_text(directory: str = DIR) -> str:
    return json.dumps(build(directory), ensure_ascii=False, indent=1) + "\n"


def main(argv: list[str]) -> int:
    out = OUT
    if "--write" in argv:
        out = argv[argv.index("--write") + 1]
    doc = build()
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    for k, r in doc["runs"].items():
        t = r["twin_minus_asis"]
        print(f"{k:4} {r['file']:40} mean {t['mean']:+.3f} [{t['ci95'][0]:+.2f}; {t['ci95'][1]:+.2f}] median {t['median']:+.3f} trim1 {t['trim1']:+.3f} "
              f"P10/P90 {t['p10']:+.2f}/{t['p90']:+.2f} worse {100 * t['share_worse']:.0f} % better {100 * t['share_better']:.0f} % "
              f"top {r['top_shift']['seed']} {r['top_shift']['d_cu_t']:+.1f}")
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
