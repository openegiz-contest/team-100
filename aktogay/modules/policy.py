"""Queue policy: rank(troubles, now, prm) -> Plan. Pure function, no I/O.

Design file 17, section 5 "queue of issues"; evidence map file 19, section 3 A:
  1. Safety first: S0 (people, dam) then S1 (equipment at risk), by time found.
     S0 is never counted in money.
  2. The rest by money over a sliding horizon (12 h): expected loss of every
     order of calls over >= 200 samples of crew arrival (uniform 20-40 min),
     repair time after arrival (lognormal, sigma_ln 0.4) and LME price
     (uniform over the band). Up to q_max_enum issues every order is
     enumerated; above that an ATC-like index orders them.
     A crew (crew-kip, crew-cpd, crew-mill, crew-water) serves one issue at a time;
     an issue with no crew (a role decides) does not compete for anyone.
  3. Levels inside the non-safety part: "now" (losses already run or start
     within 60 min, or the deferral is not safe at P90) and "wait" (can be
     deferred until call_by with P(stock ends before repair) <= 10 %).
     Bands of time to consequence: <3 / 3-15 / 15-60 / >60 min.
  4. Robustness: share of samples in which the chosen first issue is also
     first in that sample's best order. Below q_robust_min the plan says
     "order does not matter" and falls back to level, band and money.
  5. Cost of a 1 h delay per issue: E[r (max(0, A + D + 1 - T) - max(0, A + D - T))].
  6. The "alarm order" (loud issues first, by time found) is evaluated on
     the same samples; the difference is what ordering by money saves.
The result is advice: the web shows "Accept / Disagree"; nothing is called here.
"""
from __future__ import annotations

import itertools
import math
import random
from dataclasses import dataclass, field

from .params import Prm

NO_VALUE = -1.0
MIN_PER_H = 60.0
LEVELS = ("S0", "S1", "now", "wait")
BANDS = ("<3", "3-15", "15-60", ">60")
Z90 = 1.2815515655446004


@dataclass
class Trouble:
    """One issue as the priority module sees it (rates are model estimates)."""
    id: str                      # stable key, e.g. "crusher-2:stop" or "flot-1:loss"
    node: str                    # thing name without namespace
    kind: str                    # rule key, e.g. "crusher_stop", "loss_flot", "hard_ore"
    safety: str = ""             # "S0" | "S1" | ""
    rate_cu_tph: float = 0.0     # loss rate once the consequence starts, t Cu/h
    rate_usd_h: float = 0.0      # the same in USD/h at the base price
    t_conseq_h: float = 0.0      # hours until losses start (0: already running)
    repair_h: float = 1.0        # median repair time after arrival, h
    crew: str = ""               # crew thing that must come, "" when a role decides
    role: str = ""               # responsible role (Russian text)
    detected_at: float = 0.0     # model minute when found
    loud: bool = True            # visible alarm (a state) rather than a module finding
    status: str = "OPEN"
    text: str = ""
    person: str = ""             # person twin who is called (thing name), "" when unknown
    hold: str = ""               # the call waits for this ("пожарные разрешат ремонт"), "" when none
    usd_extra_h: float = 0.0     # part of rate_usd_h that is not copper (energy, reagents, buyer's penalty, water), USD/h
    rep_key: str = ""            # parameter row of the median repair time (its label says what the price stands on)


@dataclass
class Ranked:
    id: str
    rank: int
    level: str                   # S0 | S1 | now | wait
    band: str                    # time-to-consequence band
    exp_loss_usd: float          # loss over the horizon if nobody comes: r x max(0, H - T)
    exp_loss_cu_t: float
    delay_cost_usd: float        # expected cost of calling 1 h later (standalone)
    delay_cost_cu_t: float
    call_by_min: float           # latest safe call time (model min) or NO_VALUE = call now
    p_late_now: float            # P(arrival + repair > T) when called now
    repair_p90_h: float
    crew_free_at: float          # model min when the crew can start (NO_VALUE: free now)


@dataclass
class Plan:
    order: list[Ranked] = field(default_factory=list)        # safety first, then the chosen order
    robust_share: float = 1.0                                # share of samples agreeing on the first non-safety issue
    order_matters: bool = False
    gain_usd: float = 0.0                                    # E[loss, alarm order] - E[loss, chosen order]
    gain_cu_t: float = 0.0
    loss_value_usd: float = 0.0                              # E[loss] of the chosen order over the horizon
    loss_value_cu_t: float = 0.0
    loss_alarm_usd: float = 0.0
    loss_alarm_cu_t: float = 0.0
    alarm_order: list[str] = field(default_factory=list)     # ids in "as now" order
    samples: int = 0
    enumerated: bool = True                                  # False: index order (too many issues)
    horizon_h: float = 12.0


@dataclass
class _Sample:
    arrive: list[float]     # min per trouble
    repair: list[float]     # h per trouble
    price_mult: float


def band_of(t_conseq_h: float, prm: Prm) -> str:
    m = t_conseq_h * MIN_PER_H
    if m < prm["q_band1_min"]:
        return BANDS[0]
    if m < prm["q_band2_min"]:
        return BANDS[1]
    if m <= prm["q_band3_min"]:
        return BANDS[2]
    return BANDS[3]


def p90_hours(median_h: float, prm: Prm) -> float:
    return median_h * math.exp(Z90 * prm["q_sigma_ln"])


def _draw(troubles: list[Trouble], prm: Prm, seed: int) -> list[_Sample]:
    rng = random.Random(seed)
    n = max(1, int(prm["q_samples"]))
    lo, hi = prm["q_arrive_lo_min"], prm["q_arrive_hi_min"]
    p0 = prm["cu_price_usd_t"]
    plo, phi = prm["cu_price_lo_usd_t"], prm["cu_price_hi_usd_t"]
    out = []
    for _ in range(n):
        arrive = [rng.uniform(lo, hi) for _ in troubles]
        repair = [max(0.0, t.repair_h) * math.exp(prm["q_sigma_ln"] * rng.gauss(0.0, 1.0)) for t in troubles]
        price = rng.uniform(plo, phi) / p0 if p0 > 0.0 else 1.0
        out.append(_Sample(arrive, repair, price))
    return out


def _loss(order: tuple[int, ...], smp: _Sample, troubles: list[Trouble], now: float, horizon_min: float,
          crews: dict[str, list[float]]) -> tuple[float, float]:
    """(USD, t Cu) lost over the horizon when crews are called in `order` under one sample."""
    free = {c: list(v) for c, v in crews.items()}
    usd = cu = 0.0
    for i in order:
        tr = troubles[i]
        if tr.crew:
            slots = free.setdefault(tr.crew, [now])
            j = min(range(len(slots)), key=lambda k: slots[k])
            start = max(now, slots[j])
        else:
            start = now
            j = -1
        arrive = start + smp.arrive[i]
        done = arrive + smp.repair[i] * MIN_PER_H
        if j >= 0:
            free[tr.crew][j] = done
        t0 = now + max(0.0, tr.t_conseq_h) * MIN_PER_H
        t1 = min(done, now + horizon_min)
        hours = max(0.0, t1 - t0) / MIN_PER_H
        if tr.safety == "S0":
            continue                                   # not counted in money
        usd += tr.rate_usd_h * hours * smp.price_mult
        cu += tr.rate_cu_tph * hours
    return usd, cu


def _mean(xs) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def _index_order(rest: list[int], smp: _Sample | None, troubles: list[Trouble], mean_d: float) -> list[int]:
    """ATC-like index: rate / (A + D) x exp(-slack / kappa), slack = max(0, T - (A + D)), kappa = mean D."""
    def prio(i: int) -> float:
        tr = troubles[i]
        a = smp.arrive[i] / MIN_PER_H if smp else 0.5
        d = smp.repair[i] if smp else tr.repair_h
        dur = max(0.05, a + d)
        slack = max(0.0, tr.t_conseq_h - dur)
        return tr.rate_usd_h / dur * math.exp(-slack / max(0.5, mean_d))
    return sorted(rest, key=lambda i: (-prio(i), troubles[i].detected_at, troubles[i].id))


def _fallback_order(rest: list[int], troubles: list[Trouble], prm: Prm, horizon_h: float) -> list[int]:
    """Issues that cost nothing over the horizon last; then time-to-consequence band, expected loss
    over the horizon, time found. (A $0 issue never goes first just because its band is "now".)"""
    def key(i: int):
        tr = troubles[i]
        band = BANDS.index(band_of(tr.t_conseq_h, prm))
        loss = tr.rate_usd_h * max(0.0, horizon_h - tr.t_conseq_h)
        return (loss <= 0.0, band, -loss, tr.detected_at, tr.id)
    return sorted(rest, key=key)


def rank(troubles: list[Trouble], now_min: float, prm: Prm, crews: dict[str, list[float]] | None = None,
         seed: int = 0) -> Plan:
    """Rank issues; see the module docstring.

    troubles: active issues (OPEN or SNOOZED; CALLED ones are represented by
    the busy crews). now_min: model minute. crews: crew name -> list of model
    minutes when each team is free (missing crew = one team, free now).
    seed: makes the samples reproducible (the module passes seed and tact).
    """
    plan = Plan(horizon_h=prm["q_horizon_h"], samples=int(prm["q_samples"]))
    if not troubles:
        return plan
    troubles = sorted(troubles, key=lambda t: (t.detected_at, t.id))
    horizon_min = plan.horizon_h * MIN_PER_H
    crews = {c: [max(now_min, float(x)) if x != NO_VALUE else now_min for x in v]
             for c, v in (crews or {}).items()}
    samples = _draw(troubles, prm, seed)
    idx = list(range(len(troubles)))
    s0 = [i for i in idx if troubles[i].safety == "S0"]
    s1 = [i for i in idx if troubles[i].safety == "S1"]
    rest = [i for i in idx if troubles[i].safety not in ("S0", "S1")]
    prefix = tuple(s0 + s1)

    # --- choose the order of the non-safety issues ---
    chosen: list[int]
    if len(rest) >= 2:
        if len(rest) <= int(prm["q_max_enum"]):
            perms = list(itertools.permutations(rest))
            table = [[_loss(prefix + p, s, troubles, now_min, horizon_min, crews)[0] for s in samples]
                     for p in perms]
            means = [_mean(row) for row in table]
            # ties (an issue without loss does not change the sum): issues with a loss go first
            best = min(range(len(perms)), key=lambda k: (round(means[k], 6),
                                                          tuple(troubles[i].rate_usd_h <= 0.0 for i in perms[k]),
                                                          perms[k]))
            chosen = list(perms[best])
            first = chosen[0]
            agree = 0
            for si in range(len(samples)):
                col = [table[k][si] for k in range(len(perms))]
                m = min(col)
                if any(perms[k][0] == first and col[k] <= m + 1e-9 for k in range(len(perms))):
                    agree += 1
            plan.robust_share = agree / len(samples)
            # best order with another first issue: the gain of the choice
            others = [means[k] for k in range(len(perms)) if perms[k][0] != first]
            alt = min(others) if others else means[best]
            plan.enumerated = True
        else:
            mean_d = _mean(t.repair_h for t in troubles)
            chosen = _index_order(rest, None, troubles, mean_d)
            first = chosen[0]
            agree = sum(1 for s in samples if _index_order(rest, s, troubles, mean_d)[0] == first)
            plan.robust_share = agree / len(samples)
            best_loss = _mean(_loss(prefix + tuple(chosen), s, troubles, now_min, horizon_min, crews)[0]
                              for s in samples)
            swapped = [chosen[1], chosen[0]] + chosen[2:]
            alt = _mean(_loss(prefix + tuple(swapped), s, troubles, now_min, horizon_min, crews)[0]
                        for s in samples)
            means = [best_loss]
            best = 0
            plan.enumerated = False
        gain_first = alt - means[best]
        plan.order_matters = (plan.robust_share >= prm["q_robust_min"]
                              and gain_first > max(50.0, 0.01 * abs(means[best])))
        if not plan.order_matters:
            chosen = _fallback_order(rest, troubles, prm, plan.horizon_h)
    else:
        chosen = list(rest)
        plan.robust_share = 1.0
        plan.order_matters = False

    order = list(prefix) + chosen
    alarm = list(prefix) + sorted(rest, key=lambda i: (not troubles[i].loud, troubles[i].detected_at, troubles[i].id))
    plan.alarm_order = [troubles[i].id for i in alarm]

    v = [_loss(tuple(order), s, troubles, now_min, horizon_min, crews) for s in samples]
    a = [_loss(tuple(alarm), s, troubles, now_min, horizon_min, crews) for s in samples]
    plan.loss_value_usd, plan.loss_value_cu_t = _mean(x[0] for x in v), _mean(x[1] for x in v)
    plan.loss_alarm_usd, plan.loss_alarm_cu_t = _mean(x[0] for x in a), _mean(x[1] for x in a)
    plan.gain_usd = plan.loss_alarm_usd - plan.loss_value_usd
    plan.gain_cu_t = plan.loss_alarm_cu_t - plan.loss_value_cu_t

    # --- per issue numbers ---
    for r, i in enumerate(order, start=1):
        tr = troubles[i]
        ad = sorted(s.arrive[k] / MIN_PER_H + s.repair[k] for k, s in ((i, s) for s in samples))
        q90 = ad[min(len(ad) - 1, int(math.ceil(0.9 * len(ad))) - 1)] if ad else tr.repair_h
        p_late = sum(1 for x in ad if x > tr.t_conseq_h) / len(ad) if ad else 1.0
        t_free = NO_VALUE
        if tr.crew and crews.get(tr.crew):
            t_free = min(crews[tr.crew])
            if t_free <= now_min:
                t_free = NO_VALUE
        wait_from = now_min if t_free == NO_VALUE else t_free
        delay = [tr.rate_usd_h * (max(0.0, x + 1.0 - tr.t_conseq_h) - max(0.0, x - tr.t_conseq_h)) * s.price_mult
                 for x, s in zip((s.arrive[i] / MIN_PER_H + s.repair[i] for s in samples), samples)]
        delay_cu = [tr.rate_cu_tph * (max(0.0, x + 1.0 - tr.t_conseq_h) - max(0.0, x - tr.t_conseq_h))
                    for x in (s.arrive[i] / MIN_PER_H + s.repair[i] for s in samples)]
        call_by = now_min + tr.t_conseq_h * MIN_PER_H - q90 * MIN_PER_H
        if tr.safety in ("S0", "S1"):
            level = tr.safety
            call_by = NO_VALUE
        elif (band_of(tr.t_conseq_h, prm) != BANDS[3] or p_late > prm["q_defer_p_max"]
              or call_by <= wait_from):
            level = "now"
            call_by = NO_VALUE
        else:
            level = "wait"
        horizon_loss_h = max(0.0, plan.horizon_h - tr.t_conseq_h)
        plan.order.append(Ranked(
            id=tr.id, rank=r, level=level, band=band_of(tr.t_conseq_h, prm),
            exp_loss_usd=0.0 if tr.safety == "S0" else tr.rate_usd_h * horizon_loss_h,
            exp_loss_cu_t=tr.rate_cu_tph * horizon_loss_h,
            delay_cost_usd=0.0 if tr.safety == "S0" else _mean(delay),
            delay_cost_cu_t=_mean(delay_cu),
            call_by_min=call_by, p_late_now=p_late, repair_p90_h=p90_hours(tr.repair_h, prm),
            crew_free_at=t_free))
    return plan


def first_choice_losses(troubles: list[Trouble], now_min: float, prm: Prm,
                        crews: dict[str, list[float]] | None = None, seed: int = 0) -> dict[str, tuple[float, float]]:
    """Expected loss over the horizon (USD, t Cu) when each non-safety trouble is called FIRST and the others
    follow in their best order; the same samples as rank(). Safety issues go first in every case.
    Used for the price of a choice (one free crew, two troubles) and for the shift review ("what if you had
    called otherwise"). Empty when there are fewer than two non-safety troubles."""
    troubles = sorted(troubles, key=lambda t: (t.detected_at, t.id))
    idx = list(range(len(troubles)))
    prefix = tuple(i for i in idx if troubles[i].safety == "S0") + tuple(i for i in idx if troubles[i].safety == "S1")
    rest = [i for i in idx if troubles[i].safety not in ("S0", "S1")]
    if len(rest) < 2:
        return {}
    crews = {c: [max(now_min, float(x)) if x != NO_VALUE else now_min for x in v] for c, v in (crews or {}).items()}
    samples = _draw(troubles, prm, seed)
    horizon_min = prm["q_horizon_h"] * MIN_PER_H
    out: dict[str, tuple[float, float]] = {}
    for first in rest:
        others = [i for i in rest if i != first]
        if len(others) <= int(prm["q_max_enum"]) - 1:
            orders = [(first,) + p for p in itertools.permutations(others)]
        else:
            orders = [(first,) + tuple(_fallback_order(others, troubles, prm, prm["q_horizon_h"]))]
        best = None
        for o in orders:
            rows = [_loss(prefix + o, smp, troubles, now_min, horizon_min, crews) for smp in samples]
            usd, cu = _mean(r[0] for r in rows), _mean(r[1] for r in rows)
            if best is None or usd < best[0] - 1e-9:
                best = (usd, cu)
        out[troubles[first].id] = best
    return out


def hhmm(t_min: float) -> str:
    """Model minute -> 'HH:MM' on a 24 h clock."""
    m = int(round(t_min)) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"
