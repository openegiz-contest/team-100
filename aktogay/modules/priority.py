"""akt-priority: the queue of issues. Troubles -> policy.rank -> issue-* and mod-priority.

Design file 17, section 5 "queue of issues"; file 19, section 3 A.

A trouble is a state of a physical thing (STOP, SLOW, UPSET, LIMITED,
RELINE, pebble LIMIT/STOP, fleet SHORT, filter ONE/STOP, thickener and
concentrate stock HIGH/FULL, water ALARM or SHORT, a dam piezometer alarm,
a fire at the HPGR of a pebble circuit), a "loss" status from akt-losses,
or a hard-ore forecast from akt-ore. Decisions without a crew carry their
cost too: blend the hard ore (12 h forecast), what to shed first in a grid
cut (copper per MW), the shortage of return water (copper and m3 of fresh
water). A line whose SAG stands loses its copper once, as the SAG's issue. Each gets a loss rate (t Cu/h, USD/h),
a time to consequence (stock hours left, hours to full; 0 for flotation),
a median repair time, the crew it needs (crew-kip, crew-cpd, crew-mill,
crew-water or none) and the person and role to call, all three from one table (WHO). The pure policy ranks them; this module writes
the advice: every line starts with the analysis (rate, when the losses
start, the cost of a 1 h delay, the crew), the advice is below it.

Advice only: the web shows "Accept / Disagree"; the decision and its reason
go to the journal thing (written by akt-web), which this module reads to
move an issue to CALLED or SNOOZED. No automatic calls unless the stand is
started with auto=1 (then auto_call is written for the first "call now"
issue once).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from . import dispatch as dp
from . import expect as ex
from . import flood
from . import oxide
from . import forecast as fc
from . import lever_advice
from . import readiness as rd
from . import tiers
from . import tiers_t
from .params import ROW, Prm
from .policy import Plan, Ranked, Trouble, first_choice_losses, rank
from .store import NO_VALUE, Store
from .text import ANALOG, ASSUME, EST, LIT, batch_ru, cu_tph, dur, hhmm, hhmm_day, num, signed, usd, usd_h

log = logging.getLogger("priority")

LINES = (1, 2)
# Things of the simulator the tact waits for (barrier on sim_time).
READS = ("site", "pit", "exc-1", "exc-2", "exc-3", "fleet", "crusher-1", "crusher-2", "conveyor-1", "conveyor-2",
         "stockpile-1", "stockpile-2", "line-1", "line-2", "sag-1", "sag-2", "pebble-1", "pebble-2",
         "ball-1a", "ball-1b", "ball-2a", "ball-2b", "cyclones-1", "cyclones-2", "flot-1", "flot-2",
         "rougher-1", "rougher-2", "cleaner-1", "cleaner-2", "thick-1", "thick-2", "filter-1", "filter-2",
         "conc-stock", "water", "power", "crew-kip", "crew-cpd", "crew-mill", "crew-water", "ph-1", "ph-2")
READS_TYPES = ("batch",)
# Read as well, written by other services: the two modules (waited for through processed_sim_time)
# and the interface things (journal decisions, control flags).
READS_EXTRA = ("mod-losses", "mod-ore", "journal", "control")
WAITS_FOR = ("mod-losses", "mod-ore")

# Crews of the stand and the role of the person who leads each (crew thing responsible.person).
CREW_RU = {"crew-kip": "бригада КИПиА", "crew-cpd": "бригада механиков ЦПД",
           "crew-mill": "бригада механиков фабрики", "crew-water": "бригада хвостового хозяйства"}
CREW_LEAD = {"crew-kip": "kip", "crew-cpd": "crusher_mech", "crew-mill": "plant_mech",
             "crew-water": "tailings_engineer"}
# Who answers for each trouble kind: (crew, roles). roles[0] is the person twin who is called (the lead of
# the crew when there is one, CREW_LEAD); the other roles are named with him in the advice. One table for
# the crew line, the person (issue.person) and the role text (issue.responsible) of every issue, so the
# three never disagree. The crews match the simulator (sim/state.CREW_FOR), the decision persons match
# sim/site_*.DECISION_PERSON (tests/test_mod_priority.WhoTest).
WHO: dict[str, tuple[str, tuple[str, ...]]] = {
    "crusher_stop": ("crew-cpd", ("crusher_mech",)),
    "conveyor_stop": ("crew-cpd", ("crusher_mech",)),
    "pit_stop": ("", ("mine_dispatcher", "shift_geologist")),              # no ore from the pit: the stockpile carries the plant
    "lube_trip": ("crew-kip", ("kip",)),                                   # protection sensor and its circuit
    "reline": ("", ("mine_dispatcher", "plant_shift_manager")),            # ore to the line; access to the SAG
    "sag_stop": ("crew-mill", ("plant_mech",)),
    "hpgr_fire": ("", ("power_engineer", "shift_supervisor")),             # de-energise; evacuate
    "pebble_stop": ("crew-mill", ("plant_mech",)),
    "pebble_stop_fire": ("", ("plant_mech",)),                             # repair once the firemen allow it
    "ball_stop": ("crew-mill", ("plant_mech",)),
    "filter_one": ("crew-mill", ("plant_mech", "plant_shift_manager")),
    "filter_stop": ("crew-mill", ("plant_mech", "plant_shift_manager")),
    "thick_high": ("crew-mill", ("plant_mech", "plant_shift_manager")),    # the filter behind the thickener
    "thick_full": ("crew-mill", ("plant_mech", "plant_shift_manager")),
    "cstock_high": ("", ("shift_metallurgist", "plant_shift_manager")),    # shipping
    "cstock_full": ("", ("shift_metallurgist", "plant_shift_manager")),
    "fleet_short": ("", ("mine_dispatcher",)),
    "grid_limited": ("", ("power_engineer",)),
    "dam_alarm": ("", ("tailings_engineer",)),                             # dam piezometer
    "water_short": ("crew-water", ("tailings_engineer",)),                 # return-water pipeline
    # blend: faces and trucks; a new face changes the ore, the metallurgist is told and changes the regime (T5)
    "hard_ore": ("", ("shift_geologist", "mine_dispatcher", "shift_metallurgist")),
    # SAG kWh/t above the ore (overload, coarse feed, liner, harder ore): the metallurgist decides first; the
    # simulator sends the mill mechanics itself when it is the liner (sim/site_*.DECISION_PERSON "liner")
    "loss_sag": ("", ("shift_metallurgist", "plant_mech")),
    "reagent_over": ("crew-kip", ("kip", "shift_metallurgist")),          # collector overdose: flowmeter, pump
    "loss_cyclones": ("crew-mill", ("plant_mech", "shift_metallurgist")),  # clogged cyclone or grind
    "loss_flot": ("crew-kip", ("kip", "shift_metallurgist")),              # collector flowmeter, dose
    "loss_flot_oxide": ("", ("shift_geologist", "shift_metallurgist")),    # oxidised ore: blend; the regime is the metallurgist's
    # people in a ball mill under a work permit and a start command is on (S0): the shift head cancels the start
    "startup_zone": ("", ("plant_shift_manager", "plant_mech")),
    "tailings_dust": ("", ("tailings_engineer",)),                         # dusting beach (ecology S1)
    "grind_coarse": ("", ("shift_metallurgist", "plant_mech")),            # P80 above the norm: feed rate, mill power
    "conc_low": ("", ("shift_metallurgist", "kip")),                       # concentrate Cu below the buyer's norm
    # tier S of 23.10.2026
    "road_winter": ("", ("mine_dispatcher", "mine_shift_head", "road_service")),   # restrict the traffic (S0)
    "driver_fatigue": ("", ("mine_dispatcher", "mine_shift_head")),                # scenario, assumption (S0)
    "roping": ("", ("grinding_operator", "shift_metallurgist")),                   # cyclone roping, ball mill overload
    "sensor_ph": ("crew-kip", ("kip", "shift_metallurgist")),                      # pH electrode: clean, calibrate, check
    "hpgr_uneven": ("crew-mill", ("plant_mech", "grinding_operator")),             # HPGR feed chute, cheek plates, metal
    "crusher_mantle": ("crew-cpd", ("crusher_mech", "plant_shift_manager")),       # planned mantle change
    "oil_contam": ("", ("shift_mechanic", "mine_dispatcher")),                     # hydraulic oil of an excavator
    "exc_down": ("", ("shift_mechanic", "mine_dispatcher")),                       # excavator failed, ore from the others
    "leach_cold": ("", ("shift_metallurgist", "plant_shift_manager")),             # oxide line: cold leaching, cathode below the quarter level
}
# Short name of a trouble kind: tells two issues of one node apart in the order lines
# ("Дробление гали 1 (пожар) → Дробление гали 1 (останов)").
SHORT_RU = {"crusher_stop": "останов", "lube_trip": "защита по маслу", "conveyor_stop": "останов", "pit_stop": "останов",
            "reline": "перефутеровка", "sag_stop": "останов", "hpgr_fire": "пожар", "pebble_stop": "останов",
            "ball_stop": "останов", "filter_one": "один пресс", "filter_stop": "останов",
            "thick_high": "заполняется", "thick_full": "полон", "cstock_high": "заполняется", "cstock_full": "полон",
            "fleet_short": "нехватка самосвалов", "grid_limited": "урезание сети", "dam_alarm": "пьезометр дамбы",
            "water_short": "нехватка воды", "hard_ore": "твёрдая руда", "loss_sag": "перерасход энергии",
            "reagent_over": "перерасход реагента", "startup_zone": "пуск при людях",
            "tailings_dust": "пыление пляжа", "grind_coarse": "крупный помол", "conc_low": "Cu в концентрате ниже нормы",
            "loss_cyclones": "скрытые потери", "loss_flot": "скрытые потери",
            "road_winter": "зимняя дорога", "driver_fatigue": "усталость водителя", "roping": "канатирование",
            "sensor_ph": "pH-метр под подозрением", "hpgr_uneven": "неравномерное питание ВВД",
            "crusher_mantle": "замена брони", "oil_contam": "загрязнение масла", "exc_down": "отказ",
            "leach_cold": "холодное выщелачивание"}
# trouble kind -> card of readiness (checklist and closure shown on the issue card, FEATURES_22 «ОПРЕДЕЛЕНИЕ ГОТОВНОСТИ»)
KIND_READY = {"pit_stop": "pit_stop", "conveyor_stop": "conveyor_stop", "reline": "fc_liner",
              "road_winter": "winter_road", "driver_fatigue": "driver_fatigue", "roping": "cyclone_roping",
              "sensor_ph": "sensor_suspect", "hpgr_uneven": "hpgr_uneven", "crusher_mantle": "crusher_mantle",
              "oil_contam": "oil_contam", "exc_down": "exc_down", "leach_cold": "leach_cold", "hard_ore": "ore_regime",
              "loss_flot_oxide": "ore_regime"}
# tier T of 24.10.2026 (modules/tiers_t.py): eight slow equipment troubles
WHO.update(tiers_t.WHO)
SHORT_RU.update(tiers_t.SHORT_RU)
KIND_READY.update(tiers_t.KIND_READY)
tiers.EVIDENCE.update(tiers_t.EVIDENCE)
STATUS_RU = {"OPEN": "открыта", "CALLED": "позвали", "IN_WORK": "в работе", "RESOLVED": "устранена",
             "SNOOZED": "отложена"}
T_CONSEQ_MAX_H = 48.0     # beyond: "not within the horizon" (a stock that is not falling gives no time)
ACCEPT = ("accept", "call", "принять", "позвать")
DISAGREE = ("disagree", "snooze", "defer", "не согласен", "отложить")
RESOLVE = ("done", "resolve", "resolved", "устранено")
REMIND = ("remind", "next", "напомнить", "позвать следующего")


@dataclass
class Issue:
    key: str                       # trouble id
    name: str                      # issue-N
    seq: int
    status: str = "OPEN"
    created_at: float = NO_VALUE
    snoozed_until: float = NO_VALUE
    decision: str = ""             # last journal decision text
    gone_since: float = NO_VALUE   # model min when the trouble disappeared
    auto_called: bool = False
    crew_seen: bool = False        # the issue's crew was seen travelling to or working at the node
    called_at: float = NO_VALUE    # model min of the call (journal, auto call, or the crew seen on its way)
    eta: float = NO_VALUE          # expected arrival, model min (called_at + travel; after a busy crew frees)
    late_since: float = NO_VALUE   # model min when "not arrived by ETA + esc_after_min" was first seen
    escalation: str = ""           # text of the escalation (empty when none)
    enroute_at: float = NO_VALUE   # model min when the crew was first seen on its way
    onsite_at: float = NO_VALUE    # model min when the crew was first seen at work
    mech: dict = field(default_factory=dict)   # entry of this issue in journal.mech: status told by the called person
    trouble: Trouble | None = None
    ranked: Ranked | None = None


class PriorityModule:
    name = "priority"
    thing = "mod-priority"

    def __init__(self, prm: Prm, store: Store, losses, ore, roles: dict[str, str] | None = None,
                 auto_call: bool = False):
        self.prm = prm
        self.store = store
        self.losses = losses
        self.ore = ore
        self.roles = roles or {}
        self.auto_env = auto_call
        self.tact = prm["tact_priority_min"]
        self.processed = NO_VALUE
        self.issues: dict[str, Issue] = {}
        self.next_seq = 1
        self.journal_seq = -1
        self.call_seq = 0
        self.plan: Plan = Plan()
        self.new_issues: list[Issue] = []
        self.auto_call_value: dict = {}
        self.first_seen: dict[str, float] = {}
        self.pruned: list[str] = []
        self.esc_log: list[dict] = []          # escalations and reminders of this run (shown with the journal)
        self.handover: dict = {}               # last handover sheet (07:30 / 19:30 model time)
        self.handover_slot: int | None = None  # index of the last handover slot seen
        self.decisions: list[dict] = []        # calls of the run against the model's order (shift review)
        self._prev: list[Trouble] = []         # troubles waiting for a call at the previous tact
        self.deviations: list[dict] = []       # deviations (chronicle for the shift report), not queue issues
        self.flood = flood.FloodCounter()      # alarm-like events of the shift against the issues of the queue (feature alarm_flood)

    def reset(self) -> None:
        names = [i.name for i in self.issues.values()]
        self.__init__(self.prm, self.store, self.losses, self.ore, self.roles, self.auto_env)
        self.stale_names = names

    def role(self, key: str) -> str:
        return self.roles.get(key, key)

    # ------------------------------------------------------------------ troubles from states
    def _line_cu(self, n: int) -> float:
        """Cu t/h of a line (measured; base when the line is down)."""
        prm = self.prm
        v = self.store.f(f"line-{n}", "cu_tph")
        base = ex.cu_tph(prm["line_tph_base"], prm["flot_grade_ref_pct"], prm["flot_rec_ref_pct"])
        return v if v != NO_VALUE and v > 0.1 * base else base

    def _stock_hours(self, n: int, inflow_stops: bool = False) -> float:
        """Hours the stockpile of line n feeds the SAG. inflow_stops: the crusher or the belt stands, so
        the inflow ends once the belt has run empty and the stock lasts level / out; the measured
        hours_left still counts the belt's last minutes as inflow (right after a stop it reads "not
        falling") and would put the losses days away."""
        st = self.store
        level = st.f(f"stockpile-{n}", "level_t")
        out = st.f(f"stockpile-{n}", "out_tph")
        if inflow_stops and level != NO_VALUE and out > 0.0:
            return level / out
        h = st.f(f"stockpile-{n}", "hours_left")
        if h != NO_VALUE and h >= 0.0:
            return h
        if level != NO_VALUE and out > 0.0:
            return level / out
        return 0.0

    def _who(self, who: str, node: str) -> tuple[str, str, str]:
        """(crew, role text, person twin) of a WHO entry: "Дежурный КИПиА и металлург смены"."""
        crew, roles = WHO[who]
        names = [self.role(r) for r in roles]
        text = names[0] + "".join(" и " + (x[:1].lower() + x[1:]) for x in names[1:])
        person = self._person_of_role(roles[0]) or (self._person(crew) if crew else "") or self._person(node)
        return crew, text, person

    def _person(self, node: str) -> str:
        """Person twin who answers for the node (attribute responsible.person, without namespace)."""
        s = self.store.get(node)
        r = (s.attrs.get("responsible") if s else None) or {}
        p = str(r.get("person") or "")
        return p.split(":", 1)[1] if ":" in p else p

    def _person_of_role(self, role: str) -> str:
        """Person twin with this role (attribute responsible.role of a person thing), "" when none."""
        for s in self.store.of_type("person"):
            r = s.attrs.get("responsible") or {}
            if r.get("role") == role:
                return s.name
        return ""

    def _tr(self, key, node, kind, rate_cu, t_h, rep_key, t, loud=True, safety="", text="",
            usd_extra_h: float = 0.0, who: str = "", hold: str = "", repair_mult: float = 1.0) -> Trouble:
        """Crew, role and person come from WHO[who or kind].
        usd_extra_h: money lost besides copper (water bought), USD/h; ranked as its copper equivalent.
        hold: the call waits for this (a fire not yet out); said in the advice."""
        prm = self.prm
        det = self.first_seen.setdefault(key, t)
        t_h = min(max(0.0, t_h), T_CONSEQ_MAX_H)
        rate = max(0.0, rate_cu)
        if usd_extra_h > 0.0:
            rate += usd_extra_h / max(1e-9, prm["cu_price_usd_t"] * prm["payable_frac"])
        crew, role, person = self._who(who or kind, node)
        return Trouble(id=key, node=node, kind=kind, safety=safety, rate_cu_tph=rate,
                       rate_usd_h=ex.usd_h(rate, prm), t_conseq_h=t_h,
                       repair_h=prm[rep_key] * repair_mult if rep_key else 0.0, crew=crew, role=role, detected_at=det,
                       loud=loud, text=text, person=person, hold=hold, usd_extra_h=max(0.0, usd_extra_h), rep_key=rep_key)

    def _settling(self, key: str, t: float) -> bool:
        """The trouble is closing now or was closed settle_min minutes ago or less: the lagging detectors are catching up
        (the issue is still listed as open in the tact its signal returned: it is closed after the troubles are collected)."""
        iss = self.issues.get(key)
        if iss is None:
            return False
        if iss.status != "RESOLVED":
            return True
        return iss.gone_since != NO_VALUE and t - iss.gone_since < self.prm["settle_min"]

    def _running(self) -> dict[int, bool]:
        """Lines whose SAG turns: a line in RELINE or STOP loses its copper once, as the SAG's issue."""
        return {n: self.store.s(f"sag-{n}", "state") not in ("RELINE", "STOP") for n in LINES}

    def _grid_text(self, running: dict[int, bool]) -> str:
        """What the automatic shedding already did (power.shed_text), then which load to shed next and
        what each costs: the twin's order by copper per MW, without the loads already shed."""
        prm = self.prm
        st = self.store
        eff = prm["motor_eff"]
        cands = [("other_cat2", "фидер прочей нагрузки кат. 2", prm["shed_feeder_mw"], 0.0)]
        base_cu = ex.cu_tph(prm["line_tph_base"], prm["flot_grade_ref_pct"], prm["flot_rec_ref_pct"])
        for n in LINES:
            if not running[n]:
                continue
            cu = max(self._line_cu(n), base_cu)       # what the line gives with both mills
            sag_kw = st.f(f"sag-{n}", "power_kw")
            sag_kw = sag_kw if sag_kw != NO_VALUE and sag_kw > 0.0 else prm["sag_power_sp_mw"] * 1000.0
            for b in (f"ball-{n}a", f"ball-{n}b"):
                kw = st.f(b, "power_kw")
                kw = kw if kw != NO_VALUE and kw > 0.0 else prm["ball_power_mw"] * 1000.0
                sag_cut = prm["ball_stop_loss_frac"] * sag_kw     # the line rule halves the SAG with one mill
                mw = (kw + sag_cut) / 1000.0 / eff
                cands.append((b, f"шаровая {b.split('-')[1].upper()}", mw, cu * prm["ball_stop_loss_frac"]))
        shed = [x.strip() for x in (st.s("power", "shed_text") or "").split(",") if x.strip()]
        cands = [c for c in cands if c[0] not in shed]          # a load already shed is not advised again
        cands.sort(key=lambda c: (c[3] / max(c[2], 1e-6), -c[2]))
        parts = []
        for i, (_id, name, mw, cu) in enumerate(cands[:4], 1):
            cost = "медь не теряется" if cu <= 0.0 else f"{cu_tph(-cu)} · {usd_h(-ex.usd_h(cu, prm))}"
            parts.append(f"{i}) {name} ≈ {num(mw, 0)} МВт, {cost}")
        names = {"other_cat2": "фидер кат. 2"}
        auto = ", ".join(names.get(x, "шаровая " + x.split("-", 1)[1].upper() if x.startswith("ball-") else x)
                         for x in shed)
        head = "что отключать первым" if not auto else "если лимит снизят ещё, отключать дальше"
        nxt = (f"{head} (дешевле по меди на МВт): " + "; ".join(parts) + f" {EST}" if parts
               else "отключать больше нечего, кроме мельниц SAG")
        return (f"автоматика уже сбросила: {auto}; " if auto else "") + nxt

    def troubles(self, t: float) -> list[Trouble]:
        prm = self.prm
        st = self.store
        out: list[Trouble] = []
        running = self._running()
        for n in LINES:
            cu = self._line_cu(n)
            feed_stops = st.s(f"crusher-{n}", "state") == "STOP" or st.s(f"conveyor-{n}", "state") == "STOP"
            # a line whose SAG stands draws nothing from its stockpile: a crusher stop costs nothing until
            # the SAG runs again (the line's loss is the SAG's issue, not counted twice)
            stock_h = self._stock_hours(n, inflow_stops=feed_stops) if running[n] else T_CONSEQ_MAX_H
            # crusher and conveyor: the stockpile buys time
            cs = st.s(f"crusher-{n}", "state")
            mantle = tiers.crusher_mantle(self, n, stock_h, t) if cs == "STOP" else None
            if mantle is not None:
                out.append(mantle)                         # planned mantle change (C11), not a fault
            elif cs == "STOP":
                lube = st.f(f"crusher-{n}", "lube_kpa")
                trip = lube != NO_VALUE and lube < 0.8 * 250.0
                out.append(self._tr(f"crusher-{n}:stop", f"crusher-{n}", "lube_trip" if trip else "crusher_stop",
                                    cu, stock_h, "rep_lube_trip_h" if trip else "rep_crusher_h", t,
                                    text=("сработала защита по давлению масла: проверить датчик и цепь защиты" if trip
                                          else "дробилка стоит")))
            # a belt that stands because no ore comes (pit stop, full stockpile) is not a belt trouble: when the
            # belt publishes its trip signal (fault) the trouble needs it; older data without it keep the old rule
            belt_fault = st.f(f"conveyor-{n}", "fault")
            if st.s(f"conveyor-{n}", "state") == "STOP" and cs != "STOP" and (belt_fault == NO_VALUE or belt_fault == 1.0):
                out.append(self._tr(f"conveyor-{n}:stop", f"conveyor-{n}", "conveyor_stop", cu, stock_h,
                                    "rep_conveyor_h", t, text="конвейер стоит"))
            # SAG
            ss = st.s(f"sag-{n}", "state")
            sag_down = ss in ("RELINE", "STOP")
            if ss == "RELINE":
                out.append(self._tr(f"sag-{n}:reline", f"sag-{n}", "reline", cu, 0.0, "", t, safety="S0",
                                    text=(f"люди в SAG-{n} — пуск запрещён; плановая потеря линии: руду на склад "
                                          f"линии {n} — пока он не полон")))
            elif ss == "STOP":
                out.append(self._tr(f"sag-{n}:stop", f"sag-{n}", "sag_stop", cu, 0.0, "rep_sag_h", t,
                                    text="мельница стоит"))
            # tier S: cyclone roping, pH sensor, uneven HPGR feed; they own the losses their cause explains
            tier = tiers.line_troubles(self, n, running[n], sag_down, t) + tiers_t.line_troubles(self, n, running[n], sag_down, t)
            tier_ids = {x.id for x in tier}
            out.extend(tier)
            # fire at the HPGR of the pebble circuit (event of 09.08.2026 at concentrator 1): S0 first
            fire = st.f(f"pebble-{n}", "fire") == 1.0
            if fire:
                other = f"; линия {3 - n} работает, её пожар не задевает" if n in LINES else ""
                out.append(self._tr(f"pebble-{n}:fire", f"pebble-{n}", "hpgr_fire", 0.0, 0.0, "", t, safety="S0",
                                    text=(f"пожар на участке ВВД фабрики {n} (как 09.08.2026 во время ППР): вывести "
                                          f"людей (тогда эвакуировали 20 человек), обесточить ВВД, пуск запрещён"
                                          + other)))
            # pebble crusher and ball mills stand because the SAG above them stands: the line loss is
            # already the SAG's issue, so they are not counted again (nothing to repair there)
            if st.s(f"pebble-{n}", "state") == "STOP" and not sag_down and f"pebble-{n}:uneven" not in tier_ids:
                # while the fire is not out nobody repairs the circuit: no crew to call yet
                out.append(self._tr(f"pebble-{n}:stop", f"pebble-{n}", "pebble_stop",
                                    cu * prm["pebble_stop_loss_frac"], 0.0, "rep_pebble_h", t,
                                    who="pebble_stop_fire" if fire else "",
                                    hold="пожарные разрешат ремонт" if fire else "",
                                    text="дробление гали стоит: расход энергии SAG на тонну +6…10 %, т/ч SAG ниже"
                                         + ("; ремонт — после разрешения пожарных" if fire else "")))
            for b in (f"ball-{n}a", f"ball-{n}b"):
                if st.s(b, "state") == "STOP" and st.s("power", "state") != "LIMITED" and not sag_down:
                    out.append(self._tr(f"{b}:stop", b, "ball_stop", cu * prm["ball_stop_loss_frac"], 0.0,
                                        "rep_ball_h", t,
                                        text="шаровая стоит: линия идёт на половине т/ч или с грубым помолом"))
            # thickener and filter: the thickener buys time; once full, the line keeps only the share
            # of its concentrate the filter takes (one press: about 35 of 56 t/h)
            fs = st.s(f"filter-{n}", "state")
            th_h = st.f(f"thick-{n}", "hours_to_full")
            th_state = st.s(f"thick-{n}", "state")
            conc_in = st.f(f"thick-{n}", "feed_tph")
            lim = st.f(f"filter-{n}", "limit_tph")
            short = (max(0.0, 1.0 - lim / conc_in) if (conc_in > 0.0 and lim != NO_VALUE and lim >= 0.0)
                     else 1.0)
            if fs in ("ONE", "STOP") and st.s("conc-stock", "state") != "FULL" and not sag_down and short > 0.0:
                out.append(self._tr(f"filter-{n}:{fs.lower()}", f"filter-{n}", "filter_" + fs.lower(), cu * short,
                                    0.0 if (th_state == "FULL" or fs == "STOP") else
                                    (th_h if th_h >= 0.0 else T_CONSEQ_MAX_H), "rep_filter_h", t,
                                    text=("фильтр: один пресс; когда сгуститель заполнится, линия потеряет "
                                          f"{num(100 * short, 0)} % концентрата" if fs == "ONE" else "фильтр стоит")))
            elif th_state in ("HIGH", "FULL") and not sag_down and short > 0.0:
                # (a high thickener the filter is already drawing down is not an issue: no loss ahead)
                out.append(self._tr(f"thick-{n}:{th_state.lower()}", f"thick-{n}", "thick_" + th_state.lower(),
                                    cu * short, 0.0 if th_state == "FULL" else
                                    (th_h if th_h >= 0.0 else T_CONSEQ_MAX_H), "rep_filter_h", t,
                                    text=("сгуститель концентрата полон: фильтр не принимает весь концентрат"
                                          if th_state == "FULL" else
                                          "сгуститель концентрата заполняется: фильтр не успевает")))
            # losses found by akt-losses (none on a line whose SAG stands: nothing flows there)
            for kind in ("sag", "cyclones", "flot"):
                node = f"{kind}-{n}"
                r = self.losses.results.get(node) if self.losses is not None else None
                if r is None or r.status != "loss" or r.gap_cu_tph <= 0.0 or sag_down:
                    continue
                if kind in ("cyclones", "flot") and (f"cyclones-{n}:rope" in tier_ids
                                                      or self._settling(f"cyclones-{n}:rope", t)):
                    continue                      # roping explains the coarse overflow and the flotation loss behind it
                if kind == "flot" and (f"ph-{n}:suspect" in tier_ids or self._settling(f"ph-{n}:suspect", t)):
                    continue                      # the pH sensor explains the flotation loss (and its lag after the fix)
                rep = {"sag": "rep_decision_h", "cyclones": "rep_cyclone_h", "flot": "rep_dose_h"}[kind]
                who = ""
                if kind == "flot" and "shift_geologist" in r.role_keys:
                    rep, who = "rep_decision_h", "loss_flot_oxide"
                key = f"{node}:loss"
                self.first_seen.setdefault(key, r.detected_at if r.detected_at != NO_VALUE else t)
                rate, extra = r.gap_cu_tph, 0.0
                if kind == "sag":
                    # silent energy overspend: the energy is money in any case, copper only at the power limit
                    extra = max(0.0, r.detail.get("energy_usd_h", 0.0))
                    if not r.detail.get("limited", True):
                        rate = 0.0
                    if extra > 0.0:
                        # the price of the overspend follows the hour (feature 6): night cheaper, evening peak dearer
                        tf = dp.tariff_info(t, prm)
                        extra *= tf["mult"]
                        r_text = r.cause + (f"; цена по тарифу часа (сценарий «что если»): {tf['band_ru']} "
                                            f"×{num(tf['mult'], 2)} {ASSUME}" if dp.zones_on(prm) else "")
                    else:
                        r_text = r.cause
                else:
                    r_text = r.cause
                out.append(self._tr(key, node, "loss_" + kind, rate, 0.0, rep, t, loud=False, text=r_text,
                                    who=who, usd_extra_h=extra))
            # collector overdose found by the tank balance (the flowmeter reads the setpoint)
            g = (getattr(self.losses, "reagent", {}) or {}).get(n) if self.losses is not None else None
            if g and g.get("status") == "loss" and not sag_down:
                out.append(self._tr(f"rougher-{n}:reagent", f"rougher-{n}", "reagent_over", 0.0, 0.0, "rep_dose_h", t,
                                    loud=False, usd_extra_h=g["usd_h"],
                                    text="перерасход реагентов: " + g.get("text", "")))
            out.extend(self._grind_conc_troubles(n, running[n], sag_down, t, out))
        # copper of the running lines only: a line whose SAG stands is already the SAG's issue
        cu_run = sum(self._line_cu(n) for n in LINES if running[n])
        # concentrate stock (shared)
        cs_state = st.s("conc-stock", "state")
        if cs_state in ("HIGH", "FULL") and cu_run > 0.0:
            h = st.f("conc-stock", "hours_to_full")
            out.append(self._tr(f"conc-stock:{cs_state.lower()}", "conc-stock", "cstock_" + cs_state.lower(),
                                cu_run, 0.0 if cs_state == "FULL" else (h if h >= 0.0 else 12.0),
                                "rep_train_h", t, text="склад концентрата: отгрузка не успевает"))
        # fleet short of trucks
        if st.s("fleet", "state") == "SHORT":
            haul = st.f("fleet", "haul_tph")
            need = st.f("site", "tph")
            share = max(0.0, 1.0 - haul / need) if haul != NO_VALUE and need > 0.0 else 0.2
            hours = [self._stock_hours(n) for n in LINES if running[n]]
            out.append(self._tr("fleet:short", "fleet", "fleet_short", share * cu_run,
                                min(hours) if hours else T_CONSEQ_MAX_H, "rep_decision_h", t,
                                text="самосвалов не хватает"))
        # grid restriction: the loss of the running lines against their base, and what to shed first
        if st.s("power", "state") == "LIMITED":
            base_line = ex.cu_tph(prm["line_tph_base"], prm["flot_grade_ref_pct"], prm["flot_rec_ref_pct"])
            base_cu = base_line * sum(1 for n in LINES if running[n])
            now = [st.f(f"line-{n}", "cu_tph") for n in LINES if running[n]]
            now_cu = sum(v for v in now if v != NO_VALUE) if now and all(v != NO_VALUE for v in now) else NO_VALUE
            loss = max(0.0, base_cu - now_cu) if now_cu != NO_VALUE else 0.3 * base_cu
            out.append(self._tr("power:limited", "power", "grid_limited", loss, 0.0, "rep_grid_h", t,
                                text=(f"сеть урезала мощность: лимит {num(st.f('power', 'grid_limit_mw'), 0)} МВт "
                                      f"{ASSUME}; " + self._grid_text(running))))
        # dam safety: the piezometer above its setpoint
        high = [s.name for s in st.of_type("piezometer") if s.run_id == st.run_id and s.f("alarm") == 1.0]
        if st.s("water", "state") == "ALARM" or high:
            what = ", ".join(f"П-{x.split('-')[-1]} {num(st.f(x, 'kpa'), 0)} кПа" for x in sorted(high))
            out.append(self._tr("water:alarm", "water", "dam_alarm", 0.0, 0.0, "", t, safety="S0",
                                text="пьезометр дамбы выше уставки" + (f": {what}" if what else "")))
        # shortage of return water (leak on the return pipeline, low pond, winter): water bought and ore cut
        w_state = st.s("water", "state")
        # no meter on a leak: the module's water balance (residual of intake - losses - pond) names it
        bal = getattr(self.losses, "balances", {}) if self.losses is not None else {}
        leak = max(0.0, bal.get("water_leak_m3h", NO_VALUE) if bal else NO_VALUE)
        cut = max(0.0, st.f("water", "cut_tph"))
        if w_state == "SHORT" or leak > 0.0 or cut > 0.0:
            short = max(0.0, st.f("water", "short_m3h"))
            cap = st.f("water", "intake_cap_m3h")
            cu = ex.cu_tph(cut, prm["flot_grade_ref_pct"], prm["flot_rec_ref_pct"])
            water_usd = leak * prm["water_usd_m3"]
            winter = st.f("water", "winter") == 1.0
            wm = prm["winter_water_mult"] if winter else 1.0
            cu, water_usd = cu * wm, water_usd * wm
            air = st.f("water", "air_temp_c")
            season = ((f"ЗИМА: возврат воды с хвостохранилища снижен (лёд), воздух {num(air, 0)} °C"
                       + (" — риск замерзания труб" if air != NO_VALUE and air <= prm["winter_freeze_air_c"] else "")
                       + f"; цена беды ×{num(wm, 1)}, ремонт дольше ×{num(prm['winter_repair_mult'], 1)}, "
                       f"звать сразу {ASSUME}; ") if winter else "")
            text = (season + ("нехватка оборотной воды: " if (w_state == "SHORT" or cut > 0) else "тихая утечка воды: ")
                    + (f"невязка водного баланса ≈ {num(leak, 0)} м³/ч за 2 ч (забор больше, чем ушло с хвостами, "
                       f"кеком и испарением, при том же пруде) — утечка на водоводе {EST}; " if leak > 0 else "")
                    + (f"свежая вода на пределе {num(cap, 0)} м³/ч, не хватает {num(short, 0)} м³/ч; " if short > 0 else "")
                    + (f"руда урезана на {num(cut, 0)} т/ч ({cu_tph(-cu)} {EST}); " if cut > 0 else "")
                    + (f"лишний забор свежей воды {num(leak, 0)} м³/ч ≈ {usd_h(-water_usd)} {EST}; "
                       "найти и отсечь утечку, перейти на резервную нитку водовода" if leak > 0 else
                       "утечки не видно: проверить насосные оборотной воды и уровень пруда"))
            out.append(self._tr("water:short", "water", "water_short", cu, 0.0, "rep_water_h", t, text=text,
                                usd_extra_h=water_usd,
                                repair_mult=prm["winter_repair_mult"] if winter else 1.0))
        out.extend(self._pit_stop_troubles(t, running))
        out.extend(tiers.pit_troubles(self, t, running))
        out.extend(tiers_t.site_troubles(self, t, running))
        out.extend(oxide.troubles(self, t))
        out.extend(self._safety_troubles(t))
        # hard ore forecast (12 h ahead): a decision of the shift geologist, blend before it reaches the SAG
        if self.ore is not None:
            for n in LINES:
                nh = self.ore.next_hard.get(n)
                if nh is None or nh.tph_at == NO_VALUE:
                    continue
                q_now = st.f(f"sag-{n}", "feed_tph")
                q_now = q_now if q_now > 0.0 else prm["line_tph_base"]
                drop = max(0.0, q_now - nh.tph_at)
                rate = ex.cu_tph(drop, nh.cu, prm["flot_rec_ref_pct"])
                if rate <= 0.0:
                    continue                  # the forecast t/h is not below today's: nothing to decide
                key = f"ore-{n}:{nh.batch}"
                lead = max(0.0, (nh.early - t) / 60.0)
                when = f"через ≈ {dur(lead)} на линию {n} придёт" if lead >= 5.0 / 60.0 else f"на линию {n} уже идёт"
                # the blend is dug in the pit (sim/ore._dig_line): it changes only the part still in the pit
                if nh.state in ("PLANNED", ""):
                    todo = "шихтовать 50/50 с мягкой рудой при выемке, до подачи на склад"
                elif nh.state == "DIG":
                    todo = "шихтовать 50/50 с мягкой рудой остаток партии в забое, до подачи на склад"
                else:
                    todo = ("партия уже вынута из карьера, шихтовка её не изменит: предупредить оператора SAG, "
                            "держать склад линии полным, следующие твёрдые блоки шихтовать при выемке")
                out.append(self._tr(key, "pit", "hard_ore", rate, lead, "rep_decision_h", t,
                                    loud=False, text=(f"руда (прогноз на 12 ч): {when} твёрдая руда — "
                                                      f"{batch_ru(nh.block, nh.batch)} (A×b {num(nh.axb, 0)}): "
                                                      f"SAG {num(q_now, 0)} → ≈ {num(nh.tph_at, 0)} т/ч {EST}; "
                                                      f"что делать: {todo}")))
        # a state without a loss (fleet "short" while the haul still covers the plant, a grid limit the
        # plant stays under) is not an issue: a $0 line would only push real ones down the queue
        return [tr for tr in out if tr.safety or tr.rate_cu_tph > 0.0]

    # ------------------------------------------------------------------ pit stop (chain pit -> stockpile -> SAG)
    def _pit_stop_troubles(self, t: float, running: dict[int, bool]) -> list[Trouble]:
        """Every ore excavator stands: the plant lives on the stockpile (feature 11). One trouble per line whose SAG
        turns; the loss of the line starts when its stock (and the ore still on the way) is gone."""
        st = self.store
        f = fc.stock(st, self.prm, t)
        if not f["pit_stopped"]:
            return []
        out: list[Trouble] = []
        for n in LINES:
            r = f["lines"].get(str(n))
            if r is None or not running[n] or r["hours"] == NO_VALUE:
                continue
            at = hhmm_day(r["run_out_at"], t)
            text = (f"карьер не подаёт руду: все экскаваторы руды стоят; склад линии {n} ({num(r['level_t'], 0)} т) и руда "
                    f"на пути хватят ≈ на {dur(r['hours'])} — SAG-{n} встанет к {at} {EST}. Откатка и лента ещё довезут "
                    f"≈ {num(r['transit_t'], 0)} т. Решение горного диспетчера: срок возобновления выемки, забой на "
                    f"другой экскаватор. По ПЭК рабочий объём склада 163 кт — 2 суток [проект], в модели живая часть "
                    f"{num(self.prm['stock_live_t'] / 1000, 0)} кт {ASSUME}")
            out.append(self._tr(f"pit:stop:{n}", "pit", "pit_stop", self._line_cu(n), r["hours"], "rep_pit_h", t,
                                text=text))
        return out

    # ------------------------------------------------------------------ features 7, 8, 14, 15
    def _grind_conc_troubles(self, n: int, running: bool, sag_down: bool, t: float, so_far: list[Trouble]) -> list[Trouble]:
        """Coarse grind (feature 7) and concentrate Cu below the buyer's norm (feature 8) of line n."""
        prm, st = self.prm, self.store
        out: list[Trouble] = []
        if not running or sag_down:
            return out
        have = {x.id for x in so_far}
        q = st.f(f"sag-{n}", "feed_tph")
        grade = st.mean(f"flot-{n}", "feed_cu", t, prm["window_min"])
        p80 = st.mean(f"cyclones-{n}", "p80_um", t, prm["window_min"])
        one_mill = st.s(f"ball-{n}a", "state") != "RUN" or st.s(f"ball-{n}b", "state") != "RUN"
        if (p80 != NO_VALUE and q > 0.0 and grade > 0.0 and f"cyclones-{n}:loss" not in have and not one_mill
                and f"cyclones-{n}:rope" not in have and not self._settling(f"cyclones-{n}:rope", t)
                and st.s("power", "state") != "LIMITED"):
            excess = p80 - prm["p80_ref_um"]
            if excess > prm["p80_alarm_um"]:
                pp = prm["grind_pp_10um"] * excess / 10.0
                pp_lo, pp_hi = prm["grind_pp_10um_lo"] * excess / 10.0, prm["grind_pp_10um_hi"] * excess / 10.0
                rate = ex.cu_tph(q, grade, pp)
                out.append(self._tr(
                    f"cyclones-{n}:p80", f"cyclones-{n}", "grind_coarse", rate, 0.0, "rep_decision_h", t, loud=False,
                    text=(f"помол крупнее нормы: P80 {num(p80, 0)} мкм при {num(prm['p80_ref_um'], 0)} (вендор); "
                          f"извлечение ниже на ≈ {num(pp, 1)} п.п. ({cu_tph(-rate)}) {EST}, по наклону {ANALOG} Бозшаколь "
                          f"(тот же оператор): диапазон {num(pp_lo, 1)}–{num(pp_hi, 1)} п.п. на {num(excess, 0)} мкм "
                          f"(лаборатория 0,8–1,2 п.п. на 10 мкм, суточные данные фабрики 1,95); в модели стенда наклон "
                          f"{num(prm['flot_p80_pp_10um'], 1)} п.п. на 10 мкм {ASSUME}; что делать: снизить подачу "
                          f"SAG или поднять мощность шаровых, проверить пески циклонов — решает металлург")))
        c = st.mean(f"flot-{n}", "conc_cu", t, prm["conc_window_min"])
        tph = st.f(f"flot-{n}", "conc_tph")
        if c != NO_VALUE and c > 0.0 and tph > 0.0 and c < prm["conc_norm_pct"]:
            deficit = prm["conc_norm_pct"] - c
            usd_h_ = tph * deficit * prm["conc_penalty_usd_dmt_pp"]
            out.append(self._tr(
                f"flot-{n}:conc", f"flot-{n}", "conc_low", 0.0, 0.0, "rep_decision_h", t, loud=False,
                usd_extra_h=usd_h_,
                text=(f"Cu в концентрате {num(c, 1)} % при норме покупателя {num(prm['conc_norm_pct'], 1)} % {ASSUME}: "
                      f"штраф ≈ {usd_h(-usd_h_)} (≈ {num(prm['conc_penalty_usd_dmt_pp'], 0)} $/т сухого за п.п. {ASSUME}); "
                      f"оплата идёт по 96,5 % Cu или по содержанию минус 1 п.п. (вендор); что делать: проверить "
                      f"промывку пены и расход воздуха в перечистке, снизить выход в пенный продукт — металлург")))
        return out

    def _safety_troubles(self, t: float) -> list[Trouble]:
        """S0: people inside a mill under a work permit while a start command is on (feature 14);
        S1 ecology: dusting of the tailings beach (feature 15)."""
        prm, st = self.prm, self.store
        out: list[Trouble] = []
        for p in st.of_type("person"):
            node = p.s("permit")
            if not node or p.s("state") != "WORK" or st.f(node, "start_cmd") != 1.0:
                continue
            ru = self._node_ru(node)
            out.append(self._tr(
                f"{node}:startup", node, "startup_zone", 0.0, 0.0, "", t, safety="S0",
                text=(f"ПУСК ПРИ ЛЮДЯХ: {ru} — {p.attrs.get('name_ru') or p.name} работает внутри по наряду-допуску, "
                      f"а команда на пуск включена; отменить пуск, снять напряжение, плакат «Не включать! Работают люди!» "
                      f"(п. 315 Правил № 348), работа внутри мельницы — п. 63, 326")))
        wind, dry = st.f("water", "wind_ms"), st.f("water", "beach_dry_pct")
        if wind != NO_VALUE and dry != NO_VALUE and wind >= prm["dust_wind_ms"] and dry >= prm["dust_dry_pct"]:
            out.append(self._tr(
                "water:dust", "water", "tailings_dust", 0.0, 0.0, "rep_dust_h", t, safety="S1",
                text=(f"пыление пляжа хвостохранилища: ветер {num(wind, 0)} м/с при сухом пляже {num(dry, 0)} % "
                      f"{ASSUME} (пороги не найдены); экология, ПДК по PM10 — приказ МЗ РК № ДСМ-70 (текст не проверен); "
                      f"что делать: смочить пляж, перенести выпуск пульпы на влажные секции")))
        return out

    def _deviations(self, t: float) -> list[dict]:
        """Deviations: the chronicle for the shift report and the economy page, not queue issues (UI rule 2).
        Grinding media above the norm (feature 9)."""
        prm, st = self.prm, self.store
        out = []
        for n in LINES:
            g = st.mean(f"line-{n}", "balls_gt", t, prm["ball_window_min"])
            q = st.f(f"line-{n}", "tph")
            norm = prm["ball_norm_gt"]
            if g != NO_VALUE and q > 0.0 and g > norm * (1.0 + prm["ball_over_min_frac"]):
                kg_h = (g - norm) / 1000.0 * q
                cost = kg_h * prm["ball_usd_kg"]
                out.append({"kind": "balls", "node": f"line-{n}", "value_gt": g, "norm_gt": norm, "usd_h": cost,
                            "text": (f"Шары, линия {n}: {num(g, 0)} г/т при норме {num(norm, 0)} {ASSUME}; перерасход "
                                     f"≈ {num(kg_h, 0)} кг/ч ≈ {usd_h(-cost)} {EST} — отклонение: в очередь не попадает, "
                                     f"идёт в отчёт смены; проверить загрузку шаров и износ футеровки")})
        # on-stream analyser with old data (T-T6): a blocked sample line; no price of its own, the losses it hides are
        # found by the other nodes and the balances; the age is shown in every card that uses its readings
        for n in LINES:
            a = f"analyzer-{n}"
            age = st.f(a, "age_min")
            if (st.s(a, "state") == "SUSPECT" and age != NO_VALUE and st.s(f"flot-{n}", "state") != "STOP"
                    and age > prm["age_stale_an_cycles"] * prm["an_cycle_min"]):
                out.append({"kind": "analyzer_stale", "node": a, "age_min": age, "usd_h": 0.0,
                            "text": (f"Анализатор {n}: данные старше {num(age, 0)} мин при цикле {num(prm['an_cycle_min'], 0)} мин — "
                                     f"засорение пробоотборной линии? (Metso Metrics: типичная проблема, частот нет {ANALOG}); "
                                     f"хвосты и питание на экране устарели, тревоги АСУ по хвостам слепы — отклонение: в очередь не "
                                     f"попадает, идёт в лист сдачи; позвать дежурного КИПиА: прочистить линию")})
        return out

    # ------------------------------------------------------------------ journal and issues
    def _apply_journal(self, t: float) -> None:
        last = self.store.get("journal")
        if last is None:
            return
        j = last.o("last")
        if not j:
            return
        seq = int(float(j.get("seq", -1))) if isinstance(j.get("seq"), (int, float)) else -1
        if seq <= self.journal_seq:
            return
        self.journal_seq = seq
        issue_name = str(j.get("issue", ""))
        action = str(j.get("action", "")).strip().lower()
        reason = str(j.get("text", ""))
        iss = next((i for i in self.issues.values() if i.name == issue_name), None)
        if iss is None:
            return
        if action in ACCEPT:
            iss.status = "CALLED"
            who = str(j.get("role", "") or (iss.trouble.role if iss.trouble else ""))
            iss.decision = f"совет принят в {hhmm(t)}" + (f", позвали: {who}" if who else "")
            self._called(iss, t)
        elif action in REMIND:
            nxt = action in ("next", "позвать следующего")
            iss.eta = t + (self.prm["q_arrive_hi_min"] if nxt else self.prm["remind_eta_min"])
            iss.late_since = NO_VALUE
            iss.escalation = ""
            iss.decision = (f"позвали следующего в {hhmm(t)}" if nxt else f"напомнили в {hhmm(t)}") + \
                f", ждём к {hhmm(iss.eta)}"
            self.esc_log.append({"t": t, "issue": iss.name, "action": "next" if nxt else "remind",
                                 "text": iss.decision})
        elif action in DISAGREE:
            iss.status = "SNOOZED"
            iss.snoozed_until = t + self.prm["q_snooze_h"] * 60.0
            iss.decision = f"не согласен в {hhmm(t)}: {reason or 'без причины'}"
        elif action in RESOLVE:
            iss.status = "RESOLVED"
            iss.decision = f"устранено в {hhmm(t)}"

    # ------------------------------------------------------------------ status of the called person (screen ?view=mech)
    MECH_RU = {"accepted": "принял", "enroute": "в пути", "onsite": "на месте", "help": "нужна помощь", "done": "готово"}

    def _apply_mech(self) -> None:
        """journal.mech.items[issue-N] = {status, person, run, t, log: [{s, t}]}: what the called person pressed on
        the screen of the mechanic. Only entries of the current run count (issue names restart with a run)."""
        j = self.store.get("journal")
        items = (j.o("mech").get("items") if j is not None else None) or {}
        run = self.store.run_id
        for iss in self.issues.values():
            e = items.get(iss.name) if isinstance(items, dict) else None
            ok = isinstance(e, dict) and (not run or e.get("run") == run)
            iss.mech = e if ok else {}

    def _mech_time(self, iss: Issue, status: str) -> float:
        for rec in iss.mech.get("log") or []:
            if isinstance(rec, dict) and rec.get("s") == status and isinstance(rec.get("t"), (int, float)):
                return float(rec["t"])
        return NO_VALUE

    def _lifecycle(self, iss: Issue) -> dict:
        """Life cycle of the issue (UI rules, item 4): new -> called -> accepted -> on the way -> on site -> resolved.
        «принял / в пути / на месте» come from the called person's screen; where the person pressed nothing, the
        twin's own estimate (the crew seen on its way or at work) stands, marked as such. Fixed shape."""
        steps = []

        def add(key: str, ru: str, t: float, src: str) -> None:
            steps.append({"key": key, "ru": ru, "t": t, "src": src})

        add("new", "новая", iss.created_at, "модель")
        if iss.called_at != NO_VALUE:
            add("called", "позвали", iss.called_at, "журнал")
        t_acc = self._mech_time(iss, "accepted")
        if t_acc != NO_VALUE:
            add("accepted", "принял", t_acc, "механик")
        # the model's own estimate of «в пути» / «на месте» stands only where the person told nothing and it does not
        # precede what the person has already told (the person's word is the record of the human stages)
        told = [float(r["t"]) for r in (iss.mech.get("log") or []) if isinstance(r, dict) and isinstance(r.get("t"), (int, float))]
        last_told = max(told) if told else NO_VALUE
        t_way = self._mech_time(iss, "enroute")
        if t_way != NO_VALUE:
            add("enroute", "в пути", t_way, "механик")
        elif iss.enroute_at != NO_VALUE and (last_told == NO_VALUE or iss.enroute_at >= last_told):
            add("enroute", "в пути", iss.enroute_at, "модель")
        t_site = self._mech_time(iss, "onsite")
        if t_site != NO_VALUE:
            add("onsite", "на месте", t_site, "механик")
        elif iss.onsite_at != NO_VALUE and (last_told == NO_VALUE or iss.onsite_at >= last_told):
            add("onsite", "на месте", iss.onsite_at, "модель")
        t_done = self._mech_time(iss, "done")
        if t_done != NO_VALUE:
            add("done", "готово (по словам)", t_done, "механик")
        if iss.status == "RESOLVED":
            add("resolved", "решена", iss.gone_since, "модель")
        help_on = str(iss.mech.get("status", "")) == "help"
        help_t = float(iss.mech["t"]) if help_on and isinstance(iss.mech.get("t"), (int, float)) else NO_VALUE
        who = iss.trouble.role.split(" и ")[0] if iss.trouble is not None and iss.trouble.role else "вызванный"
        stage = steps[-1]
        parts = [f"{s['ru']}" + (f" {hhmm(s['t'])}" if s["t"] != NO_VALUE else "") + (" (механик)" if s["src"] == "механик" else "")
                 for s in steps[1:]]
        return {"stage": stage["key"], "stage_ru": stage["ru"], "steps": steps,
                "help": 1.0 if help_on else 0.0,
                "help_text": (f"{who} просит помощь (в {hhmm(help_t)}): позвать следующего по цепочке или начальника смены"
                              if help_on else ""),
                "text": " → ".join(parts), "snoozed": 1.0 if iss.status == "SNOOZED" else 0.0}

    # ------------------------------------------------------------------ what the price stands on (card, second level)
    LABEL_RU = {"fact": "факт", "vendor": "вендор", "project": "проект", "analog": "аналог", "assumption": "допущение",
                "calc": "расчёт"}
    WEAKEST = ("assumption", "analog", "project", "vendor", "calc", "fact")     # from the least to the most solid

    def _support(self, what: str, key: str = "", label: str = "") -> dict:
        lab = label or (ROW[key].label if key in ROW else "assumption")
        return {"what": what, "label": self.LABEL_RU[lab], "key": lab}

    def _weakest(self, sup: list[dict]) -> str:
        keys = [s["key"] for s in sup]
        for k in self.WEAKEST:
            if k in keys:
                return k
        return "calc"

    def _cost(self, tr: Trouble, r: Ranked) -> dict:
        """Breakdown of the price of a trouble into copper, energy, reagents and the buyer's penalty (+ water), USD/h,
        and for each part what it stands on (fact / calculation / assumption: the label of every parameter row
        it multiplies). Fixed shape; the parts add up to loss_usd_h."""
        prm = self.prm
        empty = {"usd_h": NO_VALUE, "items": [], "horizon": {"usd": NO_VALUE, "hours": self.plan.horizon_h, "label": "",
                                                              "supports": []}, "weakest": "", "text": ""}
        if tr.safety:
            empty["text"] = "класс безопасности: в деньгах не считается (правило очереди)"
            return empty
        price = prm["cu_price_usd_t"] * prm["payable_frac"]
        extra = tr.usd_extra_h
        cu_usd = max(0.0, tr.rate_usd_h - extra)
        cu_rate = max(0.0, tr.rate_cu_tph - extra / max(1e-9, price))
        kind_extra = {"loss_sag": "energy", "reagent_over": "reagent", "conc_low": "penalty", "water_short": "water"}.get(tr.kind, "")
        sup = {
            "cu": [self._support(f"цена меди LME {num(prm['cu_price_usd_t'], 0)} $/т на 15.10.2026", "cu_price_usd_t"),
                   self._support(f"доля оплаты {num(100 * prm['payable_frac'], 1)} % (по отчётам KAZ Minerals)", "payable_frac"),
                   self._support(f"потеря меди {num(cu_rate, 2)} т/ч по измерениям узла и балансам", label="calc")],
            "energy": [self._support(f"тариф {num(prm['power_usd_mwh'], 0)} $/МВт·ч (16 тг/кВт·ч)", "power_usd_mwh"),
                       self._support("перерасход энергии на тонну по балансу SAG", label="calc"),
                       self._support(f"КПД привода {num(prm['motor_eff'], 2)}", "motor_eff")],
            "reagent": [self._support(f"цена собирателя {num(prm['reagent_usd_kg'], 1)} $/кг", "reagent_usd_kg"),
                        self._support("перерасход по балансу бака реагента", label="calc")],
            "penalty": [self._support(f"норма покупателя {num(prm['conc_norm_pct'], 1)} % Cu", "conc_norm_pct"),
                        self._support(f"штраф {num(prm['conc_penalty_usd_dmt_pp'], 0)} $/т сухого за п.п.", "conc_penalty_usd_dmt_pp"),
                        self._support("Cu в концентрате по анализатору линии", label="calc")],
            "water": [self._support(f"цена свежей воды {num(prm['water_usd_m3'], 2)} $/м³", "water_usd_m3"),
                      self._support("лишний забор по водному балансу за 2 ч", label="calc")],
        }
        title = {"cu": "Медь", "energy": "Энергия", "reagent": "Реагенты", "penalty": "Штраф покупателя", "water": "Вода"}
        usd = {"cu": cu_usd, "energy": 0.0, "reagent": 0.0, "penalty": 0.0, "water": 0.0}
        if kind_extra:
            usd[kind_extra] = extra
        order = ["cu", "energy", "reagent", "penalty"] + (["water"] if usd["water"] > 0.0 else [])
        items = []
        for k in order:
            on = usd[k] >= 0.5                  # below half a dollar an hour a part is not in the price
            s = sup[k] if on else []
            weak = self._weakest(s) if on else ""
            items.append({"key": k, "title": title[k], "usd_h": usd[k], "label": self.LABEL_RU[weak] if weak else "",
                          "weak": weak, "supports": s})
        timing = [self._support(f"ремонт: медиана {num(tr.repair_h, 1)} ч", tr.rep_key) if tr.rep_key
                  else self._support("решение роли, без ремонта", label="assumption"),
                  self._support(f"приезд {num(prm['q_arrive_lo_min'], 0)}–{num(prm['q_arrive_hi_min'], 0)} мин", "q_arrive_hi_min"),
                  self._support(f"цена меди в коридоре LME {num(prm['cu_price_lo_usd_t'] / 1e3, 0)}–{num(prm['cu_price_hi_usd_t'] / 1e3, 0)} тыс. $/т",
                                "cu_price_lo_usd_t")]
        if tr.t_conseq_h > 0.0:
            timing.insert(0, self._support(f"потери начнутся через {dur(tr.t_conseq_h)} (запас склада)", label="calc"))
        weak_all = self._weakest([s for it in items if it["usd_h"] > 0.0 for s in it["supports"]]) if tr.rate_usd_h > 0 else ""
        text = ("цена в час держится на " + ("допущениях" if weak_all == "assumption" else "расчёте" if weak_all in ("calc", "fact")
                else "аналогах и допущениях")) if weak_all else ""
        return {"usd_h": tr.rate_usd_h, "items": items,
                "horizon": {"usd": r.exp_loss_usd, "hours": self.plan.horizon_h, "label": "допущение", "supports": timing},
                "weakest": weak_all, "text": text}

    # ------------------------------------------------------------------ the button «Сдать смену»
    def _alarm_flood(self, t: float) -> dict:
        """Entries of nodes into abnormal states in this shift (flood.ABNORMAL) against the issues the queue made of them."""
        st = self.store
        items = []
        for name, snap in st.things.items():
            if snap.type in flood.ABNORMAL and not st.is_orphan(snap):
                items.append((name, snap.type, snap.s("state"), snap.f("alarm") if snap.type == "piezometer" else None))
        self.flood.observe(t, self._shift_index(t), items)
        return self.flood.summary(t, self._shift_issue_count(t))

    def _shift_issue_count(self, t: float) -> int:
        """Issues the queue made in the shift of t (open and closed)."""
        s0 = self.prm["shift_start_h"] * 60.0 + self._shift_index(t) * self.prm["shift_h"] * 60.0
        return sum(1 for i in self.issues.values() if i.trouble is not None and i.created_at >= s0 - 1e-6)

    @staticmethod
    def flood_text(f: dict) -> str:
        """One line for the shift report and the handover sheet: events -> issues -> one on the main screen."""
        if not f or f.get("events", -1) < 0 or f.get("elapsed_min", -1) < 0:
            return ""
        per = f.get("per_10min", -1)
        return (f"Тревоги за смену: {num(f['events'], 0)} событий-тревог по {num(f['nodes'], 0)} узлам (узел ушёл в ненорму) → "
                f"{num(f['issues'], 0)} бед в очереди → 1 на главном экране"
                + (f"; {num(per, 1)} за 10 мин против ≈ {num(f['isa_per_10min'], 0)} за 10 мин на оператора по ANSI/ISA-18.2 (ориентир {ANALOG})"
                   if per != NO_VALUE else "") + f" {EST}, нижняя граница: числовые пороги не считаны")

    def _handover_btn(self, t: float) -> dict:
        """The button is shown handover_btn_lead_min before the end of the shift (08:00 and 20:00), and only then."""
        prm = self.prm
        s0, sh = prm["shift_start_h"] * 60.0, prm["shift_h"] * 60.0
        end = s0 + (math.floor((t - s0) / sh) + 1) * sh
        lead = prm["handover_btn_lead_min"]
        return {"show": 1.0 if end - t <= lead else 0.0, "from": end - lead, "end": end, "lead_min": lead}

    def _sync_issues(self, troubles: list[Trouble], t: float) -> None:
        active = {tr.id: tr for tr in troubles}
        self.new_issues = []
        for key, tr in active.items():
            iss = self.issues.get(key)
            if iss is None or iss.status == "RESOLVED" and iss.gone_since != NO_VALUE:
                iss = Issue(key, f"issue-{self.next_seq}", self.next_seq, created_at=t)
                self.next_seq += 1
                self.issues[key] = iss
                self.new_issues.append(iss)
            iss.trouble = tr
            iss.gone_since = NO_VALUE
            if iss.status == "SNOOZED" and iss.snoozed_until != NO_VALUE and t >= iss.snoozed_until:
                iss.status = "OPEN"
            on, _free = self._crew_on(tr)
            if on == "TRAVEL" and iss.enroute_at == NO_VALUE:
                iss.enroute_at = t
            if on == "WORK" and iss.onsite_at == NO_VALUE:
                iss.onsite_at = t
            if on:
                iss.crew_seen = True
                if iss.status in ("OPEN", "SNOOZED"):
                    # the crew already goes there (called by the alarm or by phone, past the queue): advising
                    # to call it, or showing it "busy" with its own job, would contradict what people see
                    iss.status = "CALLED"
                    iss.decision = f"бригада уже вызвана мимо очереди (замечено в {hhmm(t)})"
                    self._called(iss, t)
                if on == "WORK":
                    iss.status = "IN_WORK"
            elif iss.crew_seen and iss.status in ("CALLED", "IN_WORK"):
                # the crew has left and the trouble is still there: back to the queue
                iss.status = "OPEN"
                iss.crew_seen = False
                iss.decision = ""
        self.pruned = []
        for key, iss in list(self.issues.items()):
            if key not in active and iss.status != "RESOLVED":
                iss.status = "RESOLVED"
                iss.gone_since = t
                if iss.trouble is not None:
                    # closure (point 7 of the readiness card): the signal is back to normal -> a line in the journal
                    self.esc_log.append({"t": t, "issue": iss.name, "action": "resolved",
                                         "text": f"{self._closed_name(iss)}: устранена в {hhmm(t)} (сигнал вернулся в норму)"})
            elif key not in active and iss.gone_since != NO_VALUE and \
                    t - iss.gone_since >= self.prm["q_issue_keep_h"] * 60.0:
                self.pruned.append(iss.name)          # the thing is deleted; its history stays in InfluxDB
                del self.issues[key]
                self.first_seen.pop(key, None)

    def _closed_name(self, iss: Issue) -> str:
        """Name of a closed trouble for the journal and the sheet: the node and, where two troubles share a node,
        the kind ("Карьер (останов на линию 1)")."""
        tr = iss.trouble
        name = self._node_ru(tr.node)
        short = SHORT_RU.get(tr.kind, "")
        if tr.kind == "pit_stop":
            short += " на линию " + iss.key.rpartition(":")[2]
        return f"{name} ({short})" if short else name

    def _crews(self, t: float) -> dict[str, list[float]]:
        out = {}
        for c in CREW_RU:
            s = self.store.get(c)
            if s is None:
                continue
            free_at = s.f("free_at")
            state = s.s("state")
            out[c] = [free_at if (state in ("TRAVEL", "WORK") and free_at > t) else NO_VALUE]
        return out

    # ------------------------------------------------------------------ escalation
    def _called(self, iss: Issue, t: float) -> None:
        """Remember the call and the expected arrival: travel q_arrive_hi_min, after the crew frees when busy."""
        if iss.called_at != NO_VALUE:
            return
        self._record_decision(iss, t)
        iss.called_at = t
        start = t
        tr = iss.trouble
        s = self.store.get(tr.crew) if (tr is not None and tr.crew) else None
        if s is not None and s.s("state") in ("TRAVEL", "WORK") and tr.node not in str(s.s("task") or ""):
            free = s.f("free_at")
            if free != NO_VALUE and free > t:
                start = free
        iss.eta = start + self.prm["q_arrive_hi_min"]

    def _arrived(self, tr: Trouble) -> bool:
        """The crew works at the node, or (a decision) the person is there."""
        on, _ = self._crew_on(tr)
        if on == "WORK":
            return True
        if not tr.crew and tr.person:
            p = self.store.get(tr.person)
            if p is not None and p.s("state") == "WORK" and p.s("location") == tr.node:
                return True
        return False

    def _escalate(self, t: float) -> None:
        """Not arrived by ETA + esc_after_min: the issue says so and the log records it once."""
        for iss in self.issues.values():
            tr = iss.trouble
            if tr is None or iss.status != "CALLED" or iss.eta == NO_VALUE:
                if iss.status == "IN_WORK" and iss.late_since != NO_VALUE:
                    self.esc_log.append({"t": t, "issue": iss.name, "action": "arrived",
                                         "text": f"прибыли в {hhmm(t)} (ожидали к {hhmm(iss.eta)})"})
                    iss.late_since = NO_VALUE
                iss.escalation = ""
                continue
            if self._arrived(tr):
                iss.escalation = ""
                continue
            if t >= iss.eta + self.prm["esc_after_min"]:
                who = tr.role.split(" и ")[0] if tr.role else "вызванный"
                iss.escalation = (f"не прибыл: {who} ждали к {hhmm(iss.eta)}, прошло больше "
                                  f"{num(self.prm['esc_after_min'], 0)} мин — напомнить или позвать следующего")
                if iss.late_since == NO_VALUE:
                    iss.late_since = t
                    self.esc_log.append({"t": t, "issue": iss.name, "action": "late", "text": iss.escalation})

    # ------------------------------------------------------------------ decisions (feature 3)
    def _tr_ru(self, tr: Trouble) -> str:
        name = self._node_ru(tr.node)
        return f"{name} ({SHORT_RU.get(tr.kind, tr.kind)})" if any(
            o.node == tr.node and o.id != tr.id for o in self._prev) else name

    def _shift_index(self, t: float) -> int:
        h = self.prm["shift_start_h"] * 60.0
        return int((t - h) // (self.prm["shift_h"] * 60.0))

    def _record_decision(self, iss: Issue, t: float) -> None:
        """A call at a fork (two or more troubles waiting for a call): the model's loss over the horizon when this
        one goes first against the best first one, same samples as the queue."""
        tr = iss.trouble
        cand = [x for x in self._prev if x.safety not in ("S0", "S1")]
        if tr is None or tr.safety in ("S0", "S1") or len(cand) < 2 or tr.id not in {c.id for c in cand}:
            return
        loss = first_choice_losses(cand, t, self.prm, self._crews(t), seed=7919 * self.next_seq + int(t))
        if tr.id not in loss:
            return
        best_id = min(loss, key=lambda k: (round(loss[k][0], 6), k))
        mine, best = loss[tr.id], loss[best_id]
        by_id = {c.id: c for c in cand}
        self.decisions.append({
            "t": t, "shift": self._shift_index(t), "issue": iss.name, "called": self._tr_ru(tr),
            "best": self._tr_ru(by_id[best_id]), "same": best_id == tr.id,
            "regret_usd": max(0.0, mine[0] - best[0]), "regret_cu": max(0.0, mine[1] - best[1])})
        del self.decisions[:-40]

    def review_text(self, shift: int) -> str:
        """'What if you had called otherwise?' for one shift: the calls at forks against the model's best first
        call, in t Cu and USD (a model estimate, not a rating of people)."""
        prm = self.prm
        ds = [d for d in self.decisions if d["shift"] == shift]
        head = "А если бы позвали иначе?"
        if not ds:
            return f"{head} Развилок за смену не было: две беды сразу без явного порядка не стояли"
        bad = [d for d in ds if d["regret_usd"] >= prm["review_min_fork_usd"]]
        if not bad:
            return (f"{head} Развилок за смену: {len(ds)}; порядок вызовов совпал с лучшим по модели или отличался "
                    f"меньше чем на {usd(prm['review_min_fork_usd'])}: потерь от порядка нет {EST}")
        lines = [f"{head} Развилок за смену: {len(ds)}, из них порядок хуже лучшего — {len(bad)}."]
        for d in bad:
            lines.append(f"{hhmm(d['t'])} позвали «{d['called']}» первой, по модели лучше «{d['best']}»: потери за "
                         f"{num(prm['q_horizon_h'], 0)} ч больше на ≈ {usd(d['regret_usd'])} / "
                         f"{num(d['regret_cu'], 2)} т Cu {EST}")
        lines.append(f"Итого от порядка вызовов ≈ {usd(sum(d['regret_usd'] for d in bad))} / "
                     f"{num(sum(d['regret_cu'] for d in bad), 2)} т Cu {EST}; это оценка порядка, а не оценка людей")
        return "\n".join(lines)

    # ------------------------------------------------------------------ chain, permit, price of a choice (1, 2, 4)
    def _chain(self, iss: Issue, t: float) -> dict:
        tr = iss.trouble
        started = iss.status in ("CALLED", "IN_WORK") and self._arrived_or_on(tr)
        c = dp.build_chain(self.store, tr.person, tr.node, t, self._node_ru, job_started=started, kind=tr.kind)
        if iss.escalation and c["items"]:
            # not arrived: the next link of the chain, not just 'the next person of the trade'
            idx = next((i for i, it in enumerate(c["items"]) if it["person"] == tr.person), 0)
            nxt = c["items"][idx + 1] if idx + 1 < len(c["items"]) else None
            if nxt is not None:
                c["text"] = (c["text"] + "; " if c["text"] else "") + (
                    f"следующий по цепочке: {nxt['name']} ({'свободен' if nxt['available'] else 'занят'})")
        return c

    def _arrived_or_on(self, tr: Trouble) -> bool:
        return bool(self._crew_on(tr)[0]) or self._arrived(tr)

    def _choice_texts(self, active: list[Trouble], t: float, seed: int) -> dict[str, str]:
        """One crew, two troubles waiting (feature 2): the price of the choice for the two first in each crew."""
        out: dict[str, str] = {}
        by_crew: dict[str, list[Trouble]] = {}
        order = {r.id: r.rank for r in self.plan.order}
        for tr in active:
            if tr.crew and tr.safety not in ("S0", "S1"):
                by_crew.setdefault(tr.crew, []).append(tr)
        for crew, trs in by_crew.items():
            if len(trs) < 2:
                continue
            trs.sort(key=lambda x: order.get(x.id, 99))
            loss = first_choice_losses(active, t, self.prm, self._crews(t), seed)
            a, b = trs[0], trs[1]
            if a.id not in loss or b.id not in loss:
                continue
            lines = {a.node.rpartition("-")[2][:1], b.node.rpartition("-")[2][:1]}
            text = dp.choice_text(self._tr_ru(a), self._tr_ru(b), loss, a.id, b.id, self.prm, self._crew_ru(crew),
                                  two_lines=len(lines) == 2 and all(x.isdigit() for x in lines))
            out[a.id] = out[b.id] = text
        return out

    # ------------------------------------------------------------------ handover
    def _handover_due(self, t: float) -> bool:
        """True once per crossing of 07:30 or 19:30 model time (not at the first tact of a run)."""
        am, pm = self.prm["handover_am_h"] * 60.0, self.prm["handover_pm_h"] * 60.0
        slot = int((t - am) // 1440) + int((t - pm) // 1440)      # marks passed since the model origin
        prev, self.handover_slot = self.handover_slot, slot
        return prev is not None and slot > prev

    def handover_sheet(self, t: float, mark: float | None = None) -> dict:
        """What the shift hands over: open troubles (who was called, ETA), postponed ones with their
        deadline, suspect sensors, the 12 h ore forecast, crews and people."""
        st = self.store
        open_, snoozed = [], []
        for iss in sorted(self.issues.values(), key=lambda i: i.seq):
            tr = iss.trouble
            if tr is None or iss.status == "RESOLVED":
                continue
            name = self._node_ru(tr.node)
            money = "" if tr.safety else (
                f", {usd_h(-tr.rate_usd_h)} {EST}" if tr.t_conseq_h <= 0.0 else
                f", потерь до {hhmm_day(t + tr.t_conseq_h * 60.0, t)} нет, потом {usd_h(-tr.rate_usd_h)} {EST}"
                if tr.t_conseq_h < T_CONSEQ_MAX_H else "")
            if iss.status == "SNOOZED":
                snoozed.append(f"{name}: отложено до {hhmm_day(iss.snoozed_until, t)} ({iss.decision or 'без причины'})"
                               + money)
                continue
            if iss.status in ("CALLED", "IN_WORK"):
                who = iss.decision or f"позвали: {tr.role}"
                eta = (f"; ждём к {hhmm_day(iss.eta, t)}" if iss.status == "CALLED" and iss.eta != NO_VALUE else "")
                state = "в работе" if iss.status == "IN_WORK" else "позвали"
                line = f"{name}: {state} — {who}{eta}" + (f"; {iss.escalation}" if iss.escalation else "") + money
            else:
                r = iss.ranked
                by = (f"; позвать до {hhmm_day(r.call_by_min, t)}" if r is not None and r.call_by_min != NO_VALUE
                      and tr.t_conseq_h < T_CONSEQ_MAX_H and r.level not in ("now", "S0", "S1") else "")
                line = f"{name}: не вызвана — {tr.role}{by}" + money
            (snoozed if iss.status == "SNOOZED" else open_).append(line)
        # closed during this shift (the last 12 h): the sheet says what is done, not only what is open
        shift_min = self.prm["shift_h"] * 60.0
        done = [f"{self._closed_name(i)}: устранена в {hhmm(i.gone_since)}"
                for i in sorted(self.issues.values(), key=lambda i: i.seq)
                if i.trouble is not None and i.status == "RESOLVED" and i.gone_since != NO_VALUE
                and t - i.gone_since <= shift_min]
        sensors = list(getattr(self.losses, "suspect", {}).values()) if self.losses is not None else []
        ore = str(st.s("mod-ore", "fc_text") or "")
        crews = []
        for c in CREW_RU:
            s = st.get(c)
            if s is None:
                continue
            state = s.s("state") or "FREE"
            free = s.f("free_at")
            crews.append(f"{self._crew_ru(c)}: " + ({"FREE": "свободна", "TRAVEL": "в пути", "WORK": "на работе",
                                                     "OFF": "нет на смене"}.get(state, state.lower()))
                         + (f" ({s.s('task')}), освободится в {hhmm_day(free, t)}" if state in ("TRAVEL", "WORK")
                            and free != NO_VALUE and free > t else ""))
        # the shift that takes over: the next shift start after t (08:00 day, 20:00 night)
        m, day0 = t % 1440, self.prm["shift_start_h"] * 60.0
        nxt = "ночную" if day0 <= m < day0 + self.prm["shift_h"] * 60.0 else "дневную"
        # the sheet carries the mark it is for (19:30); a tact that came later says when it was written
        head = f"Сдача смены {hhmm(mark if mark is not None else t)} — в {nxt} смену" +             (f" (записан в {hhmm(t)})" if mark is not None and t - mark >= 1.0 else "")
        body = [head,
                "Открытые беды: " + ("; ".join(open_) if open_ else "нет"),
                "Отложенные: " + ("; ".join(snoozed) if snoozed else "нет"),
                "Приборы под подозрением: " + ("; ".join(sensors) if sensors else "нет"),
                "Руда на 12 ч: " + (ore if ore else "прогноза нет"),
                "Бригады: " + ("; ".join(crews) if crews else "нет данных")]
        devs = [d["text"] for d in self.deviations]
        body.append("Отклонения: " + ("; ".join(devs) if devs else "нет"))
        fl_text = self.flood_text(self.flood.summary(t, self._shift_issue_count(t)))
        if fl_text:
            body.append(fl_text)
        if done:
            body.append("Устранено за смену: " + "; ".join(done))
        review = self.review_text(self._shift_index(mark if mark is not None else t))
        body.append(review)
        if st.f("water", "winter") == 1.0:
            body.append("Зима: возврат воды снижен, беды с водой дороже и срочнее")
        return {"at": t, "title": head, "text": "\n".join(body), "issues": open_, "snoozed": snoozed,
                "sensors": sensors, "ore": ore, "crews": crews, "deviations": devs, "review": review, "done": done}

    NOTIFY = {"hard_ore": "новый забой с твёрдой рудой: металлург смены узнаёт заранее и меняет режим помола и подачи "
                          "(Бозшаколь: извлечение 78,5 → 73,8 % при сложной минералогии, KAZ Minerals, H1 2025 — пример влияния "
                          "минералогии, не потеря от задержки)",
              "loss_flot_oxide": "новый забой с окисленной рудой: металлург смены узнаёт заранее и меняет реагентный режим "
                                 "(Бозшаколь: извлечение 78,5 → 73,8 % при сложной минералогии, KAZ Minerals, H1 2025 — пример "
                                 "влияния минералогии, не потеря от задержки)"}

    def _notify_text(self, tr: Trouble) -> str:
        """Roles told besides the one called: ore changed, the regime must change (T5)."""
        return self.NOTIFY.get(tr.kind, "")

    # ------------------------------------------------------------------ texts
    def _crew_ru(self, crew: str) -> str:
        """'бригада механиков фабрики': the crew thing's name in Ditto, else the table."""
        s = self.store.get(crew)
        name = str((s.attrs.get("name_ru") if s else "") or CREW_RU.get(crew, crew))
        return name[:1].lower() + name[1:]

    def _crew_on(self, tr: Trouble) -> tuple[str, float]:
        """("TRAVEL" | "WORK", free_at) when the trouble's crew goes to or works at its node, else ("", NO_VALUE).
        The crew thing's task is the node of its current job ("," between nodes when several teams work)."""
        s = self.store.get(tr.crew) if tr.crew else None
        if s is None:
            return "", NO_VALUE
        state = s.s("state")
        if state in ("TRAVEL", "WORK") and tr.node in [x.strip() for x in str(s.s("task") or "").split(",")]:
            return state, s.f("free_at")
        return "", NO_VALUE

    def _line_text(self, iss: Issue, r: Ranked, t: float, ranked: bool = True) -> str:
        """One line of the queue: what, the analysis (losses, the price of a delay, the crew), the advice.
        Every model number carries EST; the crew, the person and the role are one WHO entry.
        ranked: False for an issue outside the ranking (called, in work): no place number, no delay price."""
        tr = iss.trouble
        prm = self.prm
        node_ru = self._node_ru(tr.node)
        parts = [(f"{r.rank}. " if ranked else "") + f"{node_ru}: {tr.text}"]
        t_loss = t + max(0.0, tr.t_conseq_h) * 60.0
        waiting = ranked and iss.status in ("OPEN", "SNOOZED")
        if tr.safety:
            if tr.kind == "tailings_dust":
                parts.append("класс S1 (экология) — после людей и до денег, в деньгах не считается")
            else:
                parts.append(f"класс {tr.safety} — впереди всего, в деньгах не считается")
        else:
            rate = f"{cu_tph(-tr.rate_cu_tph)} · {usd_h(-tr.rate_usd_h)} {EST}"
            if tr.t_conseq_h <= 0.0:
                parts.append(f"потери идут: {rate}")
            elif tr.t_conseq_h >= T_CONSEQ_MAX_H:
                parts.append(f"потерь в ближайшие {num(T_CONSEQ_MAX_H, 0)} ч не ожидается (запас не расходуется); "
                             f"если начнутся — {rate}")
            else:
                parts.append(f"потерь до {hhmm_day(t_loss, t)} нет (ещё {dur(tr.t_conseq_h)}), потом {rate}")
            # a delay that costs nothing (the repair still ends before the losses start) is not priced at "$0":
            # the line above already says until when there are no losses
            if waiting and tr.t_conseq_h < T_CONSEQ_MAX_H and r.delay_cost_usd >= 0.5:
                # the policy prices a delay over the LME band, the rate above is at the table price
                band = f"{num(prm['cu_price_lo_usd_t'] / 1e3, 0)}–{num(prm['cu_price_hi_usd_t'] / 1e3, 0)}"
                if tr.t_conseq_h <= 0.0:
                    parts.append(f"отсрочка вызова на 1 ч стоит ≈ {usd(r.delay_cost_usd)} при цене меди "
                                 f"{band} тыс. $/т {EST}")
                else:
                    # losses start later: the delay costs only through the risk that the work ends after that
                    work = "ремонт" if tr.crew else "решение"
                    parts.append(f"час отсрочки вызова — в среднем ≈ {usd(r.delay_cost_usd)}: риск, что {work} "
                                 f"не успеет до {hhmm_day(t_loss, t)} (цена меди {band} тыс. $/т) {EST}")
        crew_ru = self._crew_ru(tr.crew) if tr.crew else ""
        on, free_at = self._crew_on(tr)
        if tr.crew:
            if on == "WORK":
                parts.append(f"{crew_ru} на месте" + (f", освободится в {hhmm_day(free_at, t)}" if free_at > t else ""))
            elif on == "TRAVEL":
                parts.append(f"{crew_ru} в пути")
            elif waiting:
                parts.append(f"{crew_ru} свободна" if r.crew_free_at == NO_VALUE else
                             f"{crew_ru} занята, освободится в {hhmm_day(r.crew_free_at, t)}")
            else:
                s = self.store.get(tr.crew)
                busy_until = s.f("free_at") if s is not None and s.s("state") in ("TRAVEL", "WORK") else NO_VALUE
                if busy_until > t:
                    parts.append(f"{crew_ru} пока на другой работе, освободится в {hhmm_day(busy_until, t)}")
        if iss.status == "IN_WORK":
            advice = "в работе" + (f" ({iss.decision})" if iss.decision else "")
        elif iss.status == "CALLED":
            advice = iss.decision or f"позвали: {tr.role}"
        elif iss.status == "SNOOZED":
            advice = f"отложено до {hhmm_day(iss.snoozed_until, t)} ({iss.decision})"
        elif tr.hold:
            advice = f"Совет: позвать, когда {tr.hold}, — {tr.role}"
        elif r.level in ("S0", "S1"):
            advice = f"Совет: позвать сейчас — {tr.role}"
        elif r.level == "now":
            why = ""
            if 0.0 < tr.t_conseq_h < T_CONSEQ_MAX_H:
                if r.band != ">60":
                    why = "потери начнутся меньше чем через час"
                elif r.p_late_now > prm["q_defer_p_max"]:
                    why = (f"риск не успеть до {hhmm_day(t_loss, t)} даже при вызове сейчас — "
                           f"{num(100 * r.p_late_now, 0)} % {EST}")
                elif r.crew_free_at != NO_VALUE:
                    why = (f"{crew_ru} освободится только в {hhmm_day(r.crew_free_at, t)}: позже вызов "
                           f"не успеет до {hhmm_day(t_loss, t)} {EST}")
                else:
                    why = f"позже {'ремонт' if tr.crew else 'решение'} не успеет до {hhmm_day(t_loss, t)} по P90 {EST}"
            advice = f"Совет: позвать сейчас — {tr.role}" + (f" ({why})" if why else "")
        elif tr.t_conseq_h >= T_CONSEQ_MAX_H:
            # no loss start within the horizon: a "call by" 2 days ahead would invent a time of losses
            advice = f"Совет: срочности нет — позвать в плановом порядке; ответственный — {tr.role}"
        else:
            q90 = max(0.0, (t_loss - r.call_by_min) / 60.0)
            done, work = ("ремонт закончится", "ремонт") if tr.crew else ("решение будет принято", "решение")
            sure = num(100 * (1.0 - prm["q_defer_p_max"]), 0)
            advice = (f"Совет: можно отложить до {hhmm_day(r.call_by_min, t)} — и тогда {done} до начала потерь "
                      f"({hhmm_day(t_loss, t)}) с вероятностью не ниже {sure} % (прибытие и {work}: P90 "
                      f"{dur(q90)}) {EST}; ответственный — {tr.role}")
        parts.append(advice)
        return " · ".join(parts)

    @staticmethod
    def _node_ru(node: str) -> str:
        names = {"sag": "Мельница SAG-{n}", "cyclones": "Гидроциклоны {n}", "flot": "Флотация {n}",
                 "crusher": "Дробилка {n}", "conveyor": "Конвейер {n}", "pebble": "Дробление гали {n}",
                 "ball": "Шаровая {n}", "filter": "Фильтр {n}", "thick": "Сгуститель {n}",
                 "rougher": "Реагенты флотации {n}", "exc": "Экскаватор EX0{n}", "ph": "pH-метр {n}"}
        if node in ("pit", "fleet", "water", "power", "conc-stock"):
            return {"pit": "Карьер", "fleet": "Парк карьера", "water": "Хвосты и вода", "power": "Энергоснабжение",
                    "conc-stock": "Склад концентрата"}[node]
        kind, _, n = node.rpartition("-")
        return names.get(kind, node).format(n=n.upper())

    # ------------------------------------------------------------------ tact
    def compute(self, t: float, seed: int = 0) -> tuple[dict, dict[str, dict]]:
        """One tact; returns (mod-priority features, {issue name: features})."""
        prm = self.prm
        self._apply_journal(t)
        self._apply_mech()
        self.deviations = self._deviations(t)
        troubles = self.troubles(t)
        self._sync_issues(troubles, t)
        self._escalate(t)
        active = [i.trouble for i in self.issues.values() if i.status in ("OPEN", "SNOOZED") and i.trouble]
        self.plan = rank(active, t, prm, self._crews(t), seed=seed * 7919 + int(t))
        by_id = {r.id: r for r in self.plan.order}
        choice = self._choice_texts(active, t, seed * 7919 + int(t) + 1)
        lines = []
        issue_feats: dict[str, dict] = {}
        auto = self.auto_env or bool(self.store.get("control") and
                                     str(self.store.get("control").o("scenario").get("auto", "")).lower() in ("1", "true"))
        self.auto_call_value = {}
        for iss in sorted(self.issues.values(), key=lambda i: (by_id[i.key].rank if i.key in by_id else 999, i.seq)):
            tr = iss.trouble
            if tr is None:
                continue
            r = by_id.get(iss.key)
            ranked = r is not None
            if r is None:
                r = Ranked(iss.key, 99, "now", ">60", 0.0, 0.0, 0.0, 0.0, NO_VALUE, 0.0, 0.0, NO_VALUE)
            iss.ranked = r
            text = self._line_text(iss, r, t, ranked)
            chain = self._chain(iss, t) if iss.status != "RESOLVED" else {"items": [], "text": "", "pick": "", "via": ""}
            if chain["text"] and (iss.status in ("OPEN", "SNOOZED") or iss.escalation):
                text += " · " + chain["text"]
            if iss.status != "RESOLVED":
                lines.append(text)
            if auto and iss.status == "OPEN" and r.level in ("S0", "S1", "now") and not iss.auto_called \
                    and not self.auto_call_value:
                self.call_seq += 1
                iss.auto_called = True
                iss.status = "CALLED"
                self._called(iss, t)
                iss.decision = f"автовызов (auto=1) в {hhmm(t)}, позвали: {tr.role}"
                self.auto_call_value = {"seq": self.call_seq, "issue": iss.name, "role": tr.role, "sim_time": t,
                                        "node": tr.node}
            evi = tiers.evidence(self, tr, t, getattr(self.losses, "suspect", {}) if self.losses is not None else {})                 if iss.status != "RESOLVED" else {"items": [], "n_suspect": 0, "text": ""}
            money = tr.safety != "S0"           # S0 is never counted in money (policy rule 1)
            loss_from = NO_VALUE
            if money and tr.rate_usd_h > 0.0 and tr.t_conseq_h < T_CONSEQ_MAX_H:
                loss_from = t + max(0.0, tr.t_conseq_h) * 60.0
            issue_feats[iss.name] = {
                "status": iss.status, "status_ru": STATUS_RU.get(iss.status, ""), "person": tr.person,
                "node": tr.node, "kind": tr.kind, "safety_class": tr.safety,
                "loss_usd_h": tr.rate_usd_h if money else NO_VALUE, "loss_from": loss_from,
                "loss_shift_usd": r.exp_loss_usd if money else NO_VALUE,
                "delay_cost_usd": r.delay_cost_usd if money else NO_VALUE,
                # no loss start within the horizon: no "call by" either (it would be a made-up time)
                "call_by": r.call_by_min if tr.t_conseq_h < T_CONSEQ_MAX_H else NO_VALUE,
                "rank": float(r.rank), "responsible": tr.role, "text": text,
                "eta": iss.eta if iss.status == "CALLED" else NO_VALUE, "escalation": iss.escalation,
                "chain": {"items": chain["items"], "pick": chain["pick"], "via": chain["via"],
                          "line": chain.get("line", "")},
                "chain_text": chain["text"], "choice_text": choice.get(iss.key, ""),
                "permit_text": chain["text"] if chain["items"] and chain["items"][0].get("permit") else "",
                "checklist": ("Что делать: " + rd.by_id(KIND_READY[tr.kind])["checklist"]) if tr.kind in KIND_READY else "",
                "closure": ("Закроется: " + rd.by_id(KIND_READY[tr.kind])["closure"]) if tr.kind in KIND_READY else "",
                # measurements behind the trouble with the age of each (T3) and the roles told besides the one called (T5)
                "evidence": evi, "evidence_text": evi["text"], "notify_text": self._notify_text(tr),
                "lifecycle": self._lifecycle(iss), "cost": self._cost(tr, r),
                "lever": lever_advice.suggest(tr, prm) if iss.status != "RESOLVED" else dict(lever_advice.EMPTY)}
            if not issue_feats[iss.name]["escalation"] and issue_feats[iss.name]["lifecycle"]["help"]:
                issue_feats[iss.name]["escalation"] = issue_feats[iss.name]["lifecycle"]["help_text"]
        n_active = len(active)
        st_winter = self.store.f("water", "winter") == 1.0
        if n_active == 0:
            # issues already called or in work stay listed: "no troubles" next to them would contradict them
            queue_text = ("\n".join(lines + ["Новых бед нет: остальные беды уже вызваны или в работе"]) if lines
                          else "Бед нет: все узлы работают, потерь сверх шума не найдено")
        else:
            n_money = sum(1 for a in active if a.safety not in ("S0", "S1"))
            share = num(100 * self.plan.robust_share, 0)
            if n_active < 2:
                rob = ("Беда одна: порядок не нужен" if len(lines) <= 1 else
                       "Ждёт решения одна беда, остальные уже вызваны или в работе: порядок не нужен")
            elif n_money == 0:
                rob = "Только безопасность (S0, S1): порядок — по классу и времени, в деньгах не считается"
            elif n_money < 2:
                rob = "Безопасность (S0, S1) впереди, остальная беда одна: выбирать порядок не из чего"
            elif self.plan.order_matters:
                rob = f"Порядок устойчив в {share} % из {self.plan.samples} выборок (прибытие, ремонт, цена) {EST}"
            elif self.plan.robust_share < prm["q_robust_min"]:
                rob = (f"Порядок не важен: устойчивость {share} % < {num(100 * prm['q_robust_min'], 0)} % — "
                       f"звать можно в любом порядке, список — по времени до потерь и деньгам {EST}")
            else:
                rob = (f"Порядок не важен: от выбора первой беды потери меняются меньше чем на $50 или 1 % "
                       f"(бригады разные или запас держит) — звать можно в любом порядке {EST}")
            queue_text = "\n".join(lines + [rob])
        def ru(key: str) -> str:
            """Trouble id -> the node's Russian name (the ids are code: 'crusher-2:stop'); two issues of one
            node get the kind as well ("Дробление гали 1 (пожар)")."""
            iss = self.issues.get(key)
            if iss is None or iss.trouble is None:
                return key
            tr = iss.trouble
            name = self._node_ru(tr.node)
            if any(o is not iss and o.trouble is not None and o.status != "RESOLVED" and o.trouble.node == tr.node
                   for o in self.issues.values()):
                short = SHORT_RU.get(tr.kind, tr.kind)
                if tr.kind == "hard_ore":
                    short += " на линию " + key.split(":", 1)[0].rpartition("-")[2]
                elif tr.kind == "pit_stop":
                    short += " на линию " + key.rpartition(":")[2]
                name += f" ({short})"
            return name

        def t_cu(x: float, sign: bool = False) -> str:
            """t Cu with one decimal, two below 0.1 t (0.04 t is not "0,0")."""
            d = 2 if 0.0 < abs(x) < 0.1 else 1
            return (signed(x, d) if sign else num(x, d)) + " т Cu"

        feats = {
            "queue_text": queue_text,
            "order_text": (f"по $: {' → '.join(ru(by_id[i].id) for i in sorted(by_id, key=lambda k: by_id[k].rank))}; "
                           f"если звать сейчас в этом порядке, потери за 12 ч ≈ {usd(self.plan.loss_value_usd)} / "
                           f"{t_cu(self.plan.loss_value_cu_t)} {EST}"
                           if by_id else ""),
            "alarm_order_text": (f"по громкости: {' → '.join(ru(k) for k in self.plan.alarm_order)}; потери ≈ "
                                 f"{usd(self.plan.loss_alarm_usd)} / {t_cu(self.plan.loss_alarm_cu_t)}; "
                                 f"разница {t_cu(self.plan.gain_cu_t, sign=True)} "
                                 f"({usd(self.plan.gain_usd)}) {EST}" if by_id else ""),
            "auto_call": self.auto_call_value,
            # issue thing -> node and kind: akt-sim turns a call of "issue-N" (journal, auto_call) into a crew
            # booking or a decision at that node
            "issue_map": {i.name: {"node": i.trouble.node, "kind": i.trouble.kind}
                          for i in self.issues.values() if i.trouble is not None and i.status != "RESOLVED"},
            "processed_sim_time": t,
            "resend": NO_VALUE,
            "deviations": {"items": self.deviations},
            "deviations_text": "\n".join(d["text"] for d in self.deviations),
            "review_text": self.review_text(self._shift_index(t)),
            "decisions": {"log": self.decisions[-20:], "shift": self._shift_index(t),
                          "regret_usd": sum(d["regret_usd"] for d in self.decisions
                                            if d["shift"] == self._shift_index(t)),
                          "regret_cu": sum(d["regret_cu"] for d in self.decisions
                                           if d["shift"] == self._shift_index(t))},
            "tariff": {k: v for k, v in dp.tariff_info(t, prm).items() if k != "text"},
            "tariff_text": dp.tariff_info(t, prm)["text"],
            "season_text": ("Зима: возврат воды с хвостохранилища снижен, беды с водой дороже и срочнее"
                            if st_winter else ""),
        }
        # forecasts (features 10, 11, 13): ore on the stockpile if the pit stops, SAG liners, copper to the shift end
        # only what is lost now: a trouble whose loss starts later (the stock still holds) is not in the corridor yet
        loss_open = sum(a.rate_cu_tph for a in active if not a.safety and a.t_conseq_h <= 0.0)
        forecast = fc.build(self.store, prm, t, loss_open)
        feats["forecast"] = forecast
        feats["forecast_text"] = " ".join(x for x in forecast["texts"].values() if x)
        draft = self.handover_sheet(t)
        if self._handover_due(t):
            am, pm = self.prm["handover_am_h"] * 60.0, self.prm["handover_pm_h"] * 60.0
            day = (t // 1440) * 1440
            mark = max(m for m in (day - 1440 + pm, day + am, day + pm) if m <= t)
            self.handover = self.handover_sheet(t, mark)
        # fixed forms (lists are replaced whole by a merge): nothing of an earlier run survives in Ditto
        feats["handover"] = self.handover or {"at": NO_VALUE, "title": "", "text": "", "issues": [], "snoozed": [],
                                              "sensors": [], "ore": "", "crews": [], "deviations": [], "review": "",
                                              "done": []}
        feats["handover_btn"] = self._handover_btn(t)
        feats["alarm_flood"] = self._alarm_flood(t)
        feats["alarm_flood_text"] = self.flood_text(feats["alarm_flood"])
        feats["handover_text"] = self.handover.get("text", "")
        feats["handover_draft_text"] = draft["text"]
        feats["escalations"] = {"log": self.esc_log[-20:]}
        self._prev = list(active)
        self.processed = t
        return feats, issue_feats
