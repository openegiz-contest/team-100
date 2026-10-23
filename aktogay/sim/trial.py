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
DECISION = ("hard", "grid", "reline")   # no crew: the call changes operation (blend, headroom, excavators)

DEFAULTS = {
    "n": 100, "seed0": 1001, "kip": 1, "sigma_ln": 0.4, "miss": 0.0, "detect_min": 75.0,
    "loud_react_min": 30.0, "no_twin": False, "price": None, "p_two": 0.6, "start_span_h": 10.0,
    "est_sigma": 0.2, "tact_min": TACT_MIN, "boot": 10000, "jobs": 1,
    "set": {}, "hidden_mult": 1.0, "mag": 1.0, "asis": True, "asis_notice_min": 10.0,
}
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
    cats = [c for c in LIBRARY]
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
        issue, node, crew = ev.issue_for(kind, line)
        start = t0 + rng.random() * cfg["start_span_h"] * MIN_PER_H
        if node in nodes:
            continue
        nodes.add(node)
        hidden = kind in HIDDEN
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
        if mode not in ("value", "loud", "asis"):
            raise ValueError("mode must be value, loud or asis")
        self.plant, self.troubles, self.mode, self.cfg, self.seed, self.rank = plant, troubles, mode, cfg, seed, rank_fn
        self.booked: dict[str, dict] = {}

    def known_at(self, tr: Trouble) -> float:
        """Model minute the twin knows the trouble: a loud one right after its start, a hidden one when found."""
        if not tr.hidden:
            return tr.t_start_min + EPS
        return math.inf if tr.t_found_min == NO_VALUE else tr.t_found_min

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
        return tr.t_start_min + notice

    def tact(self, t: float) -> None:
        if self.mode == "asis":
            for tr in self.troubles:
                if tr.issue not in self.booked and tr.kind in DECISION and t + EPS >= self.asis_at(tr):
                    self._book(tr, t)
            return
        pending = [tr for tr in self.troubles if tr.issue not in self.booked and self.known_at(tr) <= t + EPS]
        if not pending:
            return
        if self.mode == "value":
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
            "by": "operator" if self.mode == "asis" else "twin",
        }


def _plant_jobs(plant: Plant, seen: dict[str, dict]) -> None:
    """Record crew jobs the plant booked by itself (alarm notice, laboratory, tails alarm)."""
    for issue, job in getattr(plant, "_jobs", {}).items():
        if issue not in seen:
            seen[issue] = {"t_call_min": float(job.t_call_min), "t_arrive_min": float(job.t_arrive_min),
                           "t_done_min": float(job.t_done_min), "by": "plant"}


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
    copies: dict[str, Plant] = {"by_value": fact, "by_loud": fact.clone(), "base": fact.clone()}
    if cfg["no_twin"]:
        copies["no_twin"] = fact.clone()
    for name, c in copies.items():
        if name != "base":
            c.apply_scenario(spec)
    ctrl = {"by_value": Controller(copies["by_value"], shift.troubles, "value", cfg, seed, rank_fn),
            "by_loud": Controller(copies["by_loud"], shift.troubles, "loud", cfg, seed, rank_fn)}
    if cfg["no_twin"] and cfg.get("asis", True):
        ctrl["no_twin"] = Controller(copies["no_twin"], shift.troubles, "asis", cfg, seed, rank_fn)
    bookings: dict[str, dict[str, dict]] = {name: {} for name in copies}
    tact = float(cfg["tact_min"])
    t = fact.t_min
    end1 = t + prm["cal_shift_h"] * MIN_PER_H
    end2 = t + 2.0 * prm["cal_shift_h"] * MIN_PER_H

    def advance(target: float) -> None:
        nonlocal t
        while t < target - EPS:
            t = min(t + tact, target)
            for c in copies.values():
                c.run_until(t)
            for name, k in ctrl.items():
                k.tact(t)
                for issue, rec in k.booked.items():
                    bookings[name].setdefault(issue, rec)
            for name, c in copies.items():
                _plant_jobs(c, bookings[name])

    advance(end1)
    w1 = {name: c.shift_summary() for name, c in copies.items()}
    for c in copies.values():
        if c.state.site_state == "PAUSED":          # auto pause at 20:00: go on into the night
            c.state.site_state = "RUN"
    advance(end2)
    w2 = {name: c.shift_summary() for name, c in copies.items()}

    def cu(w, name):
        return float(w[name]["cu_t"])

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
        "loss_cu_t_2000": {name: cu(w1, "base") - cu(w1, name) for name in copies if name != "base"},
        "d_cu_t": cu(w1, "by_value") - cu(w1, "by_loud"),
        "d_cu_t_0800": cu(w2, "by_value") - cu(w2, "by_loud"),
        "d_usd": usd(w1, "by_value") - usd(w1, "by_loud"),
        "bookings": bookings,
        "seconds": round(time.perf_counter() - wall0, 2),
        # extras for the sensitivity report
        "rec_pct_2000": {name: float(w1[name].get("recovery_pct", NO_VALUE)) for name in copies},
        "cu_feed_t_2000": {name: float(w1[name].get("cu_feed_t", NO_VALUE)) for name in copies},
        "n_hidden": sum(1 for tr in shift.troubles if tr.hidden),
    }
    if "no_twin" in copies:
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
    seeds = list(range(int(cfg["seed0"]), int(cfg["seed0"]) + int(cfg["n"])))
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
    summary = {
        "d_cu_t_2000": summarize([r["d_cu_t"] for r in rows], boot, rng),
        "d_cu_t_0800": summarize([r["d_cu_t_0800"] for r in rows], boot, rng),
        "d_usd_2000": summarize([r["d_usd"] for r in rows], boot, rng, zero=ZERO_T * 14539 * 0.955),
    }
    if cfg["no_twin"]:
        summary["detection_cu_t_2000"] = summarize([r["detection_cu_t"] for r in rows], boot, rng)
        summary["twin_cu_t_2000"] = summarize([r["twin_cu_t"] for r in rows], boot, rng)
    small = max(1000, boot // 5)
    cuts: dict[str, dict] = {}
    for key, label in (("n_troubles", "troubles"), ("shared_crew", "shared_crew")):
        for val in sorted({r[key] for r in rows}, key=str):
            sel = [r["d_cu_t"] for r in rows if r[key] == val]
            cuts[f"{label}={val}"] = summarize(sel, small, rng)
    kinds_cut: dict[str, dict] = {}
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
    out += _fmt_stats(doc["summary"]["d_cu_t_2000"], "t")
    out.append("D at 08:00 next day, t Cu")
    out += _fmt_stats(doc["summary"]["d_cu_t_0800"], "t")
    out.append("D at 20:00, USD (payable Cu - energy - water)")
    out += _fmt_stats(doc["summary"]["d_usd_2000"], "USD")
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
    a = ap.parse_args(argv)
    sets: dict[str, float] = {}
    for item in a.set:
        key, _, val = item.partition("=")
        if key.strip() not in default():
            raise SystemExit("unknown parameter in --set: " + key)
        sets[key.strip()] = float(val)
    cfg = {"n": a.n, "seed0": a.seed0, "kip": a.kip, "sigma_ln": a.sigma_ln, "miss": a.miss,
           "detect_min": a.detect_min, "loud_react_min": a.loud_react, "price": a.price, "no_twin": a.no_twin,
           "boot": a.boot, "jobs": a.jobs, "set": sets, "hidden_mult": a.hidden_mult, "mag": a.mag,
           "asis": not a.no_asis, "asis_notice_min": a.asis_notice}

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
