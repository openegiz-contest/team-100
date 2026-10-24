"""Simulator service (sim/service.py) without a broker: commands, pacing, published things."""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sim import publish, service  # noqa: E402
from sim.state import NO_VALUE  # noqa: E402
from tests.support import prm  # noqa: E402


class FakeClock:
    def __init__(self):
        self.now = 1000.0
        self.unix = 1_800_000_000.0

    def __call__(self):
        return self.now

    def sleep(self, s):
        self.now += s
        self.unix += s

    def wall(self):
        return self.unix


def make_runner(**kw):
    cfg = service.Config(dry_run=True, warmup_publish_min=30.0, publish_min=1.0, min_publish_gap_s=0.0, **kw)
    cat = publish.Catalog()
    pub = publish.Publisher(command="merge", catalog=cat, max_rate=0.0)
    sink = service.Sink(pub, dry=True)
    clock = FakeClock()
    runner = service.Runner(cfg, sink, prm(), clock=clock, sleep=clock.sleep, wall=clock.wall)
    return runner, sink, clock


def event(name, path, value, seq=None):
    if seq is not None:
        value = {"properties": {"value": dict(value, seq=seq)}}
    return (f"opentwins/twin/events/kz.aktogay/{name}",
            json.dumps({"topic": f"kz.aktogay/{name}/things/twin/events/modified", "path": path, "value": value}))


class TestParsing(unittest.TestCase):
    def test_feature_values_paths(self):
        obj = {"seq": 3, "value": 300}
        wrapped = {"properties": {"value": obj, "unit": ""}}
        self.assertEqual(service.feature_values("/", {"features": {"speed": wrapped}}), {"speed": obj})
        self.assertEqual(service.feature_values("/features", {"speed": wrapped}), {"speed": obj})
        self.assertEqual(service.feature_values("/features/speed", wrapped), {"speed": obj})
        self.assertEqual(service.feature_values("/features/speed/properties", wrapped["properties"]), {"speed": obj})
        self.assertEqual(service.feature_values("/features/speed/properties/value", obj), {"speed": obj})
        self.assertEqual(service.feature_values("/attributes/x", 1), {})
        self.assertEqual(service.feature_values("/features/speed/properties/unit", ""), {})

    def test_command_log_seq(self):
        log = service.CommandLog()
        self.assertEqual(log.take("control", {"speed": {"seq": 1}}, act=False), [])
        self.assertEqual(log.take("control", {"speed": {"seq": 1}}), [])                 # same seq
        self.assertEqual(len(log.take("control", {"speed": {"seq": 2}})), 1)
        self.assertEqual(log.take("control", {"speed": {"seq": 2}}), [])
        self.assertEqual(len(log.take("control", {"speed": {"value": 60}})), 1)          # event without seq
        self.assertEqual(log.take("control", {"speed": {"value": 60}}, act=False), [])   # polled without seq
        self.assertEqual(log.take("control", {"speed": "bad"}), [])
        # a writer that started its seq again is still heard when its wall clock is later
        self.assertEqual(len(log.take("control", {"scenario": {"seq": 31, "t_wall": 100.0}})), 1)
        self.assertEqual(log.take("control", {"scenario": {"seq": 31, "t_wall": 100.0}}), [])   # same command again
        self.assertEqual(log.take("control", {"scenario": {"seq": 2, "t_wall": 90.0}}), [])     # older
        self.assertEqual(len(log.take("control", {"scenario": {"seq": 3, "t_wall": 120.0}})), 1)
        self.assertEqual(log.take("control", {"scenario": {"seq": 3, "t_wall": 120.0}}), [])

    def test_thing_name(self):
        self.assertEqual(service.thing_name("opentwins/twin/events/kz.aktogay/control", {}), "control")
        self.assertEqual(service.thing_name("", {"topic": "kz.aktogay/journal/things/twin/events/merged"}), "journal")

    def test_truthy(self):
        self.assertTrue(service._truthy(1) and service._truthy("1") and service._truthy("true"))
        self.assertFalse(service._truthy(0) or service._truthy("0") or service._truthy("") or service._truthy(None))


class TestRunner(unittest.TestCase):
    def test_free_run_start_and_pacing(self):
        r, sink, clock = make_runner()
        r.tick()
        self.assertTrue(r.run_id.startswith("s42-free-0001-"))
        self.assertEqual(r.t_min, 8 * 60)
        # WARMUP announced, warm-up snapshots at 06:30, 07:00, 07:30 and 08:00 (hook); no second 08:00 point
        reasons = [x[1] for x in r.stats.log]
        self.assertEqual(reasons.count("warmup"), 4)
        self.assertEqual(reasons[-1], "warmup")
        self.assertEqual(r.stats.log[-1][0], 8 * 60)
        snap = sink.last_snapshot
        self.assertEqual(snap["site"]["state"], "RUN")
        self.assertEqual(snap["site"]["speed"], 60.0)
        self.assertNotIn("baseline", snap)                     # copies only in scenarios
        self.assertEqual(sink.snapshot_names[0], ("site",))    # WARMUP announced first
        self.assertIn("validation-sim", sink.snapshot_names[1])  # truth log with the first point of the run
        self.assertNotIn("validation-sim", snap)               # then only when it changes
        names = [k for k in snap if not k.startswith("batch-")]
        slow = [k for k in names if r.cat.things.get(k) in service.SLOW_TYPES]
        # 41 plant things (4 crews) + 2 stripping excavators + 12 people + 11 instruments at every checkpoint;
        # trucks, faces, roads, drill rigs and dozers (58) in rotation, one sixth per checkpoint
        self.assertEqual(len(names) - len(slow), 69)
        self.assertEqual(len(slow), 10)
        self.assertEqual(snap["site"]["state_ru"], "работает")
        n_slow = sum(1 for typ in r.cat.things.values() if typ in service.SLOW_TYPES)
        self.assertEqual(n_slow, 58)
        first = sink.snapshot_names[1]                      # first point of the run carries every thing
        self.assertEqual(sum(1 for k in first if r.cat.things.get(k) in service.SLOW_TYPES), n_slow)
        self.assertTrue(all(not f.endswith("_base") for v in snap.values() for f in v))
        creates = [op for op in sink.raw_ops if op[1] == "/" and op[2] == "modify"]
        self.assertGreaterEqual(len(creates), 4)                 # initial batches created as things
        # x60: one model minute per wall second, no publishing before the first model minute is due
        n0 = r.stats.points
        hint = r.tick()
        self.assertGreater(hint, 0.0)
        clock.sleep(1.0)
        r.tick()
        self.assertEqual(r.t_min, 8 * 60 + 1)
        if r.stats.log[-1] == (8 * 60 + 1, "live"):
            live = sink.snapshot_names[-1]                  # between checkpoints: plant things only
            self.assertNotIn("person-kip", live)
            self.assertNotIn("truck-01", live)
            self.assertIn("sag-1", live)
        clock.sleep(4.0)
        r.tick()
        self.assertEqual(r.t_min, 8 * 60 + 5)
        self.assertEqual([x[1] for x in r.stats.log[n0:]][-1], "checkpoint")
        self.assertEqual(r.stats.log[-1][0], 8 * 60 + 5)

    def test_scenario_command_cancel_reset(self):
        r, sink, clock = make_runner()
        r.tick()
        run1 = r.run_id
        r.handle_event(*event("control", "/features/scenario", {"id": "crusher:1", "kip": 2, "speed": 300}, seq=1))
        self.assertIsNotNone(r.copies)
        self.assertNotEqual(r.run_id, run1)
        self.assertTrue(r.run_id.startswith("s42-scen-0002-"))
        self.assertEqual(r.speed, 300.0)
        self.assertEqual(set(r.copies.copies), {"fact", "base"})
        snap = sink.last_snapshot
        self.assertIn("baseline", snap)
        self.assertIn("line-1_tph_base", snap["baseline"])
        self.assertIn("shift_result", snap["baseline"])
        self.assertNotIn("tph_base", snap["line-1"])
        self.assertEqual(snap["site"]["scenario"], "crusher:1")
        # same seq again: ignored
        r.handle_event(*event("control", "/features/scenario", {"id": "crusher:1"}, seq=1))
        self.assertEqual(r.stats.commands, 1)
        # run to the first checkpoint at x300: 5 model minutes per wall second
        clock.sleep(1.0)
        r.tick()
        self.assertEqual(r.t_min, 8 * 60 + 5)
        self.assertEqual(r.plant.state.line(1).crusher.state, "STOP")
        r.handle_event(*event("control", "/features/cancel", {}, seq=1))
        self.assertIsNone(r.plant.state.scenario)
        self.assertEqual(r.stats.commands, 2)
        r.handle_event(*event("control", "/features/reset", {"seed": 7}, seq=1))
        self.assertIsNone(r.copies)
        self.assertEqual(r.seed, 7)
        self.assertTrue(r.run_id.startswith("s7-free-0003-"))
        self.assertEqual(r.t_min, 8 * 60)
        self.assertEqual(r.speed, 60.0)                          # reset returns to the configured speed

    def test_merge_event_and_fork(self):
        r, sink, clock = make_runner()
        r.tick()
        patch = {"scenario": {"properties": {"value": {"seq": 5, "preset": "fork", "kip": 1}}}}
        r.handle_event("opentwins/twin/events/kz.aktogay/control",
                       json.dumps({"topic": "kz.aktogay/control/things/twin/events/merged", "path": "/features",
                                   "value": patch}))
        self.assertEqual(set(r.copies.copies), {"fact", "base", "loud", "no_twin"})
        b = sink.last_snapshot["baseline"]
        self.assertNotEqual(b["alt_loud_cum_cu_t"], NO_VALUE)
        self.assertEqual(sink.last_snapshot["site"]["scenario"], "fork")   # dose:1 stays hidden

    def test_pause_heartbeat_and_journal_call(self):
        r, sink, clock = make_runner()
        r.tick()
        r.handle_event(*event("control", "/features/scenario", {"id": "crusher:2"}, seq=1))
        r.handle_event(*event("control", "/features/speed", {"value": 0}, seq=1))
        self.assertTrue(r.paused)
        r.tick()
        self.assertEqual(sink.last_snapshot["site"]["state"], "PAUSED")
        self.assertEqual(sink.last_snapshot["site"]["speed_fact"], 0.0)
        hb0 = r.stats.heartbeats
        clock.sleep(2.5)
        r.tick()
        self.assertEqual(r.stats.heartbeats, hb0 + 1)
        self.assertEqual(set(sink.last_snapshot), {"site"})
        t = r.t_min
        r.handle_event(*event("journal", "/features/last", {"action": "call", "issue": "crusher:2", "role": "x"}, seq=1))
        self.assertEqual(r.stats.calls, 1)
        self.assertEqual(r.t_min, t)                                    # a call does not move the model
        r.handle_event(*event("control", "/features/speed", {"value": 1200}, seq=2))
        self.assertFalse(r.paused)
        self.assertEqual(r.speed, 1200.0)

    def test_call_of_an_issue_thing_books_the_crew(self):
        """The interface calls an issue thing ("issue-3") or a node; the plant gets the node through
        mod-priority.issue_map and finds the issue there: the crew of the crusher is booked."""
        r, sink, clock = make_runner()
        r.tick()
        r.handle_event(*event("control", "/features/scenario", {"id": "crusher:1"}, seq=1))
        r.handle_event(*event("mod-priority", "/features/issue_map",
                              {"properties": {"value": {"issue-3": {"node": "crusher-1", "kind": "crusher_stop"}}}}))
        self.assertEqual(r.plant_call("issue-3"), ("", "crusher-1"))
        self.assertEqual(r.plant_call("crusher-1"), ("", "crusher-1"))
        self.assertEqual(r.plant_call("crusher:1"), ("crusher:1", ""))
        self.assertEqual(r.plant_call("issue-9"), ("", ""))                   # unknown issue thing
        r.handle_event(*event("journal", "/features/last", {"action": "call", "issue": "issue-3", "role": "x"}, seq=1))
        fact = r.copies.copies["fact"]
        self.assertIn("crusher:1", fact._jobs)
        self.assertEqual(fact._jobs["crusher:1"].node, "crusher-1")
        r.tick()
        clock.sleep(1.0)
        r.tick()
        self.assertEqual(fact.state.people["person-crusher-mech"].state, "TRAVEL")

    def test_auto_pause_at_shift_end(self):
        r, sink, clock = make_runner()
        r.tick()
        r.handle_event(*event("control", "/features/scenario", {"id": "grid", "speed": 1200}, seq=1))
        for _ in range(400):
            clock.sleep(0.5)
            r.tick()
            if r.paused:
                break
        self.assertTrue(r.paused)
        self.assertEqual(r.t_min, 20 * 60)
        self.assertEqual(sink.last_snapshot["site"]["state"], "PAUSED")
        self.assertIn("shift_result", sink.last_snapshot["baseline"])
        self.assertEqual(sink.last_snapshot["baseline"]["shift_result"]["t_min"], 20 * 60)

    def test_module_events_barrier_and_auto_call(self):
        r, sink, clock = make_runner(barrier=("mod-losses", "mod-ore"), barrier_timeout_s=0.5)
        r.tick()
        r.handle_event(*event("mod-losses", "/features/processed_sim_time", {"properties": {"value": 480.0}}))
        self.assertEqual(r.processed["mod-losses"], 480.0)
        clock.sleep(5.0)
        r.tick()                      # checkpoint 08:05 without confirmations: times out, degraded
        self.assertEqual(r.t_min, 8 * 60 + 5)
        self.assertEqual(r.degraded, 1.0)
        self.assertEqual(r.stats.barrier_timeouts, 1)
        r.handle_event(*event("mod-priority", "/features/auto_call", {"issue": "crusher:1"}, seq=1))
        self.assertEqual(r.stats.calls, 1)

    def test_baseline_of_a_new_run_replaces_the_old_one(self):
        """Every run starts with its own baseline: run id in shift_result, fixed shape (a Ditto merge
        overwrites every leaf), and in a free run no *_base value of an earlier scenario."""
        r, sink, clock = make_runner()
        r.tick()
        first = next(n for n in sink.snapshot_names if "baseline" in n)
        self.assertIn("baseline", first)
        r.handle_event(*event("control", "/features/scenario", {"preset": "fork", "kip": 1}, seq=1))
        sr = sink.last_snapshot["baseline"]["shift_result"]
        self.assertEqual(sr["run"], r.run_id)
        self.assertEqual(sr["kind"], "scenario")
        self.assertEqual(set(sr["copies"]), set(service.SHIFT_COPIES))
        self.assertGreater(sr["copies"]["loud"]["cu_t"], -1.0 + 1e-9)
        # back to a free run: the loud copy and every *_base value are cleared, not left from "fork"
        r.handle_event(*event("control", "/features/reset", {"seed": 42}, seq=1))
        snaps = [n for n in sink.snapshot_names if "baseline" in n]
        self.assertTrue(snaps)
        b = r._baseline(r.t_min)
        self.assertEqual(b["shift_result"]["run"], r.run_id)
        self.assertEqual(b["shift_result"]["kind"], "none")
        self.assertEqual(b["shift_result"]["copies"]["loud"]["cu_t"], NO_VALUE)
        self.assertEqual(set(b["shift_result"]["copies"]), set(service.SHIFT_COPIES))
        self.assertEqual(b["line-2_tph_base"], NO_VALUE)
        self.assertEqual(b["alt_loud_cum_cu_t"], NO_VALUE)
        self.assertEqual(b["line-1_state_base"], "")
        # shift end in a free run: the summary goes into copies.fact of the same shape
        summary = {"t_min": 1200.0, "cu_t": 300.0, "ore_t": 90000.0, "energy_mwh": 3000.0,
                   "water_m3": 50000.0, "usd": 4.0e6, "l1_cu_t": 150.0}
        r.hooks.on_shift_end(r.plant.state, summary)
        self.assertEqual(r.shift_result["run"], r.run_id)
        sr = r._baseline(1200.0)["shift_result"]
        self.assertEqual((sr["kind"], sr["t_min"], sr["copies"]["fact"]["cu_t"]), ("shift", 1200.0, 300.0))
        self.assertNotIn("l1_cu_t", sr["copies"]["fact"])
        # a summary of another run (an earlier run of the process) is never published under this run
        r.shift_result = dict(summary, run="s42-free-0001-old")
        sr = r._baseline(1200.0)["shift_result"]
        self.assertEqual((sr["run"], sr["kind"], sr["copies"]["fact"]["cu_t"]), (r.run_id, "none", NO_VALUE))
        # and a reset drops the summary of the run before
        r.hooks.on_shift_end(r.plant.state, summary)
        r.handle_event(*event("control", "/features/reset", {"seed": 42}, seq=2))
        self.assertEqual(r._baseline(r.t_min)["shift_result"]["kind"], "none")

    def test_batch_deletes_purged_and_repeated(self):
        r, sink, clock = make_runner()
        r.tick()
        deletes = [op[0] for op in sink.raw_ops if op[2] == "delete"]
        alive = set(r.known_batches)
        # first point of the process: numbers it does not use are deleted (things of a former process)
        self.assertIn("batch-0099", deletes)
        self.assertFalse(alive & set(deletes))
        # a batch the plant drops is deleted, then again at the next checkpoints
        bid = "batch-0098"
        r.known_batches[bid] = "line-1"
        n0 = len(sink.raw_ops)
        for _ in range(4):
            clock.sleep(5.0)
            r.tick()
        again = [op[0] for op in sink.raw_ops[n0:] if op[2] == "delete" and op[0] == bid]
        self.assertGreaterEqual(len(again), 2)
        self.assertLessEqual(len(again), 1 + service.BATCH_DELETE_REPEATS)
        # creates are sent again too (a create lost under load would leave merges Ditto refuses),
        # and every live batch once a model hour
        n1 = len(sink.raw_ops)
        while r.t_min < 9 * 60:
            clock.sleep(5.0)
            r.tick()
        heal = {op[0] for op in sink.raw_ops[n1:] if op[1] == "/" and op[2] == "modify"}
        self.assertTrue(set(r.known_batches) <= heal, set(r.known_batches) - heal)

    def test_bad_scenario_falls_back(self):
        r, sink, clock = make_runner()
        r.tick()
        r.handle_event(*event("control", "/features/scenario", {"id": "nonsense:9"}, seq=1))
        self.assertIsNone(r.copies)
        self.assertIsNotNone(r.plant)
        self.assertEqual(r.plant.state.mode, "free")


if __name__ == "__main__":
    unittest.main()
