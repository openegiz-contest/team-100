"""Sensors: measurement noise, on-stream analyser, laboratory, the constant
tails alarm of the control system, and the measured feature snapshot.

Design: section 4 "noise and delays", "control-system rule"; section 3
(features per thing); section 5 (modules read only measured features).

Noise is a pure function of (seed, step, stream): the same value in every
copy of the plant. Truth fields (state "truth" comments) never go out.

Measured snapshot, per instrument (sigma from the parameter table):
  belt weighers  sens_weigher_sigma   crusher/conveyor t/h (one scale), SAG feed
                                      (= line t/h, rougher feed), pebbles, pit,
                                      excavators, concentrate flows, cake
  power meters   sens_power_sigma     unit kW, site / grinding MW
  flowmeters     sens_flow_sigma      water intake and recycle, thickener overflow
  P80 analyser   sens_p80_sigma_um    cyclone overflow P80 (absolute)
  dose meter     sens_dose_sigma      collector flowmeter (reads the setpoint
                                      during a drift: the truth is dose_true_gt)
  analyser       sens_an_*_sigma      flot grades, held between 15 min cycles
Recovery, Cu t/h and concentrate t/h of a line come from the two-product
formula on analyser grades and the weighed feed, as plant accounting does:
  R = c (f - t) / (f (c - t)),  y = (f - t) / (c - t),  conc = Q y,  Cu = Q c y / 100.
Readings that are already noisy at the source (lube pressure, piezometer,
cake moisture) and computed counters (cum_*, wear by norm, levels) pass as is.
"""
from __future__ import annotations

import math

from .events import scenario_label
from . import wear as wear_mod
from .params import FEATURE_RULES, ParamSet
from .state import (MIN_PER_H, NO_VALUE, AnalyzerState, FlotState, LabResult, LabState, LineState,
                    PlantState, ThingInfo, normal, topology)

# Site features filled by the service layer, not by the model core.
SERVICE_FEATURES = {"site": ("speed", "speed_fact", "heartbeat", "degraded")}

# Features published as strings; every other feature is a float.
STR_FEATURES = frozenset({"state", "state_ru", "block", "location", "plan_text", "scenario", "task", "shed_text",
                          "duty", "hardness", "permit", "fatigue_truck", "brake_truck"})

# Russian words of the state codes (feature state_ru, for display; "state" keeps the code).
STATE_RU = {
    "RUN": "работает", "PAUSED": "пауза", "WARMUP": "прогрев", "STOP": "стоит", "SLOW": "медленно",
    "DIG": "копает", "MOVE": "переезд", "IDLE": "простой", "DOWN": "неисправен",
    "PLANNED": "в плане", "BELT": "в пути", "IN_STOCK": "на складе", "DONE": "переработана",
    "NORMAL": "норма", "LOW": "мало", "EMPTY": "пусто", "FULL": "полон", "HIGH": "высоко",
    "LIMITED": "ограничена", "STARVED": "мало питания", "LIMITED_GRID": "лимит сети",
    "RELINE": "перефутеровка", "UPSET": "сбой режима", "LIMIT": "на пределе", "ONE": "один пресс",
    "ALARM": "тревога", "SHORT": "не хватает", "FREE": "свободен", "TRAVEL": "в пути", "WORK": "работает",
    "OFF": "вне работы", "LOADING": "погрузка", "HAUL_FULL": "едет гружёный", "QUEUE": "очередь",
    "DUMP": "разгрузка", "RETURN": "едет порожний", "OPEN": "открыта", "CLOSED": "закрыта",
    "ACTIVE": "в работе", "OK": "исправен", "DRIFT": "дрейф", "SUSPECT": "под подозрением",
    "DRILLING": "бурит", "MOVING": "переезд", "COLD": "холодное выщелачивание",
}


def state_ru(code: str) -> str:
    """Russian word of a state code ("" for an empty or unknown code)."""
    return STATE_RU.get(str(code or ""), "")


KPA_PER_M = 9.81            # unit conversion: kPa of one metre of water (piezometer level)


def hardness_ru(axb: float, prm: ParamSet) -> str:
    """Hardness class of a block by its A*b estimate: the colour classes of the interface (ui_axb_*)."""
    if not _valid(axb) or axb <= 0.0:
        return ""
    if axb < prm["ui_axb_hard"]:
        return "твёрдая"
    if axb >= prm["ui_axb_soft"]:
        return "мягче базовой"
    return "средняя"

_EPS = 1e-6   # min, tolerance for cycle boundaries
_PCT = 100.0  # % per unit share

_TOPO: dict[str, ThingInfo] | None = None


def _topo() -> dict[str, ThingInfo]:
    global _TOPO
    if _TOPO is None:
        _TOPO = topology()
    return _TOPO


def _f(x) -> float:
    """Published float: bool -> 1.0/0.0, None or non-finite -> NO_VALUE."""
    if x is None:
        return NO_VALUE
    v = float(x)
    return v if math.isfinite(v) else NO_VALUE


def _valid(x: float) -> bool:
    return x != NO_VALUE and math.isfinite(x)


# ---------------------------------------------------------------------------
# Noise
# ---------------------------------------------------------------------------
def noisy(value: float, rel_sigma: float, seed: int, step: int, stream: str, k: int = 0) -> float:
    """value * (1 + rel_sigma * N(0, 1)) from (seed, step, stream, k); NO_VALUE passes through."""
    if value is None or value == NO_VALUE or not math.isfinite(value):
        return NO_VALUE
    return float(value) * (1.0 + rel_sigma * normal(seed, step, stream, k))


def noisy_abs(value: float, sigma: float, seed: int, step: int, stream: str, k: int = 0) -> float:
    """value + sigma * N(0, 1) from (seed, step, stream, k); NO_VALUE passes through."""
    if value is None or value == NO_VALUE or not math.isfinite(value):
        return NO_VALUE
    return float(value) + sigma * normal(seed, step, stream, k)


# ---------------------------------------------------------------------------
# Analyser, laboratory, control-system rule
# ---------------------------------------------------------------------------
def _cycle_no(t_min: float, cycle_min: float) -> int:
    return math.floor((t_min + _EPS) / cycle_min)


def analyzer_step(an: AnalyzerState, fl: FlotState, line: int, t_min: float, seed: int,
                  step: int, prm: ParamSet) -> bool:
    """On-stream analyser of one line; returns True when a new reading is made.

    A reading every sens_an_cycle_min (first at the first call; then once in
    each cycle of the model clock, so a 10 min step still gives 4 per hour):
    feed_cu, tail_cu, conc_cu (% Cu) = true values of fl with relative noise
    sens_an_feed_sigma, sens_an_tail_sigma, sens_an_conc_sigma (streams
    "an-feed-<line>", "an-tail-<line>", "an-conc-<line>"). A stopped section
    (grades NO_VALUE) reads NO_VALUE. Control rule: above_count += 1 when
    tail_cu > acs_tail_sp_pct else 0; alarm = above_count >= acs_cycles.
    """
    cycle = prm["sens_an_cycle_min"]
    if an.blocked and an.last_t_min != NO_VALUE:
        return False                                  # blocked sample line: the last reading is held, its age grows
    if an.last_t_min != NO_VALUE and _cycle_no(t_min, cycle) <= _cycle_no(an.last_t_min, cycle):
        return False
    an.last_t_min = float(t_min)
    an.feed_cu = noisy(fl.feed_cu, prm["sens_an_feed_sigma"], seed, step, f"an-feed-{line}")
    an.tail_cu = noisy(fl.tail_cu, prm["sens_an_tail_sigma"], seed, step, f"an-tail-{line}")
    an.conc_cu = noisy(fl.conc_cu, prm["sens_an_conc_sigma"], seed, step, f"an-conc-{line}")
    if _valid(an.tail_cu) and an.tail_cu > prm["acs_tail_sp_pct"]:
        an.above_count += 1
    else:
        an.above_count = 0
    an.alarm = an.above_count >= int(prm["acs_cycles"])
    return True


def lab_step(lab: LabState, ln: LineState, ascu_true: float, t_min: float, seed: int,
             step: int, prm: ParamSet, feed_batch: str = "") -> LabResult | None:
    """Shift laboratory of one line; returns a result when it becomes ready.

    Samples every sens_lab_every_h aligned to model midnight; result ready
    sens_lab_delay_h later with relative noise sens_lab_sigma on feed Cu,
    ASCu and tails Cu (truth taken at sampling time; streams "lab-feed-<n>",
    "lab-ascu-<n>", "lab-tail-<n>"). lab.last = newest ready.
    ascu_true: ASCu of the flotation feed now, % of total Cu (cause effects included).
    feed_batch: batch that dominates the SAG feed at sampling time; the result
    carries it (batch_id), so the plant can book the feed Cu to that batch (cu_meas).
    """
    every = prm["sens_lab_every_h"] * MIN_PER_H
    delay = prm["sens_lab_delay_h"] * MIN_PER_H
    t = float(t_min)
    if lab.next_sample_min == NO_VALUE:
        lab.next_sample_min = math.ceil((t - _EPS) / every) * every
    if t + _EPS >= lab.next_sample_min:
        fl = ln.flot
        feed = fl.feed_cu if fl is not None else NO_VALUE
        tail = fl.tail_cu if fl is not None else NO_VALUE
        sig = prm["sens_lab_sigma"]
        n = ln.n
        lab.pending.append(LabResult(
            t_sample_min=t, t_ready_min=t + delay,
            feed_cu=noisy(feed, sig, seed, step, f"lab-feed-{n}"),
            ascu_pct=noisy(ascu_true, sig, seed, step, f"lab-ascu-{n}"),
            tail_cu=noisy(tail, sig, seed, step, f"lab-tail-{n}"), batch_id=feed_batch))
        lab.next_sample_min = (math.floor((t + _EPS) / every) + 1) * every
    ready = [r for r in lab.pending if r.t_ready_min <= t + _EPS]
    if not ready:
        return None
    lab.pending = [r for r in lab.pending if r.t_ready_min > t + _EPS]
    lab.last = max(ready, key=lambda r: r.t_ready_min)
    return lab.last


def two_product(feed_cu: float, tail_cu: float, conc_cu: float) -> tuple[float, float]:
    """Two-product formula: (recovery %, concentrate mass yield -) from grades in % Cu.

    R = c (f - t) / (f (c - t)) * 100, y = (f - t) / (c - t); clamped to
    [0, 100] and [0, 1]. (NO_VALUE, NO_VALUE) when a grade is missing or c <= t.
    """
    f, t, c = feed_cu, tail_cu, conc_cu
    if not (_valid(f) and _valid(t) and _valid(c)) or f <= 0.0 or c <= t:
        return NO_VALUE, NO_VALUE
    y = min(1.0, max(0.0, (f - t) / (c - t)))
    rec = min(_PCT, max(0.0, _PCT * c * y / f))
    return rec, y


# ---------------------------------------------------------------------------
# Feature snapshots
# ---------------------------------------------------------------------------
def _blank(typ: str) -> dict[str, float | str]:
    return {k: ("" if k in STR_FEATURES else NO_VALUE) for k in FEATURE_RULES[typ]}


def _keys(typ: str) -> tuple[str, ...]:
    skip = SERVICE_FEATURES.get(typ, ())
    return tuple(k for k in FEATURE_RULES[typ] if k not in skip)


def _line_no(tid: str) -> int:
    tail = tid.rsplit("-", 1)[-1]
    digits = ""
    for ch in tail:
        if not ch.isdigit():
            break
        digits += ch
    return int(digits) if digits else 0


class _Snap:
    """Builds the snapshot of one state, measured (with noise) or truth."""

    def __init__(self, st: PlantState, prm: ParamSet | None, measured: bool):
        self.st = st
        self.prm = prm
        self.m = measured
        self.seed = st.seed
        self.step = st.clock.step
        self.lines = {ln.n: ln for ln in st.lines}
        self.q: dict[int, float] = {}       # line t/h
        self.rec: dict[int, float] = {}     # line recovery, %
        self.cu: dict[int, float] = {}      # line Cu in concentrate, t/h
        self.conc: dict[int, float] = {}    # line concentrate, t/h
        self._trucks = None                 # name -> TruckState, built on first use
        for n, ln in self.lines.items():
            self._line_pass(n, ln)

    # -- instruments -------------------------------------------------------
    def rel(self, value, sigma_key: str, stream: str) -> float:
        """Relative noise of the instrument sigma_key (truth: value as is)."""
        if not self.m:
            return _f(value)
        return _f(noisy(_f(value), self.prm[sigma_key], self.seed, self.step, stream))

    def weigher(self, value, stream: str) -> float:
        return self.rel(value, "sens_weigher_sigma", stream)

    def power(self, value, stream: str) -> float:
        return self.rel(value, "sens_power_sigma", stream)

    def flow(self, value, stream: str) -> float:
        return self.rel(value, "sens_flow_sigma", stream)

    def pct(self, value, sigma_key: str, stream: str) -> float:
        """Assay-based percentage (stage recovery): relative noise, kept in [0, 100]."""
        v = self.rel(value, sigma_key, stream)
        return min(_PCT, max(0.0, v)) if _valid(v) else v

    # -- per line accounting ------------------------------------------------
    def _line_pass(self, n: int, ln: LineState) -> None:
        fl = ln.flot
        if not self.m:
            self.q[n] = _f(ln.tph)
            self.rec[n] = _f(ln.recovery)
            self.cu[n] = _f(ln.cu_tph)
            self.conc[n] = _f(fl.conc_tph) if fl is not None else NO_VALUE
            return
        q = self.weigher(ln.tph, f"sag-{n}-feed_tph")
        an = ln.analyzer
        rec, y = two_product(an.feed_cu, an.tail_cu, an.conc_cu)
        self.q[n] = q
        self.rec[n] = rec
        if _valid(q) and q <= 0.0:
            self.cu[n], self.conc[n] = 0.0, 0.0
        elif _valid(q) and _valid(y):
            self.conc[n] = q * y
            self.cu[n] = q * y * an.conc_cu / _PCT
        else:
            self.cu[n], self.conc[n] = NO_VALUE, NO_VALUE

    # -- things ------------------------------------------------------------
    def thing(self, tid: str, info: ThingInfo) -> dict[str, float | str]:
        typ = info.type
        build = _BUILDERS[typ]
        obj = self.obj(tid, typ)
        if obj is None:
            return {k: v for k, v in _blank(typ).items() if k in _keys(typ)}
        d = build(self, tid, obj)
        return self.conform(typ, d)

    @staticmethod
    def conform(typ: str, d: dict) -> dict[str, float | str]:
        """Exactly the rule keys of the type: strings stay str, the rest float; state_ru from state."""
        blank = _blank(typ)
        out: dict[str, float | str] = {}
        for k in _keys(typ):
            v = d.get(k, blank[k])
            out[k] = str(v) if k in STR_FEATURES else _f(v)
        if "state_ru" in out and not d.get("state_ru"):
            out["state_ru"] = state_ru(out.get("state", ""))
        return out

    @property
    def table(self) -> ParamSet:
        """Parameters (the table values for a truth snapshot, which has none)."""
        if self.prm is None:
            from .params import default
            self.prm = default()
        return self.prm

    def obj(self, tid: str, typ: str):
        st = self.st
        if typ == "site":
            return st
        if typ == "pit":
            return st.pit
        if typ == "fleet":
            return st.fleet
        if typ == "exc":
            return next((e for e in st.excavators + st.waste_excavators if e.name == tid), None)
        if typ == "person":
            return st.people.get(tid)
        if typ == "truck":
            if self._trucks is None:
                self._trucks = {x.name: x for x in st.trucks}
            return self._trucks.get(tid)
        if typ == "face":
            return st.faces.get(tid)
        if typ == "drill":
            return next((x for x in st.drills if x.name == tid), None)
        if typ == "dozer":
            return next((x for x in st.dozers if x.name == tid), None)
        if typ == "road":
            return st.roads.get(tid)
        if typ == "piezometer":
            return st.water
        if typ == "conc-stock":
            return st.conc_stock
        if typ == "leach":
            return st.leach
        if typ == "sxew":
            return st.sxew
        if typ == "water":
            return st.water
        if typ == "power":
            return st.power
        if typ == "crew":
            return st.crews.get(tid)
        ln = self.lines.get(_line_no(tid))
        if ln is None:
            return None
        if typ in ("line", "analyzer", "weigher", "flowmeter", "phmeter"):
            return ln
        if typ == "ball":
            return next((b for b in ln.balls if b.name == tid), None)
        return getattr(ln, _LINE_ATTR[typ], None)

    def batch(self, b) -> dict[str, float | str]:
        d = {"state": b.state, "location": b.location, "tonnes_left": b.tonnes_left,
             "pit_t": max(0.0, b.tonnes - b.dug_t), "cu_meas": b.cu_meas, "axb_soft": b.axb_soft}
        if not self.m:
            # Truth: the quantities the lab and the soft sensor estimate.
            d["cu_meas"] = b.true.cu_pct if b.true.cu_pct > 0.0 else NO_VALUE
            d["axb_soft"] = b.true.axb if b.true.axb > 0.0 else NO_VALUE
        return self.conform("batch", d)


# ---------------------------------------------------------------------------
# Builders per thing type: (snap, thingId, state object) -> {feature: value}
# ---------------------------------------------------------------------------
_LINE_ATTR = {"crusher": "crusher", "conveyor": "conveyor", "stockpile": "stockpile", "sag": "sag",
              "pebble": "pebble", "cyclones": "cyclones", "flot": "flot", "rougher": "rougher",
              "cleaner": "cleaner", "thick": "thick", "filter": "filter"}


def _sum_or_none(values) -> float:
    vals = list(values)
    if not vals or any(not _valid(v) for v in vals):
        return NO_VALUE
    return float(sum(vals))


def _b_site(c: _Snap, tid, st: PlantState):
    return {
        "state": st.site_state,
        "seed": float(st.seed),
        "tph": _sum_or_none(c.q.values()),
        "cu_tph": _sum_or_none(c.cu.values()),
        "power_mw": c.power(st.power.site_mw, "power-site_mw"),
        "water_m3h": c.flow(st.water.intake_m3h, "water-intake_m3h"),
        "scenario": scenario_label(st.scenario, hidden=not c.m),
        # what-if levers (control of the model, not of the plant): 100 / -1 = neutral
        "lever_on": 1.0 if st.levers else 0.0,
        "lever_feed_1": st.levers.get("feed_1", 100.0), "lever_feed_2": st.levers.get("feed_2", 100.0),
        "lever_p80_um": st.levers.get("p80_um", NO_VALUE), "lever_dose_gt": st.levers.get("dose_gt", NO_VALUE),
    }


def _b_pit(c: _Snap, tid, pit):
    restrict = pit.restrict_until_min != NO_VALUE and c.st.clock.t_min < pit.restrict_until_min
    return {"state": pit.state, "mining_tph": c.weigher(pit.mining_tph, "pit-mining_tph"),
            "next_block": pit.next_block_no,
            "plan_text": pit.plan_text, "hard_in_plan": 1.0 if pit.hard_in_plan else 0.0,
            "visibility_m": pit.visibility_m, "road_grip": pit.road_grip,
            "haul_speed_pct": _PCT / pit.cycle_mult if pit.cycle_mult > 0.0 else NO_VALUE,
            "road_restrict": 1.0 if restrict else 0.0}


def _b_exc(c: _Snap, tid, e):
    d = {"state": e.state, "tph": c.weigher(e.tph, f"{tid}-tph"), "block": e.block, "bench": e.bench,
         "oil_pct": NO_VALUE, "oil_alert": NO_VALUE}
    if tid in _oil_sensor():               # only machines whose sensor a source confirms (EX3600-6)
        d["oil_pct"] = e.oil_pct if not c.m else _f(noisy(e.oil_pct, 0.01, c.seed, c.step, f"{tid}-oil_pct"))
        d["oil_alert"] = 1.0 if e.oil_pct >= c.table["pit_oil_alert_pct"] else 0.0
    return d


def _oil_sensor() -> tuple[str, ...]:
    from .state import site
    return tuple(getattr(site(), "OIL_SENSOR", ()))


def _b_fleet(c: _Snap, tid, fl):
    st = c.st
    return {"state": fl.state, "exc_total": fl.exc_total, "exc_ready": fl.exc_ready,
            "trucks_total": fl.trucks_total,
            "trucks_ready": fl.trucks_ready, "truck_kio_shift": fl.truck_kio_shift,
            "haul_tph": fl.haul_tph, "mining_tph": c.weigher(fl.mining_tph, "pit-mining_tph"),
            "trucks_ore": sum(1 for t in st.trucks if t.ready and t.duty == "ore") if st.trucks else NO_VALUE,
            "waste_tph": c.weigher(sum(e.tph for e in st.waste_excavators), "pit-waste_tph"),
            "fatigue": 1.0 if fl.fatigue else 0.0, "fatigue_truck": fl.fatigue_truck}


def _b_crusher(c: _Snap, tid, cr):
    n = cr.line
    lube = cr.lube_kpa if c.m else cr.lube_kpa - cr.lube_bias_kpa   # truth: without the sensor fault
    t = c.st.clock.t_min
    svc = cr.fault == "mantle"
    left = max(0.0, cr.service_until_min - t) / MIN_PER_H if svc and cr.service_until_min != NO_VALUE else NO_VALUE
    return {"state": cr.state, "tph": c.weigher(cr.tph, f"conveyor-{n}-tph"),
            "power_kw": c.power(cr.power_kw, f"{tid}-power_kw"), "lube_kpa": lube,
            "service": 1.0 if svc else 0.0, "service_left_h": left}


def _b_conveyor(c: _Snap, tid, cv):
    return {"state": cv.state, "tph": c.weigher(cv.tph, f"conveyor-{cv.line}-tph"),
            "power_kw": c.power(cv.power_kw, f"{tid}-power_kw"), "fault": 1.0 if cv.fault else 0.0}


def _b_stockpile(c: _Snap, tid, sp):
    return {"state": sp.state, "level_t": sp.level_t, "in_tph": c.weigher(sp.in_tph, f"{tid}-in_tph"),
            "out_tph": c.weigher(sp.out_tph, f"sag-{sp.line}-feed_tph"), "hours_left": sp.hours_left}


def _b_line(c: _Snap, tid, ln):
    n = ln.n
    return {"state": ln.state, "tph": c.q[n], "cu_tph": c.cu[n], "recovery": c.rec[n],
            "cum_cu_t": ln.cum_cu_t, "cum_mwh": ln.cum_mwh, "cum_m3": ln.cum_m3, "cum_usd": ln.cum_usd,
            "cum_cu_t_total": ln.cum_cu_t_total, "cum_mwh_total": ln.cum_mwh_total,
            "cum_m3_total": ln.cum_m3_total, "cum_usd_total": ln.cum_usd_total,
            "balls_gt": c.rel(ln.balls_gt, "sens_balls_sigma", f"line-{n}-balls_gt") if ln.tph > 0.0 else NO_VALUE}


def _b_sag(c: _Snap, tid, sag):
    n = sag.line
    p = c.power(sag.power_kw, f"{tid}-power_kw")
    q = c.weigher(sag.feed_tph, f"sag-{n}-feed_tph")
    d = {"state": sag.state, "power_kw": p, "power_limit_kw": sag.power_limit_kw, "feed_tph": q,
         "speed_pct": sag.speed_pct, "load_pct": sag.load_pct, "liner_wear_mm": sag.liner_wear_mm,
         "liner_ground_t": sag.liner_ground_t}
    if not c.m:
        d["e_kwh_t"] = sag.e_kwh_t
        d["axb_soft"] = sag.feed_ore.axb if sag.feed_ore.axb > 0.0 else NO_VALUE
        return d
    e_meas = p / q if _valid(p) and _valid(q) and q > 0.0 and p > 0.0 else NO_VALUE
    d["e_kwh_t"] = e_meas
    # Soft sensor on measured P/Q: E ~ DWi^b ~ (A*b)^-b, so A*b scales as E^(-1/b).
    e_true = sag.power_kw / sag.feed_tph if sag.feed_tph > 0.0 and sag.power_kw > 0.0 else NO_VALUE
    axb = sag.axb_soft
    if _valid(axb) and axb > 0.0 and _valid(e_meas) and _valid(e_true):
        axb = axb * (e_meas / e_true) ** (-1.0 / c.prm["sag_morrell_b"])
    d["axb_soft"] = axb
    return d


def _b_pebble(c: _Snap, tid, pb):
    feed = c.weigher(pb.feed_tph, f"{tid}-feed_tph")
    if c.m:
        load = _PCT * feed / pb.limit_tph if _valid(feed) and pb.limit_tph > 0.0 else NO_VALUE
    else:
        load = pb.load_pct
    fire = 1.0 if c.st.flags.get("fire") == float(pb.line) else 0.0
    hp = pb.hpgr_tph > 0.0
    if hp:
        hload = _PCT * feed / pb.hpgr_tph if c.m and _valid(feed) else pb.hpgr_load_pct
        hkw = c.power(pb.hpgr_kw, f"{tid}-hpgr_kw") if pb.hpgr_kw > 0.0 else 0.0
    else:
        hload = hkw = NO_VALUE
    return {"state": pb.state, "feed_tph": feed, "limit_tph": pb.limit_tph, "load_pct": load, "fire": fire,
            "hpgr_tph": pb.hpgr_tph if hp else NO_VALUE, "hpgr_load_pct": hload, "hpgr_kw": hkw,
            "hpgr_skew_pct": pb.hpgr_skew_pct if hp else NO_VALUE,
            "hpgr_kw_diff_pct": pb.hpgr_kw_diff_pct if hp else NO_VALUE,
            "metal_alarm": (1.0 if pb.metal_alarm else 0.0) if hp else NO_VALUE}


def _b_ball(c: _Snap, tid, b):
    p = c.power(b.power_kw, f"{tid}-power_kw")
    if c.m:
        q = c.q.get(b.line, NO_VALUE)
        ln = c.lines.get(b.line)
        n_run = sum(1 for x in ln.balls if x.state == "RUN") if ln is not None else 0
        # each running mill grinds q / n_run
        e = p * n_run / q if _valid(p) and _valid(q) and q > 0.0 else NO_VALUE
    else:
        e = b.e_kwh_t
    pct = 0.0
    if b.state == "RUN":
        pct = _PCT + b.overload_pct
        if c.m:
            pct = c.power(pct, f"{tid}-power_pct")
    return {"state": b.state, "power_kw": p, "e_kwh_t": e, "start_cmd": b.start_cmd, "power_pct": pct}


def _b_cyclones(c: _Snap, tid, cy):
    if c.m:
        p80 = _f(noisy_abs(_f(cy.p80_um), c.prm["sens_p80_sigma_um"], c.seed, c.step, f"{tid}-p80_um"))
        open_n = cy.open_count                       # a clogged unit still counts as open
    else:
        p80 = cy.p80_um
        open_n = max(0, cy.open_count - cy.clogged)  # truth: units that really work
    circ = cy.circ_load_pct
    if c.m:
        circ = c.flow(circ, f"{tid}-circ_load_pct")
    return {"state": cy.state, "p80_um": p80, "pressure_kpa": cy.pressure_kpa, "open_count": open_n,
            "circ_load_pct": circ}


def _b_flot(c: _Snap, tid, fl):
    n = fl.line
    if c.m:
        an = c.lines[n].analyzer
        grades = (an.feed_cu, an.tail_cu, an.conc_cu)
    else:
        grades = (fl.feed_cu, fl.tail_cu, fl.conc_cu)
    rec = c.rec[n] if c.m else fl.recovery
    cu = c.cu[n] if c.m else fl.cu_tph
    conc = c.conc[n] if c.m else fl.conc_tph
    return {"state": fl.state, "feed_cu": grades[0], "tail_cu": grades[1], "conc_cu": grades[2],
            "recovery": rec, "cu_tph": cu, "conc_tph": conc}


def _b_rougher(c: _Snap, tid, r):
    n = r.line
    q = c.weigher(r.feed_tph, f"sag-{n}-feed_tph")
    d = {"state": r.state, "feed_tph": q, "dose_sp_gt": r.dose_sp_gt,
         "stage_recovery": c.pct(r.stage_recovery, "sens_an_feed_sigma", f"{tid}-stage_recovery"),
         "mass_pull_pct": c.weigher(r.mass_pull_pct, f"{tid}-mass_pull_pct"),
         "rconc_cu": c.rel(r.rconc_cu, "sens_an_conc_sigma", f"{tid}-rconc_cu")}
    if c.m:
        res = r.residence_min
        if _valid(res) and _valid(q) and q > 0.0 and r.feed_tph > 0.0:
            res = res * r.feed_tph / q               # tau ~ 1/Q on the weighed feed
        d["residence_min"] = res
        d["dose_meas_gt"] = c.rel(r.dose_meas_gt, "sens_dose_sigma", f"{tid}-dose_meas_gt")
        d["tank_t"] = _f(noisy_abs(r.tank_t, c.prm["sens_tank_sigma_t"], c.seed, c.step, f"{tid}-tank_t"))
    else:
        d["residence_min"] = r.residence_min
        d["dose_meas_gt"] = r.dose_true_gt          # truth: the dose the meter should read
        d["tank_t"] = r.tank_t
    # deliveries are booked (exact); the flowmeter totalizer counts the meter's own reading
    d["tank_in_t_total"] = r.tank_in_t_total
    d["dose_t_total"] = r.dose_t_total
    return d


def _b_cleaner(c: _Snap, tid, cl):
    n = cl.line
    d = {"state": cl.state, "feed_tph": c.weigher(cl.feed_tph, f"{tid}-feed_tph"),
         "stage_recovery": c.pct(cl.stage_recovery, "sens_an_conc_sigma", f"{tid}-stage_recovery"),
         "tail_cu": c.rel(cl.tail_cu, "sens_an_tail_sigma", f"{tid}-tail_cu")}
    if c.m:
        d["conc_cu"] = c.lines[n].analyzer.conc_cu   # final concentrate = analyser conc stream
        d["conc_tph"] = c.conc[n]
        # stage recovery from the published noisy grades (feed = the rougher concentrate as published, tail, concentrate):
        # two-product formula; it is below 100 % whenever conc > feed > tail > 0, where a noisy copy of the true value was
        # clamped at 100 (24.10.2026)
        rc = c.lines[n].rougher
        f_pub = c.rel(rc.rconc_cu, "sens_an_conc_sigma", f"rougher-{n}-rconc_cu") if rc is not None else NO_VALUE
        rec, _y = two_product(f_pub, d["tail_cu"], d["conc_cu"])
        d["stage_recovery"] = rec if f_pub != NO_VALUE and _valid(d["tail_cu"]) and d["tail_cu"] > 0.0 and d["conc_cu"] > f_pub > d["tail_cu"]             else c.pct(cl.stage_recovery, "sens_an_conc_sigma", f"{tid}-stage_recovery")
    else:
        d["conc_cu"] = cl.conc_cu
        d["conc_tph"] = cl.conc_tph
    return d


def _b_thick(c: _Snap, tid, th):
    return {"state": th.state, "feed_tph": c.weigher(th.feed_tph, f"{tid}-feed_tph"),
            "underflow_tph": c.weigher(th.underflow_tph, f"{tid}-underflow_tph"),
            "inventory_t": th.inventory_t, "solids_pct": th.solids_pct,
            "overflow_m3h": c.flow(th.overflow_m3h, f"{tid}-overflow_m3h"), "hours_to_full": th.hours_to_full,
            "feed_t_total": th.feed_t_total, "underflow_t_total": th.underflow_t_total}


def _b_filter(c: _Snap, tid, fi):
    return {"state": fi.state, "presses_on": fi.presses_on, "cake_tph": c.weigher(fi.cake_tph, f"{tid}-cake_tph"),
            "moisture_pct": fi.moisture_pct, "limit_tph": fi.limit_tph}


def _b_conc_stock(c: _Snap, tid, cs):
    return {"state": cs.state, "stock_t": cs.stock_t, "in_tph": c.weigher(cs.in_tph, f"{tid}-in_tph"),
            "shipped_t_shift": cs.shipped_t_shift, "wagons_shift": cs.wagons_shift,
            "hours_to_full": cs.hours_to_full}


def _b_leach(c: _Snap, tid, lc):
    return {"state": lc.state, "quarter_cathode_kt": lc.quarter_cathode_kt, "level_tph": lc.level_tph, "cold_frac": lc.cold_frac}


def _b_sxew(c: _Snap, tid, sx):
    return {"state": sx.state, "cathode_tph": sx.cathode_tph, "cathode_level_tph": sx.cathode_level_tph,
            "cathode_t_total": sx.cathode_t_total, "year": sx.year, "quarter": sx.quarter}


def _b_water(c: _Snap, tid, w):
    return {"state": w.state, "intake_m3h": c.flow(w.intake_m3h, "water-intake_m3h"),
            "recycle_m3h": c.flow(w.recycle_m3h, "water-recycle_m3h"), "tails_loss_m3h": w.tails_loss_m3h,
            "evap_m3h": w.evap_m3h, "pond_m3": w.pond_m3, "residual_pct": w.residual_pct,
            "piezo_kpa": w.piezo_kpa, "intake_m3_total": w.intake_m3_total, "loss_m3_total": w.loss_m3_total,
            # no meter on a leak: measured -1, the modules see it only as the residual of the balance
            "leak_m3h": NO_VALUE if c.m else w.leak_m3h,
            "short_m3h": w.short_m3h, "cut_tph": w.cut_tph, "intake_cap_m3h": w.intake_cap_m3h,
            "air_temp_c": w.air_temp_c, "wind_ms": w.wind_ms, "beach_dry_pct": w.beach_dry_pct, "winter": w.winter}


def _b_power(c: _Snap, tid, pw):
    site = c.power(pw.site_mw, "power-site_mw")
    head = pw.grid_limit_mw - site if c.m and _valid(site) else pw.headroom_mw
    return {"state": pw.state, "grid_limit_mw": pw.grid_limit_mw, "site_mw": site,
            "grinding_mw": c.power(pw.grinding_mw, "power-grinding_mw"),
            "grinding_shaft_mw": c.power(pw.grinding_shaft_mw, "power-grinding_shaft_mw"),
            "other_mw": pw.other_mw, "shed_mw": pw.shed_mw, "headroom_mw": head, "shed_text": ",".join(pw.shed)}


def _b_crew(c: _Snap, tid, cr):
    return {"state": cr.state, "task": cr.task, "free_at": cr.free_at_min}


def _b_person(c: _Snap, tid, p):
    # work permit (nariad-dopusk): a mechanic works inside a mill, crusher or conveyor of his job
    permit = p.task if (p.state == "WORK" and p.crew in ("crew-mill", "crew-cpd") and p.task) else ""
    return {"state": p.state, "location": p.location, "task": p.task, "free_at": p.free_at_min, "permit": permit}


def _b_truck(c: _Snap, tid, tr):
    duty = f"руда, линия {tr.line}" if tr.duty == "ore" else "вскрыша"
    return {"state": tr.state, "location": tr.location, "load_t": tr.load_t, "cycle_min": tr.cycle_min,
            "duty": duty}


def _b_face(c: _Snap, tid, f):
    b = c.st.batches.get(f.block) if f.block else None
    est = b.est if b is not None else None
    if not c.m and b is not None:
        est = b.true                                     # truth: the ore the block really is
    axb = est.axb if est is not None and est.axb > 0.0 else NO_VALUE
    return {"state": f.state, "block": f.block, "est_cu": est.cu_pct if est is not None else NO_VALUE,
            "est_axb": axb, "hardness": hardness_ru(axb, c.table) if f.kind == "ore" else "вскрыша",
            "bench": float(f.bench), "tph": c.weigher(f.tph, f"{tid}-tph"), "blasted_t": f.blasted_t}


def _b_drill(c: _Snap, tid, d):
    return {"state": d.state, "location": d.face, "holes_shift": d.holes_shift}


def _b_dozer(c: _Snap, tid, z):
    return {"state": z.state, "location": z.place}


def _b_road(c: _Snap, tid, rd):
    mult = c.table["pit_road_detour"] if rd.state == "CLOSED" else 1.0
    return {"state": rd.state, "trucks_on": rd.trucks_on, "cycle_mult": mult}


def _dose_drift_confirmed(st: PlantState, line: int) -> bool:
    """A collector dose drift on the line that is known (found by the lab, the tails alarm, a module call or the crew)."""
    t = st.clock.t_min
    return any(cz.kind == "dose" and cz.line == line and cz.t_found_min != NO_VALUE and cz.t_found_min <= t
               and cz.t_start_min <= t and (cz.t_end_min == NO_VALUE or t < cz.t_end_min) for cz in st.causes)


def _b_analyzer(c: _Snap, tid, ln):
    an = ln.analyzer
    t = c.st.clock.t_min
    age = t - an.last_t_min if an.last_t_min != NO_VALUE else NO_VALUE
    stale = age == NO_VALUE or age > c.table["sens_an_stale_cycles"] * c.table["sens_an_cycle_min"]
    stopped = ln.flot is not None and ln.flot.state == "STOP"
    if c.m:
        grades = (an.feed_cu, an.tail_cu, an.conc_cu)
    else:
        fl = ln.flot
        grades = (fl.feed_cu, fl.tail_cu, fl.conc_cu) if fl is not None else (NO_VALUE,) * 3
    return {"state": "SUSPECT" if (stale or stopped) else "OK", "feed_cu": grades[0], "tail_cu": grades[1],
            "conc_cu": grades[2], "age_min": age}


def _b_weigher(c: _Snap, tid, ln):
    cv = ln.conveyor
    return {"state": "OK", "tph": c.weigher(cv.tph, f"conveyor-{ln.n}-tph"), "total_t": cv.weighed_t_total}


def _b_flowmeter(c: _Snap, tid, ln):
    r = ln.rougher
    if c.m:
        dose = c.rel(r.dose_meas_gt, "sens_dose_sigma", f"rougher-{ln.n}-dose_meas_gt")
    else:
        dose = r.dose_true_gt
    if _dose_drift_confirmed(c.st, ln.n):
        state = "DRIFT"
    elif ln.analyzer.alarm and abs(r.dose_meas_gt - r.dose_sp_gt) <= c.table["sens_dose_sigma"] * r.dose_sp_gt:
        state = "SUSPECT"            # tails above the alarm while the meter shows the setpoint
    else:
        state = "OK"
    return {"state": state, "dose_gt": dose, "sp_gt": r.dose_sp_gt}


def _b_phmeter(c: _Snap, tid, ln):
    """pH meter of the rougher: the reading is held at the setpoint by the control (a scaled electrode reads low and the lime
    dosing follows it), the grab sample with a hand-held meter is the check value. Truth snapshot: the real pH."""
    ph, prm = ln.ph, c.table
    t = c.st.clock.t_min
    real = prm["flot_ph_sp"] + ph.bias
    reading = ph.reading if ph.reading != NO_VALUE else prm["flot_ph_sp"]
    if c.m:
        reading = _f(noisy_abs(reading, prm["sens_ph_sigma"], c.seed, c.step, f"{tid}-ph"))
    else:
        reading = real
    age = t - ph.lab_t_min if ph.lab_t_min != NO_VALUE else NO_VALUE
    found = any(cz.kind == "phdrift" and cz.line == ln.n and cz.t_found_min != NO_VALUE and cz.t_found_min <= t
                and cz.t_start_min <= t and (cz.t_end_min == NO_VALUE or t < cz.t_end_min) for cz in c.st.causes)
    gap = abs(ph.lab_ph - ph.reading) if ph.lab_ph != NO_VALUE and ph.reading != NO_VALUE else 0.0
    state = "DRIFT" if found else ("SUSPECT" if c.m and gap >= prm["sens_ph_suspect_gap"] else "OK")
    return {"state": state, "ph": reading, "sp_ph": prm["flot_ph_sp"], "lab_ph": ph.lab_ph, "age_min": age}


def _b_piezometer(c: _Snap, tid, w):
    prm = c.table
    key = _site_piezo().get(tid)
    off = prm[key] if key else 0.0
    kpa = w.piezo_kpa + off
    if c.m:
        kpa = _f(noisy_abs(kpa, prm["pond_piezo_noise_kpa"], c.seed, c.step, f"{tid}-kpa"))
    sp = prm["pond_piezo_sp_kpa"]
    return {"state": "OK", "kpa": kpa, "level_m": kpa / KPA_PER_M if _valid(kpa) else NO_VALUE, "sp_kpa": sp,
            "alarm": 1.0 if _valid(kpa) and kpa >= sp else 0.0}


def _site_piezo() -> dict[str, str]:
    from .state import site
    return dict(getattr(site(), "PIEZO_OFFSET", {}))


_BUILDERS = {
    "site": _b_site, "pit": _b_pit, "exc": _b_exc, "fleet": _b_fleet, "crusher": _b_crusher,
    "conveyor": _b_conveyor, "stockpile": _b_stockpile, "line": _b_line, "sag": _b_sag,
    "pebble": _b_pebble, "ball": _b_ball, "cyclones": _b_cyclones, "flot": _b_flot,
    "rougher": _b_rougher, "cleaner": _b_cleaner, "thick": _b_thick, "filter": _b_filter,
    "conc-stock": _b_conc_stock, "leach": _b_leach, "sxew": _b_sxew, "water": _b_water, "power": _b_power, "crew": _b_crew,
    "person": _b_person, "truck": _b_truck, "face": _b_face, "road": _b_road, "analyzer": _b_analyzer,
    "weigher": _b_weigher, "flowmeter": _b_flowmeter, "piezometer": _b_piezometer, "phmeter": _b_phmeter,
    "drill": _b_drill, "dozer": _b_dozer,
}


def _with_wear(build, typ):
    """Builder of a thing type that carries a monitored signal of tier T (sim/wear.py): the signal is added to the raw dict."""
    def wrapped(c, tid, obj):
        d = build(c, tid, obj)
        d.update(wear_mod.signals(c.st, tid, typ))
        return d
    return wrapped


for _typ in wear_mod.SIGNAL_TYPES:
    _BUILDERS[_typ] = _with_wear(_BUILDERS[_typ], _typ)


def _snapshot(st: PlantState, prm: ParamSet | None, measured: bool) -> dict[str, dict[str, float | str]]:
    c = _Snap(st, prm, measured)
    out = {tid: c.thing(tid, info) for tid, info in _topo().items()}
    for bid, b in st.batches.items():
        out[bid] = c.batch(b)
    return out


def measured_features(st: PlantState, prm: ParamSet) -> dict[str, dict[str, float | str]]:
    """Measured features of every physical thing and live batch, keyed by thingId (no namespace).

    Keys per thing type = params.FEATURE_RULES[type] (minus SERVICE_FEATURES),
    for all things of state.topology() plus batches not yet deleted.
    Noise (stream "<thing>-<feature>", one stream per instrument when two
    features read the same one, step = st.clock.step): weigher
    sens_weigher_sigma on t/h, sens_power_sigma on power, sens_p80_sigma_um
    on P80, sens_dose_sigma on dose_meas_gt, sens_flow_sigma on water flows;
    flot feed/tail/conc grades are the latest analyser readings (NO_VALUE
    before the first); recovery, Cu t/h and concentrate t/h by the
    two-product formula; batch cu_meas is the lab value or NO_VALUE.
    site.scenario leaves out hidden-cause tokens.
    Numbers are float, states and texts are str; never None/NaN
    (NO_VALUE for missing). Hidden truth (eta, liner_x, clogged, dose_true,
    stockpile composition, true ore) is not included.
    """
    return _snapshot(st, prm, True)


def truth_features(st: PlantState) -> dict[str, dict[str, float | str]]:
    """Same keys as measured_features but true values, without noise (validation and tests only).

    Estimated features carry the quantity they estimate: rougher
    dose_meas_gt -> true dose, crusher lube_kpa -> pressure without the
    sensor fault, cyclones open_count -> units that really work, sag and
    batch axb_soft -> true A*b, batch cu_meas -> true Cu; site.scenario
    shows hidden-cause tokens too.
    """
    return _snapshot(st, None, False)
