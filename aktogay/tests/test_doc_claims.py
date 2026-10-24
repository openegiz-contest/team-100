"""Numbers of the scenario tables in SUBMISSION.md and VALIDATION.md against a fresh run of the model, and web/static/verify.json
against the output of its script (sim/verify.py).

Each scenario of the table is run here: CopySet(None, 42, scenario).run_to_end() to 20:00; the fork with one and two
instrument engineers the same way. A number in the documents must equal the computed one at the precision it is printed.
Nothing here edits a document: a mismatch fails the test and the document is corrected by hand.
"""
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sim import verify  # noqa: E402
from sim.params import default  # noqa: E402
from sim.plant import CopySet  # noqa: E402

DOCS = os.path.normpath(os.path.join(ROOT, "..", "final_docs"))
STATIC = os.path.join(ROOT, "web", "static")
SINGLE = ("crusher:1", "grid", "hard:1", "reline:1", "water", "hpgr_fire")
_CACHE: dict = {}


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


def num(text: str):
    """'−$9 900' -> (-9900.0, 0 decimals); '+1,09 (см. ниже)' -> (1.09, 2)."""
    t = text.split("(")[0].strip().replace("−", "-").replace("$", "").replace(" ", "").replace(" ", "")
    t = t.replace(",", ".")
    dec = len(t.split(".")[1]) if "." in t else 0
    return float(t), dec


def runs():
    """Fresh runs through CopySet, shared by the tests of this file."""
    if not _CACHE:
        for sid in SINGLE:
            _CACHE[sid] = CopySet(None, verify.SEED, sid).run_to_end()
        for kip in (1, 2):
            _CACHE["fork%d" % kip] = CopySet(None, verify.SEED, "", preset="fork", kip=kip).run_to_end()
    return _CACHE


def table_rows(text: str) -> dict:
    """Rows of the scenario table: id in backticks -> the five cells (cu, ore, energy, water, usd)."""
    out = {}
    for line in text.split("\n"):
        m = re.match(r"^\| (.*?`([a-z_:0-9]+)`) \|", line)
        if m and m.group(2) in SINGLE and line.count("|") == 7:
            out[m.group(2)] = [c.strip() for c in line.strip().strip("|").split("|")[1:]]
    return out


def close(doc_cell: str, value: float, unit: float = 0.0) -> bool:
    v, dec = num(doc_cell)
    half = max(0.5 * 10 ** (-dec), 0.5 * unit)
    return abs(v - value) <= half + 1e-9


class TestScenarioTables(unittest.TestCase):
    def check_doc(self, name):
        rows = table_rows(read(DOCS, name))
        self.assertEqual(sorted(rows), sorted(SINGLE), name + ": rows of the scenario table")
        for sid in SINGLE:
            res = runs()[sid]
            d = res["diff"]["fact"]
            cells = rows[sid]
            for cell, key, unit in zip(cells, ("cu_t", "ore_t", "energy_mwh", "water_m3", "usd"), (0, 0, 0, 0, 100)):
                with self.subTest(doc=name, scenario=sid, column=key):
                    self.assertTrue(close(cell, d[key], unit),
                                    "%s %s %s: document %r, model %.4f" % (name, sid, key, cell, d[key]))

    def test_submission_table(self):
        self.check_doc("SUBMISSION.md")

    def test_validation_table(self):
        self.check_doc("VALIDATION.md")

    def test_base_copper_and_hard_night(self):
        base = runs()["crusher:1"]["copies"]["base"]["cu_t"]
        vj = verify.run_one({"id": "hard:1", "text": "hard:1", "preset": "", "kip": 1})
        for name in ("SUBMISSION.md", "VALIDATION.md"):
            text = read(DOCS, name)
            self.assertIn("304,8 т", text)
            self.assertAlmostEqual(base, 304.8, delta=0.05)
        total, night = vj["next_day_cu_t"]["diff_total"], vj["next_day_cu_t"]["night_shift"]
        self.assertEqual("%.1f" % total, "-7.2")
        self.assertEqual("%.1f" % night, "-8.3")
        for name in ("SUBMISSION.md", "VALIDATION.md"):
            text = read(DOCS, name)
            self.assertIn("−7,2 т Cu", text)
            self.assertIn("−8,3 т", text)

    def test_fork_table(self):
        for name in ("SUBMISSION.md", "VALIDATION.md"):
            text = read(DOCS, name)
            for kip, col in ((1, 0), (2, 1)):
                r = runs()["fork%d" % kip]
                c = r["copies"]
                want = {"находк": c["loud"]["cu_t"] - c["no_twin"]["cu_t"], "порядок": c["fact"]["cu_t"] - c["loud"]["cu_t"],
                        "целиком": c["fact"]["cu_t"] - c["no_twin"]["cu_t"]}
                for line in text.split("\n"):
                    for key, val in want.items():
                        if line.startswith("|") and key in line and "«по" in line and line.count("|") == 4:
                            cells = [x.strip() for x in line.strip().strip("|").split("|")]
                            with self.subTest(doc=name, kip=kip, row=key):
                                self.assertTrue(close(cells[1 + col], val), "%s fork kip=%d %s: %r vs %.4f" % (name, kip, key, cells[1 + col], val))

    def test_parameters_named_in_scenario_text(self):
        """Magnitudes that the scenario rows state in words are the ones in the parameter table."""
        p = default()
        sub = read(DOCS, "SUBMISSION.md")
        self.assertEqual((p["pow_grid_limit_mw"], p["pow_c2_limit_mw"], p["pow_c2_h"]), (300, 218, 2))
        self.assertIn("300 → 218 МВт на 2 ч", sub)
        self.assertEqual(p["liner_reline_h"], 84)
        self.assertIn("на 84 ч", sub)
        self.assertEqual(p["crush_repair_h"], 3)
        self.assertEqual(p["ore_axb_hard"], 27)
        self.assertEqual(p["scen_fire_h"], 8)
        self.assertEqual(p["scen_pitstop_h"], 8)


class TestVerifyJson(unittest.TestCase):
    def test_equals_script_output(self):
        stored = json.loads(read(STATIC, "verify.json"))
        fresh = json.loads(verify.json_text(jobs=3))
        self.assertEqual(stored, fresh, "verify.json is stale: python -I aktogay/run.py verify --write aktogay/web/static/verify.json")

    def test_file_is_lf_and_has_seed_and_hash(self):
        raw = open(os.path.join(STATIC, "verify.json"), "rb").read()
        self.assertNotIn(b"\r", raw)
        d = json.loads(raw.decode("utf-8"))
        self.assertEqual(d["seed"], 42)
        self.assertEqual(d["code_hash"], verify.code_hash())
        self.assertIn("verify --write", d["command"])

    def test_agrees_with_fresh_runs(self):
        d = {(r["id"], r["kip"]): r for r in json.loads(read(STATIC, "verify.json"))["runs"]}
        for sid in SINGLE:
            self.assertAlmostEqual(d[(sid, 1)]["diff"]["fact"]["cu_t"], runs()[sid]["diff"]["fact"]["cu_t"], places=3)
        for kip in (1, 2):
            fk = runs()["fork%d" % kip]["fork"]
            self.assertAlmostEqual(d[("fork", kip)]["fork_cu_t"]["detection_cu_t"], fk["detection_cu_t"], places=3)
            self.assertAlmostEqual(d[("fork", kip)]["fork_cu_t"]["order_cu_t"], fk["order_cu_t"], places=3)

    def test_every_catalog_scenario_present(self):
        from modules import scenarios
        ids = {r["id"] for r in json.loads(read(STATIC, "verify.json"))["runs"]}
        for s in scenarios.catalog():
            self.assertIn(s["id"], ids)

    def test_ui_shows_label(self):
        js = read(STATIC, "app.js") + read(STATIC, "pages.js")
        self.assertIn("verify.json", js)
        self.assertIn("посчитано заранее тем же кодом", js)
        self.assertIn("оценка на модели", js)


if __name__ == "__main__":
    unittest.main()
