"""Twin model (setup/things.json, models/*.tm.jsonld): consistency without Ditto."""
import json
import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETUP = os.path.join(ROOT, "setup")
MODELS = os.path.join(ROOT, "models")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if SETUP not in sys.path:
    sys.path.insert(0, SETUP)

import twins  # noqa: E402
from sim.params import FEATURE_RULES  # noqa: E402


class TwinModelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = twins.Model()

    def test_counts(self):
        m = self.m
        service = [t for t in m.things if t["type"] in m.service]
        self.assertEqual(len(m.things), 136)                   # 52 (4 crews, leach pad and SX-EW) + 83 generated from the site passport (+4 people, +2 pH meters)
        self.assertEqual(len(service), 9)
        self.assertEqual(len(m.types) - len(m.service), 35)   # 33 own types incl. batch (+ phmeter, leach, sxew)
        by_type = {}
        for t in m.things:
            by_type[t["type"]] = by_type.get(t["type"], 0) + 1
        self.assertEqual((by_type["person"], by_type["truck"], by_type["exc"], by_type["face"], by_type["road"]),
                         (13, 37, 5, 5, 3))
        self.assertEqual((by_type["analyzer"], by_type["weigher"], by_type["flowmeter"], by_type["piezometer"],
                          by_type["phmeter"]), (2, 2, 2, 3, 2))
        self.assertEqual((by_type["drill"], by_type["dozer"]), (6, 7))
        self.assertEqual(m.by_name["truck-21"]["passport"]["bort"][:3], ["HT141", "", "kaz_equip2024"])
        self.assertEqual(m.by_name["exc-1"]["passport"]["bort"][0], "EX01")
        self.assertIn("условный", m.by_name["exc-2"]["passport"]["bort"][3])

    def test_every_node_has_a_responsible_person(self):
        m = self.m
        for t in m.things:
            if t["type"] in m.service:
                continue
            r = m.attributes(t)["responsible"]
            self.assertTrue(r.get("person", "").startswith(m.ns + ":person-"), t["name"])
            self.assertTrue(r.get("person_ru"), t["name"])
        a = m.attributes(m.by_name["crusher-1"])
        self.assertEqual(a["responsible"]["person"], "kz.aktogay:person-crusher-mech")
        self.assertEqual(m.attributes(m.by_name["crew-kip"])["responsible"]["person"], "kz.aktogay:person-kip")

    def test_site_part_is_generated(self):
        """things.json carries exactly what setup/gen_site.py writes from sim/site_aktogay.py."""
        import gen_site
        with open(m_path := os.path.join(SETUP, "things.json"), encoding="utf-8") as f:
            text = f.read()
        self.assertEqual(gen_site.render(gen_site.build(json.loads(text), gen_site.load_site())), text, m_path)

    def test_line2_has_its_own_passport(self):
        m = self.m
        p2 = m.by_name["pebble-2"]["passport"]
        self.assertEqual(p2["hpgr_tph"][:3], [1061, "t/h", "im2021_hpgr"])
        self.assertEqual(m.sources["im2021_hpgr"]["label"], "vendor")
        self.assertIn("Wemco", m.by_name["flot-2"]["passport"]["cells"][0])
        self.assertIn("FLSmidth", m.by_name["line-2"]["passport"]["package"][0])
        self.assertIn("63 × 89", m.by_name["crusher-2"]["passport"]["kind"][0])
        self.assertNotIn("design_ref", m.by_name["sag-2"]["passport"])

    def test_models_current(self):
        want = self.m.all_tms()
        have = {n for n in os.listdir(MODELS) if n.endswith(".tm.jsonld")}
        self.assertEqual(have, set(want), "run setup/gen_tm.py")
        for name, tm in want.items():
            with open(os.path.join(MODELS, name), encoding="utf-8") as f:
                self.assertEqual(json.load(f), tm, name)

    def test_sim_features_in_models(self):
        for typ, rules in FEATURE_RULES.items():
            missing = set(rules) - set(self.m.feature_map(typ))
            self.assertFalse(missing, f"{typ}: {sorted(missing)}")

    def test_graph(self):
        m = self.m
        roots = [t["name"] for t in m.things if not t.get("parent")]
        self.assertEqual(roots, ["site"])
        for t in m.things:
            a = m.attributes(t)
            self.assertTrue(a["source"], t["name"])
            for ref in a["feeds"] + a["fed_by"] + a["supplies"] + [a.get("_parents", m.tid("site"))]:
                self.assertIn(ref.split(":", 1)[1], m.by_name)
            for src in {p["src"] for p in a["passport"].values()}:
                self.assertIn(src, a["source"])

    def test_feature_values_typed(self):
        m = self.m
        for t in m.things:
            for f, feat in m.thing_body(t)["features"].items():
                v = feat["properties"]["value"]
                self.assertIsNotNone(v)
                if isinstance(v, float):
                    self.assertTrue(math.isfinite(v))
                self.assertIsInstance(feat["properties"]["unit"], str)
                self.assertEqual(len(feat["definition"]), 1)


if __name__ == "__main__":
    unittest.main()
