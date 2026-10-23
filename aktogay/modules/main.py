"""akt-modules runner: polls Ditto, keeps model-time windows, runs the three modules in tacts.

  python -I modules/main.py run              service loop (environment below)
  python -I modules/main.py once [--dry-run] one tact at the latest point, print the result
  python -I modules/main.py check            read Ditto and InfluxDB, print what the modules see

Environment: DITTO_URL (http://ditto-nginx:80), DITTO_USER (ditto), DITTO_PASSWORD,
INFLUX_URL (http://influxdb:8086), INFLUXDB_TOKEN, INFLUX_ORG (opentwins),
INFLUX_BUCKET (default), POLL_S (1.0), AKT_AUTO_CALL (0), AKT_SEED (42), AKT_LOG (INFO).

Tacts run on model time (sim_time), not wall time: a point T is computed
when every thing in READS shows sim_time >= T; akt-priority also waits for
processed_sim_time >= T from akt-losses and akt-ore (the last point that is
a multiple of 15 min for akt-ore). The module repeats processed_sim_time
every second while the simulator stands at T, and writes resend = T when
the point stays incomplete for 3 s (design file 17, section 2).
A new idSimulationRun resets every window, detector and issue.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from modules import losses as losses_mod  # noqa: E402
from modules import ore as ore_mod  # noqa: E402
from modules import priority as priority_mod  # noqa: E402
from modules.clients import Ditto, Influx  # noqa: E402
from modules.params import default  # noqa: E402
from modules.store import NO_VALUE, Store  # noqa: E402
from modules.writer import Catalog, Writer  # noqa: E402

log = logging.getLogger("modules")

SEARCH_FIELDS = "thingId,attributes/_parents,attributes/type,attributes/name_ru,attributes/responsible,attributes/passport,attributes/block,features"
ALIVE_FILE = os.environ.get("AKT_ALIVE_FILE", "/tmp/akt-modules.alive")


def floor_to(t: float, step: float) -> float:
    return float(int(t // step) * step)


class Runner:
    def __init__(self, dry_run: bool = False):
        self.prm = default()
        self.cat = Catalog()
        self.store = Store(self.cat.ns, self.prm["hist_min"])
        url = os.environ.get("DITTO_URL", "http://localhost:8080")
        pw = os.environ.get("DITTO_PASSWORD", "")
        self.ditto = Ditto(url, os.environ.get("DITTO_USER", "ditto"), pw) if pw else None
        tok = os.environ.get("INFLUXDB_TOKEN", "")
        self.influx = Influx(os.environ.get("INFLUX_URL", "http://localhost:8086"), tok,
                             os.environ.get("INFLUX_ORG", "opentwins"), os.environ.get("INFLUX_BUCKET", "default")) \
            if tok else None
        self.poll_s = float(os.environ.get("POLL_S", "1.0"))
        self.seed = int(os.environ.get("AKT_SEED", "42"))
        auto = os.environ.get("AKT_AUTO_CALL", "0") in ("1", "true", "yes")
        self.losses = losses_mod.LossesModule(self.prm, self.store, self.cat.roles)
        self.ore = ore_mod.OreModule(self.prm, self.store)
        self.priority = priority_mod.PriorityModule(self.prm, self.store, self.losses, self.ore, self.cat.roles, auto)
        self.writers = {m.name: Writer(self.ditto, self.cat, m.name, dry_run) for m in (self.losses, self.ore, self.priority)}
        self.run_id = ""
        self.backfilled = False
        self.last_tact_wall = {m.name: 0.0 for m in (self.losses, self.ore, self.priority)}
        self.resent: dict[str, float] = {}
        self.incomplete_since: dict[str, float] = {}
        self.tmax_seen = NO_VALUE
        self.tmax_wall = 0.0
        self.stop = False
        self.issue_names: set[str] = set()

    # ------------------------------------------------------------------ polling
    def poll(self) -> bool:
        if self.ditto is None:
            return False
        items = self.ditto.search(self.cat.ns, SEARCH_FIELDS)
        if not items:
            self.store.last_poll_ok = False
            return False
        self.store.update_from_search(items)
        self.store.last_poll_ok = True
        run = self.store.run_id
        if run and run != self.run_id:
            if self.run_id:
                log.info("new run %s (was %s): reset", run, self.run_id)
            self.on_new_run(run)
        return True

    def on_new_run(self, run: str) -> None:
        self.run_id = run
        # issues of the previous run (ours in the registry, and any left in Ditto by an earlier process)
        stale = {i.name for i in self.priority.issues.values()}
        stale |= {s.name for s in self.store.of_type("issue")}
        self.store.reset()
        self.losses.reset()
        self.ore.reset()
        self.priority.reset()
        for name in stale:
            self.writers["priority"].delete_thing(name)
        self.issue_names.clear()
        self.resent.clear()
        self.incomplete_since.clear()
        self.backfilled = False

    def backfill(self) -> None:
        """Windows from InfluxDB after a start or a run change (the only use of history here)."""
        self.backfilled = True
        if self.influx is None or not self.run_id:
            return
        things = sorted(set(losses_mod.READS) | set(ore_mod.READS))
        fields = sorted({f"value_{f}_properties_value" for f in
                         set(losses_mod.BACKFILL_FIELDS) | set(ore_mod.BACKFILL_FIELDS)})
        rows = self.influx.history(self.run_id, things, fields, since="-12h")
        n = self.store.add_history_rows(rows)
        fc = self.influx.history(self.run_id, ["mod-ore"],
                                 ["value_layers_l1_properties_value", "value_layers_l2_properties_value"], since="-12h")
        k = self.ore.restore(fc)
        log.info("backfill run %s: %d rows, %d points added, %d forecasts restored", self.run_id, len(rows), n, k)

    # ------------------------------------------------------------------ tacts
    def _reads_complete(self, reads, types, t: float) -> tuple[bool, float]:
        """(every READS thing at or past t, max sim_time seen)."""
        names = [n for n in reads if n in self.store.things]
        if len(names) < len(reads) * 0.8:
            return False, NO_VALUE
        tmin = self.store.min_sim_time(names)
        tmax = self.store.max_sim_time(names)
        for typ in types:
            for s in self.store.of_type(typ):
                # a dynamic thing (batch) lowers the minimum; it never completes a point on its own
                # while a READS thing is still missing in this run (tmin NO_VALUE); an orphan (a batch
                # whose delete was lost, far behind the other batches) is skipped, or it would hold
                # every later tact back for good
                if self.store.is_orphan(s):
                    continue
                if s.sim_time != NO_VALUE and (tmin != NO_VALUE or not names):
                    tmin = min(tmin, s.sim_time) if tmin != NO_VALUE else s.sim_time
        return (tmin != NO_VALUE and tmin >= t), tmax

    def due(self, module, reads, types) -> float:
        """Next point to compute for a module, or NO_VALUE."""
        complete, tmax = self._reads_complete(reads, types, 0.0)
        if tmax == NO_VALUE:
            return NO_VALUE
        target = floor_to(tmax, module.tact)
        if module.processed != NO_VALUE and target <= module.processed:
            return NO_VALUE
        ok, _ = self._reads_complete(reads, types, target)
        key = module.name
        now = time.monotonic()
        if tmax != self.tmax_seen:
            self.tmax_seen, self.tmax_wall = tmax, now
        if not ok:
            since = self.incomplete_since.setdefault(key, now)
            # resend only when the simulator stands at the point (barrier) and it stays incomplete:
            # in free run a point is published over a few seconds and completes by itself
            standing = now - self.tmax_wall > 3.0
            if standing and now - since > 3.0 and self.resent.get(key) != target:
                self.resent[key] = target
                self.writers[key].write(module.thing, {"resend": target}, self.run_id, target, partial=True)
                log.info("%s: point %.0f incomplete for 3 s while the simulator stands, resend written", key, target)
            return NO_VALUE
        self.incomplete_since.pop(key, None)
        return target

    def tact_losses(self, t: float) -> None:
        feats = self.losses.compute(t)
        self.writers["losses"].write("mod-losses", feats, self.run_id, t)
        self.last_tact_wall["losses"] = time.monotonic()
        log.info("losses %s: %s", t, feats.get("top_text", "")[:120])

    def tact_ore(self, t: float) -> None:
        feats = self.ore.compute(t)
        self.writers["ore"].write("mod-ore", feats, self.run_id, t)
        self.last_tact_wall["ore"] = time.monotonic()
        log.info("ore %s: %s", t, feats.get("fc_text", "")[:120])

    def tact_priority(self, t: float) -> None:
        feats, issues = self.priority.compute(t, self.seed)
        w = self.writers["priority"]
        for iss in self.priority.new_issues:
            tr = iss.trouble
            w.ensure_thing(iss.name, "issue", tr.node if tr else "site", f"Беда {iss.seq}",
                           {"responsible": {"role": "", "name_ru": tr.role if tr else ""}})
            self.issue_names.add(iss.name)
        for name, f in issues.items():
            w.write(name, f, self.run_id, t)
        for name in self.priority.pruned:
            w.delete_thing(name)
            self.issue_names.discard(name)
        w.write("mod-priority", feats, self.run_id, t)
        self.last_tact_wall["priority"] = time.monotonic()
        log.info("priority %s: %d issues, order %s", t, len(issues), feats.get("order_text", "")[:100])

    def step(self) -> None:
        if not self.poll():
            return
        if not self.backfilled:
            self.backfill()
        t = self.due(self.losses, losses_mod.READS, losses_mod.READS_TYPES)
        if t != NO_VALUE:
            self.tact_losses(t)
        t = self.due(self.ore, ore_mod.READS, ore_mod.READS_TYPES)
        if t != NO_VALUE:
            self.tact_ore(t)
        t = self.due(self.priority, priority_mod.READS, priority_mod.READS_TYPES)
        if t != NO_VALUE:
            ore_ok = self.ore.processed != NO_VALUE and self.ore.processed >= floor_to(t, self.ore.tact)
            if self.losses.processed != NO_VALUE and self.losses.processed >= t and ore_ok:
                self.tact_priority(t)
        self.repeat_processed()

    def repeat_processed(self) -> None:
        """Repeat processed_sim_time once a second while the simulator still stands at that point."""
        site_t = self.store.sim_time("site")
        now = time.monotonic()
        for m in (self.losses, self.ore, self.priority):
            if m.processed == NO_VALUE or site_t == NO_VALUE:
                continue
            last = self.last_tact_wall[m.name]
            if site_t <= m.processed and 1.0 <= now - last <= 60.0 and self.store.s("site", "state") != "PAUSED":
                self.writers[m.name].write(m.thing, {"processed_sim_time": m.processed}, self.run_id, m.processed,
                                           partial=True)
                self.last_tact_wall[m.name] = now

    def run(self) -> int:
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "stop", True))
        signal.signal(signal.SIGINT, lambda *_: setattr(self, "stop", True))
        log.info("akt-modules: Ditto %s, Influx %s, poll %.1f s, auto_call %s", self.ditto.url if self.ditto else "-",
                 self.influx.url if self.influx else "-", self.poll_s, self.priority.auto_env)
        while not self.stop:
            t0 = time.monotonic()
            try:
                self.step()
            except Exception as e:  # keep the service alive; the next poll retries
                log.exception("step failed: %s", e)
            self.touch_alive()
            time.sleep(max(0.05, self.poll_s - (time.monotonic() - t0)))
        return 0

    @staticmethod
    def touch_alive() -> None:
        """Liveness file for the container healthcheck ("process alive", nothing else)."""
        try:
            with open(ALIVE_FILE, "w") as f:
                f.write(str(time.time()))
        except OSError:
            pass

    def once(self) -> int:
        """One tact of every module at the latest point available (no barrier), for smoke tests."""
        if not self.poll():
            print("Ditto: no things read", file=sys.stderr)
            return 1
        self.backfill()
        t = self.store.max_sim_time(losses_mod.READS)
        if t == NO_VALUE:
            print("no sim_time in the things", file=sys.stderr)
            return 1
        tl = floor_to(t, self.losses.tact)
        to = floor_to(t, self.ore.tact)
        self.tact_losses(tl)
        self.tact_ore(to)
        self.tact_priority(tl)
        print(json.dumps({"run": self.run_id, "sim_time": t, "losses": self.losses.processed, "ore": self.ore.processed,
                          "priority": self.priority.processed,
                          "issues": [i.name for i in self.priority.issues.values()],
                          "top": self.losses.results and max(self.losses.results.values(), key=lambda r: abs(r.z)).node},
                         ensure_ascii=False))
        failed = sum(w.failed for w in self.writers.values())
        return 0 if failed == 0 else 1

    def check(self) -> int:
        ok = self.poll()
        print(f"Ditto: {'ok' if ok else 'FAILED'}, {len(self.store.things)} things, run {self.run_id!r}, "
              f"site sim_time {self.store.sim_time('site')}")
        if self.influx is not None and self.run_id:
            rows = self.influx.history(self.run_id, ["sag-1"], ["value_feed_tph_properties_value"], since="-6h")
            print(f"InfluxDB: {len(rows)} points of sag-1.feed_tph in run {self.run_id}")
        missing = [n for n in set(losses_mod.READS) | set(ore_mod.READS) | set(priority_mod.READS)
                   | set(priority_mod.READS_EXTRA) if n not in self.store.things]
        print("missing things: " + (", ".join(sorted(missing)) if missing else "none"))
        return 0 if ok and not missing else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("run", "once", "check"))
    ap.add_argument("--dry-run", action="store_true", help="print writes instead of sending them")
    a = ap.parse_args(argv)
    logging.basicConfig(level=os.environ.get("AKT_LOG", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    r = Runner(dry_run=a.dry_run)
    if a.cmd == "run":
        return r.run()
    if a.cmd == "once":
        return r.once()
    return r.check()


if __name__ == "__main__":
    sys.exit(main())
