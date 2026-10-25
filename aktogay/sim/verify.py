"""Expected shift result of every catalog scenario, computed beforehand by the same code as the stand (verify.json).

For each scenario of the catalog (modules/scenarios.py) and the two fork runs (one and two instrument engineers) the
copies of the model are run from 08:00 to 20:00 with the scenario seed: «база» (no scenario), «факт» (the scenario,
no clicks in the interface; with the fork preset the copy follows the calls of the module code, sim/modloop.py), and for the fork «по громкости»
and «без двойника». Written per copy: copper in the concentrate (t) and money (USD) by 20:00, plus key moments of the
«факт» copy (the ore stockpile of a line runs out, the SAG of a line stops being fed) that the base copy does not have
at that minute. Nothing is read from the stand. Every number is a model estimate.

  python -I aktogay/run.py verify --write aktogay/web/static/verify.json [--jobs 4]

The page «Как проверить» and the blue banner of a scenario show these numbers as the expected result; a test keeps the
file equal to the output of this script and checks every number of the scenario table in SUBMISSION.md against it.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

SEED = 42
KEYS = ("cu_t", "ore_t", "energy_mwh", "water_m3", "usd")
ROUND = {"cu_t": 4, "ore_t": 2, "energy_mwh": 3, "water_m3": 1, "usd": 0}
# files of the model: the hash of these tells whether the numbers were computed by the same code
MODEL_FILES = ("comminution.py", "events.py", "flotation.py", "haul.py", "modloop.py", "ore.py", "oxide.py", "params.py",
               "params_lev.py", "params_ox.py", "params_t.py", "people.py", "pit.py", "plant.py", "sensors.py",
               "site_aktogay.py", "state.py", "utilities.py", "wear.py")
COMMAND = "python -I aktogay/run.py verify --write aktogay/web/static/verify.json"
COPY_RU = {"base": "база", "fact": "факт", "loud": "по громкости", "no_twin": "без двойника"}
FORK_RU = {"fact": "по $", "loud": "по громкости", "no_twin": "без двойника", "base": "база"}
LABEL = "оценка на модели; тот же код, что в akt-sim; копия «факт» без нажатий в интерфейсе"


def code_hash() -> str:
    h = hashlib.sha256()
    for name in MODEL_FILES:
        with open(os.path.join(HERE, name), "rb") as f:
            h.update(name.encode() + b"\0" + f.read().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:12]


def runs_list() -> list[dict]:
    """(id, scenario text, preset, kip) of every run: the catalog and fork with two engineers."""
    from modules import scenarios
    out = []
    for s in scenarios.catalog():
        sid = s["id"]
        out.append({"id": sid, "text": "" if sid == "fork" else sid, "preset": "fork" if sid == "fork" else "", "kip": 1})
    out.append({"id": "fork", "text": "", "preset": "fork", "kip": 2})
    return out


def _clock(t_min: float) -> str:
    m = int(round(t_min)) % 1440
    return "%02d:%02d" % (m // 60, m % 60)


def _first_times(plant) -> dict:
    """Which stockpile is empty and which SAG is off now, per line."""
    out = {}
    for ln in plant.state.lines:
        if ln.stockpile is not None and ln.stockpile.state == "EMPTY":
            out["stock_empty_%d" % ln.n] = True
        if ln.sag is not None and ln.sag.state in ("STARVED", "STOP", "RELINE"):
            out["sag_off_%d" % ln.n] = True
    return out


def run_one(spec: dict) -> dict:
    """One scenario to 20:00 with the same loop as CopySet.run_to_end, noting key moments of the «факт» copy."""
    from sim.plant import CopySet, EPS
    prm = None
    if spec.get("set"):
        from sim.params import default
        prm = default().copy(**spec["set"])                # sensitivity runs (sim/stock_sens.py); the stand file has none
    first_f: dict[str, float] = {}
    first_b: dict[str, float] = {}

    def note(cs_) -> None:
        for k in _first_times(cs_.copies["fact"]):
            first_f.setdefault(k, cs_.copies["fact"].t_min)
        for k in _first_times(cs_.copies["base"]):
            first_b.setdefault(k, cs_.copies["base"].t_min)

    if spec["preset"] == "fork":
        # «Два сразу»: the fact copy follows the calls of the module code (sim/modloop.py), as the stand does
        from sim import modloop
        cs = modloop.run_copies(prm, spec.get("seed", SEED), spec["text"], preset=spec["preset"], kip=spec["kip"], on_step=note)
        fact, base = cs.copies["fact"], cs.copies["base"]
        t0 = cs.t0_min
    else:
        cs = CopySet(prm, spec.get("seed", SEED), spec["text"], preset=spec["preset"], kip=spec["kip"])
        fact, base = cs.copies["fact"], cs.copies["base"]
        dt = cs.prm["cal_step_live_min"]
        end = cs.end_min()
        t0 = fact.t_min
        while fact.t_min < end - EPS and fact.state.site_state != "PAUSED":
            cs.step(min(dt, end - fact.t_min))
            note(cs)
    res = cs.shift_result()
    copies = {name: {k: round(v[k], ROUND[k]) for k in KEYS} for name, v in res["copies"].items()}
    diff = {name: {k: round(v[k], ROUND[k]) for k in KEYS} for name, v in res["diff"].items()}
    moments = {}
    for k, t in sorted(first_f.items()):
        if k in first_b and first_b[k] <= t + 1e-6:
            continue                                   # the base copy has it as well: not a result of the scenario
        moments[k] = {"min": round(t - t0, 1), "clock": _clock(t)}
    out = {"id": spec["id"], "kip": spec["kip"], "fork": bool(spec["preset"]), "seed": spec.get("seed", SEED),
           "t_start": _clock(t0), "t_end": _clock(res["t_min"]), "copies": copies, "diff": diff, "moments": moments}
    if res["fork"]:
        out["fork_cu_t"] = {k: round(v, 6) for k, v in res["fork"].items()}
        out["fork_cu_t"]["total_cu_t"] = round(res["copies"]["fact"]["cu_t"] - res["copies"]["no_twin"]["cu_t"], 6)
        pol = cs.policy_report()
        out["fork_policy"] = {"mode": pol.get("mode", ""), "n_calls": pol.get("n_calls", 0), "n_module": pol.get("n_module", 0),
                              "order": pol.get("order", []), "order_by_value": pol.get("order_by_value", []),
                              "same_order": pol.get("same_order"),
                              "calls": [{"clock": _clock(c["t"]), "node": c["node"], "src": c["src"]} for c in pol.get("calls", [])]}
    if spec["id"] == "hard:1":
        # the hard batch reaches the SAG about 20:00: the loss shows in the night shift, so run on to 08:00 next day
        day = cs.prm["cal_step_live_min"]
        for c in cs.copies.values():
            c.state.site_state = "RUN"
        dcu = out["diff"]["fact"]["cu_t"]
        while fact.t_min < t0 + 1440.0 - EPS:
            cs.step(min(day, t0 + 1440.0 - fact.t_min))
        total = fact.state.total.cu_conc_t - base.state.total.cu_conc_t
        out["next_day_cu_t"] = {"until": _clock(fact.t_min), "diff_total": round(total, 3),
                                "night_shift": round(total - dcu, 3)}
    return out


def _job(spec: dict) -> dict:
    return run_one(spec)


def build(jobs: int = 1) -> dict:
    specs = runs_list()
    if jobs > 1:
        import multiprocessing as mp
        with mp.get_context("spawn").Pool(min(jobs, len(specs))) as pool:
            runs = pool.map(_job, specs, chunksize=1)
    else:
        runs = [run_one(s) for s in specs]
    return {"seed": SEED, "code_hash": code_hash(), "command": COMMAND, "label": LABEL, "copy_ru": COPY_RU,
            "fork_ru": FORK_RU, "runs": runs}


def json_text(jobs: int = 1) -> str:
    return json.dumps(build(jobs), ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    path = None
    jobs = 1
    i = 0
    while i < len(argv):
        if argv[i] == "--write":
            path = argv[i + 1]
            i += 1
        elif argv[i] == "--jobs":
            jobs = int(argv[i + 1])
            i += 1
        i += 1
    text = json_text(jobs)
    if path:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print("written", path, len(text), "bytes")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
