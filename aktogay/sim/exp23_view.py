"""Compact file for the pages «Экономика» and «Калибровка»: the result of the experiment of 24.10.2026 (VALIDATION.md 8.6-8.8).

Built only from `sim/data/experiment_23.json` (the summary of `sim/data/exp23/*.json`); nothing is simulated here and the
older files (`trial_n100.json`, the report of the calibration job) are not touched. Every number is a model estimate.

  python -I aktogay/run.py exp23 --write aktogay/web/static/exp23.json
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "data", "experiment_23.json")
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


def build(path: str = SRC) -> dict:
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
