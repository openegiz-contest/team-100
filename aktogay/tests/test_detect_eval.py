"""Check of the module «Где теряется медь» on hidden causes (sim/detect_eval.py) and of the false alarms of its CUSUM (sim/cusum_eval.py):
the helpers, the stored result files and the page «Модули» that shows them. The full runs are offline (VALIDATION 8.14, 8.15)."""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sim import cusum_eval, detect_eval  # noqa: E402

STATIC = os.path.join(ROOT, "web", "static")


def load(name):
    with open(os.path.join(STATIC, name), encoding="utf-8") as f:
        return json.load(f)


class DetectEvalTest(unittest.TestCase):
    def test_grid_has_every_cause_line_magnitude_seed(self):
        cs = detect_eval.cases(25)
        causes = [c for c in cs if c.get("cause") and not c.get("preset")]
        n_mag = sum(len(detect_eval.magnitudes(c)) for c in detect_eval.CAUSES)
        self.assertEqual(len(causes), n_mag * 2 * 25)
        self.assertEqual(len([c for c in cs if c.get("preset") == "fork"]), 25)
        self.assertEqual(len([c for c in cs if c.get("cause") is None and not c.get("preset")]), 25)
        self.assertEqual({c["line"] for c in causes}, {1, 2})

    def test_magnitudes_come_from_the_parameter_table(self):
        self.assertEqual(detect_eval.magnitudes("dose"), [0.25, 0.4, 0.5])
        self.assertEqual(detect_eval.magnitudes("cyclone"), [1.0, 2.0])

    def test_one_run_finds_a_clogged_cyclone_and_names_the_role(self):
        r = detect_eval.run_case({"cause": "cyclone", "line": 2, "mag": 2.0, "seed": 1001})
        self.assertTrue(r["detected"])
        self.assertEqual(r["node"], "cyclones-2")
        self.assertTrue(r["role_ok"])
        self.assertGreater(r["latency_loss"], 0)
        self.assertLess(r["latency_loss"], 180)

    def test_summary_of_handmade_rows(self):
        nodes = detect_eval.NODES

        def row(cause, line, det, lat, unsure=False, first=None):
            node = {"dose": "flot", "liner": "sag"}[cause] + "-%d" % line
            return {"seed": 1, "cause": cause, "line": line, "mag": 1, "preset": "", "node": node, "detected": det, "unsure_only": unsure,
                    "latency_loss": lat, "latency_unsure": lat, "role_ok": True if det else None, "role_first": True if det else None,
                    "first_alarm_node": first if first is not None else (node if det else ""), "first_loss": {node: lat} if det else {},
                    "first_unsure": {}, "episodes": {n: 0 for n in nodes}, "unsure_episodes": {n: 0 for n in nodes}, "loss_tacts": {}}

        control = {"seed": 1, "cause": None, "line": None, "mag": None, "preset": "", "episodes": {n: (2 if n == "sag-1" else 0) for n in nodes},
                   "unsure_episodes": {n: 0 for n in nodes}, "first_loss": {}, "first_unsure": {}, "first_alarm_node": "", "loss_tacts": {}}
        rows = [row("dose", 1, True, 60.0), row("dose", 1, True, 120.0), row("dose", 2, False, None), row("liner", 1, True, 300.0, first="flot-1"), control]
        s = detect_eval.summarize(rows, 1)
        d = s["by_cause"]["dose"]
        self.assertEqual((d["n"], d["detected"], d["missed"]), (3, 2, 1))
        self.assertAlmostEqual(d["detected_share"], 0.667, places=3)
        self.assertEqual(d["latency_median_min"], 90.0)
        self.assertEqual(s["by_cause"]["liner"]["first_alarm_is_true_node_share"], 0.0)
        self.assertEqual(s["control"]["loss_episodes"], 2)
        self.assertEqual(s["control"]["runs_with_loss"], 1)


class StoredResultTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = load("detect_eval.json")

    def test_file_is_complete_and_current(self):
        d = self.d
        self.assertEqual(d["runs"], len(detect_eval.cases(d["n_seeds"])))
        self.assertGreaterEqual(d["n_seeds"], 15)
        self.assertEqual(set(d["by_cause"]), set(detect_eval.CAUSES))
        self.assertEqual(d["code_hash"], detect_eval.code_hash(), "the model changed after detect_eval.json was written: "
                         "python -I aktogay/run.py detect_eval --seeds 25 --jobs 4 --write aktogay/web/static/detect_eval.json")
        self.assertIn("detect_eval", d["command"])

    def test_shares_are_shares(self):
        for k, b in self.d["by_cause"].items():
            self.assertEqual(b["detected"] + b["unsure_only"] + b["missed"], b["n"], k)
            self.assertLessEqual(b["detected_ci95"][0], b["detected_share"] + 1e-9)
            self.assertGreaterEqual(b["detected_ci95"][1], b["detected_share"] - 1e-9)
            if b["latency_median_min"] is not None:
                self.assertLessEqual(b["latency_median_min"], b["latency_p90_min"])

    def test_control_runs_are_reported_as_they_are(self):
        c = self.d["control"]
        self.assertEqual(c["runs"], self.d["n_seeds"])
        self.assertIn("loss_per_week", c)

    def test_matrix_has_the_four_causes_and_own_node_column(self):
        m = self.d["matrix_by_kind"]
        self.assertEqual(set(m), set(detect_eval.CAUSES))
        for k, row in m.items():
            self.assertTrue(any("своя линия" in h for h in row))


class CusumEvalTest(unittest.TestCase):
    def test_siegmund_matches_the_textbook_value(self):
        self.assertAlmostEqual(cusum_eval.siegmund(0.5, 6.5), 4253, delta=5)

    def test_episodes_counts_latched_alarms(self):
        quiet = [0.0] * 50
        self.assertEqual(cusum_eval.episodes(quiet, 0.5, 6.5, 3.5), 0)
        step = [0.0] * 10 + [1.5] * 12 + [-5.0] * 30 + [1.5] * 12
        self.assertEqual(cusum_eval.episodes(step, 0.5, 6.5, 3.5), 2)
        self.assertEqual(cusum_eval.episodes([4.0, 0.0, 4.0], 0.5, 6.5, 3.5), 1)       # the alarm is latched while S stays above 0
        self.assertEqual(cusum_eval.episodes([4.0, -5.0, 4.0], 0.5, 6.5, 3.5), 2)      # the fast threshold, S cleared between

    def test_first_alarm_ignores_alarms_before_the_cause(self):
        z = [4.0] + [0.0] * 20 + [2.0] * 12
        i = cusum_eval.first_alarm(z, 0.5, 6.5, 3.5, 10)
        self.assertIsNotNone(i)
        self.assertGreater(i, 20)

    def test_monte_carlo_is_near_the_theory_for_independent_z(self):
        r = cusum_eval.monte_carlo(60, 0.5, 6.5, 99.0)
        theory = 6 * cusum_eval.WEEK_TACTS / cusum_eval.siegmund(0.5, 6.5)
        self.assertAlmostEqual(r["alarms_per_week_6_monitors"], theory, delta=1.2)

    def test_stored_result(self):
        c = load("cusum_eval.json")
        self.assertEqual(len(c["curve"]), len(cusum_eval.H_GRID) * len(cusum_eval.FAST_GRID))
        self.assertEqual(sum(1 for r in c["curve"] if r["work_point"]), 1)
        wp = [r for r in c["curve"] if r["work_point"]][0]
        self.assertEqual((wp["h"], wp["fast"]), cusum_eval.WORK)
        self.assertEqual(c["stated_false_alarms_per_week"], 0.95)
        fr = c["free_run"]
        self.assertEqual(fr["hidden_causes"], 0)
        self.assertEqual(set(fr["z_autocorr_lag1_2_3"]), set(cusum_eval.NODES))
        by = {(r["h"], r["fast"]): r["false_alarms_per_week_free_run"] for r in c["curve"]}
        for f in cusum_eval.FAST_GRID:
            seq = [by[(h, f)] for h in cusum_eval.H_GRID]
            self.assertEqual(seq, sorted(seq, reverse=True), "a higher threshold never gives more false alarms")


class PageTest(unittest.TestCase):
    def test_modules_page_shows_both_files(self):
        with open(os.path.join(STATIC, "modview.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("/detect_eval.json", js)
        self.assertIn("/cusum_eval.json", js)
        self.assertIn("Ложные тревоги", js)
        self.assertIn("Нашёл", js)


if __name__ == "__main__":
    unittest.main()
