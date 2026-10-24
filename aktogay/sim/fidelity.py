"""Behaviour fidelity of the model: the checks of 24.10.2026 that go beyond the quarterly back-test.

  availability   crusher / SAG / flotation share of time in work in the 2025 annual run against the design
                 availabilities of Ausenco (crushing 70-75 %, grinding and flotation 91-92 %). Only flotation is a check:
                 grinding follows the availability fitted to the ore of 2025 (class "fit"), and the crusher row is a
                 REQUIREMENT of the reported ore on the equipment (class "requirement", no tolerance verdict: the OVOS range
                 4386-5043.9 t/h is the design rate of the crushing area with the factor 1.15, not a crusher nameplate)
  relines        real events from the KAZ reports: the model runs the quarter of a SAG reline with and without the
                 reline window and the predicted drop of the line's ore is set against the reported one
  forward_2026   Q1 and Q2 2026 (unseen: the model is fitted on 2025): ore, copper in concentrate, recovery implied
  recovery       refit of the grade slope and the level on 2018-2021 (single plant), test on 2023-2025 against
                 the 2025-fit model and the constants
  spread         quarter-to-quarter spread of the grade (and of recovery) of the 28 reported test quarters against the
                 model with the mine-plan variability of ore.draw_block switched on

Nothing is hidden: every result goes to sim/data/fidelity.json whatever it is, the stand shows it on «Калибровка»,
VALIDATION.md section 6.2 quotes it.

  python -I aktogay/run.py fidelity [--only availability,relines,forward,recovery,spread] [--jobs N] [--out FILE]
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics as st
import sys
import time
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sim import backtest as bt  # noqa: E402
from sim import calib  # noqa: E402
from sim import flotation  # noqa: E402
from sim.params import TABLE, Reline, ParamSet, default  # noqa: E402
from sim.plant import Plant  # noqa: E402
from sim.state import MIN_PER_DAY  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(HERE, "data", "fidelity.json")
CSV_2026 = os.path.join(HERE, "data", "kaz_quarterly_2026.csv")
SEED = 42
PCT = 100.0
G0 = 0.41
# design availabilities, Ausenco (facts_round2 «Раунд 4», D7 and D8)
LIT_AVAIL = {"crusher": (70.0, 75.0), "grinding": (91.0, 92.0), "flotation": (91.0, 92.0)}
DESIGN_CRUSH_H = 285 * 2 * 10.0               # OVOS p. 26: coarse crushing 285 days a year, two shifts of 10 h = 5 700 h (65.1 % of the hours of a year)
HOURS_YEAR = 8760.0
LIT_SRC = ("Ausenco, Constancia: дробление 70,0 %, измельчение и флотация 91,3 % (проектная доступность, таблица 3); "
           "Ausenco, «Designing Circuits for High Availability»: цель 75 % для первичного дробления и 92 % для мельниц")


def _fit(seed: int = SEED, dt: float = 30.0) -> ParamSet:
    prm, _rows = calib.fit_2025(default(), seed, dt)
    return prm


# --------------------------------------------------------------------------------------------------------------
# availability
# --------------------------------------------------------------------------------------------------------------
def availability(prm: ParamSet, year: int = 2025, dt: float = 30.0, seed: int = SEED) -> dict:
    """Share of time each unit is in work in a calib-mode year with the fitted availability and the SAG stop calendar."""
    avail = prm["cal_avail"]
    p = calib.year_params(prm, year)
    t0, t1 = calib.calendar_min(year, 1, 1), calib.year_min(year)
    plant = Plant(p, seed, mode="calib", t0_min=t0, year=year, origin_doy=0)
    calib._set_liner(plant, p, year, t0, avail)
    rel = [w for w in calib.reline_windows(year, p) if w[2] > t0 and w[1] < t1]
    plant.set_relines(rel)
    stops = calib.line_stops(year, p, seed, avail)
    for line in calib.LINES:
        plant.set_downtime(line, [(a, b) for a, b in stops[line] if b > t0 and a < t1])
    cnt: dict[str, list[float]] = {"crusher": [0, 0, 0], "grinding": [0, 0, 0], "flotation": [0, 0, 0]}   # run, slow/starved, stop
    crush = {"run": 0.0, "run_hi": 0.0, "wait_ore": 0.0, "stock_full": 0.0, "stopped": 0.0}      # crusher time, in line-steps
    cap = p["crush_cap_tph"]
    cap_hi = TABLE["crush_cap_tph"].max               # the other end of the project range 4386-5043.9 t/h (OVOS), not known which one holds
    n = 0
    while plant.t_min < t1 - 1e-6:
        plant.step(dt)
        n += 1
        for ln in plant.state.lines:
            c, s, f = ln.crusher.state, ln.sag.state, ln.flot.state
            cnt["crusher"][0 if c == "RUN" else 1 if c == "SLOW" else 2] += 1
            cnt["grinding"][0 if s == "RUN" else 1 if s in ("STARVED", "LIMITED_GRID") else 2] += 1
            cnt["flotation"][0 if f == "RUN" else 1 if f == "UPSET" else 2] += 1
            # the crusher is a batch machine: it crushes at the rated rate while there is ore in the pocket and room on the
            # belt, and stands idle otherwise; the model averages the flows over a step, so the hours at the rated rate are
            # the crushed ore over the rated rate (the hour meter), the rest of a running step is waiting
            if c == "STOP":
                crush["stopped"] += 1.0
            else:
                duty = min(1.0, max(0.0, ln.crusher.tph) / cap)
                crush["run_hi"] += min(1.0, max(0.0, ln.crusher.tph) / cap_hi)
                crush["run"] += duty
                crush["stock_full" if c == "SLOW" else "wait_ore"] += 1.0 - duty
    m = n * len(plant.state.lines)
    out = {}
    for k, (run, part, stop) in cnt.items():
        lo, hi = LIT_AVAIL[k]
        # availability = not stopped (RUN + slowed/starved/upset still count as available); in_work = RUN only
        avail_pct = PCT * (run + part) / m
        run_pct = PCT * run / m
        ok = (lo - 2.0) <= run_pct <= (hi + 2.0)
        if k == "crusher":
            run_pct = PCT * crush["run"] / m           # hour meter: crushed ore / rated rate (the lower end of the project range)
            run_hi = PCT * crush["run_hi"] / m         # the same at the upper end of the range
            # the project gives a range of the rated rate, and the literature a range of availability: the check passes when the two overlap
            ok = run_hi <= hi + 2.0 and run_pct >= lo - 2.0
        out[k] = {"avail_pct": avail_pct, "run_pct": run_pct, "lit_lo": lo, "lit_hi": hi,
                  "ok": ok, "delta_pp": run_pct - (lo + hi) / 2.0, "class": "check"}
        if k == "grinding":
            # the grinding hours follow cal_avail, which is fitted to the ore of 2025: a fit, not a check
            out[k]["class"] = "fit"
            out[k]["ok"] = None
        if k == "crusher":
            out[k]["run_pct_range"] = [run_hi, run_pct]
            out[k]["cap_tph_range"] = [cap, cap_hi]
            # a requirement of the reported ore on the equipment: no tolerance verdict (no crusher nameplate exists to compare with)
            ore_per_crusher = prm["tgt_2025_ore_mt"] * 1e6 / len(plant.state.lines)
            rate_78 = ore_per_crusher / (0.78 * HOURS_YEAR)            # the rate at which the hours would be 78 % of the year (KIO read as hours)
            out[k]["class"] = "requirement"
            out[k]["ok"] = None
            out[k]["delta_pp"] = None
            out[k]["required_rates_tph"] = [cap, rate_78, cap_hi]
            out[k]["required_hours_pct"] = [PCT * ore_per_crusher / r / HOURS_YEAR for r in (cap, rate_78, cap_hi)]
            out[k]["design_hours_pct"] = PCT * DESIGN_CRUSH_H / HOURS_YEAR
        if k == "crusher":
            out[k]["state_run_pct"] = PCT * run / m           # the old measure: steps in the state RUN (any load)
            out[k]["breakdown_pct"] = {"crushing_at_rated_rate": PCT * crush["run"] / m,
                                       "waiting_for_ore_or_trucks": PCT * crush["wait_ore"] / m,
                                       "stockpile_full": PCT * crush["stock_full"] / m, "stopped": PCT * crush["stopped"] / m}
    return {"year": year, "steps": n, "units": out, "source": LIT_SRC, "design_crush_h": DESIGN_CRUSH_H,
            "fit_cal_avail": avail,
            "note": "«В работе» у мельниц и флотации — доля шагов в состоянии RUN (полная работа); допуск проверки ±2 п.п. к вилке литературы. "
                    "У дробилки — часы работы по счётчику: переработанная руда / темп участка крупного дробления (crush_cap_tph); остальное время "
                    "агрегат ждёт руду или самосвалы, ждёт места на складе или стоит. 4 386–5 044 т/ч (ОВОС, с. 26) — проектный темп участка с "
                    "коэффициентом неравномерности 1,15, а не паспорт дробилки, и какая из границ верна для руды Актогая, не сказано. Строка дробилки — "
                    "требование отчётного тоннажа к оборудованию (80,8 / 78,0 / 70,3 % часов года при 4 386 / 4 544 / 5 044 т/ч против 65,1 % часов по "
                    "проекту ОВОС: 285 сут × 2 смены × 10 ч), вердикта допуска у неё нет. Измельчение следует из готовности линии, подогнанной на руду "
                    "2025 г. (подгонка, не проверка); проверкой остаётся только флотация. "
                    "Собственные простои дробилки в годовом прогоне: короткие остановки, плановое обслуживание (пока стоит мельница линии), "
                    "замена брони внутри перефутеровки SAG. Доля шагов в состоянии RUN (state_run_pct) показывает только «не стоит», а не работу."}


# --------------------------------------------------------------------------------------------------------------
# reline events
# --------------------------------------------------------------------------------------------------------------
EVENTS = (
    # id, quarter, line, reference quarter, month, day, what the report says
    ("2023Q4-S1", "2023Q4", 1, "2023Q3", 10, 15, "Sulphide 1: плановая перефутеровка SAG перенесена с августа на октябрь (отчёт Q3 2023); «reline moved from Q3» (Q4 2023)"),
    ("2023Q4-S2", "2023Q4", 2, "2023Q3", 11, 15, "Sulphide 2: «also due to a SAG mill reline in Q4» (Q4 2023); день допущен"),
    ("2024Q4-S2", "2024Q4", 2, "2024Q3", 10, 15, "Sulphide 2: плановое обслуживание SAG в октябре 2024 (Q4 2024)"),
    ("2025Q1-S1", "2025Q1", 1, "2024Q4", 1, 15, "Sulphide 1: перефутеровка SAG и шаровой в январе 2025 (Q1 2025)"),
    ("2025Q3-S2", "2025Q3", 2, "2025Q2", 8, 15, "Sulphide 2: перефутеровка SAG в августе 2025, −5 % к Q2 (Q3 2025)"),
)


def _days(q: str) -> int:
    """Days of a quarter: the quarters of the events differ by 1-3 days, so the reported drop is also given per day."""
    import calendar
    y, n = bt.parse_quarter(q)
    return sum(calendar.monthrange(y, m)[1] for m in range(3 * (n - 1) + 1, 3 * (n - 1) + 4))


def _line_ore(res: dict, line: int) -> float:
    return res[f"ore_kt_l{line}"]


def relines(prm: ParamSet, rows: list[dict], dt: float = 30.0, seed: int = SEED) -> dict:
    """Event back-test: reference quarter fixes the availability; the event quarter is run with and without the reline."""
    quarters = {r["q"]: r for r in bt.load_quarters()}
    brow = {r["q"]: r for r in rows}
    out = []
    saved = calib.RELINE_CALENDAR
    dur_h = prm["liner_reline_h"]
    try:
        for eid, q, line, ref, month, day, what in EVENTS:
            year, qn = bt.parse_quarter(q)
            ry, rq = bt.parse_quarter(ref)
            a_ref = brow[ref]["avail"]
            ev = Reline(line, year, month, day, "KAZ Minerals production report " + q, "fact", "reline")
            t_year = calib.year_min(year)
            a_with = a_ref - dur_h * 60.0 / t_year          # the reline comes on top of the random stops of the reference
            calib.RELINE_CALENDAR = ()
            calib.clear_cache()
            without = calib.run_quarter(prm, year, qn, seed, dt, availability=a_ref, grade=quarters[q]["grade_pct"])
            calib.RELINE_CALENDAR = (ev,)
            calib.clear_cache()
            with_ = calib.run_quarter(prm, year, qn, seed, dt, availability=a_with, grade=quarters[q]["grade_pct"])
            rep_ev, rep_ref = quarters[q], quarters[ref]
            key = "ore1_kt" if line == 1 else "ore2_kt"
            obs_drop = PCT * (rep_ev[key] / rep_ref[key] - 1.0)
            obs_pday = PCT * ((rep_ev[key] / _days(q)) / (rep_ref[key] / _days(ref)) - 1.0)
            pred_drop = PCT * (_line_ore(with_, line) / _line_ore(without, line) - 1.0)
            out.append({
                "id": eid, "quarter": q, "line": line, "ref": ref, "what": what, "date_assumed": f"{day:02d}.{month:02d}.{year}",
                "obs_drop_pct": obs_drop, "obs_drop_per_day_pct": obs_pday, "pred_drop_pct": pred_drop,
                "ore_rep_kt": rep_ev[key], "ore_ref_kt": rep_ref[key],
                "ore_with_kt": _line_ore(with_, line), "ore_without_kt": _line_ore(without, line),
                "err_with_pct": PCT * (_line_ore(with_, line) / rep_ev[key] - 1.0),
                "err_without_pct": PCT * (_line_ore(without, line) / rep_ev[key] - 1.0),
                "url": rep_ev["url"], "page": rep_ev["page"],
            })
    finally:
        calib.RELINE_CALENDAR = saved
        calib.clear_cache()
    for r in out:
        r["better_with"] = abs(r["err_with_pct"]) < abs(r["err_without_pct"])
        r["diff_pp"] = r["pred_drop_pct"] - r["obs_drop_pct"]
        r["diff_per_day_pp"] = r["pred_drop_pct"] - r["obs_drop_per_day_pct"]
    n = len(out)
    sens = {}
    for h in (72.0, 84.0):
        pp = prm.copy(liner_reline_h=h)
        diffs = []
        for eid, q, line, ref, month, day, what in EVENTS:
            year, qn = bt.parse_quarter(q)
            a_ref = brow[ref]["avail"]
            ev = Reline(line, year, month, day, "KAZ Minerals production report " + q, "fact", "reline")
            t_year = calib.year_min(year)
            calib.RELINE_CALENDAR = ()
            calib.clear_cache()
            wo = calib.run_quarter(pp, year, qn, seed, dt, availability=a_ref, grade=quarters[q]["grade_pct"])
            calib.RELINE_CALENDAR = (ev,)
            calib.clear_cache()
            wi = calib.run_quarter(pp, year, qn, seed, dt, availability=a_ref - h * 60.0 / t_year, grade=quarters[q]["grade_pct"])
            key = "ore1_kt" if line == 1 else "ore2_kt"
            obs = quarters[q][key] / quarters[ref][key] - 1.0
            diffs.append((PCT * (_line_ore(wi, line) / _line_ore(wo, line) - 1.0), PCT * obs))
        calib.RELINE_CALENDAR = ()
        calib.clear_cache()
        sens[f"{h:.0f}"] = {"mean_pred_pct": st.mean(d[0] for d in diffs), "mean_obs_pct": st.mean(d[1] for d in diffs),
                            "mae_drop_pp": st.mean(abs(d[0] - d[1]) for d in diffs)}
    calib.RELINE_CALENDAR = saved
    calib.clear_cache()
    return {
        "events": out, "reline_h": dur_h, "sensitivity_reline_h": sens,
        "mean_obs_pct": st.mean(r["obs_drop_pct"] for r in out), "mean_pred_pct": st.mean(r["pred_drop_pct"] for r in out),
        "mean_obs_per_day_pct": st.mean(r["obs_drop_per_day_pct"] for r in out),
        "mean_diff_per_day_pp": st.mean(r["diff_per_day_pp"] for r in out),
        "n_model_deeper_per_day": sum(1 for r in out if r["diff_per_day_pp"] < 0.0),
        "mae_with_pct": st.mean(abs(r["err_with_pct"]) for r in out),
        "mae_without_pct": st.mean(abs(r["err_without_pct"]) for r in out),
        "mae_drop_pp": st.mean(abs(r["diff_pp"]) for r in out), "n": n,
        "n_better_with": sum(1 for r in out if r["better_with"]),
        "note": "падение руды линии в квартале события: модель (то же квартальное состояние, окно перефутеровки "
                f"{dur_h:.0f} ч сверх случайных остановок опорного квартала) против отчёта (квартал к опорному). В отчётном "
                "падении есть и другие причины (марка руды, прочие остановки), поэтому совпадение — ориентир, не точное измерение.",
    }


# --------------------------------------------------------------------------------------------------------------
# forward test 2026
# --------------------------------------------------------------------------------------------------------------
def load_2026(path: str = CSV_2026) -> list[dict]:
    out = []
    with open(path, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            year, qn = bt.parse_quarter(r["quarter"])
            out.append({"q": r["quarter"], "year": year, "qn": qn, "ore_kt": float(r["sulphide_ore_kt"]),
                        "grade_pct": float(r["grade_pct"]), "cu_kt": float(r["cu_conc_kt"]),
                        "url": r["source_url"], "page": r["source_page"]})
    return out


def forward_2026(prm: ParamSet, rows: list[dict], dt: float = 30.0, seed: int = SEED) -> dict:
    """Q1 and Q2 2026: totals only (no plant split, no recovery printed). Model fitted on 2025."""
    q25 = {r["q"]: r for r in bt.load_quarters()}
    res = []
    for rep in load_2026():
        cal_ore = rep["ore_kt"]
        # (a) ore given, as in the back-test: Cu in concentrate and implied recovery
        pts, reached = bt.solve_quarter(prm, rep["year"], rep["qn"], cal_ore, rep["grade_pct"], (), seed, dt)
        a_best, best = min(pts, key=lambda p: abs(p[1]["ore_kt"] / cal_ore - 1.0))
        # (b) blind: the 2025 availability, no ore from the report
        blind = calib.run_quarter(prm, rep["year"], rep["qn"], seed, dt, availability=prm["cal_avail"], grade=rep["grade_pct"])
        same_q_2025 = q25[f"2025Q{rep['qn']}"]
        mean_2025 = st.mean(q25[f"2025Q{k}"]["ore_kt"] for k in range(1, 5))
        cu_const = cal_ore * rep["grade_pct"] / PCT * prm["flot_rec_ref_pct"] / PCT
        implied = PCT * rep["cu_kt"] / (cal_ore * rep["grade_pct"] / PCT)
        round_pp = PCT * prm["tol_grade_round_pct"] / rep["grade_pct"]       # grade is printed to 0.01 %
        res.append({
            "q": rep["q"], "ore_rep": cal_ore, "grade_rep": rep["grade_pct"], "cu_rep": rep["cu_kt"],
            "rec_implied": implied, "rec_implied_pm": implied * round_pp / PCT,
            "rec_model": best["rec_pct"], "rec_const": prm["flot_rec_ref_pct"],
            "cu_model": best["cu_kt"], "cu_const": cu_const,
            "cu_err_model_pct": PCT * (best["cu_kt"] / rep["cu_kt"] - 1.0),
            "cu_err_const_pct": PCT * (cu_const / rep["cu_kt"] - 1.0),
            "avail_solved": a_best, "ore_reached": bool(reached),
            "blind_ore": blind["ore_kt"], "blind_ore_err_pct": PCT * (blind["ore_kt"] / cal_ore - 1.0),
            "blind_cu": blind["cu_kt"], "blind_cu_err_pct": PCT * (blind["cu_kt"] / rep["cu_kt"] - 1.0),
            "persist_same_q_pct": PCT * (same_q_2025["ore_kt"] / cal_ore - 1.0),
            "persist_mean_pct": PCT * (mean_2025 / cal_ore - 1.0),
            "tol_cu_pct": PCT * prm["tol_cu_frac"] + PCT * prm["tol_grade_round_pct"] / rep["grade_pct"],
            "url": rep["url"], "page": rep["page"],
        })
    return {
        "quarters": res,
        "note": "Q1 и Q2 2026 — данные, которых модель не видела (подгонка на 2025 г.). В отчётах 2026 нет разбивки по фабрикам "
                "и нет извлечения: оно получено как медь в концентрате / (руда × содержание) и несёт ошибку округления содержания "
                "(±0,005 % Cu, около ±1,2 п.п.). Квартал 3 2026 (пожар ВВД 09.08, отключение сети 14.08): отчёта ещё нет, оценки "
                "потерь в открытых источниках нет — сравнить с нашими сценариями hpgr_fire и grid нечем.",
    }


# --------------------------------------------------------------------------------------------------------------
# recovery refit
# --------------------------------------------------------------------------------------------------------------
def _lsq(xs: list[float], ys: list[float]) -> tuple[float, float]:
    mx, my = st.mean(xs), st.mean(ys)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    return my - b * mx, b


def _run_rows(prm: ParamSet, quarters: list[dict], jobs: int, dt: float, seed: int) -> list[dict]:
    args = [(r, prm.overrides(), seed, dt) for r in quarters]
    if jobs > 1:
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            return list(ex.map(bt._run_one_args, args))
    return [bt.run_one(*a) for a in args]


def recovery(prm: ParamSet, rows: list[dict], jobs: int = 4, dt: float = 30.0, seed: int = SEED) -> dict:
    """Refit of the grade slope and level on the quarters before 2023, test on 2023-2025 (12 quarters)."""
    quarters = bt.load_quarters()
    test_q = [r for r in quarters if r["year"] >= 2023]
    out: dict = {"variants": []}
    kc = flotation._base_stage_share(prm)
    s0 = prm["flot_grade_pp_ln"]
    brow = {r["q"]: r for r in rows}
    test_rows_now = [brow[r["q"]] for r in test_q]
    n = len(test_q)

    def mae(vals):
        return sum(abs(v - r["rec_pct"]) for v, r in zip(vals, test_q)) / n

    rep_mean_train = {}
    for name, kinds in (("single", ("single",)), ("single+ramp", ("single", "ramp"))):
        tr = [brow[r["q"]] for r in quarters if r["year"] < 2023 and brow[r["q"]]["kind"] in kinds]
        a, b = _lsq([math.log(r["grade_rep"] / G0) for r in tr], [r["rec_rep"] - r["rec_mod"] for r in tr])
        p2 = prm.copy(flot_grade_pp_ln=max(0.0, s0 + b), flot_rinf0_pct=prm["flot_rinf0_pct"] + a / kc)
        rows2 = _run_rows(p2, test_q, jobs, dt, seed)
        train_mean = st.mean(r["rec_rep"] for r in tr)
        rep_mean_train[name] = train_mean
        out["variants"].append({
            "train": name, "n_train": len(tr), "d_slope": b, "d_level_pp": a, "slope_refit": p2["flot_grade_pp_ln"],
            "slope_analog": s0, "train_mean_rec": train_mean,
            "mae_refit": mae([r["rec_mod"] for r in rows2]),
            "mae_const_train_mean": mae([train_mean] * n),
            "refit_rows": [{"q": r["q"], "rec_mod": r["rec_mod"], "rec_rep": r["rec_rep"]} for r in rows2],
        })
    out["mae_model_2025fit"] = mae([r["rec_mod"] for r in test_rows_now])
    out["mae_const_2025"] = mae([prm["flot_rec_ref_pct"]] * n)
    out["n_test"] = n
    # the same two models over 2023-2024 only (true out of sample for the 2025 fit)
    t24 = [r for r in test_q if r["year"] <= 2024]
    out["n_test_2023_24"] = len(t24)
    out["mae_model_2023_24"] = st.mean(abs(brow[r["q"]]["rec_mod"] - r["rec_pct"]) for r in t24)
    out["mae_const_2023_24"] = st.mean(abs(prm["flot_rec_ref_pct"] - r["rec_pct"]) for r in t24)
    out["wins_model_2023_24"] = sum(1 for r in t24 if abs(brow[r["q"]]["rec_mod"] - r["rec_pct"]) < abs(prm["flot_rec_ref_pct"] - r["rec_pct"]))
    # all 28 quarters (as in the back-test): model, constant
    allq = [r for r in quarters if r["year"] != 2025]
    out["mae_model_all28"] = st.mean(abs(brow[r["q"]]["rec_mod"] - r["rec_pct"]) for r in allq)
    out["mae_const_all28"] = st.mean(abs(prm["flot_rec_ref_pct"] - r["rec_pct"]) for r in allq)
    best = min(out["variants"], key=lambda v: v["mae_refit"])
    out["verdict"] = ("refit_worse" if best["mae_refit"] > out["mae_model_2025fit"] else "refit_better")
    out["kept"] = "2025fit" if out["verdict"] == "refit_worse" else "refit"
    return out


# --------------------------------------------------------------------------------------------------------------
# spread of the ore (grade) from quarter to quarter
# --------------------------------------------------------------------------------------------------------------
def quarterly_spread(prm: ParamSet, n_seeds: int = 30, quarters: int = 12, blocks_per_q: int = 1000,
                     with_recovery: bool = True, n_rec: int = 12) -> dict:
    """SD of the quarter-to-quarter change of the quarter-mean block grade: reported (28 test quarters) against
    sampled blocks with the mine-plan variability off and on (ore.draw_block, parameters blk_plan_*)."""
    from sim import ore
    rep = bt.load_quarters()
    g = [r["grade_pct"] for r in rep if r["year"] != 2025]
    # real series: change from one quarter to the next, ln; single plant and two plants mixed, as reported
    dl = [math.log(b / a) for a, b in zip(g, g[1:])]
    rec = [r["rec_pct"] for r in rep if r["year"] != 2025 and not ((2021, 4) <= (r["year"], r["qn"]) <= (2022, 4))]
    drec = [b - a for a, b in zip(rec, rec[1:])]
    out = {"reported_sd_dln": st.pstdev(dl), "reported_n": len(dl), "reported_mean_dln": st.mean(dl),
           "reported_rec_sd_pp": st.pstdev(rec), "reported_rec_sd_change_pp": st.pstdev(drec), "reported_rec_n": len(rec)}
    for tag, on in (("off", 0.0), ("on", 1.0)):
        p = prm.copy(blk_plan_on=on)
        sds, recsd = [], []
        for s in range(1, n_seeds + 1):
            means = []
            for q in range(quarters):
                tot = 0.0
                for b in range(blocks_per_q):
                    est, true = ore.draw_block(s, q * blocks_per_q + b + 1, p)
                    tot += true.cu_pct
                means.append(tot / blocks_per_q)
            d = [math.log(y / x) for x, y in zip(means, means[1:])]
            sds.append(st.pstdev(d))
        out[f"model_{tag}_sd_dln"] = st.mean(sds)
        if with_recovery:
            # recovery of twelve independent quarters (seeds), same grade, 2025 fit: spread of the level
            recs = [calib.run_quarter(p, 2025, 3, 100 + i, 30.0, availability=0.93, grade=0.41)["rec_pct"] for i in range(n_rec)]
            out[f"model_{tag}_rec_sd_pp"] = st.pstdev(recs)
    out["rec_note"] = ("разброс извлечения между 12 независимыми кварталами модели (разные зёрна) при одном содержании; в отчётах — "
                       "разброс уровня и квартального изменения 23 кварталов без разгона второй фабрики")
    return out


# --------------------------------------------------------------------------------------------------------------
def run(only: set[str], jobs: int, dt: float = 30.0, seed: int = SEED) -> dict:
    t0 = time.perf_counter()
    doc: dict = {"kind": "akt-fidelity", "version": 1, "generated": time.strftime("%Y-%m-%d"), "seed": seed, "dt_min": dt}
    with open(bt.OUT_PATH, encoding="utf-8") as f:
        fit = json.load(f)["fit"]
    prm = default().copy(**fit)                     # the fit of the committed back-test (run.py backtest)
    doc["fit"] = {k: prm[k] for k in ("cal_avail", "sag_k", "flot_rinf0_pct")}
    with open(bt.OUT_PATH, encoding="utf-8") as f:         # the committed quarterly back-test (run.py backtest) of the same fit
        bdoc = json.load(f)
    doc["backtest_summary"] = bdoc["summary"]["all"]
    rows = bdoc["rows"]
    if "availability" in only:
        doc["availability"] = availability(prm, 2025, dt, seed)
    if "relines" in only:
        doc["relines"] = relines(prm, rows, dt, seed)
    if "forward" in only:
        doc["forward_2026"] = forward_2026(prm, rows, dt, seed)
    if "recovery" in only:
        doc["recovery"] = recovery(prm, rows, jobs, dt, seed)
    if "spread" in only:
        doc["spread"] = quarterly_spread(prm)
    doc["seconds"] = round(time.perf_counter() - t0, 1)
    return doc


def _round(x, nd=4):
    if isinstance(x, float):
        return round(x, nd) if math.isfinite(x) else None
    if isinstance(x, list):
        return [_round(v, nd) for v in x]
    if isinstance(x, dict):
        return {k: _round(v, nd) for k, v in x.items()}
    return x


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Behaviour fidelity checks of 24.10.2026")
    ap.add_argument("--only", default="availability,relines,forward,recovery,spread")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--out", default=OUT_PATH)
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    only = {x.strip() for x in a.only.split(",") if x.strip()}
    doc = run(only, a.jobs)
    if only != {"availability", "relines", "forward", "recovery", "spread"} and os.path.exists(a.out):
        with open(a.out, encoding="utf-8") as f:           # a partial run replaces only its own parts
            old = json.load(f)
        old.update({k: v for k, v in doc.items() if k in ("availability", "relines", "forward_2026", "recovery", "spread", "seconds")})
        doc = old
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(_round(doc), f, ensure_ascii=False, indent=1, allow_nan=False)
        f.write("\n")
    print("wrote", a.out, doc["seconds"], "s")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
