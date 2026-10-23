"""Ore batches as the modules see them: block-model estimates and positions.

A batch thing (type "batch") carries the estimates in its passport
(est_axb, est_cu, est_ascu, block) and its position in attributes._parents
or the feature "location" (pit, conveyor-N, stockpile-N, line-N). The
modules never see the true ore: they read the estimates, with their error.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .params import Prm
from .store import NO_VALUE, Store, ThingSnap, as_float, passport_value

_LINE_RE = re.compile(r"-(\d)(?:[a-z])?$")
_PLAN_RE = re.compile(r"L(\d)\s*:\s*([^;]*)")
_PLAN_ITEM_RE = re.compile(r"^(\d{1,6})(?:\s+\S+)?$")
NO_PLAN = 10 ** 6


@dataclass
class BatchView:
    name: str
    line: int                  # 1, 2 or 0 (unknown)
    state: str                 # PLANNED | DIG | BELT | IN_STOCK | DONE (by the last tonne of the batch)
    location: str
    block: str
    tonnes_left: float         # not yet fed to the SAG (weigher accounting)
    est_axb: float
    est_cu: float
    est_ascu: float
    axb_soft: float
    cu_meas: float
    number: int                # from the name, for ordering
    pit_t: float = NO_VALUE    # still in the pit (NO_VALUE: the simulator does not say)
    tonnes: float = NO_VALUE   # block size from the passport
    plan_pos: int = NO_PLAN    # position in the dig plan of its line (pit.plan_text), NO_PLAN when not planned


def line_of_thing(name: str) -> int:
    m = _LINE_RE.search(name)
    return int(m.group(1)) if m else 0


def plan_lines(plan_text: str) -> dict[str, int]:
    """'L1: B-1201 B-1203; L2: B-1202' -> {'B-1201': 1, 'B-1203': 1, 'B-1202': 2}."""
    out = {}
    for m in _PLAN_RE.finditer(plan_text or ""):
        for tok in m.group(2).split():
            out[tok.strip(",")] = int(m.group(1))
    return out


def plan_order(plan_text: str) -> dict[str, tuple[int, int]]:
    """Dig order of the simulator's plan text: 'L1: 0012 M, 0013 T; L2: 0011 S' ->
    {'batch-0012': (1, 0), 'batch-0013': (1, 1), 'batch-0011': (2, 0)} (line, position).

    A scenario block is inserted into the plan, so its number is not its place in the queue."""
    out: dict[str, tuple[int, int]] = {}
    for m in _PLAN_RE.finditer(plan_text or ""):
        line = int(m.group(1))
        pos = 0
        for item in m.group(2).split(","):
            im = _PLAN_ITEM_RE.match(item.strip())
            if im:
                out[f"batch-{int(im.group(1)):04d}"] = (line, pos)
                pos += 1
    return out


def batch_view(snap: ThingSnap, prm: Prm, plan: dict[str, int] | None = None,
               order: dict[str, tuple[int, int]] | None = None) -> BatchView:
    attrs = snap.attrs or {}
    location = snap.s("location") or ""
    parent = attrs.get("_parents") or ""
    if isinstance(parent, str) and ":" in parent:
        parent = parent.split(":", 1)[1]
    where = location or parent
    line = line_of_thing(where) if where else 0
    if not line:
        line = int(passport_value(attrs, "line", 0.0)) or 0
    block = ""
    p = attrs.get("passport") if isinstance(attrs.get("passport"), dict) else {}
    for src in (p.get("block"), attrs.get("block")):
        if isinstance(src, dict):
            src = src.get("value")
        elif isinstance(src, (list, tuple)):
            src = src[0] if src else None
        if isinstance(src, str) and src:
            block = src
            break
        if isinstance(src, (int, float)) and not isinstance(src, bool) and src > 0:
            block = f"блок {int(src)}"
            break
    if not line and plan and block in plan:
        line = plan[block]
    pos = NO_PLAN
    if order and snap.name in order:
        ln_o, pos = order[snap.name]
        line = line or ln_o
    m = re.search(r"(\d+)$", snap.name)
    return BatchView(
        name=snap.name, line=line, state=snap.s("state"), location=where, block=block,
        tonnes_left=snap.f("tonnes_left", 0.0),
        est_axb=passport_value(attrs, "est_axb", prm["ore_axb_base"]),
        est_cu=passport_value(attrs, "est_cu", prm["flot_grade_ref_pct"]),
        est_ascu=passport_value(attrs, "est_ascu", prm["flot_ascu_ref_pct"]),
        axb_soft=snap.f("axb_soft"), cu_meas=snap.f("cu_meas"),
        number=int(m.group(1)) if m else 0, pit_t=snap.f("pit_t"),
        tonnes=passport_value(attrs, "tonnes"), plan_pos=pos)


def all_batches(store: Store, prm: Prm) -> list[BatchView]:
    """Batches the simulator still publishes (orphans left by a lost delete are skipped), by number."""
    plan_text = store.s("pit", "plan_text")
    plan = plan_lines(plan_text)
    order = plan_order(plan_text)
    out = [batch_view(s, prm, plan, order) for s in store.live_of_type("batch")]
    return sorted(out, key=lambda b: b.number)


def ore_in_sag(batches: list[BatchView], line: int, prm: Prm) -> tuple[float, float, float, str]:
    """(est A*b, est Cu %, est ASCu %, batch name) of the ore now fed to the SAG of a line.

    The batch with a soft-sensor A*b (the feed batch) wins; else the newest
    batch in that line's stockpile; else the base ore of the block model.
    The first tonnes of a batch reach the SAG while it is still dug (state
    DIG or BELT), so those states count when the soft sensor has seen them.
    """
    mine = [b for b in batches if b.line == line and b.state == "IN_STOCK"]
    fed = [b for b in batches if b.line == line and b.state in ("DIG", "BELT", "IN_STOCK")
           and b.axb_soft != NO_VALUE]
    pick = fed[-1] if fed else (mine[-1] if mine else None)
    if pick is None:
        return prm["ore_axb_base"], prm["flot_grade_ref_pct"], prm["flot_ascu_ref_pct"], ""
    return pick.est_axb, pick.est_cu, pick.est_ascu, pick.name


def est_or(x: float, default: float) -> float:
    return x if as_float(x) != NO_VALUE and x > 0.0 else default
