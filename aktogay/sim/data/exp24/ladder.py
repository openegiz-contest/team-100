"""The steps between the base of 8.8 and the symmetric base of 8.17, one rule at a time, on the merged code (VALIDATION 8.17, variants table).

`--twin-human same` is the end of a ladder; this script builds the intermediate steps by patching the controller of a `--twin-human none`
run (the way the research scripts of 24.10.2026 did on a snapshot), so that «what does each rule cost» is a result of this code, not of a copy:

  S1  loud troubles at the people's minute in both copies (crusher, trip, grid, reline: the alarm / the plan; hard ore: start + notice;
      mantle change: the plant alarm); the twin copy books them itself, in its order
  S3  S1 + the finding time of dose and cyclone from the module evaluation (MODULE_FIND) + a read of the card U(5; 15) min + the twin never
      later than the people (min) + pH drift seen at the same grab sample as the people
  S5  S3 + uneven HPGR feed known to the twin only when the people know it. S5 must equal `--twin-human same` shift for shift (the check
      of the port: `python -I -B ladder.py S5 --check R1_same_dig_s1001`)

python -I -B -X utf8 aktogay/sim/data/exp24/ladder.py STAGE [--seed0 1001] [--n 100] [--jobs 4] [--check RUN]   (from the folder that holds aktogay/)
Writes `exp24/ladder/<stage>_s<seed0>.json` with the rows of the shifts (cu_t_2000 of the copies) and the contrast.
"""
import json
import math
import os
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
SIM = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(SIM))
from sim import events as ev  # noqa: E402
from sim import trial as T  # noqa: E402

OUT_DIR = os.path.join(HERE, "ladder")
STAGES = {
    "S1": {"sym_loud": 1},
    "S3": {"sym_loud": 1, "human_leg": 1, "det_module": 1, "min_human": 1, "ph_grab": 1},
    "S5": {"sym_loud": 1, "human_leg": 1, "det_module": 1, "min_human": 1, "ph_grab": 1, "hpgr_neutral": 1},
}
OPTS: dict = {}


def patch(opts: dict) -> None:
    """Worker initializer: the controller of a `none` run with the rules of the stage added."""
    OPTS.clear()
    OPTS.update(opts)
    C = T.Controller
    if getattr(C, "_ladder_patched", False):
        return
    C._ladder_patched = True
    orig_known, orig_tact, orig_draw = C.known_at, C.tact, T.draw_shift

    def draw_shift(seed, cfg):
        sh = orig_draw(seed, cfg)
        if OPTS.get("det_module"):
            same = dict(cfg, twin_human="same")
            for tr in sh.troubles:
                if tr.hidden and tr.kind in T.MODULE_FIND and not tr.missed:
                    tr.t_found_min = T.found_min(seed, same, tr)
        return sh
    T.draw_shift = draw_shift

    def core(self, tr):
        if self.mode in ("value", "loud") and OPTS.get("sym_loud") and not tr.hidden:
            if tr.kind == "mantle":
                return tr.t_start_min + ev.notice_delay_min(self.seed, tr.issue, self.plant.prm) + self.delay_of(tr)
            if tr.kind in T.IMMEDIATE:
                return self.seen_at(tr) + self.delay_of(tr)
            if tr.kind == "hard":
                return tr.t_start_min + float(self.cfg.get("asis_notice_min", 10.0)) + self.delay_of(tr)
        base = orig_known(self, tr)
        if self.mode in ("value", "loud") and OPTS.get("human_leg") and tr.hidden and base != math.inf:
            return base + ev.notice_delay_min(self.seed, tr.issue, self.plant.prm)
        return base

    def known_at(self, tr):
        if self.mode in ("value", "loud"):
            if OPTS.get("ph_grab") and tr.kind == "phdrift":
                t = self.seen_at(tr)
            elif OPTS.get("hpgr_neutral") and tr.kind == "hpgr":
                t = self.seen_at(tr)
            else:
                t = core(self, tr)
            return min(t, self.seen_at(tr)) if OPTS.get("min_human") else t
        return orig_known(self, tr)
    C.known_at = known_at

    def tact(self, t):
        if self.mode == "value" and OPTS.get("sym_loud"):
            self._silence_alarm(False)
        orig_tact(self, t)
    C.tact = tact


def main() -> None:
    stage = sys.argv[1]
    arg = lambda f, d: type(d)(sys.argv[sys.argv.index(f) + 1]) if f in sys.argv else d   # noqa: E731
    seed0, n, jobs = arg("--seed0", 1001), arg("--n", 100), arg("--jobs", 4)
    opts = STAGES[stage]
    cfg = dict(T.DEFAULTS, library="tier_s", copies=["base", "by_value", "no_twin", "value_nd"], n=n, seed0=seed0, twin_human="none")
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=jobs, initializer=patch, initargs=(opts,)) as ex:
        rows = list(ex.map(T.run_shift, [(s, cfg) for s in range(seed0, seed0 + n)], chunksize=1))
    d = [r["cu_t_2000"]["by_value"] - r["cu_t_2000"]["no_twin"] for r in rows]
    os.makedirs(OUT_DIR, exist_ok=True)
    out = {"stage": stage, "opts": opts, "seed0": seed0, "n": n, "seconds": round(time.time() - t0),
           "rows": [{"seed": r["seed"], "text": r["text"], "by_value": r["cu_t_2000"]["by_value"], "no_twin": r["cu_t_2000"]["no_twin"], "d": x}
                    for r, x in zip(rows, d)]}
    path = os.path.join(OUT_DIR, f"{stage}_s{seed0}.json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    srt = sorted(d)
    print(f"{stage} seeds {seed0}-{seed0 + n - 1}: mean {statistics.fmean(d):+.3f} median {statistics.median(d):+.3f} trim1 {statistics.fmean(srt[1:-1]):+.3f} "
          f"({out['seconds']} s) -> {path}")
    if "--check" in sys.argv:
        ref = json.load(open(os.path.join(HERE, sys.argv[sys.argv.index("--check") + 1] + ".json"), encoding="utf-8"))
        mine = {r["seed"]: r["d"] for r in out["rows"]}
        worst = max(abs(mine[r["seed"]] - (r["cu_t_2000"]["by_value"] - r["cu_t_2000"]["no_twin"])) for r in ref["shifts"])
        print(f"check against {sys.argv[sys.argv.index('--check') + 1]}: largest difference of a shift {worst:.2e} t Cu")


if __name__ == "__main__":
    main()
