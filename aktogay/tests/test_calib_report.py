"""Calibration report for validation-calib (sim/calib_report.py): trial summary, report text, writes."""
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sim import calib_report as cr  # noqa: E402

ROW = {"group": "fit 2025", "name": "recovery", "model": 87.10912345678, "report": 87.2, "unit": "%",
       "tol": 0.1, "ok": True, "note": "flot_rinf0_pct fitted"}


class FakeWriter(cr.DittoWriter):
    def __init__(self):
        super().__init__("http://ditto", "ditto", "x", tries=1)
        self.sent = []

    def patch(self, values: dict) -> bool:
        self.sent.append(values)
        return True


class TestCalibReport(unittest.TestCase):
    def test_repo_trial_summary(self):
        t = cr.load_trial(cr.TRIAL_DEFAULT)
        self.assertIsNotNone(t, "sim/data/trial_n100.json must ship with the image")
        self.assertEqual(t["n"], 100)
        self.assertEqual(t["seeds"], [1001, 1100])
        self.assertNotIn("shifts", t)
        for k in ("d_cu_t_2000", "d_cu_t_0800", "d_usd_2000", "detection_cu_t_2000", "twin_cu_t_2000"):
            s = t["summary"][k]
            self.assertEqual(s["n"], 100)
            lo, hi = s["ci95_mean_bca"]
            self.assertLessEqual(lo, s["mean"])
            self.assertLessEqual(s["mean"], hi)
            self.assertIn("p0_ci95_wilson", s)
            self.assertIn("p_minus_ci95_wilson", s)

    def test_load_trial_missing_or_broken(self):
        self.assertIsNone(cr.load_trial(""))
        self.assertIsNone(cr.load_trial(os.path.join(ROOT, "no-such-file.json")))
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.json")
            with open(p, "w", encoding="utf-8") as f:
                f.write('{"n": 3}')
            self.assertIsNone(cr.load_trial(p))

    def test_build_report_compact_and_finite(self):
        calib = {"seed": 42, "quick": True, "rows": [ROW, dict(ROW, model=float("nan"), ok=None)],
                 "errors": [], "seconds": {"total": 88.4}, "fitted": {"sag_k": 0.48851234567}, "years": {"2025": {}}}
        doc = cr.build_report(calib, cr.load_trial(cr.TRIAL_DEFAULT))
        self.assertEqual(doc["kind"], "akt-calib")
        self.assertEqual(len(doc["rows"]), 2)
        self.assertNotIn("years", doc)
        self.assertEqual(doc["rows"][0]["model"], 87.109123)
        self.assertIsNone(doc["rows"][1]["model"])            # NaN -> null, JSON stays valid
        text = cr.report_text(doc)
        self.assertLess(len(text.encode("utf-8")), cr.MAX_REPORT_BYTES)
        self.assertEqual(json.loads(text)["trial"]["n"], 100)

    def test_publish_sequence(self):
        w = FakeWriter()
        trial = cr.load_trial(cr.TRIAL_DEFAULT)
        self.assertTrue(cr.publish_start(w, trial))
        self.assertTrue(cr.publish_done(w, {"rows": [ROW], "errors": []}, trial))
        self.assertEqual(w.sent[0]["state"], "RUNNING")
        self.assertEqual(w.sent[0]["shifts_total"], 100.0)
        self.assertEqual(w.sent[1]["state"], "DONE")
        self.assertIsInstance(w.sent[1]["report_json"], str)
        self.assertEqual(json.loads(w.sent[1]["report_json"])["rows"][0]["name"], "recovery")
        cr.publish_done(w, {"rows": [], "errors": ["boom"]}, None)
        self.assertEqual(w.sent[2]["state"], "FAILED")
        self.assertEqual(w.sent[2]["shifts_total"], 0.0)


if __name__ == "__main__":
    unittest.main()
