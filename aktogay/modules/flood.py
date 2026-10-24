"""Alarm flood: how many alarm-like events one shift gives against the one trouble the main screen shows.

A conventional control room raises an alarm every time a node goes into an abnormal state, and one root cause drags many nodes
with it (a crusher stop starves the belt, the stockpile falls, the SAG starves, the line is limited, the flotation upsets ...).
This module counts those entries from the published states of the nodes: an event is a node going from a normal state to an
abnormal one (the table ABNORMAL), counted once per entry; a node that stays abnormal is one event, and one that returns and
goes again is two. It is a lower bound of what a plant shows: numeric limits (high and low alarms on t/h, kW, kPa, level) are not
counted, and an entry between two points of the twin (5 model minutes) that is gone by the next point is not seen.

The reference is the figure the submission already uses: about 150 alarms per operator per day (ANSI/ISA-18.2), that is about
one per 10 minutes. The module reads the states from the store of the twin (Ditto), never from the simulator; the trial calls
the same class on the snapshot of the plant, so the stand and the experiment count the same way.

  fc = FloodCounter()
  fc.observe(t_min, shift_index, items)      # items: iterable of (thing name, type, state, alarm flag or None)
  fc.summary(t_min, issues_in_queue)         # dict for the feature `alarm_flood` of mod-priority
"""
from __future__ import annotations

NO_VALUE = -1.0
ISA_PER_DAY = 150.0                     # ANSI/ISA-18.2 orientation used in SUBMISSION (about one alarm per 10 min per operator)
ISA_PER_10MIN = ISA_PER_DAY / 24.0 / 6.0
SHIFT_H = 12.0

# type of a thing -> states a plant would alarm on. Persons, trucks, faces, drills, dozers, roads, batches and crews are not here:
# a state of theirs is a status of work, not an alarm.
ABNORMAL: dict[str, frozenset[str]] = {
    "crusher": frozenset({"STOP", "SLOW"}),
    "conveyor": frozenset({"STOP"}),
    "stockpile": frozenset({"LOW", "EMPTY", "FULL"}),
    "line": frozenset({"LIMITED", "STOP"}),
    "sag": frozenset({"STARVED", "LIMITED_GRID", "RELINE", "STOP"}),
    "ball": frozenset({"STOP"}),
    "pebble": frozenset({"LIMIT", "STOP"}),
    "cyclones": frozenset({"UPSET"}),
    "flot": frozenset({"UPSET", "STOP"}),
    "rougher": frozenset({"UPSET", "STOP"}),
    "cleaner": frozenset({"UPSET", "STOP"}),
    "thick": frozenset({"HIGH", "FULL"}),
    "filter": frozenset({"STOP"}),                      # ONE = a planned change of cloth on one press, not an alarm
    "conc-stock": frozenset({"HIGH", "FULL"}),
    "water": frozenset({"LOW", "SHORT", "ALARM"}),
    "power": frozenset({"LIMITED"}),
    "pit": frozenset({"STOP"}),
    "fleet": frozenset({"SHORT"}),
    "exc": frozenset({"DOWN"}),
    "analyzer": frozenset({"DRIFT", "SUSPECT"}),
    "weigher": frozenset({"DRIFT", "SUSPECT"}),
    "phmeter": frozenset({"DRIFT", "SUSPECT"}),
    "flowmeter": frozenset({"DRIFT", "SUSPECT"}),
    "piezometer": frozenset({"DRIFT", "SUSPECT"}),
}


def abnormal(typ: str, state: str, alarm_flag: float | None = None) -> bool:
    """True when a node of this type in this state would raise an alarm (a piezometer also by its own alarm flag)."""
    if typ == "piezometer" and alarm_flag is not None and alarm_flag >= 1.0:
        return True
    return state in ABNORMAL.get(typ, ())


class FloodCounter:
    """Counts entries into abnormal states within the current shift."""

    def __init__(self) -> None:
        self.shift = None
        self.prev: dict[str, bool] = {}
        self.events = 0
        self.names: dict[str, int] = {}
        self.now = 0
        self.t_shift0 = NO_VALUE
        self.t_seen = NO_VALUE

    def reset(self) -> None:
        """New run: forget everything."""
        self.__init__()

    def observe(self, t: float, shift: int, items) -> None:
        """One look at the nodes at model minute t of shift number `shift`; `items` is (name, type, state, alarm flag or None)."""
        if t < self.t_seen:                       # the clock went back: a new run
            self.reset()
        if shift != self.shift:                   # a new shift: counters restart, nodes that are abnormal keep their state
            self.shift, self.events, self.names, self.t_shift0 = shift, 0, {}, t
        self.t_seen = t
        now = 0
        for name, typ, state, flag in items:
            ab = abnormal(typ, state, flag)
            now += 1 if ab else 0
            was = self.prev.get(name)
            if ab and was is False:
                self.events += 1
                self.names[name] = self.names.get(name, 0) + 1
            self.prev[name] = ab
        self.now = now

    def summary(self, t: float, issues: int) -> dict:
        """The feature value: events of this shift so far against the issues of the queue and the one issue on the main screen."""
        el = t - self.t_shift0 if self.t_shift0 != NO_VALUE else NO_VALUE
        per10 = self.events / (el / 10.0) if el != NO_VALUE and el >= 10.0 else NO_VALUE
        return {"shift": -1 if self.shift is None else int(self.shift), "elapsed_min": el, "events": self.events,
                "nodes": len(self.names), "now": self.now, "issues": int(issues), "main": 1 if issues > 0 else 0,
                "per_10min": per10, "isa_per_10min": ISA_PER_10MIN, "isa_per_shift": ISA_PER_DAY * SHIFT_H / 24.0,
                "label": "оценка на модели, нижняя граница"}
