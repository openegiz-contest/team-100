"""The summary of the symmetric people / twin base (sim/exp24.py, sim/data/experiment_24.json, VALIDATION.md 8.17): the runs it reads exist and
carry the settings their names say, the stored numbers are those of the stored rows, the control run reproduces the base of 8.8, the paired
contrasts are differences of the same shifts, and the documents quote the headline of the file."""
import json
import os
import random
import statistics
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(os.path.dirname(ROOT), "final_docs")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

sys.path.insert(0, os.path.join(ROOT, "scripts"))
from sim import exp24  # noqa: E402
import check_numbers as cn  # noqa: E402

DATA = os.path.join(ROOT, "sim", "data")


def load(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return json.load(f)


def text(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


class RunsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = {k: load(exp24.DIR, v[0] + ".json") for k, v in exp24.RUNS.items()}

    def test_every_run_has_the_settings_its_name_says(self):
        want = {"R1": ("same", "dig", 1001, 163000), "R2": ("same", "dig", 2001, 163000), "R3": ("same", "sag", 1001, 163000),
                "R4": ("same", "sag", 2001, 163000), "R5": ("none", "dig", 1001, 163000), "R5b": ("none", "dig", 2001, 163000),
                "R6": ("same", "dig", 1001, 163000), "R6b": ("same", "dig", 2001, 163000), "R7": ("same", "sag", 1001, 163000),
                "R7b": ("same", "sag", 2001, 163000)}
        self.assertEqual(set(self.docs), set(want))
        for k, d in self.docs.items():
            human, hard, seed0, live_b = want[k]
            cfg = d["config"]
            self.assertEqual((cfg["twin_human"], cfg["asis_hard"]), (human, hard), k)
            self.assertEqual(cfg["library"], "tier_s", k)
            self.assertEqual(d["seeds"], [seed0, seed0 + 99], k)
            self.assertEqual(len(d["shifts"]), 100, k)
            stock_b = k in ("R6", "R6b", "R7", "R7b")
            self.assertEqual(cfg["set"].get("stock_live_t") == live_b, stock_b, k)
            self.assertEqual(set(d["shifts"][0]["cu_t_2000"]), {"base", "by_value", "by_loud", "no_twin", "novice", "value_nd"}, k)

    def test_paired_runs_use_the_same_shifts(self):
        for a, b in (("R1", "R5"), ("R1", "R3"), ("R1", "R6"), ("R2", "R5b"), ("R3", "R7"), ("R4", "R7b")):
            sa = [(s["seed"], s["text"]) for s in self.docs[a]["shifts"]]
            sb = [(s["seed"], s["text"]) for s in self.docs[b]["shifts"]]
            self.assertEqual(sa, sb, (a, b))                                 # the same seeds draw the same troubles whatever the base

    def test_the_symmetric_twin_is_never_later_than_the_people_on_a_loud_trouble(self):
        for k in ("R1", "R3"):
            n = 0
            for s in self.docs[k]["shifts"]:
                for issue, ex in s["bookings"]["no_twin"].items():
                    tw = s["bookings"]["by_value"].get(issue)
                    if tw is not None and issue.split(":")[0] in ("crusher", "trip", "grid", "reline"):
                        n += 1
                        self.assertLessEqual(tw["t_call_min"], ex["t_call_min"] + 1e-6, (k, s["seed"], issue))
            self.assertGreater(n, 50, k)


class StatisticsTest(unittest.TestCase):
    def test_block_on_a_known_sample(self):
        xs = [0.0, 0.0, 1.0, 2.0, 10.0]
        b = exp24._block(xs, random.Random(1), 300)
        self.assertAlmostEqual(b["mean"], 2.6)
        self.assertAlmostEqual(b["median"], 1.0)
        self.assertAlmostEqual(b["trim1"], 1.0)                              # 0, 1, 2 remain
        self.assertEqual((b["min"], b["max"], b["n"]), (0.0, 10.0, 5))
        self.assertLess(b["ci95"][0], 2.6)
        self.assertGreater(b["ci95"][1], 2.6)
        self.assertAlmostEqual(b["share_better"], 3 / 5)                     # 1, 2, 10 are above the 0.05 t threshold
        self.assertAlmostEqual(b["share_none"], 2 / 5)

    def test_stored_headline_is_the_one_of_the_stored_rows(self):
        stored = load(DATA, "experiment_24.json")
        for key in ("R1", "R3", "R5"):
            doc = load(exp24.DIR, exp24.RUNS[key][0] + ".json")
            got = exp24.summarize_run(doc, random.Random(7), boot=200)
            old = stored["runs"][key]
            d = [float(r["cu_t_2000"]["by_value"]) - float(r["cu_t_2000"]["no_twin"]) for r in doc["shifts"]]
            self.assertAlmostEqual(old["twin_minus_asis"]["mean"], statistics.fmean(d), places=9, msg=key)
            for field in ("mean", "median", "trim1", "p10", "p90", "min", "max", "share_worse", "share_better"):
                self.assertAlmostEqual(old["twin_minus_asis"][field], got["twin_minus_asis"][field], places=9, msg=(key, field))
            self.assertEqual(old["top_shift"]["seed"], got["top_shift"]["seed"])
            self.assertAlmostEqual(old["without_top_shift"]["mean"], got["without_top_shift"]["mean"], places=9)
            self.assertEqual(old["gain_sits_in"]["other"]["n"] + old["gain_sits_in"]["hard_ore"]["n"] + old["gain_sits_in"]["dose_or_cyclone"]["n"], 100)
            lo, hi = old["twin_minus_asis"]["ci95"]
            self.assertLess(lo, old["twin_minus_asis"]["mean"])
            self.assertGreater(hi, old["twin_minus_asis"]["mean"])
        # the largest shift of seeds 1001-1100 is the reorder artefact of 8.8 and it sets the mean
        self.assertEqual(stored["runs"]["R1"]["top_shift"]["seed"], exp24.ARTEFACT_SEED)
        self.assertGreater(stored["runs"]["R1"]["top_shift"]["d_cu_t"], 30.0)

    def test_paired_contrasts_are_differences_of_the_same_shifts(self):
        stored = load(DATA, "experiment_24.json")
        self.assertEqual(set(stored["paired"]), {n for n, _a, _b in exp24.PAIRED})
        for name, a, b in exp24.PAIRED:
            p = stored["paired"][name]
            self.assertEqual((p["a"], p["b"]), (a, b))
            self.assertAlmostEqual(p["mean"], stored["runs"][a]["twin_minus_asis"]["mean"] - stored["runs"][b]["twin_minus_asis"]["mean"], places=9, msg=name)

    def test_the_control_run_reproduces_the_base_of_8_8(self):
        stored = load(DATA, "experiment_24.json")
        old = load(DATA, "experiment_23.json")["b3_d1"]["main_full"]["pairs"]["twin-expert"]["cu"]["mean"]
        self.assertAlmostEqual(stored["runs"]["R5"]["twin_minus_asis"]["mean"], old, delta=0.03)       # +1.07 published, +1.09 on the merged code
        self.assertEqual({w["seed"] for w in stored["runs"]["R5"]["worse_shifts"]}, {1078, 1067, 1005})  # the same roping shifts as in 8.11
        self.assertLess(stored["runs"]["R1"]["twin_minus_asis"]["mean"], 0.8 * old)                    # the symmetric base is lower, not higher


class DocumentsQuoteTheFileTest(unittest.TestCase):
    def test_headline_in_the_documents(self):
        stored = load(DATA, "experiment_24.json")
        r1 = stored["runs"]["R1"]["twin_minus_asis"]
        head = cn.fmt(r1["mean"], 2)
        ci = "[%s; %s]" % (cn.fmt(r1["ci95"][0], 2), cn.fmt(r1["ci95"][1], 2))
        for name in ("SUBMISSION.md", "README_aktogay.md", "VALIDATION.md"):
            t = text(DOCS, name).replace("\xa0", " ").replace(" ", " ")
            self.assertIn(head, t, name)
            self.assertIn(ci, t, name)
        # both readings of the stockpile stay visible next to each other
        v = text(DOCS, "VALIDATION.md").replace("\xa0", " ")
        self.assertIn(cn.fmt(stored["runs"]["R6"]["twin_minus_asis"]["mean"], 2), v)
        self.assertIn("163 кт", v)

    def test_the_command_exists(self):
        run = text(ROOT, "run.py")
        self.assertIn('cmd == "exp24"', run)
        self.assertTrue(os.path.exists(os.path.join(exp24.DIR, "run_exp24.py")))


if __name__ == "__main__":
    unittest.main()
