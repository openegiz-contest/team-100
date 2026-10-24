"""Two readings of the PEK sentence about the ore stockpile, and what each does to the conclusions (VALIDATION 8.16).

PEK: «Рабочий объем рудного склада составляет 163000 тонн, что равняется 2-х дневному объему измельчения».
The model reads 163 kt as the working volume of the WHOLE pile and keeps 24.5 % of it (40 kt, analog Skouries) as the live
stock the SAG draws from (`stock_live_t`). The other reading: 163 kt is all live. This script does not change the model;
it runs the scenarios under both readings with the same seeds and writes the numbers.

  reading A  live 40 kt   (the model: stock_live_t = 163 000 x 0.245, start levels 11.6 / 30 kt)
  reading B  live 163 kt, the start level of each pile at the same share of live (x 4.075)
  reading C  live 163 kt, the start level the same in tonnes (11.6 / 30 kt): a bigger tank that starts as low

  python -I aktogay/run.py stock_sens --write aktogay/sim/data/stock_sens.json --jobs 4
  python -I aktogay/run.py stock_sens --trial-summary A.json B.json aktogay/sim/data/stock_sens_trial.json

The headline benefit of the twin (trial N = 100, seeds 1001-1100) is run with the same readings by `run.py trial --set ...`
(see `TRIAL_CMD`), and its summary is stored in `sim/data/stock_sens_trial.json` by `--trial-summary`.
"""
from __future__ import annotations

import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

LIVE_B = 163000.0
SCALE = LIVE_B / 40000.0 * 1.0
SEEDS = tuple(range(1001, 1011))
SCENARIOS = ("crusher:1", "conveyor:1", "mantle:1", "pitstop", "reline:1", "grid", "hard:1", "water", "hpgr_fire", "fork")
READINGS = {
    "A": {"label": "живой запас 40 кт (модель)", "set": {}},
    "B": {"label": "живой запас 163 кт, начальный уровень в той же доле", "set": {
        "stock_live_t": LIVE_B, "stock1_t0": round(11600.0 * LIVE_B / 40000.0), "stock2_t0": round(30000.0 * LIVE_B / 40000.0)}},
    "C": {"label": "живой запас 163 кт, начальный уровень прежний в тоннах", "set": {"stock_live_t": LIVE_B}},
}
TRIAL_CMD = ("python -I aktogay/run.py trial --library tier_s --n 100 --seed0 1001 --jobs 4 --copies base,by_value,by_loud,no_twin "
             "--set stock_live_t=163000 --set stock1_t0=47270 --set stock2_t0=122250 --out B.json")


def _job(a: tuple) -> dict:
    from sim import verify
    reading, sid, seed = a
    spec = {"id": sid, "text": "" if sid == "fork" else sid, "preset": "fork" if sid == "fork" else "", "kip": 1,
            "seed": seed, "set": READINGS[reading]["set"]}
    r = verify.run_one(spec)
    d = r["diff"]["fact"]
    row = {"reading": reading, "scenario": sid, "seed": seed, "d_cu_t": d["cu_t"], "d_usd": d["usd"],
           "moments": {k: v["min"] for k, v in r["moments"].items()}}
    if r["fork"]:
        row["twin_total"] = r["copies"]["fact"]["cu_t"] - r["copies"]["no_twin"]["cu_t"]
        row["detection"] = r["fork_cu_t"]["detection_cu_t"]
        row["order"] = r["fork_cu_t"]["order_cu_t"]
    return row


def _low():
    try:
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
        else:
            os.nice(10)
    except Exception:
        pass


def _stat(v):
    v = [x for x in v if x is not None]
    if not v:
        return None
    return {"n": len(v), "mean": round(statistics.fmean(v), 3), "min": round(min(v), 3), "max": round(max(v), 3)}


def build(jobs: int = 4) -> dict:
    import multiprocessing as mp
    args = [(r, s, seed) for r in READINGS for s in SCENARIOS for seed in SEEDS]
    with mp.get_context("spawn").Pool(jobs, initializer=_low) as pool:
        rows = pool.map(_job, args, chunksize=2)
    out = {"seeds": [SEEDS[0], SEEDS[-1]], "readings": {k: {"label": v["label"], "set": v["set"]} for k, v in READINGS.items()},
           "trial_command": TRIAL_CMD, "scenarios": {}}
    for sid in SCENARIOS:
        out["scenarios"][sid] = {}
        for r in READINGS:
            rs = [x for x in rows if x["scenario"] == sid and x["reading"] == r]
            blk = {"d_cu_t": _stat([x["d_cu_t"] for x in rs]), "d_usd": _stat([x["d_usd"] for x in rs])}
            keys = sorted({k for x in rs for k in x["moments"]})
            blk["stock_or_sag_moment_min"] = {k: {"runs": sum(1 for x in rs if k in x["moments"]),
                                                  "median_min": round(statistics.median([x["moments"][k] for x in rs if k in x["moments"]]), 1)}
                                              for k in keys}
            if sid == "fork":
                blk["twin_total_cu_t"] = _stat([x["twin_total"] for x in rs])
                blk["detection_cu_t"] = _stat([x["detection"] for x in rs])
                blk["order_cu_t"] = _stat([x["order"] for x in rs])
            out["scenarios"][sid][r] = blk
    return out


def _bca(v: list[float], n: int = 10000, seed: int = 5) -> tuple[float, float]:
    import random
    from statistics import NormalDist
    rnd = random.Random(seed)
    m = len(v)
    mean = statistics.fmean(v)
    bs = sorted(statistics.fmean(rnd.choices(v, k=m)) for _ in range(n))
    nd = NormalDist()
    z0 = nd.inv_cdf(sum(1 for b in bs if b < mean) / n)
    jk = [(sum(v) - x) / (m - 1) for x in v]
    jm = statistics.fmean(jk)
    num = sum((jm - j) ** 3 for j in jk)
    den = 6 * (sum((jm - j) ** 2 for j in jk) ** 1.5)
    acc = num / den if den else 0.0

    def q(p):
        zz = nd.inv_cdf(p)
        return nd.cdf(z0 + (z0 + zz) / (1 - acc * (z0 + zz)))
    return bs[int(q(0.025) * n)], bs[min(n - 1, int(q(0.975) * n))]


def trial_summary(path_a: str, path_b: str) -> dict:
    """Headline of the on/off trial (twin minus «as now», t Cu per shift, 100 paired shifts, BCa 95 %) under reading A and reading B,
    and the difference B - A on the same shifts. The two inputs are the files of `run.py trial` with the six copies of the main run."""
    out = {"command_a": TRIAL_CMD.split(" --set")[0] + " --out A.json", "command_b": TRIAL_CMD}
    docs = {}
    for k, p in (("A", path_a), ("B", path_b)):
        with open(p, encoding="utf-8") as f:
            docs[k] = json.load(f)
        v = [x["twin_cu_t"] for x in docs[k]["shifts"]]
        lo, hi = _bca(v)
        out[k] = {"n": len(v), "mean": round(statistics.fmean(v), 4), "ci95": [round(lo, 4), round(hi, 4)], "median": round(statistics.median(v), 4),
                  "worse_than_expert": sum(1 for x in v if x < -0.05),
                  "loss_vs_base_no_twin_cu_t": round(statistics.fmean([x["loss_cu_t_2000"]["no_twin"] for x in docs[k]["shifts"]]), 3)}
    dv = [b["twin_cu_t"] - a["twin_cu_t"] for a, b in zip(docs["A"]["shifts"], docs["B"]["shifts"])]
    lo, hi = _bca(dv)
    out["B_minus_A"] = {"mean": round(statistics.fmean(dv), 4), "ci95": [round(lo, 4), round(hi, 4)]}
    return out


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--trial-summary":
        text = json.dumps(trial_summary(argv[1], argv[2]), ensure_ascii=False, indent=1, sort_keys=True) + chr(10)
        with open(argv[3], "w", encoding="utf-8", newline=chr(10)) as f:
            f.write(text)
        print("written", argv[3])
        return 0
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
    _low()
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
