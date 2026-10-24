"""Influence screen of 24.10.2026 (VALIDATION 9.4): every label, both edges, and the recovery rows with the limit recovery re-solved."""
import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from modules import params as mparams  # noqa: E402
from sim import influence as inf  # noqa: E402
from sim import params as sp  # noqa: E402

T = sp.TABLE


def base_recovery(set_: dict) -> float:
    """Steady recovery of the base copy from the formula of sim/flotation (limit recovery, ASCu correction, rougher kinetics, cleaner)."""
    kt = set_.get("flot_ktau0", T["flot_ktau0"].value)
    cl = set_.get("clean_r0_pct", T["clean_r0_pct"].value)
    r0 = set_.get(inf.R_INF, T[inf.R_INF].value)
    asc = set_.get("blk_ascu_mean_pct", T["blk_ascu_mean_pct"].value)
    rinf = r0 - T["flot_jose_ascu"].value / inf._share(kt, cl) * (asc - T["flot_ascu_ref_pct"].value)
    return rinf * (1.0 - math.exp(-kt)) * cl / 100.0


class EdgesTest(unittest.TestCase):
    def test_a_row_has_the_ends_that_differ_from_its_value(self):
        self.assertEqual(inf.edges(T["pond_m3_0"]), [1.0e6, 1.5e6])                 # value 1.25e6 inside the range: two edges
        self.assertEqual(inf.edges(T["sens_lab_every_h"]), [12.0])                  # value 4 at the bottom of 4-12: one edge
        self.assertEqual(inf.edges(T["crush_kio"]), [])                             # no range: nothing to move
        self.assertEqual(inf._far(T["sens_lab_every_h"]), 12.0)                     # the end farther from the value

    def test_the_tasks_cover_every_edge_and_the_recovery_family_twice(self):
        keys = ["pond_m3_0", "sens_lab_every_h", "blk_ascu_mean_pct", "flot_ktau0"]
        tasks = inf._tasks_for(keys)
        kinds = [(t[0], t[1]) for t in tasks]
        self.assertEqual(sum(1 for k in kinds if k == ("edge", "pond_m3_0")), 2)
        self.assertEqual(sum(1 for k in kinds if k == ("edge", "sens_lab_every_h")), 1)
        self.assertEqual(sum(1 for k in kinds if k == ("refit", "blk_ascu_mean_pct")), 2)
        self.assertEqual(sum(1 for k in kinds if k == ("refit", "flot_ktau0")), 2)
        self.assertFalse(any(k[0] == "refit" and k[1] in ("pond_m3_0", "sens_lab_every_h") for k in kinds))
        for kind, key, x, s in tasks:
            self.assertEqual(s[key], x)
            self.assertEqual(inf.R_INF in s, kind == "refit")


class RefitTest(unittest.TestCase):
    def test_the_refit_keeps_the_base_recovery_of_the_report(self):
        self.assertAlmostEqual(base_recovery({}), T["tgt_2025_rec_pct"].value, delta=0.01)
        for k in inf.RECOVERY_FAMILY:
            for x in inf.edges(T[k]):
                moved = base_recovery({k: x})
                self.assertGreater(abs(moved - 87.2), 0.5, (k, x))                      # without the refit the edge breaks the 87.2 %
                refit = base_recovery({k: x, inf.R_INF: inf.refit_rinf(k, x)})
                self.assertAlmostEqual(refit, 87.2, delta=0.01, msg=(k, x))

    def test_the_edge_up_to_which_the_range_is_compatible_with_the_report(self):
        top = T[inf.R_INF].max
        self.assertAlmostEqual(inf.compatible_edge("blk_ascu_mean_pct"), 7.98, delta=0.01)       # ASCu up to 8.0 %
        self.assertAlmostEqual(inf.compatible_edge("flot_ktau0"), 2.756, delta=0.002)            # kinetics down to 2.75
        self.assertIsNone(inf.compatible_edge("clean_r0_pct"))                                   # the whole range of the cleaner stays inside
        for k in ("blk_ascu_mean_pct", "flot_ktau0"):
            self.assertAlmostEqual(inf.refit_rinf(k, inf.compatible_edge(k)), top, delta=1e-6)


class ClassifyTest(unittest.TestCase):
    def setUp(self):
        mkeys = [p.key for p in mparams.PARAMS][:3]
        self.read = {"sim": ["pond_m3_0", "sens_an_cycle_min", "crush_kio", "blk_ascu_mean_pct"], "modules": mkeys}
        self.scr = {"base_gain": 0.5, "rows": {
            "pond_m3_0": {"dev": 0.4, "edges": [], "refit_edges": []},
            "sens_an_cycle_min": {"dev": 0.01, "edges": [], "refit_edges": []},                  # a vendor row: screened like the rest
            "blk_ascu_mean_pct": {"dev": 0.6, "dev_refit": 0.0, "edges": [], "refit_edges": []}}}

    def test_every_label_is_screened_and_a_row_without_a_range_is_counted_apart(self):
        cl = inf.classify(self.read, self.scr)
        by = {r["key"]: r for r in cl["rows"] if r["table"] == "model"}
        self.assertEqual(by["pond_m3_0"]["cls"], "matters")
        self.assertEqual(by["sens_an_cycle_min"]["cls"], "read_small")                         # vendor, read, small
        self.assertEqual(T["sens_an_cycle_min"].label, "vendor")
        self.assertEqual(by["crush_kio"]["cls"], "read_fixed")                                # project, no range: cannot be moved
        self.assertEqual(by["blk_ascu_mean_pct"]["cls"], "matters")
        self.assertFalse(by["blk_ascu_mean_pct"]["matters_refit"])                            # matters at the edge, not once the report is respected
        self.assertEqual(sum(1 for r in cl["rows"] if r["table"] == "modules" and r["cls"] == "read"), 3)
        self.assertNotIn("read_sourced", {r["cls"] for r in cl["rows"]})
        s = inf.summary(cl["rows"])
        self.assertEqual(sum(s[c] for c in inf.CLASSES), s["total"])
        self.assertEqual(s["total"], len(T) + len(mparams.PARAMS))
        self.assertEqual(s["refit_removes"], ["blk_ascu_mean_pct"])
        self.assertEqual(s["vendor"]["read_small"], 1)
        self.assertEqual(s["assumption"]["matters"], 2)


if __name__ == "__main__":
    unittest.main()
