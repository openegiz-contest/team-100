"""How akt-modules reads Ditto (23.10): the whole twin is not read every poll, and not the things nobody reads.

A full read of the twin cost Ditto a retrieval per thing (150) and half a megabyte of JSON, every 1.5-3 s:
110 % of a core in the things service, 36 % in the gateway. These tests fix the rules of the reduction.
"""
import contextlib
import io
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests import mod_support as ms  # noqa: E402
from modules import losses, main as mod_main, ore, priority  # noqa: E402
from modules.main import PollGate, search_filter  # noqa: E402

RUN = ms.RUN


class FakeDitto:
    """Counts the calls of the modules: probe (GET site), search (whole twin), writes."""
    url = "http://fake"

    def __init__(self, runner_clock):
        self.t = 480.0
        self.run = RUN
        self.probes = 0
        self.searches = []
        self.fail_probe = False
        self.fail_search = False
        self.wall = runner_clock

    def request(self, method, path, body=None, headers=None, retries=3, raw=None):
        if method == "GET" and path.startswith("/api/2/things/kz.aktogay:site"):
            self.probes += 1
            if self.fail_probe:
                return 0, "down"
            return 200, {"features": {"idSimulationRun": {"properties": {"value": self.run}},
                                      "sim_time": {"properties": {"value": self.t}}}}
        return 200, {}

    def search(self, ns, fields="", size=200, flt=None):
        self.searches.append(flt)
        if self.fail_search:
            return []
        return ms.snapshot(self.t, run=self.run)

    def merge_features(self, *a, **k):
        return 200, {}

    def put_thing_if_absent(self, *a, **k):
        return 201, {}

    def delete_thing(self, *a, **k):
        return 204, None


def make_runner(**env):
    old = {k: os.environ.get(k) for k in env}
    os.environ.update({k: str(v) for k, v in env.items()})
    try:
        r = mod_main.Runner(dry_run=True)
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    fake = FakeDitto(None)
    r.ditto = fake
    for w in r.writers.values():
        w.ditto = fake
    r.backfilled = True              # no InfluxDB here
    return r, fake


class ClockPatch:
    """Replaces time.monotonic in modules.main with a settable clock; the dry-run writes print, not here."""

    def __init__(self):
        self.now = 1000.0
        self._orig = None
        self._out = contextlib.redirect_stdout(io.StringIO())

    def __enter__(self):
        self._orig = mod_main.time.monotonic
        mod_main.time.monotonic = lambda: self.now
        self._out.__enter__()
        return self

    def __exit__(self, *a):
        self._out.__exit__(*a)
        mod_main.time.monotonic = self._orig


class FilterTest(unittest.TestCase):
    def test_filter_skips_only_bulk_things_nobody_reads(self):
        flt = search_filter("kz.aktogay")
        self.assertTrue(flt.startswith('and(like(thingId,"kz.aktogay:*")'))
        skipped = re.findall(r'not\(like\(thingId,"kz\.aktogay:([a-z-]+)\*?"\)\)', flt)
        self.assertEqual(sorted(skipped), sorted(p.rstrip("*") for p in mod_main.SEARCH_SKIP))

    def test_nothing_the_modules_read_is_skipped(self):
        """Every thing named in READS / READS_EXTRA, and every dynamic type the store lists, is outside the skip list."""
        names = set(losses.READS) | set(ore.READS) | set(priority.READS) | set(priority.READS_EXTRA)
        names |= {"batch-0001", "issue-1", "person-kip", "piezo-1", "analyzer-1", "weigher-1", "flowmeter-1",
                  "mod-priority", "exc-4"}
        for n in names:
            self.assertFalse(n.startswith(mod_main.SEARCH_SKIP) or n == "baseline", n)

    def test_search_uses_the_filter(self):
        r, fake = make_runner()
        with ClockPatch():
            self.assertTrue(r.poll())
        self.assertEqual(fake.searches, [search_filter("kz.aktogay")])


class GateTest(unittest.TestCase):
    def gate(self):
        return PollGate(settle_s=2.0, retry_s=1.5, max_age_s=10.0, duty=0.5)

    def test_first_read_at_once_then_quiet_while_the_clock_stands(self):
        g = self.gate()
        c = (RUN, 480.0)
        self.assertTrue(g.due(0.0, c, False))
        g.done(0.0, 0.2, c, True)
        for now in (1.2, 2.2, 5.0, 9.0):
            self.assertFalse(g.due(now, c, False), now)
        self.assertTrue(g.due(10.3, c, False))                  # max age

    def test_clock_moved_reads_after_the_settle_time(self):
        g = self.gate()
        g.done(0.0, 0.2, (RUN, 480.0), True)
        new = (RUN, 485.0)
        self.assertFalse(g.due(1.0, new, False))                # first sight of the change
        self.assertFalse(g.due(2.0, (RUN, 490.0), False))       # moving on does not restart the wait
        self.assertTrue(g.due(3.1, (RUN, 490.0), False))        # 2 s after the first change

    def test_pending_point_is_read_again_after_retry(self):
        g = self.gate()
        g.done(0.0, 0.2, (RUN, 480.0), True)
        self.assertFalse(g.due(1.0, (RUN, 480.0), True))
        self.assertTrue(g.due(1.8, (RUN, 480.0), True))

    def test_duty_rule_spaces_slow_reads(self):
        g = PollGate(settle_s=0.0, retry_s=0.0, max_age_s=0.0, duty=0.25)
        g.done(0.0, 2.0, (RUN, 480.0), True)                    # a read of 2 s: 6 s of rest at duty 0.25
        self.assertFalse(g.due(7.9, (RUN, 485.0), True))
        self.assertTrue(g.due(8.1, (RUN, 485.0), True))

    def test_failed_read_is_repeated_not_hammered(self):
        g = self.gate()
        g.done(0.0, 0.1, None, False)
        self.assertFalse(g.due(0.5, (RUN, 480.0), False))
        self.assertTrue(g.due(1.6, (RUN, 480.0), False))

    def test_unanswered_probe_does_not_trigger_reads_before_max_age(self):
        g = self.gate()
        g.done(0.0, 0.2, (RUN, 480.0), True)
        self.assertFalse(g.due(5.0, None, False))
        self.assertTrue(g.due(10.5, None, False))

    def test_new_run_is_a_change_too(self):
        g = self.gate()
        g.done(0.0, 0.2, (RUN, 615.0), True)
        self.assertFalse(g.due(1.0, ("s42-scen-0002", 480.0), False))
        self.assertTrue(g.due(3.1, ("s42-scen-0002", 480.0), False))


class StepTest(unittest.TestCase):
    """Runner.step with a counting Ditto: how many whole reads per minute of a free run at x60."""

    def drive(self, seconds, sim_every=3.5, **env):
        r, fake = make_runner(**env)
        with ClockPatch() as clk:
            next_point = 0.0
            for i in range(int(seconds / 0.5)):
                clk.now = 1000.0 + i * 0.5
                if clk.now - 1000.0 >= next_point:                      # a new point of the free run
                    fake.t += 5.0
                    next_point += sim_every
                r.step()
        return r, fake

    def test_free_run_reads_the_twin_about_once_per_point(self):
        r, fake = self.drive(60.0)
        points = 60.0 / 3.5
        self.assertLessEqual(len(fake.searches), points * 1.5, len(fake.searches))     # was ~ 2.5 per point
        self.assertGreaterEqual(len(fake.searches), points * 0.5, len(fake.searches))  # but it does follow
        self.assertGreaterEqual(fake.probes, 60)                                       # the cheap read each poll

    def test_standing_simulator_costs_one_read_per_max_age(self):
        r, fake = make_runner()
        with ClockPatch() as clk:
            for i in range(120):                                       # 60 s, the clock never moves
                clk.now = 1000.0 + i * 0.5
                r.step()
        self.assertLessEqual(len(fake.searches), 1 + 60 // 10, len(fake.searches))

    def test_ditto_down_does_not_spin(self):
        r, fake = make_runner()
        fake.fail_probe = True
        fake.fail_search = True
        with ClockPatch() as clk:
            for i in range(120):
                clk.now = 1000.0 + i * 0.5
                r.step()
        self.assertLessEqual(len(fake.searches), 45, len(fake.searches))   # retry_s spacing, not every poll

    def test_a_tact_is_still_computed_when_the_point_is_complete(self):
        r, fake = make_runner()
        with ClockPatch() as clk:
            fake.t = 480.0
            r.step()
            self.assertEqual(r.losses.processed, 480.0)
            clk.now += 20.0
            fake.t = 485.0
            r.step()                                                    # first sight of the change
            clk.now += 2.5
            r.step()                                                    # settled: read and compute
        self.assertEqual(r.losses.processed, 485.0)


if __name__ == "__main__":
    unittest.main()
