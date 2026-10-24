"""Check of the module «Где теряется медь» (modules/losses.py) on the library of hidden causes.

For each hidden cause (dose, cyclone, liner, oxide) x line 1/2 x three sizes x seeds the plant is run from 08:00; the cause
starts 60 min later (the detector has seen an hour of normal work); every 5 model min the published points
(`tests/mod_support.items_from_plant`, numbers rounded as sim/publish sends them) go through `LossesModule.compute`, as
in `tests/test_mod_losses.py::test_concentrate_balance_on_the_simulator`. The module reads only what Ditto would hold.
Written per run: when the node of the cause first shows «потеря» and when it first shows «не уверен», which nodes
show «потеря» at all, whether the module names the role of the crew that fixes the cause. Control runs without a cause
(same seeds, same window) count false alarms. Everything is a model estimate: the truth of the cause is known only here.

  python -I aktogay/run.py detect_eval --seeds 25 --jobs 4 --write aktogay/web/static/detect_eval.json
  python3 -I aktogay/sim/detect_eval.py --seeds 25 --jobs 4

Truth table (cause -> node of the cause, role of the fixing crew), from `events.issue_for` and `state.CREW_FOR`:
dose -> flot-N, kip (crew-kip); cyclone -> cyclones-N, plant_mech (crew-mill); liner -> sag-N, plant_mech (crew-mill);
oxide -> flot-N, shift_metallurgist (no crew: the metallurgist changes the regime).
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

START_MIN = 60.0                 # the cause starts this long after 08:00
TACTS = 144                      # 12 h of 5 min
STEPS_PER_TACT = 5
WARMUP_TACTS = 12                # control runs count false alarms after the first hour
CAUSES = ("dose", "cyclone", "liner", "oxide")
TRUTH = {"dose": ("flot", "kip"), "cyclone": ("cyclones", "plant_mech"), "liner": ("sag", "plant_mech"),
         "oxide": ("flot", "shift_metallurgist")}
ROW = {"dose": "hc_dose_drop", "cyclone": "hc_cyclone_n", "liner": "hc_liner_eta_loss", "oxide": "hc_oxide_ascu_pp"}
SEED0 = 1001
FILES = ("modules/losses.py", "modules/expect.py", "modules/cusum.py", "modules/batches.py", "modules/store.py",
         "modules/params.py", "modules/text.py")
COMMAND = "python -I aktogay/run.py detect_eval --seeds 25 --jobs 4 --write aktogay/web/static/detect_eval.json"
NODES = ("sag-1", "cyclones-1", "flot-1", "sag-2", "cyclones-2", "flot-2")


def magnitudes(cause: str) -> list[float]:
    from sim.params import TABLE
    p = TABLE[ROW[cause]]
    vals = sorted({float(p.min), float(p.value), float(p.max)})
    return [round(v, 4) for v in vals]


def code_hash() -> str:
    import hashlib
    from sim import verify
    h = hashlib.sha256(verify.code_hash().encode())
    for rel in FILES:
        with open(os.path.join(ROOT, *rel.split("/")), "rb") as f:
            h.update(rel.encode() + b"\0" + f.read().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:12]


def _make_module(fact):
    from tests import mod_support as ms
    from modules import losses
    st, prm = ms.make_store(fact.t_min)
    return ms, st, losses.LossesModule(prm, st, ms.ROLES)


def run_case(case: dict) -> dict:
    """One run. case: {cause, line, mag, seed} ('cause' None = control without a cause) or {preset: 'fork', seed}."""
    from sim.plant import CopySet
    cause, line, mag, seed = case.get("cause"), case.get("line"), case.get("mag"), case["seed"]
    if case.get("preset") == "fork":
        cs = CopySet(None, seed, "", preset="fork", kip=1, auto=False)
        cause, line = "dose", 1
    elif cause:
        cs = CopySet(None, seed, "%s:%d@%d=%s" % (cause, line, int(START_MIN), mag))
    else:
        cs = CopySet(None, seed, "")
    fact = cs.copies["fact"]
    t0 = fact.t_min
    start = 0.0 if case.get("preset") == "fork" else START_MIN     # fork: the silent dose drop starts at 08:00
    ms, st, mod = _make_module(fact)
    first_loss: dict[str, float] = {}
    first_unsure: dict[str, float] = {}
    role_at: dict[str, tuple] = {}
    episodes = {n: 0 for n in NODES}            # transitions into «потеря» (control: after the warm-up)
    unsure_ep = {n: 0 for n in NODES}
    prev = {n: "noise" for n in NODES}
    loss_tacts = {n: 0 for n in NODES}
    top_at_first = ""
    for i in range(TACTS):
        for _ in range(STEPS_PER_TACT):
            fact.step()
        st.update_from_search(ms.items_from_plant(fact))
        f = mod.compute(fact.t_min)
        rel = fact.t_min - t0 - start
        for n in NODES:
            s = f[n + "_status"]
            if i >= WARMUP_TACTS:
                if s == "loss" and prev[n] != "loss":
                    episodes[n] += 1
                if s == "unsure" and prev[n] not in ("unsure", "loss"):
                    unsure_ep[n] += 1
                if s == "loss":
                    loss_tacts[n] += 1
            prev[n] = s
            if cause and rel >= 0.0:
                if s == "loss" and n not in first_loss:
                    first_loss[n] = rel
                    role_at[n] = tuple(mod.results[n].role_keys)
                    if not top_at_first:
                        top_at_first = n
                if s in ("unsure", "loss") and n not in first_unsure:
                    first_unsure[n] = rel
    out = {"seed": seed, "cause": cause, "line": line, "mag": mag, "preset": case.get("preset", ""),
           "first_loss": {k: round(v, 1) for k, v in first_loss.items()},
           "first_unsure": {k: round(v, 1) for k, v in first_unsure.items()},
           "first_alarm_node": top_at_first, "episodes": episodes, "unsure_episodes": unsure_ep,
           "loss_tacts": loss_tacts}
    if cause:
        kind, role = TRUTH[cause]
        node = "%s-%d" % (kind, line)
        out["node"] = node
        out["detected"] = node in first_loss
        out["unsure_only"] = node in first_unsure and node not in first_loss
        out["latency_loss"] = first_loss.get(node)
        out["latency_unsure"] = first_unsure.get(node)
        out["role_ok"] = (role in role_at[node]) if node in role_at else None
        out["role_first"] = (role_at[node][0] == role) if node in role_at else None
    return out


def cases(seeds: int) -> list[dict]:
    out = []
    for cause in CAUSES:
        for line in (1, 2):
            for mag in magnitudes(cause):
                for k in range(seeds):
                    out.append({"cause": cause, "line": line, "mag": mag, "seed": SEED0 + k})
    for k in range(seeds):
        out.append({"preset": "fork", "seed": SEED0 + k})
    for k in range(seeds):
        out.append({"cause": None, "seed": SEED0 + k})
    return out


def _pct(vals, q):
    if not vals:
        return None
    v = sorted(vals)
    k = (len(v) - 1) * q
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return round(v[lo] + (v[hi] - v[lo]) * (k - lo), 1)


def _share(k, n):
    return round(k / n, 3) if n else None


def _wilson(k, n, z=1.96):
    if not n:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    a = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round((c - a) / d, 3), round((c + a) / d, 3)]


def summarize(rows: list[dict], seeds: int) -> dict:
    cause_rows = [r for r in rows if r["cause"] and not r["preset"]]
    fork_rows = [r for r in rows if r["preset"] == "fork"]
    ctrl = [r for r in rows if not r["cause"] and not r["preset"]]

    def block(rs):
        n = len(rs)
        det = [r for r in rs if r["detected"]]
        uns = [r for r in rs if r["unsure_only"]]
        lat = [r["latency_loss"] for r in det]
        ok = [r for r in det if r["role_ok"]]
        first = [r for r in det if r["role_first"]]
        node_first = [r for r in rs if r["first_alarm_node"] == r["node"]]
        anyloss = [r for r in rs if r["first_alarm_node"]]
        return {"n": n, "detected": len(det), "detected_share": _share(len(det), n), "detected_ci95": _wilson(len(det), n),
                "unsure_only": len(uns), "unsure_only_share": _share(len(uns), n),
                "missed": n - len(det) - len(uns), "missed_share": _share(n - len(det) - len(uns), n),
                "latency_median_min": round(statistics.median(lat), 1) if lat else None, "latency_p90_min": _pct(lat, 0.9),
                "latency_p10_min": _pct(lat, 0.1),
                "latency_unsure_median_min": round(statistics.median([r["latency_unsure"] for r in rs if r["latency_unsure"] is not None]), 1)
                if any(r["latency_unsure"] is not None for r in rs) else None,
                "latency_unsure_p10_min": _pct([r["latency_unsure"] for r in rs if r["latency_unsure"] is not None], 0.1),
                "latency_unsure_p90_min": _pct([r["latency_unsure"] for r in rs if r["latency_unsure"] is not None], 0.9),
                "role_named_share": _share(len(ok), len(det)), "role_first_share": _share(len(first), len(det)),
                "first_alarm_is_true_node_share": _share(len(node_first), len(anyloss)),
                "alarmed_runs": len(anyloss)}

    by_cause = {c: block([r for r in cause_rows if r["cause"] == c]) for c in CAUSES}
    by_mag = {}
    for c in CAUSES:
        by_mag[c] = {str(m): block([r for r in cause_rows if r["cause"] == c and r["mag"] == m]) for m in magnitudes(c)}
    by_line = {c: {str(n): block([r for r in cause_rows if r["cause"] == c and r["line"] == n]) for n in (1, 2)} for c in CAUSES}
    matrix = {}
    first_matrix = {}
    for c in CAUSES:
        rs = [r for r in cause_rows if r["cause"] == c]
        matrix[c] = {}
        first_matrix[c] = {}
        for node in NODES:
            # nodes are compared on the line of the cause: «own line» nodes by kind, other line apart
            matrix[c][node] = _share(sum(1 for r in rs if node in r["first_loss"]), len(rs))
            first_matrix[c][node] = _share(sum(1 for r in rs if r["first_alarm_node"] == node), len(rs))
    # the same matrix by node kind on the line of the cause, and the other line («чужая линия»)
    kinds = ("sag", "cyclones", "flot")
    matrix_kind = {}
    for c in CAUSES:
        rs = [r for r in cause_rows if r["cause"] == c]
        row = {}
        for k in kinds:
            row[k + " своя линия"] = _share(sum(1 for r in rs if "%s-%d" % (k, r["line"]) in r["first_loss"]), len(rs))
        row["другая линия (любой узел)"] = _share(sum(1 for r in rs if any(n.endswith("-%d" % (3 - r["line"])) for n in r["first_loss"])), len(rs))
        matrix_kind[c] = row
    fork = block([dict(r, node="flot-1", detected=r["detected"]) for r in fork_rows]) if fork_rows else None
    nc = len(ctrl)
    hours = nc * (TACTS - WARMUP_TACTS) * 5 / 60.0
    control = {"runs": nc, "hours_total": round(hours, 1),
               "loss_episodes": sum(sum(r["episodes"].values()) for r in ctrl),
               "unsure_episodes": sum(sum(r["unsure_episodes"].values()) for r in ctrl),
               "runs_with_loss": sum(1 for r in ctrl if sum(r["episodes"].values()) > 0),
               "loss_per_week": round(sum(sum(r["episodes"].values()) for r in ctrl) / hours * 168.0, 2) if hours else None,
               "by_node_loss": {n: sum(r["episodes"][n] for r in ctrl) for n in NODES}}
    # accounting: false «потеря» in runs with a cause, on nodes that are not the node of the cause (for the matrix reader)
    allc = block(cause_rows)
    return {"overall": allc, "by_cause": by_cause, "by_cause_magnitude": by_mag, "by_cause_line": by_line,
            "matrix_any_loss_by_node": matrix, "matrix_first_alarm_by_node": first_matrix, "matrix_by_kind": matrix_kind,
            "fork_silent_dose": fork, "control": control}


def build(seeds: int = 25, jobs: int = 4) -> dict:
    cs = cases(seeds)
    if jobs > 1:
        import multiprocessing as mp
        with mp.get_context("spawn").Pool(jobs, initializer=_low_priority) as pool:
            rows = pool.map(run_case, cs, chunksize=4)
    else:
        rows = [run_case(c) for c in cs]
    out = {"seeds": [SEED0, SEED0 + seeds - 1], "n_seeds": seeds, "runs": len(rows), "code_hash": code_hash(), "command": COMMAND,
           "harness": "CopySet -> tests/mod_support.items_from_plant (numbers rounded as sim/publish sends them) -> "
                      "LossesModule.compute every 5 model min, 12 h from 08:00; the cause starts at 09:00",
           "start_min_after_0800": START_MIN, "nodes": list(NODES),
           "magnitudes": {c: magnitudes(c) for c in CAUSES}, "truth": {c: list(v) for c, v in TRUTH.items()},
           "label": "оценка на модели"}
    out.update(summarize(rows, seeds))
    return out


def _low_priority() -> None:
    try:
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)   # BELOW_NORMAL
        else:
            os.nice(10)
    except Exception:
        pass


def json_text(seeds: int = 25, jobs: int = 4) -> str:
    return json.dumps(build(seeds, jobs), ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    seeds, jobs, path = 25, 4, None
    i = 0
    while i < len(argv):
        if argv[i] == "--seeds":
            seeds = int(argv[i + 1])
            i += 1
        elif argv[i] == "--jobs":
            jobs = min(4, int(argv[i + 1]))
            i += 1
        elif argv[i] == "--write":
            path = argv[i + 1]
            i += 1
        i += 1
    _low_priority()
    text = json_text(seeds, jobs)
    if path:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print("written", path, len(text), "bytes")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
