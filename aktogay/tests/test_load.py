"""Load on the platform (23.10): the browser side cache of akt-web, publishing of batches, the overlay of the stand.

The incident of 23.10 (host asleep for 12 minutes, the Ditto cluster downed itself on wake, after an hour
of starved heartbeats) left a stand that used two cores of four for nothing but reading its own twin. These
tests keep the reductions: one read of the twin for all browsers, no write to a batch that is not there,
and the settings of the overlay that keep the logs and the cluster in bounds.
"""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
for p in (ROOT, WEB):
    if p not in sys.path:
        sys.path.insert(0, p)

import server  # noqa: E402
from tests.test_service import make_runner  # noqa: E402


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class StateCacheTest(unittest.TestCase):
    def cache(self, **kw):
        clk = Clock()
        calls = []

        def fetch():
            calls.append(clk.now)
            if getattr(self, "down", False):
                raise server.UpstreamError(502, "Ditto unreachable")
            return [{"thingId": "kz.aktogay:site", "n": len(calls)}]

        c = server.StateCache(fetch, refresh_s=2.5, stale_s=30.0, idle_s=20.0, clock=clk, thread=False, **kw)
        return c, clk, calls

    def setUp(self):
        self.down = False

    def test_many_callers_one_read(self):
        c, clk, calls = self.cache()
        first = c.get()
        for _ in range(50):                    # 50 tabs polling within the refresh period
            clk.now += 0.05
            self.assertIs(c.get(), first)
        self.assertEqual(len(calls), 1)

    def test_answer_is_json_bytes_of_the_read(self):
        c, clk, calls = self.cache()
        body = c.get()
        self.assertIsInstance(body, bytes)
        import json
        d = json.loads(body.decode("utf-8"))
        self.assertEqual(d["count"], 1)
        self.assertEqual(d["things"][0]["thingId"], "kz.aktogay:site")
        self.assertEqual(d["now"], 1000.0)

    def test_background_round_reads_only_while_somebody_asks(self):
        c, clk, calls = self.cache()
        c.get()
        clk.now += 3.0
        self.assertTrue(c.refresh_if_wanted())
        self.assertEqual(len(calls), 2)
        clk.now += 25.0                        # nobody asked for 25 s: the thread leaves Ditto alone
        self.assertFalse(c.refresh_if_wanted())
        self.assertEqual(len(calls), 2)
        c.get()                                # the next browser gets a fresh read at once
        self.assertEqual(len(calls), 3)

    def test_failed_read_gives_the_old_answer_until_stale(self):
        c, clk, calls = self.cache()
        old = c.get()
        self.down = True
        clk.now += 8.0                         # older than 2 * refresh: read again, fails, old bytes served
        self.assertIs(c.get(), old)
        clk.now += 40.0                        # older than stale_s: the browser is told there is no link
        with self.assertRaises(server.UpstreamError):
            c.get()

    def test_first_read_failure_raises(self):
        c, clk, calls = self.cache()
        self.down = True
        with self.assertRaises(server.UpstreamError):
            c.get()

    def test_slow_tier_is_read_less_often_and_joined(self):
        clk = Clock()
        fast, slow = [], []

        def f():
            fast.append(clk.now)
            return [{"thingId": "kz.aktogay:site"}]

        def sl():
            slow.append(clk.now)
            return [{"thingId": "kz.aktogay:truck-01"}, {"thingId": "kz.aktogay:validation-calib"}]

        import json
        c = server.StateCache(f, refresh_s=2.5, clock=clk, thread=False, fetch_slow=sl, slow_s=10.0)
        d = json.loads(c.get().decode("utf-8"))
        self.assertEqual([t["thingId"] for t in d["things"]],
                         ["kz.aktogay:site", "kz.aktogay:truck-01", "kz.aktogay:validation-calib"])
        self.assertEqual(d["count"], 3)
        for _ in range(6):                           # 18 s of reads every 3 s
            clk.now += 3.0
            c.refresh_if_wanted()
        self.assertEqual(len(fast), 7)
        self.assertLessEqual(len(slow), 3, slow)     # 10 s apart, not every read
        d = json.loads(c.get().decode("utf-8"))
        self.assertEqual(d["count"], 3)              # the slow things stay in the answer between their reads

    def test_slow_tier_failure_keeps_the_last_slow_things(self):
        clk = Clock()
        state = {"down": False}

        def sl():
            if state["down"]:
                raise server.UpstreamError(502, "x")
            return [{"thingId": "kz.aktogay:truck-01"}]

        import json
        c = server.StateCache(lambda: [{"thingId": "kz.aktogay:site"}], clock=clk, thread=False, fetch_slow=sl, slow_s=10.0)
        c.get()
        state["down"] = True
        clk.now += 11.0
        c.refresh_if_wanted()
        d = json.loads(c.get().decode("utf-8"))
        self.assertEqual(d["count"], 2)

    def test_tier_filters_name_the_same_things(self):
        fast, slow = server.fast_filter(), server.slow_filter()
        for p in server.SLOW_PREFIXES:
            self.assertIn(f'not(like(thingId,"kz.aktogay:{p}*"))', fast)
            self.assertIn(f'like(thingId,"kz.aktogay:{p}*")', slow)
        self.assertIn('eq(thingId,"kz.aktogay:validation-calib")', slow)
        # nothing the interface reads live is in the slow tier
        for n in ("site", "mod-priority", "control", "journal", "baseline", "batch-", "issue-", "person-", "exc-"):
            self.assertFalse(any(n.startswith(p) for p in server.SLOW_PREFIXES), n)

    def test_ttl_cache_reads_once_per_period(self):
        clk = Clock()
        t = server.TtlCache(5.0, clock=clk)
        n = []
        for _ in range(10):
            t.get(("j", "24h", None), lambda: n.append(1) or {"rows": []})
        self.assertEqual(len(n), 1)
        clk.now += 6.0
        t.get(("j", "24h", None), lambda: n.append(1) or {"rows": []})
        self.assertEqual(len(n), 2)
        t.get(("j", "2h", None), lambda: n.append(1) or {"rows": []})      # another key is another read
        self.assertEqual(len(n), 3)


class BatchPublishTest(unittest.TestCase):
    """The simulator is the only writer of batch things: it creates them, writes to live ones, deletes them."""

    def run_hours(self, hours):
        r, sink, clock = make_runner()
        while r.t_min < hours * 60:
            clock.sleep(5.0)
            r.tick()
        return r, sink

    def test_no_write_to_a_batch_that_is_not_there(self):
        r, sink = self.run_hours(11)
        ops = sink.raw_ops
        created = {op[0] for op in ops if op[1] == "/" and op[2] == "modify"}
        deleted = {op[0] for op in ops if op[2] == "delete"}
        self.assertTrue(created, "the run should have made batches")
        written = {n for names in sink.snapshot_names for n in names if n.startswith("batch-")}
        # every batch that gets feature writes was created by this process first
        self.assertTrue(written <= created, written - created)
        # and none is written after its delete (the plant never brings a batch back)
        last_write = {}
        for i, names in enumerate(sink.snapshot_names):
            for n in names:
                if n.startswith("batch-"):
                    last_write[n] = i
        self.assertTrue(set(last_write) <= created)
        self.assertTrue(deleted & created, "batches are deleted when consumed")

    def test_a_delete_is_sent_at_most_twice(self):
        r, sink = self.run_hours(11)
        per = {}
        for op in sink.raw_ops:
            if op[2] == "delete":
                per[op[0]] = per.get(op[0], 0) + 1
        purge = {f"batch-{i:04d}" for i in range(1, 100)}
        used = {n: c for n, c in per.items() if n in {op[0] for op in sink.raw_ops if op[2] == "modify"}}
        self.assertTrue(used)
        self.assertLessEqual(max(used.values()), 2, used)    # each failed repeat is a WARN with a stack in Ditto
        self.assertTrue(set(per) & purge)


class OverlayTest(unittest.TestCase):
    """aktogay/compose.yml: what keeps a long run inside the machine (README_dev.md, "Long run")."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "compose.yml"), encoding="utf-8") as f:
            cls.text = f.read()

    def block(self, name):
        m = re.search(rf"^  {re.escape(name)}:\n((?:    .*\n|\n)*)", self.text, re.M)
        self.assertIsNotNone(m, name)
        return m.group(1)

    def test_ditto_services_log_only_warnings_of_ditto_and_rotate(self):
        for n in ("policies", "things", "things-search", "connectivity", "gateway"):
            b = self.block(n)
            self.assertIn("LOG_LEVEL_APPLICATION: WARN", b, n)
            self.assertIn("logging: *akt-logging", b, n)
            self.assertRegex(b, r"cpu_shares: [0-9]{4}", n)

    def test_every_long_running_service_rotates_its_log(self):
        for n in ("mosquitto", "mongodb", "ditto-nginx", "influxdb", "telegraf", "grafana", "extended-api",
                  "akt-models", "akt-modules", "akt-web", "akt-sim"):
            self.assertIn("logging: *akt-logging", self.block(n), n)
        self.assertRegex(self.text, r'max-size: "[0-9]+m"')
        self.assertRegex(self.text, r'max-file: "[0-9]+"')

    def test_modules_gate_knobs_are_set(self):
        b = self.block("akt-modules")
        for k in ("AKT_SETTLE_S", "AKT_RETRY_S", "AKT_MAX_AGE_S", "AKT_DUTY"):
            self.assertIn(k, b)


if __name__ == "__main__":
    unittest.main()
