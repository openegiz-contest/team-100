"""Simulator service akt-sim: the plant in model time, twins over MQTT, commands from Ditto.

Design: section 2 (one model time, speeds, warm-up, auto pause, heartbeat,
checkpoints, barrier, idSimulationRun), section 3 (things, batches, baseline,
validation-sim), section 7 (scenarios, "Two at once", cancel, reset).

What it does
  - Runs a Plant (free run) or a CopySet (scenario) in 1 min model steps,
    paced by the wall clock at `speed` model minutes per wall minute (x60 =
    one model minute per second; x300, x1200; 0 = pause).
  - Publishes every physical thing and live batch through sim.publish
    (command merge, so the feature definitions from the Thing Models stay),
    with idSimulationRun and sim_time: at every checkpoint
    (cal_checkpoint_min) and, at x60 and below, between checkpoints as often
    as the rate budget allows (publish.Publisher: at most max_rate messages
    per second, ramp after connect). Above x60 the model waits for the
    publisher at each checkpoint; site.speed_fact tells the achieved speed.
  - Warm-up 06:00 -> 08:00 at full speed under a new idSimulationRun with
    site.state WARMUP, snapshots every warmup_publish_min.
  - The copies "base", "loud" and "no_twin" of a scenario go ONLY to the
    baseline thing (<thing>_<feature>_base, cum_*_base, alt_*, shift_result);
    the physical things carry the fact copy only. The first point of every
    run publishes the baseline too (a free run: every *_base value NO_VALUE),
    and shift_result has one fixed shape with the run id (shift_object), so a
    Ditto merge never leaves a value of an earlier run behind.
  - validation-sim.truth_log after a hidden cause ends (the sim's own log).
  - Batches: modify / (whole thing with policyId) when a batch appears, again
    at the next BATCH_CREATE_REPEATS checkpoints and for every live batch once
    a model hour; modify /attributes/_parents when it moves; delete / when the
    plant drops it, again at the next BATCH_DELETE_REPEATS checkpoints. The
    first point of the process deletes batch-0001..0099 it does not use
    (things of a former process). A create or delete lost while Ditto is busy
    would otherwise leave a batch Ditto refuses merges for, or an orphan.
  - Commands from the thing `control` (written by akt-web): features
    scenario, speed, reset, cancel; each an object with a growing seq, a seq
    seen before is ignored (run=1 repeats). journal.last {seq, action: call,
    issue} and mod-priority.auto_call {seq, issue} book a crew on the fact
    copy. Source: Ditto twin events on MQTT (opentwins/twin/events/<ns>/<thing>)
    and, when DITTO_URL is set, HTTP polling of control and journal every poll_s.
  - Barrier (AKT_BARRIER=mod-losses,mod-ore,mod-priority; off by default):
    after a checkpoint T the model waits until every listed module reports
    processed_sim_time at or past its tact point before T; resend = T from
    a module republishes the point; after barrier_timeout_s the run goes on
    with site.degraded = 1.
  - In pause (speed 0, or the 20:00 auto pause of a scenario) the site thing
    is republished every heartbeat_s with a fresh heartbeat.

Control objects (any extra keys are ignored):
  scenario {seq, id|text: "crusher:1+grid", preset: "fork", kip: 1, auto: 1,
            safety: 0, speed: 60}       empty id and preset -> same as reset
  speed    {seq, value: 60 | 300 | 1200 | 0}   0 pauses
  reset    {seq, seed: 42, speed: 60}
  cancel   {seq}
lever    {seq, feed_1, feed_2 (% of the nominal line rate), p80_um (grind target, 0 = off), dose_gt (collector dose, 0 = off),
          reset: 1 clears every lever}   what-if levers: control of the model, not of the plant

Environment: MQTT_HOST, MQTT_PORT, DITTO_URL (optional), DITTO_USER,
DITTO_PASSWORD, AKT_SEED, AKT_SPEED, AKT_MAX_RATE, AKT_RAMP_S, AKT_QOS,
AKT_BARRIER, AKT_BARRIER_TIMEOUT_S, AKT_FACT_POLICY (offline | module),
AKT_WARMUP_PUBLISH_MIN, AKT_PUBLISH_MIN, AKT_HEARTBEAT_S, AKT_POLL_S.

  python -I aktogay/run.py service                       # service (needs MQTT)
  python -I aktogay/run.py service --dry-run --duration 30 --speed 1200
  python -I aktogay/run.py service --dry-run --scenario crusher:1+grid --duration 20
"""
from __future__ import annotations

import argparse
import base64
import collections
import json
import logging
import math
import os
import queue
import signal
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if __name__ == "__main__" and ROOT not in sys.path:
    sys.path.insert(0, ROOT)
SETUP = os.path.join(ROOT, "setup")
if SETUP not in sys.path:
    sys.path.insert(0, SETUP)

import twins  # noqa: E402  (setup/twins.py: Ditto bodies of things from things.json)
from sim import publish  # noqa: E402
from sim import sensors as se  # noqa: E402
from sim.params import ParamSet, default  # noqa: E402
from sim.plant import CopySet, Plant  # noqa: E402
from sim.state import MIN_PER_H, NO_VALUE, PlantHooks, PlantState  # noqa: E402

log = logging.getLogger("service")

EPS = 1e-6
CONTROL_FEATURES = ("scenario", "speed", "reset", "cancel", "lever")
CALL_ACTIONS = ("call", "auto_call")
REMIND_ACTIONS = ("remind", "next")      # "not arrived": remind the person, or call the next one of the trade
EVENT_THINGS = ("control", "journal", "mod-losses", "mod-ore", "mod-priority")
# Module tact in model minutes: a module confirms the last point of its tact at or before T.
MODULE_TACT_MIN = {"mod-losses": 5.0, "mod-ore": 15.0, "mod-priority": 5.0}
LIVE_SPEED_MAX = 60.0            # above this, publishing only at checkpoints
REANCHOR_LAG_MIN = 10.0          # model minutes of lag after which the pace clock is reset
TRUTH_LINES = 50                 # last lines of validation-sim.truth_log
SPEED_WINDOW_S = 30.0            # speed_fact is measured over this wall window

# Features of the base copy published on the baseline thing as <thing>_<feature>_base.
BASE_FEATURES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("site", ("tph", "cu_tph", "power_mw", "water_m3h")),
    ("power", ("site_mw", "grid_limit_mw", "headroom_mw")),
    ("water", ("intake_m3h", "recycle_m3h", "pond_m3")),
    ("conc-stock", ("stock_t",)),
    ("pit", ("mining_tph",)),
    ("exc-1", ("state", "tph")),
    ("exc-2", ("state", "tph")),
    ("exc-3", ("state", "tph")),
) + tuple(
    (name.format(n=n), feats)
    for n in (1, 2)
    for name, feats in (
        ("line-{n}", ("state", "tph", "cu_tph", "recovery", "cum_cu_t", "cum_mwh", "cum_m3", "cum_usd")),
        ("crusher-{n}", ("state", "tph")),
        ("conveyor-{n}", ("tph",)),
        ("stockpile-{n}", ("level_t", "hours_left")),
        ("sag-{n}", ("state", "power_kw", "feed_tph", "load_pct", "e_kwh_t")),
        ("pebble-{n}", ("feed_tph",)),
        ("cyclones-{n}", ("p80_um",)),
        ("flot-{n}", ("state", "tail_cu", "recovery", "cu_tph", "conc_tph")),
        ("rougher-{n}", ("dose_meas_gt",)),
        ("thick-{n}", ("inventory_t",)),
        ("filter-{n}", ("cake_tph",)),
    )
)
# baseline.shift_result has one fixed shape in every run, so a Ditto merge overwrites every leaf
# and nothing of an earlier run (a "loud" copy of "Two at once", a free-run summary) survives.
SHIFT_COPIES = ("fact", "base", "loud", "no_twin")
SHIFT_KEYS = ("cu_t", "ore_t", "energy_mwh", "water_m3", "usd")
BATCH_TAG_RU = {"": "блок плана карьера", "hard": "блок сценария «Твёрдая руда»",
                "blend": "мягкая руда для шихтовки 50/50", "initial": "руда на складе и в пути к 06:00"}
BATCH_PURGE_MAX = 99            # at process start: delete batch-0001..0099 left by an earlier process
BATCH_DELETE_REPEATS = 1         # a batch delete is sent once more at the next checkpoint (a lost delete would
                                 # leave a batch thing with an old sim_time behind). Every send after the one that
                                 # worked fails in Ditto (ThingNotAccessible, a WARN with a stack and dead letters
                                 # in the things log: 3 repeats gave 3 such errors per batch, 23.10)
BATCH_CREATE_REPEATS = 2         # a batch create (modify /) is sent again at the next checkpoints, and
BATCH_HEAL_MIN = 60.0            # every live batch once a model hour: a create lost under load would
                                 # leave merges that Ditto refuses (ThingNotAccessible) for good
# Rate budget (publish.Publisher, 20 msg/s with a ramp): the site passport things go out less often.
SLOW_TYPES = ("truck", "face", "road", "drill", "dozer")   # in rotation: each every SLOW_EVERY checkpoints
SLOW_EVERY = 6
CHECKPOINT_TYPES = ("person", "analyzer", "weigher", "flowmeter", "piezometer", "leach", "sxew")   # checkpoints only, not live
FULL_REASONS = ("start", "cancel", "pause", "auto-pause")   # points that carry every thing


def shift_object(run: str, kind: str, t_min: float, copies: dict | None = None) -> dict:
    """baseline.shift_result: {run, kind, t_min, copies{fact, base, loud, no_twin}{cu_t, ...}, diff, fork}.

    kind "none" (no result yet in this run), "shift" (free run: summary of the last shift in copies.fact)
    or "scenario" (copies at t_min). Missing copies and values are NO_VALUE; diff = copy - base.
    """
    copies = copies or {}
    out = {"run": run, "kind": kind, "t_min": float(t_min), "copies": {}, "diff": {}, "fork": {}}
    for name in SHIFT_COPIES:
        c = copies.get(name) or {}
        out["copies"][name] = {k: float(c[k]) if k in c else NO_VALUE for k in SHIFT_KEYS}
    base = copies.get("base")
    for name in SHIFT_COPIES[:1] + SHIFT_COPIES[2:]:
        c = copies.get(name)
        out["diff"][name] = {k: (float(c[k]) - float(base[k])) if (c and base and k in c and k in base) else NO_VALUE
                             for k in SHIFT_KEYS}
    loud, no_twin, fact = copies.get("loud"), copies.get("no_twin"), copies.get("fact")
    out["fork"] = {
        "detection_cu_t": float(loud["cu_t"]) - float(no_twin["cu_t"]) if loud and no_twin else NO_VALUE,
        "order_cu_t": float(fact["cu_t"]) - float(loud["cu_t"]) if loud and fact else NO_VALUE,
    }
    return out


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
def _env(name: str, default_value):
    v = os.environ.get(name)
    if v is None or v == "":
        return default_value
    if isinstance(default_value, bool):
        return v.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(default_value, int):
        return int(float(v))
    if isinstance(default_value, float):
        return float(v)
    return v


@dataclass
class Config:
    mqtt_host: str = "mosquitto"
    mqtt_port: int = 1883
    ditto_url: str = ""              # e.g. http://ditto-nginx:80; empty = events only
    ditto_user: str = "ditto"
    ditto_password: str = ""
    seed: int = 42
    speed: float = 60.0
    max_rate: float = 20.0
    ramp_s: float = 120.0
    qos: int = 1
    barrier: tuple[str, ...] = ()
    barrier_timeout_s: float = 60.0
    fact_policy: str = "offline"     # offline: fork fact copy follows events.fork_policies; module: calls only
    warmup_publish_min: float = 20.0
    publish_min: float = 1.0         # model minutes between live snapshots at x60 and below
    min_publish_gap_s: float = 1.0   # wall seconds between live snapshots
    heartbeat_s: float = 2.0
    poll_s: float = 2.0
    duration_s: float = 0.0          # 0 = until stopped
    dry_run: bool = False
    scenario: str = ""               # start in this scenario (tests, demo)
    preset: str = ""
    kip: int | None = None
    auto: bool | None = None
    safety: bool = False
    writer: str = "sim"
    things_json: str | None = None

    @classmethod
    def from_env(cls) -> "Config":
        c = cls()
        c.mqtt_host = _env("MQTT_HOST", c.mqtt_host)
        c.mqtt_port = _env("MQTT_PORT", c.mqtt_port)
        c.ditto_url = _env("DITTO_URL", c.ditto_url)
        c.ditto_user = _env("DITTO_USER", c.ditto_user)
        c.ditto_password = _env("DITTO_PASSWORD", c.ditto_password)
        c.seed = _env("AKT_SEED", c.seed)
        c.speed = _env("AKT_SPEED", c.speed)
        c.max_rate = _env("AKT_MAX_RATE", c.max_rate)
        c.ramp_s = _env("AKT_RAMP_S", c.ramp_s)
        c.qos = _env("AKT_QOS", c.qos)
        c.barrier = tuple(x.strip() for x in str(_env("AKT_BARRIER", "")).split(",") if x.strip())
        c.barrier_timeout_s = _env("AKT_BARRIER_TIMEOUT_S", c.barrier_timeout_s)
        c.fact_policy = _env("AKT_FACT_POLICY", c.fact_policy)
        c.warmup_publish_min = _env("AKT_WARMUP_PUBLISH_MIN", c.warmup_publish_min)
        c.publish_min = _env("AKT_PUBLISH_MIN", c.publish_min)
        c.heartbeat_s = _env("AKT_HEARTBEAT_S", c.heartbeat_s)
        c.poll_s = _env("AKT_POLL_S", c.poll_s)
        c.writer = _env("AKT_WRITER", c.writer)
        c.things_json = os.environ.get("AKT_THINGS") or None
        return c


# ---------------------------------------------------------------------------
# Ditto events and commands
# ---------------------------------------------------------------------------
def _prop_value(body):
    if isinstance(body, dict):
        props = body.get("properties")
        if isinstance(props, dict):
            return props.get("value")
    return None


def feature_values(path: str, value) -> dict:
    """{feature: properties.value} from a Ditto event or thing part (path, value).

    Paths: "/" (whole thing), "/features", "/features/<f>",
    "/features/<f>/properties", "/features/<f>/properties/value".
    Other paths give {}.
    """
    parts = [p for p in (path or "/").split("/") if p]
    if not parts:
        feats = value.get("features") if isinstance(value, dict) else None
        return {f: _prop_value(b) for f, b in feats.items()} if isinstance(feats, dict) else {}
    if parts[0] != "features":
        return {}
    if len(parts) == 1:
        return {f: _prop_value(b) for f, b in value.items()} if isinstance(value, dict) else {}
    f, rest = parts[1], parts[2:]
    if not rest:
        return {f: _prop_value(value)}
    if rest == ["properties"]:
        return {f: value.get("value")} if isinstance(value, dict) else {}
    if rest == ["properties", "value"]:
        return {f: value}
    return {}


def thing_name(mqtt_topic: str, payload: dict) -> str:
    """Thing name (without namespace) of an event from its MQTT topic, else from the Ditto topic."""
    name = (mqtt_topic or "").rsplit("/", 1)[-1]
    if not name or name in ("events", "twin"):
        parts = str(payload.get("topic", "")).split("/")
        name = parts[1] if len(parts) > 1 else ""
    return name


def _seq_of(obj) -> int | None:
    try:
        return int(obj.get("seq"))
    except (AttributeError, TypeError, ValueError):
        return None


def _truthy(v) -> bool:
    """1, 1.0, "1", True, "true", "yes" -> True; 0, "0", "", None, "false" -> False."""
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true", "yes", "on"):
            return True
        try:
            return float(s) != 0.0
        except ValueError:
            return False
    try:
        return bool(float(v))
    except (TypeError, ValueError):
        return False


def _wall_of(obj) -> float | None:
    try:
        v = float(obj.get("t_wall"))
    except (AttributeError, TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


class CommandLog:
    """Remembers the last (seq, t_wall) per (thing, feature); a repeated or older command is dropped.

    A command is new when its seq is higher, or when its t_wall (wall clock of the writer) is later:
    if the writer ever starts its seq again (a read of the old object failed, the thing was
    recreated), the command still goes through instead of being lost until a restart.
    """

    def __init__(self):
        self.seen: dict[tuple[str, str], tuple[int, float | None]] = {}

    def take(self, thing: str, feats: dict, act: bool = True) -> list[tuple[str, dict]]:
        """Command objects of `feats` that are new; act=False only records their seq."""
        out = []
        for f, obj in feats.items():
            if not isinstance(obj, dict):
                continue
            seq = _seq_of(obj)
            wall = _wall_of(obj)
            key = (thing, f)
            if seq is not None:
                last = self.seen.get(key)
                if last is not None:
                    later = wall is not None and last[1] is not None and wall > last[1]
                    if seq <= last[0] and not later:
                        continue
                self.seen[key] = (seq, wall if wall is not None else (last[1] if last else None))
            elif not act:
                continue                      # polled object without seq: cannot be de-duplicated
            if act:
                out.append((f, obj))
        return out


# ---------------------------------------------------------------------------
# MQTT sink (live or dry)
# ---------------------------------------------------------------------------
class Sink:
    """Publishes through publish.Publisher and collects Ditto events from MQTT.

    dry=True builds every message (types checked by the catalog) and counts
    it without a broker; tests and --dry-run use it.
    """

    def __init__(self, pub: publish.Publisher, dry: bool = False):
        self.pub = pub
        self.dry = dry
        self.cat = pub.cat
        self.events_q: queue.Queue = queue.Queue()
        self.sent = 0
        self.unacked = 0
        self.last_snapshot: dict[str, dict] = {}
        self.snapshot_names: list[tuple[str, ...]] = []    # things of every snapshot, dry run only
        self.raw_ops: list[tuple[str, str, str]] = []     # (name, path, action), dry run only
        self._topics: list[str] = []

    def connect(self, topics: list[str]) -> None:
        self._topics = list(topics)
        if self.dry:
            return
        self.pub.connect()
        c = self.pub.client
        c.on_message = self._on_message
        c.on_connect = self._on_connect
        self._subscribe()

    def _subscribe(self) -> None:
        if self.pub.client is not None and self._topics:
            self.pub.client.subscribe([(t, 1) for t in self._topics])

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        log.info("MQTT connected (%s); subscribing %d topics", reason_code, len(self._topics))
        self._subscribe()

    def _on_message(self, client, userdata, msg):
        self.events_q.put((msg.topic, msg.payload))

    def events(self) -> list[tuple[str, bytes]]:
        out = []
        while True:
            try:
                out.append(self.events_q.get_nowait())
            except queue.Empty:
                return out

    def snapshot(self, snap: dict[str, dict], run_id: str, sim_time: float) -> int:
        """Publish {name: {feature: value}}; returns messages not acknowledged."""
        if self.dry:
            for name, values in snap.items():
                _topic, msg = self.pub.build(name, values, run_id, sim_time)
                json.dumps(msg, ensure_ascii=False, allow_nan=False)
                self.sent += 1
            self.last_snapshot = {k: dict(v) for k, v in snap.items()}
            self.snapshot_names.append(tuple(snap))
            return 0
        missing = self.pub.publish_snapshot(snap, run_id, sim_time)
        self.sent = self.pub.sent
        self.unacked = self.pub.unacked
        return missing

    def raw(self, name: str, path: str, value=None, action: str = "modify") -> None:
        if self.dry:
            msg = publish.message(self.cat.ns, name, path, value, action=action)
            json.dumps(msg, ensure_ascii=False, allow_nan=False)
            self.raw_ops.append((name, path, action))
            self.sent += 1
            return
        self.pub.publish_raw(name, path, value, action)
        self.sent = self.pub.sent

    def close(self) -> None:
        if not self.dry:
            self.pub.close()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
class _Hooks(PlantHooks):
    """Plant callbacks: warm-up snapshots, truth log, shift summaries."""

    def __init__(self, runner: "Runner"):
        self.r = runner

    def on_checkpoint(self, st: PlantState) -> None:
        # Warm-up snapshots every warmup_publish_min; the last one is the
        # 08:00 point, where the plant already reports RUN (Plant.step flips
        # the state before its hooks), so the runner's flag decides, not the state.
        if self.r.warming:
            every = self.r.cfg.warmup_publish_min
            t = st.clock.t_min
            if every > 0 and abs(t / every - round(t / every)) < EPS:
                self.r.publish_point("warmup", st)

    def on_truth(self, st: PlantState, entry) -> None:
        self.r.truth.append(entry.text)
        self.r.truth_dirty = True

    def on_shift_end(self, st: PlantState, summary: dict) -> None:
        # the summary belongs to the run that is stepping now; _baseline publishes it for that run only
        self.r.shift_result = dict(summary, run=self.r.run_id)
        self.r.baseline_dirty = True


@dataclass
class RunStats:
    points: int = 0
    heartbeats: int = 0
    batches_created: int = 0
    batches_moved: int = 0
    batches_deleted: int = 0
    commands: int = 0
    calls: int = 0
    barrier_waits: int = 0
    barrier_timeouts: int = 0
    resends: int = 0
    unacked: int = 0
    log: list = field(default_factory=list)   # (sim_time, reason) of the last points, dry run


class Runner:
    """Model time, publishing and commands of the simulator service.

    clock / sleep / wall are injectable for tests (monotonic seconds, sleep,
    Unix time).
    """

    def __init__(self, cfg: Config, sink: Sink, prm: ParamSet | None = None, clock=time.monotonic,
                 sleep=time.sleep, wall=time.time):
        self.cfg = cfg
        self.sink = sink
        self.cat = sink.cat
        self.prm = default() if prm is None else prm
        self.clock, self.sleep, self.wall = clock, sleep, wall
        self.model = twins.Model(cfg.things_json)
        self.seed = int(cfg.seed)
        self.speed = float(cfg.speed)
        self.kip: int | None = cfg.kip
        self.auto: bool | None = cfg.auto
        self.user_paused = False
        self.warming = False             # True while a run warms up 06:00 -> 08:00
        self.run_no = 0
        self.run_id = ""
        self.plant: Plant | None = None
        self.copies: CopySet | None = None
        self.hooks = _Hooks(self)
        self.cmds = CommandLog()
        self.degraded = 0.0
        self.truth: list[str] = []
        self.truth_dirty = False
        self.shift_result: dict = {}
        self.baseline_dirty = False
        self.known_batches: dict[str, str] = {}
        self.issue_nodes: dict[str, dict] = {}          # issue-N -> {node, kind} (mod-priority.issue_map)
        self.stale_batches: set[str] = set()
        self.deleted_batches: dict[str, int] = {}   # batch -> delete repeats left (sent at checkpoints)
        self.created_batches: dict[str, int] = {}   # batch -> create repeats left (sent at checkpoints)
        self.purge_batches = True                   # first point of the process: clear batches of a former process
        self.processed: dict[str, float] = {}
        self.resend: dict[str, float] = {}
        self.stats = RunStats()
        self.cp_min = float(self.prm["cal_checkpoint_min"])
        self._slow_index: dict[str, int] | None = None
        self._first_point = True
        self._pause_published = False
        self._anchor_wall = clock()
        self._anchor_t = 0.0
        self._last_pub_t = -math.inf
        self._last_pub_wall = -math.inf
        self._hb_wall = -math.inf
        self._samples: collections.deque = collections.deque()
        self._poll_wall = -math.inf
        self._polled_once = False
        self._http_err_wall = -math.inf

    # ------------------------------------------------------------ properties
    @property
    def t_min(self) -> float:
        return self.plant.state.clock.t_min if self.plant is not None else 0.0

    @property
    def paused(self) -> bool:
        """User pause or the auto pause of a scenario at 20:00."""
        return self.user_paused or (self.plant is not None and self.plant.state.site_state == "PAUSED")

    def site_state(self, st: PlantState) -> str:
        if st.site_state == "WARMUP":
            return "WARMUP"
        return "PAUSED" if (self.user_paused or st.site_state == "PAUSED") else "RUN"

    # ------------------------------------------------------------------ runs
    def _new_run(self, kind: str) -> None:
        self.run_no += 1
        stamp = time.strftime("%d%H%M%S", time.gmtime(self.wall()))
        self.run_id = f"s{self.seed}-{kind}-{self.run_no:04d}-{stamp}"
        self.degraded = 0.0
        self.truth = []
        self.truth_dirty = False
        self.shift_result = {}
        self.issue_nodes = {}            # issue things are numbered again in every run
        self.baseline_dirty = True       # the first point of a run replaces the baseline of the run before
        self.processed = {}
        self.resend = {}
        self.stale_batches |= set(self.known_batches)
        self.known_batches = {}
        self._first_point = True
        self._pause_published = False
        self.user_paused = False
        self._samples.clear()

    def _announce_warmup(self) -> None:
        """One site message with state WARMUP before the warm-up, so the panel can say so."""
        st = self.plant.state if self.plant is not None else None
        values = {"state": "WARMUP", "state_ru": se.state_ru("WARMUP"), "speed": self.speed, "speed_fact": 0.0,
                  "seed": float(self.seed),
                  "heartbeat": float(self.wall()), "degraded": self.degraded, "scenario": ""}
        if st is not None:
            site = se.measured_features(st, self.prm).get("site", {})
            values = dict(site, **values)
        self.sink.snapshot({"site": values}, self.run_id, self.t_min)

    def start_free(self, seed: int | None = None, speed: float | None = None) -> None:
        """Reset: new run, free run from 06:00 with the warm-up to 08:00, then x`speed` (default: as before)."""
        if seed is not None:
            try:
                self.seed = int(float(seed))
            except (TypeError, ValueError):
                log.warning("reset: bad seed %r kept %d", seed, self.seed)
        try:
            if speed is not None and float(speed) > 0:
                self.speed = float(speed)
        except (TypeError, ValueError):
            log.warning("reset: bad speed %r", speed)
        self.copies = None
        self.plant = None
        self._new_run("free")
        log.info("run %s: free run, seed %d, x%.0f", self.run_id, self.seed, self.speed)
        self._announce_warmup()
        self.plant = Plant(self.prm, self.seed, mode="free", hooks=self.hooks)
        self.plant.base_winter = self.plant.winter_on = self.season_winter()
        self.plant.ox_date = self.host_date()
        self.plant.late_calls = True           # a called person may get the message late (crew_late_p)
        self.warming = True
        try:
            self.plant.warmup()
        finally:
            self.warming = False
        self._publish_start()
        self._anchor(self.t_min)

    def start_scenario(self, text: str, preset: str = "", kip: int | None = None, auto: bool | None = None,
                       safety: bool = False, speed: float | None = None) -> bool:
        """Scenario: new run, CopySet (fact, base; fork: loud, no_twin) warmed up to 08:00. False on a bad text."""
        try:
            if speed is not None and float(speed) > 0:
                self.speed = float(speed)
        except (TypeError, ValueError):
            log.warning("scenario: bad speed %r", speed)
        try:
            kip_n = self.kip if kip is None else int(float(kip))
        except (TypeError, ValueError):
            kip_n = self.kip
        auto_b = self.auto if auto is None else bool(auto)
        self.copies = None
        self.plant = None
        self._new_run("scen")
        log.info("run %s: scenario %r preset %r kip %s auto %s safety %s x%.0f", self.run_id, text, preset,
                 kip_n, auto_b, safety, self.speed)
        self._announce_warmup()
        self.warming = True
        try:
            self.copies = CopySet(self.prm, self.seed, text, preset=preset, kip=kip_n, safety=safety,
                                  auto=auto_b, hooks=self.hooks,
                                  fact_policy=(self.cfg.fact_policy != "module"))
        except ValueError as e:
            self.warming = False
            log.warning("scenario rejected: %s; back to free run", e)
            self.start_free()
            return False
        finally:
            self.warming = False
        self.plant = self.copies.copies["fact"]
        for c in self.copies.copies.values():
            if not c.winter_on:
                c.base_winter = c.winter_on = self.season_winter()
            c.ox_date = self.host_date()
        # late arrivals of called people on the fact copy of a training scenario; never in "Two at once",
        # whose copies are compared call by call
        self.plant.late_calls = (preset or "").strip().lower() != "fork" and "fork" not in str(text).lower()
        self._publish_start()
        self._anchor(self.t_min)
        return True

    @staticmethod
    def host_date() -> tuple[int, int]:
        """(year, 0-based day of the year) of the host date: the quarter of the oxide line (sim/oxide.py)."""
        import datetime
        d = datetime.date.today()
        return d.year, d.timetuple().tm_yday - 1

    def season_winter(self) -> bool:
        """Season of the run: AKT_SEASON = auto (date of the model clock = the host date), winter or summer."""
        mode = (os.environ.get("AKT_SEASON") or "auto").strip().lower()
        if mode in ("winter", "summer"):
            return mode == "winter"
        import datetime
        from .utilities import is_winter
        return is_winter(float(datetime.date.today().timetuple().tm_yday - 1), self.prm)

    def _publish_start(self) -> None:
        """The 08:00 point of a new run, unless the warm-up hook has just published that very minute."""
        if self._first_point or self._last_pub_t != self.t_min or self.copies is not None:
            self.publish_point("start")

    def cancel(self) -> None:
        """Cancel: the fact copy becomes the base copy; the run id stays."""
        if self.copies is None:
            log.info("cancel: no scenario active")
            return
        lever_only = self.copies.lever_only
        self.copies.cancel()
        self.plant = self.copies.copies["fact"]
        if lever_only:
            self._leave_lever_comparison()            # a free run again: levers off, no base copy
        log.info("run %s: %s at %s", self.run_id, "levers cleared" if lever_only else "scenario cancelled",
                 self.plant.state.clock.hhmm())
        self.publish_point("cancel")

    def _leave_lever_comparison(self) -> None:
        """Back to a plain free run: the fact copy (without levers) goes on alone, the baseline thing is blanked."""
        self.copies = None
        self.baseline_dirty = True

    def set_levers(self, obj: dict) -> None:
        """Command control.lever: set (or, with reset, clear) the what-if levers on the fact copy.

        In a free run the first lever starts the comparison: the base copy is a clone of the plant at that minute (no
        levers) and is stepped with it, so the interface shows base / fact / difference. When every lever is neutral again
        the base copy is dropped. In a scenario run the base copy is the run without scenario and without levers."""
        if self.plant is None:
            return
        reset = _truthy(obj.get("reset"))
        vals = {}
        if not reset:
            for k in Plant.LEVER_KEYS:
                if obj.get(k) is not None:
                    try:
                        vals[k] = float(obj[k])
                    except (TypeError, ValueError):
                        log.warning("lever %s: bad value %r", k, obj[k])
        if not reset and not vals:
            return
        if self.copies is None and not reset:
            self.copies = CopySet.from_plant(self.plant)
            self.baseline_dirty = True
        fact = self.copies.copies["fact"] if self.copies is not None else self.plant
        try:
            now = fact.set_levers(None if reset else vals)
        except ValueError as e:
            log.warning("lever rejected: %s", e)
            return
        log.info("levers at %s: %s", fact.state.clock.hhmm(), now or "off")
        if not now and self.copies is not None and self.copies.lever_only:
            self._leave_lever_comparison()
        self.publish_point("lever")

    def set_speed(self, value) -> None:
        try:
            v = float(value)
        except (TypeError, ValueError):
            log.warning("speed: bad value %r", value)
            return
        if v <= 0.0:
            self.user_paused = True
            self._pause_published = False
            log.info("paused by command")
            return
        self.speed = v
        was_paused = self.user_paused
        self.user_paused = False
        self._anchor(self.t_min)
        log.info("speed x%.0f%s", v, " (resumed)" if was_paused else "")

    def plant_call(self, issue: str, node: str = "") -> tuple[str, str]:
        """(issue key of the plant, node) for a call from the journal or a module.

        The interface and akt-priority call an issue thing ("issue-7") or a node ("crusher-1");
        the plant knows issue keys ("crusher:1", "grid", "water"). An issue thing becomes its node
        (mod-priority.issue_map), a node is passed as the node, and the plant finds the issue
        there from its state (Plant._issue_at).
        """
        issue = str(issue or "").strip()
        node = str(node or "").strip()
        if issue.startswith("issue-"):
            node = node or str((self.issue_nodes.get(issue) or {}).get("node", ""))
            return "", node
        if issue and ":" not in issue and issue in self.cat.things:
            return "", issue                    # a thing name, not an issue key
        return issue, node

    def call(self, issue: str, node: str = "", via: str = "") -> None:
        """Book a crew for `issue` on the fact copy (journal call or module auto_call)."""
        if self.plant is None or not (issue or node):
            return
        issue, node = self.plant_call(issue, node)
        if not issue and not node:
            log.info("call: issue not known to the simulator, nothing booked")
            return
        if self.copies is not None:
            job = self.copies.copies["fact"].call(node, issue=issue, via=via)
            if self.copies.lever_only:                   # the base copy of the levers is the same shift: same decisions
                self.copies.copies["base"].call(node, issue=issue, via=via)
        else:
            job = self.plant.call(node, issue=issue, via=via)
        self.stats.calls += 1
        if job is None:
            log.info("call %s at %s: no crew job (decision or nothing to fix)", issue, self.plant.state.clock.hhmm())
        else:
            log.info("call %s at %s: %s arrives %.0f, done %.0f", issue, self.plant.state.clock.hhmm(), job.node,
                     job.t_arrive_min, job.t_done_min)

    def remind(self, issue: str, node: str = "", action: str = "remind") -> None:
        """'Not arrived' on the fact copy: remind the called person or call the next one (Plant.remind)."""
        if self.plant is None or not (issue or node):
            return
        issue, node = self.plant_call(issue, node)
        job = self.plant.remind(issue, node, action)
        log.info("%s %s at %s: %s", action, issue or node, self.plant.state.clock.hhmm(),
                 "arrives %.0f" % job.t_arrive_min if job is not None else "nothing on its way")

    # ------------------------------------------------------------- commands
    def handle_event(self, mqtt_topic: str, payload: bytes | str | dict) -> None:
        """One Ditto twin event (or a polled thing part): control, journal, mod-* things."""
        try:
            data = payload if isinstance(payload, dict) else json.loads(payload)
        except (TypeError, ValueError):
            log.warning("event on %s: not JSON", mqtt_topic)
            return
        if not isinstance(data, dict):
            return
        name = thing_name(mqtt_topic, data)
        feats = feature_values(str(data.get("path", "/")), data.get("value"))
        self.apply_features(name, feats, act=True)

    def apply_features(self, name: str, feats: dict, act: bool = True) -> None:
        if name == "control":
            for f, obj in self.cmds.take("control", {k: v for k, v in feats.items() if k in CONTROL_FEATURES}, act):
                self.stats.commands += 1
                self._apply_control(f, obj)
            for f in ("kip", "auto"):          # optional top-level defaults for the next scenario
                if f in feats and feats[f] is not None and act:
                    try:
                        if f == "kip":
                            self.kip = int(float(feats[f]))
                        else:
                            self.auto = _truthy(feats[f])
                    except (TypeError, ValueError):
                        pass
        elif name == "journal":
            for _f, obj in self.cmds.take("journal", {"last": feats.get("last")}, act):
                action = str(obj.get("action", "")).lower()
                if action in CALL_ACTIONS:
                    self.call(str(obj.get("issue", "")), str(obj.get("node", "") or ""), str(obj.get("via", "") or ""))
                elif action in REMIND_ACTIONS:
                    self.remind(str(obj.get("issue", "")), str(obj.get("node", "") or ""), action)
        elif name.startswith("mod-"):
            for f, v in feats.items():
                if f == "processed_sim_time" and isinstance(v, (int, float)):
                    self.processed[name] = float(v)
                elif f == "resend" and isinstance(v, (int, float)) and v >= 0:
                    self.resend[name] = float(v)
            if name == "mod-priority":
                imap = feats.get("issue_map")
                if isinstance(imap, dict):
                    self.issue_nodes.update({k: v for k, v in imap.items() if isinstance(v, dict)})
                for _f, obj in self.cmds.take(name, {"auto_call": feats.get("auto_call")}, act):
                    self.call(str(obj.get("issue", "")), str(obj.get("node", "") or ""))

    def _apply_control(self, f: str, obj: dict) -> None:
        if f == "scenario":
            text = str(obj.get("id") or obj.get("text") or obj.get("scenario") or "")
            preset = str(obj.get("preset") or "")
            safety = _truthy(obj.get("safety"))
            if not text and not preset and not safety:
                self.start_free(obj.get("seed"), obj.get("speed", self.cfg.speed))
                return
            if obj.get("seed") is not None:
                self.seed = int(float(obj["seed"]))
            auto = None if obj.get("auto") is None else _truthy(obj.get("auto"))
            self.start_scenario(text, preset, obj.get("kip"), auto, safety, obj.get("speed"))
        elif f == "speed":
            v = obj.get("value", obj.get("speed", obj.get("x")))
            if obj.get("pause"):
                v = 0.0
            self.set_speed(v)
        elif f == "reset":
            # "Reset 08:00": the snapshot, the seed and the free run at the configured speed (x60)
            self.start_free(obj.get("seed"), obj.get("speed", self.cfg.speed))
        elif f == "cancel":
            self.cancel()
        elif f == "lever":
            self.set_levers(obj)

    def drain_events(self) -> None:
        for topic, payload in self.sink.events():
            self.handle_event(topic, payload)

    def poll_http(self) -> None:
        """When DITTO_URL is set: control and journal every poll_s (the first read only records seqs)."""
        if not self.cfg.ditto_url:
            return
        now = self.clock()
        if now - self._poll_wall < self.cfg.poll_s:
            return
        self._poll_wall = now
        auth = "Basic " + base64.b64encode(f"{self.cfg.ditto_user}:{self.cfg.ditto_password}".encode()).decode()
        for name in ("control", "journal"):
            url = f"{self.cfg.ditto_url.rstrip('/')}/api/2/things/{self.cat.tid(name)}/features"
            try:
                req = urllib.request.Request(url, headers={"Authorization": auth, "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    value = json.loads(resp.read().decode("utf-8"))
            except (urllib.error.URLError, OSError, ValueError) as e:
                if now - self._http_err_wall > 60.0:
                    log.warning("poll %s failed: %s", name, e)
                    self._http_err_wall = now
                continue
            self.apply_features(name, feature_values("/features", value), act=self._polled_once)
        self._polled_once = True

    # ------------------------------------------------------------- publishing
    def speed_fact(self) -> float:
        if self.paused or len(self._samples) < 2:
            return 0.0 if self.paused else float(self.speed)
        now_w, now_t = self._samples[-1]
        ref = None
        for w, t in self._samples:
            if now_w - w <= SPEED_WINDOW_S:
                ref = (w, t)
                break
        if ref is None or now_w - ref[0] < 1.0:
            return float(self.speed)
        return max(0.0, (now_t - ref[1]) / (now_w - ref[0]) * 60.0)

    def _sample(self, t: float) -> None:
        now = self.clock()
        self._samples.append((now, t))
        while self._samples and now - self._samples[0][0] > 2 * SPEED_WINDOW_S:
            self._samples.popleft()

    def _site_service(self, site: dict, st: PlantState) -> None:
        site["state"] = self.site_state(st)
        site["state_ru"] = se.state_ru(site["state"])
        site["speed"] = float(self.speed)
        site["speed_fact"] = float(self.speed_fact())
        site["heartbeat"] = float(self.wall())
        site["degraded"] = float(self.degraded)
        site["seed"] = float(st.seed)

    def _batch_body(self, b, values: dict, t: float) -> dict:
        """Whole batch thing for modify / (policyId, definition, attributes with the block passport, features)."""
        person = self.model.by_name.get("person-geologist")
        thing = {
            "name": b.batch_id, "type": "batch", "name_ru": f"Партия руды {b.batch_id[-4:]}",
            "parent": b.location,
            "responsible": dict({"role": "shift_geologist"}, **({"person": "person-geologist"} if person else {})),
            "passport": {
                "block": [float(b.block_no), "-", "stand", BATCH_TAG_RU.get(b.tag, b.tag) or BATCH_TAG_RU[""]],
                "line": [float(b.line), "-", "stand"],
                "tonnes": [float(b.tonnes), "t", "stand"],
                "est_cu": [round(b.est.cu_pct, 4), "% Cu", "geomet", "оценка блочной модели"],
                "est_axb": [round(b.est.axb, 2), "-", "geomet", "оценка блочной модели"],
                "est_ascu": [round(b.est.ascu_pct, 3), "% of Cu", "geomet", "оценка блочной модели"],
            },
        }
        body = self.model.thing_body(thing)
        feats = self.cat.features(b.batch_id, values, self.run_id, t)
        for f, spec in feats.items():
            body["features"].setdefault(f, {})["properties"] = spec["properties"]
        return body

    def _baseline(self, t: float) -> dict:
        """Features of the baseline thing from the copies (scenario) or the last shift summary (free run).

        Free run: every <thing>_<feature>_base, cum_*_base and alt_* is NO_VALUE (no base copy), so
        the values of an earlier scenario run never stay in Ditto; shift_result has the fixed shape
        of shift_object() with the run id, so a reader can tell whose result it is.
        """
        if self.copies is None:
            out: dict = {f"{thing}_{f}_base": NO_VALUE for thing, feats in BASE_FEATURES for f in feats
                         if f != "state"}
            out.update({f"{thing}_state_base": "" for thing, feats in BASE_FEATURES if "state" in feats})
            for k in ("cum_cu_t_base", "cum_mwh_base", "cum_m3_base", "cum_usd_base", "alt_loud_cum_cu_t",
                      "alt_notwin_cum_cu_t", "alt_loud_cum_usd", "alt_notwin_cum_usd"):
                out[k] = NO_VALUE
            s = self.shift_result
            if s and s.get("run") == self.run_id:
                out["shift_result"] = shift_object(self.run_id, "shift", s.get("t_min", t),
                                                   {"fact": {k: s[k] for k in SHIFT_KEYS if k in s}})
            else:
                out["shift_result"] = shift_object(self.run_id, "none", NO_VALUE)
            return out
        out = {}
        cp = self.copies.copies
        base = se.measured_features(cp["base"].state, self.prm)
        for thing, feats in BASE_FEATURES:
            src = base.get(thing, {})
            for f in feats:
                if f in src:
                    out[f"{thing}_{f}_base"] = src[f]
        bl = cp["base"].state.lines
        out["cum_cu_t_base"] = float(sum(ln.cum_cu_t for ln in bl))
        out["cum_mwh_base"] = float(sum(ln.cum_mwh for ln in bl))
        out["cum_m3_base"] = float(sum(ln.cum_m3 for ln in bl))
        out["cum_usd_base"] = float(sum(ln.cum_usd for ln in bl))
        for alt, name in (("loud", "loud"), ("notwin", "no_twin")):
            c = cp.get(name)
            out[f"alt_{alt}_cum_cu_t"] = float(sum(ln.cum_cu_t for ln in c.state.lines)) if c else NO_VALUE
            out[f"alt_{alt}_cum_usd"] = float(sum(ln.cum_usd for ln in c.state.lines)) if c else NO_VALUE
        sr = self.copies.shift_result()
        out["shift_result"] = shift_object(self.run_id, "scenario", sr["t_min"], sr["copies"])
        return out

    def _thin(self, snap: dict, reason: str, t: float) -> None:
        """Keep the message count inside the rate budget: site passport things go out less often.

        Trucks, faces and roads (SLOW_TYPES) in rotation, each one at every SLOW_EVERY-th checkpoint;
        people and instruments (CHECKPOINT_TYPES) at checkpoints, not on the live points between them.
        The first point of a run, a cancel and a pause carry every thing.
        """
        if self._first_point or reason in FULL_REASONS:
            return
        if self._slow_index is None:
            slow = sorted(n for n, typ in self.cat.things.items() if typ in SLOW_TYPES)
            self._slow_index = {n: i for i, n in enumerate(slow)}
        live = not self._is_checkpoint(t)
        tick = int(round(t / self.cp_min)) % SLOW_EVERY
        for name in list(snap):
            typ = self.cat.things.get(name)
            if typ in SLOW_TYPES:
                if live or self._slow_index.get(name, 0) % SLOW_EVERY != tick:
                    del snap[name]
            elif typ in CHECKPOINT_TYPES and live:
                del snap[name]

    def publish_point(self, reason: str, st: PlantState | None = None) -> int:
        """Publish every physical thing and batch of the fact state (plus baseline, validation-sim)."""
        if st is None:
            if self.plant is None:
                return 0
            st = self.plant.state
        t = st.clock.t_min
        snap = se.measured_features(st, self.prm)
        self._site_service(snap["site"], st)
        self._thin(snap, reason, t)
        now_batches = {bid: b.location for bid, b in st.batches.items()}
        creates = [bid for bid in now_batches if bid not in self.known_batches]
        moves = [bid for bid, loc in now_batches.items()
                 if bid in self.known_batches and self.known_batches[bid] != loc]
        gone = [bid for bid in self.known_batches if bid not in now_batches]
        gone += [bid for bid in self.stale_batches if bid not in now_batches and bid not in gone]
        if self.purge_batches:
            # batch things of an earlier process (its deletes may have been lost): this process
            # does not know them, so it deletes every number it does not use itself
            self.purge_batches = False
            gone += [n for n in (f"batch-{i:04d}" for i in range(1, BATCH_PURGE_MAX + 1))
                     if n not in now_batches and n not in gone]
        repeat, recreate = [], []
        if self._is_checkpoint(t):
            for bid in list(self.deleted_batches):
                if bid in now_batches:
                    del self.deleted_batches[bid]
                    continue
                repeat.append(bid)
                self.deleted_batches[bid] -= 1
                if self.deleted_batches[bid] <= 0:
                    del self.deleted_batches[bid]
            for bid in list(self.created_batches):
                if bid not in now_batches or bid in creates:
                    if bid not in now_batches:
                        del self.created_batches[bid]
                    continue
                recreate.append(bid)
                self.created_batches[bid] -= 1
                if self.created_batches[bid] <= 0:
                    del self.created_batches[bid]
            if abs(t / BATCH_HEAL_MIN - round(t / BATCH_HEAL_MIN)) < EPS:
                recreate += [bid for bid in now_batches if bid not in creates and bid not in recreate]
        for bid in creates:
            self.sink.raw(bid, "/", self._batch_body(st.batches[bid], snap[bid], t), "modify")
            self.created_batches[bid] = BATCH_CREATE_REPEATS
        for bid in recreate:
            self.sink.raw(bid, "/", self._batch_body(st.batches[bid], snap[bid], t), "modify")
        for bid in moves:
            self.sink.raw(bid, "/attributes/_parents", self.cat.tid(now_batches[bid]), "modify")
        if self.copies is not None or self.baseline_dirty:
            snap["baseline"] = self._baseline(t)
            self.baseline_dirty = False
        if self.truth_dirty or self._first_point:
            snap["validation-sim"] = {"truth_log": "\n".join(self.truth[-TRUTH_LINES:])}
            self.truth_dirty = False
        missing = self.sink.snapshot(snap, self.run_id, t)
        for bid in gone + [b for b in repeat if b not in gone]:
            self.sink.raw(bid, "/", None, "delete")
        for bid in gone:
            if bid in self.known_batches or bid in self.stale_batches:
                self.deleted_batches[bid] = BATCH_DELETE_REPEATS
        self.known_batches = now_batches
        self.stale_batches = set()
        self._first_point = False
        self._last_pub_t = t
        self._last_pub_wall = self.clock()
        self._hb_wall = self._last_pub_wall
        self._sample(t)
        s = self.stats
        s.points += 1
        s.batches_created += len(creates)
        s.batches_moved += len(moves)
        s.batches_deleted += len(gone)
        s.unacked += missing
        if self.sink.dry:
            s.log.append((t, reason))
        if missing:
            log.warning("point %s at %.0f: %d messages not acked", reason, t, missing)
        return missing

    def heartbeat(self) -> None:
        """Site only: fresh heartbeat (pause) without moving the model."""
        st = self.plant.state
        site = se.measured_features(st, self.prm)["site"]
        self._site_service(site, st)
        self.sink.snapshot({"site": site}, self.run_id, st.clock.t_min)
        self._hb_wall = self.clock()
        self._sample(st.clock.t_min)
        self.stats.heartbeats += 1

    # ------------------------------------------------------------------ pace
    def _anchor(self, t: float) -> None:
        self._anchor_wall = self.clock()
        self._anchor_t = t

    def _is_checkpoint(self, t: float) -> bool:
        return abs(t / self.cp_min - round(t / self.cp_min)) < EPS

    def _step(self, dt: float) -> None:
        if self.copies is not None:
            self.copies.step(dt)
        else:
            self.plant.step(dt)

    def _barrier(self, t: float) -> None:
        """Wait until every barrier module confirms its tact point at or before t (or time out)."""
        mods = self.cfg.barrier
        if not mods:
            return
        run_no = self.run_no
        deadline = self.clock() + self.cfg.barrier_timeout_s
        self.stats.barrier_waits += 1
        while True:
            self.drain_events()
            self.poll_http()
            if self.run_no != run_no or self.plant is None:
                return                                   # a command restarted the run
            for m, t_req in list(self.resend.items()):
                if abs(t_req - t) < EPS:
                    del self.resend[m]
                    self.stats.resends += 1
                    log.info("resend of point %.0f requested by %s", t, m)
                    self.publish_point("resend")
            need = {m: t - math.fmod(t, MODULE_TACT_MIN.get(m, self.cp_min)) for m in mods}
            if all(self.processed.get(m, -math.inf) >= need[m] - EPS for m in mods):
                return
            now = self.clock()
            if now > deadline:
                self.degraded = 1.0
                self.stats.barrier_timeouts += 1
                late = [m for m in mods if self.processed.get(m, -math.inf) < need[m] - EPS]
                log.warning("barrier at %.0f: no confirmation from %s in %.0f s; run marked degraded", t, late,
                            self.cfg.barrier_timeout_s)
                return
            if now - self._hb_wall >= self.cfg.heartbeat_s:
                self.heartbeat()
            self.sleep(0.1)

    def tick(self) -> float:
        """One loop iteration; returns the wall seconds the loop may sleep."""
        self.drain_events()
        self.poll_http()
        if self.plant is None:
            if self.cfg.scenario or self.cfg.preset or self.cfg.safety:
                self.start_scenario(self.cfg.scenario, self.cfg.preset, self.cfg.kip, self.cfg.auto,
                                    self.cfg.safety)
            else:
                self.start_free()
            return 0.0
        if self.paused:
            if not self._pause_published:
                self._pause_published = True
                self.publish_point("pause")
            elif self.clock() - self._hb_wall >= self.cfg.heartbeat_s:
                self.heartbeat()
            return 0.1
        self._pause_published = False
        now = self.clock()
        due = self._anchor_t + (now - self._anchor_wall) * self.speed / 60.0
        t = self.t_min
        if due < t + 1.0 - EPS:
            return max(0.0, (t + 1.0 - due) * 60.0 / self.speed)
        if due - t > REANCHOR_LAG_MIN:
            due = t + REANCHOR_LAG_MIN
        while self.t_min + 1.0 <= due + EPS and not self.paused:
            self._step(1.0)
            t = self.t_min
            if self.paused:                                # auto pause at 20:00 of a scenario
                self._pause_published = True
                self.publish_point("auto-pause")
                break
            if self._is_checkpoint(t):
                self.publish_point("checkpoint")
                self._barrier(t)
                if self.plant is None or self.paused:
                    break
                lag = self._anchor_t + (self.clock() - self._anchor_wall) * self.speed / 60.0 - t
                if lag > REANCHOR_LAG_MIN:
                    self._anchor(t)
                    break
            elif (self.speed <= LIVE_SPEED_MAX and t - self._last_pub_t >= self.cfg.publish_min - EPS
                  and self.clock() - self._last_pub_wall >= self.cfg.min_publish_gap_s):
                self.publish_point("live")
        return 0.0

    def loop(self, stop=lambda: False) -> None:
        t_end = self.clock() + self.cfg.duration_s if self.cfg.duration_s > 0 else math.inf
        while not stop() and self.clock() < t_end:
            hint = self.tick()
            if hint > 0.0:
                self.sleep(min(hint, 0.25))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build(cfg: Config) -> tuple[Runner, Sink]:
    cat = publish.Catalog(cfg.things_json)
    pub = publish.Publisher(cfg.mqtt_host, cfg.mqtt_port, cfg.writer, cfg.qos, "merge", cat, cfg.max_rate,
                            cfg.ramp_s)
    sink = Sink(pub, dry=cfg.dry_run)
    return Runner(cfg, sink), sink


def main(argv: list[str] | None = None) -> int:
    cfg = Config.from_env()
    ap = argparse.ArgumentParser(prog="service", description="Aktogay simulator service (akt-sim)")
    ap.add_argument("--mqtt-host", default=cfg.mqtt_host)
    ap.add_argument("--mqtt-port", type=int, default=cfg.mqtt_port)
    ap.add_argument("--ditto-url", default=cfg.ditto_url, help="HTTP polling of control (optional)")
    ap.add_argument("--seed", type=int, default=cfg.seed)
    ap.add_argument("--speed", type=float, default=cfg.speed, help="model minutes per wall minute")
    ap.add_argument("--max-rate", type=float, default=cfg.max_rate)
    ap.add_argument("--ramp", type=float, default=cfg.ramp_s)
    ap.add_argument("--qos", type=int, choices=(0, 1), default=cfg.qos)
    ap.add_argument("--barrier", default=",".join(cfg.barrier), help="module things to wait for, comma separated")
    ap.add_argument("--barrier-timeout", type=float, default=cfg.barrier_timeout_s)
    ap.add_argument("--fact-policy", choices=("offline", "module"), default=cfg.fact_policy)
    ap.add_argument("--warmup-publish-min", type=float, default=cfg.warmup_publish_min)
    ap.add_argument("--publish-min", type=float, default=cfg.publish_min)
    ap.add_argument("--heartbeat", type=float, default=cfg.heartbeat_s)
    ap.add_argument("--poll", type=float, default=cfg.poll_s)
    ap.add_argument("--duration", type=float, default=0.0, help="wall seconds, 0 = until stopped")
    ap.add_argument("--dry-run", action="store_true", help="no MQTT: build and count messages")
    ap.add_argument("--scenario", default="", help="start in this scenario, e.g. crusher:1+grid")
    ap.add_argument("--preset", default="")
    ap.add_argument("--kip", type=int, default=None)
    ap.add_argument("--auto", type=int, default=None)
    ap.add_argument("--safety", action="store_true")
    ap.add_argument("--log-level", default="INFO")
    a = ap.parse_args(argv)
    logging.basicConfig(level=getattr(logging, a.log_level.upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(message)s")
    cfg.mqtt_host, cfg.mqtt_port, cfg.ditto_url = a.mqtt_host, a.mqtt_port, a.ditto_url
    cfg.seed, cfg.speed, cfg.max_rate, cfg.ramp_s, cfg.qos = a.seed, a.speed, a.max_rate, a.ramp, a.qos
    cfg.barrier = tuple(x.strip() for x in a.barrier.split(",") if x.strip())
    cfg.barrier_timeout_s, cfg.fact_policy = a.barrier_timeout, a.fact_policy
    cfg.warmup_publish_min, cfg.publish_min = a.warmup_publish_min, a.publish_min
    cfg.heartbeat_s, cfg.poll_s, cfg.duration_s, cfg.dry_run = a.heartbeat, a.poll, a.duration, a.dry_run
    cfg.scenario, cfg.preset, cfg.kip, cfg.safety = a.scenario, a.preset, a.kip, a.safety
    cfg.auto = None if a.auto is None else bool(a.auto)

    runner, sink = build(cfg)
    stop = []
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, lambda *_: stop.append(1))
        except (ValueError, OSError):
            pass
    topics = [f"opentwins/twin/events/{sink.cat.ns}/{name}" for name in EVENT_THINGS]
    sink.connect(topics)
    log.info("akt-sim: seed %d, x%.0f, max %.0f msg/s, barrier %s, %s", cfg.seed, cfg.speed, cfg.max_rate,
             list(cfg.barrier) or "off", "dry run" if cfg.dry_run else f"mqtt://{cfg.mqtt_host}:{cfg.mqtt_port}")
    t0 = time.monotonic()
    try:
        runner.loop(lambda: bool(stop))
    finally:
        sink.close()
    s = runner.stats
    log.info("done %s after %.0f s: model %s, %d points, %d heartbeats, %d messages, %d not acked, "
             "batches +%d ~%d -%d, %d commands, %d calls, barrier waits %d timeouts %d, degraded %.0f",
             runner.run_id, time.monotonic() - t0, runner.plant.state.clock.hhmm() if runner.plant else "-",
             s.points, s.heartbeats, sink.sent, sink.unacked, s.batches_created, s.batches_moved,
             s.batches_deleted, s.commands, s.calls, s.barrier_waits, s.barrier_timeouts, runner.degraded)
    return 0 if sink.unacked == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
