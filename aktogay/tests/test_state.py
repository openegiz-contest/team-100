import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # aktogay/: packages sim, tests
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sim.state import (Clock, Counters, initial_state, normal, rng_at, topology, u01)
from tests.support import prm


class TestRandom(unittest.TestCase):
    def test_u01_deterministic_and_range(self):
        a = [u01(42, s, "x") for s in range(1000)]
        b = [u01(42, s, "x") for s in range(1000)]
        self.assertEqual(a, b)
        self.assertTrue(all(0.0 < x < 1.0 for x in a))
        self.assertNotEqual(a[:10], [u01(42, s, "y") for s in range(10)])
        self.assertNotEqual(a[:10], [u01(43, s, "x") for s in range(10)])
        self.assertAlmostEqual(sum(a) / len(a), 0.5, delta=0.03)

    def test_normal_moments(self):
        z = [normal(7, s, "n") for s in range(4000)]
        m = sum(z) / len(z)
        sd = math.sqrt(sum((x - m) ** 2 for x in z) / len(z))
        self.assertAlmostEqual(m, 0.0, delta=0.05)
        self.assertAlmostEqual(sd, 1.0, delta=0.05)

    def test_rng_at_stable(self):
        self.assertEqual(rng_at(42, 5, "fleet").random(), rng_at(42, 5, "fleet").random())


class TestClock(unittest.TestCase):
    def test_hours_and_shifts(self):
        c = Clock(t_min=8 * 60)
        self.assertEqual(c.hour(), 8.0)
        self.assertEqual(c.shift_index(), 0)
        c.t_min = 20 * 60 - 1
        self.assertEqual(c.shift_index(), 0)
        c.t_min = 20 * 60
        self.assertEqual(c.shift_index(), 1)
        c.t_min = 6 * 60
        self.assertEqual(c.shift_index(), -1)
        self.assertEqual(Clock(t_min=24 * 60 + 9 * 60 + 20).hhmm(), "09:20")


class TestInitialState(unittest.TestCase):
    def setUp(self):
        self.p = prm()
        self.st = initial_state(self.p)

    def test_lines_and_stock(self):
        st = self.st
        self.assertEqual(len(st.lines), 2)
        self.assertEqual(st.clock.t_min, 6 * 60)
        for n in (1, 2):
            sp = st.line(n).stockpile
            self.assertAlmostEqual(sum(sp.column.values()) + sum(sp.sides.values()), sp.level_t)
            self.assertAlmostEqual(sp.cum_in_t - sp.cum_out_t, sp.level_t)
        self.assertEqual(st.line(1).stockpile.level_t, 11600)
        self.assertEqual(st.line(2).stockpile.level_t, 30000)
        self.assertEqual(len(st.batches), 4)
        q = self.p["cal_line_tph"]
        for n in (1, 2):
            haul = sum(x.tonnes for x in st.pit.haul[n])
            belt = sum(x.tonnes for x in st.line(n).conveyor.belt)
            self.assertAlmostEqual(haul, q * self.p["pit_haul_min"] / 60, delta=1e-6)
            self.assertAlmostEqual(belt, q * self.p["conv_transit_min"] / 60, delta=1e-6)
            pipe = [b for b in st.batches.values() if b.line == n and b.state == "BELT"]
            self.assertEqual(len(pipe), 1)
            self.assertAlmostEqual(pipe[0].tonnes, haul + belt, delta=1e-6)

    def test_base_numbers(self):
        ln = self.st.line(1)
        self.assertAlmostEqual(ln.tph, 3853, delta=1)
        self.assertAlmostEqual(ln.flot.tail_cu, 0.0533, delta=0.0005)
        self.assertAlmostEqual(ln.flot.conc_tph, 56.7, delta=0.1)
        self.assertAlmostEqual(ln.pebble.feed_tph, 578, delta=1)
        self.assertEqual(len(ln.balls), 2)
        self.assertEqual(self.st.fleet.trucks_ready, 31)           # 37 x 0.85
        # ore trucks 17 x 236 + 6 x 136 = 4 828 t per cycle x 0.85 ready x 60 / the cycle of their route
        # (sim/haul.py, mean 30 min as in the 2025 fit) = about 8 200 t/h, above the 7706 t/h both lines need
        from sim import haul as hl
        haul = sum(t.payload_t * 60.0 / hl.cycle_min(self.p, t.line) for t in self.st.trucks if t.duty == "ore") * self.p["fleet_kio"]
        self.assertAlmostEqual(self.st.fleet.haul_tph, haul, delta=1e-6)
        self.assertAlmostEqual(haul, 8200, delta=60)
        self.assertGreater(haul, 2 * self.p["cal_line_tph"])
        # site passport: people, trucks by model, faces, roads, stripping excavators
        self.assertEqual(len(self.st.people), 13)
        self.assertEqual([t.model for t in self.st.trucks].count("CAT 793"), 17)
        self.assertEqual(len(self.st.faces), 5)
        self.assertEqual(len(self.st.roads), 3)
        self.assertEqual(len(self.st.excavators) + len(self.st.waste_excavators), 5)
        for ln in self.st.lines:
            self.assertEqual((ln.cum_cu_t_total, ln.cum_mwh_total, ln.cum_m3_total, ln.cum_usd_total),
                             (0.0, 0.0, 0.0, 0.0))
        self.assertEqual(self.st.crews["crew-kip"].count, 1)

    def test_flotation_grades_set(self):
        for ln in self.st.lines:
            g = ln.flot.feed_cu
            self.assertAlmostEqual(ln.rougher.rconc_cu, g * ln.rougher.stage_recovery / ln.rougher.mass_pull_pct)
            cu_feed = ln.tph * g / 100.0
            cu_rconc = cu_feed * ln.rougher.stage_recovery / 100.0
            tails_t = ln.cleaner.feed_tph - ln.cleaner.conc_tph
            self.assertAlmostEqual(cu_rconc, ln.flot.cu_tph + tails_t * ln.cleaner.tail_cu / 100.0)
            self.assertGreater(ln.cleaner.tail_cu, ln.flot.tail_cu)

    def test_kip2(self):
        st = initial_state(prm(crew_kip=2))
        self.assertEqual(len(st.crews["crew-kip"].slot_free_min), 2)


class TestTopology(unittest.TestCase):
    def test_graph(self):
        t = topology()
        # 41 plant things (4 crews) + 8 people + 2 stripping excavators + 5 faces + 3 roads + 37 trucks + 9 instruments
        self.assertEqual(len(t), 127)                     # + 6 drill rigs + 7 dozers + 4 people of the pit and the grinding control room + 2 pH meters + leach pad and SX-EW
        for info in t.values():
            for p in info.parents:
                self.assertIn(p, t, info.thing_id)
            for f in info.feeds:
                self.assertIn(f, t, info.thing_id)
        roots = [i for i in t.values() if not i.parents]
        self.assertEqual([r.thing_id for r in roots], ["site"])
        self.assertIn("pebble-1", t["sag-1"].feeds)
        self.assertIn("sag-1", t["pebble-1"].feeds)


class TestCounters(unittest.TestCase):
    def test_add(self):
        a = Counters(ore_t=1, cu_conc_t=2)
        a.add(Counters(ore_t=3, usd=5))
        self.assertEqual((a.ore_t, a.cu_conc_t, a.usd), (4, 2, 5))


if __name__ == "__main__":
    unittest.main()
