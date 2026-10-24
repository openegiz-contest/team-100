"""Published stage recovery of the cleaner: two-product formula on the published noisy grades (24.10.2026).

A noisy copy of the true recovery (97 %) was clamped at 100 and the card showed 100 %. Now the recovery is computed from
what is published: concentrate, tail and the rougher concentrate grade. Invariants: it equals the formula on the
published grades within 0.1 pp, and it is below 100 whenever the tail grade is above zero.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sim import sensors as se  # noqa: E402
from sim.plant import CopySet, Plant  # noqa: E402


class StageRecoveryTest(unittest.TestCase):
    def check(self, plant, steps):
        seen = 0
        for _ in range(steps):
            plant.step()
            f = se.measured_features(plant.state, plant.prm)
            for n in (1, 2):
                cl, ro = f["cleaner-%d" % n], f["rougher-%d" % n]
                if cl["stage_recovery"] < 0.0:
                    continue
                r_flows, _ = se.two_product(ro["rconc_cu"], cl["tail_cu"], cl["conc_cu"])
                self.assertLess(abs(r_flows - cl["stage_recovery"]), 0.1)
                if cl["tail_cu"] > 0.0:
                    self.assertLess(cl["stage_recovery"], 100.0)
                self.assertGreater(cl["stage_recovery"], 90.0)
                seen += 1
        self.assertGreater(seen, steps)

    def test_free_run(self):
        p = Plant(None, 42, mode="scenario")
        p.warmup()
        self.check(p, 240)

    def test_with_a_silent_dose_drop(self):
        cs = CopySet(None, 7, "dose:1@0=0.5")
        self.check(cs.copies["fact"], 240)

    def test_mean_is_the_true_value(self):
        p = Plant(None, 3, mode="scenario")
        p.warmup()
        vals = []
        for _ in range(240):
            p.step()
            f = se.measured_features(p.state, p.prm)
            vals.append(f["cleaner-1"]["stage_recovery"])
        truth = p.state.lines[0].cleaner.stage_recovery
        self.assertAlmostEqual(sum(vals) / len(vals), truth, delta=0.5)

    def test_truth_snapshot_is_unchanged(self):
        p = Plant(None, 3, mode="scenario")
        p.warmup()
        p.step()
        t = se.truth_features(p.state)
        self.assertAlmostEqual(t["cleaner-1"]["stage_recovery"], p.state.lines[0].cleaner.stage_recovery)


if __name__ == "__main__":
    unittest.main()
