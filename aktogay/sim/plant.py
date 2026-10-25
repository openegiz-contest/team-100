"""Plant: assembles the two lines along the feeds graph, advances the model,
applies scenarios and hidden causes, models crew response, keeps counters,
and runs the copies (fact / base / loud / no_twin) for scenario results.

Design: section 2 (one model time, warm-up 06:00 -> 08:00, auto pause at
20:00, free run with shift change, checkpoints), section 3 (things,
links, batches), section 4 (all rows; regulators), section 5 (crews, loud
issues noticed by alarm), section 7 (C1-C4, "Two at once", cancel).

This file uses only the APIs of sim.comminution, sim.flotation, sim.ore,
sim.utilities, sim.events, sim.sensors and sim.state.

Step order (Plant.step, one call = dt model minutes):
  1. due events at t: scenario events, preset/random hidden causes (random
     ones drawn per shift in modes free and calib), pebble stops (free,
     calib), line downtime and relines (calib), safety flag.
  2. crews: events.crew_step; finished jobs clear their fault/cause
     (crusher fault, lube bias, hidden cause t_end, found_by "crew").
     Planned calls due now are booked (events.crew_call). Loud issues with
     no call are noticed after events.notice_delay_min and called.
     people.people_step: the people of the shift follow their crews and duties.
  3. ore: plan_step, fleet_step, mining_targets, dig_step; pit.pit_step (trucks,
     faces, roads, stripping: names only, no effect on the ore path).
  4. per line: pocket_avail_tph -> comminution.crusher_step(room from
     ore.stock_room_tph) -> ore.convey_step.
  5. per line (a line is down while its SAG is RELINE or STOP or a calib
     downtime window is open: ball mills STOP, flotation STOP, no power
     drawn by the mills; crusher and belt keep filling the stockpile):
     SAG power cap = min(grid cap from the shed plan,
     line rule comminution.line_feed_cap_tph converted with
     sag_power_for_tph) -> comminution.sag_step(feed from
     ore.stock_available_tph, ore.feed_props + cause effects ASCu)
     -> ore.reclaim_step -> comminution.ball_step -> cyclone_step
     -> flotation.flotation_step -> filter_capacity_tph -> thickener_step
     -> filter_step.
  6. flotation.conc_stock_step with both lines' wet cake.
  7. utilities.power_balance (the shed plan is made in step 1 when the grid
     limit changes), utilities.water_step.
  8. sensors.analyzer_step, sensors.lab_step (a lab result can mark a
     hidden cause found when it shows the cause, found_by "lab"; the
     control-system tails alarm marks it found_by "acs"); a silent issue
     found this way is called at once.
  9. counters: line_shift, shift, total (Cu, ore, energy, water, value via
     utilities.value_usd, CO2); line state RUN / LIMITED / STOP.
 10. clock: t += dt, step += 1; shift boundary: free run and calib ->
     hooks.on_shift_end and reset shift counters (cum_*), concentrate
     shipped_t_shift and wagons_shift; scenario mode -> site_state PAUSED
     at scen_end_h (hooks.on_shift_end with the counters, no reset).
 11. ore.batches_step; hooks.on_batch (created, moved, deleted);
     hooks.on_step; hooks.on_checkpoint every cal_checkpoint_min.

Issues and calls. Issue keys follow the scenario syntax: "crusher:N"
(crusher fault, crew-cpd), "trip:N" (lube sensor fault, crew-kip),
"dose:N", "cyclone:N", "liner:N", "oxide:N" (hidden causes), "grid" (C2),
"hard:N" (C3), "reline:N" (C4). Only crew issues are noticed by alarm
without a call; C2-C4 calls change operation and need the button (or a
module call).

Units: time in model minutes, flows in t/h, unit power in kW, site power
in MW, energy in MWh, water in m3, money in USD.
"""
from __future__ import annotations

import copy
import math

from . import comminution as cm
from . import events as ev
from . import flotation as fz
from . import ore
from . import oxide
from . import people as pp
from . import pit as pt
from . import sensors as se
from . import utilities as ut
from . import wear
from .params import ParamSet, default
from .state import (CREW_FOR, MIN_PER_DAY, MIN_PER_H, NO_VALUE, CauseEffects, Counters, CrewJob,
                    HiddenCause, LabResult, LineState, OreProps, PlannedCall, PlantHooks, PlantState,
                    PowerLoads, ScenarioEvent, ScenarioSpec, TruthEntry, WaterFlows, base_ore,
                    initial_state, normal, site, u01)

MODES = ("free", "scenario", "calib")

INF = float("inf")
EPS = 1e-6              # min, tolerance of time comparisons
KW_PER_MW = 1000.0      # unit conversion
PCT = 100.0             # unit conversion
G_PER_T = 1e6           # unit conversion: g/t x t/h -> t/h divides by this
WATER_SCALE_FULL = 0.999   # numerical: an ore cut for water below 0.1 % ends (the filter never reaches 1)

CAUSE_KINDS = ("dose", "cyclone", "liner", "oxide", "energy", "reagent", "leak", "balls", "conc", "roping", "phdrift")
DECISION_CAUSES = ("energy", "balls", "conc", "roping")   # ended by a decision of the metallurgist / grinding operator
LAB_SHOWS = ("dose", "oxide")              # causes a lab sample can reveal
ACS_SHOWS = ("dose", "oxide", "cyclone")   # causes behind a tails alarm
SUMMARY_KEYS = ("cu_t", "ore_t", "energy_mwh", "water_m3", "usd")

# issue kind -> thing where the work is ("{}" = line number)
ISSUE_NODE = {"piezo": "water", "crusher": "crusher-{}", "trip": "crusher-{}", "dose": "flot-{}", "oxide": "flot-{}",
              "cyclone": "cyclones-{}", "liner": "sag-{}", "grid": "power", "hard": "pit",
              "reline": "sag-{}", "water": "water", "hpgr_fire": "pebble-{}", "road": "ramp-{}", "pit": "pit",
              "conveyor": "conveyor-{}", "pitstop": "pit",
              "energy": "sag-{}", "reagent": "rougher-{}", "leak": "water", "balls": "ball-{}a", "conc": "flot-{}",
              "startup": "ball-{}a", "icy": "pit", "fatigue": "fleet", "oil": "exc-1", "roping": "cyclones-{}", "leachcold": "leach-1",
              "ewtrip": "ew-1", "sxcrud": "sx-1",
              "phdrift": "ph-{}", "hpgr": "pebble-{}", "mantle": "crusher-{}", "sample": "analyzer-{}",
              "gmd": "sag-{}", "idler": "conveyor-{}", "froth": "flot-{}", "rake": "thick-{}", "cloth": "filter-{}",
              "slurry": "cyclones-{}", "brake": "fleet", "track": "exc-1"}
SITE_ISSUES = ("grid", "water", "piezo", "hpgr_fire", "leak", "pitstop", "icy", "fatigue", "oil", "leachcold", "brake", "track", "ewtrip", "sxcrud")   # issue keys without a line number
_CREW_KEY = {"trip": "lube_trip", "cyclones": "cyclone"}   # issue / node kind -> state.CREW_FOR key
# Russian words of the truth log (validation-sim.truth_log is shown in the interface)
CAUSE_RU = {"dose": "дрейф расходомера собирателя", "cyclone": "засор циклона", "liner": "износ футеровки SAG",
            "oxide": "окисленная руда", "energy": "перерасход энергии SAG (перегруз или крупное питание)",
            "reagent": "передозировка собирателя (расходомер занижает)",
            "leak": "утечка на водоводе оборотной воды",
            "balls": "перерасход мелющих шаров", "conc": "разубоживание концентрата (Cu ниже нормы)",
            "roping": "канатирование гидроциклонов и перегрузка шаровой мельницы",
            "phdrift": "дрейф pH-метра (электрод в накипи извести)"}
FOUND_BY_RU = {"lab": "лаборатория", "acs": "тревога АСУ по хвостам", "module": "модуль двойника",
               "crew": "бригада на месте", "cancel": "не найдена, сценарий отменён", "": "не найдена",
               "report": "суточный отчёт по энергии", "audit": "сверка бака реагентов",
               "patrol": "обход водовода"}


def parse_issue(issue: str) -> tuple[str, int]:
    """"trip:2" -> ("trip", 2); "grid" -> ("grid", 0)."""
    kind, _, rest = (issue or "").partition(":")
    try:
        n = int(rest) if rest else 0
    except ValueError:
        n = 0
    return kind.strip(), n


def node_kind_line(node: str) -> tuple[str, int]:
    """"ball-2b" -> ("ball", 2); "power" -> ("power", 0); "batch-0007" -> ("batch", 0)."""
    head, sep, tail = (node or "").rpartition("-")
    if sep and head and head not in ("batch", "exc") and tail[:1].isdigit():
        return head, int(tail[0])
    if sep and head in ("batch", "exc"):
        return head, 0
    return node or "", 0


def _floor_idx(t: float, offset: float, period: float) -> int:
    return int(math.floor((t - offset + EPS) / period))


def _hhmm(t: float) -> str:
    day = int(math.floor(t / MIN_PER_DAY))
    m = int(round(t - day * MIN_PER_DAY))
    return f"d{day} {m // 60 % 24:02d}:{m % 60:02d}"


class Plant:
    """One copy of the plant model.

    Plant(prm=None, seed=None, mode="free", t0_min=None, year=2026, origin_doy=0, hooks=None)
    builds the state with state.initial_state (06:00 of day 0 unless t0_min
    is given). prm defaults to params.default(); seed to cal_seed.
    """

    def __init__(self, prm: ParamSet | None = None, seed: int | None = None, mode: str = "free",
                 t0_min: float | None = None, year: int = 2026, origin_doy: int = 0,
                 hooks: PlantHooks | None = None):
        if mode not in MODES:
            raise ValueError("mode must be one of " + ", ".join(MODES))
        self.prm = default() if prm is None else prm
        self.state = initial_state(self.prm, seed, mode, t0_min, year, origin_doy)
        self.hooks = hooks if hooks is not None else PlantHooks()
        p, st = self.prm, self.state
        t0 = st.clock.t_min
        lines = [ln.n for ln in st.lines]
        # random windows start after the warm-up in free run, at once in calib
        self._rand_t0 = t0 if mode == "calib" else self._shift_start(self._shift_idx(t0 - EPS) + 1)
        self._hc_until = self._rand_t0          # hidden causes drawn up to this minute
        self._hc_last_end = -INF                # end of the last drawn cause (one at a time)
        self._hc2_until = self._rand_t0         # silent causes (free run only) drawn up to this minute
        self._hc2_last_end = -INF
        self.late_calls = False                 # set by akt-sim on the live copy: some called people come late
        self._late_ok = False
        self._peb_until = self._rand_t0         # pebble stops drawn up to this minute
        self._peb: dict[int, list[tuple[float, float]]] = {n: [] for n in lines}
        self._crw_until = self._rand_t0         # own stops of the primary crusher (calib run) drawn up to this minute
        self._crw: dict[int, list[tuple[float, float]]] = {n: [] for n in lines}          # short stops
        self._crp: dict[int, list[float]] = {n: [] for n in lines}                        # nominal starts of planned windows
        self._crp_left: dict[int, float] = {n: 0.0 for n in lines}                        # planned crusher work still to do, min
        self._crp_since: dict[int, float] = {n: NO_VALUE for n in lines}                  # when the oldest planned work was due
        self._crp_t: dict[int, float] = {n: NO_VALUE for n in lines}                      # previous call, min
        self._mantle_year: dict[int, int] = {n: -1 for n in lines}                        # year of the last liner change
        self._events: list[ScenarioEvent] = []  # announced events not applied yet
        self._grid: list[tuple[float, float, float]] = []   # (start, end, limit MW)
        self._limit_mw = p["pow_grid_limit_mw"]
        self._shed_balls: list[str] = []
        self._grid_cap_kw = {n: INF for n in lines}     # SAG shaft cap from the grid
        self._bonus_kw = {n: 0.0 for n in lines}        # C2 call: SAG shaft above the line rule
        self._c2_latch: tuple[str, int] | None = None   # C2 call waiting for the shed (applied when it happens)
        self._c4 = {n: False for n in lines}            # C4 call: excavators idle at full stock
        self._leak_frac = 0.0                           # scenario water: share of the pond return leaking
        self._extra_teams: list[str] = []               # crews with a temporary extra team (call via deputy)
        self._extra_until: dict[str, float] = {}
        self.base_winter = False                        # season by the date (set by akt-sim)
        self.winter_on = False                          # winter return loss (set by akt-sim from the date, or scenario winter)
        self._dust_until = NO_VALUE                     # scenario dust: windy dry spell until this minute
        self._leach_until = NO_VALUE                    # scenario leachcold: cold spell on the leach pad until this minute
        self.ox_date = None                             # (year, 0-based day of year) of the quarter of the oxide line; None = model clock (set by akt-sim)
        self._startups: dict[int, tuple[float, float]] = {}   # line -> (start command from, to), scenario startup
        self._ball_repair: set[int] = set()             # lines whose ball mill "a" stands for the repair with people inside
        self._water_scale = 1.0                         # ore share the water allows (1 = no cut)
        self._fire_until = NO_VALUE                     # scenario hpgr_fire: S0 flag until this minute
        self._piezo_until = NO_VALUE                    # scenario safety: the dam alarm ends at this minute (the technologist called)
        self._pitstop_until = NO_VALUE                  # scenario pitstop: ore excavators stand until this minute
        self._icy_until = NO_VALUE                      # scenario icy: ice and snowstorm on the haul roads until this minute
        self._fatigue_until = NO_VALUE                  # scenario fatigue: alert of a tired driver until this minute
        self._wq: dict[int, tuple] = {}                 # tier T: line -> (feed factor, recovery loss pp, filter capacity factor)
        self._wmult = 1.0                               # tier T: truck cycle multiplier of a throttled brake
        self._hpgr: dict[int, float] = {}               # scenario hpgr:N: line -> minute the uneven feed started
        self._hpgr_tripped: set[int] = set()            # lines whose metal detector already tripped
        self._rope_flot: dict[int, float] = {}          # line -> minute until which a rougher line stands after heavy roping
        self._relines: list[tuple[int, float, float, bool]] = []   # (line, start, end, scenario)
        self._warmup_end: float | None = None           # target minute of a running warm-up
        self._down_idx = {n: 0 for n in lines}
        self._down = {n: False for n in lines}
        self._calls: list[PlannedCall] = []
        self._jobs: dict[str, CrewJob] = {}             # open crew job per issue
        self._work_set: dict[str, float] = {}           # median repair time (h) set by the constructor, per issue key
        self._loud: dict[str, float] = {}               # issue -> minute it is noticed by alarm
        self.follow_module = False                      # the dispatcher follows the module's calls: an alarm alone books no crew
        self._held_loud: dict[str, float] = {}          # loud issues held back while follow_module is on (minute noticed)
        self.call_log: list[dict] = []                  # every crew booking: {t, issue, node, src}; src: module, alarm, plan, button, fallback
        self._crew_t = t0
        thick0 = sum(ln.thick.inventory_t for ln in st.lines)
        self._acc = {"cu_feed": 0.0, "cu_conc": 0.0, "cu_tails": 0.0, "clean_t": 0.0, "filt_dry_t": 0.0,
                     "filt_wet_t": 0.0, "ship_t": 0.0, "thick0": thick0, "cstock0": st.conc_stock.stock_t}
        # Snapshot face: at t0 each line's excavator works one block of base ore
        # (estimate = truth), the same ore as the "initial" stockpile and
        # pipeline batches, so the 08:00 reference holds the design values;
        # random blocks of the plan follow it.
        for ln in st.lines:
            ore.inject_block(st, ln.n, base_ore(p), base_ore(p), 0.0, p, tag="initial")
        self._power_balance()

    # -- attributes set by __init__ --
    prm: ParamSet
    state: PlantState
    hooks: PlantHooks

    @property
    def t_min(self) -> float:
        """Current model minute."""
        return self.state.clock.t_min

    # ------------------------------------------------------------------ time
    def step(self, dt_min: float | None = None) -> None:
        """Advance one step of dt_min model minutes (default cal_step_live_min). See module doc.

        Does nothing while site_state is PAUSED (auto pause of a scenario).
        """
        st, p = self.state, self.prm
        if st.site_state == "PAUSED":
            return
        dt = p["cal_step_live_min"] if dt_min is None else float(dt_min)
        if not dt > 0.0:
            return
        clk = st.clock
        t = clk.t_min
        k = clk.step
        clk.dt_min = dt
        hooks = self.hooks
        watch = type(hooks).on_batch is not PlantHooks.on_batch
        marks = {bid: (b.state, b.location) for bid, b in st.batches.items()} if watch else None

        # 1. events
        self._apply_due_events(t)
        if st.mode != "scenario":
            self._random_events(t, dt)
        self._end_due_causes(t)
        self._windows(t)
        if self._c2_latch is not None:
            self._c2_try()
        # 2. crews and people
        self._crews_step(t)
        pp.people_step(st, t)
        # 3. ore (haul roads: weather, restriction; excavator oil first, a failure takes the machine down)
        self._pit_weather(t)
        self._oil_step(t)
        if st.wear or self._wq or self._wmult != 1.0:
            wear.step(self, t)               # tier T: slow troubles with a monitored signal
        ore.plan_step(st, p)
        ore.fleet_step(st, p)
        targets = ore.mining_targets(st, p)
        full_t = p["stock_full_frac"] * p["stock_live_t"]
        for n, on in self._c4.items():
            if on and st.line(n).stockpile.level_t >= full_t:
                targets[n] = 0.0
                st.pit.target_tph[n] = 0.0
        ore.dig_step(st, targets, dt, p)
        pt.pit_step(st, p, t)
        # 4. crusher and belt
        ws = p["sens_weigher_sigma"]
        for ln in st.lines:
            n = ln.n
            avail = ore.pocket_avail_tph(st, n, dt)
            room = 0.0 if ln.conveyor.fault else ore.stock_room_tph(st, n, dt, p)   # tripped belt: nowhere to discharge
            c_tph = cm.crusher_step(ln.crusher, avail, room, p, normal(st.seed, k, "lube-%d" % n))
            if ln.crusher.fault == "lube_trip":
                self._register_loud("trip:%d" % n, t)
            ore.convey_step(st, n, c_tph, dt, p)
            cv = ln.conveyor
            cv.weighed_t_total += max(0.0, cv.tph) * (1.0 + ws * normal(st.seed, k, "conveyor-%d-tot" % n)) \
                * dt / MIN_PER_H
        # 5. grinding, flotation, thickener, filter
        cs_full = st.conc_stock.state == "FULL"
        flows = [self._line_step(ln, t, dt, k, cs_full) for ln in st.lines]
        # 6. concentrate stock
        wet = sum(f["wet_tph"] for f in flows)
        shipped = fz.conc_stock_step(st.conc_stock, wet, t, dt, p)
        # 7. power and water
        self._power_balance()
        self._water_step(flows, dt, k)
        # 8. sensors
        self._sensors_step(t, k, flows)
        # 9. counters
        self._count(flows, dt, wet, shipped)
        # 10. clock, shifts
        t_new = t + dt
        clk.t_min = t_new
        clk.step = k + 1
        if st.site_state == "WARMUP":
            # The warm-up ends inside the step that reaches its target minute,
            # before the hooks of that step: the 08:00 checkpoint is the first
            # point of the run (state RUN, shift counters from zero), not the
            # last point of the warm-up. No shift end is reported here.
            if self._warmup_end is not None and t_new >= self._warmup_end - EPS:
                self._warmup_end = None
                st.site_state = "RUN"
                self._reset_shift()
        elif st.mode == "scenario":
            end = p["scen_end_h"] * MIN_PER_H
            if _floor_idx(t_new, end, MIN_PER_DAY) > _floor_idx(t, end, MIN_PER_DAY):
                st.site_state = "PAUSED"
                hooks.on_shift_end(st, self.shift_summary())
        else:
            start, length = p["cal_shift_start_h"] * MIN_PER_H, p["cal_shift_h"] * MIN_PER_H
            if _floor_idx(t_new, start, length) > _floor_idx(t, start, length):
                hooks.on_shift_end(st, self.shift_summary())
                self._reset_shift()
        # 11. batches, hooks
        removed = ore.batches_step(st, p)
        if watch:
            for bid, b in st.batches.items():
                if marks.get(bid) != (b.state, b.location):
                    hooks.on_batch(st, b)
            for b in removed or ():
                hooks.on_batch(st, b)
        hooks.on_step(st)
        cp = p["cal_checkpoint_min"]
        if _floor_idx(t_new, 0.0, cp) > _floor_idx(t, 0.0, cp):
            hooks.on_checkpoint(st)

    def run_until(self, t_min: float, dt_min: float | None = None) -> None:
        """Step until the model minute reaches t_min (last step shortened, never overshoots)."""
        dt = self.prm["cal_step_live_min"] if dt_min is None else float(dt_min)
        if not dt > 0.0:
            raise ValueError("dt_min must be positive")
        st = self.state
        while st.clock.t_min < t_min - EPS and st.site_state != "PAUSED":
            self.step(min(dt, t_min - st.clock.t_min))

    def warmup(self) -> None:
        """Run from cal_warmup_from_h to cal_warmup_to_h with site_state WARMUP, then RUN.

        The target is cal_warmup_to_h of the current model day; the shift
        counters start from zero at its end (08:00 = start of the shift).
        """
        st, p = self.state, self.prm
        day0 = math.floor((st.clock.t_min + EPS) / MIN_PER_DAY) * MIN_PER_DAY
        t_end = day0 + p["cal_warmup_to_h"] * MIN_PER_H
        if st.clock.t_min < t_end - EPS:
            st.site_state = "WARMUP"
            self._warmup_end = t_end
            self.run_until(t_end)             # step() flips to RUN at t_end, before its hooks
        if st.site_state != "RUN":            # already at or past t_end: no step ran
            self._warmup_end = None
            st.site_state = "RUN"
            self._reset_shift()

    # -------------------------------------------------------------- scenario
    def apply_scenario(self, spec: ScenarioSpec) -> None:
        """Activate a scenario on this copy (mode becomes "scenario").

        crusher:N -> crusher-N fault "scenario" (loud issue, crew-cpd);
        grid      -> power grid limit pow_c2_limit_mw for duration, shed plan,
                     line rule on the line with a shed ball mill; restored after;
        hard:N    -> ore.inject_block with ore_axb_hard / ore_bwi_hard, lead scen_hard_lead_h;
        reline:N  -> SAG-N RELINE for liner_reline_h, new liner (liner_x 0) after;
                     safety flag "people_in_sag" (value = line) while relining;
        trip:N    -> crusher-N lube_bias_kpa below trip (sensor fault: the reading
                     drops to zero), crew-kip fixes;
        dose/cyclone/liner/oxide -> events.preset_causes;
        safety    -> flag "piezo" from its start time (S0 issue for modules);
                     the piezometer reads scen_piezo_over_kpa above its setpoint;
        water     -> leak of the return-water pipeline (water_leak_frac of the pond return) until
                     crew-water repairs it (loud: noticed by the water alarm); above the fresh-water
                     cap the ore of both lines is cut (water_reg_min);
        hpgr_fire -> flag "fire" (= line) for scen_fire_safety_h (S0), pebble circuit of the line
                     STOP for scen_fire_h (E_SAG up, t/h down), the mill mechanic evacuated (OFF);
                     the other line runs on (event of 09.08.2026);
        road:N    -> ramp of line N CLOSED for pit_road_close_h: ore trucks of the line on a detour.
        Random hidden causes and random pebble stops are off in mode "scenario".
        Events due now are applied at once; later ones in step 1.
        """
        st, p = self.state, self.prm
        spec = copy.deepcopy(spec)
        st.mode = "scenario"
        st.scenario = spec
        self._set_crew_count("crew-kip", int(spec.kip))
        # random causes and pebble stops belong to free run and calib only
        st.causes = [c for c in st.causes if c.preset]
        for ln in st.lines:
            self._peb[ln.n] = []
            if ln.pebble.state == "STOP":
                ln.pebble.state = "RUN"
                ln.pebble.stop_until_min = NO_VALUE
        st.causes.extend(ev.preset_causes(spec, p))
        self._events = sorted((e for e in spec.events if e.kind not in CAUSE_KINDS),
                              key=lambda e: e.t_start_min)
        self._apply_due_events(st.clock.t_min)

    def cancel_scenario(self) -> None:
        """Remove the scenario effects from this copy (faults, causes, caps, flags).

        The scenario result returns to base through CopySet.cancel(), which
        replaces the fact copy by a clone of the base copy.
        """
        st, p = self.state, self.prm
        t = st.clock.t_min
        self._events = []
        self._grid = []
        if self._limit_mw != p["pow_grid_limit_mw"]:
            self._set_grid_limit(p["pow_grid_limit_mw"])
        for ln in st.lines:
            cr = ln.crusher
            if cr.fault in ("scenario", "lube_trip"):
                cr.fault = ""
            cr.fault_until_min = NO_VALUE
            cr.lube_bias_kpa = 0.0
            ln.conveyor.fault, ln.conveyor.fault_until_min = "", NO_VALUE
            sag = ln.sag
            if sag.state == "RELINE" and any(w[0] == ln.n and w[3] for w in self._relines):
                sag.state = "RUN"
                sag.reline_until_min = NO_VALUE
            self._c4[ln.n] = False
            self._bonus_kw[ln.n] = 0.0
        self._relines = [w for w in self._relines if not w[3]]
        for c in [c for c in st.causes if c.preset]:
            self._end_cause(c, t, "cancel")
        for n, ids in st.pit.plan.items():
            st.pit.blend[n] = False
            for bid in list(ids):
                b = st.batches.get(bid)
                if b is not None and b.tag == "hard" and b.state == "PLANNED":
                    ids.remove(bid)
                    del st.batches[bid]
                    self.hooks.on_batch(st, b)
        ore.plan_step(st, p)
        st.flags.pop("piezo", None)
        st.flags.pop("people_in_sag", None)
        st.flags.pop("fire", None)
        for ln in st.lines:                     # pebble stops of a scenario run are the scenario's (hpgr_fire)
            self._peb[ln.n] = []
            if ln.pebble.state == "STOP":
                ln.pebble.state = "RUN"
                ln.pebble.stop_until_min = NO_VALUE
        self._fire_until = NO_VALUE
        self._piezo_until = NO_VALUE
        if self._pitstop_until != NO_VALUE:
            for ex in st.excavators:
                if ex.state == "DOWN":
                    ex.state, ex.down_until_min = "IDLE", NO_VALUE
            self._pitstop_until = NO_VALUE
        self._leak_frac = 0.0
        self._icy_until = NO_VALUE
        self._fatigue_until = NO_VALUE
        self._hpgr.clear()
        self._hpgr_tripped.clear()
        self._rope_flot.clear()
        wear.clear(self)
        oxide.fault_clear(st)
        st.pit.restrict_until_min = NO_VALUE
        for ex in st.excavators:
            ex.oil_pct, ex.oil_event_min, ex.oil_fix_min = self.prm["pit_oil_start_pct"], NO_VALUE, NO_VALUE
        for ln in st.lines:
            ln.crusher.service_until_min = NO_VALUE
            if ln.crusher.fault == "mantle":
                ln.crusher.fault = ""
            ln.analyzer.blocked = False
            ln.pebble.hpgr_eff, ln.pebble.hpgr_skew_pct = 1.0, 0.0
            ln.pebble.hpgr_kw_diff_pct, ln.pebble.metal_alarm = 0.0, False
        self.winter_on = self.base_winter
        self._dust_until = NO_VALUE
        self._leach_until = NO_VALUE
        self._startups.clear()
        self._ball_repair.clear()
        for ln in st.lines:
            for b in ln.balls:
                b.start_cmd = 0.0
        self._water_scale = 1.0
        self._c2_latch = None
        for rd in st.roads.values():
            rd.state, rd.closed_until_min = "OPEN", NO_VALUE
        for person in st.people.values():
            person.off_until_min = NO_VALUE
            person.duty_node, person.duty_until_min = "", NO_VALUE
        self._loud.clear()
        self._held_loud.clear()
        self._calls.clear()
        self._jobs.clear()
        self._work_set.clear()
        st.scenario = None

    def call(self, node: str, crew: str | None = None, issue: str = "",
             work_h: float | None = None, via: str = "", src: str = "button") -> CrewJob | None:
        """Button "Call" or module auto_call now: book the crew for the issue at `node`.

        crew defaults from state.CREW_FOR by issue kind, then by node kind;
        work_h defaults to events.repair_hours(seed, issue, events.work_median_h(kind)).
        C2 call (node "power" or "sag-2" during grid limit): SAG-2 cap raised
        by pow_call_use_mw (grid) when headroom allows. C3 call (node "pit"
        or a hard batch): pit.blend[line] = True. C4 call (node "pit"): excavators
        of the line go IDLE when its stockpile is FULL.
        Returns the job, or None when nothing to fix (C2-C4 change operation
        without a crew job). A call for a hidden cause marks it found ("module").
        """
        st = self.state
        t = st.clock.t_min
        kind, n = parse_issue(issue) if issue else self._issue_at(node)
        person = site().DECISION_PERSON.get(kind)
        if person:
            # the person of the decision goes to the node (people twins; no effect on the physics)
            where = node or ISSUE_NODE.get(kind, "site").format(n or int(self.prm["scen_fire_line"]))
            pp.assign_duty(st, person, where, t, self.prm)
        if kind == "grid":
            self._c2_call(node, n)
            return None
        if kind in ("hard", "reline", "pit"):
            self._pit_call(kind, n, node)
            return None
        if kind == "icy":
            self._restrict_traffic(t)         # the mine dispatcher limits the traffic on the haul roads
            return None
        if kind == "fatigue":
            self._fatigue_until = t + self.prm["crew_person_decision_h"] * MIN_PER_H   # the driver is replaced / machines separated
            return None
        if kind == "oil":
            self._oil_call(t)
            return None
        if kind in wear.KINDS:
            wear.call(self, kind, n, t)       # tier T: the person comes, the unit is fixed after the work
            return None
        if kind in oxide.FAULT_KINDS:
            oxide.fault_call(self, kind, t)   # oxide chain: the electrician restarts the rectifier / the metallurgist has the crud removed
            return None
        if kind == "piezo":
            self._piezo_call(t)               # S0 of the dam: the water technologist goes to the dam and checks it
            return None
        if kind in ("hpgr_fire", "road", "pitstop", "leachcold"):
            return None                       # decisions of a person: de-energise, evacuate, reroute, plan the stock
        if kind in DECISION_CAUSES:
            self._energy_call(n, t, kind)
            return None
        if kind == "startup":
            # the shift head cancels the start command (decision, no crew): people inside are safe again
            self._startups.pop(n, None)
            for b in st.line(n).balls:
                b.start_cmd = 0.0
            return None
        if not kind:
            return None
        issue = issue or (kind if kind in SITE_ISSUES else "%s:%d" % (kind, n))
        wh = NO_VALUE if work_h is None else float(work_h)
        self._late_ok = self.late_calls
        if via in ("deputy", "head"):
            # the main person is busy on a permit: the deputy (or the shift head) forms one more team for this job
            cn = crew if crew in st.crews else self._crew_for(kind, node)
            cr = st.crews.get(cn) if cn else None
            if cr is not None and all(s != NO_VALUE and s > t + EPS for s in cr.slot_free_min):
                self._set_crew_count(cn, cr.count + 1)
                self._extra_teams.append(cn)
        try:
            job = self._book(PlannedCall(t, node or "", crew or "", issue, wh), src)
            if job is not None and self._extra_teams:
                self._extra_until[issue] = job.t_done_min
            return job
        finally:
            self._late_ok = False

    def _piezo_call(self, t: float) -> None:
        """Dam piezometer above its setpoint (scenario safety): the technologist comes (arrival) and checks the dam
        (crew_person_decision_h); the alarm ends then. A second call while he is on the way changes nothing."""
        if self.state.flags.get("piezo") and self._piezo_until == NO_VALUE:
            p = self.prm
            way = ev.arrival_min(self.state.seed, "piezo", p)
            self._piezo_until = t + way + p["crew_person_decision_h"] * MIN_PER_H
            pp.assign_duty(self.state, site().DECISION_PERSON["piezo"], ISSUE_NODE["piezo"], t, p,
                           hours=(self._piezo_until - t) / MIN_PER_H)       # on the way and at the dam until the alarm ends

    def _energy_call(self, n: int, t: float, kind: str = "energy") -> None:
        """SAG energy overspend: the metallurgist comes (arrival) and corrects the load / feed size
        (crew_person_decision_h); the cause ends then (found by the module now)."""
        p = self.prm
        end = t + ev.arrival_min(self.state.seed, "%s:%d" % (kind, n), p) + p["crew_person_decision_h"] * MIN_PER_H
        for c in self.state.causes:
            if c.kind == kind and c.line == n and self._active(c, t):
                if c.t_found_min == NO_VALUE:
                    c.t_found_min, c.found_by = t, "module"
                c.t_end_min = end if c.t_end_min == NO_VALUE else min(c.t_end_min, end)

    def remind(self, issue: str = "", node: str = "", action: str = "remind") -> CrewJob | None:
        """'Not arrived': a reminder (arrival in crew_remind_min) or the next person of the trade
        (action "next": a fresh travel time). Only a job still on its way and later than that moves."""
        st, p = self.state, self.prm
        t = st.clock.t_min
        kind, n = parse_issue(issue) if issue else self._issue_at(node)
        key = issue or (kind if kind in SITE_ISSUES else "%s:%d" % (kind, n))
        job = self._jobs.get(key)
        if job is None or job.t_arrive_min <= t + EPS:
            return None
        new = t + (p["crew_remind_min"] if action != "next" else ev.arrival_min(st.seed, key + ":next", p))
        shift = new - job.t_arrive_min
        if shift >= 0.0:
            return job
        old_done = job.t_done_min
        job.t_arrive_min += shift
        job.t_done_min += shift
        for crew in st.crews.values():
            if job in crew.jobs:
                crew.slot_free_min = [s + shift if s == old_done else s for s in crew.slot_free_min]
                ev._refresh(crew, t)
        if kind in ("crusher", "trip") and 1 <= n <= len(st.lines):
            st.line(n).crusher.fault_until_min = job.t_done_min
        return job

    def schedule(self, calls: list[PlannedCall]) -> None:
        """Add future calls (copy policies); booked in step 2 when due (order kept for equal times)."""
        self._calls.extend(copy.copy(c) for c in calls)
        self._calls.sort(key=lambda c: c.t_min)

    def set_relines(self, windows: list[tuple[int, float, float]]) -> None:
        """Calib: SAG reline windows (line, start_min, end_min); new liner after each."""
        for line, a, b in windows:
            self._relines.append((int(line), float(a), float(b), False))
        self._relines.sort(key=lambda w: w[1])

    def set_downtime(self, line: int, windows: list[tuple[float, float]]) -> None:
        """Calib: line stop windows (start_min, end_min); SAG STOP, feed 0, mining regulator reacts."""
        ln = self.state.line(int(line))
        ln.down_windows = sorted((float(a), float(b)) for a, b in windows if b > a)
        self._down_idx[ln.n] = 0

    # --------------------------------------------------------------- outputs
    def clone(self) -> "Plant":
        """Deep copy (state and schedules); hooks are not copied (a plain PlantHooks is used)."""
        hooks = self.hooks
        self.hooks = None
        try:
            c = copy.deepcopy(self, {id(self.prm): self.prm})
        finally:
            self.hooks = hooks
        c.hooks = PlantHooks()
        return c

    def snapshot(self, measured: bool = True) -> dict[str, dict[str, float | str]]:
        """Features of all things: sensors.measured_features or sensors.truth_features,
        plus site totals (tph, cu_tph, power_mw, water_m3h, scenario, seed)."""
        st = self.state
        feats = se.measured_features(st, self.prm) if measured else se.truth_features(st)
        site = feats.setdefault("site", {})
        # sensors fill the site totals (measured: weighed and two-product);
        # these defaults only cover a missing key
        site.setdefault("tph", float(sum(ln.tph for ln in st.lines)))
        site.setdefault("cu_tph", float(sum(ln.cu_tph for ln in st.lines)))
        site.setdefault("power_mw", float(st.power.site_mw))
        site.setdefault("water_m3h", float(st.water.intake_m3h))
        site.setdefault("scenario", self.scenario_text(hidden=not measured))
        site.setdefault("seed", float(st.seed))
        return feats

    def scenario_text(self, hidden: bool = False) -> str:
        """Active scenario as text, e.g. "fork+grid"; "" without one.

        hidden=False leaves out silent-cause tokens (dose, cyclone, liner,
        oxide), which must not show before a module finds them.
        """
        sc = self.state.scenario
        if sc is None:
            return ""
        toks = [x for x in (sc.text or "").split("+") if x]
        if not hidden:
            toks = [x for x in toks if parse_issue(x)[0] not in CAUSE_KINDS]
        parts = ([sc.preset] if sc.preset else []) + toks + (["safety"] if sc.safety else [])
        return "+".join(parts)

    def balances(self) -> dict[str, float | str]:
        """Balance residuals for the calib view and checks (cumulative since the copy was built).

        cu_residual_pct: feed Cu = concentrate Cu + tails Cu + flotation hold-up change
          (the flotation model holds no mass, so the hold-up term is 0);
        water_residual_pct: from WaterState.residual_pct;
        conc_residual_pct: cleaner = thickener change + filter = stock change + shipped
          (the stage with the larger residual, % of its inflow);
        power_headroom_mw; power_parts_text e.g.
        "mills 139.6 + crushers and conveyors 8.8 + other 111.6 = 260.0 of 300 MW".
        """
        st, a = self.state, self._acc
        cu_res = PCT * (a["cu_feed"] - a["cu_conc"] - a["cu_tails"]) / a["cu_feed"] if a["cu_feed"] > 0 else 0.0
        thick = sum(ln.thick.inventory_t for ln in st.lines)
        r1 = a["clean_t"] - (thick - a["thick0"]) - a["filt_dry_t"]
        r2 = a["filt_wet_t"] - (st.conc_stock.stock_t - a["cstock0"]) - a["ship_t"]
        p1 = PCT * r1 / a["clean_t"] if a["clean_t"] > 0 else 0.0
        p2 = PCT * r2 / a["filt_wet_t"] if a["filt_wet_t"] > 0 else 0.0
        pw = st.power
        text = (f"mills {pw.grinding_mw:.1f} + crushers and conveyors {pw.cc_mw:.1f} + other "
                f"{pw.other_mw:.1f} = {pw.site_mw:.1f} of {pw.grid_limit_mw:.0f} MW")
        return {"cu_residual_pct": float(cu_res), "water_residual_pct": float(st.water.residual_pct),
                "conc_residual_pct": float(p1 if abs(p1) >= abs(p2) else p2),
                "power_headroom_mw": float(pw.headroom_mw), "power_parts_text": text}

    def shift_summary(self) -> dict[str, float]:
        """Shift counters: ore_t, cu_t, energy_mwh, water_m3, usd, co2_t, minutes, per line too.

        Site keys: t_min, ore_t, cu_feed_t, cu_t (Cu in concentrate), conc_t,
        recovery_pct (-1 without feed), energy_mwh, water_m3 (intake),
        recycle_m3, usd, co2_t, minutes; per line "l<N>_" + ore_t, cu_t,
        energy_mwh, water_m3, usd.
        """
        st = self.state
        out = {"t_min": float(st.clock.t_min)}
        out.update(self._summary(st.shift))
        for n, c in st.line_shift.items():
            s = self._summary(c)
            for key in SUMMARY_KEYS:
                out["l%d_%s" % (n, key)] = s[key]
        return out

    # ===================================================== internals: time
    def _shift_idx(self, t: float) -> int:
        p = self.prm
        return int(math.floor((t - p["cal_shift_start_h"] * MIN_PER_H) / (p["cal_shift_h"] * MIN_PER_H)))

    def _shift_start(self, s: int) -> float:
        p = self.prm
        return p["cal_shift_start_h"] * MIN_PER_H + s * p["cal_shift_h"] * MIN_PER_H

    def _reset_shift(self) -> None:
        st = self.state
        st.shift = Counters()
        st.line_shift = {ln.n: Counters() for ln in st.lines}
        for ln in st.lines:
            ln.cum_cu_t = ln.cum_mwh = ln.cum_m3 = ln.cum_usd = 0.0
        st.conc_stock.shipped_t_shift = 0.0
        st.conc_stock.wagons_shift = 0

    @staticmethod
    def _summary(c: Counters) -> dict[str, float]:
        rec = PCT * c.cu_conc_t / c.cu_feed_t if c.cu_feed_t > 0 else NO_VALUE
        return {"ore_t": c.ore_t, "cu_feed_t": c.cu_feed_t, "cu_t": c.cu_conc_t, "conc_t": c.conc_t,
                "recovery_pct": rec, "energy_mwh": c.energy_mwh, "water_m3": c.water_intake_m3,
                "recycle_m3": c.water_recycle_m3, "usd": c.usd, "co2_t": c.co2_t, "minutes": c.minutes}

    # =================================================== internals: events
    def _apply_due_events(self, t: float) -> None:
        while self._events and self._events[0].t_start_min <= t + EPS:
            self._apply_event(self._events.pop(0))

    def _apply_event(self, e: ScenarioEvent) -> None:
        st, p = self.state, self.prm
        n = e.line
        t0 = e.t_start_min
        if e.data.get("work_h"):
            self._work_set[str(e.data.get("issue", ""))] = float(e.data["work_h"])
        if e.kind == "crusher":
            cr = st.line(n).crusher
            cr.fault = "scenario"
            cr.state = "STOP"
            cr.tph = 0.0
            cr.power_kw = 0.0
            self._register_loud("crusher:%d" % n, t0)
        elif e.kind == "grid":
            hours = e.duration_h if e.duration_h > 0 else p["pow_c2_h"]
            self._grid.append((t0, t0 + hours * MIN_PER_H, float(e.data.get("limit_mw", p["pow_c2_limit_mw"]))))
        elif e.kind == "hard":
            b0 = base_ore(p)
            est = OreProps(b0.cu_pct, b0.ascu_pct, float(e.data.get("axb", p["ore_axb_hard"])),
                           float(e.data.get("bwi", p["ore_bwi_hard"])))
            b = ore.inject_block(st, n, est, est.copy(), float(e.data.get("lead_h", p["scen_hard_lead_h"])),
                                 p, tag="hard")
            ore.plan_step(st, p)
            self.hooks.on_batch(st, b)
        elif e.kind == "reline":
            hours = e.duration_h if e.duration_h > 0 else p["liner_reline_h"]
            self._relines.append((n, t0, t0 + hours * MIN_PER_H, True))
            self._relines.sort(key=lambda w: w[1])
        elif e.kind == "trip":
            # faulty lube pressure sensor: the reading sits below the trip setpoint
            bias = e.data.get("bias_kpa", p["scen_trip_lube_kpa"] - p["crush_lube_kpa"])
            st.line(n).crusher.lube_bias_kpa = float(bias)
        elif e.kind == "safety":
            st.flags[str(e.data.get("flag", "piezo"))] = 1.0
        elif e.kind == "water":
            self._leak_frac = float(e.data.get("leak_frac", p["water_leak_frac"]))
            self._register_loud("water", t0)
        elif e.kind == "hpgr_fire":
            hours = e.duration_h if e.duration_h > 0 else p["scen_fire_h"]
            safety_h = float(e.data.get("safety_h", p["scen_fire_safety_h"]))
            st.flags["fire"] = float(n)
            self._fire_until = t0 + safety_h * MIN_PER_H
            self._peb[n] = sorted(self._peb.get(n, []) + [(t0, t0 + hours * MIN_PER_H)])
            # people at the HPGR during the maintenance leave the area (OFF) while the fire is not out
            pp.evacuate(st, [site().CREW_PERSON.get("crew-mill", "")], self._fire_until)
        elif e.kind == "road":
            hours = e.duration_h if e.duration_h > 0 else p["pit_road_close_h"]
            pt.close_road(st, n, t0 + hours * MIN_PER_H)
        elif e.kind == "conveyor":
            cv = st.line(n).conveyor
            cv.fault = "scenario"
            self._register_loud("conveyor:%d" % n, t0)
        elif e.kind == "pitstop":
            hours = e.duration_h if e.duration_h > 0 else p["scen_pitstop_h"]
            self._pitstop_until = t0 + hours * MIN_PER_H
            for ex in st.excavators:
                ex.state, ex.tph, ex.block = "DOWN", 0.0, ""
                ex.down_until_min = self._pitstop_until
            self._register_loud("pitstop", t0)
        elif e.kind == "icy":
            hours = e.duration_h if e.duration_h > 0 else p["scen_icy_h"]
            self._icy_until = t0 + hours * MIN_PER_H
        elif e.kind == "fatigue":
            hours = e.duration_h if e.duration_h > 0 else p["scen_fatigue_h"]
            self._fatigue_until = t0 + hours * MIN_PER_H
        elif e.kind in wear.KINDS:
            wear.start(self, e.kind, n, t0, e.data.get("fix_h"))
        elif e.kind in oxide.FAULT_KINDS:
            oxide.fault_start(st, e.kind, t0, e.data.get("fix_h"))
        elif e.kind == "oil":
            exc1 = next((x for x in st.excavators if x.name in site().OIL_SENSOR), None)
            if exc1 is not None:
                exc1.oil_event_min, exc1.oil_fix_min = t0, NO_VALUE
        elif e.kind == "hpgr":
            self._hpgr[n] = t0                  # not loud: nobody is alarmed, the module finds it by skew and drive power
            self._hpgr_tripped.discard(n)
        elif e.kind == "sample":
            st.line(n).analyzer.blocked = True
            self._register_loud("sample:%d" % n, t0)
        elif e.kind == "mantle":
            hours = e.duration_h if e.duration_h > 0 else p["crush_mantle_h"]
            cr = st.line(n).crusher
            cr.fault, cr.state, cr.tph, cr.power_kw = "mantle", "STOP", 0.0, 0.0
            cr.service_until_min = t0 + hours * MIN_PER_H
            self._register_loud("mantle:%d" % n, t0)
        elif e.kind == "winter":
            self.winter_on = True
        elif e.kind == "dust":
            hours = e.duration_h if e.duration_h > 0 else p["scen_dust_h"]
            self._dust_until = t0 + hours * MIN_PER_H
        elif e.kind == "leachcold":
            hours = e.duration_h if e.duration_h > 0 else p["scen_leach_h"]
            self._leach_until = t0 + hours * MIN_PER_H
        elif e.kind == "startup":
            # planned repair inside the ball mill "a" of line n by the mill crew (work permit); later somebody gives
            # the start command although people are inside
            self._ball_repair.add(n)
            t_cmd = t0 + p["scen_startup_after_min"]
            self._startups[n] = (t_cmd, t_cmd + p["scen_startup_h"] * MIN_PER_H)
            self._book(PlannedCall(t0, "ball-%da" % n, "crew-mill", "startup:%d" % n, p["scen_startup_work_h"]))

    def _random_events(self, t: float, dt: float) -> None:
        """Hidden causes per shift and pebble stop windows (free run and calib)."""
        st, p = self.state, self.prm
        while t >= self._hc_until - EPS:
            start = self._hc_until
            end = self._shift_start(self._shift_idx(start + EPS) + 1)
            for c in ev.draw_hidden_causes(st.seed, start, end, p):
                if c.t_start_min >= self._hc_last_end - EPS:
                    st.causes.append(c)
                    self._hc_last_end = c.t_end_min if c.t_end_min != NO_VALUE else INF
            self._hc_until = end
        while st.mode == "free" and t >= self._hc2_until - EPS:
            start = self._hc2_until
            end = self._shift_start(self._shift_idx(start + EPS) + 1)
            for c in ev.draw_hidden_causes(st.seed, start, end, p, silent=True):
                if c.t_start_min >= self._hc2_last_end - EPS:
                    st.causes.append(c)
                    self._hc2_last_end = c.t_end_min if c.t_end_min != NO_VALUE else INF
            self._hc2_until = end
        if st.mode == "calib" and t + dt > self._crw_until - EPS:
            self._crw_until = max(t + dt, self._rand_t0) + p["cal_draw_chunk_h"] * MIN_PER_H
            for ln in st.lines:
                planned, shorts = ev.draw_crusher_stops(st.seed, ln.n, self._rand_t0, self._crw_until, p)
                self._crw[ln.n] = [x for x in shorts if x[1] > t + EPS]
                self._crp[ln.n] = [a for a in planned if a > t - MIN_PER_DAY]
        if t + dt > self._peb_until - EPS:
            # windows are counted from the model origin, so the result does not
            # depend on the chunk length; none starts before the random start
            self._peb_until = max(t + dt, self._rand_t0) + p["cal_draw_chunk_h"] * MIN_PER_H
            for ln in st.lines:
                w = ev.draw_pebble_stops(st.seed, ln.n, self._rand_t0, self._peb_until, p)
                self._peb[ln.n] = sorted(x for x in w if x[1] > t + EPS and x[0] >= self._rand_t0 - EPS)

    def _end_due_causes(self, t: float) -> None:
        st = self.state
        for c in [c for c in st.causes if c.t_end_min != NO_VALUE and c.t_end_min <= t + EPS]:
            self._end_cause(c, c.t_end_min, c.found_by or "lab")

    def _end_cause(self, c: HiddenCause, t_end: float, by: str) -> None:
        """Close a hidden cause: truth log entry (validation-sim) and removal from the state."""
        st = self.state
        c.t_end_min = t_end
        if c.t_found_min == NO_VALUE and by != "cancel":
            c.t_found_min = t_end
        if not c.found_by:
            c.found_by = by
        found = _hhmm(c.t_found_min) if c.t_found_min != NO_VALUE else "—"
        # the truth log is shown in the interface (validation-sim.truth_log): Russian text
        text = (f"{CAUSE_RU.get(c.kind, c.kind)} на линии {c.line}: с {_hhmm(c.t_start_min)} до {_hhmm(t_end)}, "
                f"найдена в {found} ({FOUND_BY_RU.get(c.found_by, c.found_by)})"
                + ("; сценарий отменён" if by == "cancel" else ""))
        entry = TruthEntry(t_end, c.kind, c.line, text,
                           {"t_start_min": c.t_start_min, "t_found_min": c.t_found_min, "t_end_min": t_end,
                            "magnitude": c.magnitude, "found_by": c.found_by, "preset": c.preset})
        st.truth_log.append(entry)
        if c in st.causes:
            st.causes.remove(c)
        self.hooks.on_truth(st, entry)

    def _windows(self, t: float) -> None:
        """Grid limit, relines, calib downtime and pebble stops active at t."""
        st, p = self.state, self.prm
        limit = p["pow_grid_limit_mw"]
        for a, b, lim in self._grid:
            if a <= t + EPS and t < b - EPS:
                limit = min(limit, lim)
        if limit != self._limit_mw:
            self._set_grid_limit(limit)
        if self._grid and all(b <= t + EPS for _a, b, _l in self._grid):
            self._grid = []
        if not self._grid and self._c2_latch is not None and not any(e.kind == "grid" for e in self._events):
            self._c2_latch = None                       # the restriction is over: the C2 call is spent
        if self._fire_until != NO_VALUE and t >= self._fire_until - EPS:
            st.flags.pop("fire", None)
            self._fire_until = NO_VALUE
        if self._piezo_until != NO_VALUE and t >= self._piezo_until - EPS:
            st.flags.pop("piezo", None)                 # the technologist checked the dam: the reading is back below the setpoint
            self._piezo_until = NO_VALUE
        if self._dust_until != NO_VALUE and t >= self._dust_until - EPS:
            self._dust_until = NO_VALUE
        if self._leach_until != NO_VALUE and t >= self._leach_until - EPS:
            self._leach_until = NO_VALUE
        if self._pitstop_until != NO_VALUE and t >= self._pitstop_until - EPS:
            self._pitstop_until = NO_VALUE            # the excavators leave DOWN by themselves (ore.dig_step)
        if self._extra_teams and self._extra_until and all(d <= t + EPS for d in self._extra_until.values()):
            for cn in self._extra_teams:                  # the deputy's jobs are done: back to the usual teams
                cr = st.crews.get(cn)
                if cr is not None and cr.count > 1:
                    self._set_crew_count(cn, cr.count - 1)
            self._extra_teams.clear()
            self._extra_until.clear()
        for ln in st.lines:
            win = self._startups.get(ln.n)
            on = 1.0 if (win is not None and win[0] <= t + EPS and t < win[1] - EPS) else 0.0
            for b in ln.balls:
                b.start_cmd = on if b.name == "ball-%da" % ln.n else 0.0
        for ln in st.lines:
            n, sag = ln.n, ln.sag
            rel = None
            for line, a, b, _scen in self._relines:
                if line == n and a <= t + EPS and t < b - EPS:
                    rel = b
                    break
            if rel is not None:
                sag.state = "RELINE"
                sag.reline_until_min = rel
                st.flags["people_in_sag"] = float(n)
            elif sag.state == "RELINE":
                sag.state = "RUN"                  # new liner after the reline
                sag.liner_x = 0.0
                sag.liner_wear_mm = 0.0
                sag.liner_ground_t = 0.0
                sag.reline_until_min = NO_VALUE
                if st.flags.get("people_in_sag") == float(n):
                    del st.flags["people_in_sag"]
            wins = ln.down_windows
            i = self._down_idx[n]
            while i < len(wins) and wins[i][1] <= t + EPS:
                i += 1
            self._down_idx[n] = i
            if sag.state != "RELINE":
                if i < len(wins) and wins[i][0] <= t + EPS:
                    sag.state = "STOP"
                elif sag.state == "STOP":
                    sag.state = "RUN"
            self._down[n] = sag.state in ("RELINE", "STOP")
            self._hpgr_step(ln, t)
            if st.mode == "calib":
                self._crusher_own_stops(ln, t)
            pw = self._peb[n]
            while pw and pw[0][1] <= t + EPS:
                pw.pop(0)
            peb = ln.pebble
            if pw and pw[0][0] <= t + EPS:
                peb.state = "STOP"
                peb.stop_until_min = pw[0][1]
            elif peb.state == "STOP":
                peb.state = "RUN"
                peb.stop_until_min = NO_VALUE
        if self._relines and any(w[2] <= t + EPS for w in self._relines):
            self._relines = [w for w in self._relines if w[2] > t + EPS]

    def _crusher_own_stops(self, ln, t: float) -> None:
        """Own stops of the primary crusher in a calib run: short stoppages; planned maintenance (crush_plan_h of work, done while the
        mill of the line stands, as the maintenance shift does, or after crush_plan_wait_d days of waiting whatever the mill does);
        the liner change of the crusher inside the first SAG reline of the year (both stand, no ore is lost)."""
        p, n, cr = self.prm, ln.n, ln.crusher
        on = any(a <= t + EPS and t < b - EPS for a, b in self._crw[n])
        dt = max(0.0, t - self._crp_t[n]) if self._crp_t[n] != NO_VALUE else 0.0
        self._crp_t[n] = t
        pend = self._crp[n]
        while pend and pend[0] <= t + EPS:                       # a nominal start passed: that much work is added
            self._crp_left[n] += p["crush_plan_h"] * MIN_PER_H
            if self._crp_since[n] == NO_VALUE:
                self._crp_since[n] = pend[0]
            pend.pop(0)
        left = self._crp_left[n]
        if left > EPS:
            mill_down = ln.sag.state in ("RELINE", "STOP")
            if mill_down or t - self._crp_since[n] >= p["crush_plan_wait_d"] * MIN_PER_DAY:
                on = True
                self._crp_left[n] = max(0.0, left - dt)
            if self._crp_left[n] <= EPS:
                self._crp_left[n], self._crp_since[n] = 0.0, NO_VALUE
        year = int(t // (365.0 * MIN_PER_DAY))
        for line, a, b, _scen in self._relines:
            if line == n and a <= t + EPS and t < min(b, a + p["crush_mantle_h"] * MIN_PER_H) - EPS and self._mantle_year[n] in (-1, year):
                on = True
                self._mantle_year[n] = year
        if on and not cr.fault:
            cr.fault = "own"
        elif not on and cr.fault == "own":
            cr.fault = ""

    # ===================================================== internals: grid
    def _power_balance(self) -> None:
        st = self.state
        loads = PowerLoads(sag_kw={ln.n: ln.sag.power_kw for ln in st.lines},
                           ball_kw={b.name: b.power_kw for ln in st.lines for b in ln.balls},
                           crusher_kw={ln.n: ln.crusher.power_kw for ln in st.lines},
                           conveyor_kw={ln.n: ln.conveyor.power_kw for ln in st.lines})
        ut.power_balance(st.power, loads, self.prm)

    def _relief_mw(self) -> dict[str, float]:
        """Grid MW each shedding candidate frees: a ball mill's own power plus the SAG cut of the line rule."""
        st, p = self.state, self.prm
        eff = p["pow_motor_eff"]
        relief = {"other_cat2": p["pow_shed_other_mw"]}
        for ln in st.lines:
            sag = ln.sag
            feed = sag.feed_ore if sag.feed_ore.axb > 0 else base_ore(p)
            e = cm.sag_specific_energy(feed, p, ln.pebble.state != "STOP")
            for b in ln.balls:
                if b.state != "RUN" or b.power_kw <= 0:
                    continue
                b.state = "STOP"
                q_cap = cm.line_feed_cap_tph(ln.balls, feed.bwi, p)
                b.state = "RUN"
                sag_after = sag.power_kw
                if q_cap < INF:
                    sag_after = min(sag.power_kw, cm.sag_power_for_tph(q_cap, e, sag.eta))
                relief[b.name] = (b.power_kw + sag.power_kw - sag_after) / KW_PER_MW / eff
        return relief

    def _set_grid_limit(self, limit_mw: float) -> None:
        """New grid limit: load shedding by utilities.shed_plan, or restore everything."""
        st, p = self.state, self.prm
        pw = st.power
        self._limit_mw = limit_mw
        pw.grid_limit_mw = limit_mw
        self._shed_balls = []
        pw.shed = []
        lines = [ln.n for ln in st.lines]
        self._grid_cap_kw = {n: INF for n in lines}
        self._bonus_kw = {n: 0.0 for n in lines}
        if limit_mw >= p["pow_grid_limit_mw"]:
            self._power_balance()
            return
        self._power_balance()
        relief = self._relief_mw()
        plan = ut.shed_plan(pw.site_mw, limit_mw, relief, p)
        self._shed_balls = list(plan.balls_off)
        pw.shed = list(plan.balls_off) + (["other_cat2"] if plan.other_shed_mw > 0 else [])
        for n, cap in plan.sag_cap_kw.items():
            self._grid_cap_kw[n] = min(self._grid_cap_kw.get(n, INF), cap)
        # still above the limit after the whole list: cap SAG power (shed line first)
        freed = sum(relief.get(x, 0.0) for x in pw.shed)
        short_kw = (pw.site_mw - freed - limit_mw) * KW_PER_MW * p["pow_motor_eff"]
        order = sorted(st.lines, key=lambda ln: (not any(b.name in self._shed_balls for b in ln.balls),
                                                 -ln.sag.power_kw))
        for ln in order:
            if short_kw <= 0:
                break
            cut = min(short_kw, ln.sag.power_kw)
            self._grid_cap_kw[ln.n] = min(self._grid_cap_kw[ln.n], ln.sag.power_kw - cut)
            short_kw -= cut

    def _c2_call(self, node: str, n: int) -> None:
        """C2 response: spend pow_call_use_mw of the headroom on the SAG of the line with a shed mill.

        The call latches: made before the automatic shedding (or while the headroom is short) it is
        applied at the first step where a ball mill is shed and the headroom allows, as a dispatcher
        would repeat it; it is spent when the grid restriction (all announced windows) is over.
        A call with no restriction active or announced does nothing.
        """
        p = self.prm
        pending = bool(self._grid) or any(e.kind == "grid" for e in self._events)
        if self._limit_mw >= p["pow_grid_limit_mw"] and not pending:
            return
        self._c2_latch = (node, int(n))
        self._c2_try()

    def _c2_try(self) -> bool:
        """Apply a latched C2 call when the shed and the headroom allow; True when the bonus is set."""
        st, p = self.state, self.prm
        if self._c2_latch is None or self._limit_mw >= p["pow_grid_limit_mw"]:
            return False
        _node, n = self._c2_latch
        lines = [node_kind_line(b)[1] for b in self._shed_balls]
        if n and n in self._bonus_kw:
            lines = [n] if not lines or n in lines else []
        if not lines:
            return False
        n = lines[0]
        if self._bonus_kw[n] > 0.0:
            return True
        if st.power.headroom_mw < p["pow_call_use_mw"]:
            return False
        self._bonus_kw[n] = p["pow_call_use_mw"] * KW_PER_MW * p["pow_motor_eff"]
        return True

    def _pit_call(self, kind: str, n: int, node: str) -> None:
        """C3 (blend the hard block 50/50) and C4 (excavators idle while the stockpile is full)."""
        st = self.state
        lines = [ln.n for ln in st.lines]
        if kind in ("hard", "pit"):
            hard_lines = [n] if (kind == "hard" and n in lines) else []
            nk, _ = node_kind_line(node)
            if nk == "batch" and node in st.batches:
                hard_lines = [st.batches[node].line]
            if not hard_lines and kind == "pit":
                hard_lines = sorted({b.line for b in st.batches.values()
                                     if b.tag == "hard" and b.state in ("PLANNED", "DIG")})
            for m in hard_lines:
                st.pit.blend[m] = True
        if kind in ("reline", "pit"):
            rel_lines = [n] if (kind == "reline" and n in lines) else []
            if kind == "pit":
                rel_lines = [ln.n for ln in st.lines if ln.sag.state == "RELINE"]
            for m in rel_lines:
                self._c4[m] = True

    # ================================================ internals: pit, tier S
    def _restrict_traffic(self, t: float) -> None:
        """Decision of the mine dispatcher: traffic restriction (speed limit) on the haul roads until the spell is over."""
        p = self.prm
        end = (self._icy_until if self._icy_until != NO_VALUE and self._icy_until > t else t + p["scen_icy_h"] * MIN_PER_H)
        self.state.pit.restrict_until_min = end + 30.0

    def _pit_weather(self, t: float) -> None:
        """Visibility, friction index and truck cycle multiplier of the haul roads for this step (winter touches the pit,
        not the plant: the multiplier of the season is small); fatigue alert flags of the fleet."""
        st, p = self.state, self.prm
        pit = st.pit
        icy = self._icy_until != NO_VALUE and t < self._icy_until - EPS
        if self._icy_until != NO_VALUE and not icy:
            self._icy_until = NO_VALUE
        if icy:
            vis, grip, mult = p["pit_vis_icy_m"], p["pit_grip_icy"], p["pit_icy_cycle_mult"]
        elif self.winter_on:
            vis, grip, mult = p["pit_vis_clear_m"], p["pit_grip_winter"], p["pit_winter_cycle_mult"]
        else:
            vis, grip, mult = p["pit_vis_clear_m"], p["pit_grip_clear"], 1.0
        if pit.restrict_until_min != NO_VALUE:
            if t < pit.restrict_until_min - EPS:
                mult *= p["pit_restrict_cycle_mult"]
            else:
                pit.restrict_until_min = NO_VALUE
        pit.visibility_m, pit.road_grip, pit.cycle_mult = vis, grip, mult * self._wmult
        fl = st.fleet
        on = self._fatigue_until != NO_VALUE and t < self._fatigue_until - EPS
        if self._fatigue_until != NO_VALUE and not on:
            self._fatigue_until = NO_VALUE
        fl.fatigue = on
        if on:
            _tid, bort, model = site().fatigue_truck(p)
            fl.fatigue_truck = f"{bort} ({model})"
        else:
            fl.fatigue_truck = ""

    def _oil_call(self, t: float) -> None:
        """The shift mechanic is called to the excavator with contaminated oil: filtration and flushing take pit_oil_fix_h;
        a call after the pump has failed does not shorten the repair."""
        p = self.prm
        for ex in self.state.excavators:
            if ex.oil_event_min != NO_VALUE and ex.state != "DOWN" and ex.oil_fix_min == NO_VALUE:
                ex.oil_fix_min = t + ev.arrival_min(self.state.seed, "oil", p) + p["pit_oil_fix_h"] * MIN_PER_H
        person = site().DECISION_PERSON.get("oil")
        if person:
            pp.assign_duty(self.state, person, "exc-1", t, p, hours=p["pit_oil_fix_h"])

    def _oil_step(self, t: float) -> None:
        """Hydraulic oil contamination of the excavator with a sensor (scenario oil): rises to the alert level over pit_oil_rise_h,
        pit_oil_fail_h later the pump fails (the excavator is DOWN for pit_oil_repair_h) unless the oil was serviced."""
        p = self.prm
        start, alert = p["pit_oil_start_pct"], p["pit_oil_alert_pct"]
        for ex in self.state.excavators:
            if ex.oil_event_min == NO_VALUE:
                continue
            if ex.oil_fix_min != NO_VALUE and t >= ex.oil_fix_min - EPS:
                ex.oil_pct, ex.oil_event_min, ex.oil_fix_min = start, NO_VALUE, NO_VALUE   # serviced (or repaired)
                continue
            if ex.state == "DOWN":
                continue
            h = max(0.0, (t - ex.oil_event_min) / MIN_PER_H)
            ex.oil_pct = min(1.4 * alert, start + (alert - start) * h / p["pit_oil_rise_h"])
            if ex.oil_fix_min == NO_VALUE and h >= p["pit_oil_rise_h"] + p["pit_oil_fail_h"]:
                ex.state, ex.tph, ex.block = "DOWN", 0.0, ""
                ex.down_until_min = t + p["pit_oil_repair_h"] * MIN_PER_H
                ex.oil_fix_min = ex.down_until_min

    def _hpgr_step(self, ln: LineState, t: float) -> None:
        """Uneven feed of the HPGR (scenario hpgr:N, line 2): skew and power difference of the drives grow over peb_hpgr_ramp_min,
        the HPGR throughput falls; if nobody repairs in peb_hpgr_tramp_after_h tramp metal reaches the rolls, the metal detector
        trips and the HPGR stands peb_hpgr_stop_h."""
        p, peb, n = self.prm, ln.pebble, ln.n
        t0 = self._hpgr.get(n)
        if t0 is None:
            if peb.hpgr_eff != 1.0 or peb.hpgr_skew_pct != 0.0 or peb.metal_alarm:
                peb.hpgr_eff, peb.hpgr_skew_pct, peb.hpgr_kw_diff_pct, peb.metal_alarm = 1.0, 0.0, 0.0, False
            return
        age = max(0.0, t - t0)
        ramp = min(1.0, age / p["peb_hpgr_ramp_min"]) if p["peb_hpgr_ramp_min"] > 0 else 1.0
        peb.hpgr_eff = 1.0 - (1.0 - p["peb_hpgr_uneven_eff"]) * ramp
        peb.hpgr_skew_pct = p["peb_hpgr_skew_pct"] * ramp
        peb.hpgr_kw_diff_pct = p["peb_hpgr_kwdiff_pct"] * ramp
        if age >= p["peb_hpgr_tramp_after_h"] * MIN_PER_H and n not in self._hpgr_tripped:
            self._hpgr_tripped.add(n)
            self._peb[n] = sorted(self._peb.get(n, []) + [(t, t + p["peb_hpgr_stop_h"] * MIN_PER_H)])
        stop = self._peb.get(n) and self._peb[n][0][0] <= t + EPS
        peb.metal_alarm = bool(n in self._hpgr_tripped and stop)

    # ==================================================== internals: crews
    def _set_crew_count(self, name: str, count: int) -> None:
        crew = self.state.crews.get(name)
        if crew is None or count < 1 or crew.count == count:
            return
        slots = list(crew.slot_free_min)
        crew.count = count
        crew.slot_free_min = (slots + [NO_VALUE] * count)[:count]

    def _register_loud(self, issue: str, t_start: float) -> None:
        """Loud issue: noticed by alarm notice_delay_min after it starts, unless called before."""
        if issue in self._loud or issue in self._held_loud or issue in self._jobs:
            return
        t_notice = t_start + ev.notice_delay_min(self.state.seed, issue, self.prm)
        if self.follow_module:
            self._held_loud[issue] = t_notice   # seen on the alarm panel, called when the module says so
        else:
            self._loud[issue] = t_notice

    def set_follow_module(self, on: bool) -> None:
        """The dispatcher of this copy follows the calls of the module (on) or the alarm panel (off).

        On: a loud issue is kept in _held_loud, no crew is booked for it by the alarm. Off (the module
        is missing, fallback): the held issues go back to the alarm list and are called at once if the
        notice time has passed.
        """
        self.follow_module = bool(on)
        if not on:
            for issue, t_notice in list(self._held_loud.items()):
                self._loud[issue] = t_notice
            self._held_loud.clear()

    def _call_pending(self, issue: str) -> bool:
        return any(c.issue == issue for c in self._calls)

    def _crews_step(self, t: float) -> None:
        st = self.state
        span = max(t - self._crew_t, EPS)
        for crew in st.crews.values():
            ev.crew_step(crew, t, span)
        self._crew_t = t
        for issue, job in [(i, j) for i, j in self._jobs.items() if j.t_done_min <= t + EPS]:
            del self._jobs[issue]
            self._finish(issue, job)
        while self._calls and self._calls[0].t_min <= t + EPS:
            pc = self._calls.pop(0)
            self._book(pc, pc.src or "plan")
        for issue, t_notice in list(self._loud.items()):
            if t >= t_notice - EPS and issue not in self._jobs and not self._call_pending(issue):
                if self._book(PlannedCall(t, "", "", issue), "alarm") is None and not self._issue_active(issue, t):
                    del self._loud[issue]
        for issue in list(self._held_loud):
            if issue in self._jobs or not self._issue_active(issue, t):
                del self._held_loud[issue]           # called by the module, or over by itself

    def _crew_for(self, kind: str, node: str) -> str | None:
        name = CREW_FOR.get(_CREW_KEY.get(kind, kind))
        if name is None and node:
            nk, _ = node_kind_line(node)
            name = CREW_FOR.get(_CREW_KEY.get(nk, nk))
        return name

    def _issue_active(self, issue: str, t: float) -> bool:
        st = self.state
        kind, n = parse_issue(issue)
        if kind == "water":
            return self._leak_frac > 0.0
        if kind == "leak":
            return any(c.kind == "leak" and self._active(c, t) for c in st.causes)
        if kind == "pitstop":
            return self._pitstop_until != NO_VALUE and t < self._pitstop_until - EPS
        if kind == "icy":
            return self._icy_until != NO_VALUE and t < self._icy_until - EPS
        if kind == "fatigue":
            return self._fatigue_until != NO_VALUE and t < self._fatigue_until - EPS
        if kind == "oil":
            return any(x.oil_event_min != NO_VALUE for x in st.excavators)
        if kind in wear.KINDS:
            return wear.active(st, kind, n)
        if kind in oxide.FAULT_KINDS:
            return kind in st.oxf
        if not 1 <= n <= len(st.lines):
            return False
        if kind == "hpgr":
            return n in self._hpgr
        if kind == "sample":
            return st.line(n).analyzer.blocked
        if kind == "mantle":
            return st.line(n).crusher.fault == "mantle"
        if kind == "conveyor":
            return st.line(n).conveyor.fault == "scenario"
        if kind == "startup":
            return n in self._ball_repair
        if kind == "crusher":
            return st.line(n).crusher.fault == "scenario"
        if kind == "trip":
            cr = st.line(n).crusher
            return cr.fault == "lube_trip" or cr.lube_bias_kpa != 0.0
        if kind in CAUSE_KINDS:
            return any(c.kind == kind and c.line == n and self._active(c, t) for c in st.causes)
        return False

    @staticmethod
    def _active(c: HiddenCause, t: float) -> bool:
        return c.t_start_min <= t + EPS and (c.t_end_min == NO_VALUE or t < c.t_end_min - EPS)

    def _book(self, pc: PlannedCall, src: str = "") -> CrewJob | None:
        """Book a crew for an issue (one open job per issue); None when nothing to fix.

        src says who called (call_log): "module" (auto_call of akt-priority), "button" (the dispatcher),
        "alarm" (the alarm panel after the notice delay), "plan" (a call of the copy policy), "fallback"
        (the offline order, used when the module is missing).
        """
        st, p = self.state, self.prm
        issue = pc.issue
        if issue in self._jobs:
            return self._jobs[issue]
        t = st.clock.t_min
        if not self._issue_active(issue, t):
            return None
        kind, n = parse_issue(issue)
        self._mark_found(kind, n, t, "module")
        node = pc.node or ISSUE_NODE.get(kind, "").format(n)
        crew_name = pc.crew if pc.crew in st.crews else self._crew_for(kind, node)
        if crew_name not in st.crews:
            return None
        work_h = pc.work_h
        if not (work_h is not None and math.isfinite(work_h) and work_h > 0.0):
            work_h = ev.repair_hours(st.seed, issue, self._work_set.get(issue) or ev.work_median_h(kind, p), p)
        travel = p["crew_dose_arrive_min"] if kind == "dose" else ev.arrival_min(st.seed, issue, p)
        if getattr(self, "_late_ok", False) and u01(st.seed, int(t), "late-" + issue, 0) < p["crew_late_p"]:
            travel += p["crew_late_min"]          # the message reached the person late (free run, people called)
        job = ev.crew_call(st.crews[crew_name], PlannedCall(pc.t_min, node, crew_name, issue, work_h),
                           travel, work_h)
        self._jobs[issue] = job
        self.call_log.append({"t": float(t), "issue": issue, "node": node, "src": src or "other"})
        if kind in ("crusher", "trip"):
            st.line(n).crusher.fault_until_min = job.t_done_min
        elif kind == "conveyor":
            st.line(n).conveyor.fault_until_min = job.t_done_min
        elif kind == "mantle":
            st.line(n).crusher.service_until_min = job.t_done_min
        return job

    def _finish(self, issue: str, job: CrewJob) -> None:
        """A crew finished: clear the fault or end the hidden cause."""
        st = self.state
        kind, n = parse_issue(issue)
        if kind in ("water", "leak"):
            if kind == "water":
                self._leak_frac = 0.0                    # leak repaired: the return water is whole again
                self._loud.pop(issue, None)
            for c in [c for c in st.causes if c.kind == "leak" and self._active(c, job.t_done_min)]:
                self._end_cause(c, job.t_done_min, "crew")
            return
        if not 1 <= n <= len(st.lines):
            return
        if kind == "startup":
            self._ball_repair.discard(n)
            self._startups.pop(n, None)
            for b in st.line(n).balls:
                b.start_cmd = 0.0
            return
        if kind == "conveyor":
            cv = st.line(n).conveyor
            cv.fault, cv.fault_until_min = "", NO_VALUE
            self._loud.pop(issue, None)
            return
        if kind == "sample":
            st.line(n).analyzer.blocked = False                  # sample line cleaned: the analyser reads again
            self._loud.pop(issue, None)
            return
        if kind == "mantle":
            cr = st.line(n).crusher
            cr.fault, cr.service_until_min = "", NO_VALUE        # new mantle: the crusher runs again
            self._loud.pop(issue, None)
            return
        if kind == "hpgr":
            self._hpgr.pop(n, None)                             # feed chute / cheek plates set, metal removed
            self._hpgr_tripped.discard(n)
            self._peb[n] = []
            peb = st.line(n).pebble
            if peb.state == "STOP":
                peb.state, peb.stop_until_min = "RUN", NO_VALUE
            self._loud.pop(issue, None)
            return
        if kind in ("crusher", "trip"):
            cr = st.line(n).crusher
            if kind == "crusher" and cr.fault == "scenario":
                cr.fault = ""
            if kind == "trip":
                cr.lube_bias_kpa = 0.0
                if cr.fault == "lube_trip":
                    cr.fault = ""
            cr.fault_until_min = NO_VALUE
            self._loud.pop(issue, None)
        elif kind in CAUSE_KINDS:
            for c in [c for c in st.causes if c.kind == kind and c.line == n and self._active(c, job.t_done_min)]:
                self._end_cause(c, job.t_done_min, "crew")
            if kind == "phdrift":
                st.line(n).ph.lab_idx = -1            # the cleaned electrode is checked with a fresh grab sample

    def _mark_found(self, kind: str, n: int, t: float, by: str) -> None:
        for c in self.state.causes:
            if c.kind == kind and c.line == n and c.t_found_min == NO_VALUE and self._active(c, t):
                c.t_found_min = t
                c.found_by = by

    def _issue_at(self, node: str) -> tuple[str, int]:
        """Issue behind a call without an issue key, from the node and the current state."""
        st = self.state
        nk, n = node_kind_line(node)
        t = st.clock.t_min
        if st.wear:
            hit = wear.issue_at(st, node)
            if hit is not None:
                return hit
        if st.oxf:
            kind_ox = oxide.fault_issue_at(st, node)
            if kind_ox is not None:
                return kind_ox, 0
        if nk == "power":
            return "grid", 0
        if nk in ("water", "piezometer", "piezo") and st.flags.get("piezo"):
            return "piezo", 0
        if nk in ("water", "piezometer", "piezo") and self._leak_frac > 0.0:
            return "water", 0
        if nk == "water" and any(c.kind == "leak" and self._active(c, t) for c in st.causes):
            return "leak", 0
        if nk == "pebble" and st.flags.get("fire") == float(n):
            return "hpgr_fire", n
        if nk == "pebble" and n in self._hpgr:
            return "hpgr", n
        if nk == "analyzer" and 1 <= n <= len(st.lines) and st.line(n).analyzer.blocked:
            return "sample", n
        if nk == "pit" and self._pitstop_until != NO_VALUE and t < self._pitstop_until - EPS:
            return "pitstop", 0
        if nk in ("pit", "road", "ramp") and self._icy_until != NO_VALUE and t < self._icy_until - EPS:
            return "icy", 0
        if nk == "fleet" and self._fatigue_until != NO_VALUE and t < self._fatigue_until - EPS:
            return "fatigue", 0
        if nk == "exc" and any(x.oil_event_min != NO_VALUE for x in st.excavators):
            return "oil", 0
        if nk in ("pit", "batch"):
            return ("hard", 0) if nk == "batch" else ("pit", 0)
        if not 1 <= n <= len(st.lines):
            return "", 0
        if nk == "crusher":
            cr = st.line(n).crusher
            if cr.fault == "scenario":
                return "crusher", n
            if cr.fault == "mantle":
                return "mantle", n
            if cr.fault == "lube_trip" or cr.lube_bias_kpa != 0.0:
                return "trip", n
            return "", 0
        if nk == "sag" and any(node_kind_line(b)[1] == n for b in self._shed_balls):
            return "grid", n
        if nk == "ball" and any(b.name == node and b.start_cmd == 1.0 for b in st.line(n).balls):
            return "startup", n
        want = {"flot": ("dose", "oxide", "reagent", "phdrift"), "rougher": ("reagent", "dose", "oxide", "phdrift"),
                "cleaner": ("dose", "oxide"), "flowmeter": ("reagent", "dose"),
                "cyclones": ("cyclone", "roping"), "sag": ("energy", "liner"), "ball": ("balls", "roping"),
                "line": ("balls",), "ph": ("phdrift",), "phmeter": ("phdrift",)}.get(nk, ())
        for c in st.causes:
            if c.line == n and c.kind in want and self._active(c, t):
                return c.kind, n
        return "", 0

    # ===================================================== internals: line
    def _line_step(self, ln: LineState, t: float, dt: float, k: int, cs_full: bool) -> dict:
        """Grinding and flotation of one line (step 5); returns the flows used by steps 6-9."""
        st, p = self.state, self.prm
        n = ln.n
        sag, peb = ln.sag, ln.pebble
        down = self._down[n]
        wq = self._wq.get(n)
        fx = ev.cause_effects(st.causes, n, t, p) if st.causes else CauseEffects()
        ln.cyclones.clogged = int(fx.clogged)
        f = ore.feed_props(st, n)
        feed = OreProps(f.cu_pct, f.ascu_pct + fx.ascu_add_pp, f.axb, f.bwi)
        for b in ln.balls:
            b.state = "STOP" if (down or b.name in self._shed_balls
                                 or (n in self._ball_repair and b.name == "ball-%da" % n)) else "RUN"
        ln.balls_gt = p["ball_media_gt"] * fx.balls_mult
        cap_kw = INF
        rule_bound = False
        avail = 0.0
        lv = st.levers                    # what-if levers (control of the model); empty = off, nothing below changes
        feed_sp = 0.0
        if not down:
            avail = ore.stock_available_tph(st, n, dt)
            if wq is not None:
                avail = min(avail, wq[0] * p["cal_line_tph"])   # tier T: drive derate, buried rakes, worn feed pump (like the water cut)
            if self._water_scale < 1.0:
                # not enough process water: the line takes only the ore the water allows
                avail = min(avail, self._water_scale * p["cal_line_tph"])
            cap_kw = self._grid_cap_kw[n]
            rule_q = cm.line_feed_cap_tph(ln.balls, feed.bwi, p, lv.get("p80_um", 0.0) if lv else 0.0)
            if rule_q < INF:
                e = cm.sag_specific_energy(feed, p, peb.state != "STOP") * fx.sag_e_mult
                eta = cm.liner_eta(sag.liner_x, p) * fx.sag_eta_mult
                rule_kw = cm.sag_power_for_tph(rule_q, e, eta) + self._bonus_kw[n]
                if rule_kw < cap_kw:
                    cap_kw = rule_kw
                    rule_bound = True
        if peb.hpgr_tph > 0.0:           # uneven feed of the HPGR lowers what the pebble circuit of line 2 can take
            peb.limit_tph = min(p["peb_limit_tph"], peb.hpgr_tph * peb.hpgr_eff)
        if lv and not down:
            feed_sp = self._lever_feed_sp(n, feed.bwi, ln)
        q = cm.sag_step(sag, peb, avail, feed, cap_kw, fx, dt, p, normal(st.seed, k, "sag-%d" % n), feed_sp)
        drawn = ore.reclaim_step(st, n, q, dt, p)
        used = feed
        if q > 0.0 and drawn is not None and drawn.cu_pct > 0.0:
            used = OreProps(drawn.cu_pct, drawn.ascu_pct + fx.ascu_add_pp, drawn.axb, drawn.bwi)
        p80_grind = cm.ball_step(ln.balls, q, used.bwi, p)
        p80 = cm.cyclone_step(ln.cyclones, q, p80_grind, p, fx.rope)
        for b in ln.balls:
            b.overload_pct = p["ball_rope_over_pct"] * fx.rope if (b.state == "RUN" and q > 0.0) else 0.0
        # recovery lost beyond the P80 effect: pH above the setpoint (scaled electrode), a rougher line stopped by heavy roping
        ln.ph.bias = fx.ph_bias
        if fx.rope_flot_pp > 0.0 and n not in self._rope_flot:
            self._rope_flot[n] = t + p["cyc_rope_flot_h"] * MIN_PER_H
        rope_loss = fx.rope_flot_pp if fx.rope_flot_pp > 0.0 else (
            p["cyc_rope_flot_pp"] if t < self._rope_flot.get(n, -INF) else 0.0)
        if fx.rope_flot_pp <= 0.0 and n in self._rope_flot and t >= self._rope_flot[n]:
            del self._rope_flot[n]
        rec_loss = p["flot_ph_pp_unit"] * fx.ph_bias + rope_loss
        if wq is not None:
            rec_loss += wq[1]                 # tier T: level oscillation of the flotation cells
        rough = ln.rougher
        dose_ratio, dose_meas, conc_drop = fx.dose_ratio, rough.dose_sp_gt, fx.conc_drop_pp
        if lv:
            rec_loss, dose_ratio, dose_meas, conc_drop = self._lever_flotation(lv, p80, rec_loss, fx, rough)
        res = fz.flotation_step(ln.flot, rough, ln.cleaner, q, used, p80, dose_ratio, dose_meas,
                                t, dt, p, conc_drop, rec_loss)
        self._reagent_tank(rough, q, dt)
        cap = fz.filter_capacity_tph(ln.filter, t, cs_full, st.seed, p)
        if wq is not None:
            cap *= wq[2]                      # tier T: blind filter cloth
        uf = fz.thickener_step(ln.thick, res.conc_tph, cap, dt, p)
        # weigher totalizers: every step's weighed rate (class 1 noise) x dt, as a plant counts them;
        # the concentrate balance of akt-losses takes differences of these, not sparse rate samples
        ws = p["sens_weigher_sigma"]
        th = ln.thick
        th.feed_t_total += max(0.0, th.feed_tph) * (1.0 + ws * normal(st.seed, k, "thick-%d-feed-tot" % n)) * dt / MIN_PER_H
        th.underflow_t_total += max(0.0, uf) * (1.0 + ws * normal(st.seed, k, "thick-%d-uf-tot" % n)) * dt / MIN_PER_H
        wet = fz.filter_step(ln.filter, uf, p, normal(st.seed, k, "moist-%d" % n))
        ln.tph = q
        ln.cu_tph = res.cu_tph
        ln.recovery = ln.flot.recovery
        if down or q <= 0.0:
            ln.state = "STOP"
        elif (rule_bound or sag.state in ("STARVED", "LIMITED_GRID") or peb.state != "RUN"
              or any(b.state != "RUN" for b in ln.balls)):
            ln.state = "LIMITED"
        else:
            ln.state = "RUN"
        tail = res.tail_cu_pct if (q > 0.0 and res.tail_cu_pct > 0.0) else 0.0
        return {"n": n, "q": q, "ore": used, "cu_feed_tph": q * used.cu_pct / PCT, "cu_tph": res.cu_tph,
                "conc_tph": res.conc_tph, "tails_cu_tph": max(0.0, q - res.conc_tph) * tail / PCT,
                "tails_tph": max(0.0, q - res.conc_tph), "cake_tph": ln.filter.cake_tph,
                "moist_pct": ln.filter.moisture_pct, "wet_tph": wet}

    # ------------------------------------------------------------ levers (what-if control of the MODEL, not of the plant)
    LEVER_KEYS = ("feed_1", "feed_2", "p80_um", "dose_gt")

    def set_levers(self, values: dict | None) -> dict[str, float]:
        """Set the what-if levers on this copy; returns the levers now in force (empty = all neutral).

        feed_N: feed rate of SAG line N, % of the nominal line rate (100 = neutral), lev_feed_min..max_pct;
        p80_um: grind P80 target (0 = off), lev_p80_min..max_um; dose_gt: collector dose (0 = off), lev_dose_min..max_gt.
        A value outside its bounds is clamped; a missing key keeps the lever as it is; None or {} clears all of them.
        """
        st, p = self.state, self.prm
        if not values:
            st.levers = {}
            return {}
        lv = dict(st.levers)
        for key, raw in values.items():
            if key not in self.LEVER_KEYS:
                raise ValueError("unknown lever: %s" % key)
            v = float(raw)
            if not math.isfinite(v):
                raise ValueError("lever %s is not a number" % key)
            if key.startswith("feed_"):
                v = min(max(v, p["lev_feed_min_pct"]), p["lev_feed_max_pct"])
                neutral = abs(v - 100.0) < 1e-9
            elif key == "p80_um":
                v = 0.0 if v <= 0.0 else min(max(v, p["lev_p80_min_um"]), p["lev_p80_max_um"])
                neutral = v == 0.0
            else:
                v = 0.0 if v <= 0.0 else min(max(v, p["lev_dose_min_gt"]), p["lev_dose_max_gt"])
                neutral = v == 0.0
            if neutral:
                lv.pop(key, None)
            else:
                lv[key] = v
        st.levers = lv
        return dict(lv)

    def _lever_feed_sp(self, n: int, bwi: float, ln: LineState) -> float:
        """Feed setpoint of line n from the levers, t/h (0 = none): the nominal line rate (or the rate at which the
        running ball mills grind to the P80 target) times the feed lever."""
        lv, p = self.state.levers, self.prm
        m = lv.get("feed_%d" % n, 100.0) / 100.0
        t80 = lv.get("p80_um", 0.0)
        if t80 <= 0.0 and m == 1.0:
            return 0.0
        base = cm.line_grind_rate_tph(ln.balls, bwi, t80, p) if t80 > 0.0 else p["cal_line_tph"]
        return base * m

    def _lever_flotation(self, lv: dict, p80: float, rec_loss: float, fx: CauseEffects, rough) -> tuple:
        """(recovery loss pp, dose ratio, measured dose, concentrate dilution pp) with the P80 and dose levers.

        P80 lever: total recovery follows lev_p80_pp_10um per 10 um around flot_p80_ref_um in both directions; the part the
        base model already takes for a coarser grind is taken off. Dose lever: ratio = dose / flot_dose_sp_gt times the cause
        ratio; below 1 the under-dose loss of the model, above 1 no gain (RG1) and the concentrate is diluted."""
        p = self.prm
        conc_drop = fx.conc_drop_pp
        ratio, meas = fx.dose_ratio, rough.dose_sp_gt
        if lv.get("p80_um", 0.0) > 0.0 and p80 != NO_VALUE and p80 > 0.0:
            d = (p80 - p["flot_p80_ref_um"]) / 10.0
            baked = p["flot_p80_pp_10um"] * fz._base_stage_share(p) * max(0.0, d)
            rec_loss += p["lev_p80_pp_10um"] * d - baked
        dose = lv.get("dose_gt", 0.0)
        if dose > 0.0:
            lr = dose / p["flot_dose_sp_gt"]
            ratio, meas = fx.dose_ratio * lr, dose
            conc_drop += p["lev_dose_conc_pp"] * max(0.0, lr - 1.0) / 0.4
        return rec_loss, ratio, meas, conc_drop

    def _reagent_tank(self, rough, q: float, dt: float) -> None:
        """Collector day tank of a line: the true dose leaves it, the flowmeter totalizer counts its own
        reading; refilled to full below flot_reag_refill_frac (the delivery is booked). g/t x t/h -> t."""
        p = self.prm
        h = dt / MIN_PER_H
        rough.tank_t -= max(0.0, rough.dose_true_gt) * max(0.0, q) * h / G_PER_T
        rough.dose_t_total += max(0.0, rough.dose_meas_gt) * max(0.0, q) * h / G_PER_T
        cap = p["flot_reag_tank_t"]
        if rough.tank_t < p["flot_reag_refill_frac"] * cap:
            rough.tank_in_t_total += cap - rough.tank_t
            rough.tank_t = cap

    def _water_step(self, flows: list[dict], dt: float, k: int) -> None:
        st, p = self.state, self.prm
        cake = sum(f["cake_tph"] for f in flows)
        moist = (sum(f["cake_tph"] * f["moist_pct"] for f in flows) / cake) if cake > 0 else p["filt_moist_pct"]
        silent = ev.cause_effects(st.causes, 0, st.clock.t_min, p).leak_frac if st.causes else 0.0
        wf = WaterFlows(ore_tph=sum(f["q"] for f in flows), tails_tph=sum(f["tails_tph"] for f in flows),
                        cake_tph=cake, cake_moist_pct=moist,
                        thick_overflow_m3h=sum(ln.thick.overflow_m3h for ln in st.lines),
                        leak_frac=self._leak_frac + silent,
                        winter_frac=p["winter_return_frac"] if self.winter_on else 0.0)
        w = st.water
        w.air_temp_c, w.wind_ms, w.beach_dry_pct = ut.weather(st.clock.t_min, st.seed, self.winter_on,
                                                              self._dust_until != NO_VALUE, p,
                                                              self._icy_until != NO_VALUE)
        w.winter = 1.0 if self.winter_on else 0.0
        rect_trip, crud_cm = oxide.faults_now(st, p, st.clock.t_min) if st.oxf else (False, None)
        oxide.oxide_step(st, self._leach_until != NO_VALUE, dt, p, self.ox_date, rect_trip, crud_cm)   # oxide chain; no effect on the sulphide plant
        ut.water_step(w, wf, dt, p, normal(st.seed, k, "piezo"))
        # totalizers: the intake flowmeter (its noise each step) and the water that leaves the circuit
        w.intake_m3_total += w.intake_m3h * (1.0 + p["sens_flow_sigma"] * normal(st.seed, k, "water-intake-tot")) \
            * dt / MIN_PER_H
        # a leak has no meter: it is not in the loss totalizer, so it shows as the residual of the balance
        w.loss_m3_total += (w.tails_loss_m3h + w.conc_moist_m3h + w.evap_m3h) * dt / MIN_PER_H
        # ore the water allows: cut while the intake is at its cap, give back while there is room
        need = w.demand_m3h
        scale = self._water_scale
        if w.short_m3h > 0.0 and need > 0.0:
            target = scale * (1.0 - w.short_m3h / need)
        elif scale < 1.0 and need > 0.0:
            target = min(1.0, scale * (1.0 + max(0.0, w.intake_cap_m3h - w.intake_m3h) / need))
        else:
            target = scale
        if target != scale:
            scale += (target - scale) * (1.0 - math.exp(-dt / p["water_reg_min"]))
            self._water_scale = 1.0 if scale > WATER_SCALE_FULL else max(0.0, scale)
        running = sum(1 for ln in st.lines if not self._down[ln.n])
        w.cut_tph = (1.0 - self._water_scale) * p["cal_line_tph"] * running
        if st.flags.get("piezo"):
            # safety scenario: the dam piezometer reads above its setpoint
            high = p["pond_piezo_sp_kpa"] + p["scen_piezo_over_kpa"] \
                + p["pond_piezo_noise_kpa"] * normal(st.seed, k, "piezo-scen")
            w.piezo_kpa = max(w.piezo_kpa, high)
            w.state = "ALARM"

    # ================================================== internals: sensors
    def _sensors_step(self, t: float, k: int, flows: list[dict]) -> None:
        st, p = self.state, self.prm
        for ln, f in zip(st.lines, flows):
            n = ln.n
            ph = ln.ph
            ph.reading = p["flot_ph_sp"]                   # the control holds the reading at the setpoint
            idx = int(t // (p["sens_ph_lab_every_h"] * MIN_PER_H))
            if idx != ph.lab_idx:                          # grab sample with a hand-held meter: the real pH
                ph.lab_idx = idx
                ph.lab_ph = p["flot_ph_sp"] + ph.bias + p["sens_ph_lab_sigma"] * normal(st.seed, idx, "ph-lab-%d" % n)
                ph.lab_t_min = t
            if se.analyzer_step(ln.analyzer, ln.flot, n, t, st.seed, k, p) and ln.analyzer.alarm:
                for c in self._unfound(n, ACS_SHOWS, t):
                    self._found(c, t, "acs")
            r = se.lab_step(ln.lab, ln, f["ore"].ascu_pct, t, st.seed, k, p,
                            feed_batch=ln.stockpile.feed_batch if ln.stockpile is not None else "")
            if r is not None:
                b = st.batches.get(r.batch_id)
                if b is not None and r.feed_cu != NO_VALUE and r.feed_cu > 0.0:
                    b.cu_meas = r.feed_cu            # lab feed Cu booked to the batch fed at sampling time
                    b.t_lab_min = t
                for c in self._unfound(n, LAB_SHOWS, t):
                    if self._lab_shows(c, r, ln, f["ore"]):
                        self._found(c, t, "lab")

    def _unfound(self, n: int, kinds: tuple[str, ...], t: float) -> list[HiddenCause]:
        return [c for c in self.state.causes
                if c.line == n and c.kind in kinds and c.t_found_min == NO_VALUE and self._active(c, t)]

    def _lab_shows(self, c: HiddenCause, r: LabResult, ln: LineState, used: OreProps) -> bool:
        """Does a lab result reveal the cause? Tails against the expectation at the lab's own
        feed grade (collector dose), or ASCu against the block-model estimate (oxide)."""
        p = self.prm
        if c.kind == "dose":
            if ln.tph <= 0.0 or r.feed_cu <= 0.0 or r.tail_cu <= 0.0:
                return False
            ref = fz.flotation_steady(ln.tph, OreProps(r.feed_cu, r.ascu_pct, used.axb, used.bwi),
                                      ln.cyclones.p80_um, 1.0, p)
            return ref.tail_cu_pct > 0.0 and r.tail_cu > ref.tail_cu_pct * (1.0 + p["sens_lab_find_frac"])
        if c.kind == "oxide":
            st = self.state
            parts = [(tn, st.batches[b].est) for b, tn in ln.stockpile.column.items()
                     if b in st.batches and tn > 0.0]
            if not parts or r.ascu_pct < 0.0:
                return False
            return r.ascu_pct - ore.blend(parts).ascu_pct > p["sens_lab_find_ascu_pp"]
        return False

    def _found(self, c: HiddenCause, t: float, by: str) -> None:
        """A silent issue is found by the lab or the tails alarm: the crew is called at once."""
        c.t_found_min = t
        c.found_by = by
        issue = "%s:%d" % (c.kind, c.line)
        person = site().DECISION_PERSON.get("found")
        if person:
            pp.assign_duty(self.state, person, ISSUE_NODE.get(c.kind, "flot-{}").format(c.line), t, self.prm)
        if issue not in self._jobs and not self._call_pending(issue):
            self._book(PlannedCall(t, "", "", issue), "lab" if by == "lab" else "alarm")

    # ================================================= internals: counters
    def _count(self, flows: list[dict], dt: float, wet: float, shipped: float) -> None:
        st, p = self.state, self.prm
        h = dt / MIN_PER_H
        pw, w = st.power, st.water
        eff = p["pow_motor_eff"]
        q_sum = sum(f["q"] for f in flows)
        nl = len(flows)
        a = self._acc
        site_part_mw = pw.other_mw - pw.line_aux_mw          # shared equally; the line part goes to its line
        for ln, f in zip(st.lines, flows):
            n = ln.n
            mills_kw = ln.sag.power_kw + sum(b.power_kw for b in ln.balls)
            aux_mw = p["pow_line_aux_mw"] if ln.sag.power_kw > 0.0 else 0.0
            line_mw = mills_kw / KW_PER_MW / eff + (ln.crusher.power_kw + ln.conveyor.power_kw) / KW_PER_MW \
                + site_part_mw / nl + aux_mw
            share = f["q"] / q_sum if q_sum > 0 else 1.0 / nl
            d_cu = f["cu_tph"] * h
            d_e = line_mw * h
            d_w = w.intake_m3h * share * h
            d_usd = ut.value_usd(d_cu, d_e, d_w, p)
            if st.levers.get("dose_gt", 0.0) > 0.0:       # reagent above (below) the setpoint dose costs (saves) money
                d_usd -= (ln.rougher.dose_true_gt - p["flot_dose_sp_gt"]) * f["q"] * h / G_PER_T * p["lev_reagent_usd_t"]
            d_co2 = ut.co2_t(d_e, p)
            vals = (f["q"] * h, f["cu_feed_tph"] * h, d_cu, f["conc_tph"] * h, f["tails_cu_tph"] * h,
                    d_e, d_w, w.recycle_m3h * share * h, d_usd, d_co2, dt)
            for c in (st.line_shift.setdefault(n, Counters()), st.shift, st.total):
                c.ore_t += vals[0]
                c.cu_feed_t += vals[1]
                c.cu_conc_t += vals[2]
                c.conc_t += vals[3]
                c.tails_cu_t += vals[4]
                c.energy_mwh += vals[5]
                c.water_intake_m3 += vals[6]
                c.water_recycle_m3 += vals[7]
                c.usd += vals[8]
                c.co2_t += vals[9]
            ls = st.line_shift[n]
            ls.minutes += dt
            ln.cum_cu_t, ln.cum_mwh, ln.cum_m3, ln.cum_usd = ls.cu_conc_t, ls.energy_mwh, ls.water_intake_m3, ls.usd
            ln.cum_cu_t_total += d_cu                      # run totals, never reset
            ln.cum_mwh_total += d_e
            ln.cum_m3_total += d_w
            ln.cum_usd_total += d_usd
            a["cu_feed"] += vals[1]
            a["cu_conc"] += vals[2]
            a["cu_tails"] += vals[4]
            a["clean_t"] += vals[3]
            a["filt_dry_t"] += f["cake_tph"] * h
        st.shift.minutes += dt
        st.total.minutes += dt
        a["filt_wet_t"] += wet * h
        a["ship_t"] += shipped or 0.0


MODULE_MISSING_MIN = 90.0        # model minutes without an answer of akt-priority: the fact copy of «Два сразу» falls back to the offline order


class CopySet:
    """Scenario copies stepped in lockstep from the same 08:00 snapshot.

    CopySet(prm, seed, text, preset="", kip=None, safety=False, auto=None,
            hooks=None, fact_policy=True):
      base = Plant(mode="scenario") warmed up 06:00 -> 08:00 (hooks on the fact copy only);
      copies "fact" and "base" always; for preset "fork" also "loud" and
      "no_twin" with events.fork_policies; the scenario is applied to every
      copy except "base". kip overrides crew_kip in every copy.
      fact_policy sets who calls for the fact copy of "Two at once" (preset "fork" with auto):
        True / "offline": the fact copy follows fork_policies()["by_value"], the order "by $"
          fixed beforehand (tests, the quick command of the old tables, the fallback);
        False / "module": the dispatcher of the fact copy follows the calls of the module
          akt-priority (auto_call, read from Ditto; Plant.call(src="module")). An alarm alone
          books no crew in this copy (Plant.follow_module); the laboratory call of 14:00
          stays as the net under a silent issue the module does not find. The "loud" copy
          calls the silent issue at the minute the fact copy found it (the module's finding
          time), but after the alarm call of the loud issue: so "detection" and "order" are
          measured against the module's own finding time. If the module is missing,
          fallback_to_offline() hands the fact copy to the offline order (fact_mode "fallback").
      Same seed and step keys -> visible random events (trucks, cloth change)
      equal in all copies.
    """

    def __init__(self, prm: ParamSet | None, seed: int | None, text: str, preset: str = "",
                 kip: int | None = None, safety: bool = False, auto: bool | None = None,
                 hooks: PlantHooks | None = None, fact_policy: bool | str = True):
        prm = default() if prm is None else prm
        fact = Plant(prm, seed, mode="scenario", hooks=hooks)
        fact.warmup()
        spec = ev.parse_scenario(text, fact.t_min, prm, preset=preset, kip=kip, safety=safety, auto=auto)
        fact._set_crew_count("crew-kip", int(spec.kip))
        copies = {"fact": fact, "base": fact.clone()}
        if preset == "fork":
            copies["loud"] = fact.clone()
            copies["no_twin"] = fact.clone()
        for name, c in copies.items():
            if name != "base":
                c.apply_scenario(spec)
        offline = fact_policy is True or fact_policy == "offline"
        self.fact_mode = "alarm"            # alarm: the plain copy (no fork policy); offline | module | fallback
        self.fallback_at = NO_VALUE
        self.t0_min = float(fact.t_min)
        self._by_value: list[PlannedCall] = []
        self._dose_tpl: PlannedCall | None = None      # module mode: the silent call the loud copy gets when the fact copy finds it
        self._trip_call_t = -INF
        self._loud_dose_set = True
        if preset == "fork":
            pol = ev.fork_policies(spec, prm, fact.state.seed)
            copies["loud"].schedule(pol["loud"])
            copies["no_twin"].schedule(pol["no_twin"])
            self._by_value = [copy.copy(c) for c in pol["by_value"]]
            if spec.auto and offline:
                fact.schedule(pol["by_value"])
                self.fact_mode = "offline"
            elif spec.auto:
                self.fact_mode = "module"
                fact.set_follow_module(True)
                lab = [c for c in pol["no_twin"] if parse_issue(c.issue)[0] == "dose"]
                for c in lab:
                    fact.schedule([PlannedCall(c.t_min, c.node, c.crew, c.issue, c.work_h, "lab")])
                dose = [c for c in pol["by_value"] if parse_issue(c.issue)[0] == "dose"]
                trips = [c for c in pol["loud"] if parse_issue(c.issue)[0] == "trip"]
                if dose:
                    # the loud copy: only the alarm call of the trip now; the silent call comes when the module finds it
                    copies["loud"]._calls = [c for c in copies["loud"]._calls if parse_issue(c.issue)[0] != "dose"]
                    self._dose_tpl = dose[0]
                    self._loud_dose_set = False
                if trips:
                    self._trip_call_t = min(c.t_min for c in trips)
        self.prm = prm
        self.copies: dict[str, Plant] = copies
        self.spec: ScenarioSpec = spec
        self.cancelled = False

    copies: dict[str, Plant]
    spec: ScenarioSpec
    lever_only = False          # True: made from a free run by the first lever (no scenario); fact + base only
    fact_mode = "alarm"         # alarm | offline | module | fallback (see __init__)
    fallback_at = NO_VALUE
    t0_min = 0.0
    _by_value: list = []
    _dose_tpl = None
    _trip_call_t = -INF
    _loud_dose_set = True

    @classmethod
    def from_plant(cls, fact: "Plant") -> "CopySet":
        """Fact copy = the running free-run plant, base copy = its clone (same state, no levers): the first lever of a
        free run starts the comparison "base / fact / difference" without a scenario."""
        cs = cls.__new__(cls)
        cs.prm = fact.prm
        cs.copies = {"fact": fact, "base": fact.clone()}
        cs.spec = ev.parse_scenario("", fact.t_min, fact.prm)
        cs.cancelled = False
        cs.lever_only = True
        return cs

    def step(self, dt_min: float | None = None) -> None:
        """Step every copy once."""
        for c in self.copies.values():
            c.step(dt_min)
        if not self._loud_dose_set:
            self._sync_loud()

    def _sync_loud(self) -> None:
        """Module mode: the loud copy calls the silent issue when the fact copy found it (the module's finding
        time), after the alarm call of the loud issue; if the fact copy has not found it, nothing is added
        (the laboratory call of the loud copy is the same as in the no-twin copy, see __init__)."""
        fact, loud = self.copies["fact"], self.copies.get("loud")
        tpl = self._dose_tpl
        if loud is None or tpl is None:
            self._loud_dose_set = True
            return
        kind, n = parse_issue(tpl.issue)
        found = [c.t_found_min for c in fact.state.causes if c.kind == kind and c.line == n and c.t_found_min != NO_VALUE]
        if not found:
            return
        t_call = max(min(found), self._trip_call_t)
        loud.schedule([PlannedCall(t_call, tpl.node, tpl.crew, tpl.issue, tpl.work_h, "plan")])
        self._loud_dose_set = True

    def fallback_to_offline(self) -> bool:
        """The module's output is missing: the fact copy goes back to the order fixed beforehand
        (fork_policies()["by_value"]), the calls not yet booked at the current minute; the alarm panel
        works again. False when nothing changed (not in module mode, or already done)."""
        if self.fact_mode != "module" or self.cancelled:
            return False
        fact = self.copies["fact"]
        t = fact.t_min
        fact.set_follow_module(False)
        booked = {e["issue"] for e in fact.call_log}
        for c in self._by_value:
            if c.issue not in booked and c.issue not in fact._jobs:
                fact.schedule([PlannedCall(max(c.t_min, t), c.node, c.crew, c.issue, c.work_h, "fallback")])
        self.fact_mode = "fallback"
        self.fallback_at = float(t)
        return True

    def policy_report(self) -> dict:
        """Who called for the fact copy of "Two at once": {} outside that scenario.

        {mode: module | fallback | offline, n_calls, n_module, share_module, calls [{t, node, src}],
         order, order_by_value, same_order, fallback_at}. The calls are the bookings for the two
         troubles of the scenario (the silent dose and the loud trip); share_module = n_module / n_calls;
         same_order: the call order of the fact copy equals the order by $ fixed beforehand."""
        if self.spec.preset != "fork" or self.fact_mode == "alarm" or self.cancelled:
            return {}
        fact = self.copies["fact"]
        rows = [e for e in fact.call_log if parse_issue(e["issue"])[0] in ("dose", "trip")]
        rows.sort(key=lambda e: e["t"])
        ref = [c.issue for c in sorted(self._by_value, key=lambda c: c.t_min)]
        order = [e["issue"] for e in rows]
        n_mod = sum(1 for e in rows if e["src"] == "module")
        return {"mode": self.fact_mode, "n_calls": len(rows), "n_module": n_mod,
                "share_module": (n_mod / len(rows)) if rows else NO_VALUE,
                "calls": [{"t": float(e["t"]), "node": e["node"], "src": e["src"]} for e in rows],
                "order": order, "order_by_value": ref,
                "same_order": (1.0 if order == ref[:len(order)] and len(order) > 0 else 0.0) if order else NO_VALUE,
                "fallback_at": float(self.fallback_at)}

    def end_min(self) -> float:
        """Model minute of the auto pause (scen_end_h of the run day)."""
        t = self.copies["fact"].t_min
        end = math.floor((t + EPS) / MIN_PER_DAY) * MIN_PER_DAY + self.prm["scen_end_h"] * MIN_PER_H
        return end if end > t - EPS else end + MIN_PER_DAY

    def run_to_end(self, dt_min: float | None = None) -> dict:
        """Run to scen_end_h (auto pause); returns shift_result()."""
        dt = self.prm["cal_step_live_min"] if dt_min is None else float(dt_min)
        end = self.end_min()
        fact = self.copies["fact"]
        while fact.t_min < end - EPS and fact.state.site_state != "PAUSED":
            self.step(min(dt, end - fact.t_min))
        return self.shift_result()

    def call(self, node: str, crew: str | None = None, issue: str = "", src: str = "button") -> CrewJob | None:
        """Call on the fact copy (button, or src="module" for the auto_call of akt-priority)."""
        return self.copies["fact"].call(node, crew, issue, src=src)

    def cancel(self) -> None:
        """"Cancel": the fact copy becomes a clone of the base copy; scenario removed."""
        old = self.copies["fact"]
        new = self.copies["base"].clone()
        new.hooks = old.hooks
        self.copies["fact"] = new
        self.cancelled = True

    def shift_result(self) -> dict:
        """Counters at now per copy and differences.

        {"t_min", "copies": {name: {cu_t, ore_t, energy_mwh, water_m3, usd}},
         "diff": {name: copy - base for each non-base copy},
         "fork": {"detection_cu_t": loud.cu_t - no_twin.cu_t,
                  "order_cu_t": fact.cu_t - loud.cu_t} (fork only; positive = gain)}.
        Without the fork preset "fork" is an empty dict.
        """
        sums = {name: c.shift_summary() for name, c in self.copies.items()}
        out = {name: {k: float(s[k]) for k in SUMMARY_KEYS} for name, s in sums.items()}
        base = out["base"]
        diff = {name: {k: v[k] - base[k] for k in SUMMARY_KEYS} for name, v in out.items() if name != "base"}
        fork: dict[str, float] = {}
        if "loud" in out and "no_twin" in out:
            fork = {"detection_cu_t": out["loud"]["cu_t"] - out["no_twin"]["cu_t"],
                    "order_cu_t": out["fact"]["cu_t"] - out["loud"]["cu_t"]}
        return {"t_min": float(self.copies["fact"].t_min), "copies": out, "diff": diff, "fork": fork}
