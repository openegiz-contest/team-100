"""Compact file for the pages «Экономика» and «Калибровка»: the result of the experiment of 24.10.2026 (VALIDATION.md 8.6-8.8, 8.17).

Built only from `sim/data/experiment_23.json` (the summary of `sim/data/exp23/*.json`, the base of 8.8: the twin sees a loud trouble at
its start, `--twin-human none`) and `sim/data/experiment_24.json` (the symmetric people / twin base of 8.17, `sim/exp24.py`); nothing is
simulated here and the older files (`trial_n100.json`, the report of the calibration job) are not touched. When experiment_24.json is
there, `main` and `replication` are the symmetric base (the headline) and the base of 8.8 moves to `history.asym_8_8`; the blocks that were
computed only on the base of 8.8 (tornado, price of an hour of delay, detection against order, laboratory) stay and are labelled so. Every
number is a model estimate.

  python -I aktogay/run.py exp23 --write aktogay/web/static/exp23.json
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "data", "experiment_23.json")
SRC24 = os.path.join(HERE, "data", "experiment_24.json")
KIND_RU = {"trip": "остановка по защите", "crusher": "поломка дробилки", "grid": "урезание сети",
           "dose": "дрейф реагента", "hard": "твёрдая руда", "cyclone": "засор циклона", "reline": "перефутеровка",
           "roping": "канатирование циклонов", "phdrift": "дрейф pH-метра", "hpgr": "неравномерное питание ВВД",
           "mantle": "замена брони дробилки"}
# kind of an issue of the module (modules/priority.py WHO) -> kind of the experiment whose price of an hour of delay it shows on the card
ISSUE_TO_EXP = {"crusher_stop": "crusher", "lube_trip": "trip", "grid_limited": "grid", "hard_ore": "hard", "reline": "reline",
                "loss_cyclones": "cyclone", "loss_flot": "dose", "roping": "roping", "sensor_ph": "phdrift",
                "hpgr_uneven": "hpgr", "crusher_mantle": "mantle"}
POLICY_RU = {"expert": "опытный (без двойника)", "nov_r": "новичок по данным", "nov_twin": "новичок с двойником", "twin": "двойник"}
TORNADO_RU = {("compliance", "0.5"): "доля выполненных советов 50 %", ("compliance", "0.75"): "доля выполненных советов 75 %",
              ("detect_min", "150"): "время находки тихой беды 150 мин (было 75)",
              ("model_error_x2", "0.4"): "ошибка оценки модуля ×2 (σ 0,4 вместо 0,2)",
              ("lab_h", "2"): "лаборатория 2 ч", ("lab_h", "24"): "лаборатория 24 ч"}


def _ci(r: dict) -> list:
    return [round(x, 6) for x in (r.get("ci95") or r.get("ci95_mean_bca"))]


def _est(r: dict, nd: int = 6) -> dict:
    return {"mean": round(r["mean"], nd), "ci95": [round(x, nd) for x in _ci(r)], "n": r.get("n")}


def _pair(c: dict, nd: int = 3) -> dict:
    """The main metric of one contrast of the novice block with the shares of shifts."""
    return {"cu": _est(c["cu"], nd), "usd": _est(c["usd"], 0), "kwh_per_t_cu": _est(c["kwh_per_t_cu"], 2),
            "down_min": _est(c["down_min"], 1), "median": round(c["cu"]["median"], 3),
            "share_worse": c["cu"]["share_worse"], "share_better": c["cu"]["share_better"],
            "effect": bool(c["cu"]["effect"])}


def _novice(d: dict) -> dict:
    """The block «novice from data» (VALIDATION 8.9, 8.10) for the pages; the 8.8 value of the «one at a time» novice stays as history."""
    b = d["b3_d1"]["main_full"]["pairs"]["expert-novice"]
    out = {"v1_expert_minus_novice_cu": _est(b["cu"], 3), "differs": False, "data": None}
    nd = d.get("novice_data", {}).get("runs", {}).get("nov_main")
    if not nd:
        return out
    P = nd["pairs"]
    exp = d["novice_data"].get("expectations", {})
    data = {"n": nd["n"], "seeds": nd["seeds"], "troubles_per_shift": nd["troubles_per_shift"],
            "means_cu": {k: round(v["cu"], 2) for k, v in nd["means"].items()},
            "pairs": {k: _pair(P[k]) for k in ("expert-nov_r", "twin-nov_r", "twin-expert", "nov_twin-nov_r", "nov_twin-expert",
                                                "twin-nov_twin", "expert-nov_det", "expert-nov_err") if k in P},
            "parts": {"seeing": _est(P["expert-nov_det"]["cu"], 3), "slips": _est(P["expert-nov_err"]["cu"], 3)},
            "expectations": exp, "ranges": {}, "holm_p": {k: P[k]["cu"].get("wilcoxon_p_holm") for k in P if "wilcoxon_p_holm" in P[k]["cu"]}}
    for tag, key in (("nov_lo", "lo"), ("nov_hi", "hi"), ("nov_rep", "rep")):
        r = d["novice_data"]["runs"].get(tag)
        if r:
            data["ranges"][key] = {"seeds": r["seeds"], "set": r["set"],
                                   "pairs": {k: _pair(r["pairs"][k]) for k in ("expert-nov_r", "twin-nov_r", "nov_twin-expert", "nov_twin-nov_r")
                                             if k in r["pairs"]}}
    ex = P["expert-nov_r"]["cu"]
    out["differs"] = bool(ex["effect"] and ex["mean"] > 0)
    out["data"] = data
    return out


def _run24(r: dict) -> dict:
    """One run of experiment_24.json in the form of the page: the statistics asked for in the brief of 24.10.2026."""
    t = r["twin_minus_asis"]
    return {"seeds": r["seeds"], "n": r["n"], "cu": _est(t, 3), "median": round(t["median"], 3), "trim1": round(t["trim1"], 3),
            "p10": round(t["p10"], 3), "p90": round(t["p90"], 3), "share_worse": t["share_worse"], "share_better": t["share_better"],
            "top_seed": r["top_shift"]["seed"], "top_d_cu": round(r["top_shift"]["d_cu_t"], 2),
            "without_top": _est(r["without_top_shift"], 3), "seed_1066": None if r.get("seed_1066") is None else round(r["seed_1066"], 2)}


def _main24(r: dict) -> dict:
    t, m = r["twin_minus_asis"], r["metrics"]
    out = {"n": r["n"], "seeds": r["seeds"], "troubles_per_shift": r["troubles_per_shift"],
           "cu": _est(t), "usd": _est(m["usd"], 0), "kwh_per_t_cu": _est(m["kwh_per_t_cu"], 3), "down_min": _est(m["down_min"], 1),
           "share_worse": t["share_worse"], "share_better": t["share_better"], "median": round(t["median"], 3),
           "cu_no_troubles": round(r["cu_no_troubles_t"], 2)}
    out.update({k: v for k, v in _run24(r).items() if k in ("trim1", "p10", "p90", "top_seed", "top_d_cu", "without_top", "seed_1066")})
    return out


def _sym(e: dict) -> dict:
    """The block `sym` of the page: every variant of 8.17 on both seed sets, the steps of the ladder, where the gain sits."""
    runs = e["runs"]
    pick = lambda *keys: {k: _run24(runs[k]) for k in keys if k in runs}          # noqa: E731
    r1 = runs["R1"]
    out = {"dig": pick("R1", "R2"), "sag": pick("R3", "R4"), "stock_b": pick("R6", "R6b", "R7", "R7b"), "none": pick("R5", "R5b"),
           "where_the_gain_sits": r1["gain_sits_in"], "decomposition": r1.get("decomposition"),
           "detection": _est(r1["detection"], 3), "order": _est(r1["order"], 3), "top_seed": r1["top_shift"]["seed"]}
    if "ladder" in e:
        out["ladder"] = {k: {"cu": _est(v, 3), "median": round(v["median"], 3), "trim1": round(v["trim1"], 3), "stage": v["stage"], "seed0": v["seed0"]}
                         for k, v in e["ladder"].items()}
    return out


def _worse24(e: dict) -> dict:
    out = {}
    for key, tag in (("R1", "main_full"), ("R2", "rep_full")):
        r = e["runs"].get(key)
        if r:
            ws = r["worse_shifts"]
            out[tag] = {"n": r["n"], "n_worse": len(ws), "n_below_zero": sum(1 for w in ws if w["d_cu"] < 0), "worst": round(ws[0]["d_cu"], 2) if ws else 0.0,
                        "rows": [{"seed": w["seed"], "d_cu": round(w["d_cu"], 3), "text": w["text"], "kinds": w["kinds"], "shared_crew": w["shared_crew"]}
                                 for w in ws]}
    return out


def build(path: str = SRC, path24: str = SRC24) -> dict:
    out = _build23(path)
    if not os.path.exists(path24):
        return out
    with open(path24, encoding="utf-8") as f:
        e = json.load(f)
    if "R1" not in e["runs"] or "R2" not in e["runs"]:
        return out
    old_main, old_rep = out["main"], out["replication"]
    out["history"]["asym_8_8"] = {"note": "база опыта 8.8: двойник видит громкую беду в её начале (--twin-human none)", "main": old_main, "replication": old_rep,
                                  "control_on_the_merged_code": _run24(e["runs"]["R5"]) if "R5" in e["runs"] else None}
    out["main"] = _main24(e["runs"]["R1"])
    r2 = e["runs"]["R2"]
    out["replication"] = {"seeds": r2["seeds"], "cu": _est(r2["twin_minus_asis"]), "share_worse": r2["twin_minus_asis"]["share_worse"]}
    out["sym"] = _sym(e)
    out["worse"] = _worse24(e)
    if e["runs"]["R1"].get("energy_co2"):
        out["energy"] = _energy({"energy_co2": e["runs"]["R1"]["energy_co2"]})
    if e.get("novice_data"):
        nd = dict(e["novice_data"])
        nd.setdefault("expectations", {})
        out["novice"] = _novice({"b3_d1": {"main_full": {"pairs": {"expert-novice": _expert_novice23(path)}}}, "novice_data": nd})
        pairs = (out["novice"].get("data") or {}).get("pairs", {})
        if "twin-expert" in pairs:
            # the same 100 differences as the headline (code control): one interval on the pages, not a second bootstrap draw of it
            pairs["twin-expert"]["cu"] = dict(out["main"]["cu"])
    out["source"] = {**out["source"], "file": "sim/data/experiment_24.json (+ experiment_23.json)", "plan": "VALIDATION.md 8.6, 8.17",
                     "doc": "VALIDATION.md 8.6-8.8, 8.17"}
    return out


def _expert_novice23(path: str) -> dict:
    """«опытный − новичок по одной беде» of 8.8 (it does not involve the twin and stays as it was)."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)["b3_d1"]["main_full"]["pairs"]["expert-novice"]


def _build23(path: str = SRC) -> dict:
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    b = d["b3_d1"]
    m = b["main_full"]
    te = m["pairs"]["twin-expert"]
    en = m["pairs"]["expert-novice"]
    rep = b["rep_full"]["pairs"]["twin-expert"]["cu"]
    base = b["main_base"]["pairs"]["twin-expert"]["cu"]
    b1, b2, b4 = d["b1"], d["b2"], d["b4"]
    tor0 = next(t for t in d["tornado"] if t["factor"] == "base")["benefit"]
    tornado = [{"label": "база (цикл 5 мин, лаборатория 4 ч)", **_est(tor0), "delta": 0.0}]
    for t in d["tornado"]:
        key = (t["factor"], str(t["value"]))
        if key in TORNADO_RU:
            e = _est(t["benefit"])
            tornado.append({"label": TORNADO_RU[key], **e, "delta": round(e["mean"] - tornado[0]["mean"], 3)})
    return {
        "source": {"file": "sim/data/experiment_23.json", "plan": d["plan"], "date": "24.10.2026", "boot": d["boot"],
                   "label": "оценка на модели", "doc": "VALIDATION.md 8.6-8.8"},
        "main": {"n": m["n"], "seeds": m["seeds"], "troubles_per_shift": m["troubles_per_shift"],
                 "cu": _est(te["cu"]), "usd": _est(te["usd"], 0), "kwh_per_t_cu": _est(te["kwh_per_t_cu"], 3),
                 "down_min": _est(te["down_min"], 1), "share_worse": te["cu"]["share_worse"], "share_better": te["cu"]["share_better"],
                 "median": round(te["cu"]["median"], 3), "cu_no_troubles": round(m["means"]["base_no_troubles"]["cu"], 2)},
        "replication": {"seeds": b["rep_full"]["seeds"], "cu": _est(rep), "share_worse": b["rep_full"]["pairs"]["twin-expert"]["cu"]["share_worse"]},
        "history": {"d2210": {"date": "22.10.2026", "mean": round(d["bridge"]["legacy_check_22_10_settings"]["twin_cu_t_2000"]["mean"], 2),
                              "note": "библиотека бед и настройки 22.10"},
                    "library_2210_cycle_1min": _est(base, 2)},
        "novice": _novice(d),
        "worse": _worse(d),
        "energy": _energy(d),
        "alarms": d.get("alarm_flood") or None,
        "delay": {"issue_kinds": ISSUE_TO_EXP, "usd_per_t_cu": round(_price(), 1),
                  "by_kind": {k: {"label": KIND_RU.get(k, k), "t_per_h": round(v["mean"], 3), "ci95": [round(x, 3) for x in v["ci95"]],
                                  "n": v["n"], "usd_per_h": round(v["mean"] * _price(), 0),
                                  "below_threshold": bool(abs(v["mean"]) < 0.05)} for k, v in b1["by_kind_60min"].items()},
                  "slope_t_per_h": _est(b1["slope_t_cu_per_h_all_troubles"]), "slope_usd_per_h": _est(b1["slope_usd_per_h_all_troubles"], 0),
                  "levels": [{"min": int(k), "loss_cu": round(v["mean"], 2), "ci95": [round(x, 2) for x in v["ci95"]],
                              "loss_usd": round(v["usd_loss"]["mean"], 0)} for k, v in b1["levels"].items()],
                  "by_kind_t_per_h": sorted(({"kind": k, "label": KIND_RU.get(k, k), "mean": round(v["mean"], 2), "n": v["n"]}
                                             for k, v in b1["by_kind_60min"].items()), key=lambda x: -x["mean"])},
        "detect_vs_order": {c: {"detection": _est(b4[c]["contrasts_cu"]["detection"], 2), "order": _est(b4[c]["contrasts_cu"]["order"], 2)}
                            for c in ("1", "2")},
        "lab": {"levels": [{"h": int(k), "mean": round(v["mean"], 2)} for k, v in b2["levels"].items()],
                "slope_t_per_h": _est(b2["slope_t_cu_per_h"], 3), "plateau_from_h": 12},
        "tornado": tornado,
    }


def _price() -> float:
    """USD per t of copper paid to the mine: LME price x payable share of the stand's parameter table."""
    from sim.params import default
    p = default()
    return float(p["econ_cu_price_usd_t"]) * float(p["econ_payable_frac"])


def _worse(d: dict) -> dict:
    """Shifts where the twin is worse than the expert by more than 0.05 t Cu (no simulation: read from the stored rows)."""
    w = d.get("worse_shifts") or {}
    out = {}
    for tag in ("main_full", "rep_full"):
        if tag in w:
            out[tag] = {"n": w[tag]["n"], "n_worse": w[tag]["n_worse"], "n_below_zero": w[tag]["n_below_zero"],
                        "worst": round(w[tag]["worst"], 2),
                        "rows": [{"seed": r["seed"], "d_cu": round(r["d_cu"], 3), "text": r["text"], "kinds": r["kinds"],
                                  "shared_crew": r["shared_crew"]} for r in w[tag]["rows"]]}
    return out


def _energy(d: dict) -> dict | None:
    e = d.get("energy_co2")
    if not e:
        return None
    t = e["twin_minus_expert"]
    return {"co2_t_per_mwh": round(e["co2_t_per_mwh"], 3), "kwh_per_t_cu": {k: round(v, 0) for k, v in e["kwh_per_t_cu"].items()},
            "co2_t_per_t_cu": {k: round(v, 2) for k, v in e["co2_t_per_t_cu"].items()},
            "mwh_per_shift": {k: round(v, 1) for k, v in e["mwh_per_shift"].items()},
            "d_mwh": _est(t["mwh_per_shift"], 2), "d_kwh_per_t_cu": _est(t["kwh_per_t_cu"], 1),
            "d_co2_kg_per_t_cu": {"mean": round(t["co2_kg_per_t_cu"]["mean"], 1), "ci95": [round(x, 1) for x in t["co2_kg_per_t_cu"]["ci95"]]},
            "d_co2_t_shift_absolute": {"mean": round(t["co2_t_per_shift_absolute"]["mean"], 2),
                                       "ci95": [round(x, 2) for x in t["co2_t_per_shift_absolute"]["ci95"]]},
            "d_co2_t_shift_same_output": {"mean": round(t["co2_t_per_shift_same_output"]["mean"], 1),
                                          "ci95": [round(x, 1) for x in t["co2_t_per_shift_same_output"]["ci95"]]}}


def json_text(path: str = SRC) -> str:
    return json.dumps(build(path), ensure_ascii=False, separators=(",", ":")) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "--write":
        with open(argv[1], "w", encoding="utf-8", newline="\n") as f:
            f.write(json_text())
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
