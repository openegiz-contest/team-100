"""What the quarterly reports of KAZ Minerals say about the cost of a SAG reline, and how the model's 84 h compares (VALIDATION.md 6.3 and 6.8).

Standard library only. Reads `sim/data/kaz_quarterly.csv` (ore of each line per quarter, 2023-2025) and `sim/data/fidelity.json`
(the model's drop of the line's ore in the five event quarters). Prints, with the IDs of the brief of 24.10.2026:

  C6   drop of the line's ore per DAY in the five events of the reports (the quarters differ by 1-3 days), report against model
  C7   regression on the 24 line-quarters 2023-2025 (line level, line trend, reline dummy): the reline effect in %, t interval
       and the residual bootstrap, for every labelling of the quarters that is defensible (the labelling is a choice, so all of them)
  C8   the same effect in line-hours and in copper at the report's average of 13.67 t Cu per line-hour; the model's -5.47 % in hours
  C11  the noise: standard deviation of the quarter-to-quarter change of a line's ore per day, with and without event quarters

The reports give no reline duration, so none of this fixes the 84 h of the model (Minera Chinalco, an analog); it says whether the model's drop is
inside what the reports can show. The trend base of the regression was chosen after the first result: that is said in 6.3.

  python -I aktogay/scripts/reline_check.py [--csv PATH] [--fidelity PATH] [--json]
"""
from __future__ import annotations

import calendar
import csv
import json
import math
import os
import random
import statistics as st
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CSV_PATH = os.path.join(ROOT, "sim", "data", "kaz_quarterly.csv")
FID_PATH = os.path.join(ROOT, "sim", "data", "fidelity.json")

FIRST = "2023Q1"
# SAG relines (or planned SAG service) named by the reports, per line, in the quarter of the event
NAMED = {1: {"2023Q4", "2024Q1", "2025Q1"}, 2: {"2023Q4", "2024Q4", "2025Q3"}}
DOCS5 = {1: {"2023Q4", "2025Q1"}, 2: {"2023Q4", "2024Q4", "2025Q3"}}             # the five events of VALIDATION 6.3 (no 2024Q1-S1)
# planned maintenance of the plant without a named SAG reline
OTHER = {1: {"2023Q2", "2024Q2", "2025Q2"}, 2: {"2023Q1", "2023Q3"}}
DEC25 = "2025Q4"                                                                  # planned maintenance of both plants in December 2025, kind not named
# the events of the model back-test (fidelity.json): id -> (quarter, line, reference quarter)
EVENTS = (("2023Q4-S1", "2023Q4", 1, "2023Q3"), ("2023Q4-S2", "2023Q4", 2, "2023Q3"), ("2024Q4-S2", "2024Q4", 2, "2024Q3"),
          ("2025Q1-S1", "2025Q1", 1, "2024Q4"), ("2025Q3-S2", "2025Q3", 2, "2025Q2"))
LINE_HOUR_CU_T = 220.3e3 / 2.0 / 8059.0                                           # t Cu per line-hour: 220.3 kt / 2 lines / 8 059 h (C4)
T975 = {10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
        21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060}


def load(path: str = CSV_PATH) -> dict[str, dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return {r["quarter"]: r for r in csv.DictReader(f)}


def days(q: str) -> int:
    y, n = int(q[:4]), int(q[-1])
    m0 = 3 * (n - 1) + 1
    return sum(calendar.monthrange(y, m)[1] for m in range(m0, m0 + 3))


def ore(rows: dict, q: str, line: int) -> float:
    return float(rows[q]["sulphide%d_ore_kt" % line])


def per_day(rows: dict, q: str, line: int) -> float:
    return ore(rows, q, line) / days(q)


# ------------------------------------------------------------------------------------------ C6
def c6(rows: dict, fidelity: dict | None) -> dict:
    out = []
    for eid, q, line, ref in EVENTS:
        raw = 100.0 * (ore(rows, q, line) / ore(rows, ref, line) - 1.0)
        pday = 100.0 * (per_day(rows, q, line) / per_day(rows, ref, line) - 1.0)
        out.append({"id": eid, "raw_pct": raw, "per_day_pct": pday, "days": [days(ref), days(q)]})
    res = {"events": out, "mean_raw_pct": st.fmean(e["raw_pct"] for e in out), "mean_per_day_pct": st.fmean(e["per_day_pct"] for e in out)}
    if fidelity:
        model = {e["id"]: e["pred_drop_pct"] for e in fidelity["relines"]["events"]}
        for e in out:
            e["model_pct"] = model[e["id"]]
            e["model_minus_report_pp"] = e["model_pct"] - e["per_day_pct"]
        res["mean_model_pct"] = st.fmean(e["model_pct"] for e in out)
        res["model_deeper_in"] = sum(1 for e in out if e["model_minus_report_pp"] < 0)
        res["mean_model_minus_report_pp"] = st.fmean(e["model_minus_report_pp"] for e in out)
    return res


# ------------------------------------------------------------------------------------------ C7
def _solve(X: list[list[float]], y: list[float]):
    k = len(X[0])
    A = [[sum(X[i][a] * X[i][b] for i in range(len(y))) for b in range(k)] for a in range(k)]
    v = [sum(X[i][a] * y[i] for i in range(len(y))) for a in range(k)]
    M = [A[i][:] + [v[i]] for i in range(k)]
    for c in range(k):
        p = max(range(c, k), key=lambda r: abs(M[r][c]))
        M[c], M[p] = M[p], M[c]
        for r in range(k):
            if r != c:
                f = M[r][c] / M[c][c]
                M[r] = [M[r][j] - f * M[c][j] for j in range(k + 1)]
    b = [M[i][k] / M[i][i] for i in range(k)]
    I = [[1.0 if i == j else 0.0 for j in range(k)] for i in range(k)]
    M = [A[i][:] + I[i] for i in range(k)]
    for c in range(k):
        p = max(range(c, k), key=lambda r: abs(M[r][c]))
        M[c], M[p] = M[p], M[c]
        piv = M[c][c]
        M[c] = [x / piv for x in M[c]]
        for r in range(k):
            if r != c:
                f = M[r][c]
                M[r] = [M[r][j] - f * M[c][j] for j in range(2 * k)]
    return b, [row[k:] for row in M]


def regression(rows: dict, event: dict[int, set], extra: dict[int, set] | None = None, boot: int = 0, seed: int = 1) -> dict:
    """ore per day = line level + line trend + dummy of the reline quarters (+ dummy of other maintenance); the effect is in % of the mean rate."""
    qs = [q for q in sorted(rows) if q >= FIRST]
    X, y = [], []
    for ln in (1, 2):
        for i, q in enumerate(qs):
            row = [1.0 if ln == 1 else 0.0, 1.0 if ln == 2 else 0.0, i if ln == 1 else 0.0, i if ln == 2 else 0.0, 1.0 if q in event[ln] else 0.0]
            if extra is not None:
                row.append(1.0 if q in extra[ln] else 0.0)
            X.append(row)
            y.append(per_day(rows, q, ln))
    b, inv = _solve(X, y)
    k, n = len(b), len(y)
    res = [y[i] - sum(X[i][j] * b[j] for j in range(k)) for i in range(n)]
    s2 = sum(r * r for r in res) / (n - k)
    se = math.sqrt(s2 * inv[4][4])
    lvl = sum(y) / n
    t = T975.get(n - k, 2.1)
    out = {"n": n, "df": n - k, "level_kt_day": lvl, "effect_kt_day": b[4], "effect_pct": 100.0 * b[4] / lvl,
           "t_ci_pct": [100.0 * (b[4] - t * se) / lvl, 100.0 * (b[4] + t * se) / lvl], "resid_sd_pct": 100.0 * math.sqrt(s2) / lvl}
    if extra is not None:
        out["other_maintenance_pct"] = 100.0 * b[5] / lvl
    if boot:
        rng = random.Random(seed)
        bs = []
        for _ in range(boot):
            yb = [y[i] - res[i] + rng.choice(res) for i in range(n)]
            bs.append(_solve(X, yb)[0][4])
        bs.sort()
        out["bootstrap_ci_pct"] = [100.0 * bs[int(0.025 * boot)] / lvl, 100.0 * bs[int(0.975 * boot)] / lvl]
    return out


def c7(rows: dict) -> dict:
    dec = {ln: NAMED[ln] | {DEC25} for ln in (1, 2)}
    maint = {ln: OTHER[ln] for ln in (1, 2)}
    return {
        "named_6_events": regression(rows, NAMED, boot=4000),
        "docs_5_events": regression(rows, DOCS5),
        "named_plus_dec2025_as_reline": regression(rows, dec),
        "named_plus_other_maintenance": regression(rows, NAMED, maint),
        "named_plus_other_maintenance_and_dec2025_as_maintenance": regression(rows, NAMED, {ln: maint[ln] | {DEC25} for ln in (1, 2)}),
    }


# ------------------------------------------------------------------------------------------ C8
def c8(rows: dict, reg: dict, model_pct: float) -> dict:
    qs = [q for q in sorted(rows) if q >= FIRST]
    quarter_h = st.fmean(days(q) for q in qs) * 24.0                  # line-hours of an average quarter
    named = reg["named_6_events"]

    def hours(pct: float) -> float:
        return abs(pct) / 100.0 * quarter_h

    lo, hi = named["bootstrap_ci_pct"]
    h = hours(named["effect_pct"])
    return {"mean_quarter_days": quarter_h / 24.0, "line_hour_cu_t": LINE_HOUR_CU_T,
            "named_hours": h, "named_hours_ci": [hours(hi), hours(lo)],
            "named_cu_kt": h * LINE_HOUR_CU_T / 1000.0, "named_cu_kt_ci": [hours(hi) * LINE_HOUR_CU_T / 1000.0, hours(lo) * LINE_HOUR_CU_T / 1000.0],
            "docs5_hours": hours(reg["docs_5_events"]["effect_pct"]), "other_maintenance_hours": hours(reg["named_plus_other_maintenance"]["effect_pct"]),
            "model_pct": model_pct, "model_hours": hours(model_pct)}


# ------------------------------------------------------------------------------------------ C11
def c11(rows: dict) -> dict:
    qs = [q for q in sorted(rows) if q >= FIRST]
    allc, clean = [], []
    for ln in (1, 2):
        for i in range(1, len(qs)):
            a, b = qs[i - 1], qs[i]
            c = 100.0 * (per_day(rows, b, ln) / per_day(rows, a, ln) - 1.0)
            allc.append(c)
            if b not in NAMED[ln] and a not in NAMED[ln]:
                clean.append(c)
    return {"n_all": len(allc), "sd_all_pct": st.stdev(allc), "n_clean": len(clean), "sd_clean_pct": st.stdev(clean)}


# ------------------------------------------------------------------------------------------ C12
def c12(rows: dict) -> dict:
    """Other relines in the reports, per day: single-plant relines of Aktogay (II quarter 2019, I quarter 2020, line 1 in IV quarter 2022), the
    sixth event of the regression (2024Q1-S1) against the quarter before the postponed reline (2023Q3), and Bozshakol (analog) next to them."""
    def drop(q, ref, line=0):
        key = "sulphide_ore_kt" if line == 0 else "sulphide%d_ore_kt" % line
        return 100.0 * ((float(rows[q][key]) / days(q)) / (float(rows[ref][key]) / days(ref)) - 1.0)

    boz = 100.0 * ((8628.0 / 92.0) / (9159.0 / 91.0) - 1.0)          # Bozshakol, throughput of all processing, Q3 2025 against Q2 2025 (report of Q3 2025, p. 4)
    return {"single_plant": {"2019Q2": drop("2019Q2", "2019Q1"), "2020Q1": drop("2020Q1", "2019Q4"), "2022Q4-S1": drop("2022Q4", "2022Q3", 1)},
            "extra_2024q1_vs_2023q3_pct": drop("2024Q1", "2023Q3", 1), "bozshakol_2025q3_per_day_pct": boz}


def compute(csv_path: str = CSV_PATH, fid_path: str | None = FID_PATH) -> dict:
    rows = load(csv_path)
    fidelity = None
    if fid_path and os.path.exists(fid_path):
        with open(fid_path, encoding="utf-8") as f:
            fidelity = json.load(f)
    six = c6(rows, fidelity)
    reg = c7(rows)
    model_pct = six.get("mean_model_pct", -5.47)
    return {"c6": six, "c7": reg, "c8": c8(rows, reg, model_pct), "c11": c11(rows), "c12": c12(rows)}


def report(r: dict) -> str:
    out = ["C6  drop of the line's ore per day, event quarter against the quarter before (the quarters differ by 1-3 days)"]
    for e in r["c6"]["events"]:
        m = f"  model {e['model_pct']:+.2f} ({e['model_minus_report_pp']:+.2f} pp)" if "model_pct" in e else ""
        out.append(f"    {e['id']}: report {e['per_day_pct']:+.2f} % per day (raw {e['raw_pct']:+.2f} %, days {e['days'][0]} -> {e['days'][1]}){m}")
    c = r["c6"]
    out.append(f"    mean: report {c['mean_per_day_pct']:+.2f} % per day (raw {c['mean_raw_pct']:+.2f} %)"
               + (f", model {c['mean_model_pct']:+.2f} %, model deeper in {c['model_deeper_in']} of 5 by {abs(c['mean_model_minus_report_pp']):.2f} pp" if "mean_model_pct" in c else ""))
    out.append("C7  regression on 24 line-quarters 2023-2025 (line level + line trend + reline dummy), effect on the ore per day, %")
    for name, x in r["c7"].items():
        extra = f", other maintenance {x['other_maintenance_pct']:+.2f} %" if "other_maintenance_pct" in x else ""
        boot = f", bootstrap [{x['bootstrap_ci_pct'][0]:+.2f}; {x['bootstrap_ci_pct'][1]:+.2f}]" if "bootstrap_ci_pct" in x else ""
        out.append(f"    {name}: {x['effect_pct']:+.2f} % t-CI [{x['t_ci_pct'][0]:+.2f}; {x['t_ci_pct'][1]:+.2f}]{boot}, resid SD {x['resid_sd_pct']:.2f} %, df {x['df']}{extra}")
    h = r["c8"]
    out.append(f"C8  in line-hours (mean quarter {h['mean_quarter_days']:.2f} d): named events {h['named_hours']:.0f} h [{h['named_hours_ci'][0]:.0f}; {h['named_hours_ci'][1]:.0f}] "
               f"= {h['named_cu_kt']:.2f} kt Cu [{h['named_cu_kt_ci'][0]:.2f}; {h['named_cu_kt_ci'][1]:.2f}] at {h['line_hour_cu_t']:.2f} t Cu/h; "
               f"5 events of the docs {h['docs5_hours']:.0f} h; with the other-maintenance dummy {h['other_maintenance_hours']:.0f} h; model {h['model_pct']:+.2f} % = {h['model_hours']:.0f} h")
    n = r["c11"]
    out.append(f"C11 q/q standard deviation of a line's ore per day: all {n['n_all']} changes {n['sd_all_pct']:.2f} %, without event and post-event quarters {n['sd_clean_pct']:.2f} % (n {n['n_clean']})")
    k = r["c12"]
    out.append("C12 other relines per day: single plant " + ", ".join(f"{q} {v:+.1f} %" for q, v in k["single_plant"].items())
               + f"; 2024Q1-S1 against 2023Q3 {k['extra_2024q1_vs_2023q3_pct']:+.1f} %; Bozshakol (analog) Q3 2025 {k['bozshakol_2025q3_per_day_pct']:+.1f} %")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    csv_path, fid_path = CSV_PATH, FID_PATH
    if "--csv" in argv:
        csv_path = argv[argv.index("--csv") + 1]
    if "--fidelity" in argv:
        fid_path = argv[argv.index("--fidelity") + 1]
    r = compute(csv_path, fid_path)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(r, ensure_ascii=False, indent=1) if "--json" in argv else report(r))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
