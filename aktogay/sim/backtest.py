"""Quarterly back-test of the model on KAZ Minerals production reports 2018-2025.

The model is fitted on 2025 only (calib.fit_2025: availability, SAG K, limit recovery). Every other
quarter is a test: the model gets what the plant management knows at the start of the quarter or what
sets the ore flow, never the result.

  inputs  (from the report of the quarter): ore processed (the availability of the quarter is solved
          so that the model ore matches the reported ore within 0.5 %, secant on calib.run_quarter),
          average sulphide copper grade (the report rounds it to 0.01 % Cu: the Cu error cannot be
          better than +-0.005 / grade, about +-1 %);
          the SAG stop calendar of params.RELINE_CALENDAR as it is (it holds 2024-2025 only);
          the number of concentrators: one before October 2021 (line 2 stands for the whole quarter),
          two from the second concentrator on.
  outputs: recovery and Cu in concentrate (contained metal, the "Copper in concentrate" row).
  blind   : the same quarter at the availability fitted on 2025 (no reported ore): what the model
          cannot know without the maintenance calendar.

Nothing is refitted to hide a miss. Quarters of 2021Q4-2022Q4 are the ramp-up of the second
concentrator, which the model does not have: they are run (both lines at one availability) and flagged.
Data: sim/data/kaz_quarterly.csv (URL and page of every row). Result: sim/data/backtest_q.json, shown
by the stand on the calibration page (validation-calib.report_json.backtest) and in VALIDATION.md 6.1.

Run: python -I run.py backtest [--quick] [--jobs N] [--out FILE] [--only 2024Q1,2024Q2]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)          # also for the spawned worker processes of --jobs

from sim import calib  # noqa: E402
from sim.params import ParamSet, default  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "data", "kaz_quarterly.csv")
OUT_PATH = os.path.join(HERE, "data", "backtest_q.json")

FIT_YEAR = 2025                      # the only calibration year
ORE_TOL = 0.005                      # model ore within 0.5 % of the reported ore
MAX_RUNS = 5                         # runs per quarter in the secant (the first one is the blind run)
A_LO, A_HI = 0.05, 1.0
FIRST_TWO_LINE = (2021, 4)           # Sulphide 2 commissioned in October 2021
FIRST_FULL = (2023, 1)               # ramp-up of line 2 ends with 2022 (Q4 2022 report: both plants above design)
KINDS = ("single", "ramp", "two")
KIND_RU = {"single": "одна фабрика", "ramp": "разгон линии 2", "two": "две фабрики"}
PCT = 100.0


def parse_quarter(q: str) -> tuple[int, int]:
    """'2024Q3' -> (2024, 3)."""
    return int(q[:4]), int(q[5])


def kind_of(year: int, qn: int) -> str:
    """single: one sulphide plant (before 2021Q4); ramp: 2021Q4-2022Q4; two: from 2023."""
    if (year, qn) < FIRST_TWO_LINE:
        return "single"
    if (year, qn) < FIRST_FULL:
        return "ramp"
    return "two"


def _num(x: str) -> float | None:
    x = (x or "").strip()
    return float(x) if x else None


def load_quarters(path: str = CSV_PATH) -> list[dict]:
    """Rows of the report data file: quarter, ore_kt, grade_pct, recovery_pct, cu_conc_kt (+ plants, url, page)."""
    out = []
    with open(path, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            year, qn = parse_quarter(r["quarter"])
            out.append({
                "q": r["quarter"], "year": year, "qn": qn,
                "ore_kt": _num(r["sulphide_ore_kt"]), "ore1_kt": _num(r["sulphide1_ore_kt"]),
                "ore2_kt": _num(r["sulphide2_ore_kt"]), "grade_pct": _num(r["grade_pct"]),
                "rec_pct": _num(r["recovery_pct"]), "cu_kt": _num(r["cu_conc_kt"]),
                "cu_total_kt": _num(r["cu_total_kt"]), "cathode_kt": _num(r["cathode_kt"]),
                "url": r["source_url"], "page": r["source_page"], "note": r["note"]})
    return out


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def solve_quarter(prm: ParamSet, year: int, qn: int, ore_kt: float, grade: float, line_off: tuple[int, ...],
                  seed: int, dt: float) -> tuple[list[tuple[float, dict]], bool]:
    """Runs of one quarter: [(availability, summary)], the first at the fitted availability (blind run).

    Secant on the quarter ore until it is within ORE_TOL of ore_kt; the flag tells whether it got there
    (an ore the model cannot reach, e.g. availability above 1, leaves it False).
    """
    a = _clamp(prm["cal_avail"], A_LO, A_HI)
    pts: list[tuple[float, dict]] = []
    reached = False
    for _ in range(MAX_RUNS):
        res = calib.run_quarter(prm, year, qn, seed, dt, availability=a, grade=grade, line_off=line_off)
        pts.append((a, res))
        if abs(res["ore_kt"] / ore_kt - 1.0) <= ORE_TOL:
            reached = True
            break
        a_prev = pts[-2][0] if len(pts) > 1 else None
        o_prev = pts[-2][1]["ore_kt"] if len(pts) > 1 else None
        if a_prev is not None and abs(a - a_prev) > 1e-9 and abs(res["ore_kt"] - o_prev) > 1e-6:
            slope = (res["ore_kt"] - o_prev) / (a - a_prev)
            a_next = a + (ore_kt - res["ore_kt"]) / slope if slope > 0.0 else a * ore_kt / res["ore_kt"]
        else:
            a_next = a * ore_kt / res["ore_kt"]
        a_next = _clamp(a_next, A_LO, A_HI)
        if abs(a_next - a) < 1e-6:
            break
        a = a_next
    return pts, reached


def run_one(rep: dict, overrides: dict, seed: int, dt: float) -> dict:
    """One quarter: solve the availability, compare with the report, keep the blind run."""
    prm = ParamSet(overrides)
    year, qn = rep["year"], rep["qn"]
    kind = kind_of(year, qn)
    line_off = (2,) if kind == "single" else ()
    pts, reached = solve_quarter(prm, year, qn, rep["ore_kt"], rep["grade_pct"], line_off, seed, dt)
    a_blind, blind = pts[0]
    a_best, best = min(pts, key=lambda p: abs(p[1]["ore_kt"] / rep["ore_kt"] - 1.0))
    const = prm["flot_rec_ref_pct"]
    round_pct = PCT * prm["tol_grade_round_pct"] / rep["grade_pct"]
    tol_cu_pct = PCT * prm["tol_cu_frac"] + round_pct
    rec_err = best["rec_pct"] - rep["rec_pct"]
    cu_err = best["cu_kt"] - rep["cu_kt"]
    cu_pct = PCT * cu_err / rep["cu_kt"]
    # the constant rule for copper: reported ore x reported grade x 87.2 % (what one gets without the model)
    cu_const = rep["ore_kt"] * rep["grade_pct"] / PCT * const / PCT
    return {
        "q": rep["q"], "kind": kind, "fit": year == FIT_YEAR, "runs": len(pts), "ore_reached": bool(reached),
        "avail": a_best, "avail_fit": a_blind,
        "ore_rep": rep["ore_kt"], "ore_mod": best["ore_kt"], "grade_rep": rep["grade_pct"],
        "grade_mod": best["grade_pct"], "rec_rep": rep["rec_pct"], "rec_mod": best["rec_pct"],
        "cu_rep": rep["cu_kt"], "cu_mod": best["cu_kt"],
        "rec_err": rec_err, "cu_err": cu_err, "cu_err_pct": cu_pct, "const_err": const - rep["rec_pct"],
        "cu_const_pct": PCT * (cu_const / rep["cu_kt"] - 1.0),
        "blind_ore": blind["ore_kt"], "blind_cu": blind["cu_kt"],
        "blind_ore_pct": PCT * (blind["ore_kt"] / rep["ore_kt"] - 1.0),
        "blind_cu_pct": PCT * (blind["cu_kt"] / rep["cu_kt"] - 1.0),
        "tol_cu_pct": tol_cu_pct, "round_cu_pct": round_pct,
        "rec_ok": abs(rec_err) <= prm["tol_rec_pp"], "cu_ok": abs(cu_pct) <= tol_cu_pct,
        "beats_const": abs(rec_err) < abs(const - rep["rec_pct"]),
        "url": rep["url"], "page": rep["page"],
    }


def _mean(v: list[float]) -> float:
    return sum(v) / len(v) if v else float("nan")


def _corr(a: list[float], b: list[float]) -> float:
    """Pearson correlation (nan for fewer than 3 points or a constant series)."""
    n = len(a)
    if n < 3:
        return float("nan")
    ma, mb = sum(a) / n, sum(b) / n
    va, vb = sum((x - ma) ** 2 for x in a), sum((y - mb) ** 2 for y in b)
    if va <= 0.0 or vb <= 0.0:
        return float("nan")
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb)


def summarize(rows: list[dict]) -> dict:
    """n, bias, mean absolute and maximum absolute error of recovery (pp) and Cu (kt, %), counts, constant rule."""
    if not rows:
        return {"n": 0}
    rec = [r["rec_err"] for r in rows]
    cuk = [r["cu_err"] for r in rows]
    cup = [r["cu_err_pct"] for r in rows]
    con = [r["const_err"] for r in rows]
    return {
        "n": len(rows),
        "rec_bias_pp": _mean(rec), "rec_mae_pp": _mean([abs(x) for x in rec]), "rec_max_pp": max(abs(x) for x in rec),
        "const_bias_pp": _mean(con), "const_mae_pp": _mean([abs(x) for x in con]),
        "const_max_pp": max(abs(x) for x in con),
        "cu_bias_kt": _mean(cuk), "cu_mae_kt": _mean([abs(x) for x in cuk]), "cu_max_kt": max(abs(x) for x in cuk),
        "cu_bias_pct": _mean(cup), "cu_mae_pct": _mean([abs(x) for x in cup]), "cu_max_pct": max(abs(x) for x in cup),
        "corr_grade_rec_rep": _corr([r["grade_rep"] for r in rows], [r["rec_rep"] for r in rows]),
        "corr_grade_rec_mod": _corr([r["grade_rep"] for r in rows], [r["rec_mod"] for r in rows]),
        "rec_rep_mean": _mean([r["rec_rep"] for r in rows]), "rec_mod_mean": _mean([r["rec_mod"] for r in rows]),
        "cu_const_bias_pct": _mean([r["cu_const_pct"] for r in rows]),
        "cu_const_mae_pct": _mean([abs(r["cu_const_pct"]) for r in rows]),
        "rec_ok": sum(1 for r in rows if r["rec_ok"]), "cu_ok": sum(1 for r in rows if r["cu_ok"]),
        "beats_const": sum(1 for r in rows if r["beats_const"]),
        "blind_cu_mae_pct": _mean([abs(r["blind_cu_pct"]) for r in rows]),
        "blind_cu_max_pct": max(abs(r["blind_cu_pct"]) for r in rows),
        "blind_ore_mae_pct": _mean([abs(r["blind_ore_pct"]) for r in rows]),
        "ore_not_reached": sum(1 for r in rows if not r["ore_reached"]),
    }


def summaries(rows: list[dict]) -> dict:
    test = [r for r in rows if not r["fit"]]
    return {
        "all": summarize(test),
        "single": summarize([r for r in test if r["kind"] == "single"]),
        "ramp": summarize([r for r in test if r["kind"] == "ramp"]),
        "two": summarize([r for r in test if r["kind"] == "two"]),
        "fit": summarize([r for r in rows if r["fit"]]),
    }


NOTES = [
    "Модель подогнана только на 2025 г. (готовность линии, коэффициент энергии SAG, предельное извлечение); "
    "остальные кварталы — проверка без подгонки, ничего не перенастроено после результата.",
    "Входы квартала из отчёта KAZ Minerals [факт]: переработанная руда (готовность линии подобрана так, чтобы руда "
    "модели совпала с отчётом в пределах 0,5 %) и среднее содержание меди; извлечение и медь модель не видит.",
    "Содержание в отчётах округлено до 0,01 % Cu: из-за этого медь не может сойтись точнее ±0,005 / содержание "
    "(около ±1 %) [расчёт]; допуск по меди = 2 % [допущение] + эта полоса, по извлечению ±0,5 п.п. [допущение].",
    "До октября 2021 г. работала одна сульфидная фабрика: в модели вторая линия стоит весь квартал. 2021 IV – 2022 IV "
    "кварталы — разгон второй фабрики, которого в модели нет: они посчитаны и помечены, в основной счёт «две фабрики» "
    "не входят.",
    "«Вслепую» — тот же квартал при готовности, подогнанной на 2025 г., без руды из отчёта: показывает, чего модель "
    "не знает без календаря остановок (ремонты, перефутеровки названы в отчётах, но модель знает их только за "
    "2024–2025 гг.).",
    "Константа — извлечение 87,2 % [факт, 2025] для любого квартала: модель полезна, только если ошибается меньше.",
    "Все колонки «модель» — [оценка на модели]; колонки «отчёт» — [факт] KAZ Minerals (ссылка и страница в строке).",
]


def run(seed: int = 42, dt_min: float | None = None, jobs: int = 1, only: list[str] | None = None,
        prm: ParamSet | None = None, path: str = CSV_PATH) -> dict:
    """Fit on 2025, run every quarter of the data file, return the JSON document."""
    t0 = time.perf_counter()
    base = default()
    dt = float(base["cal_quick_step_min"] if dt_min is None else dt_min)
    seconds: dict[str, float] = {}
    if prm is None:
        t = time.perf_counter()
        prm, _rows = calib.fit_2025(base, seed, dt)
        seconds["fit 2025"] = round(time.perf_counter() - t, 1)
    quarters = load_quarters(path)
    if only:
        want = set(only)
        quarters = [r for r in quarters if r["q"] in want]
    overrides = prm.overrides()
    args = [(r, overrides, seed, dt) for r in quarters]
    t = time.perf_counter()
    if jobs > 1 and len(args) > 1:
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            rows = list(ex.map(_run_one_args, args))
    else:
        rows = [run_one(*a) for a in args]
    seconds["quarters"] = round(time.perf_counter() - t, 1)
    seconds["total"] = round(time.perf_counter() - t0, 1)
    digest = hashlib.sha256(json.dumps(sorted(prm.as_dict().items())).encode()).hexdigest()[:12]
    return {
        "kind": "akt-backtest", "version": 1, "generated": time.strftime("%Y-%m-%d"), "seed": seed, "dt_min": dt,
        "fit_year": FIT_YEAR,
        "fit": {k: prm[k] for k in ("cal_avail", "sag_k", "flot_rinf0_pct")},
        "params_digest": digest,
        "tolerances": {"rec_pp": prm["tol_rec_pp"], "cu_frac": prm["tol_cu_frac"],
                       "grade_round_pct": prm["tol_grade_round_pct"], "const_rec_pct": prm["flot_rec_ref_pct"]},
        "kinds": KIND_RU,
        "rows": rows, "summary": summaries(rows), "notes": NOTES, "seconds": seconds,
        "source": "KAZ Minerals, quarterly production reports 2018-2025 (sim/data/kaz_quarterly.csv)",
        "command": "python -I aktogay/run.py backtest --jobs 4",
    }


def _run_one_args(a):
    return run_one(*a)


def _round(x, nd: int = 4):
    if isinstance(x, float):
        return round(x, nd) if math.isfinite(x) else None
    if isinstance(x, list):
        return [_round(v, nd) for v in x]
    if isinstance(x, dict):
        return {k: _round(v, nd) for k, v in x.items()}
    return x


def format_table(doc: dict) -> str:
    """Plain text table for the console."""
    head = ("quarter", "kind", "ore rep", "ore mod", "grade", "rec rep", "rec mod", "err pp", "const pp",
            "Cu rep", "Cu mod", "err %", "tol %", "blind %", "runs")
    lines = [" | ".join(head)]
    for r in doc["rows"]:
        lines.append(" | ".join([
            r["q"] + ("*" if r["fit"] else ""), r["kind"], f"{r['ore_rep']:.0f}", f"{r['ore_mod']:.0f}",
            f"{r['grade_rep']:.2f}", f"{r['rec_rep']:.1f}", f"{r['rec_mod']:.2f}", f"{r['rec_err']:+.2f}",
            f"{r['const_err']:+.2f}", f"{r['cu_rep']:.1f}", f"{r['cu_mod']:.2f}", f"{r['cu_err_pct']:+.1f}",
            f"{r['tol_cu_pct']:.1f}", f"{r['blind_cu_pct']:+.1f}", str(r["runs"])]))
    lines.append("* = year of the fit (not in the score)")
    for name in ("all", "two", "single", "ramp", "fit"):
        s = doc["summary"][name]
        if s.get("n"):
            lines.append(f"{name}: n {s['n']}, recovery bias {s['rec_bias_pp']:+.2f} MAE {s['rec_mae_pp']:.2f} "
                         f"max {s['rec_max_pp']:.2f} pp (constant MAE {s['const_mae_pp']:.2f}); "
                         f"Cu constant-rule MAE {s['cu_const_mae_pct']:.2f} %; Cu bias {s['cu_bias_pct']:+.2f} % MAE {s['cu_mae_pct']:.2f} % max {s['cu_max_pct']:.2f} % "
                         f"({s['cu_mae_kt']:.2f} kt); in tolerance rec {s['rec_ok']}/{s['n']}, Cu {s['cu_ok']}/{s['n']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Quarterly back-test on KAZ Minerals reports 2018-2025")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--quick", action="store_true", help="step 30 min (the default; kept for symmetry with calib)")
    ap.add_argument("--dt", type=float, default=None, help="step in model minutes (default cal_quick_step_min)")
    ap.add_argument("--jobs", type=int, default=max(1, min(4, (os.cpu_count() or 2) - 1)))
    ap.add_argument("--only", default="", help="comma separated quarters, e.g. 2024Q1,2024Q2")
    ap.add_argument("--out", default=OUT_PATH)
    a = ap.parse_args(argv)
    only = [x.strip() for x in a.only.split(",") if x.strip()] or None
    doc = run(a.seed, a.dt, a.jobs, only)
    print(format_table(doc))
    print(f"{len(doc['rows'])} quarters, {doc['seconds']['total']} s")
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(_round(doc), f, ensure_ascii=False, indent=1, allow_nan=False)
        f.write("\n")
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
