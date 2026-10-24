"""On/off trial of the issue queue on the model: "by value" against "by loudness"
(evidence map, section 4 "experiment on the stand"; design section 5 for the
money rule, section 7 for the parameter ranges).

Unit: one model shift 08:00-20:00 (window 1) and the night to 08:00 of the
next day (window 2, catches a trouble carried into the night). Seeds seed0 ..
seed0 + N - 1 (default 1001..1100; the calibration uses seeds 1..100).

Troubles per shift: 2 (p 0.6) or 3 (p 0.4), drawn from the library with the
weights of the evidence map: crusher stop (mechanical fault "crusher:N",
crew-cpd, or lube-protection trip "trip:N", crew-kip) 1; hidden loss
(collector flowmeter drift "dose:N", crew-kip; clogged cyclone "cyclone:N",
crew-mill) 1; hard ore "hard:N" 1; grid cut "grid" 1; SAG reline "reline:N"
0.1. One trouble per node, start uniform 08:00-18:00, line 1 or 2. Oxidised
ore is left out: a preset oxide cause has no crew in the plant model and would
last to the end of the run in every copy, so it cannot tell the orders apart
(listed in the JSON notes). Shift parameters from the sensitivity table:
live stock of a line with a crusher trouble U(8, 16) kt, grid limit
U(180, 240) MW for U(1, 4) h, hard A*b U(24, 30), dose loss U(2, 4) pp;
repair lognormal with the table median and sigma_ln (default 0.4).

Common random numbers: repair, arrival and notice times come from
(seed, issue) in sim.events, the module's estimate error from
(seed, issue) here, the background (trucks, cloth change, noise) from
(seed, step): every copy of a seed sees the same draws.

Copies of one seed (same plant, same scenario):
  by_value  the twin finds a hidden trouble detect_min after its start
            (unless missed with probability miss, drawn from (seed, issue));
            every tact (5 model minutes) the known, unbooked troubles are
            booked in the order of policy.rank(troubles, now, prm) from
            modules/policy.py (akt-priority); until that file exists the
            stand-in rank_fallback below applies the money rule of design
            section 5. The ranking sees the module's estimates (measured
            values with noise and an estimate error); the result is read
            from the true counters, so a wrong ranking costs copper.
  by_loud   same twin and findings, but calls go in alarm order: a loud
            trouble at its tact, a quiet finding only loud_react_min later
            (advice waits for a human; a loud alarm in between goes first).
  no_twin   (--no-twin) "as now": the plant without the twin. Loud troubles are
            noticed by alarm after 5-15 min, hidden ones by the laboratory or
            the tails alarm. The operating decisions are taken as people take
            them today, only when they see the trouble (controller "asis"):
            a grid cut and a reline are visible at once (alarm, plan) and called
            asis_notice_min (10) after the start; hard ore is seen when it
            reaches the SAG (scen_hard_lead_h after the start) plus
            asis_notice_min. --no-asis gives the old baseline where nobody takes
            those decisions without the twin (it overstated the gain).
  base      no troubles (gives the absolute loss of each copy).

Grid call: a call made before the automatic shedding has no effect at once; it
is repeated at the next tact until the SAG of the shed line gets the headroom
(a dispatcher repeats it), and the plant latches it as well (Plant._c2_call).

Metric: D = Cu(by_value) - Cu(by_loud) in t Cu, at 20:00 and at 08:00;
positive = the money order gained. Printed: mean, median, SD, P10 / P90,
bootstrap 95 % CI (10 000 resamples; BCa for the mean, percentile for the
median), p0 = share of shifts with |D| < 0.05 t and p- = share with
D < -0.05 t, both with Wilson 95 % intervals, the Wilcoxon signed-rank test
(exact when there are no ties and n <= 60, else the normal approximation
with tie correction), cuts by number of troubles and by shared crew. The
same for D in USD and, with --no-twin, the detection contribution
Cu(by_loud) - Cu(no_twin). Everything is written to JSON.

Policy contract (modules/policy.py, owned by the modules component):
  rank(troubles: list[policy.Trouble], now_min, prm: modules.params.Prm,
       crews: {crew: [slot free minutes]}, seed) -> Plan with order[].id.
  The trial builds its trouble descriptors (dicts with issue, kind, line,
  node, crew, hidden, safety, t_known_min, loss_cu_tph, loss_usd_h,
  hours_to_loss, repair_h, repair_p90_h, arrive_h, crew_slots_free_min) and
  load_rank() maps them to that call; the module keeps its own parameter
  table (q_*), so what it believes about repair times is its own business.

  python -I aktogay/run.py trial --n 100 [--seed0 1001] [--kip 1] [--sigma-ln 0.4] [--miss 0]
      [--detect-min 75] [--loud-react 30] [--no-twin] [--no-asis] [--asis-notice 10] [--jobs 4]
      [--out trial.json]

Sensitivity options (same seeds, same draws otherwise):
  --set KEY=VALUE (repeatable): ParamSet override for every shift, applied before the shift's own
      drawn overrides (used for sens_lab_delay_h).
  --hidden-mult X: frequency of hidden troubles. The base draw of draw_shift is unchanged (same
      rng sequence, same loud troubles). X < 1: each hidden trouble is kept with probability X,
      u01(seed, 0, "sens-thin:" + issue). X > 1: for each hidden trouble of the base draw,
      round(X - 1) extra hidden troubles (kind uniform dose/cyclone, line 1/2, start U(08:00, 18:00),
      free node only) from rng_at(seed, 0, "sens-extra"); their miss draw uses the same key as the
      base ("trial-miss:" + issue). An extra dose with no dose in the base draw gets
      flot_dose_pp = U(2, 4) from the same extra stream.
  --mag X: magnitude of hidden troubles. flot_dose_pp (drawn U(2, 4) pp, table 3.5) x X;
      cyc_clog_p80_um (table 12 um per clogged cyclone) x X. Applied after the draw.
  Rows also carry recovery_pct and cu_feed_t per copy at 20:00 and the number of hidden troubles.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import random
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)          # also for the spawned worker processes of --jobs

from sim import events as ev  # noqa: E402
from sim import sensors as se  # noqa: E402
from sim.params import ParamSet, default  # noqa: E402
from sim.plant import Plant  # noqa: E402
from sim.state import MIN_PER_H, NO_VALUE, normal, rng_at, u01  # noqa: E402

EPS = 1e-6
PCT = 100.0
TACT_MIN = 5.0
ZERO_T = 0.05                    # |D| below this is "no gain" (evidence map, section 4)
Z95 = 1.959963984540054          # two-sided 95 % normal quantile

# Trouble library: (category, kinds, weight). A category is drawn by weight, its kind uniformly.
LIBRARY: tuple[tuple[str, tuple[str, ...], float], ...] = (
    ("crusher", ("crusher", "trip"), 1.0),
    ("hidden", ("dose", "cyclone"), 1.0),
    ("hard", ("hard",), 1.0),
    ("grid", ("grid",), 1.0),
    ("reline", ("reline",), 0.1),
)
HIDDEN = ("dose", "cyclone")
# Tier S of 23.10.2026 (opt-in, cfg["library"] = "tier_s"; the default library and so every draw of the N = 100 trial are
# unchanged): cyclone roping with ball mill overload (decision of the grinding operator), pH electrode drift (I&C), uneven
# HPGR feed on line 2 (mill crew), planned mantle change of a crusher (crew-cpd). Not added: icy and fatigue (S0, no money),
# oil and exc_down (the effect comes 11 h after the start, beyond the 12 h shift window of this design).
LIBRARY_TIER_S: tuple[tuple[str, tuple[str, ...], float], ...] = (
    ("roping", ("roping",), 0.3),
    ("ph", ("phdrift",), 0.3),
    ("hpgr", ("hpgr",), 0.3),
    ("mantle", ("mantle",), 0.1),
)
HIDDEN_TIER_S = ("roping", "phdrift", "hpgr")           # found by the module (circulating load, grab sample, skew), not by an alarm
# Without the twin: when people see them (min after the start): operators read the circulating load / skew on the screens,
# the grab sample of pH comes every sens_ph_lab_every_h hours, the metal detector trips after peb_hpgr_tramp_after_h (assumptions).
ASIS_SEE_MIN = {"roping": 45.0, "mantle": 10.0}
DECISION = ("hard", "grid", "reline", "roping")   # no crew: the call changes operation (blend, headroom, excavators, feed)

DEFAULTS = {
    "n": 100, "seed0": 1001, "kip": 1, "sigma_ln": 0.4, "miss": 0.0, "detect_min": 75.0,
    "loud_react_min": 30.0, "no_twin": False, "price": None, "p_two": 0.6, "start_span_h": 10.0,
    "est_sigma": 0.2, "tact_min": TACT_MIN, "boot": 10000, "jobs": 1,
    "set": {}, "hidden_mult": 1.0, "mag": 1.0, "asis": True, "asis_notice_min": 10.0,
    # experiment of 24.10.2026 (VALIDATION 8.6); every default keeps the 22.10 behaviour and numbers
    "copies": None, "crews": None, "call_delay_min": 0.0, "delay_kinds": None, "compliance": 1.0,
    "fine_tact_min": 1.0, "seeds": None,
    # alarm flood of the shift (modules/flood.py): copies whose states are looked at every 5 model minutes
    "alarms": None,
}
ALL_COPIES = ("by_value", "by_loud", "base", "no_twin", "novice", "value_nd", "nov_det", "nov_err", "nov_r", "nov_twin")
MODE_OF = {"by_value": "value", "by_loud": "loud", "no_twin": "asis", "novice": "novice", "value_nd": "value_nd",
           "nov_det": "novice_det", "nov_err": "novice_err", "nov_r": "novice_r", "nov_twin": "novice_twin"}
# novice from data (VALIDATION 8.9): seeing time x nov_detect_mult / slips of diagnosis and of a step / both / the twin with a novice who executes
NOVICE_DATA = ("novice_det", "novice_err", "novice_r")
FINE_MODES = ("novice", "value_nd") + NOVICE_DATA + ("novice_twin",)   # these act at the minute the people see the trouble (plant steps are 1 min)
NOTES = (
    "D = Cu(by_value) - Cu(by_loud), t Cu; positive = the money order gained [model estimate].",
    "no_twin = 'as now': operators take the hard-ore, grid and reline decisions when they see them "
    "(asis_notice_min after the alarm; hard ore when it reaches the SAG); --no-asis: nobody takes them.",
    "A grid call is repeated until the shed line's SAG gets the headroom (the plant latches it too).",
    "Oxidised ore is not in the library: a preset oxide cause has no crew in the plant model and never ends.",
    "Shared crew = two troubles of the shift need the same crew; only there can the order matter.",
    "The twin's detection delay (detect_min) and miss share are inputs here, not results of akt-losses.",
    "by_loud: a quiet finding is called loud_react_min after it; a loud alarm in between goes first.",
    "Repair, arrival and notice times are drawn from (seed, issue): the same in every copy.",
)


# ---------------------------------------------------------------------------
# Shift design
# ---------------------------------------------------------------------------
@dataclass
class Trouble:
    issue: str
    kind: str
    line: int
    node: str
    crew: str
    t_start_min: float
    hidden: bool
    t_found_min: float = NO_VALUE    # twin finding (hidden kinds): start + detect_min; NO_VALUE when missed
    missed: bool = False


@dataclass
class ShiftSpec:
    seed: int
    troubles: list[Trouble]
    overrides: dict[str, float]

    @property
    def text(self) -> str:
        return "+".join(t.issue for t in self.troubles)

    @property
    def shared_crew(self) -> bool:
        crews = [t.crew for t in self.troubles if t.crew]
        return len(crews) != len(set(crews))


def draw_shift(seed: int, cfg: dict) -> ShiftSpec:
    """Troubles and parameter overrides of one shift from (seed, 0, "trial"); deterministic."""
    rng = rng_at(seed, 0, "trial")
    n = 2 if rng.random() < cfg["p_two"] else 3
    cats = [c for c in (LIBRARY + LIBRARY_TIER_S if cfg.get("library") == "tier_s" else LIBRARY)]
    weights = [c[2] for c in cats]
    troubles: list[Trouble] = []
    nodes: set[str] = set()
    t0 = default()["cal_shift_start_h"] * MIN_PER_H
    for _ in range(100):
        if len(troubles) >= n:
            break
        cat = rng.choices(cats, weights)[0]
        kind = rng.choice(cat[1])
        line = 0 if kind in ev.SITE_KINDS else rng.choice((1, 2))
        if kind == "hpgr":
            line = 2                                   # the HPGR is in the model on line 2 only
        issue, node, crew = ev.issue_for(kind, line)
        start = t0 + rng.random() * cfg["start_span_h"] * MIN_PER_H
        if node in nodes:
            continue
        nodes.add(node)
        hidden = kind in HIDDEN or kind in HIDDEN_TIER_S
        tr = Trouble(issue, kind, line, node, crew, float(start), hidden)
        if hidden:
            tr.missed = u01(seed, 0, "trial-miss:" + issue) < cfg["miss"]
            tr.t_found_min = NO_VALUE if tr.missed else start + cfg["detect_min"]
        troubles.append(tr)
    troubles.sort(key=lambda t: t.t_start_min)
    ov: dict[str, float] = {"crew_sigma_ln": float(cfg["sigma_ln"])}
    kinds = {t.kind for t in troubles}
    for t in troubles:
        if t.kind in ("crusher", "trip"):
            ov[f"stock{t.line}_t0"] = rng.uniform(8000.0, 16000.0)
    if "grid" in kinds:
        ov["pow_c2_limit_mw"] = rng.uniform(180.0, 240.0)
        ov["pow_c2_h"] = rng.uniform(1.0, 4.0)
    if "hard" in kinds:
        ov["ore_axb_hard"] = rng.uniform(24.0, 30.0)
    if "dose" in kinds:
        ov["flot_dose_pp"] = rng.uniform(2.0, 4.0)
    if cfg.get("price"):
        ov["econ_cu_price_usd_t"] = float(cfg["price"])
    # ---- --hidden-mult: frequency of hidden troubles (after the unchanged base draw) ----
    mult = float(cfg.get("hidden_mult", 1.0))
    if mult < 1.0:
        troubles = [t for t in troubles
                    if not t.hidden or u01(seed, 0, "sens-thin:" + t.issue) < mult]
    elif mult > 1.0:
        extra_per = int(round(mult - 1.0))
        rng2 = rng_at(seed, 0, "sens-extra")
        nodes2 = {t.node for t in troubles}
        added: list[Trouble] = []
        for base_tr in [t for t in troubles if t.hidden]:
            for _k in range(extra_per):
                for _try in range(50):
                    kind = rng2.choice(HIDDEN)
                    line = rng2.choice((1, 2))
                    issue, node, crew = ev.issue_for(kind, line)
                    start = t0 + rng2.random() * cfg["start_span_h"] * MIN_PER_H
                    if node in nodes2:
                        continue
                    nodes2.add(node)
                    tr = Trouble(issue, kind, line, node, crew, float(start), True)
                    tr.missed = u01(seed, 0, "trial-miss:" + issue) < cfg["miss"]
                    tr.t_found_min = NO_VALUE if tr.missed else start + cfg["detect_min"]
                    added.append(tr)
                    break
        if any(t.kind == "dose" for t in added) and "flot_dose_pp" not in ov:
            ov["flot_dose_pp"] = rng2.uniform(2.0, 4.0)
        troubles = sorted(troubles + added, key=lambda t: t.t_start_min)
    # ---- --mag: magnitude of hidden troubles ----
    mag = float(cfg.get("mag", 1.0))
    if mag != 1.0:
        tab = default()
        ov["flot_dose_pp"] = float(ov.get("flot_dose_pp", tab["flot_dose_pp"])) * mag
        ov["cyc_clog_p80_um"] = float(tab["cyc_clog_p80_um"]) * mag
    return ShiftSpec(seed, troubles, ov)


def make_spec(plant: Plant, shift: ShiftSpec, cfg: dict):
    """ScenarioSpec of the shift: parse_scenario text, then the drawn start times."""
    spec = ev.parse_scenario(shift.text, plant.t_min, plant.prm, kip=int(cfg["kip"]), auto=True)
    starts = {t.issue: t.t_start_min for t in shift.troubles}
    for e in spec.events:
        issue = e.data.get("issue")
        if issue in starts:
            e.t_start_min = starts[issue]
    spec.events.sort(key=lambda e: e.t_start_min)
    return spec


# ---------------------------------------------------------------------------
# What the module sees: estimates of each trouble at decision time
# ---------------------------------------------------------------------------
def _valid(x) -> bool:
    return isinstance(x, (int, float)) and x != NO_VALUE and math.isfinite(x)


def descriptors(plant: Plant, troubles: list[Trouble], now: float, prm: ParamSet, seed: int,
                est_sigma: float, known_at) -> list[dict]:
    """Trouble dicts for policy.rank from the measured snapshot (module view, with estimate error)."""
    st = plant.state
    snap = se.measured_features(st, prm)
    base_cu = prm["cal_line_tph"] * prm["blk_cu_mean_pct"] / PCT * prm["flot_rec_ref_pct"] / PCT
    price = prm["econ_cu_price_usd_t"] * prm["econ_payable_frac"]
    lo, hi = prm["crew_arrive_lo_min"], prm["crew_arrive_hi_min"]
    out = []
    for tr in troubles:
        lines = (1, 2) if tr.line == 0 else (tr.line,)
        cu = 0.0
        rec = NO_VALUE
        for n in lines:
            ln = snap.get(f"line-{n}", {})
            c = ln.get("cu_tph", NO_VALUE)
            cu += c if _valid(c) and c > 0 else base_cu
            r = ln.get("recovery", NO_VALUE)
            rec = r if _valid(r) and r > 0 else prm["flot_rec_ref_pct"]
        err = math.exp(est_sigma * normal(seed, 0, "trial-est:" + tr.issue))
        hours = 0.0
        if tr.kind in ("crusher", "trip"):
            rate = cu
            sp = snap.get(f"stockpile-{tr.line}", {})
            h = sp.get("hours_left", NO_VALUE)
            if not (_valid(h) and h > 0):
                lvl, out_tph = sp.get("level_t", NO_VALUE), sp.get("out_tph", NO_VALUE)
                h = lvl / out_tph if _valid(lvl) and _valid(out_tph) and out_tph > 0 else 0.0
            hours = max(0.0, float(h))
        elif tr.kind == "dose":
            rate = cu * prm["flot_dose_pp"] / rec * err
        elif tr.kind == "cyclone":
            rate = cu * prm["hc_cyclone_n"] * prm["cyc_clog_p80_um"] / 10.0 * prm["flot_p80_pp_10um"] / rec * err
        elif tr.kind == "hard":
            rate = cu * 0.2 * err                       # about -23 % t/h, +1.8 pp recovery (design section 7)
            hours = prm["scen_hard_lead_h"]
        elif tr.kind == "grid":
            rate = cu * 0.25 * err                      # one line halves (design section 7, C2)
        elif tr.kind == "roping":                       # P80 up by cyc_rope_p80_um: recovery down by flot_p80_pp_10um per 10 um
            rate = cu * prm["flot_p80_pp_10um"] * prm["cyc_rope_p80_um"] / 10.0 / rec * err
        elif tr.kind == "phdrift":
            rate = cu * prm["flot_ph_pp_unit"] * prm["hc_ph_drift"] / rec * err
        elif tr.kind == "hpgr":                         # the pebble circuit of line 2 takes less: SAG t/h down
            rate = cu * 0.07 * err
        elif tr.kind == "mantle":                       # the crusher stands: the stockpile buys time
            rate = cu
            sp = snap.get(f"stockpile-{tr.line}", {})
            h = sp.get("hours_left", NO_VALUE)
            if not (_valid(h) and h > 0):
                lvl, out_tph = sp.get("level_t", NO_VALUE), sp.get("out_tph", NO_VALUE)
                h = lvl / out_tph if _valid(lvl) and _valid(out_tph) and out_tph > 0 else 0.0
            hours = max(0.0, float(h))
        else:
            rate = cu * err                             # reline: the line stops
        median = ev.work_median_h(tr.kind, prm)
        crew = st.crews.get(tr.crew)
        slots = [float(x) for x in crew.slot_free_min[:max(1, crew.count)]] if crew is not None else []
        out.append({
            "issue": tr.issue, "kind": tr.kind, "line": tr.line, "node": tr.node, "crew": tr.crew,
            "hidden": tr.hidden, "safety": "", "t_known_min": float(known_at(tr)),
            "loss_cu_tph": float(rate), "loss_usd_h": float(rate * price), "hours_to_loss": float(hours),
            "repair_h": float(median), "repair_p90_h": float(ev.p90_hours(median, prm)),
            "arrive_h": float(0.5 * (lo + hi) / MIN_PER_H),
            "crew_free_at_min": float(crew.free_at_min) if crew is not None else NO_VALUE,
            "crew_slots_free_min": slots,
        })
    return out


def rank_fallback(troubles: list[dict], now: float, prm: ParamSet) -> list[dict]:
    """Stand-in for modules.policy.rank: the money order of design section 5.

    Safety class first (S0, then S1), then decisions without a crew (sorted by
    loss rate), then per crew the order with the least expected loss over the
    horizon H = min(time to shift end, issue_horizon_h): loss_i = r_i x
    max(0, min(t_fix_i, now + H) - (now + T_i)), t_fix sequential from the
    crew's free time with arrival and the median repair; all permutations
    when a crew has at most 5 troubles, else the index r_i / (arrive + D_i).
    Crews are listed by the loss rate of their first trouble.
    """
    start = prm["cal_shift_start_h"] * MIN_PER_H
    shift = prm["cal_shift_h"] * MIN_PER_H
    end = math.floor((now - start) / shift + 1.0) * shift + start
    horizon_h = min((end - now) / MIN_PER_H, prm["issue_horizon_h"])
    order_s = {"S0": 0, "S1": 1}
    safety = sorted((t for t in troubles if t.get("safety") in order_s),
                    key=lambda t: (order_s[t["safety"]], -t.get("loss_cu_tph", 0.0)))
    rest = [t for t in troubles if t.get("safety") not in order_s]
    free = sorted((t for t in rest if not t.get("crew")), key=lambda t: -t.get("loss_cu_tph", 0.0))
    by_crew: dict[str, list[dict]] = {}
    for t in rest:
        if t.get("crew"):
            by_crew.setdefault(t["crew"], []).append(t)

    def cost(seq: list[dict]) -> float:
        free_at = max((t.get("crew_free_at_min", NO_VALUE) for t in seq), default=NO_VALUE)
        t_free = now if free_at == NO_VALUE or free_at < now else free_at
        total = 0.0
        for t in seq:
            t_fix = t_free + (t.get("arrive_h", 0.5) + t.get("repair_h", 1.0)) * MIN_PER_H
            t_loss = now + t.get("hours_to_loss", 0.0) * MIN_PER_H
            total += t.get("loss_cu_tph", 0.0) * max(0.0, min(t_fix, now + horizon_h * MIN_PER_H) - t_loss) / MIN_PER_H
            t_free = t_fix
        return total

    crews_out: list[list[dict]] = []
    for crew, items in by_crew.items():
        if len(items) <= 5:
            best = min(itertools.permutations(items),
                       key=lambda p: (cost(list(p)), tuple(x.get("t_known_min", 0.0) for x in p)))
            crews_out.append(list(best))
        else:
            crews_out.append(sorted(items, key=lambda t: -t.get("loss_cu_tph", 0.0)
                                    / max(EPS, t.get("arrive_h", 0.5) + t.get("repair_h", 1.0))))
    crews_out.sort(key=lambda seq: -seq[0].get("loss_cu_tph", 0.0))
    return safety + free + [t for seq in crews_out for t in seq]


def load_rank():
    """(ranking callable, its name): modules.policy.rank through an adapter when present, else the stand-in.

    The callable takes (trouble dicts of descriptors(), now_min, prm, seed)
    and returns issue keys in call order.
    """
    try:
        from modules import params as mparams  # akt-priority's own table (q_*), owned by the modules component
        from modules import policy
    except ImportError:
        return (lambda troubles, now, prm, seed=0: [t["issue"] for t in rank_fallback(troubles, now, prm)],
                "sim.trial.rank_fallback (stand-in: modules/policy.py not found)")
    mprm = mparams.default()

    def ranked(troubles: list[dict], now: float, prm: ParamSet, seed: int = 0) -> list[str]:
        tl = [policy.Trouble(id=d["issue"], node=d["node"], kind=d["kind"], safety=d.get("safety", ""),
                             rate_cu_tph=d["loss_cu_tph"], rate_usd_h=d["loss_usd_h"],
                             t_conseq_h=d["hours_to_loss"], repair_h=d["repair_h"], crew=d["crew"],
                             detected_at=d["t_known_min"], loud=not d.get("hidden", False)) for d in troubles]
        crews = {d["crew"]: list(d.get("crew_slots_free_min") or [NO_VALUE]) for d in troubles if d["crew"]}
        plan = policy.rank(tl, now, mprm, crews, seed)
        return [r.id for r in plan.order]

    return ranked, "modules.policy.rank"


# ---------------------------------------------------------------------------
# Copies and their controllers
# ---------------------------------------------------------------------------
class Controller:
    """Books crews on one copy at every tact from what the twin knows."""

    def __init__(self, plant: Plant, troubles: list[Trouble], mode: str, cfg: dict, seed: int, rank_fn):
        if mode not in ("value", "loud", "asis", "novice", "value_nd") + NOVICE_DATA + ("novice_twin",):
            raise ValueError("mode must be value, loud, asis, novice, value_nd, novice_det, novice_err, novice_r or novice_twin")
        self.plant, self.troubles, self.mode, self.cfg, self.seed, self.rank = plant, troubles, mode, cfg, seed, rank_fn
        self.booked: dict[str, dict] = {}
        self._nov_ready: dict[str, float] = {}           # novice from data: minute the call is made, drawn once per trouble
        self.period = float(cfg["tact_min"])            # run_shift lowers it to fine_tact_min when a minute-level copy is present

    def delay_of(self, tr: Trouble) -> float:
        """Call delay of the sweep (B1), min; zero for the kinds outside cfg["delay_kinds"]."""
        d = float(self.cfg.get("call_delay_min") or 0.0)
        kinds = self.cfg.get("delay_kinds")
        return d if d > 0.0 and (not kinds or tr.kind in kinds) else 0.0

    def followed(self, tr: Trouble) -> bool:
        """Advice of the twin is carried out with probability cfg["compliance"]; the draw is the same in every copy."""
        q = float(self.cfg.get("compliance", 1.0))
        return q >= 1.0 or u01(self.seed, 0, "trial-follow:" + tr.issue) < q

    def seen_at(self, tr: Trouble) -> float:
        """Model minute the people on shift see the trouble (without the twin); inf for the quiet dose / cyclone losses."""
        if tr.kind in HIDDEN:
            return math.inf
        if tr.kind in DECISION or tr.kind in HIDDEN_TIER_S or tr.kind == "mantle":
            return self.asis_at(tr)
        return tr.t_start_min + ev.notice_delay_min(self.seed, tr.issue, self.plant.prm)

    def known_at(self, tr: Trouble) -> float:
        """Model minute the twin knows the trouble: a loud one right after its start, a hidden one when found."""
        if self.mode == "value_nd":
            return self.seen_at(tr)                     # no early detection: only what the people have seen
        if self.mode == "value" and not self.followed(tr):
            return self.seen_at(tr)                     # advice not carried out: the shift handles it as it does today
        if not tr.hidden:
            base = tr.t_start_min + EPS + self.delay_of(tr)
        else:
            base = math.inf if tr.t_found_min == NO_VALUE else tr.t_found_min + self.delay_of(tr)
        if self.mode == "novice_twin" and base != math.inf:
            return self._nov_ready.get(tr.issue, base)  # the twin knows at `base`; a novice who executes calls later by his slips
        return base

    # ---- novice from data (VALIDATION 8.9): seeing time x nov_detect_mult, a wrong diagnosis, a skipped step
    def human_min(self, tr: Trouble) -> float:
        """Minutes between the start and the call that are the people's own seeing and reacting (the part a novice is slower in);
        the physics in between (ore reaching the SAG, a lab sample, a metal detector) is not scaled."""
        p = self.plant.prm
        notice = float(self.cfg.get("asis_notice_min", 10.0))
        if tr.kind in HIDDEN:
            return 0.0
        if tr.kind in ASIS_SEE_MIN:
            return ASIS_SEE_MIN[tr.kind] + notice
        if tr.kind in DECISION or tr.kind in HIDDEN_TIER_S:
            return notice
        return ev.notice_delay_min(self.seed, tr.issue, p)

    def nov_seen_at(self, tr: Trouble) -> float:
        """Model minute a novice sees the trouble: the people's part x nov_detect_mult x a mean-preserving lognormal draw."""
        p = self.plant.prm
        s = float(p["nov_detect_sigma_ln"])
        m = float(p["nov_detect_mult"]) * math.exp(s * normal(self.seed, 0, "nov-det:" + tr.issue) - 0.5 * s * s)
        return self.seen_at(tr) + (m - 1.0) * self.human_min(tr)

    def _open_count(self, t: float) -> int:
        """Troubles the people know of that are not done at t (a decision counts as done once it is called)."""
        n = 0
        for tr in self.troubles:
            if tr.kind in HIDDEN or tr.t_start_min > t:
                continue
            b = self.booked.get(tr.issue)
            if b is None or (b["t_done_min"] != NO_VALUE and b["t_done_min"] > t + EPS):
                n += 1
        return n

    def nov_slip_min(self, tr: Trouble, t: float, diagnosis: bool) -> float:
        """Minutes lost to the novice's slips at the call: a wrong diagnosis (nov_p_diag) and a skipped step among nov_steps
        (nov_p_step each); both x nov_stress_mult with nov_stress_open open troubles. A slip costs one crew travel time
        (the wrong or incomplete crew arrives and reports; an assumption). Draws are from (seed, issue): the same in every copy."""
        p = self.plant.prm
        k = float(p["nov_stress_mult"]) if self._open_count(t) >= int(p["nov_stress_open"]) else 1.0
        lost = 0.0
        if diagnosis and u01(self.seed, 0, "nov-dx:" + tr.issue) < min(1.0, float(p["nov_p_diag"]) * k):
            lost += ev.arrival_min(self.seed, tr.issue + ":nov-dx", p)
        p_step = 1.0 - (1.0 - min(1.0, float(p["nov_p_step"]) * k)) ** int(p["nov_steps"])
        if u01(self.seed, 0, "nov-st:" + tr.issue) < p_step:
            lost += ev.arrival_min(self.seed, tr.issue + ":nov-st", p)
        return lost

    def _tact_novice_data(self, t: float) -> None:
        """novice_det: seeing time only; novice_err: slips only; novice_r: both. Hidden dose / cyclone losses stay with the
        laboratory and the tails alarm as for the expert. No order rule: every trouble is called when the novice is ready."""
        self._silence_alarm(False)
        det = self.mode in ("novice_det", "novice_r")
        err = self.mode in ("novice_err", "novice_r")
        for tr in sorted(self.troubles, key=lambda x: (x.t_start_min, x.issue)):
            if tr.issue in self.booked or tr.kind in HIDDEN:
                continue
            seen = self.nov_seen_at(tr) if det else self.seen_at(tr)
            if t + EPS < seen:
                continue
            ready = self._nov_ready.get(tr.issue)
            if ready is None:
                ready = seen + (self.nov_slip_min(tr, t, True) if err else 0.0)
                self._nov_ready[tr.issue] = ready
            if t + EPS >= ready:
                self._book(tr, t)

    def _prepare_novice_twin(self, t: float) -> None:
        """The twin tells the novice what and whom; he still executes with the slips of a skipped step (no wrong diagnosis:
        the card names the crew, an assumption). The delay is drawn at the first tact after the twin knows. The plant's own call at the
        alarm is switched off: the novice acts on the card, and a step he skips is skipped on any path."""
        self._silence_alarm(False)
        for tr in self.troubles:
            if tr.issue in self.booked or tr.issue in self._nov_ready:
                continue
            base = self.known_at(tr)
            if base != math.inf and t + EPS >= base:
                self._nov_ready[tr.issue] = base + self.nov_slip_min(tr, t, False)

    def asis_at(self, tr: Trouble) -> float:
        """Without the twin: operators take the same operating decision, but only when they see it.

        Grid cut and reline are visible at once (alarm, plan), so the call comes asis_notice_min
        after the start. Hard ore is seen only when it reaches the SAG (after the forecast lead
        scen_hard_lead_h), plus asis_notice_min. Crew troubles stay with the plant's own alarm
        and laboratory handling, as before.
        """
        notice = float(self.cfg.get("asis_notice_min", 10.0))
        if tr.kind == "hard":
            return tr.t_start_min + self.plant.prm["scen_hard_lead_h"] * MIN_PER_H + notice
        if tr.kind in ASIS_SEE_MIN:
            return tr.t_start_min + ASIS_SEE_MIN[tr.kind] + notice
        if tr.kind == "phdrift":                        # the next grab sample shows it
            p = self.plant.prm
            return tr.t_start_min + u01(self.seed, 0, "asis-ph:" + tr.issue) * p["sens_ph_lab_every_h"] * MIN_PER_H + notice
        if tr.kind == "hpgr":                           # seen when the metal detector trips
            return tr.t_start_min + self.plant.prm["peb_hpgr_tramp_after_h"] * MIN_PER_H + notice
        return tr.t_start_min + notice

    def _silence_alarm(self, only_delayed: bool) -> None:
        """The controller books these loud crew troubles itself: the plant's own call at the alarm is switched off."""
        for tr in self.troubles:
            if tr.crew and not tr.hidden and tr.issue not in self.booked and (not only_delayed or self.delay_of(tr) > 0.0):
                self.plant._loud.pop(tr.issue, None)

    def _tact_novice(self, t: float) -> None:
        """A novice takes the troubles one at a time in order of appearance and turns to the next one when the crew
        of the previous one has arrived (an assumption, VALIDATION 8.6)."""
        self._silence_alarm(False)
        busy = any(r["t_arrive_min"] != NO_VALUE and r["t_arrive_min"] > t + EPS for r in self.booked.values())
        if busy:
            return
        seen = sorted((tr for tr in self.troubles if tr.issue not in self.booked and tr.kind not in HIDDEN
                       and t + EPS >= self.seen_at(tr)), key=lambda tr: (tr.t_start_min, tr.issue))
        if seen:
            self._book(seen[0], t)

    def tact(self, t: float) -> None:
        if self.mode == "novice":
            self._tact_novice(t)
            return
        if self.mode in NOVICE_DATA:
            self._tact_novice_data(t)
            return
        if self.mode == "novice_twin":
            self._prepare_novice_twin(t)
        if self.mode == "value_nd":
            self._silence_alarm(False)
        elif float(self.cfg.get("call_delay_min") or 0.0) > 0.0:
            self._silence_alarm(True)
        if self.mode == "asis":
            for tr in self.troubles:
                if tr.issue not in self.booked and tr.kind in DECISION + HIDDEN_TIER_S + ("mantle",)                         and t + EPS >= self.asis_at(tr):
                    self._book(tr, t)
            return
        pending = [tr for tr in self.troubles if tr.issue not in self.booked and self.known_at(tr) <= t + EPS]
        if not pending:
            return
        if self.mode in ("value", "value_nd", "novice_twin"):
            desc = descriptors(self.plant, pending, t, self.plant.prm, self.seed, self.cfg["est_sigma"],
                               self.known_at)
            ranked = self.rank(desc, t, self.plant.prm, self.seed * 10000 + int(t))
            issues = [d["issue"] if isinstance(d, dict) else str(d) for d in ranked]
            issues += [tr.issue for tr in pending if tr.issue not in issues]
        else:
            react = self.cfg["loud_react_min"]
            ready = [tr for tr in pending if not tr.hidden or t + EPS >= tr.t_found_min + react]
            ready.sort(key=lambda tr: (tr.hidden, self.known_at(tr)))
            issues = [tr.issue for tr in ready]
        by_issue = {tr.issue: tr for tr in pending}
        for issue in issues:
            tr = by_issue.get(issue)
            if tr is not None:
                self._book(tr, t)

    def _book(self, tr: Trouble, t: float) -> None:
        job = self.plant.call("", issue=tr.issue)
        if job is None and tr.crew:
            return                                   # not active yet in the plant: retry next tact
        if tr.kind == "grid" and not any(v > 0.0 for v in getattr(self.plant, "_bonus_kw", {}).values()):
            return                                   # grid call had no effect yet (no shed mill or headroom): retry next tact
        self.booked[tr.issue] = {
            "t_call_min": float(t),
            "t_arrive_min": float(job.t_arrive_min) if job is not None else NO_VALUE,
            "t_done_min": float(job.t_done_min) if job is not None else NO_VALUE,
            "by": "operator" if self.mode in ("asis", "novice") + NOVICE_DATA else "twin",
        }


def _plant_jobs(plant: Plant, seen: dict[str, dict]) -> None:
    """Record crew jobs the plant booked by itself (alarm notice, laboratory, tails alarm)."""
    for issue, job in getattr(plant, "_jobs", {}).items():
        if issue not in seen:
            seen[issue] = {"t_call_min": float(job.t_call_min), "t_arrive_min": float(job.t_arrive_min),
                           "t_done_min": float(job.t_done_min), "by": "plant"}


DOWN_NODES = ("crusher", "sag", "ball", "flot", "line_stop", "line_limited")


def _sample_down(plant: Plant, dt: float, acc: dict[str, float]) -> None:
    """Add dt minutes to the nodes that stand now (crusher STOP, SAG STOP / RELINE / STARVED, any ball mill STOP,
    flotation STOP, line STOP) and to line_limited (line LIMITED); the two lines are summed."""
    for ln in plant.state.lines:
        if ln.crusher is not None and ln.crusher.state == "STOP":
            acc["crusher"] += dt
        if ln.sag is not None and ln.sag.state in ("STOP", "RELINE", "STARVED"):
            acc["sag"] += dt
        if any(b.state == "STOP" for b in ln.balls):
            acc["ball"] += dt
        if ln.flot is not None and ln.flot.state == "STOP":
            acc["flot"] += dt
        if ln.state == "STOP":
            acc["line_stop"] += dt
        elif ln.state == "LIMITED":
            acc["line_limited"] += dt


def run_shift(args: tuple[int, dict]) -> dict:
    """One seed: the copies over the shift and the night; returns the row of the JSON."""
    seed, cfg = args
    wall0 = time.perf_counter()
    rank_fn, policy_name = load_rank()
    shift = draw_shift(seed, cfg)
    prm = default().copy(**dict(cfg.get("set") or {}, **shift.overrides))   # --set first, shift draws win
    fact = Plant(prm, seed, mode="scenario")
    fact.warmup()
    spec = make_spec(fact, shift, cfg)
    names = list(cfg["copies"]) if cfg.get("copies") else (
        ["by_value", "by_loud", "base"] + (["no_twin"] if cfg["no_twin"] else []))
    bad = [n for n in names if n not in ALL_COPIES]
    if bad:
        raise ValueError("unknown copies: " + ",".join(bad))
    copies: dict[str, Plant] = {}
    for i, name in enumerate(names):
        copies[name] = fact if i == 0 else fact.clone()
    for name, c in copies.items():
        if name != "base":
            c.apply_scenario(spec)
    if cfg.get("crews"):                            # B4: the same number of free teams in every crew, every copy
        for c in copies.values():
            for cn in list(c.state.crews):
                c._set_crew_count(cn, int(cfg["crews"]))
    ctrl = {}
    for name in names:
        if name in MODE_OF and not (name == "no_twin" and not cfg.get("asis", True)):
            ctrl[name] = Controller(copies[name], shift.troubles, MODE_OF[name], cfg, seed, rank_fn)
    bookings: dict[str, dict[str, dict]] = {name: {} for name in copies}
    fine = any(MODE_OF.get(n) in FINE_MODES for n in names)
    step_min = min(float(cfg["tact_min"]), float(cfg["fine_tact_min"])) if fine else float(cfg["tact_min"])
    for k in ctrl.values():
        k.period = step_min
    down: dict[str, dict[str, float]] = {name: dict.fromkeys(DOWN_NODES, 0.0) for name in copies}
    t = fact.t_min
    t_origin = t
    end1 = t + prm["cal_shift_h"] * MIN_PER_H
    end2 = t + 2.0 * prm["cal_shift_h"] * MIN_PER_H
    from modules import flood as fl           # the counter of the stand's module: the experiment counts the same way
    from modules.store import _type_of
    flood_cnt = {n: fl.FloodCounter() for n in (cfg.get("alarms") or []) if n in copies}
    flood_next = [t]

    def flood_look() -> None:
        """Every 5 model minutes: the states of the nodes of the tracked copies into the counters (as the twin looks at them)."""
        if not flood_cnt or t + EPS < flood_next[0]:
            return
        flood_next[0] = t + 5.0
        for n, fc in flood_cnt.items():
            snap = copies[n].snapshot(measured=True)
            fc.observe(t, 0 if t <= end1 + EPS else 1,
                       [(nm, _type_of(nm), str(v.get("state", "")), v.get("alarm")) for nm, v in snap.items()
                        if _type_of(nm) in fl.ABNORMAL])

    def advance(target: float) -> None:
        nonlocal t
        while t < target - EPS:
            t_prev = t
            t = min(t + step_min, target)
            for c in copies.values():
                c.run_until(t)
            for name, c in copies.items():
                _sample_down(c, t - t_prev, down[name])
            flood_look()
            for name, k in ctrl.items():
                k.tact(t)
                for issue, rec in k.booked.items():
                    bookings[name].setdefault(issue, rec)
            for name, c in copies.items():
                _plant_jobs(c, bookings[name])

    advance(end1)
    flood1 = {n: fc.summary(t, len(shift.troubles)) for n, fc in flood_cnt.items()}
    w1 = {name: c.shift_summary() for name, c in copies.items()}
    down1 = {name: dict(d) for name, d in down.items()}
    for c in copies.values():
        if c.state.site_state == "PAUSED":          # auto pause at 20:00: go on into the night
            c.state.site_state = "RUN"
    advance(end2)
    w2 = {name: c.shift_summary() for name, c in copies.items()}

    def cu(w, name):
        return float(w[name]["cu_t"])

    def kwh_t(w, name):
        c = float(w[name]["cu_t"])
        return float(w[name]["energy_mwh"]) * 1000.0 / c if c > 0 else NO_VALUE

    def usd(w, name):
        return float(w[name]["usd"])

    row = {
        "seed": seed, "n_troubles": len(shift.troubles), "text": shift.text,
        "troubles": [asdict(tr) for tr in shift.troubles], "overrides": shift.overrides,
        "shared_crew": shift.shared_crew, "policy": policy_name,
        "cu_t_2000": {name: cu(w1, name) for name in copies},
        "cu_t_0800": {name: cu(w2, name) for name in copies},
        "usd_2000": {name: usd(w1, name) for name in copies},
        "usd_0800": {name: usd(w2, name) for name in copies},
        "loss_cu_t_2000": {name: cu(w1, "base") - cu(w1, name) for name in copies if name != "base"} if "base" in copies else {},
        "d_cu_t": cu(w1, "by_value") - cu(w1, "by_loud") if "by_loud" in copies and "by_value" in copies else NO_VALUE,
        "d_cu_t_0800": cu(w2, "by_value") - cu(w2, "by_loud") if "by_loud" in copies and "by_value" in copies else NO_VALUE,
        "d_usd": usd(w1, "by_value") - usd(w1, "by_loud") if "by_loud" in copies and "by_value" in copies else NO_VALUE,
        "bookings": bookings,
        "seconds": round(time.perf_counter() - wall0, 2),
        # extras for the sensitivity report
        "rec_pct_2000": {name: float(w1[name].get("recovery_pct", NO_VALUE)) for name in copies},
        "cu_feed_t_2000": {name: float(w1[name].get("cu_feed_t", NO_VALUE)) for name in copies},
        "n_hidden": sum(1 for tr in shift.troubles if tr.hidden),
        # extra metrics of the experiment of 24.10.2026: kWh per t Cu and minutes of standstill by node
        "kwh_per_t_cu_2000": {name: kwh_t(w1, name) for name in copies},
        "kwh_per_t_cu_0800": {name: kwh_t(w2, name) for name in copies},
        "down_min_2000": down1, "down_min_0800": down,
    }
    if flood1:
        row["alarm_flood_2000"] = flood1
    if "no_twin" in copies and "by_loud" in copies and "by_value" in copies:
        row["detection_cu_t"] = cu(w1, "by_loud") - cu(w1, "no_twin")
        row["twin_cu_t"] = cu(w1, "by_value") - cu(w1, "no_twin")
    return row


# ---------------------------------------------------------------------------
# Statistics (standard library only)
# ---------------------------------------------------------------------------
def percentile(xs_sorted: list[float], q: float) -> float:
    """Linear interpolation on sorted values, q in [0, 1]."""
    n = len(xs_sorted)
    if n == 0:
        return NO_VALUE
    pos = q * (n - 1)
    i = int(math.floor(pos))
    j = min(n - 1, i + 1)
    return xs_sorted[i] + (xs_sorted[j] - xs_sorted[i]) * (pos - i)


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval of a share k / n."""
    if n <= 0:
        return NO_VALUE, NO_VALUE
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def bootstrap_ci(xs: list[float], stat, boot: int, rng: random.Random, alpha: float = 0.05,
                 bca: bool = False) -> tuple[float, float]:
    """Bootstrap interval of stat(xs): percentile, or BCa (bias-corrected and accelerated, for the mean)."""
    n = len(xs)
    if n < 2:
        v = stat(xs) if n else NO_VALUE
        return v, v
    boots = sorted(stat(rng.choices(xs, k=n)) for _ in range(boot))
    lo_q, hi_q = alpha / 2, 1 - alpha / 2
    if bca:
        theta = stat(xs)
        prop = sum(1 for b in boots if b < theta) / len(boots)
        if 0.0 < prop < 1.0:
            nd = statistics.NormalDist()
            z0 = nd.inv_cdf(prop)
            jack = [stat(xs[:i] + xs[i + 1:]) for i in range(n)]
            jm = sum(jack) / n
            num = sum((jm - j) ** 3 for j in jack)
            den = 6.0 * sum((jm - j) ** 2 for j in jack) ** 1.5
            a = num / den if den > 0 else 0.0

            def adj(z):
                d = 1.0 - a * (z0 + z)
                return nd.cdf(z0 + (z0 + z) / d) if d != 0 else nd.cdf(z0 + z)

            lo_q, hi_q = adj(nd.inv_cdf(alpha / 2)), adj(nd.inv_cdf(1 - alpha / 2))
    return percentile(boots, lo_q), percentile(boots, hi_q)


def wilcoxon(xs: list[float]) -> dict:
    """Two-sided Wilcoxon signed-rank test of median D = 0; zeros dropped, average ranks for ties."""
    d = [x for x in xs if abs(x) > 1e-12]
    n = len(d)
    if n == 0:
        return {"n": 0, "w_plus": NO_VALUE, "p": NO_VALUE, "method": "no non-zero differences"}
    order = sorted(range(n), key=lambda i: abs(d[i]))
    ranks = [0.0] * n
    ties: list[int] = []
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs(d[order[j + 1]]) == abs(d[order[i]]):
            j += 1
        r = 0.5 * (i + j) + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = r
        if j > i:
            ties.append(j - i + 1)
        i = j + 1
    w_plus = sum(r for r, x in zip(ranks, d) if x > 0)
    if not ties and n <= 60:
        total = n * (n + 1) // 2
        counts = [0] * (total + 1)
        counts[0] = 1
        for r in range(1, n + 1):
            for s in range(total, r - 1, -1):
                counts[s] += counts[s - r]
        w = int(round(w_plus))
        scale = 2.0 ** n
        p_le = sum(counts[:w + 1]) / scale
        p_ge = sum(counts[w:]) / scale
        return {"n": n, "w_plus": w_plus, "p": min(1.0, 2.0 * min(p_le, p_ge)), "method": "exact"}
    mean = n * (n + 1) / 4.0
    var = n * (n + 1) * (2 * n + 1) / 24.0 - sum(t ** 3 - t for t in ties) / 48.0
    if var <= 0:
        return {"n": n, "w_plus": w_plus, "p": 1.0, "method": "normal (zero variance)"}
    diff = w_plus - mean
    z = (diff - 0.5 * (1 if diff > 0 else -1 if diff < 0 else 0)) / math.sqrt(var)
    p = 2.0 * (1.0 - statistics.NormalDist().cdf(abs(z)))
    return {"n": n, "w_plus": w_plus, "p": min(1.0, p), "method": "normal approximation with tie correction"}


def summarize(xs: list[float], boot: int, rng: random.Random, zero: float = ZERO_T) -> dict:
    """Mean, median, SD, P10/P90, bootstrap CIs, p0, p-, share positive, Wilcoxon."""
    n = len(xs)
    if n == 0:
        return {"n": 0}
    s = sorted(xs)
    mean = sum(xs) / n
    median = statistics.median(xs)
    sd = statistics.stdev(xs) if n > 1 else 0.0
    k0 = sum(1 for x in xs if abs(x) < zero)
    km = sum(1 for x in xs if x < -zero)
    kp = sum(1 for x in xs if x > zero)
    ci_mean = bootstrap_ci(xs, lambda v: sum(v) / len(v), boot, rng, bca=True)
    ci_median = bootstrap_ci(xs, statistics.median, boot, rng)
    return {
        "n": n, "mean": mean, "median": median, "sd": sd, "p10": percentile(s, 0.10), "p90": percentile(s, 0.90),
        "ci95_mean_bca": list(ci_mean), "ci95_median": list(ci_median),
        "p0": k0 / n, "p0_ci95_wilson": list(wilson(k0, n)),
        "p_minus": km / n, "p_minus_ci95_wilson": list(wilson(km, n)),
        "p_plus": kp / n, "p_plus_ci95_wilson": list(wilson(kp, n)),
        "zero_threshold": zero, "wilcoxon": wilcoxon(xs),
    }


# ---------------------------------------------------------------------------
# Run and report
# ---------------------------------------------------------------------------
def run_trial(cfg: dict, progress=None) -> dict:
    """All shifts (parallel with cfg["jobs"] > 1) and the summary; returns the JSON document."""
    cfg = dict(DEFAULTS, **cfg)
    wall0 = time.perf_counter()
    seeds = [int(x) for x in cfg["seeds"]] if cfg.get("seeds") else list(range(int(cfg["seed0"]), int(cfg["seed0"]) + int(cfg["n"])))
    jobs = max(1, int(cfg["jobs"]))
    rows: list[dict] = []
    if jobs == 1:
        for i, seed in enumerate(seeds):
            rows.append(run_shift((seed, cfg)))
            if progress:
                progress(i + 1, len(seeds))
    else:
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            for i, row in enumerate(ex.map(run_shift, [(s, cfg) for s in seeds], chunksize=1)):
                rows.append(row)
                if progress:
                    progress(i + 1, len(seeds))
    rng = random.Random(f"trial-boot:{cfg['seed0']}:{cfg['n']}")
    boot = int(cfg["boot"])
    both = bool(rows) and rows[0]["d_cu_t"] != NO_VALUE
    summary = {}
    if both:
        summary = {
            "d_cu_t_2000": summarize([r["d_cu_t"] for r in rows], boot, rng),
            "d_cu_t_0800": summarize([r["d_cu_t_0800"] for r in rows], boot, rng),
            "d_usd_2000": summarize([r["d_usd"] for r in rows], boot, rng, zero=ZERO_T * 14539 * 0.955),
        }
    if cfg["no_twin"] and both and "detection_cu_t" in rows[0]:
        summary["detection_cu_t_2000"] = summarize([r["detection_cu_t"] for r in rows], boot, rng)
        summary["twin_cu_t_2000"] = summarize([r["twin_cu_t"] for r in rows], boot, rng)
    small = max(1000, boot // 5)
    cuts: dict[str, dict] = {}
    if both:
        for key, label in (("n_troubles", "troubles"), ("shared_crew", "shared_crew")):
            for val in sorted({r[key] for r in rows}, key=str):
                sel = [r["d_cu_t"] for r in rows if r[key] == val]
                cuts[f"{label}={val}"] = summarize(sel, small, rng)
        kinds_cut: dict[str, list] = {}
        for r in rows:
            for tr in r["troubles"]:
                kinds_cut.setdefault(tr["kind"], []).append(r["d_cu_t"])
        cuts.update({f"has_{k}": summarize(v, small, rng) for k, v in sorted(kinds_cut.items())})
    losses = {}
    for name in rows[0]["loss_cu_t_2000"] if rows else ():
        xs = [r["loss_cu_t_2000"][name] for r in rows]
        losses[name] = {"mean": sum(xs) / len(xs), "median": statistics.median(xs)}
    return {
        "config": cfg, "policy": rows[0]["policy"] if rows else load_rank()[1], "n": len(rows),
        "seeds": [seeds[0], seeds[-1]] if seeds else [], "notes": list(NOTES),
        "summary": summary, "cuts": cuts, "loss_vs_base_cu_t_2000": losses, "shifts": rows,
        "seconds": round(time.perf_counter() - wall0, 1),
    }


def _fmt_stats(s: dict, unit: str) -> list[str]:
    if s.get("n", 0) == 0:
        return ["  (no data)"]
    lo, hi = s["ci95_mean_bca"]
    mlo, mhi = s["ci95_median"]
    w = s["wilcoxon"]
    return [
        f"  n {s['n']}: mean {s['mean']:+.3f} {unit} [95 % BCa {lo:+.3f}, {hi:+.3f}], median {s['median']:+.3f} "
        f"[{mlo:+.3f}, {mhi:+.3f}], SD {s['sd']:.3f}, P10 {s['p10']:+.3f}, P90 {s['p90']:+.3f}",
        f"  p0 (|D| < {s['zero_threshold']:.3g}) {s['p0']:.2f} [Wilson {s['p0_ci95_wilson'][0]:.2f}, "
        f"{s['p0_ci95_wilson'][1]:.2f}]; p- (D < -{s['zero_threshold']:.3g}) {s['p_minus']:.2f} "
        f"[{s['p_minus_ci95_wilson'][0]:.2f}, {s['p_minus_ci95_wilson'][1]:.2f}]; p+ {s['p_plus']:.2f}",
        f"  Wilcoxon signed-rank: n {w['n']}, W+ {w['w_plus']}, p {w['p']:.4f} ({w['method']})",
    ]


def format_report(doc: dict) -> str:
    c = doc["config"]
    out = [
        f"on/off trial: N {doc['n']} (seeds {doc['seeds'][0]}-{doc['seeds'][1]}), kip {c['kip']}, sigma_ln "
        f"{c['sigma_ln']}, detect {c['detect_min']:.0f} min, miss {c['miss']:.2f}, loud react "
        f"{c['loud_react_min']:.0f} min, tact {c['tact_min']:.0f} min, bootstrap {c['boot']}",
        f"policy: {doc['policy']}",
        "D = Cu(by value) - Cu(by loudness) at 20:00, t Cu [model estimate]",
    ]
    if "d_cu_t_2000" in doc["summary"]:
        out += _fmt_stats(doc["summary"]["d_cu_t_2000"], "t")
        out.append("D at 08:00 next day, t Cu")
        out += _fmt_stats(doc["summary"]["d_cu_t_0800"], "t")
        out.append("D at 20:00, USD (payable Cu - energy - water)")
        out += _fmt_stats(doc["summary"]["d_usd_2000"], "USD")
    else:
        out.append("  (no by_value / by_loud pair in this run: see the rows; sim.trial.aggregate reads them)")
    if "detection_cu_t_2000" in doc["summary"]:
        out.append("detection contribution Cu(by loudness) - Cu(no twin) at 20:00, t Cu")
        out += _fmt_stats(doc["summary"]["detection_cu_t_2000"], "t")
        out.append("twin in all Cu(by value) - Cu(no twin) at 20:00, t Cu")
        out += _fmt_stats(doc["summary"]["twin_cu_t_2000"], "t")
    out.append("cuts of D at 20:00, t Cu:")
    for name, s in doc["cuts"].items():
        if s.get("n", 0):
            lo, hi = s["ci95_mean_bca"]
            out.append(f"  {name:<16} n {s['n']:>3}: mean {s['mean']:+.3f} [{lo:+.3f}, {hi:+.3f}], median "
                       f"{s['median']:+.3f}, p0 {s['p0']:.2f}, p- {s['p_minus']:.2f}")
    out.append("loss against the base copy at 20:00, t Cu (mean / median): " + ", ".join(
        f"{k} {v['mean']:.2f} / {v['median']:.2f}" for k, v in doc["loss_vs_base_cu_t_2000"].items()))
    out.append(f"{doc['seconds']:.0f} s")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Aggregation of the experiment of 24.10.2026 (VALIDATION 8.6): reads the runs of one directory, writes one document
# ---------------------------------------------------------------------------
LEVELS_DELAY = (0, 15, 30, 60, 120)                 # B1, minutes
LEVELS_LAB = (2, 4, 6, 12, 24)                       # B2, hours until the result (mean wait 2 h + analysis)
KINDS_B1_PLAN = ("crusher", "trip", "dose", "cyclone", "hard", "grid", "reline")      # the kinds of the plan 8.6
KINDS_B1 = KINDS_B1_PLAN + ("roping", "phdrift", "hpgr", "mantle")                    # + tier S, run 24.10.2026 after the first results
POLICY_COPY = {"novice": "novice", "expert": "no_twin", "twin": "by_value"}
METRICS = ("cu", "usd", "kwh_per_t_cu", "recovery_pp", "down_min")
DOWN_STAND = ("crusher", "sag", "ball", "flot", "line_stop")


def _val(row: dict, copy: str, metric: str) -> float:
    """One metric of one copy of one shift row, at 20:00."""
    if metric == "cu":
        return float(row["cu_t_2000"][copy])
    if metric == "usd":
        return float(row["usd_2000"][copy])
    if metric == "kwh_per_t_cu":
        return float(row["kwh_per_t_cu_2000"][copy])
    if metric == "recovery_pp":
        return float(row["rec_pct_2000"][copy])
    if metric == "down_min":
        return sum(float(row["down_min_2000"][copy][n]) for n in DOWN_STAND)
    if metric.startswith("down_"):
        return float(row["down_min_2000"][copy][metric[5:]])
    raise KeyError(metric)


def _lin(rows: list[dict], weights: dict[str, float], metric: str) -> list[float]:
    """Per-shift linear combination of copies (a contrast); shifts with a missing value are dropped."""
    out = []
    for r in rows:
        try:
            raw = [_val(r, c, metric) for c in weights]
        except (KeyError, TypeError):
            continue
        if all(_valid(v) for v in raw):                # NO_VALUE is -1: test the raw values, not the weighted ones
            out.append(sum(w * v for w, v in zip(weights.values(), raw)))
    return out


def _brief(xs: list[float], boot: int, rng: random.Random, zero: float = ZERO_T) -> dict:
    """Mean with BCa CI, median, shares worse / better than the threshold, Wilcoxon p, and the rule of VALIDATION 8.6."""
    s = summarize(xs, boot, rng, zero=zero)
    if s.get("n", 0) == 0:
        return {"n": 0}
    lo, hi = s["ci95_mean_bca"]
    w = s["wilcoxon"]
    return {"n": s["n"], "mean": s["mean"], "ci95": [lo, hi], "median": s["median"], "sd": s["sd"],
            "share_worse": s["p_minus"], "share_worse_ci95": s["p_minus_ci95_wilson"],
            "share_better": s["p_plus"], "share_none": s["p0"], "wilcoxon_p": w["p"], "wilcoxon_method": w["method"],
            "effect": bool(lo > 0 or hi < 0) and abs(s["mean"]) > zero}


def _holm(ps: list[float]) -> list[float]:
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    out = [0.0] * len(ps)
    run = 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (len(ps) - rank) * ps[i]))
        out[i] = run
    return out


def _slopes(rows_by_level: list[list[dict]], xs: list[float], val) -> list[float]:
    """Per-shift OLS slope of val(row) on the level; only seeds present at every level."""
    maps = [{r["seed"]: r for r in rows} for rows in rows_by_level]
    seeds = sorted(set.intersection(*(set(m) for m in maps)))
    xm = sum(xs) / len(xs)
    sxx = sum((x - xm) ** 2 for x in xs)
    out = []
    for sd in seeds:
        ys = [val(m[sd]) for m in maps]
        if not all(math.isfinite(y) for y in ys):
            continue
        ym = sum(ys) / len(ys)
        out.append(sum((x - xm) * (y - ym) for x, y in zip(xs, ys)) / sxx)
    return out


def _load(dirpath: str, name: str):
    path = os.path.join(dirpath, name + ".json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def aggregate(dirpath: str) -> dict:
    """The analysis plan of VALIDATION 8.6 over the run files of `dirpath` (names in the code); no simulation."""
    boot = 10000
    rng = random.Random("exp23-aggregate")
    out: dict = {"plan": "VALIDATION.md 8.6", "dir": os.path.basename(os.path.abspath(dirpath)), "boot": boot}
    files = {}

    def get(name):
        if name not in files:
            files[name] = _load(dirpath, name)
        return files[name]

    # ---- B3 / D1: three policies, all metrics
    b3: dict = {}
    for tag in ("main_full", "main_base", "rep_full"):
        d = get(tag)
        if d is None:
            continue
        rows = d["shifts"]
        blk: dict = {"n": len(rows), "seeds": d["seeds"], "library": d["config"].get("library", "base"),
                     "troubles_per_shift": sum(r["n_troubles"] for r in rows) / len(rows), "means": {}, "pairs": {}}
        for pol, cp in POLICY_COPY.items():
            blk["means"][pol] = {m: (lambda v: sum(v) / len(v) if v else NO_VALUE)(_lin(rows, {cp: 1.0}, m)) for m in METRICS}
            blk["means"][pol]["down_by_node"] = {n: sum(float(r["down_min_2000"][cp][n]) for r in rows) / len(rows)
                                                for n in DOWN_NODES}
        if rows and "base" in rows[0]["cu_t_2000"]:
            blk["means"]["base_no_troubles"] = {m: (lambda v: sum(v) / len(v))(_lin(rows, {"base": 1.0}, m)) for m in METRICS}
        for a, b in (("twin", "expert"), ("twin", "novice"), ("expert", "novice")):
            wts = {POLICY_COPY[a]: 1.0, POLICY_COPY[b]: -1.0}
            cell = {}
            for m in METRICS:
                cell[m] = _brief(_lin(rows, wts, m), boot, rng, zero=ZERO_T if m == "cu" else 1e-9)
            cell["down_by_node"] = {n: _brief(_lin(rows, wts, "down_" + n), boot, rng, zero=1e-9) for n in DOWN_NODES}
            cell["cu_0800"] = _brief([float(r["cu_t_0800"][POLICY_COPY[a]]) - float(r["cu_t_0800"][POLICY_COPY[b]])
                                      for r in rows], boot, rng)
            blk["pairs"][f"{a}-{b}"] = cell
        holm = _holm([blk["pairs"][k]["cu"]["wilcoxon_p"] for k in blk["pairs"]])
        for k, h in zip(blk["pairs"], holm):
            blk["pairs"][k]["cu"]["wilcoxon_p_holm"] = h
        # ordering of the three policies, in the sense of E3
        p = blk["pairs"]
        blk["order_twin_gt_expert_gt_novice"] = bool(p["twin-expert"]["cu"]["effect"] and p["twin-expert"]["cu"]["mean"] > 0
                                                      and p["expert-novice"]["cu"]["mean"] > 0)
        kinds: dict = {}
        for r in rows:
            for tr in r["troubles"]:
                kinds.setdefault(tr["kind"], []).append(r)
        blk["twin_minus_expert_by_kind_cu"] = {k: _brief(_lin(v, {"by_value": 1.0, "no_twin": -1.0}, "cu"), 3000, rng)
                                               for k, v in sorted(kinds.items())}
        b3[tag] = blk
    out["b3_d1"] = b3

    # ---- B4: 2 x 2 x crews
    b4: dict = {}
    for k in (1, 2, 3):
        d = get(f"crews{k}")
        if d is None:
            continue
        rows = d["shifts"]
        A, B, C, D = "no_twin", "value_nd", "by_loud", "by_value"       # (det off, order off), (off, on), (on, off), (on, on)
        cells = {nm: (lambda v: sum(v) / len(v))(_lin(rows, {c: 1.0}, "cu")) for nm, c in
                 (("off_off", A), ("off_on", B), ("on_off", C), ("on_on", D))}
        contrasts = {
            "detection": {C: 0.5, D: 0.5, A: -0.5, B: -0.5},
            "order": {B: 0.5, D: 0.5, A: -0.5, C: -0.5},
            "interaction": {D: 1.0, C: -1.0, B: -1.0, A: 1.0},
            "all": {D: 1.0, A: -1.0},
        }
        b4[str(k)] = {"n": len(rows), "cells_cu_t": cells,
                      "contrasts_cu": {nm: _brief(_lin(rows, w, "cu"), boot, rng) for nm, w in contrasts.items()},
                      "contrasts_usd": {nm: _brief(_lin(rows, w, "usd"), 4000, rng, zero=1e-9) for nm, w in contrasts.items()},
                      "shared_crew_share": sum(1 for r in rows if r["shared_crew"]) / len(rows),
                      "order_effect_shared_crew": _brief(_lin([r for r in rows if r["shared_crew"]], contrasts["order"], "cu"),
                                                         4000, rng)}
    out["b4"] = b4

    # ---- B1: call delay
    docs = [get(f"delay_{d}") for d in LEVELS_DELAY]
    b1: dict = {}
    if all(x is not None for x in docs):
        rows_by = [x["shifts"] for x in docs]
        loss = lambda r: float(r["loss_cu_t_2000"]["by_value"])          # noqa: E731
        b1["levels"] = {}
        for d, rows in zip(LEVELS_DELAY, rows_by):
            b1["levels"][str(d)] = _brief([loss(r) for r in rows], boot, rng)
            b1["levels"][str(d)]["usd_loss"] = _brief([float(r["usd_2000"]["base"]) - float(r["usd_2000"]["by_value"])
                                                       for r in rows], 4000, rng, zero=1e-9)
        hours = [d / 60.0 for d in LEVELS_DELAY]
        sl = _slopes(rows_by, hours, loss)
        b1["slope_t_cu_per_h_all_troubles"] = _brief(sl, boot, rng)
        sl_usd = _slopes(rows_by, hours, lambda r: float(r["usd_2000"]["base"]) - float(r["usd_2000"]["by_value"]))
        b1["slope_usd_per_h_all_troubles"] = _brief(sl_usd, 4000, rng, zero=1e-9)
        by0 = {r["seed"]: r for r in rows_by[0]}
        b1["by_kind_60min"] = {}
        for kd in KINDS_B1:
            dk = get(f"delaykind_{kd}")
            if dk is None:
                continue
            per_h = [(loss(r) - loss(by0[r["seed"]])) / 1.0 for r in dk["shifts"] if r["seed"] in by0]
            # 60 min = 1 h, so the difference is t Cu per hour; the tier S kinds draw from their own stream (the numbers of the plan kinds stay)
            b1["by_kind_60min"][kd] = _brief(per_h, 4000, rng if kd in KINDS_B1_PLAN else random.Random("exp23-b1-" + kd))
    out["b1"] = b1

    # ---- B2: laboratory
    docs = {h: get(f"lab_{h}") for h in LEVELS_LAB}
    b2: dict = {}
    if all(v is not None for v in docs.values()):
        rows_by = [docs[h]["shifts"] for h in LEVELS_LAB]
        ben = lambda r: float(r["cu_t_2000"]["by_value"]) - float(r["cu_t_2000"]["no_twin"])          # noqa: E731
        b2["levels"] = {str(h): _brief([ben(r) for r in docs[h]["shifts"]], boot, rng) for h in LEVELS_LAB}
        b2["slope_t_cu_per_h"] = _brief(_slopes(rows_by, [float(h) for h in LEVELS_LAB], ben), boot, rng)
        hid = lambda r: r["n_hidden"] > 0          # noqa: E731
        for tag, sel in (("with_hidden", hid), ("without_hidden", lambda r: not hid(r))):
            sub = [[r for r in rows if sel(r)] for rows in rows_by]
            b2["slope_" + tag] = _brief(_slopes(sub, [float(h) for h in LEVELS_LAB], ben), 4000, rng)
            b2["n_" + tag] = len(sub[0])
        b2["levels_usd"] = {str(h): _brief(_lin(docs[h]["shifts"], {"by_value": 1.0, "no_twin": -1.0}, "usd"), 4000, rng, zero=1e-9)
                            for h in LEVELS_LAB}
    out["b2"] = b2

    # ---- D2 tornado: benefit twin - expert under one changed assumption at a time
    tor: list[dict] = []
    base = get("lab_4")                      # same copies and the same 5-minute cadence as the other tornado runs
    if base is not None:
        b0 = _brief(_lin(base["shifts"], {"by_value": 1.0, "no_twin": -1.0}, "cu"), boot, rng)
        tor.append({"factor": "base", "value": "lab_4", "benefit": b0})
        for h in (2, 6, 12, 24):
            d = get(f"lab_{h}")
            if d is not None:
                tor.append({"factor": "lab_h", "value": h,
                            "benefit": _brief(_lin(d["shifts"], {"by_value": 1.0, "no_twin": -1.0}, "cu"), 4000, rng)})
        for tag, factor, value in (("tor_comp50", "compliance", 0.5), ("tor_comp75", "compliance", 0.75),
                                   ("tor_err2", "model_error_x2", 0.4), ("tor_det150", "detect_min", 150)):
            d = get(tag)
            if d is not None:
                tor.append({"factor": factor, "value": value,
                            "benefit": _brief(_lin(d["shifts"], {"by_value": 1.0, "no_twin": -1.0}, "cu"), 4000, rng)})
    out["tornado"] = tor

    # ---- bridge to 22.10 and the cadence of the twin's call queue (1 min against 5 min)
    bridge: dict = {}
    leg = get("legacy_check")
    if leg is not None:
        bridge["legacy_check_22_10_settings"] = {k: leg["summary"][k] for k in
                                                 ("twin_cu_t_2000", "detection_cu_t_2000", "d_cu_t_2000") if k in leg["summary"]}
    m1, m5 = get("main_full"), get("lab_4")
    if m1 is not None and m5 is not None:
        r1, r5 = {r["seed"]: r for r in m1["shifts"]}, {r["seed"]: r for r in m5["shifts"]}
        seeds = sorted(set(r1) & set(r5))
        diff = {c: [(sd, float(r5[sd]["cu_t_2000"][c]) - float(r1[sd]["cu_t_2000"][c])) for sd in seeds]
                for c in ("by_value", "no_twin")}
        bridge["cadence_5min_minus_1min_cu"] = {c: _brief([x for _, x in v], 4000, rng) for c, v in diff.items()}
        top = sorted(diff["by_value"], key=lambda kv: -abs(kv[1]))[:3]
        bridge["cadence_largest_by_value_shifts"] = [{"seed": sd, "d_cu_t": x, "text": r1[sd]["text"]} for sd, x in top]
        ben5 = [float(r5[sd]["cu_t_2000"]["by_value"]) - float(r5[sd]["cu_t_2000"]["no_twin"]) for sd in seeds]
        bridge["benefit_5min_without_largest_shift"] = _brief(sorted(ben5)[:-1], 4000, rng)
        bridge["benefit_5min"] = _brief(ben5, 4000, rng)
    out["bridge"] = bridge
    out["worse_shifts"] = _worse_shifts(get)
    out["novice_data"] = _novice_block(get)
    out["energy_co2"] = _energy_block(get)
    out["alarm_flood"] = _flood_block(get)
    out["p80_slope"] = _p80_block(get)
    out["files_missing"] = [k for k, v in files.items() if v is None]
    return out



# ---------------------------------------------------------------------------
# Shifts where the twin is worse than the expert (P2) and the novice from data (VALIDATION 8.9, 8.10)
# ---------------------------------------------------------------------------
NOV_PAIRS = {                                        # name -> (copy a, copy b); the contrast is a - b
    "expert-nov_r": ("no_twin", "nov_r"),            # the single main comparison of 8.9
    "twin-nov_r": ("by_value", "nov_r"),
    "twin-expert": ("by_value", "no_twin"),          # code control: equals main_full of 8.8
    "nov_twin-nov_r": ("nov_twin", "nov_r"),
    "nov_twin-expert": ("nov_twin", "no_twin"),
    "twin-nov_twin": ("by_value", "nov_twin"),
    "expert-nov_det": ("no_twin", "nov_det"),        # seeing time only
    "expert-nov_err": ("no_twin", "nov_err"),        # slips only
    "nov_det-nov_r": ("nov_det", "nov_r"),           # what the slips add on top of the seeing time
    "nov_err-nov_r": ("nov_err", "nov_r"),           # what the seeing time adds on top of the slips
    "expert-novice_v1": ("no_twin", "novice"),       # the "one at a time" novice of 8.8
}
NOV_MAIN3 = ("twin-expert", "twin-nov_r", "expert-nov_r")      # Holm over these three (8.9)


def _pair_cell(rows: list[dict], a: str, b: str, boot: int, rng: random.Random) -> dict:
    """The five metrics of 8.6 for the contrast copy a - copy b over the shifts, plus the time by node and the copper at 08:00."""
    wts = {a: 1.0, b: -1.0}
    cell = {m: _brief(_lin(rows, wts, m), boot, rng, zero=ZERO_T if m == "cu" else 1e-9) for m in METRICS}
    cell["down_by_node"] = {n: _brief(_lin(rows, wts, "down_" + n), boot, rng, zero=1e-9) for n in DOWN_NODES}
    cell["cu_0800"] = _brief([float(r["cu_t_0800"][a]) - float(r["cu_t_0800"][b]) for r in rows], boot, rng)
    return cell


def _worse_shifts(get) -> dict:
    """Shifts with twin - expert below -ZERO_T t Cu: seed, size, troubles, calls of the two copies (no simulation)."""
    out: dict = {}
    for tag in ("main_full", "rep_full", "main_base"):
        d = get(tag)
        if d is None:
            continue
        rows = []
        for r in d["shifts"]:
            dd = float(r["cu_t_2000"]["by_value"]) - float(r["cu_t_2000"]["no_twin"])
            if dd >= -ZERO_T:
                continue
            calls = {}
            for tr in r["troubles"]:
                tw, ex = r["bookings"]["by_value"].get(tr["issue"]), r["bookings"]["no_twin"].get(tr["issue"])
                calls[tr["issue"]] = {"start": round(tr["t_start_min"], 1), "found_by_twin": (None if tr["t_found_min"] < 0 else round(tr["t_found_min"], 1)),
                                      "call_twin": None if tw is None else round(tw["t_call_min"], 1),
                                      "call_expert": None if ex is None else round(ex["t_call_min"], 1),
                                      "by_expert": None if ex is None else ex["by"]}
            rows.append({"seed": r["seed"], "d_cu": dd, "text": r["text"], "shared_crew": r["shared_crew"],
                         "kinds": sorted({tr["kind"] for tr in r["troubles"]}), "calls": calls})
        diffs = [float(r["cu_t_2000"]["by_value"]) - float(r["cu_t_2000"]["no_twin"]) for r in d["shifts"]]
        out[tag] = {"n": len(diffs), "n_worse": len(rows), "n_below_zero": sum(1 for x in diffs if x < 0.0),
                    "worst": min(diffs), "rows": sorted(rows, key=lambda x: x["d_cu"])}
    return out


def _energy_block(get) -> dict:
    """Energy and CO2 of the twin against the expert (main_full of 8.8), from the kWh per t Cu and the copper of each shift.
    The CO2 factor is the stand's own row econ_co2_t_mwh (group Scope 2 / group electricity, a calculation)."""
    d = get("main_full")
    if d is None:
        return {}
    rows = d["shifts"]
    f = float(default()["econ_co2_t_mwh"])
    rng = random.Random("exp23-energy")

    def en(r, c):                                           # MWh of the shift to 20:00
        return float(r["kwh_per_t_cu_2000"][c]) * float(r["cu_t_2000"][c]) / 1000.0

    mean = lambda xs: sum(xs) / len(xs)                      # noqa: E731
    out = {"co2_t_per_mwh": f, "n": len(rows), "mwh_per_shift": {c: mean([en(r, c) for r in rows]) for c in ("base", "no_twin", "by_value")},
           "kwh_per_t_cu": {c: mean([float(r["kwh_per_t_cu_2000"][c]) for r in rows]) for c in ("base", "no_twin", "by_value")},
           "cu_t_per_shift": {c: mean([float(r["cu_t_2000"][c]) for r in rows]) for c in ("base", "no_twin", "by_value")}}
    out["co2_t_per_t_cu"] = {c: v * f / 1000.0 for c, v in out["kwh_per_t_cu"].items()}
    d_mwh = _brief([en(r, "by_value") - en(r, "no_twin") for r in rows], 10000, rng, zero=1e-9)
    d_int = _brief([float(r["kwh_per_t_cu_2000"]["by_value"]) - float(r["kwh_per_t_cu_2000"]["no_twin"]) for r in rows], 10000, rng, zero=1e-9)
    out["twin_minus_expert"] = {"mwh_per_shift": d_mwh, "kwh_per_t_cu": d_int,
                                "co2_kg_per_t_cu": {"mean": d_int["mean"] * f, "ci95": [x * f for x in d_int["ci95"]]},
                                "co2_t_per_shift_absolute": {"mean": d_mwh["mean"] * f, "ci95": [x * f for x in d_mwh["ci95"]]},
                                "co2_t_per_shift_same_output": {"mean": d_int["mean"] * out["cu_t_per_shift"]["by_value"] / 1000.0 * f,
                                                                "ci95": [x * out["cu_t_per_shift"]["by_value"] / 1000.0 * f for x in d_int["ci95"]]}}
    return out


def _p80_block(get) -> dict:
    """Twin - expert under the slope of recovery on P80 of the Bozshakol analog (laboratory 1.2, plant regression 1.95 pp per 10 um)
    against the stand's 0.3 (assumption); same copies and 5-minute cycle (runs lab_4, sens_p80_12, sens_p80_195). Descriptive, not pre-registered."""
    rng = random.Random("exp23-p80")
    out: dict = {}
    for tag, slope in (("lab_4", 0.3), ("sens_p80_12", 1.2), ("sens_p80_195", 1.95)):
        d = get(tag)
        if d is None:
            continue
        rows = d["shifts"]
        out[str(slope)] = {"run": tag, "n": len(rows),
                           "twin_minus_expert": _brief(_lin(rows, {"by_value": 1.0, "no_twin": -1.0}, "cu"), 10000, rng),
                           "expert_cu_t": sum(float(r["cu_t_2000"]["no_twin"]) for r in rows) / len(rows),
                           "twin_cu_t": sum(float(r["cu_t_2000"]["by_value"]) for r in rows) / len(rows)}
    return out


def _flood_block(get) -> dict:
    """Alarm-like events per shift (modules/flood.py) against the troubles injected and the one on the main screen (run `flood`)."""
    d = get("flood")
    if d is None:
        return {}
    rows = [r for r in d["shifts"] if "alarm_flood_2000" in r]
    tps = sum(r["n_troubles"] for r in rows) / len(rows) if rows else 0.0
    out: dict = {"n": len(rows), "isa_per_shift": 150.0 * 12.0 / 24.0, "troubles_per_shift": tps}
    for c in ("no_twin", "by_value"):
        ev = sorted(float(r["alarm_flood_2000"][c]["events"]) for r in rows if c in r["alarm_flood_2000"])
        nodes = [float(r["alarm_flood_2000"][c]["nodes"]) for r in rows if c in r["alarm_flood_2000"]]
        if not ev:
            continue
        out[c] = {"events_mean": sum(ev) / len(ev), "events_median": percentile(ev, 0.5), "events_p10": percentile(ev, 0.1),
                  "events_p90": percentile(ev, 0.9), "events_max": ev[-1], "nodes_mean": sum(nodes) / len(nodes),
                  "events_per_trouble": sum(ev) / len(ev) / out["troubles_per_shift"] if out["troubles_per_shift"] else None,
                  "per_10min_mean": sum(ev) / len(ev) / 72.0}
    return out


def _novice_block(get) -> dict:
    """Pre-registered analysis of 8.9 over the runs nov_main, nov_rep, nov_lo, nov_hi (names in run_exp23.py)."""
    rng = random.Random("exp23-novice")
    boot = 10000
    out: dict = {"plan": "VALIDATION.md 8.9", "runs": {}}
    for tag in ("nov_main", "nov_rep", "nov_lo", "nov_hi"):
        d = get(tag)
        if d is None:
            continue
        rows = d["shifts"]
        have = set(rows[0]["cu_t_2000"]) if rows else set()
        blk: dict = {"n": len(rows), "seeds": d["seeds"], "library": d["config"].get("library", "base"),
                     "troubles_per_shift": sum(r["n_troubles"] for r in rows) / len(rows),
                     "set": d["config"].get("set") or {}, "means": {}, "pairs": {}}
        pol = {"expert": "no_twin", "twin": "by_value", "nov_r": "nov_r", "nov_twin": "nov_twin", "nov_det": "nov_det",
               "nov_err": "nov_err", "novice_v1": "novice", "base_no_troubles": "base"}
        for name, cp in pol.items():
            if cp in have:
                blk["means"][name] = {m: (lambda v: sum(v) / len(v) if v else NO_VALUE)(_lin(rows, {cp: 1.0}, m)) for m in METRICS}
                blk["means"][name]["down_by_node"] = {n: sum(float(r["down_min_2000"][cp][n]) for r in rows) / len(rows)
                                                      for n in DOWN_NODES}
        for name, (a, b) in NOV_PAIRS.items():
            if a in have and b in have:
                blk["pairs"][name] = _pair_cell(rows, a, b, boot if tag in ("nov_main", "nov_rep") else 4000, rng)
        main3 = [k for k in NOV_MAIN3 if k in blk["pairs"]]
        if len(main3) == 3:
            for k, h in zip(main3, _holm([blk["pairs"][k]["cu"]["wilcoxon_p"] for k in main3])):
                blk["pairs"][k]["cu"]["wilcoxon_p_holm"] = h
        if "expert-nov_r" in blk["pairs"]:
            kinds: dict = {}
            for r in rows:
                for tr in r["troubles"]:
                    kinds.setdefault(tr["kind"], []).append(r)
            blk["expert_minus_nov_r_by_kind_cu"] = {k: _brief(_lin(v, {"no_twin": 1.0, "nov_r": -1.0}, "cu"), 3000, rng)
                                                    for k, v in sorted(kinds.items())}
            blk["expert_minus_nov_r_by_shared_crew_cu"] = {
                str(flag): _brief(_lin([r for r in rows if r["shared_crew"] == flag], {"no_twin": 1.0, "nov_r": -1.0}, "cu"), 3000, rng)
                for flag in (False, True) if any(r["shared_crew"] == flag for r in rows)}
            slips = {"seeing_min_extra": [], "n_calls": 0}
            for r in rows:
                for tr in r["troubles"]:
                    ex, nv = r["bookings"]["no_twin"].get(tr["issue"]), r["bookings"]["nov_r"].get(tr["issue"])
                    if ex is not None and nv is not None and tr["kind"] not in HIDDEN:
                        slips["n_calls"] += 1
                        slips["seeing_min_extra"].append(nv["t_call_min"] - ex["t_call_min"])
            xs = slips["seeing_min_extra"]
            slips["mean_call_later_min"] = sum(xs) / len(xs) if xs else NO_VALUE
            slips["n_calls_later_than_30_min"] = sum(1 for x in xs if x > 30.0)
            slips.pop("seeing_min_extra")
            blk["call_later_than_expert"] = slips
        out["runs"][tag] = blk
    m = out["runs"].get("nov_main")
    if m and {"expert-nov_r", "twin-nov_r", "twin-expert", "nov_twin-nov_r", "nov_twin-expert"} <= set(m["pairs"]):
        P = m["pairs"]
        en = lambda k: P[k]["cu"]                                        # noqa: E731
        out["expectations"] = {
            "EN1_expert_better_than_nov_r": bool(en("expert-nov_r")["effect"] and en("expert-nov_r")["mean"] > 0),
            "EN2_twin_lifts_novice_at_least_as_much": bool(en("twin-nov_r")["mean"] >= en("twin-expert")["mean"]),
            "EN3_nov_twin_better_than_nov_r": bool(en("nov_twin-nov_r")["effect"] and en("nov_twin-nov_r")["mean"] > 0),
            "EN3_nov_twin_not_below_expert": bool(en("nov_twin-expert")["ci95"][0] >= -ZERO_T),
            "EN4_slips_less_than_seeing": bool("nov_det-nov_r" in P and "nov_err-nov_r" in P
                                               and abs(P["nov_det-nov_r"]["cu"]["mean"]) < abs(P["nov_err-nov_r"]["cu"]["mean"])),
            "twin_expert_equals_main_full_8_8": None,
        }
        mf = get("main_full")
        if mf is not None:
            ref = _brief(_lin(mf["shifts"], {"by_value": 1.0, "no_twin": -1.0}, "cu"), 3000, rng)
            out["expectations"]["twin_expert_equals_main_full_8_8"] = bool(abs(ref["mean"] - en("twin-expert")["mean"]) < 1e-9)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="trial", description="On/off trial of the issue queue on the model")
    ap.add_argument("--n", type=int, default=DEFAULTS["n"])
    ap.add_argument("--seed0", type=int, default=DEFAULTS["seed0"])
    ap.add_argument("--kip", type=int, default=DEFAULTS["kip"])
    ap.add_argument("--sigma-ln", type=float, default=DEFAULTS["sigma_ln"])
    ap.add_argument("--miss", type=float, default=DEFAULTS["miss"], help="share of hidden troubles the twin misses")
    ap.add_argument("--detect-min", type=float, default=DEFAULTS["detect_min"])
    ap.add_argument("--loud-react", type=float, default=DEFAULTS["loud_react_min"])
    ap.add_argument("--price", type=float, default=None, help="Cu price USD/t (table value when omitted)")
    ap.add_argument("--no-twin", action="store_true", help="add the copy without the twin")
    ap.add_argument("--boot", type=int, default=DEFAULTS["boot"])
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--out", default="trial.json")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                    help="ParamSet override for every shift (repeatable)")
    ap.add_argument("--hidden-mult", type=float, default=1.0, help="frequency factor of hidden troubles")
    ap.add_argument("--mag", type=float, default=1.0, help="magnitude factor of hidden troubles")
    ap.add_argument("--no-asis", action="store_true",
                    help="old baseline: without the twin nobody takes the hard/grid/reline decisions")
    ap.add_argument("--asis-notice", type=float, default=10.0,
                    help="minutes from seeing a decision trouble to the call, without the twin")
    ap.add_argument("--library", choices=("base", "tier_s"), default="base",
                    help="trouble library: base (the N = 100 trial) or tier_s (+ roping, pH drift, HPGR, mantle change)")
    ap.add_argument("--copies", default=None, help="comma list of copies: " + ",".join(ALL_COPIES))
    ap.add_argument("--crews", type=int, default=None, help="teams in every crew (B4: 1 / 2 / 3)")
    ap.add_argument("--call-delay", type=float, default=0.0, help="minutes from the twin knowing a trouble to the call (B1)")
    ap.add_argument("--delay-kinds", default=None, help="comma list of kinds the delay applies to (all when omitted)")
    ap.add_argument("--compliance", type=float, default=1.0, help="share of the twin's calls the shift carries out")
    ap.add_argument("--est-sigma", type=float, default=DEFAULTS["est_sigma"], help="log-sd of the module's loss estimate")
    ap.add_argument("--seeds", default=None, help="comma list of seeds (instead of --seed0 / --n)")
    ap.add_argument("--alarms", default=None, help="comma list of copies whose node states are counted as alarm-like events")
    ap.add_argument("--aggregate", default=None, metavar="DIR",
                    help="read the runs of the experiment from DIR (see aggregate) and write --out; no simulation")
    a = ap.parse_args(argv)
    if a.aggregate:
        doc = aggregate(a.aggregate)
        with open(a.out, "w", encoding="utf-8", newline="\n") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
        print("wrote", a.out)
        return 0
    sets: dict[str, float] = {}
    for item in a.set:
        key, _, val = item.partition("=")
        if key.strip() not in default():
            raise SystemExit("unknown parameter in --set: " + key)
        sets[key.strip()] = float(val)
    cfg = {"n": a.n, "seed0": a.seed0, "kip": a.kip, "sigma_ln": a.sigma_ln, "miss": a.miss,
           "detect_min": a.detect_min, "loud_react_min": a.loud_react, "price": a.price, "no_twin": a.no_twin,
           "boot": a.boot, "jobs": a.jobs, "set": sets, "hidden_mult": a.hidden_mult, "mag": a.mag,
           "asis": not a.no_asis, "asis_notice_min": a.asis_notice, "est_sigma": a.est_sigma}
    if a.copies:
        cfg["copies"] = [x.strip() for x in a.copies.split(",") if x.strip()]
    if a.crews:
        cfg["crews"] = a.crews
    if a.call_delay:
        cfg["call_delay_min"] = a.call_delay
    if a.delay_kinds:
        cfg["delay_kinds"] = [x.strip() for x in a.delay_kinds.split(",") if x.strip()]
    if a.compliance != 1.0:
        cfg["compliance"] = a.compliance
    if a.seeds:
        cfg["seeds"] = [int(x) for x in a.seeds.split(",") if x.strip()]
    if a.alarms:
        cfg["alarms"] = [x.strip() for x in a.alarms.split(",") if x.strip()]
    if a.library != "base":
        cfg["library"] = a.library              # absent in the default config, so the stored N = 100 summary stays comparable

    def progress(i, n):
        if i == n or i % 10 == 0:
            print(f"  {i} of {n} shifts", flush=True)

    doc = run_trial(cfg, progress)
    print(format_report(doc))
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
