"""On/off trial (sim/trial.py): shift design, stand-in policy, statistics, one paired shift."""
import math
import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sim import trial  # noqa: E402
from sim.state import NO_VALUE  # noqa: E402
from tests.support import prm  # noqa: E402

CFG = dict(trial.DEFAULTS, n=1, jobs=1, boot=200)


class TestDesign(unittest.TestCase):
    def test_draw_shift_deterministic_and_valid(self):
        a, b = trial.draw_shift(1001, CFG), trial.draw_shift(1001, CFG)
        self.assertEqual(a, b)
        counts = {2: 0, 3: 0}
        for seed in range(1001, 1061):
            s = trial.draw_shift(seed, CFG)
            counts[len(s.troubles)] += 1
            nodes = [t.node for t in s.troubles]
            self.assertEqual(len(nodes), len(set(nodes)), nodes)
            for t in s.troubles:
                self.assertTrue(8 * 60 <= t.t_start_min <= 18 * 60)
                self.assertEqual(t.hidden, t.kind in trial.HIDDEN)
                if t.hidden:
                    self.assertAlmostEqual(t.t_found_min, t.t_start_min + CFG["detect_min"])
                if t.kind in ("crusher", "trip"):
                    self.assertIn(f"stock{t.line}_t0", s.overrides)
            self.assertEqual(s.overrides["crew_sigma_ln"], 0.4)
        self.assertGreater(counts[2], counts[3])
        self.assertGreater(counts[3], 5)

    def test_miss_draw(self):
        cfg = dict(CFG, miss=1.0)
        s = next(trial.draw_shift(seed, cfg) for seed in range(1001, 1100)
                 if any(t.hidden for t in trial.draw_shift(seed, cfg).troubles))
        for t in s.troubles:
            if t.hidden:
                self.assertTrue(t.missed)
                self.assertEqual(t.t_found_min, NO_VALUE)


class TestPolicy(unittest.TestCase):
    def test_rank_fallback_money_order(self):
        p = prm()
        now = 9 * 60 + 20
        dose = {"issue": "dose:1", "kind": "dose", "crew": "crew-kip", "safety": "", "loss_cu_tph": 0.55,
                "hours_to_loss": 0.0, "repair_h": 0.5, "arrive_h": 0.5, "crew_free_at_min": NO_VALUE,
                "t_known_min": 9 * 60 + 15}
        trip = {"issue": "trip:2", "kind": "trip", "crew": "crew-kip", "safety": "", "loss_cu_tph": 13.7,
                "hours_to_loss": 7.8, "repair_h": 3.0, "arrive_h": 0.5, "crew_free_at_min": NO_VALUE,
                "t_known_min": 9 * 60 + 20}
        order = [t["issue"] for t in trial.rank_fallback([trip, dose], now, p)]
        self.assertEqual(order, ["dose:1", "trip:2"])            # the stock covers the trip repair
        trip_short = dict(trip, hours_to_loss=0.5)
        order = [t["issue"] for t in trial.rank_fallback([dose, trip_short], now, p)]
        self.assertEqual(order, ["trip:2", "dose:1"])            # stock runs out first: crusher first
        safety = dict(dose, issue="piezo", crew="", safety="S0", loss_cu_tph=0.0)
        grid = dict(dose, issue="grid", crew="", loss_cu_tph=3.0)
        order = [t["issue"] for t in trial.rank_fallback([trip_short, dose, grid, safety], now, p)]
        self.assertEqual(order[:2], ["piezo", "grid"])

    def test_load_rank(self):
        fn, name = trial.load_rank()
        self.assertTrue(callable(fn))
        self.assertIn("rank", name)
        p = prm()
        now = 9 * 60 + 20
        dose = {"issue": "dose:1", "kind": "dose", "line": 1, "node": "flot-1", "crew": "crew-kip", "hidden": True,
                "safety": "", "loss_cu_tph": 0.55, "loss_usd_h": 7600.0, "hours_to_loss": 0.0, "repair_h": 0.5,
                "repair_p90_h": 0.8, "arrive_h": 0.5, "crew_free_at_min": NO_VALUE,
                "crew_slots_free_min": [NO_VALUE], "t_known_min": 9 * 60 + 15}
        trip = dict(dose, issue="trip:2", kind="trip", line=2, node="crusher-2", hidden=False, loss_cu_tph=13.7,
                    loss_usd_h=190000.0, hours_to_loss=7.8, repair_h=3.0, repair_p90_h=5.0, t_known_min=now)
        order = fn([trip, dose], now, p, 1)
        self.assertEqual(sorted(order), ["dose:1", "trip:2"])
        self.assertEqual(order[0], "dose:1")                     # the stock covers the trip repair


class TestStats(unittest.TestCase):
    def test_wilson(self):
        lo, hi = trial.wilson(0, 10)
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 0.2775, places=3)
        lo, hi = trial.wilson(5, 10)
        self.assertAlmostEqual(lo, 0.2366, places=3)
        self.assertAlmostEqual(hi, 0.7634, places=3)

    def test_wilcoxon_exact(self):
        # textbook pairs: all positive differences, n = 6 -> W+ = 21, p = 2 / 64
        r = trial.wilcoxon([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        self.assertEqual(r["method"], "exact")
        self.assertAlmostEqual(r["w_plus"], 21.0)
        self.assertAlmostEqual(r["p"], 2 / 64)
        r = trial.wilcoxon([1.0, -1.0, 2.0, -2.0, 0.0])
        self.assertIn("normal", r["method"])
        self.assertAlmostEqual(r["w_plus"], 5.0)                 # ties: ranks 1.5, 1.5, 3.5, 3.5
        self.assertGreater(r["p"], 0.5)
        self.assertEqual(trial.wilcoxon([0.0, 0.0])["n"], 0)

    def test_wilcoxon_normal_matches_exact_for_large_n(self):
        rng = random.Random(3)
        xs = [rng.gauss(0.3, 1.0) for _ in range(40)]
        exact = trial.wilcoxon(xs)
        self.assertEqual(exact["method"], "exact")
        tied = xs + [xs[0]]                                  # one tie forces the normal approximation
        approx = trial.wilcoxon(tied)
        self.assertIn("normal", approx["method"])
        self.assertLess(abs(math.log(max(exact["p"], 1e-6)) - math.log(max(approx["p"], 1e-6))), 1.0)

    def test_summarize_and_bootstrap(self):
        rng = random.Random(1)
        xs = [rng.gauss(0.8, 1.36) for _ in range(100)]
        s = trial.summarize(xs, 2000, random.Random(2))
        self.assertEqual(s["n"], 100)
        lo, hi = s["ci95_mean_bca"]
        self.assertLess(lo, s["mean"])
        self.assertGreater(hi, s["mean"])
        self.assertLess(hi - lo, 1.0)
        self.assertAlmostEqual(s["p0"] + s["p_minus"] + s["p_plus"], 1.0)
        self.assertTrue(0 <= s["p_minus_ci95_wilson"][0] <= s["p_minus"] <= s["p_minus_ci95_wilson"][1] <= 1)
        self.assertEqual(trial.percentile(sorted(xs), 0.0), min(xs))
        self.assertEqual(trial.percentile(sorted(xs), 1.0), max(xs))
        same = trial.summarize([0.0] * 5, 200, random.Random(0))
        self.assertEqual(same["ci95_mean_bca"], [0.0, 0.0])


class TestShift(unittest.TestCase):
    def test_one_paired_shift(self):
        cfg = dict(CFG, no_twin=True)
        row = trial.run_shift((1001, cfg))
        self.assertEqual(set(row["cu_t_2000"]), {"by_value", "by_loud", "base", "no_twin"})
        for name, v in row["cu_t_2000"].items():
            self.assertTrue(math.isfinite(v) and v > 0, name)
            self.assertGreater(row["cu_t_0800"][name], v)              # the night adds copper
        self.assertAlmostEqual(row["d_cu_t"], row["cu_t_2000"]["by_value"] - row["cu_t_2000"]["by_loud"])
        self.assertIn(row["n_troubles"], (2, 3))
        for tr in row["troubles"]:
            self.assertTrue(tr["issue"] in row["bookings"]["by_value"] or tr["kind"] in trial.DECISION
                            or tr["missed"], tr)
        self.assertLessEqual(row["loss_cu_t_2000"]["by_value"], row["loss_cu_t_2000"]["no_twin"] + 5.0)

    def test_fair_baseline_is_the_default(self):
        """Without the twin people still take the hard-ore, grid and reline decisions, only later
        (asis); --no-asis brings back the old baseline where nobody takes them."""
        self.assertTrue(trial.DEFAULTS["asis"])
        self.assertEqual(trial.DEFAULTS["asis_notice_min"], 10.0)
        seed = next(s for s in range(1001, 1100)                  # a deep cut: a ball mill is shed
                    if trial.draw_shift(s, CFG).overrides.get("pow_c2_limit_mw", 999.0) < 210.0)
        row = trial.run_shift((seed, dict(CFG, no_twin=True)))
        grid = next(t for t in row["troubles"] if t["kind"] == "grid")
        rec = row["bookings"]["no_twin"].get(grid["issue"])
        self.assertIsNotNone(rec)
        self.assertEqual(rec["by"], "operator")
        self.assertGreaterEqual(rec["t_call_min"], grid["t_start_min"] + 10.0 - 1e-6)
        row_old = trial.run_shift((seed, dict(CFG, no_twin=True, asis=False)))
        self.assertNotIn(grid["issue"], row_old["bookings"]["no_twin"])
        self.assertGreaterEqual(row["cu_t_2000"]["no_twin"], row_old["cu_t_2000"]["no_twin"] - 1e-6)

    def test_run_trial_small(self):
        doc = trial.run_trial(dict(CFG, n=2, seed0=1003))
        self.assertEqual(doc["n"], 2)
        self.assertIn("d_cu_t_2000", doc["summary"])
        self.assertEqual(doc["summary"]["d_cu_t_2000"]["n"], 2)
        text = trial.format_report(doc)
        self.assertIn("Wilcoxon", text)
        self.assertIn("by_value", text)


if __name__ == "__main__":
    unittest.main()
