"""Oxide line (heap leach -> SX-EW -> cathode, 24.10.2026): the cathode level of the quarter from the reports, the scenario
leachcold, the trouble «Куча выщелачивания: катод ниже нормы», its card of readiness, the things and the web wiring."""
import csv
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "web", "static")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests import mod_support as ms  # noqa: E402
from tests.test_mod_priority import T0, modules  # noqa: E402
from modules import priority, readiness  # noqa: E402
from sim import oxide  # noqa: E402
from sim import sensors as se  # noqa: E402
from sim.params import FEATURE_RULES, TABLE, default as TABLE_DEFAULT  # noqa: E402
from sim.plant import CopySet, Plant  # noqa: E402


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


class QuarterTest(unittest.TestCase):
    def test_the_32_quarters_are_the_reports(self):
        c = oxide.cathode_by_quarter()
        self.assertEqual(len(c), 32)
        self.assertAlmostEqual(sum(c[(2025, q)] for q in (1, 2, 3, 4)), 15.3, places=6)     # 2025: 15.3 kt (Q4 2025 report, p. 3)
        with open(os.path.join(ROOT, "sim", "data", "kaz_quarterly.csv"), encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual({(int(r["quarter"][:4]), int(r["quarter"][5])): float(r["cathode_kt"]) for r in rows}, c)

    def test_level_is_kt_per_hours_of_the_quarter(self):
        self.assertAlmostEqual(oxide.level_tph(2025, 1), 3.4 * 1000 / (90 * 24), places=9)
        self.assertAlmostEqual(oxide.level_tph(2024, 4), 3.6 * 1000 / (92 * 24), places=9)
        self.assertEqual(oxide.quarter_hours(2024, 1), 91 * 24)                      # leap year

    def test_quarter_of_a_date_and_dates_after_2025(self):
        self.assertEqual(oxide.quarter_of(2025, 0), (2025, 1))
        self.assertEqual(oxide.quarter_of(2025, 299), (2025, 4))                      # 27 October
        self.assertEqual(oxide.quarter_of(2026, 299), (2025, 4))                      # after 2025: the same quarter of 2025
        self.assertEqual(oxide.quarter_of(2030, 100), (2025, 2))

    def test_the_reported_quarters_hold_the_season(self):
        c = oxide.cathode_by_quarter()
        self.assertLess(c[(2024, 4)], c[(2024, 3)])                                  # A5-8: Q4 2024 below Q3 2024
        self.assertAlmostEqual(c[(2024, 4)] / c[(2024, 3)] - 1.0, -0.25, delta=0.001)


class PlantTest(unittest.TestCase):
    def snap(self, plant):
        return se.measured_features(plant.state, plant.prm)

    def test_normal_run_follows_the_quarter(self):
        p = Plant(TABLE_DEFAULT(), 42, mode="scenario")
        p.ox_date = (2025, 299)
        p.run_until(p.t_min + 60)
        s = self.snap(p)
        self.assertEqual((s["leach-1"]["state"], s["sxew-1"]["state"]), ("NORMAL", "NORMAL"))
        self.assertAlmostEqual(s["sxew-1"]["cathode_tph"], oxide.level_tph(2025, 4), places=9)
        self.assertEqual((s["sxew-1"]["year"], s["sxew-1"]["quarter"]), (2025.0, 4.0))
        self.assertAlmostEqual(s["leach-1"]["quarter_cathode_kt"], 3.5)
        self.assertEqual(s["leach-1"]["cold_frac"], 0.0)

    def test_winter_flag_does_not_cut_the_reported_level_twice(self):
        a = Plant(TABLE_DEFAULT(), 42, mode="scenario")
        b = Plant(TABLE_DEFAULT(), 42, mode="scenario")
        b.winter_on = True
        for p in (a, b):
            p.ox_date = (2025, 330)
            p.run_until(p.t_min + 30)
        self.assertEqual(self.snap(a)["sxew-1"]["cathode_tph"], self.snap(b)["sxew-1"]["cathode_tph"])

    def test_leachcold_cuts_the_output_for_the_spell_and_ends(self):
        cs = CopySet(None, 42, "leachcold")
        fact = cs.copies["fact"]
        fact.ox_date = (2025, 299)
        for _ in range(90):
            cs.step()
        s = self.snap(fact)
        lvl = oxide.level_tph(2025, 4)
        self.assertEqual((s["leach-1"]["state"], s["sxew-1"]["state"]), ("COLD", "LOW"))
        self.assertAlmostEqual(s["leach-1"]["cold_frac"], TABLE["ox_cold_frac"].value)
        self.assertAlmostEqual(s["sxew-1"]["cathode_tph"], lvl * 0.75, places=9)
        for _ in range(int(fact.prm["scen_leach_h"] * 60)):
            cs.step()
        s = self.snap(fact)
        self.assertEqual(s["leach-1"]["state"], "NORMAL")
        self.assertAlmostEqual(s["sxew-1"]["cathode_tph"], lvl, places=9)

    def test_the_oxide_line_changes_nothing_in_the_sulphide_plant(self):
        a = CopySet(None, 42, "")
        b = CopySet(None, 42, "leachcold")
        for _ in range(120):
            a.step()
            b.step()
        sa, sb = a.copies["fact"].shift_summary(), b.copies["fact"].shift_summary()
        for k in ("cu_t", "ore_t", "energy_mwh", "water_m3", "usd"):
            self.assertEqual(sa[k], sb[k], k)

    def test_the_token_takes_a_duration_inside_the_row(self):
        cs = CopySet(None, 42, "leachcold@60=3")
        fact = cs.copies["fact"]
        ev = [e for e in fact._events if e.kind == "leachcold"]
        self.assertEqual(len(ev), 1)
        self.assertAlmostEqual(ev[0].duration_h, 3.0)
        with self.assertRaises(ValueError):
            CopySet(None, 42, "leachcold:1")


class ModuleTest(unittest.TestCase):
    def run_mod(self, cold):
        st, prm = ms.make_store(T0)
        lvl = oxide.level_tph(2025, 4)
        ov = {"leach-1": {"state": "COLD" if cold else "NORMAL", "quarter_cathode_kt": 3.5, "level_tph": lvl,
                          "cold_frac": 0.25 if cold else 0.0},
              "sxew-1": {"state": "LOW" if cold else "NORMAL", "cathode_tph": lvl * (0.75 if cold else 1.0),
                         "cathode_level_tph": lvl, "cathode_t_total": 10.0, "year": 2025.0, "quarter": 4.0}}
        items = ms.snapshot(T0, ov)
        items += [ms.item("leach-1", ov["leach-1"], T0), ms.item("sxew-1", ov["sxew-1"], T0)]
        st.update_from_search(items)
        lm, om, pm = modules(st, prm)
        lm.compute(T0)
        om.compute(T0)
        return pm.compute(T0, seed=1), prm

    def test_cold_pad_is_a_priced_money_trouble_for_the_metallurgist(self):
        (feats, issues), prm = self.run_mod(True)
        f = next(x for x in issues.values() if x["kind"] == "leach_cold")
        self.assertEqual(f["node"], "leach-1")
        self.assertIn("Металлург смены", f["responsible"])
        self.assertEqual(f.get("safety_class", ""), "")
        lost = oxide.level_tph(2025, 4) * 0.25
        self.assertAlmostEqual(f["loss_usd_h"], lost * prm["cu_price_usd_t"], delta=0.02 * lost * prm["cu_price_usd_t"])
        self.assertIn("допущение", f["text"])
        self.assertIn("катод", f["text"])
        self.assertIn(readiness.NOT_FOUND, f["checklist"])
        self.assertIn("Закроется", f["closure"])

    def test_normal_pad_is_no_trouble(self):
        (feats, issues), _prm = self.run_mod(False)
        self.assertNotIn("leach_cold", {x["kind"] for x in issues.values()})

    def test_the_kind_has_names_and_a_card(self):
        self.assertIn("leach_cold", priority.WHO)
        self.assertIn("leach_cold", priority.SHORT_RU)
        self.assertEqual(priority.KIND_READY["leach_cold"], "leach_cold")
        card = readiness.by_id("leach_cold")
        self.assertEqual(readiness.missing(), [])
        self.assertIn("кт", card["problem"])
        ru = read(STATIC, "ru.js")
        self.assertIn("leach_cold:", ru)


class ThingsTest(unittest.TestCase):
    def test_types_and_things(self):
        d = json.loads(read(ROOT, "setup", "things.json"))
        self.assertIn("leach", d["types"])
        self.assertIn("sxew", d["types"])
        names = {t["name"]: t for t in d["things"]}
        self.assertEqual(names["leach-1"]["feeds"], ["sxew-1"])
        self.assertEqual(names["sxew-1"]["parent"], "site")
        for n in ("leach-1", "sxew-1"):
            self.assertTrue(names[n]["passport"])
            for k, v in names[n]["passport"].items():
                if len(v) >= 3:
                    self.assertIn(v[2], d["sources"] | {"assume": 1, "calc": 1}, f"{n}.{k}")
        for typ in ("leach", "sxew"):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, "models", f"{typ}-1.0.0.tm.jsonld")))
            self.assertEqual(set(d["types"][typ]["features"]), set(FEATURE_RULES[typ]))

    def test_parameters_have_source_label_and_range(self):
        for k in ("ox_cold_frac", "scen_leach_h"):
            r = TABLE[k]
            self.assertTrue(r.source and r.label in ("analog", "assumption") and r.min < r.max)
        self.assertEqual(TABLE["ox_cold_frac"].label, "analog")
        self.assertIn("-25 %", TABLE["ox_cold_frac"].source)


class WebTest(unittest.TestCase):
    def test_catalog_card_and_pages(self):
        sc = json.loads(read(STATIC, "scenarios.json"))
        s = next(x for x in sc["scenarios"] if x["id"] == "leachcold")
        self.assertEqual(s["test"], "tests/test_oxide.py")
        self.assertIn("leachcold", {t["kind"] for t in sc["constructor"]["troubles"]})
        rd = json.loads(read(STATIC, "readiness.json"))
        self.assertIn("leach_cold", {x["id"] for x in rd["items"]})
        flow, plan = read(STATIC, "flow.js"), read(STATIC, "plan.js")
        self.assertIn("cp-ox", flow)
        self.assertIn("не измерение", flow)
        self.assertIn("leach-1", plan)
        self.assertIn("sxew-1", plan)
        anchors = json.loads(read(STATIC, "plan.json"))["anchors"]
        self.assertTrue(anchors["leach-1"]["scheme"] and anchors["sxew-1"]["scheme"])
        self.assertIn("COLD", read(STATIC, "app.js"))

    def test_only_a_deviation_gets_a_label(self):
        plan = read(STATIC, "plan.js")
        m = re.search(r"const oxText = \(\) => (.*)", plan)
        self.assertIn("=== 'COLD'", m.group(1))
        self.assertIn(": ''", m.group(1))


if __name__ == "__main__":
    unittest.main()
