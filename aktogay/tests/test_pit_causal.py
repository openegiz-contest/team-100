"""The pit is causal, not only named: a closed ramp lengthens the truck cycle, cuts the haul and lowers the stockpile of its
line against the base copy; an ore excavator stop empties the stockpile and stops the SAG (SUBMISSION, table «Объект →
состояние → связь → эффект»)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sim import haul  # noqa: E402
from sim.ore import route_mult  # noqa: E402
from sim.plant import CopySet  # noqa: E402


def run_to(cs, t_end):
    f = cs.copies["fact"]
    while f.t_min < t_end - 1e-9:
        cs.step(min(cs.prm["cal_step_live_min"], t_end - f.t_min))


class PitCausalTest(unittest.TestCase):
    def test_closed_ramp_reaches_the_stockpile(self):
        cs = CopySet(None, 42, "road:1", preset="", kip=1)
        f, b = cs.copies["fact"], cs.copies["base"]
        t0 = f.t_min
        run_to(cs, t0 + 60)
        self.assertEqual(f.state.roads["ramp-1"].state, "CLOSED")
        self.assertEqual(b.state.roads["ramp-1"].state, "OPEN")
        self.assertGreater(route_mult(f.state, 1, cs.prm), route_mult(b.state, 1, cs.prm))
        self.assertGreater(haul.cycle_min(cs.prm, 1) * route_mult(f.state, 1, cs.prm), haul.cycle_min(cs.prm, 1))
        self.assertLess(f.state.fleet.haul_tph, b.state.fleet.haul_tph)
        run_to(cs, t0 + 150)
        self.assertLess(f.state.lines[0].stockpile.level_t, b.state.lines[0].stockpile.level_t)
        self.assertEqual(f.state.roads["ramp-1"].state, "OPEN")              # 2 h closure is over, the detour ends

    def test_pit_stop_reaches_the_sag(self):
        cs = CopySet(None, 42, "pitstop", preset="", kip=1)
        f, b = cs.copies["fact"], cs.copies["base"]
        run_to(cs, f.t_min + 300)
        self.assertTrue(all(e.state == "DOWN" for e in f.state.excavators))
        self.assertLess(f.state.lines[0].stockpile.level_t, b.state.lines[0].stockpile.level_t)
        self.assertLess(f.state.lines[0].sag.feed_tph, b.state.lines[0].sag.feed_tph)
        self.assertLess(f.state.lines[0].cum_cu_t, b.state.lines[0].cum_cu_t)

    def test_drill_stop_runs_the_face_out_and_stops_its_excavator(self):
        cs = CopySet(None, 42, "drill:1", preset="", kip=1)
        f, b = cs.copies["fact"], cs.copies["base"]
        t0 = f.t_min
        run_to(cs, t0 + 30)
        self.assertTrue(all(d.state == "DOWN" for d in f.state.drills if d.face == "face-1"))
        run_to(cs, t0 + 6 * 60)                                  # 4 h of blasted rock left: used up by now
        self.assertLessEqual(f.state.faces["face-1"].blasted_t, 1e-6)
        exc1 = next(e for e in f.state.excavators if e.name == "exc-1")
        self.assertEqual(exc1.tph, 0.0)
        run_to(cs, t0 + 12 * 60)
        self.assertLess(f.state.lines[0].stockpile.level_t, b.state.lines[0].stockpile.level_t - 1000.0)

    def test_dump_dozer_slows_the_stripping_only(self):
        from sim import pit
        cs = CopySet(None, 42, "dozer", preset="", kip=1)
        f, b = cs.copies["fact"], cs.copies["base"]
        run_to(cs, f.t_min + 60)
        self.assertEqual(next(z for z in f.state.dozers if z.place == "road-dump").state, "DOWN")
        self.assertLess(pit.waste_tph(f.state), pit.waste_tph(b.state))
        self.assertAlmostEqual(f.state.lines[0].cum_cu_t, b.state.lines[0].cum_cu_t, places=6)   # the ore is not touched

    def test_outside_the_scenarios_the_blasted_stock_does_not_limit(self):
        from sim import pit
        cs = CopySet(None, 42, "", preset="", kip=1)
        st = cs.copies["fact"].state
        st.faces["face-1"].blasted_t = 0.0
        self.assertFalse(pit.blast_limited(st, "exc-1"))


if __name__ == "__main__":
    unittest.main()
