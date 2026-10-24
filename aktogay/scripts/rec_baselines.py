"""What the reports can test about the recovery formula: every baseline against the model on quarters, half-years and years (VALIDATION.md 6.5, 6.9).

Standard library only. Reads `sim/data/kaz_quarterly.csv` (reported recovery, ore, grade, copper of 32 quarters) and `sim/data/backtest_q.json`
(the model's recovery of each quarter, ore and grade taken from the report: `sim/backtest.py`). Prints, with the IDs of the brief of 24.10.2026:

  C14  the spread of the reported recovery: two plants 2023-2025 (12 quarters), all 28 check quarters, one plant, without the ramp-up of plant 2;
       the correlation with the grade
  C15  does the quarterly recovery alternate (turning points of the series, quarter-of-year means)
  C16  half-years and years (feed-weighted recovery), reported and modelled
  C17  mean absolute error of the model and of every baseline: constant 87.2 % (the 2025 level, so a hindsight constant), the last report,
       the mean of the last four reports, the mean of all earlier reports, the mean of the test period itself (a hindsight constant), per
       quarter set, half-years 2023-2024 and years 2023-2024
  C20  recovery of 2026 implied by the reports (copper / (ore x grade)) and its rounding band

A baseline that uses the future (the 2025 constant, the mean of the test period) is marked: it is not a forecast, it is the best that a
constant can do when the answer is known. The formula is judged against it because the formula itself was fitted on 2025.

  python -I aktogay/scripts/rec_baselines.py [--csv PATH] [--backtest PATH] [--json]
"""
from __future__ import annotations

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
BT_PATH = os.path.join(ROOT, "sim", "data", "backtest_q.json")
CONST = 87.2                              # recovery of 2025 [fact]
RAMP = ("2021Q4", "2022Q4")                # ramp-up of plant 2
CSV_2026 = (("2026Q1", 15594.0, 0.41, 55.3), ("2026Q2", 16179.0, 0.41, 58.4))   # ore kt, grade %, Cu in concentrate kt (A21, A22)
GRADE_ROUND = 0.005                        # the grade is printed to 0.01 %


def load(csv_path: str = CSV_PATH, bt_path: str = BT_PATH) -> list[dict]:
    with open(csv_path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    with open(bt_path, encoding="utf-8") as f:
        bt = {r["q"]: r for r in json.load(f)["rows"]}
    out = []
    for x in rows:
        q = x["quarter"]
        d = {"q": q, "ore": float(x["sulphide_ore_kt"]), "g": float(x["grade_pct"]), "r": float(x["recovery_pct"]), "cu": float(x["cu_conc_kt"]),
             "rm": float(bt[q]["rec_mod"]) if q in bt else None}
        d["feed"] = d["ore"] * d["g"] / 100.0
        out.append(d)
    return out


def mae(xs: list[float]) -> float:
    return st.fmean(abs(x) for x in xs)


# ------------------------------------------------------------------------------------------ C14
def spread(Q: list[dict]) -> dict:
    def ms(L):
        return {"n": len(L), "mean": st.fmean(L), "sd": st.stdev(L), "min": min(L), "max": max(L)}
    two = [d for d in Q if d["q"] >= "2023Q1"]
    out = {
        "two_plants_2023_2025": ms([d["r"] for d in two]),
        "check_28_2018_2024": ms([d["r"] for d in Q if d["q"] < "2025Q1"]),
        "one_plant_2018_2021Q3": ms([d["r"] for d in Q if d["q"] <= "2021Q3"]),
        "without_ramp": ms([d["r"] for d in Q if not (RAMP[0] <= d["q"] <= RAMP[1])]),
        "corr_grade_rec_two_plants": st.correlation([d["g"] for d in two], [d["r"] for d in two]),
        "corr_grade_rec_28": st.correlation([d["g"] for d in Q if d["q"] < "2025Q1"], [d["r"] for d in Q if d["q"] < "2025Q1"]),
        "pstdev_two_plants": st.pstdev([d["r"] for d in two]),
    }
    return out


# ------------------------------------------------------------------------------------------ C15
def alternating_probability(n: int) -> float:
    """Probability that every interior point of a random order of n different values is a turning point: 2 E_n / n! (E_n: Euler zigzag number)."""
    row = [1]
    for k in range(1, n + 1):                      # Seidel-Entringer triangle
        new = [0]
        for v in reversed(row):
            new.append(new[-1] + v)
        row = new
    return 2.0 * row[-1] / math.factorial(n)


def zigzag(Q: list[dict]) -> dict:
    def turns(x):
        return sum(1 for i in range(1, len(x) - 1) if (x[i] - x[i - 1]) * (x[i + 1] - x[i]) < 0)
    two = [d for d in Q if d["q"] >= "2023Q1"]
    r = [d["r"] for d in two]
    by: dict[str, list[float]] = {}
    for d in two:
        by.setdefault(d["q"][-1], []).append(d["r"])
    gm = st.fmean(r)

    def f_stat(groups):
        ssb = sum(len(v) * (st.fmean(v) - gm) ** 2 for v in groups.values())
        ssw = sum(sum((x - st.fmean(v)) ** 2 for x in v) for v in groups.values())
        return (ssb / 3.0) / (ssw / 8.0)

    f0 = f_stat(by)
    rng = random.Random(5)
    labs = [d["q"][-1] for d in two]
    hit, n = 0, 20000
    for _ in range(n):
        p = r[:]
        rng.shuffle(p)
        g: dict[str, list[float]] = {}
        for lab, x in zip(labs, p):
            g.setdefault(lab, []).append(x)
        if f_stat(g) >= f0:
            hit += 1
    return {"turns_of": [turns(r), len(r) - 2], "turns_ore": turns([d["ore"] for d in two]), "turns_grade": turns([d["g"] for d in two]),
            "turns_cu": turns([d["cu"] for d in two]), "all_turns_probability": alternating_probability(len(r)),
            "quarter_of_year_means": {k: [round(st.fmean(v), 2), v] for k, v in sorted(by.items())},
            "f": f0, "permutation_p": hit / n, "q2_vs_others": [st.fmean(by["2"]), st.fmean([x for k, v in by.items() if k != "2" for x in v])]}


# ------------------------------------------------------------------------------------------ C16, C17
def halves(Q: list[dict]) -> list[dict]:
    grp: dict[str, list[dict]] = {}
    for d in Q:
        grp.setdefault(d["q"][:4] + ("H1" if int(d["q"][5]) <= 2 else "H2"), []).append(d)
    out = []
    for k, L in grp.items():
        f = sum(d["feed"] for d in L)
        out.append({"h": k, "r": sum(d["r"] * d["feed"] for d in L) / f,
                    "rm": (sum(d["rm"] * d["feed"] for d in L) / f) if all(d["rm"] is not None for d in L) else None,
                    "g": f / sum(d["ore"] for d in L) * 100.0})
    return out


def years(Q: list[dict]) -> list[dict]:
    grp: dict[str, list[dict]] = {}
    for d in Q:
        grp.setdefault(d["q"][:4], []).append(d)
    out = []
    for k, L in grp.items():
        f = sum(d["feed"] for d in L)
        out.append({"y": k, "r": sum(d["r"] * d["feed"] for d in L) / f,
                    "rm": (sum(d["rm"] * d["feed"] for d in L) / f) if all(d["rm"] is not None for d in L) else None})
    return out


def quarter_baselines(Q: list[dict], lo: str, hi: str) -> dict:
    qs = [d["q"] for d in Q]
    idx = {q: i for i, q in enumerate(qs)}
    rec = {d["q"]: d["r"] for d in Q}
    S = [d for d in Q if lo <= d["q"] <= hi]

    def last(d):
        i = idx[d["q"]]
        return rec[qs[i - 1]] if i else None

    def ma4(d):
        i = idx[d["q"]]
        prev = [rec[p] for p in qs[max(0, i - 4):i]]
        return st.fmean(prev) if prev else None

    def past(d):
        i = idx[d["q"]]
        prev = [rec[p] for p in qs[:i]]
        return st.fmean(prev) if prev else None

    res = {"n": len(S), "model": mae([d["rm"] - d["r"] for d in S]), "const_87_2_hindsight": mae([CONST - d["r"] for d in S]),
           "period_mean_hindsight": mae([st.fmean(x["r"] for x in S) - d["r"] for d in S])}
    for name, fn in (("last_report", last), ("mean_last_4_reports", ma4), ("mean_all_earlier_reports", past)):
        res[name] = mae([fn(d) - d["r"] for d in S if fn(d) is not None])
    return res


def half_year_baselines(Q: list[dict]) -> dict:
    H = halves(Q)
    idx = {h["h"]: i for i, h in enumerate(H)}
    test = ["2023H1", "2023H2", "2024H1", "2024H2"]
    r = lambda k: H[idx[k]]["r"]               # noqa: E731
    return {"n": len(test), "model": mae([H[idx[h]]["rm"] - r(h) for h in test]), "const_87_2_hindsight": mae([CONST - r(h) for h in test]),
            "previous_half": mae([H[idx[h] - 1]["r"] - r(h) for h in test]), "const_2025H1_hindsight": mae([r("2025H1") - r(h) for h in test]),
            "period_mean_hindsight": mae([st.fmean(r(x) for x in test) - r(h) for h in test])}


def year_baselines(Q: list[dict]) -> dict:
    Y = years(Q)
    idx = {y["y"]: i for i, y in enumerate(Y)}
    test = ["2023", "2024"]
    r = lambda k: Y[idx[k]]["r"]               # noqa: E731
    return {"n": len(test), "model": mae([Y[idx[y]]["rm"] - r(y) for y in test]), "const_87_2_hindsight": mae([CONST - r(y) for y in test]),
            "previous_year": mae([Y[idx[y] - 1]["r"] - r(y) for y in test]), "period_mean_hindsight": mae([st.fmean(r(x) for x in test) - r(y) for y in test])}


# ------------------------------------------------------------------------------------------ C20
def forward_2026() -> dict:
    out = {}
    for q, ore, g, cu in CSV_2026:
        r = cu / (ore * g / 100.0) * 100.0
        out[q] = {"implied": r, "band": [cu / (ore * (g + GRADE_ROUND) / 100.0) * 100.0, cu / (ore * (g - GRADE_ROUND) / 100.0) * 100.0]}
    ore = sum(x[1] for x in CSV_2026)
    cu = sum(x[3] for x in CSV_2026)
    feed = sum(x[1] * x[2] / 100.0 for x in CSV_2026)
    out["H1"] = {"implied": 100.0 * cu / feed}
    return out


def compute(csv_path: str = CSV_PATH, bt_path: str = BT_PATH) -> dict:
    Q = load(csv_path, bt_path)
    H = halves(Q)
    Y = years(Q)
    return {
        "c14": spread(Q), "c15": zigzag(Q),
        "c16_halves": [{"h": h["h"], "report": h["r"], "model": h["rm"], "grade": h["g"]} for h in H],
        "c16_years": [{"y": y["y"], "report": y["r"], "model": y["rm"]} for y in Y],
        "c17": {"quarters_2023_2024": quarter_baselines(Q, "2023Q1", "2024Q4"), "quarters_2023_2025": quarter_baselines(Q, "2023Q1", "2025Q4"),
                "quarters_2018_2024": quarter_baselines(Q, Q[0]["q"], "2024Q4"), "half_years_2023_2024": half_year_baselines(Q),
                "years_2023_2024": year_baselines(Q)},
        "c20": forward_2026(),
    }


def report(r: dict) -> str:
    out = []
    s = r["c14"]
    out.append("C14 reported recovery, %: two plants 2023-2025 (12 q) mean {mean:.2f} SD {sd:.2f} [{min:.1f}; {max:.1f}]; 28 q mean {m28:.2f} SD {s28:.2f}; "
               "one plant mean {m1:.2f} SD {s1:.2f}; without the ramp-up mean {mr:.2f} SD {sr:.2f}; corr(grade, recovery) {c12:+.2f} (12 q), {c28:+.3f} (28 q); "
               "population SD of the 12 {ps:.2f}".format(
                   mean=s["two_plants_2023_2025"]["mean"], sd=s["two_plants_2023_2025"]["sd"], min=s["two_plants_2023_2025"]["min"], max=s["two_plants_2023_2025"]["max"],
                   m28=s["check_28_2018_2024"]["mean"], s28=s["check_28_2018_2024"]["sd"], m1=s["one_plant_2018_2021Q3"]["mean"], s1=s["one_plant_2018_2021Q3"]["sd"],
                   mr=s["without_ramp"]["mean"], sr=s["without_ramp"]["sd"], c12=s["corr_grade_rec_two_plants"], c28=s["corr_grade_rec_28"], ps=s["pstdev_two_plants"]))
    z = r["c15"]
    out.append(f"C15 the quarterly recovery of 2023-2025 turns {z['turns_of'][0]} times in {z['turns_of'][1]} possible (p {z['all_turns_probability']:.4f} for a random "
               f"order; ore {z['turns_ore']}, grade {z['turns_grade']}, Cu {z['turns_cu']}); quarter-of-year means "
               + ", ".join(f"Q{k} {v[0]}" for k, v in z["quarter_of_year_means"].items()) + f"; F {z['f']:.2f}, permutation p {z['permutation_p']:.3f}")
    out.append("C16 half-years (feed-weighted, report / model): " + "; ".join(f"{h['h']} {h['report']:.2f} / {h['model']:.2f}" for h in r["c16_halves"] if h["model"] is not None)
               + " | years: " + "; ".join(f"{y['y']} {y['report']:.2f} / {y['model']:.2f}" for y in r["c16_years"] if y["model"] is not None))
    out.append("C17 mean absolute error, pp (hindsight = uses the answer, not a forecast):")
    for k, v in r["c17"].items():
        out.append(f"    {k} (n {v['n']}): " + ", ".join(f"{a} {b:.2f}" for a, b in v.items() if a != "n"))
    f = r["c20"]
    out.append("C20 2026 from the reports: " + "; ".join(f"{q} {v['implied']:.2f}" + (f" [{v['band'][0]:.2f}; {v['band'][1]:.2f}]" if "band" in v else "") for q, v in f.items()))
    return "\n".join(out)


def main(argv: list[str]) -> int:
    csv_path, bt_path = CSV_PATH, BT_PATH
    if "--csv" in argv:
        csv_path = argv[argv.index("--csv") + 1]
    if "--backtest" in argv:
        bt_path = argv[argv.index("--backtest") + 1]
    r = compute(csv_path, bt_path)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(r, ensure_ascii=False, indent=1) if "--json" in argv else report(r))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
