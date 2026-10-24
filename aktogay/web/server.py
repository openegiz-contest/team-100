"""akt-web: static files and a small /api that proxies Ditto and InfluxDB.

Design section 6 of the stand. The browser never sees platform credentials:
this process holds them and forwards a fixed list of requests.

  GET  /healthz                       process alive (no platform call)
  GET  /api/state                     all kz.aktogay things (Ditto search, size 200); read once per STATE_REFRESH_S
                                      for all browsers together (a tab never starts a read of its own)
  GET  /api/thing?id=<thingId>        one thing, raw JSON with _modified and _revision
  GET  /api/history?thing=<name>&field=<f1,f2>&range=2h[&run=<idSimulationRun>]
                                      InfluxDB points of the features, by sim_time
  GET  /api/journal?range=24h         rows written to journal.last (InfluxDB)
  POST /api/scenario {id, preset, kip, safety, auto, speed, seed}   -> control.scenario (id may carry a start and a
                                                                 magnitude per token: crusher:1@90=4.5, see sim/events.py)
  POST /api/cancel   {}                                       -> control.cancel
  POST /api/reset    {}                                       -> control.reset
  POST /api/speed    {value}                                  -> control.speed
  POST /api/lever    {feed_1?, feed_2?, p80_um?, dose_gt?, reset?}  -> control.lever (what-if levers of the MODEL, not of the
                                                                 plant: feed 80..120 % of the line rate, grind P80 target
                                                                 160..200 um or 0 = off, collector dose 15..40 g/t or 0 = off;
                                                                 reset 1 clears them; a value outside its range is refused)
  POST /api/call     {issue, role, text, via?}                -> journal.last (action "call"; via "deputy" or "head":
                                                                 the main person is busy on a work permit)
  POST /api/snooze   {issue, role, reason}                    -> journal.last (action "snooze")
  POST /api/remind   {issue, role, text, next?}               -> journal.last (action "remind" or "next":
                                                                 the called person has not arrived)
  POST /api/mech     {issue, status, person?, text?}          -> journal.mech (status of the called person from the
                                                                 mechanic's screen: accepted, enroute, onsite, help, done)

Reads: Ditto HTTP (search, things) and InfluxDB Flux. Writes: merge patches on
the control and journal things only, header x-correlation-id akt-web-<thing>,
so Telegraf keeps one series per writer. The simulator is never addressed.

Standard library only; Python 3.12.
"""
from __future__ import annotations

import base64
import csv
import io
import json
import logging
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

log = logging.getLogger("akt-web")

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.environ.get("AKT_STATIC") or os.path.join(HERE, "static")
PORT = int(os.environ.get("PORT", "8000"))
NS = os.environ.get("AKT_NAMESPACE", "kz.aktogay")

DITTO_URL = os.environ.get("DITTO_URL", "http://ditto-nginx:80").rstrip("/")
DITTO_USER = os.environ.get("DITTO_USER", "ditto")
DITTO_PASSWORD = os.environ.get("DITTO_PASSWORD", "")
INFLUX_URL = os.environ.get("INFLUX_URL", "http://influxdb:8086").rstrip("/")
INFLUX_TOKEN = os.environ.get("INFLUXDB_TOKEN", "")
INFLUX_ORG = os.environ.get("INFLUX_ORG", "opentwins")
INFLUX_BUCKET = os.environ.get("INFLUX_BUCKET", "default")

# One read of the whole twin costs Ditto a retrieval per thing (150) and about 0.5 MB of JSON. It is made by one
# thread every STATE_REFRESH_S while somebody asks (STATE_IDLE_S), whatever the number of tabs and their poll
# period (22.10: a tab polled every 2 s, each answer waited for its own read under a lock). A browser gets the
# last read at once; it is told "no link" only when that read is older than STATE_STALE_S.
STATE_REFRESH_S = float(os.environ.get("AKT_STATE_REFRESH_S", "3"))
STATE_STALE_S = float(os.environ.get("AKT_STATE_STALE_S", "30"))
STATE_IDLE_S = 20.0
# Things published in rotation, each one every 30 model minutes (trucks, faces, ramps, drills, dozers, the dump road)
# and the calibration report that changes once: read every STATE_SLOW_S, not with every read of the rest. Reading
# these 62 things cost Ditto more than reading the other 88 (23.10).
STATE_SLOW_S = float(os.environ.get("AKT_STATE_SLOW_S", "10"))
SLOW_PREFIXES = ("truck-", "dozer-", "drill-", "face-", "ramp-", "road-")
SLOW_EXACT = ("validation-calib",)
INFLUX_CACHE_S = float(os.environ.get("AKT_INFLUX_CACHE_S", "5"))
TIMEOUT_DITTO = 8
TIMEOUT_INFLUX = 20
MAX_BODY = 16 * 1024

RE_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
RE_FIELD = re.compile(r"^[A-Za-z0-9_-]{1,60}$")
RE_RANGE = re.compile(r"^([1-9][0-9]{0,2})([mhd])$")
RE_RUN = re.compile(r"^[A-Za-z0-9._:-]{1,80}$")
RE_SCENARIO = re.compile(r"^[a-z0-9_:+@.=]{0,200}$")   # crusher:1, grid, hard:1+grid, crusher:1@90=4.5 (start min, magnitude)
RE_ISSUE = re.compile(r"^issue-[0-9]{1,6}$")
RE_PERSON = re.compile(r"^person-[a-z0-9-]{1,30}$")
LEVER_RANGES = {"feed_1": (80.0, 120.0, False), "feed_2": (80.0, 120.0, False),      # key -> (min, max, 0 = off allowed)
                "p80_um": (160.0, 200.0, True), "dose_gt": (15.0, 40.0, True)}       # = lev_* rows of sim/params_lev.py
MECH_STATUS = ("accepted", "enroute", "onsite", "help", "done")     # accepted, on the way, on site, need help, done
MECH_LOG_MAX = 12

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".jpg": "image/jpeg",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".woff2": "font/woff2",
}


class UpstreamError(Exception):
    def __init__(self, status: int, text: str):
        super().__init__(text)
        self.status = status


# ---------------------------------------------------------------------------
# Ditto
# ---------------------------------------------------------------------------
def _ditto_headers(extra: dict | None = None) -> dict:
    token = base64.b64encode(f"{DITTO_USER}:{DITTO_PASSWORD}".encode()).decode()
    h = {"Authorization": f"Basic {token}", "Accept": "application/json"}
    if extra:
        h.update(extra)
    return h


def ditto(method: str, path: str, body: dict | None = None, headers: dict | None = None):
    data = None
    h = _ditto_headers(headers)
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(DITTO_URL + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_DITTO) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raise UpstreamError(e.code, f"Ditto {e.code}: {e.read()[:300].decode('utf-8', 'replace')}") from e
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise UpstreamError(502, f"Ditto unreachable: {e}") from e


THING_FIELDS = "thingId,policyId,definition,attributes,features,_modified,_revision,_created"


def slow_filter() -> str:
    """RQL: the things of the slow tier."""
    parts = [f'like(thingId,"{NS}:{p}*")' for p in SLOW_PREFIXES] + [f'eq(thingId,"{NS}:{n}")' for n in SLOW_EXACT]
    return "or(" + ",".join(parts) + ")"


def fast_filter() -> str:
    """RQL: the namespace without the slow tier."""
    parts = [f'not(like(thingId,"{NS}:{p}*"))' for p in SLOW_PREFIXES] + [f'not(eq(thingId,"{NS}:{n}"))' for n in SLOW_EXACT]
    return f'and(like(thingId,"{NS}:*"),' + ",".join(parts) + ")"


def search_things(flt: str | None = None) -> list:
    items = []
    cursor = None
    for _ in range(5):  # at most 1000 things; the stand has about 150
        option = "size(200)" + (f",cursor({cursor})" if cursor else "")
        q = urllib.parse.urlencode({"filter": flt or f'like(thingId,"{NS}:*")', "option": option, "fields": THING_FIELDS})
        page = ditto("GET", f"/api/2/search/things?{q}") or {}
        items.extend(page.get("items", []))
        cursor = page.get("cursor")
        if not cursor:
            break
    return items


class StateCache:
    """The last read of the twin as ready JSON bytes, kept fresh by one background thread.

    get() answers from memory when the read is younger than 2 * refresh_s; otherwise (first request, a long
    idle gap, a thread that keeps failing) it reads once under a lock, and a second caller waits for that
    read instead of making its own. A failed read gives the old bytes while they are younger than stale_s,
    then UpstreamError.
    """

    def __init__(self, fetch, refresh_s: float = 2.5, stale_s: float = 30.0, idle_s: float = 20.0,
                 clock=time.time, thread: bool = True, fetch_slow=None, slow_s: float = 10.0):
        self.fetch, self.refresh_s, self.stale_s, self.idle_s, self.clock = fetch, refresh_s, stale_s, idle_s, clock
        self.fetch_slow, self.slow_s = fetch_slow, slow_s
        self.slow: list = []
        self.slow_t = -1e18
        self.slow_reads = 0
        self.use_thread = thread
        self.body: bytes | None = None
        self.t = 0.0
        self.asked = 0.0
        self.reads = 0
        self.failures = 0
        self._read_lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def _read(self) -> None:
        things = self.fetch()
        if self.fetch_slow is not None and self.clock() - self.slow_t >= self.slow_s:
            try:
                self.slow = self.fetch_slow()
                self.slow_t = self.clock()
                self.slow_reads += 1
            except UpstreamError:
                if not self.slow:                      # nothing to show yet: the read as a whole failed
                    raise
        if self.slow:
            things = things + self.slow
        self.body = json.dumps({"now": self.clock(), "count": len(things), "things": things},
                               ensure_ascii=False).encode("utf-8")
        self.t = self.clock()
        self.reads += 1

    def get(self) -> bytes:
        now = self.clock()
        self.asked = now
        body, t = self.body, self.t
        if body is not None and now - t <= 2 * self.refresh_s:
            self._start()
            return body
        with self._read_lock:
            if self.t > t and self.body is not None:        # another caller has just read it
                return self.body
            try:
                self._read()
            except UpstreamError:
                self.failures += 1
                if self.body is not None and self.clock() - self.t <= self.stale_s:
                    return self.body
                raise
        self._start()
        return self.body

    def _start(self) -> None:
        if self.use_thread and self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="state-refresh", daemon=True)
            self._thread.start()

    def refresh_if_wanted(self) -> bool:
        """One round of the background thread: read when somebody asked lately. True when it read."""
        if self.clock() - self.asked > self.idle_s or not self._read_lock.acquire(blocking=False):
            return False
        try:
            self._read()
            return True
        except UpstreamError as e:
            self.failures += 1
            log.warning("state read failed: %s", e)
            return False
        finally:
            self._read_lock.release()

    def _loop(self) -> None:
        while True:
            t0 = time.monotonic()
            try:
                self.refresh_if_wanted()
            except Exception:  # noqa: BLE001 - the thread must outlive any single failure
                log.exception("state refresh")
            time.sleep(max(0.2, self.refresh_s - (time.monotonic() - t0)))


STATE = StateCache(lambda: search_things(fast_filter()), STATE_REFRESH_S, STATE_STALE_S, STATE_IDLE_S,
                   fetch_slow=lambda: search_things(slow_filter()), slow_s=STATE_SLOW_S)


def state_bytes() -> bytes:
    return STATE.get()


class TtlCache:
    """Small time-to-live cache for InfluxDB answers: the same card or journal asked by several tabs is read once."""

    def __init__(self, ttl_s: float, clock=time.time, limit: int = 200):
        self.ttl_s, self.clock, self.limit = ttl_s, clock, limit
        self.items: dict = {}
        self.lock = threading.Lock()

    def get(self, key, fn):
        now = self.clock()
        with self.lock:
            hit = self.items.get(key)
            if hit and now - hit[0] < self.ttl_s:
                return hit[1]
        value = fn()
        with self.lock:
            if len(self.items) >= self.limit:
                self.items = {k: v for k, v in self.items.items() if now - v[0] < self.ttl_s}
            self.items[key] = (now, value)
        return value


_influx_cache = TtlCache(INFLUX_CACHE_S)


def merge_features(thing: str, features: dict) -> None:
    """PATCH merge on /features: keeps other features and their definitions."""
    ditto("PATCH", f"/api/2/things/{NS}:{thing}/features", features,
          {"Content-Type": "application/merge-patch+json", "x-correlation-id": f"akt-web-{thing}"})


def feature_value(thing: str, feature: str, default=None):
    try:
        v = ditto("GET", f"/api/2/things/{NS}:{thing}/features/{feature}/properties/value")
        return default if v is None else v
    except UpstreamError:
        return default


def current_value(thing: str, feature: str):
    """properties.value of a feature that a command object will follow: {} when there is none yet
    (404); UpstreamError when Ditto does not answer. A guessed {} would restart seq at 1, and the
    simulator drops every seq it has seen (it remembers the highest), so the command would be lost."""
    try:
        v = ditto("GET", f"/api/2/things/{NS}:{thing}/features/{feature}/properties/value")
    except UpstreamError as e:
        if e.status == 404:
            return {}
        raise
    return {} if v is None else v


def next_seq(thing: str, feature: str) -> int:
    cur = current_value(thing, feature)
    seq = 0
    if isinstance(cur, dict):
        try:
            seq = int(float(cur.get("seq", 0)))
        except (TypeError, ValueError):
            seq = 0
    return max(seq + 1, 1)


def site_clock() -> tuple[str, float]:
    run = feature_value("site", "idSimulationRun", "")
    sim_time = feature_value("site", "sim_time", -1.0)
    try:
        sim_time = float(sim_time)
    except (TypeError, ValueError):
        sim_time = -1.0
    return (str(run) if run is not None else ""), sim_time


def control_patch(cur, obj: dict) -> dict:
    """Merge patch that leaves exactly obj in the value: keys of the current object that obj
    lacks are set to null (RFC 7396 removes them), so a preset or kip of an earlier
    scenario cannot stick to the next one."""
    patch = dict(obj)
    if isinstance(cur, dict):
        for k in cur:
            if k not in obj:
                patch[k] = None
    return patch


def write_control(feature: str, payload: dict) -> dict:
    run, sim_time = site_clock()
    cur = current_value("control", feature)
    seq = 0
    if isinstance(cur, dict):
        try:
            seq = int(float(cur.get("seq", 0)))
        except (TypeError, ValueError):
            seq = 0
    obj = {"seq": max(seq + 1, 1), "t_wall": round(time.time(), 1), "sim_time": sim_time, "run": run}
    obj.update(payload)
    merge_features("control", {
        feature: {"properties": {"value": control_patch(cur, obj)}},
        "idSimulationRun": {"properties": {"value": run}},
        "sim_time": {"properties": {"value": sim_time}},
    })
    return obj


def lever_payload(body: dict) -> dict:
    """Validated body of control.lever: numbers inside the ranges of LEVER_RANGES, nothing else; {reset: 1} clears all."""
    if body.get("reset"):
        return {"reset": 1}
    payload: dict = {}
    for k, (lo, hi, off) in LEVER_RANGES.items():
        if body.get(k) in (None, ""):
            continue
        try:
            v = float(body[k])
        except (TypeError, ValueError):
            raise ValueError("bad lever value: " + k) from None
        if v != v or v in (float("inf"), float("-inf")) or not ((off and v == 0.0) or lo <= v <= hi):
            raise ValueError("lever %s outside %g..%g%s" % (k, lo, hi, " (or 0 = off)" if off else ""))
        payload[k] = v
    if not payload:
        raise ValueError("no lever given")
    return payload


def write_journal(action: str, issue: str, role: str, text: str, via: str = "") -> dict:
    run, sim_time = site_clock()
    obj = {"seq": next_seq("journal", "last"), "issue": issue, "action": action, "role": role,
           "text": text, "sim_time": sim_time, "t_wall": round(time.time(), 1), "run": run}
    if via in ("deputy", "head"):
        obj["via"] = via            # the main person is busy on a permit: the deputy or the shift head goes
    patch = dict(obj)
    if "via" not in patch:
        patch["via"] = None             # a merge patch keeps old keys: a call without via must not inherit the via of an earlier call
    merge_features("journal", {
        "last": {"properties": {"value": patch}},
        "idSimulationRun": {"properties": {"value": run}},
        "sim_time": {"properties": {"value": sim_time}},
    })
    return obj


def write_mech(issue: str, status: str, person: str = "", text: str = "") -> dict:
    """Status of the called person (screen ?view=mech) into journal.mech. The value keeps the last entry and, per issue,
    the log of statuses with model times (a merge patch replaces arrays, so the log is read and extended here); entries
    of an earlier run are set to null in the same patch."""
    if not RE_ISSUE.match(issue):
        raise ValueError("bad issue")
    if status not in MECH_STATUS:
        raise ValueError("bad status")
    if person and not RE_PERSON.match(person):
        raise ValueError("bad person")
    run, sim_time = site_clock()
    cur = current_value("journal", "mech")
    cur = cur if isinstance(cur, dict) else {}
    try:
        seq = int(float(cur.get("seq", 0))) + 1
    except (TypeError, ValueError):
        seq = 1
    items = cur.get("items") if isinstance(cur.get("items"), dict) else {}
    prev = items.get(issue) if isinstance(items.get(issue), dict) else {}
    log = list(prev.get("log") or []) if prev.get("run") == run else []
    log.append({"s": status, "t": sim_time})
    entry = {"status": status, "person": person, "run": run, "t": sim_time, "t_wall": round(time.time(), 1),
             "text": text[:200], "log": log[-MECH_LOG_MAX:]}
    patch_items = {k: None for k, v in items.items() if isinstance(v, dict) and v.get("run") != run}
    patch_items[issue] = entry
    obj = {"seq": max(seq, 1), "issue": issue, "status": status, "person": person, "run": run, "sim_time": sim_time,
           "t_wall": entry["t_wall"], "items": patch_items}
    merge_features("journal", {
        "mech": {"properties": {"value": obj}},
        "idSimulationRun": {"properties": {"value": run}},
        "sim_time": {"properties": {"value": sim_time}},
    })
    return obj


# ---------------------------------------------------------------------------
# InfluxDB (Flux, annotated CSV)
# ---------------------------------------------------------------------------
def flux(query: str) -> list[dict]:
    """Run a Flux query; returns rows as dicts (all tables merged, values as strings)."""
    req = urllib.request.Request(
        f"{INFLUX_URL}/api/v2/query?org={urllib.parse.quote(INFLUX_ORG)}",
        data=query.encode("utf-8"), method="POST",
        headers={"Authorization": f"Token {INFLUX_TOKEN}", "Content-Type": "application/vnd.flux",
                 "Accept": "application/csv"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_INFLUX) as r:
            text = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise UpstreamError(e.code, f"InfluxDB {e.code}: {e.read()[:300].decode('utf-8', 'replace')}") from e
    except (urllib.error.URLError, OSError) as e:
        raise UpstreamError(502, f"InfluxDB unreachable: {e}") from e
    return parse_annotated_csv(text)


def parse_annotated_csv(text: str) -> list[dict]:
    rows: list[dict] = []
    header: list[str] | None = None
    for rec in csv.reader(io.StringIO(text)):
        if not rec or all(c == "" for c in rec):
            header = None
            continue
        if rec[0].startswith("#"):
            continue
        if header is None:
            header = rec
            continue
        rows.append({k: v for k, v in zip(header, rec) if k})
    return rows


def _num(s: str):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def history(thing: str, fields: list[str], rng: str, run: str | None) -> dict:
    names = " or ".join(f'r._field == "value_{f}_properties_value"' for f in fields + ["sim_time"])
    run_f = f' and r.idSimulationRun == "{run}"' if run else ""
    q = (f'from(bucket:"{INFLUX_BUCKET}") |> range(start:-{rng})'
         f' |> filter(fn:(r) => r._measurement == "mqtt_consumer" and r.thingId == "{NS}:{thing}"{run_f}'
         f' and ({names}))'
         f' |> keep(columns:["_time","_field","_value","idSimulationRun"])')
    by_time: dict[str, dict] = {}
    for r in flux(q):
        rec = by_time.setdefault(r["_time"], {"t": r["_time"]})
        f = r["_field"]
        key = "sim_time" if f == "value_sim_time_properties_value" else f[len("value_"):-len("_properties_value")]
        rec[key] = _num(r["_value"]) if _num(r["_value"]) is not None else r["_value"]
    pts = [p for p in by_time.values() if isinstance(p.get("sim_time"), float) and p["sim_time"] >= 0]
    pts.sort(key=lambda p: (p["sim_time"], p["t"]))
    return {"thing": thing, "fields": fields, "range": rng, "run": run or "", "points": pts}


def journal(rng: str, run: str | None) -> dict:
    run_f = f' and r.idSimulationRun == "{run}"' if run else ""
    q = (f'from(bucket:"{INFLUX_BUCKET}") |> range(start:-{rng})'
         f' |> filter(fn:(r) => r._measurement == "mqtt_consumer" and r.thingId == "{NS}:journal"{run_f}'
         f' and r._field =~ /^value_last_properties_value_/)'
         f' |> keep(columns:["_time","_field","_value"])')
    by_time: dict[str, dict] = {}
    for r in flux(q):
        rec = by_time.setdefault(r["_time"], {"t": r["_time"]})
        key = r["_field"][len("value_last_properties_value_"):]
        v = r["_value"]
        rec[key] = _num(v) if key in ("seq", "sim_time", "t_wall") and _num(v) is not None else v
    rows = sorted(by_time.values(), key=lambda p: p["t"], reverse=True)
    # one row per seq (QoS 1 duplicates possible)
    seen: set = set()
    out = []
    for r in rows:
        k = r.get("seq", r["t"])
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return {"range": rng, "run": run or "", "rows": out[:100]}


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "akt-web/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # quieter: one line per request at DEBUG
        log.debug("%s " + fmt, self.address_string(), *args)

    # -- helpers
    def _send(self, status: int, body: bytes, ctype: str = "application/json; charset=utf-8",
              cache: str = "no-store") -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, obj) -> None:
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _error(self, status: int, text: str) -> None:
        self._json(status, {"error": text})

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ValueError("body too large")
        raw = self.rfile.read(n) if n else b""
        if not raw:
            return {}
        obj = json.loads(raw.decode("utf-8"))
        if not isinstance(obj, dict):
            raise ValueError("object expected")
        return obj

    # -- routing
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        qs = urllib.parse.parse_qs(url.query)
        try:
            if url.path == "/healthz":
                self._send(200, b"ok\n", "text/plain; charset=utf-8")
            elif url.path == "/api/state":
                self._send(200, state_bytes())
            elif url.path == "/api/thing":
                self.api_thing(qs)
            elif url.path == "/api/history":
                self.api_history(qs)
            elif url.path == "/api/journal":
                self.api_journal(qs)
            elif url.path.startswith("/api/"):
                self._error(404, "unknown api")
            else:
                self.static(url.path)
        except UpstreamError as e:
            self._error(502 if e.status >= 500 else e.status, str(e))
        except ValueError as e:
            self._error(400, str(e))
        except Exception as e:  # noqa: BLE001 - last resort, keep the server up
            log.exception("GET %s", self.path)
            self._error(500, f"{type(e).__name__}: {e}")

    def do_POST(self):
        url = urllib.parse.urlsplit(self.path)
        try:
            body = self._body()
            name = url.path[len("/api/"):] if url.path.startswith("/api/") else ""
            if name == "scenario":
                sid = str(body.get("id", ""))
                if not RE_SCENARIO.match(sid):
                    raise ValueError("bad scenario id")
                payload = {"id": sid}
                for k in ("preset",):
                    if body.get(k):
                        payload[k] = str(body[k])[:20]
                for k in ("kip", "safety", "auto", "speed", "seed"):
                    if body.get(k) not in (None, ""):
                        payload[k] = float(body[k])
                self._json(200, {"ok": True, "control": "scenario", "value": write_control("scenario", payload)})
            elif name == "cancel":
                self._json(200, {"ok": True, "control": "cancel", "value": write_control("cancel", {})})
            elif name == "reset":
                payload = {"seed": float(body.get("seed", 42)), "speed": float(body.get("speed", 60)), "start": "08:00"}
                self._json(200, {"ok": True, "control": "reset", "value": write_control("reset", payload)})
            elif name == "speed":
                v = float(body.get("value", 60))
                if v not in (0.0, 60.0, 300.0, 1200.0):
                    raise ValueError("speed must be 0, 60, 300 or 1200")
                self._json(200, {"ok": True, "control": "speed", "value": write_control("speed", {"value": v})})
            elif name == "lever":
                self._json(200, {"ok": True, "control": "lever", "value": write_control("lever", lever_payload(body))})
            elif name in ("call", "snooze", "remind"):
                issue = str(body.get("issue", ""))[:40]
                role = str(body.get("role", ""))[:60]
                text = str(body.get("text") or body.get("reason") or "")[:300]
                if name == "snooze" and not text:
                    raise ValueError("reason required")
                action = ("next" if body.get("next") else "remind") if name == "remind" else name
                via = str(body.get("via", "")) if name == "call" else ""
                self._json(200, {"ok": True, "journal": write_journal(action, issue, role, text, via)})
            elif name == "mech":
                obj = write_mech(str(body.get("issue", "")), str(body.get("status", "")), str(body.get("person", "")),
                                 str(body.get("text", "")))
                self._json(200, {"ok": True, "journal": obj})
            else:
                self._error(404, "unknown api")
        except UpstreamError as e:
            self._error(502 if e.status >= 500 else e.status, str(e))
        except (ValueError, json.JSONDecodeError) as e:
            self._error(400, str(e))
        except Exception as e:  # noqa: BLE001
            log.exception("POST %s", self.path)
            self._error(500, f"{type(e).__name__}: {e}")

    # -- api
    def api_thing(self, qs):
        tid = (qs.get("id") or [""])[0]
        name = tid[len(NS) + 1:] if tid.startswith(NS + ":") else tid
        if not RE_NAME.match(name):
            raise ValueError("bad id")
        self._json(200, ditto("GET", f"/api/2/things/{NS}:{name}?fields={THING_FIELDS}"))

    def api_history(self, qs):
        thing = (qs.get("thing") or [""])[0]
        if thing.startswith(NS + ":"):
            thing = thing[len(NS) + 1:]
        fields = [f for f in (qs.get("field") or [""])[0].split(",") if f]
        rng = (qs.get("range") or ["2h"])[0]
        run = (qs.get("run") or [""])[0] or None
        if not RE_NAME.match(thing) or not fields or len(fields) > 8 or not all(RE_FIELD.match(f) for f in fields):
            raise ValueError("bad thing or field")
        m = RE_RANGE.match(rng)
        if not m or (m.group(2) == "d" and int(m.group(1)) > 7):
            raise ValueError("bad range (max 7d)")
        if run and not RE_RUN.match(run):
            raise ValueError("bad run")
        self._json(200, _influx_cache.get(("h", thing, tuple(fields), rng, run), lambda: history(thing, fields, rng, run)))

    def api_journal(self, qs):
        rng = (qs.get("range") or ["24h"])[0]
        run = (qs.get("run") or [""])[0] or None
        if not RE_RANGE.match(rng) or (run and not RE_RUN.match(run)):
            raise ValueError("bad range or run")
        self._json(200, _influx_cache.get(("j", rng, run), lambda: journal(rng, run)))

    # -- static
    def static(self, path: str):
        rel = urllib.parse.unquote(path).lstrip("/") or "index.html"
        full = os.path.normpath(os.path.join(STATIC, rel))
        if not full.startswith(os.path.normpath(STATIC) + os.sep) and full != os.path.normpath(STATIC):
            self._error(404, "not found")
            return
        if os.path.isdir(full):
            full = os.path.join(full, "index.html")
        if not os.path.isfile(full):
            # any unknown page -> the app shell (views are chosen by ?view=)
            full = os.path.join(STATIC, "index.html")
            if not os.path.isfile(full):
                self._error(404, "not found")
                return
        ext = os.path.splitext(full)[1].lower()
        with open(full, "rb") as f:
            data = f.read()
        self._send(200, data, CONTENT_TYPES.get(ext, "application/octet-stream"), "no-cache")


def main() -> int:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
    if not DITTO_PASSWORD:
        log.warning("DITTO_PASSWORD is empty")
    if not INFLUX_TOKEN:
        log.warning("INFLUXDB_TOKEN is empty")
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    srv.daemon_threads = True
    log.info("akt-web on :%d, static %s, ditto %s, influx %s", PORT, STATIC, DITTO_URL, INFLUX_URL)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
