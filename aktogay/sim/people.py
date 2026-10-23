"""People of the shift as twins: state FREE / TRAVEL / WORK / OFF, location, free time.

A person with a crew (state.PersonState.crew) is the first team of that crew:
the crew books jobs (events.crew_call) and the person shows them (TRAVEL to
the node, WORK at it, free at the end of the job). A person without a crew
(metallurgist, power engineer, geologist, dispatcher) is busy when a decision
is called to him (Plant.call for grid, blend, fire, road; a hidden cause found
by the laboratory goes to the metallurgist): WORK at the node for
crew_person_decision_h. The water technologist leads crew-water and is also
sent to a water call as a decision (DECISION_PERSON). OFF while evacuated (scenario
hpgr_fire) until off_until_min. Free people stand at their home node.

Pure bookkeeping: nothing here changes the plant physics or the random draws.
"""
from __future__ import annotations

from .params import ParamSet
from .state import MIN_PER_H, NO_VALUE, PlantState

_EPS = 1e-6


def people_step(st: PlantState, t_min: float) -> None:
    """State, location, task and free time of every person at t_min (after the crews step)."""
    for p in st.people.values():
        if p.off_until_min != NO_VALUE:
            if t_min < p.off_until_min - _EPS:
                p.state, p.location, p.task, p.free_at_min = "OFF", "site", "", p.off_until_min
                continue
            p.off_until_min = NO_VALUE
        crew = st.crews.get(p.crew) if p.crew else None
        if crew is not None and crew.state in ("WORK", "TRAVEL"):
            node = crew.task.split(",")[0] if crew.task else ""
            p.state, p.task, p.location = crew.state, node, node
            slot = crew.slot_free_min[0] if crew.slot_free_min else NO_VALUE
            p.free_at_min = slot if slot != NO_VALUE and slot > t_min else crew.free_at_min
            continue
        if p.duty_until_min != NO_VALUE and t_min < p.duty_until_min - _EPS:
            p.state, p.task, p.location, p.free_at_min = "WORK", p.duty_node, p.duty_node, p.duty_until_min
            continue
        p.duty_node, p.duty_until_min = "", NO_VALUE
        p.state, p.task, p.location, p.free_at_min = "FREE", "", p.home, NO_VALUE


def assign_duty(st: PlantState, person: str, node: str, t_min: float, prm: ParamSet,
                hours: float | None = None) -> bool:
    """A decision called to `person`: busy at `node` from t_min for hours (default crew_person_decision_h)."""
    p = st.people.get(person)
    if p is None:
        return False
    h = prm["crew_person_decision_h"] if hours is None else float(hours)
    until = t_min + max(0.0, h) * MIN_PER_H
    if p.duty_until_min == NO_VALUE or until > p.duty_until_min:
        p.duty_until_min = until
    p.duty_node = node
    return True


def evacuate(st: PlantState, people: list[str], until_min: float) -> list[str]:
    """People leave the area (state OFF) until until_min; returns those who were on the roster."""
    out = []
    for name in people:
        p = st.people.get(name)
        if p is not None:
            p.off_until_min = max(p.off_until_min, float(until_min)) if p.off_until_min != NO_VALUE \
                else float(until_min)
            out.append(name)
    return out
