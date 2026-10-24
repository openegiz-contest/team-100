"""Telemetry publisher: feature snapshots -> MQTT -> Ditto (design sections 2 and 3).

One message per thing: a Ditto protocol command on /features with ALL
features of the thing, published to telemetry/<namespace>/<name>. The
platform source connection reads telemetry/#; Ditto applies the command and
its twin event goes on to Telegraf and InfluxDB (fields
value_<feature>_properties_value and value_<feature>_properties_unit).

- Feature list, value type and unit come from setup/things.json (the same
  file the Thing Models are generated from). Features the caller leaves out
  are sent as "no value" (-1.0, "" or {}), so a modify never drops a feature.
- One type per feature: numbers are always float, states and texts str,
  objects dict. None, NaN and inf become -1.0. Features unknown to the model
  are dropped (logged once), except <thing>_<feature>_base in baseline.
- idSimulationRun and sim_time are added to every thing.
- correlation-id is constant per writer and thing (akt-<writer>-<name>), so
  the Telegraf tag correlationId does not create a new series per message.
- command "modify" replaces /features (drops feature definitions set from
  the Thing Model); "merge" (application/merge-patch+json) keeps them.
- At most max_rate messages per second, evenly spaced, with a ramp after
  connect (see Publisher): Ditto drops events on bursts and when cold.

The message builders need only the standard library; paho-mqtt is imported
when a Publisher connects.

  python -I sim/publish.py demo [--interval 3] [--duration 120] [--speed 60] [--max-rate 20]
  python -I sim/publish.py demo --dry-run          # print one tick, no MQTT
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import random
import signal
import socket
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
THINGS_JSON = os.environ.get("AKT_THINGS") or os.path.join(os.path.dirname(HERE), "setup", "things.json")
TOPIC_PREFIX = "telemetry"
MERGE_JSON = "application/merge-patch+json"

log = logging.getLogger("publish")


# ---------------------------------------------------------------------------
# Feature catalog from things.json
# ---------------------------------------------------------------------------
class Catalog:
    """Feature specs per thing: kind (number / string / object), unit, states."""

    def __init__(self, path: str | None = None):
        with open(path or THINGS_JSON, encoding="utf-8") as f:
            d = json.load(f)
        self.ns = d["namespace"]
        self.no_value = float(d["no_value"])
        self.types = d["types"]
        self.quant = d["quantities"]
        self.common = d["common_features"]
        self.things = {t["name"]: t["type"] for t in d["things"]}
        self._warned: set[tuple[str, str]] = set()

    def tid(self, name: str) -> str:
        return f"{self.ns}:{name}"

    def type_of(self, name: str) -> str | None:
        """Type of a thing; dynamic things by prefix (batch-0001 -> batch, issue-3 -> issue)."""
        if name in self.things:
            return self.things[name]
        prefix = name.rsplit("-", 1)[0]
        return prefix if prefix in self.types else None

    def _spec_of(self, typ: str, feature: str) -> tuple[str, str, tuple[str, ...]] | None:
        feats = dict(self.types[typ]["features"], **self.common)
        q = feats.get(feature)
        if q is None:
            return None
        if q == "state":
            return "string", "", tuple(self.types[typ].get("states", ()))
        spec = self.quant[q]
        return spec["type"], spec["unit"], ()

    def spec(self, name: str, feature: str) -> tuple[str, str, tuple[str, ...]] | None:
        typ = self.type_of(name)
        if typ is None:
            return None
        s = self._spec_of(typ, feature)
        if s is None and typ == "baseline" and feature.endswith("_base"):
            # <thing>_<feature>_base: same kind and unit as the feature of that thing
            stem = feature[:-len("_base")]
            for thing in sorted(self.things, key=len, reverse=True):
                if stem.startswith(thing + "_") and self.things[thing] != "baseline":
                    s = self._spec_of(self.things[thing], stem[len(thing) + 1:])
                    break
        return s

    def feature_names(self, name: str) -> list[str]:
        typ = self.type_of(name)
        if typ is None:
            raise KeyError(f"unknown thing {name}")
        return list(dict(self.types[typ]["features"], **self.common))

    def _warn_once(self, name: str, feature: str, text: str) -> None:
        key = (self.type_of(name) or name, feature)
        if key not in self._warned:
            self._warned.add(key)
            log.warning("%s.%s: %s", name, feature, text)

    def coerce(self, name: str, feature: str, kind: str, states: tuple[str, ...], value):
        if kind == "number":
            v = number(value, self.no_value)
            if value is not None and not isinstance(value, (bool, int, float)):
                self._warn_once(name, feature, f"not a number: {value!r}")
            return v
        if kind == "string":
            v = "" if value is None else str(value)
            if states and v and v not in states:
                self._warn_once(name, feature, f"state {v!r} not in {list(states)}")
            return v
        if not isinstance(value, dict):
            if value is not None:
                self._warn_once(name, feature, f"not an object: {value!r}")
            return {}
        return clean_object(value, self.no_value)

    def features(self, name: str, values: dict, run_id: str, sim_time: float) -> dict:
        """Ditto /features value: every feature of the thing as {properties: {value, unit}}."""
        vals = dict(values)
        vals["idSimulationRun"] = run_id
        vals["sim_time"] = sim_time
        out = {}
        for f in self.feature_names(name):
            kind, unit, states = self.spec(name, f)
            out[f] = {"properties": {"value": self.coerce(name, f, kind, states, vals.pop(f, None)), "unit": unit}}
        for f, v in vals.items():
            s = self.spec(name, f)
            if s is None:
                self._warn_once(name, f, "not in the model, dropped")
                continue
            kind, unit, states = s
            out[f] = {"properties": {"value": self.coerce(name, f, kind, states, v), "unit": unit}}
        return out


def number(value, no_value: float = -1.0) -> float:
    """Published float: bool -> 1.0 / 0.0; None, NaN, inf and non-numbers -> no_value."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return no_value
    if not math.isfinite(v):
        return no_value
    return float(f"{v:.7g}") if abs(v) < 1e7 else round(v, 1)


def clean_object(obj: dict, no_value: float = -1.0) -> dict:
    """Object value for InfluxDB: numbers as float, None dropped, nested dicts cleaned."""
    out = {}
    for k, v in obj.items():
        if v is None:
            continue
        if isinstance(v, dict):
            out[str(k)] = clean_object(v, no_value)
        elif isinstance(v, (bool, int, float)):
            out[str(k)] = number(v, no_value)
        else:
            out[str(k)] = v if isinstance(v, (str, list)) else str(v)
    return out


# ---------------------------------------------------------------------------
# Ditto protocol messages
# ---------------------------------------------------------------------------
def topic_for(ns: str, name: str) -> str:
    return f"{TOPIC_PREFIX}/{ns}/{name}"


def message(ns: str, name: str, path: str, value=None, *, action: str = "modify",
            correlation_id: str | None = None) -> dict:
    """Ditto protocol twin command; action modify / merge / delete (batches use path "/").

    response-required false: the source connection has no reply target, so a
    response would only load Ditto connectivity and then be dropped.
    """
    msg = {"topic": f"{ns}/{name}/things/twin/commands/{action}", "path": path,
           "headers": {"response-required": False}}
    if correlation_id:
        msg["headers"]["correlation-id"] = correlation_id
    if action == "merge":
        msg["headers"]["content-type"] = MERGE_JSON
    if action != "delete":
        msg["value"] = value
    return msg


# ---------------------------------------------------------------------------
# MQTT
# ---------------------------------------------------------------------------
class Publisher:
    """Sends feature snapshots to MQTT; one instance per writer (sim, a module).

    Messages leave evenly spaced, at most max_rate per second (0 = no limit),
    and for ramp_s seconds after connect the limit grows from a fifth of
    max_rate. Bursts overflow the outbound queue of Ditto connectivity (500,
    then events are dropped); a cold Ditto that cannot answer the enrichment
    of extraFields within 10 s makes the target connection reconnect, and
    events are dropped meanwhile. Twin state stays right, history is lost.
    Defaults: no loss right after a Ditto start on 4 vCPU (4 -> 20 per s);
    a warm Ditto took 48 per s.
    """

    def __init__(self, host: str = "mosquitto", port: int = 1883, writer: str = "sim", qos: int = 1,
                 command: str = "modify", catalog: Catalog | None = None, max_rate: float = 20.0,
                 ramp_s: float = 120.0):
        if command not in ("modify", "merge"):
            raise ValueError("command must be modify or merge")
        self.cat = catalog or Catalog()
        self.host, self.port, self.writer, self.qos, self.command = host, port, writer, qos, command
        self.max_rate, self.ramp_s = max_rate, ramp_s
        self.client = None
        self.sent = 0
        self.unacked = 0
        self._t_conn = time.monotonic()
        self._next = 0.0

    def rate(self, now: float | None = None) -> float:
        """Current limit, messages per second (0 = none)."""
        if self.max_rate <= 0:
            return 0.0
        age = (time.monotonic() if now is None else now) - self._t_conn
        if self.ramp_s > 0 and age < self.ramp_s:
            return self.max_rate * (0.2 + 0.8 * age / self.ramp_s)
        return self.max_rate

    def _throttle(self) -> None:
        now = time.monotonic()
        if self._next > now:
            time.sleep(self._next - now)
            now = self._next
        r = self.rate(now)
        self._next = max(self._next, now) + (1.0 / r if r > 0 else 0.0)

    def connect(self, attempts: int = 30, delay_s: float = 2.0) -> None:
        import paho.mqtt.client as mqtt
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"akt-{self.writer}-{socket.gethostname()}",
                        protocol=mqtt.MQTTv311)
        c.reconnect_delay_set(1, 10)
        for i in range(attempts):
            try:
                c.connect(self.host, self.port, keepalive=30)
                break
            except OSError as e:
                log.warning("MQTT %s:%s not reachable (%s), retry %d", self.host, self.port, e, i + 1)
                time.sleep(delay_s)
        else:
            raise ConnectionError(f"MQTT {self.host}:{self.port} not reachable")
        c.loop_start()
        self.client = c
        self._t_conn = time.monotonic()

    def close(self) -> None:
        if self.client is not None:
            self.client.loop_stop()
            self.client.disconnect()
            self.client = None

    def build(self, name: str, values: dict, run_id: str, sim_time: float) -> tuple[str, dict]:
        feats = self.cat.features(name, values, run_id, sim_time)
        msg = message(self.cat.ns, name, "/features", feats, action=self.command,
                      correlation_id=f"akt-{self.writer}-{name}")
        return topic_for(self.cat.ns, name), msg

    def send(self, topic: str, msg: dict):
        self._throttle()
        info = self.client.publish(topic, json.dumps(msg, ensure_ascii=False, separators=(",", ":")), qos=self.qos)
        self.sent += 1
        return info

    def publish_snapshot(self, snapshot: dict[str, dict], run_id: str, sim_time: float,
                         wait_s: float = 10.0) -> int:
        """Publish every thing of snapshot {name: {feature: value}}; returns messages not acked in wait_s."""
        infos = [self.send(*self.build(name, values, run_id, sim_time)) for name, values in snapshot.items()]
        if self.qos == 0 or wait_s <= 0:
            return 0
        deadline = time.monotonic() + wait_s
        for info in infos:
            left = deadline - time.monotonic()
            if left <= 0:
                break
            try:
                info.wait_for_publish(timeout=left)
            except (RuntimeError, ValueError) as e:
                log.warning("publish failed: %s", e)
        missing = sum(1 for i in infos if not _acked(i))
        self.unacked += missing
        return missing

    def publish_raw(self, name: str, path: str, value=None, action: str = "modify"):
        """Other twin commands (batches: modify / with policyId, delete /, modify /attributes/_parents)."""
        msg = message(self.cat.ns, name, path, value, action=action, correlation_id=f"akt-{self.writer}-{name}")
        return self.send(topic_for(self.cat.ns, name), msg)


def _acked(info) -> bool:
    """True when the broker acknowledged the message (paho raises for messages it could not queue)."""
    try:
        return info.is_published()
    except (RuntimeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Demo: synthetic but plausible values (design sections 1 and 4, base case)
# ---------------------------------------------------------------------------
# Written by akt-setup only (single writer rule): the demo leaves it alone.
DEMO_SKIP = frozenset({"validation-setup"})

BASE = {
    "site": {"state": "RUN", "speed": 60.0, "speed_fact": 60.0, "seed": 42.0, "tph": 7706.0, "cu_tph": 27.4,
             "power_mw": 260.0, "water_m3h": 4300.0, "scenario": "", "degraded": 0.0},
    "pit": {"state": "RUN", "mining_tph": 7706.0, "hard_in_plan": 0.0},
    "exc": {"state": "DIG", "tph": 2600.0, "bench": 12.0},
    "fleet": {"state": "NORMAL", "exc_total": 3.0, "exc_ready": 3.0, "trucks_total": 36.0, "trucks_ready": 31.0,
              "truck_kio_shift": 0.85, "haul_tph": 8680.0, "mining_tph": 7706.0},
    "crusher": {"state": "RUN", "tph": 3853.0, "power_kw": 750.0, "lube_kpa": 250.0},
    "conveyor": {"state": "RUN", "tph": 3853.0, "power_kw": 3640.0, "fault": 0.0},
    "stockpile": {"state": "NORMAL", "level_t": 28000.0, "in_tph": 3853.0, "out_tph": 3853.0, "hours_left": -1.0},
    "line": {"state": "RUN", "tph": 3853.0, "cu_tph": 13.7, "recovery": 87.2},
    "sag": {"state": "RUN", "power_kw": 26000.0, "power_limit_kw": 28000.0, "feed_tph": 3853.0, "speed_pct": 76.0,
            "load_pct": 25.0, "e_kwh_t": 6.75, "axb_soft": 35.0},
    "pebble": {"state": "RUN", "feed_tph": 578.0, "limit_tph": 740.0, "load_pct": 78.1},
    "ball": {"state": "RUN", "power_kw": 20500.0, "e_kwh_t": 10.64},
    "cyclones": {"state": "NORMAL", "p80_um": 179.0, "pressure_kpa": 85.0, "open_count": 10.0},
    "flot": {"state": "RUN", "feed_cu": 0.41, "tail_cu": 0.053, "conc_cu": 24.3, "recovery": 87.2, "cu_tph": 13.7,
             "conc_tph": 56.4},
    "rougher": {"state": "RUN", "feed_tph": 3853.0, "stage_recovery": 89.9, "mass_pull_pct": 7.0, "rconc_cu": 5.1,
                "residence_min": 30.0, "dose_sp_gt": 25.0, "dose_meas_gt": 25.0},
    "cleaner": {"state": "RUN", "feed_tph": 270.0, "stage_recovery": 97.0, "conc_cu": 24.3, "conc_tph": 56.4,
                "tail_cu": 0.19},
    "thick": {"state": "NORMAL", "feed_tph": 56.4, "underflow_tph": 56.4, "inventory_t": 170.0, "solids_pct": 60.0,
              "overflow_m3h": 120.0, "hours_to_full": -1.0},
    "filter": {"state": "RUN", "presses_on": 2.0, "cake_tph": 56.4, "moisture_pct": 8.0, "limit_tph": 70.0},
    "conc-stock": {"state": "NORMAL", "stock_t": 9000.0, "in_tph": 122.6, "wagons_shift": 0.0, "hours_to_full": -1.0},
    "water": {"state": "NORMAL", "intake_m3h": 4300.0, "recycle_m3h": 21130.0, "tails_loss_m3h": 2380.0,
              "evap_m3h": 1910.0, "pond_m3": 1.25e6, "residual_pct": 0.4, "piezo_kpa": 148.0},
    "power": {"state": "NORMAL", "grid_limit_mw": 300.0, "site_mw": 260.0, "grinding_mw": 139.6,
              "grinding_shaft_mw": 134.0, "other_mw": 111.6, "shed_mw": 0.0, "headroom_mw": 40.0},
    "crew": {"state": "FREE", "task": "", "free_at": -1.0},
    "validation-calib": {"state": "WAITING", "shifts_done": 0.0, "shifts_total": 100.0},
}
# Exact values: setpoints, limits, counts, flags.
FIXED = frozenset({"speed", "seed", "speed_pct", "power_limit_kw", "limit_tph", "open_count", "presses_on",
                   "grid_limit_mw", "exc_total", "exc_ready", "trucks_total", "trucks_ready", "dose_sp_gt",
                   "bench", "degraded", "hard_in_plan", "shed_mw", "shifts_done", "shifts_total", "wagons_shift"})
# Quantity -> default for features without a base value (module and service things).
BY_QUANTITY = {"tph": 0.0, "usdh": 0.0, "usd": 0.0, "t": 0.0, "mwh": 0.0, "m3": 0.0, "pct": 0.0, "mw": 50.0,
               "h": -1.0, "n": 0.0, "flag": 0.0, "axb": 35.0, "text": "", "obj": {}}


class Demo:
    """Base case with noise, slow swings and counters; deterministic for a seed."""

    def __init__(self, cat: Catalog, seed: int = 42, start_min: float = 480.0):
        self.cat = cat
        self.rng = random.Random(seed)
        self.t0 = start_min
        self.t = start_min
        self.cum: dict[tuple[str, str], float] = {}
        self.names = [n for n in cat.things if n not in DEMO_SKIP]

    def step(self, dt_min: float) -> dict[str, dict]:
        self.t += dt_min
        return {n: self.values(n, dt_min) for n in self.names}

    def _noisy(self, base: float, rel: float = 0.01) -> float:
        swing = 0.02 * math.sin(2 * math.pi * (self.t - self.t0) / 60.0)
        return base * (1.0 + swing + rel * self.rng.gauss(0.0, 1.0))

    def _count(self, name: str, f: str, rate_per_h: float, dt_min: float, start: float = 0.0) -> float:
        k = (name, f)
        self.cum[k] = self.cum.get(k, start) + rate_per_h * dt_min / 60.0
        return self.cum[k]

    def values(self, name: str, dt_min: float) -> dict:
        typ = self.cat.type_of(name)
        base = BASE.get(typ, {})
        feats = self.cat.types[typ]["features"]
        out = {}
        for f, q in feats.items():
            if f in base:
                b = base[f]
                out[f] = b if isinstance(b, str) or f in FIXED or b <= 0 else self._noisy(b)
            elif q == "min":
                out[f] = -1.0 if f in ("resend", "call_by") else self.t
            elif q == "s":
                out[f] = time.time()
            elif q == "state":
                out[f] = self.cat.types[typ]["states"][0]
            else:
                out[f] = BY_QUANTITY.get(q, -1.0)
        # counters and texts
        if typ == "line":
            cu = out["cu_tph"]
            for f, rate, start in (("cum_cu_t", cu, 0.0), ("cum_mwh", 126.0, 0.0), ("cum_m3", 2150.0, 0.0),
                                   ("cum_usd", cu * 14539 * 0.955 - 126.0 * 1000 * 16 / 470, 0.0)):
                out[f] = self._count(name, f, rate, dt_min, start)
                out[f + "_total"] = self._count(name, f + "_total", rate, dt_min, 1000.0 * rate)
        elif typ == "sag":
            out["liner_wear_mm"] = self._count(name, "liner_wear_mm", 20.41 * out["feed_tph"] / 1e6, dt_min, 120.0)
            out["liner_ground_t"] = self._count(name, "liner_ground_t", out["feed_tph"], dt_min, 3.0e6)
        elif typ == "pit":
            out["next_block"] = 1201.0 + math.floor((self.t - self.t0) / 15.0)
            out["plan_text"] = "L1: B-{0:.0f} B-{1:.0f}; L2: B-{2:.0f}".format(
                out["next_block"], out["next_block"] + 2, out["next_block"] + 1)
        elif typ == "exc":
            out["block"] = "B-{0:.0f}".format(1200 + int(name.rsplit("-", 1)[1]))
        elif typ == "conc-stock":
            out["shipped_t_shift"] = 1470.0 if (self.t % 720) >= 600 else 0.0
        elif typ == "mod-ore":
            for h in range(1, 13):
                out[f"fc_tph_h{h}"] = self._noisy(7706.0 - 60.0 * h, 0.005)
            out.update(next_hard_eta_early_h_l1=3.5, next_hard_eta_h_l1=4.2, next_hard_axb=27.0, hit_rate=70.0)
        elif typ == "mod-losses":
            for node in ("sag-1", "sag-2", "cyclones-1", "cyclones-2", "flot-1", "flot-2"):
                gap = 0.05 * self.rng.gauss(0.0, 1.0)
                out.update({f"{node}_gap_cu_tph": gap, f"{node}_gap_usd_h": gap * 14539 * 0.955,
                            f"{node}_sigma": 0.15, f"{node}_status": "noise"})
            out["power_headroom_mw"] = 50.0
        elif typ == "baseline":
            for ln in ("line-1", "line-2"):
                out[f"{ln}_tph_base"] = self._noisy(3853.0)
                out[f"{ln}_cu_tph_base"] = self._noisy(13.7)
            out["cum_cu_t_base"] = self._count(name, "cum_cu_t_base", 27.4, dt_min)
        return out


def demo(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="publish.py demo", description="Synthetic telemetry for all things")
    ap.add_argument("--mqtt-host", default=os.environ.get("MQTT_HOST", "localhost"))
    ap.add_argument("--mqtt-port", type=int, default=int(os.environ.get("MQTT_PORT", "1883")))
    ap.add_argument("--interval", type=float, default=3.0, help="wall seconds between snapshots")
    ap.add_argument("--max-rate", type=float, default=20.0, help="messages per second, 0 = no limit")
    ap.add_argument("--ramp", type=float, default=120.0, help="seconds to reach max-rate after connect")
    ap.add_argument("--speed", type=float, default=60.0, help="model seconds per wall second")
    ap.add_argument("--duration", type=float, default=120.0, help="wall seconds, 0 = until stopped")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--run-id", default="", help="idSimulationRun (default demo-s<seed>-<UTC time>)")
    ap.add_argument("--command", choices=("modify", "merge"), default="modify")
    ap.add_argument("--qos", type=int, choices=(0, 1), default=1)
    ap.add_argument("--writer", default=os.environ.get("AKT_WRITER", "sim"))
    ap.add_argument("--only", default="", help="comma separated thing names (default all but validation-setup)")
    ap.add_argument("--dry-run", action="store_true", help="print one snapshot as messages, no MQTT")
    a = ap.parse_args(argv)

    cat = Catalog()
    sim = Demo(cat, a.seed)
    if a.only:
        sim.names = [n for n in a.only.split(",") if n]
    run_id = a.run_id or time.strftime(f"demo-s{a.seed}-%Y%m%dT%H%M%SZ", time.gmtime())
    dt_min = a.interval * a.speed / 60.0
    pub = Publisher(a.mqtt_host, a.mqtt_port, a.writer, a.qos, a.command, cat, a.max_rate, a.ramp)

    if a.dry_run:
        for name, values in sim.step(dt_min).items():
            topic, msg = pub.build(name, values, run_id, sim.t)
            print(topic, json.dumps(msg, ensure_ascii=False))
        return 0

    stop = []
    signal.signal(signal.SIGTERM, lambda *_: stop.append(1))
    signal.signal(signal.SIGINT, lambda *_: stop.append(1))
    pub.connect()
    log.info("run %s: %d things every %.1f s, x%.0f, %s qos %d -> mqtt://%s:%s", run_id, len(sim.names),
             a.interval, a.speed, a.command, a.qos, a.mqtt_host, a.mqtt_port)
    t_start = time.monotonic()
    ticks = 0
    try:
        while not stop and (a.duration <= 0 or time.monotonic() - t_start < a.duration):
            t_tick = time.monotonic()
            missing = pub.publish_snapshot(sim.step(dt_min), run_id, sim.t)
            ticks += 1
            took = time.monotonic() - t_tick
            if ticks == 1 or ticks % 10 == 0 or missing:
                log.info("tick %d sim_time %.0f min: %d sent, %d not acked, %.3f s", ticks, sim.t, pub.sent,
                         missing, took)
            time.sleep(max(0.0, a.interval - took))
    finally:
        pub.close()
    log.info("done %s: %d ticks, %d messages, %d not acked, last sim_time %.0f", run_id, ticks, pub.sent,
             pub.unacked, sim.t)
    return 0 if pub.unacked == 0 else 1


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if argv and argv[0] == "demo":
        return demo(argv[1:])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
