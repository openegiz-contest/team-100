"""Snapshot store: the latest state of every thing and windows over model time.

Fed by Ditto search results (polling) and, after a start or a run change,
by InfluxDB history. Windows are keyed by sim_time, not wall time, so a
tact gives the same result at any speed (design file 17, section 2).
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

NO_VALUE = -1.0
# A dynamic thing (batch) this many model minutes behind the newest thing of its type is no longer
# published: its delete was lost (a Ditto restart) or it belongs to another run. It must neither hold
# a tact back nor count. The reference is the type's newest thing, not the site: when Ditto lags
# (x300, x1200, a busy cluster) all batches lag the site together and none of them is an orphan.
ORPHAN_LAG_MIN = 30.0


def _value(feature: dict | None):
    if not isinstance(feature, dict):
        return None
    p = feature.get("properties")
    if isinstance(p, dict) and "value" in p:
        return p["value"]
    return None


def as_float(x, default: float = NO_VALUE) -> float:
    """float of a published value; NO_VALUE (or default) for None, strings, NaN, inf."""
    if isinstance(x, bool):
        return 1.0 if x else 0.0
    if isinstance(x, (int, float)):
        v = float(x)
        return v if math.isfinite(v) else default
    return default


def passport_value(attrs: dict, key: str, default: float = NO_VALUE) -> float:
    """Number from attributes.passport[key] in any of the stand's shapes, or attributes[key]."""
    p = attrs.get("passport") if isinstance(attrs, dict) else None
    v = None
    if isinstance(p, dict) and key in p:
        v = p[key]
    elif isinstance(attrs, dict) and key in attrs:
        v = attrs[key]
    if isinstance(v, dict):
        v = v.get("value")
    elif isinstance(v, (list, tuple)):
        v = v[0] if v else None
    return as_float(v, default)


@dataclass
class ThingSnap:
    name: str
    type: str = ""
    attrs: dict = field(default_factory=dict)
    values: dict = field(default_factory=dict)      # feature -> value
    sim_time: float = NO_VALUE
    run_id: str = ""
    revision: int = -1

    def f(self, feature: str, default: float = NO_VALUE) -> float:
        return as_float(self.values.get(feature), default)

    def s(self, feature: str, default: str = "") -> str:
        v = self.values.get(feature)
        return v if isinstance(v, str) else default

    def o(self, feature: str) -> dict:
        v = self.values.get(feature)
        return v if isinstance(v, dict) else {}


class Store:
    """Latest snapshot per thing plus bounded windows of (sim_time, values)."""

    def __init__(self, ns: str = "kz.aktogay", hist_min: float = 120.0):
        self.ns = ns
        self.hist_min = float(hist_min)
        self.things: dict[str, ThingSnap] = {}
        self.history: dict[str, deque] = {}
        self.run_id: str = ""
        self.last_poll_ok = False

    # -- feeding ---------------------------------------------------------------
    def reset(self) -> None:
        """New run: drop the windows and the history of the old run; the latest snapshots stay
        (they already belong to the new run), their windows restart from the current point."""
        self.history.clear()
        for name, snap in self.things.items():
            if snap.run_id != self.run_id:
                snap.sim_time = NO_VALUE          # not yet published in the new run: no point to wait for
            elif snap.sim_time != NO_VALUE:
                self._push(name, snap.sim_time, snap.values)

    def update_from_search(self, items: list[dict]) -> set[str]:
        """Apply a search result; returns names whose sim_time advanced (or appeared).

        The run is the site's. A thing that still carries another run (the old
        run right after a scenario start, a reset or a cancel of the barrier)
        keeps sim_time NO_VALUE until the simulator republishes it in this run:
        its old sim_time would otherwise become the point the modules wait for
        (an old run at 10:15 held the new run at 08:00 back for 2 model hours).
        """
        changed: set[str] = set()
        seen: set[str] = set()
        site_run = next((_value((it.get("features") or {}).get("idSimulationRun")) for it in items
                         if it.get("thingId") == f"{self.ns}:site"), None)
        if isinstance(site_run, str) and site_run:
            self.run_id = site_run
        for it in items:
            tid = it.get("thingId", "")
            if not tid.startswith(self.ns + ":"):
                continue
            name = tid[len(self.ns) + 1:]
            seen.add(name)
            attrs = it.get("attributes") or {}
            feats = it.get("features") or {}
            values = {k: _value(v) for k, v in feats.items()}
            snap = self.things.get(name)
            if snap is None:
                snap = ThingSnap(name)
                self.things[name] = snap
            snap.attrs = attrs
            snap.type = attrs.get("type") or _type_of(name)
            snap.values = values
            t = as_float(values.get("sim_time"))
            run = values.get("idSimulationRun")
            prev_run = snap.run_id
            snap.run_id = run if isinstance(run, str) else ""
            if self.run_id and snap.run_id != self.run_id:
                snap.sim_time = NO_VALUE          # not (yet) published in the site's run
                continue
            if t != NO_VALUE and (snap.sim_time == NO_VALUE or t > snap.sim_time or snap.run_id != prev_run):
                snap.sim_time = t
                changed.add(name)
                self._push(name, t, values)
            elif t != NO_VALUE and t == snap.sim_time:
                # same sim_time, newer values (e.g. a re-sent point): keep the latest
                h = self.history.get(name)
                if h and h[-1][0] == t:
                    h[-1] = (t, dict(values))
        # dynamic things (batches, issues) that disappeared
        for name in [n for n in self.things if n not in seen and _type_of(n) in ("batch", "issue")]:
            del self.things[name]
            self.history.pop(name, None)
        site = self.things.get("site")
        if site is not None and site.run_id:
            self.run_id = site.run_id
        return changed

    def _push(self, name: str, t: float, values: dict) -> None:
        h = self.history.get(name)
        if h is None:
            h = deque()
            self.history[name] = h
        if h and h[-1][0] >= t:
            while h and h[-1][0] >= t:
                h.pop()
        h.append((t, dict(values)))
        while h and h[0][0] < t - self.hist_min:
            h.popleft()

    def add_history_rows(self, rows: list[dict]) -> int:
        """Backfill from Influx history rows (value_<f>_properties_value keys); returns points added."""
        n = 0
        by_thing: dict[str, list[tuple[float, dict]]] = {}
        for r in rows:
            tid = r.get("thingId", "")
            if not tid.startswith(self.ns + ":"):
                continue
            name = tid[len(self.ns) + 1:]
            t = as_float(r.get("value_sim_time_properties_value"))
            if t == NO_VALUE:
                continue
            vals = {}
            for k, v in r.items():
                if k.startswith("value_") and k.endswith("_properties_value"):
                    vals[k[len("value_"):-len("_properties_value")]] = v
            by_thing.setdefault(name, []).append((t, vals))
        for name, pts in by_thing.items():
            h = self.history.get(name)
            existing = {p[0] for p in h} if h else set()
            merged = list(h) if h else []
            for t, vals in pts:
                if t in existing:
                    continue
                merged.append((t, vals))
                n += 1
            merged.sort(key=lambda p: p[0])
            d = deque(merged)
            tmax = d[-1][0] if d else NO_VALUE
            while d and tmax != NO_VALUE and d[0][0] < tmax - self.hist_min:
                d.popleft()
            self.history[name] = d
        return n

    # -- queries ---------------------------------------------------------------
    def get(self, name: str) -> ThingSnap | None:
        return self.things.get(name)

    def sim_time(self, name: str) -> float:
        s = self.things.get(name)
        return s.sim_time if s else NO_VALUE

    def f(self, name: str, feature: str, default: float = NO_VALUE) -> float:
        s = self.things.get(name)
        return s.f(feature, default) if s else default

    def s(self, name: str, feature: str, default: str = "") -> str:
        s = self.things.get(name)
        return s.s(feature, default) if s else default

    def of_type(self, typ: str) -> list[ThingSnap]:
        return [s for s in self.things.values() if s.type == typ]

    def newest(self, typ: str) -> float:
        ts = [s.sim_time for s in self.of_type(typ) if s.sim_time != NO_VALUE]
        return max(ts) if ts else NO_VALUE

    def is_orphan(self, snap: ThingSnap) -> bool:
        """A dynamic thing the simulator no longer publishes: other run (sim_time NO_VALUE), or
        ORPHAN_LAG_MIN behind the newest thing of its type."""
        if snap.sim_time == NO_VALUE:
            return True
        ref = self.newest(snap.type)
        return ref != NO_VALUE and snap.sim_time < ref - ORPHAN_LAG_MIN

    def live_of_type(self, typ: str) -> list[ThingSnap]:
        """of_type without orphans (see is_orphan)."""
        return [s for s in self.of_type(typ) if not self.is_orphan(s)]

    def max_sim_time(self, names) -> float:
        ts = [self.sim_time(n) for n in names]
        ts = [t for t in ts if t != NO_VALUE]
        return max(ts) if ts else NO_VALUE

    def min_sim_time(self, names) -> float:
        ts = [self.sim_time(n) for n in names]
        if not ts or any(t == NO_VALUE for t in ts):
            return NO_VALUE
        return min(ts)

    def window(self, name: str, feature: str, t_to: float, span_min: float) -> list[tuple[float, float]]:
        """(sim_time, value) points of a numeric feature in (t_to - span, t_to], NO_VALUE points skipped."""
        h = self.history.get(name)
        if not h:
            return []
        out = []
        for t, vals in h:
            if t_to - span_min < t <= t_to:
                v = as_float(vals.get(feature))
                if v != NO_VALUE:
                    out.append((t, v))
        return out

    def mean(self, name: str, feature: str, t_to: float, span_min: float, default: float = NO_VALUE) -> float:
        pts = self.window(name, feature, t_to, span_min)
        if not pts:
            v = self.f(name, feature)
            return v if v != NO_VALUE else default
        return sum(v for _, v in pts) / len(pts)

    def median(self, name: str, feature: str, t_to: float, span_min: float, default: float = NO_VALUE) -> float:
        pts = sorted(v for _, v in self.window(name, feature, t_to, span_min))
        if not pts:
            v = self.f(name, feature)
            return v if v != NO_VALUE else default
        n = len(pts)
        return pts[n // 2] if n % 2 else 0.5 * (pts[n // 2 - 1] + pts[n // 2])

    def value_at(self, name: str, feature: str, t: float, default: float = NO_VALUE) -> float:
        """Value at the last point with sim_time <= t."""
        h = self.history.get(name)
        if not h:
            return self.f(name, feature, default)
        best = None
        for tt, vals in h:
            if tt <= t:
                best = vals
            else:
                break
        if best is None:
            return default
        v = as_float(best.get(feature))
        return v if v != NO_VALUE else default


def _type_of(name: str) -> str:
    """Type by name convention: batch-0001 -> batch, issue-3 -> issue, sag-1 -> sag, ball-1a -> ball."""
    if name in ("site", "pit", "fleet", "water", "power", "control", "journal", "baseline", "conc-stock"):
        return name
    if name.startswith(("mod-", "validation-")):
        return name
    if name.startswith("crew-"):
        return "crew"
    return name.rsplit("-", 1)[0]
