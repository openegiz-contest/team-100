"""Replay of a shift «с двойником / без» (design notes of 22.10.2026, item V2): two timelines of the same shift side by side,
started -> noticed -> called -> arrived -> resolved, the difference in hours and in t Cu.

Built only from the rows of the on/off trial that are already stored (`sim/data/trial_n100.json`, `shifts[*]`):
`troubles[*].t_start_min`, `t_found_min` (hidden troubles: the moment the twin finds them), and `bookings.by_value`
(the twin) and `bookings.no_twin` ("as now") with `t_call_min`, `t_arrive_min`, `t_done_min`; the copper of the three
copies is `cu_t_2000` (at 20:00). Nothing is simulated here and the trial is not run again: the page shows the
shifts of the trial N = 100, seeds 1001-1100, and every number is a model estimate.

  python -I aktogay/run.py replay --write aktogay/web/static/replay.json

Model minutes count from the start of the model day (480 = 08:00). The trial stores no separate "noticed" time of
the copy without the twin: people call when they see the trouble (alarm notice, laboratory, the call of an operator),
so «заметили» equals «позвали» there. A trouble that no crew fixes (hard ore, grid cut, reline) is a decision: its
«прибыл» is empty and «решено» is the call.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TRIAL = os.path.join(HERE, "data", "trial_n100.json")
NO_VALUE = -1.0
DECISION = ("hard", "grid", "reline")          # no crew: the call is the decision
TITLE_RU = {"crusher": "Дробилка {n}: поломка", "trip": "Дробилка {n}: защита по давлению масла",
            "hard": "Твёрдая руда на линии {n}", "grid": "Сеть урезала мощность",
            "cyclone": "Гидроциклоны {n}: засорение (скрытое)", "dose": "Флотация {n}: недодозировка реагента (скрытая)",
            "reline": "Перефутеровка SAG-{n}"}
WINDOW_END_MIN = 1200.0                        # 20:00 of the first model day: the copper of cu_t_2000 is counted to here


def _t(v) -> float | None:
    return None if v is None or float(v) < 0.0 else round(float(v), 1)


def _copy(tr: dict, bk: dict | None, twin: bool) -> dict:
    """Stages of one trouble in one copy (None = did not happen within the trial window)."""
    start = float(tr["t_start_min"])
    if bk is None:
        called = None
    else:
        called = _t(bk["t_call_min"])
    if twin:
        noticed = _t(tr["t_found_min"]) if tr["hidden"] else round(start, 1)
        if tr["hidden"] and noticed is None:
            noticed = called
    else:
        noticed = called
    if noticed is not None and called is not None and noticed > called:
        noticed = called                # the plant's own alarm or laboratory called the crew before the twin found the trouble
    decision = tr["kind"] in DECISION
    arrived = None if decision or bk is None else _t(bk["t_arrive_min"])
    done = called if decision else (None if bk is None else _t(bk["t_done_min"]))
    return {"noticed": noticed, "called": called, "arrived": arrived, "done": done,
            "by": (bk or {}).get("by", "")}


def shift_row(row: dict) -> dict:
    troubles = []
    for tr in row["troubles"]:
        w = _copy(tr, row["bookings"]["by_value"].get(tr["issue"]), True)
        o = _copy(tr, row["bookings"]["no_twin"].get(tr["issue"]), False)
        item = {"issue": tr["issue"], "kind": tr["kind"], "line": tr["line"], "node": tr["node"], "crew": tr["crew"],
                "hidden": bool(tr["hidden"]), "decision": tr["kind"] in DECISION,
                "title": TITLE_RU.get(tr["kind"], tr["kind"]).format(n=tr["line"]),
                "start": round(float(tr["t_start_min"]), 1), "with": w, "without": o}
        for key in ("called", "done"):
            a, b = w[key], o[key]
            item["d_" + key + "_h"] = round((b - a) / 60.0, 2) if a is not None and b is not None else None
        troubles.append(item)
    cu = row["cu_t_2000"]
    usd = row["usd_2000"]
    return {"seed": row["seed"], "text": row["text"], "shared_crew": bool(row["shared_crew"]), "troubles": troubles,
            "cu_t": {"with": round(cu["by_value"], 3), "without": round(cu["no_twin"], 3), "base": round(cu["base"], 3)},
            "gain_cu_t": round(cu["by_value"] - cu["no_twin"], 3),
            "gain_usd": round(usd["by_value"] - usd["no_twin"], 0)}


def build(path: str = TRIAL) -> dict:
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    shifts = [shift_row(r) for r in d["shifts"]]
    tw = d["summary"]["twin_cu_t_2000"]
    return {
        "source": {"file": "sim/data/trial_n100.json", "n": d["n"], "seed0": d["seeds"][0], "seed1": d["seeds"][1],
                   "asis_notice_min": d["config"].get("asis_notice_min"), "detect_min": d["config"].get("detect_min"),
                   "label": "оценка на модели"},
        "summary": {"n": tw["n"], "mean_cu_t": round(tw["mean"], 3), "median_cu_t": round(tw["median"], 3),
                    "ci95": [round(x, 3) for x in tw["ci95_mean_bca"]], "p_plus": tw["p_plus"], "p_minus": tw["p_minus"]},
        "window_end_min": WINDOW_END_MIN,
        "shifts": shifts,
    }


def json_text(path: str = TRIAL) -> str:
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
