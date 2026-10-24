"""Timing of «first trouble + whom to call» for every scenario of the catalog, measured on a running stand through its web API.

For each scenario of web/static/scenarios.json: POST /api/scenario (seed 42), then poll GET /api/state every POLL_S seconds and note

  t_record   wall seconds until control.scenario shows the scenario (the command reached Ditto)
  t_run      wall seconds until a new run (idSimulationRun) with the scenario label is published (the warm-up 06:00-08:00 is over)
  t_issue    wall seconds until the first open issue of the new run that names a person to call (`responsible`/`person`)
  model_min  model minutes after 08:00 at that moment (the site clock `sim_time`)
  issue      its kind, safety class, rank and the person to call

then POST /api/cancel and wait until the free run is back. Scenarios whose card says that no issue appears (a label such as «Зима») are
marked `no issue` after WAIT_S seconds. Run at the stand's own speed (×60: a model minute per wall second); nothing else should load the host.

  python -I aktogay/scripts/measure_scenarios.py [--only crusher:1,fork] [--wait 150] [--out FILE.json]
  python -I aktogay/scripts/measure_scenarios.py --model [--out FILE.json]     # model minutes without the stand: the three modules on the simulator

The result is the table of VALIDATION 10.1 and the «Когда видно» line of the catalog card. Every time is a measurement of one run on one host.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

BASE = os.environ.get("AKT_URL", "http://127.0.0.1:8000")
HERE = os.path.dirname(os.path.abspath(__file__))
SCEN = os.path.join(os.path.dirname(HERE), "web", "static", "scenarios.json")
POLL_S = 1.5
MODEL_COMMAND = "python -I aktogay/scripts/measure_scenarios.py --model --out aktogay/web/static/scenario_timing.json"
START_MIN = 480.0


def get(path: str):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.load(r)


def post(path: str, body: dict):
    req = urllib.request.Request(BASE + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def things() -> dict:
    return {t["thingId"].split(":", 1)[1]: t for t in get("/api/state")["things"]}


def feat(t, k):
    return (((t.get("features") or {}).get(k) or {}).get("properties") or {}).get("value")


def open_issues(th: dict, run: str) -> list[dict]:
    out = []
    for n, t in th.items():
        if (t.get("attributes") or {}).get("type") != "issue":
            continue
        if feat(t, "idSimulationRun") != run or feat(t, "status") in ("RESOLVED", None):
            continue
        out.append({"name": n, "kind": feat(t, "kind"), "safety": feat(t, "safety_class"), "rank": feat(t, "rank"),
                    "who": feat(t, "responsible"), "person": feat(t, "person"), "created": feat(t, "sim_time"),
                    "title": str(feat(t, "text") or "")[:90]})
    out.sort(key=lambda i: (i["rank"] if isinstance(i["rank"], (int, float)) and i["rank"] >= 0 else 99))
    return out


def measure(sid: str, wait_s: float, seed: int = 42) -> dict:
    th0 = things()
    run0 = feat(th0["site"], "idSimulationRun")
    t0 = time.time()
    r = post("/api/scenario", {"id": sid, "seed": seed})
    out = {"id": sid, "ok": bool(r.get("ok", True))}
    t_record = t_run = t_issue = None
    run = None
    issue = None
    while time.time() - t0 < wait_s:
        time.sleep(POLL_S)
        th = things()
        now = time.time() - t0
        scen = str(feat(th["control"], "scenario") or "")
        if t_record is None and sid.split("+")[0].split(":")[0] in scen.replace("{", "").replace("}", ""):
            t_record = now
        site = th["site"]
        rid = feat(site, "idSimulationRun")
        if t_run is None and rid and rid != run0 and feat(site, "state") == "RUN":
            t_run, run = now, rid
        if run is not None and issue is None:
            iss = open_issues(th, run)
            if iss:
                t_issue, issue = now, iss[0]
                out["model_min"] = round(float(feat(site, "sim_time") or 0) - START_MIN, 1)
                out["issue_model_min"] = round(float(issue["created"] or 0) - START_MIN, 1) if issue["created"] is not None else None
                break
    out.update({"t_record_s": None if t_record is None else round(t_record, 1), "t_run_s": None if t_run is None else round(t_run, 1),
                "t_issue_s": None if t_issue is None else round(t_issue, 1), "issue": issue})
    try:
        post("/api/cancel", {})
    except Exception as e:                              # noqa: BLE001
        out["cancel_error"] = repr(e)
    return out


def _model_run(text: str, preset: str, seed: int, horizon_min: int):
    """Generator: (minutes after 08:00, open issues {name: features}) every 5 model minutes of the fact copy through the three modules."""
    ROOT = os.path.dirname(HERE)
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from tests import mod_support as ms
    from modules import losses, ore, priority
    from sim.plant import CopySet
    cs = CopySet(None, seed, text, preset=preset, kip=1)
    fact = cs.copies["fact"]
    for k in [k for k in cs.copies if k != "fact"]:
        cs.copies.pop(k)
    st, prm = ms.make_store(fact.t_min)
    lm, om = losses.LossesModule(prm, st, ms.ROLES), ore.OreModule(prm, st)
    pm = priority.PriorityModule(prm, st, lm, om, ms.ROLES)
    t0 = fact.t_min
    for _ in range(horizon_min // 5):
        for _ in range(5):
            fact.step()
        t = fact.t_min
        st.update_from_search(ms.items_from_plant(fact))
        lm.compute(t)
        if t % 15 == 0:
            om.compute(t)
        _feats, issues = pm.compute(t, seed=1)
        yield t - t0, {k: v for k, v in issues.items() if v.get("status") not in ("RESOLVED", None)}


def model_row(sid: str, seed: int = 42, horizon_min: int = 720, background: set | None = None) -> dict:
    """Model time to the first open issue of the scenario and the person to call, without the stand: the fact copy goes through the three
    modules every 5 model minutes (the same code as akt-modules, on the published points as Ditto would hold them). Issues that the run
    without the scenario shows as well (a short truck fleet at 09:05, the same random events in every copy) are not the scenario's:
    `background` holds their (kind, node). The wall time of the stand is this plus the lag of the modules (VALIDATION 10.1)."""
    out = {"id": sid, "first_issue_min": None, "issue": None}
    for m, open_ in _model_run("" if sid == "fork" else sid, "fork" if sid == "fork" else "", seed, horizon_min):
        own = {k: v for k, v in open_.items() if (v.get("kind"), v.get("node")) not in (background or set())}
        if own:
            k = sorted(own, key=lambda n: own[n].get("rank", 99))[0]
            v = own[k]
            out.update({"first_issue_min": round(m, 1), "n_open": len(own),
                        "issue": {"name": k, "kind": v.get("kind"), "node": v.get("node"), "safety": v.get("safety_class"), "rank": v.get("rank"),
                                  "who": v.get("responsible"), "title": str(v.get("text") or "")[:100]}})
            return out
    return out


def background_issues(seed: int = 42, horizon_min: int = 720) -> set:
    """(kind, node) of every issue that opens in the run without a scenario within the horizon."""
    seen = set()
    for _m, open_ in _model_run("", "", seed, horizon_min):
        for v in open_.values():
            seen.add((v.get("kind"), v.get("node")))
    return seen


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", action="store_true", help="model time without the stand (the three modules on the simulator)")
    ap.add_argument("--only", default="")
    ap.add_argument("--wait", type=float, default=150.0)
    ap.add_argument("--out", default="")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args(argv)
    with open(SCEN, encoding="utf-8") as f:
        ids = [s["id"] for s in json.load(f)["scenarios"]]
    if a.only:
        ids = [i for i in ids if i in a.only.split(",")]
    if a.model:
        rows = []
        bg = background_issues(a.seed)
        print("issues of the run without a scenario (not counted):", sorted(bg), flush=True)
        for sid in ids:
            r = model_row(sid, a.seed, background=bg)
            rows.append(r)
            iss = r["issue"] or {}
            print(f"{sid:14} first issue {r['first_issue_min']} min after 08:00: {iss.get('kind')} / {iss.get('safety')} / {iss.get('who')}", flush=True)
        if a.out:
            with open(a.out, "w", encoding="utf-8", newline="\n") as f:
                ROOT = os.path.dirname(HERE)
                if ROOT not in sys.path:
                    sys.path.insert(0, ROOT)
                from sim import verify
                json.dump({"seed": a.seed, "mode": "model", "code_hash": verify.code_hash(), "command": MODEL_COMMAND, "tact_min": 5,
                           "note": "минуты модели после 08:00 до первой беды сценария в очереди (шаг модулей 5 мин); беды, которые есть и без сценария, не считаются; оценка на модели",
                           "background": sorted(map(list, bg)), "rows": rows}, f, ensure_ascii=False, indent=1)
                f.write("\n")
        return 0
    rows = []
    for sid in ids:
        r = measure(sid, a.wait, a.seed)
        rows.append(r)
        iss = r["issue"] or {}
        print(f"{sid:14} record {r['t_record_s']} s, run {r['t_run_s']} s, issue {r['t_issue_s']} s (model {r.get('model_min')} min): "
              f"{iss.get('kind')} / {iss.get('safety')} / {iss.get('who')}", flush=True)
        time.sleep(8)                                   # the free run comes back
    if a.out:
        with open(a.out, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"seed": a.seed, "base": BASE, "rows": rows}, f, ensure_ascii=False, indent=1)
            f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
