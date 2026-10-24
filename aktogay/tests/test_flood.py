"""Alarm flood (modules/flood.py, feature `alarm_flood` of mod-priority, 24.10.2026): events of the shift against the issues of the queue
and the one trouble on the main screen; the same counter is used by the experiment (sim/trial.py, `alarm_flood` block)."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests import mod_support as ms  # noqa: E402
from tests.test_mod_priority import T0, fork_ov, modules  # noqa: E402
from modules import flood  # noqa: E402


def items(**states):
    return [(n.replace("_", "-"), n.rsplit("_", 1)[0] if n[-1].isdigit() else n, s, None) for n, s in states.items()]


class CounterTest(unittest.TestCase):
    def test_entry_into_abnormal_counts_once_and_a_staying_state_does_not_repeat(self):
        c = flood.FloodCounter()
        c.observe(480, 0, [("crusher-1", "crusher", "RUN", None), ("sag-1", "sag", "RUN", None)])
        self.assertEqual(c.events, 0)                          # the first look sets the state, nothing is counted
        c.observe(485, 0, [("crusher-1", "crusher", "STOP", None), ("sag-1", "sag", "RUN", None)])
        c.observe(490, 0, [("crusher-1", "crusher", "STOP", None), ("sag-1", "sag", "STARVED", None)])
        c.observe(495, 0, [("crusher-1", "crusher", "STOP", None), ("sag-1", "sag", "STARVED", None)])
        self.assertEqual(c.events, 2)                          # crusher stop, then the SAG starves
        self.assertEqual(c.now, 2)
        c.observe(500, 0, [("crusher-1", "crusher", "RUN", None), ("sag-1", "sag", "STARVED", None)])
        c.observe(505, 0, [("crusher-1", "crusher", "STOP", None), ("sag-1", "sag", "STARVED", None)])
        self.assertEqual(c.events, 3)                          # the crusher went again: a new alarm
        self.assertEqual(c.names, {"crusher-1": 2, "sag-1": 1})

    def test_states_that_are_work_not_alarms_are_ignored(self):
        c = flood.FloodCounter()
        c.observe(480, 0, [("person-a", "person", "FREE", None), ("truck-1", "truck", "QUEUE", None)])
        c.observe(485, 0, [("person-a", "person", "WORK", None), ("truck-1", "truck", "DOWN", None),
                           ("crew-kip", "crew", "OFF", None)])
        self.assertEqual(c.events, 0)

    def test_new_shift_restarts_the_count_but_keeps_the_state(self):
        c = flood.FloodCounter()
        c.observe(1100, 0, [("crusher-1", "crusher", "RUN", None)])
        c.observe(1105, 0, [("crusher-1", "crusher", "STOP", None)])
        self.assertEqual(c.events, 1)
        c.observe(1200, 1, [("crusher-1", "crusher", "STOP", None)])
        self.assertEqual((c.events, c.now), (0, 1))            # still stopped, but not an entry of the new shift
        c.observe(1205, 1, [("crusher-1", "crusher", "RUN", None)])
        c.observe(1210, 1, [("crusher-1", "crusher", "STOP", None)])
        self.assertEqual(c.events, 1)

    def test_a_new_run_clears_the_counter(self):
        c = flood.FloodCounter()
        c.observe(900, 0, [("crusher-1", "crusher", "RUN", None)])
        c.observe(905, 0, [("crusher-1", "crusher", "STOP", None)])
        c.observe(485, 0, [("crusher-1", "crusher", "RUN", None)])     # the clock went back
        self.assertEqual(c.events, 0)

    def test_piezometer_alarm_flag_counts(self):
        c = flood.FloodCounter()
        c.observe(480, 0, [("piezometer-1", "piezometer", "OK", 0.0)])
        c.observe(485, 0, [("piezometer-1", "piezometer", "OK", 1.0)])
        self.assertEqual(c.events, 1)

    def test_summary_against_the_isa_orientation(self):
        c = flood.FloodCounter()
        c.observe(480, 0, [("crusher-1", "crusher", "RUN", None)])
        c.observe(540, 0, [("crusher-1", "crusher", "STOP", None)])
        s = c.summary(540, 2)
        self.assertEqual((s["events"], s["issues"], s["main"]), (1, 2, 1))
        self.assertAlmostEqual(s["per_10min"], 1 / 6.0, places=6)
        self.assertAlmostEqual(s["isa_per_10min"], 150.0 / 144.0, places=6)         # 150 a day = 1.04 per 10 min
        self.assertEqual(s["isa_per_shift"], 75.0)
        self.assertIn("нижняя граница", s["label"])
        self.assertEqual(flood.FloodCounter().summary(480, 0)["per_10min"], -1.0)
        self.assertEqual(c.summary(485, 0)["issues"], 0)

    def test_every_type_in_the_table_is_a_stand_type_with_a_state(self):
        import json
        with open(os.path.join(ROOT, "setup", "things.json"), encoding="utf-8") as f:
            types = json.load(f)["types"]
        for typ in flood.ABNORMAL:
            self.assertIn(typ, types, typ)
            self.assertIn("state", types[typ]["features"], typ)


class ModuleTest(unittest.TestCase):
    def test_mod_priority_publishes_the_flood_and_the_sheet_says_it(self):
        st, prm = ms.make_store(T0 - 30.0)
        lm, om, pm = modules(st, prm)
        lm.compute(T0 - 30.0)
        om.compute(T0 - 30.0)
        feats, _ = pm.compute(T0 - 30.0)
        self.assertEqual(feats["alarm_flood"]["events"], 0)
        for i, t in enumerate((T0 - 25.0, T0 - 20.0, T0 - 15.0)):
            st.update_from_search(ms.snapshot(t, fork_ov(**({"sag-2": {"state": "STARVED"}} if i else {}))))
            lm.compute(t)
            om.compute(t)
            feats, issues = pm.compute(t, seed=3)
        f = feats["alarm_flood"]
        self.assertGreaterEqual(f["events"], 3)              # crusher-2 stop, conveyor-2 stop, SAG-2 starved
        self.assertIn("crusher-2", {k for k in pm.flood.names})
        self.assertEqual(f["main"], 1)
        self.assertEqual(f["issues"], len(issues))
        self.assertIn("1 на главном экране", feats["alarm_flood_text"])
        self.assertIn("ISA-18.2", feats["alarm_flood_text"])
        self.assertIn("нижняя граница", feats["alarm_flood_text"])
        self.assertIn("Тревоги за смену", feats["handover_draft_text"])

    def test_the_feature_is_declared_for_the_thing(self):
        import json
        with open(os.path.join(ROOT, "setup", "things.json"), encoding="utf-8") as f:
            feats = json.load(f)["types"]["mod-priority"]["features"]
        self.assertEqual(feats["alarm_flood"], "obj")
        self.assertEqual(feats["alarm_flood_text"], "text")


if __name__ == "__main__":
    unittest.main()
