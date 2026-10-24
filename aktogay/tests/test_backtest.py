"""Quarterly back-test (sim/backtest.py): the report data file, a short model run, the committed result file
and its way into validation-calib."""
import json
import math
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sim import backtest as bt  # noqa: E402
from sim import calib, calib_report as cr  # noqa: E402
from sim.params import TABLE, default  # noqa: E402

QUARTERS = [f"{y}Q{q}" for y in range(2018, 2026) for q in range(1, 5)]


class DataFileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = bt.load_quarters()
        cls.by = {r["q"]: r for r in cls.rows}

    def test_32_quarters_each_with_a_source(self):
        self.assertEqual([r["q"] for r in self.rows], QUARTERS)
        for r in self.rows:
            self.assertTrue(r["url"].startswith("https://"), r["q"])
            self.assertTrue(r["page"].strip(), r["q"])
            for k in ("ore_kt", "grade_pct", "rec_pct", "cu_kt"):
                self.assertIsNotNone(r[k], (r["q"], k))
            self.assertTrue(0.3 < r["grade_pct"] < 0.8 and 75 < r["rec_pct"] < 95, r["q"])

    def test_plants_add_up_to_the_total(self):
        for r in self.rows:
            if r["ore1_kt"] is not None and r["ore2_kt"] is not None:
                self.assertAlmostEqual(r["ore1_kt"] + r["ore2_kt"], r["ore_kt"], delta=1.0, msg=r["q"])
            # copper in concentrate is the contained metal: payable plus cathode never exceeds the total
            self.assertLessEqual(r["cu_kt"], r["cu_total_kt"] + 1e-9, r["q"])

    def test_second_concentrator_from_2021q4(self):
        for r in self.rows:
            two = (r["year"], r["qn"]) >= (2021, 4)
            self.assertEqual(r["ore2_kt"] is not None and r["ore2_kt"] > 0, two, r["q"])

    def test_quarters_sum_to_the_printed_year(self):
        def total(year, key):
            return sum(self.by[f"{year}Q{q}"][key] for q in range(1, 5))
        # FY ore: 54 358 kt (2023) and 58 306 kt (2024) in the KAZ Minerals water table, 62.1 Mt in 2025 (params)
        self.assertAlmostEqual(total(2023, "ore_kt"), 54358, delta=1)
        self.assertAlmostEqual(total(2024, "ore_kt"), 58306, delta=1)
        self.assertAlmostEqual(total(2025, "ore_kt") / 1e3, TABLE["tgt_2025_ore_mt"].value, delta=0.06)
        # copper in concentrate 239.5 / 221.0 / 220.3 kt, Aktogay total copper 228.8 (2024) and 225.7 (2025) kt
        self.assertAlmostEqual(total(2023, "cu_kt"), 239.5, delta=0.05)
        self.assertAlmostEqual(total(2024, "cu_kt"), 221.0, delta=0.05)
        self.assertAlmostEqual(total(2025, "cu_kt"), TABLE["tgt_2025_cu_kt"].value, delta=0.05)
        self.assertAlmostEqual(total(2024, "cu_total_kt"), 228.8, delta=0.05)
        self.assertAlmostEqual(total(2025, "cu_total_kt"), 225.7, delta=0.05)

    def test_agrees_with_the_quarters_already_in_the_parameter_table(self):
        q3, q2 = self.by["2025Q3"], self.by["2025Q2"]
        self.assertEqual(q3["rec_pct"], TABLE["tgt_q3_2025_rec_pct"].value)
        self.assertEqual(q3["grade_pct"], TABLE["tgt_q3_2025_grade_pct"].value)
        self.assertEqual(q3["ore_kt"], TABLE["tgt_q3_2025_ore_kt"].value)
        self.assertEqual(q2["rec_pct"], TABLE["tgt_q2_2025_rec_pct"].value)
        self.assertEqual(self.by["2023Q4"]["ore1_kt"], 7001)       # reline quarter, report Q4 2023 p. 3
        self.assertEqual(self.by["2023Q4"]["ore2_kt"], 6603)

    def test_kinds(self):
        self.assertEqual(bt.kind_of(2021, 3), "single")
        self.assertEqual(bt.kind_of(2021, 4), "ramp")
        self.assertEqual(bt.kind_of(2022, 4), "ramp")
        self.assertEqual(bt.kind_of(2023, 1), "two")
        self.assertEqual(bt.parse_quarter("2024Q3"), (2024, 3))


class ModelRunTest(unittest.TestCase):
    """Two quarters at a coarse step with the table parameters (the real run fits 2025 first)."""

    @classmethod
    def setUpClass(cls):
        cls.rep = {r["q"]: r for r in bt.load_quarters()}
        cls.ov = default().overrides()

    def test_line_off_keeps_the_default_runs_and_stops_line_2(self):
        prm = default()
        calib.clear_cache()
        a = calib.run_quarter(prm, 2024, 2, 42, 60.0)
        b = calib.run_quarter(prm, 2024, 2, 42, 60.0, line_off=())
        self.assertEqual(a["ore_kt"], b["ore_kt"])
        one = calib.run_quarter(prm, 2018, 2, 42, 60.0, grade=0.62, line_off=(2,))
        self.assertEqual(one["ore_kt_l2"], 0.0)
        self.assertGreater(one["ore_kt_l1"], 3000.0)
        self.assertTrue(math.isfinite(one["cu_kt"]) and one["cu_kt"] > 10.0)
        self.assertGreater(one["rec_pct"], 80.0)

    def test_two_quarters_ore_matches_and_model_does_not_see_the_result(self):
        for q, kind in (("2024Q1", "two"), ("2018Q2", "single")):
            r = bt.run_one(self.rep[q], self.ov, 42, 60.0)
            self.assertEqual(r["kind"], kind)
            self.assertLessEqual(abs(r["ore_mod"] / r["ore_rep"] - 1.0), bt.ORE_TOL + 1e-9, q)
            self.assertTrue(r["ore_reached"])
            self.assertAlmostEqual(r["rec_err"], r["rec_mod"] - r["rec_rep"], places=9)
            self.assertAlmostEqual(r["cu_err"], r["cu_mod"] - r["cu_rep"], places=9)
            self.assertAlmostEqual(r["const_err"], TABLE["flot_rec_ref_pct"].value - r["rec_rep"], places=9)
            # the copper follows from ore, feed grade and model recovery, not from the report
            self.assertAlmostEqual(r["cu_mod"], r["ore_mod"] * r["grade_mod"] / 100.0 * r["rec_mod"] / 100.0,
                                   delta=0.01 * r["cu_mod"])
            if kind == "single":                  # at the two-line availability of 2025 one plant gives far more than reported
                self.assertGreater(r["blind_ore_pct"], 5.0)
            self.assertEqual(r["fit"], False)
            # the grade tolerance band: 2 % + 0.005 / grade
            self.assertAlmostEqual(r["tol_cu_pct"], 2.0 + 100 * 0.005 / r["grade_rep"], places=6)

    def test_summary_counts_and_excludes_the_fit_year(self):
        rows = [dict(q="2024Q1", kind="two", fit=False, rec_err=-0.5, cu_err=-0.4, cu_err_pct=-1.0, const_err=-0.6,
                     rec_ok=True, cu_ok=True, beats_const=True, blind_cu_pct=10.0, blind_ore_pct=9.0,
                     ore_reached=True, cu_const_pct=0.5, grade_rep=0.44, rec_rep=88.0, rec_mod=87.5),
                dict(q="2024Q2", kind="two", fit=False, rec_err=-1.5, cu_err=0.4, cu_err_pct=2.0, const_err=-1.0,
                     rec_ok=False, cu_ok=True, beats_const=False, blind_cu_pct=-8.0, blind_ore_pct=-7.0,
                     ore_reached=True, cu_const_pct=-1.0, grade_rep=0.43, rec_rep=88.5, rec_mod=87.0),
                dict(q="2025Q1", kind="two", fit=True, rec_err=9.0, cu_err=9.0, cu_err_pct=9.0, const_err=9.0,
                     rec_ok=False, cu_ok=False, beats_const=False, blind_cu_pct=1.0, blind_ore_pct=1.0,
                     ore_reached=True, cu_const_pct=1.0, grade_rep=0.42, rec_rep=80.0, rec_mod=89.0)]
        s = bt.summaries(rows)
        self.assertEqual(s["all"]["n"], 2)
        self.assertEqual(s["fit"]["n"], 1)
        self.assertAlmostEqual(s["all"]["rec_bias_pp"], -1.0)
        self.assertAlmostEqual(s["all"]["rec_mae_pp"], 1.0)
        self.assertAlmostEqual(s["all"]["rec_max_pp"], 1.5)
        self.assertAlmostEqual(s["all"]["const_mae_pp"], 0.8)
        self.assertEqual((s["all"]["rec_ok"], s["all"]["cu_ok"], s["all"]["beats_const"]), (1, 2, 1))
        self.assertEqual(s["single"]["n"], 0)
        self.assertAlmostEqual(s["all"]["rec_rep_mean"], 88.25)
        self.assertAlmostEqual(s["all"]["rec_mod_mean"], 87.25)
        self.assertTrue(math.isnan(s["all"]["corr_grade_rec_rep"]))          # two points: no correlation


class ResultFileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(bt.OUT_PATH, encoding="utf-8") as f:
            cls.doc = json.load(f)
        cls.csv = {r["q"]: r for r in bt.load_quarters()}

    def test_every_quarter_of_the_data_file_is_there_with_its_source(self):
        rows = self.doc["rows"]
        self.assertEqual([r["q"] for r in rows], QUARTERS)
        for r in rows:
            c = self.csv[r["q"]]
            self.assertEqual((r["ore_rep"], r["grade_rep"], r["rec_rep"], r["cu_rep"]),
                             (c["ore_kt"], c["grade_pct"], c["rec_pct"], c["cu_kt"]), r["q"])
            self.assertEqual((r["url"], r["page"]), (c["url"], c["page"]), r["q"])
            self.assertEqual(r["fit"], c["year"] == 2025, r["q"])
            self.assertEqual(r["kind"], bt.kind_of(c["year"], c["qn"]), r["q"])
            self.assertAlmostEqual(r["rec_err"], r["rec_mod"] - r["rec_rep"], delta=2e-4)
            self.assertAlmostEqual(r["cu_err"], r["cu_mod"] - r["cu_rep"], delta=2e-4)
            self.assertLessEqual(abs(r["ore_mod"] / r["ore_rep"] - 1.0), bt.ORE_TOL + 1e-3, r["q"])

    def test_summary_is_what_the_rows_give_and_the_fit_year_is_not_scored(self):
        again = bt.summaries(self.doc["rows"])
        for k in ("all", "single", "ramp", "two", "fit"):
            for key, v in again[k].items():
                self.assertAlmostEqual(self.doc["summary"][k][key], v, delta=2e-3, msg=(k, key))
        self.assertEqual(self.doc["summary"]["all"]["n"], 28)
        self.assertEqual(self.doc["summary"]["two"]["n"], 8)
        self.assertEqual(self.doc["summary"]["fit"]["n"], 4)
        self.assertEqual(self.doc["fit_year"], 2025)

    def test_nothing_is_refitted_to_the_test_quarters(self):
        # the fitted parameters are the ones of the annual 2025 fit (calib quick table: 0.9206 / 0.4885 / 93.187)
        f = self.doc["fit"]
        self.assertAlmostEqual(f["cal_avail"], 0.9206, delta=0.002)
        self.assertAlmostEqual(f["sag_k"], 0.4885, delta=0.002)
        self.assertAlmostEqual(f["flot_rinf0_pct"], 93.187, delta=0.05)
        tol = self.doc["tolerances"]
        self.assertEqual(tol["rec_pp"], TABLE["tol_rec_pp"].value)
        self.assertEqual(tol["cu_frac"], TABLE["tol_cu_frac"].value)
        self.assertEqual(tol["grade_round_pct"], TABLE["tol_grade_round_pct"].value)
        self.assertTrue(self.doc["notes"])


class PublishTest(unittest.TestCase):
    def test_backtest_goes_into_the_report(self):
        b = cr.load_backtest(cr.BACKTEST_DEFAULT)
        self.assertIsNotNone(b)
        calib_doc = {"seed": 42, "quick": True, "rows": [{"group": "g", "name": "n", "model": 1.0, "report": 1.0,
                                                          "unit": "%", "tol": 0.1, "ok": True, "note": ""}],
                     "errors": [], "seconds": {"total": 1.0}, "fitted": {}}
        doc = cr.build_report(calib_doc, cr.load_trial(cr.TRIAL_DEFAULT), b)
        self.assertEqual(len(doc["backtest"]["rows"]), 32)
        self.assertEqual(doc["backtest"]["summary"]["all"]["n"], 28)
        text = cr.report_text(doc)
        self.assertLess(len(text.encode("utf-8")), cr.MAX_REPORT_BYTES)
        self.assertEqual(json.loads(text)["backtest"]["rows"][0]["q"], "2018Q1")
        # without a back-test the key is null (old reports and a missing file)
        self.assertIsNone(cr.build_report(calib_doc, None)["backtest"])

    def test_missing_or_broken_file(self):
        self.assertIsNone(cr.load_backtest(""))
        self.assertIsNone(cr.load_backtest(os.path.join(ROOT, "no-such-backtest.json")))
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "b.json")
            with open(p, "w", encoding="utf-8") as f:
                f.write('{"rows": []}')
            self.assertIsNone(cr.load_backtest(p))

    def test_publish_done_sends_the_backtest(self):
        class W(cr.DittoWriter):
            def __init__(self):
                super().__init__("http://ditto", "ditto", "x", tries=1)
                self.sent = []

            def patch(self, values):
                self.sent.append(values)
                return True

        w = W()
        row = {"group": "g", "name": "n", "model": 1.0, "report": 1.0, "unit": "%", "tol": 0.1, "ok": True, "note": ""}
        cr.publish_done(w, {"rows": [row], "errors": []}, cr.load_trial(cr.TRIAL_DEFAULT),
                        cr.load_backtest(cr.BACKTEST_DEFAULT))
        self.assertEqual(len(json.loads(w.sent[0]["report_json"])["backtest"]["rows"]), 32)


class WebFilesTest(unittest.TestCase):
    def test_script_is_registered_and_the_calibration_view_uses_it(self):
        web = os.path.join(ROOT, "web", "static")
        with open(os.path.join(web, "index.html"), encoding="utf-8") as f:
            self.assertIn('<script src="/backtest.js"></script>', f.read())
        with open(os.path.join(web, "views.js"), encoding="utf-8") as f:
            v = f.read()
        self.assertIn("Проверка по кварталам", v)
        self.assertIn("AKT.backtest.render(rep && rep.backtest)", v)
        with open(os.path.join(web, "backtest.js"), encoding="utf-8") as f:
            self.assertIn("A.backtest = {", f.read())


if __name__ == "__main__":
    unittest.main()
