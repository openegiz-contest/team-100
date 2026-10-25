"""Telemetry publisher (sim/publish.py): messages and types without MQTT."""
import json
import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETUP = os.path.join(ROOT, "setup")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if SETUP not in sys.path:
    sys.path.insert(0, SETUP)

import twins  # noqa: E402
from sim import publish  # noqa: E402
from sim.params import FEATURE_RULES  # noqa: E402

KIND = {"number": float, "string": str, "object": dict}


class PublishTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = twins.Model()
        cls.cat = publish.Catalog()
        cls.pub = publish.Publisher(catalog=cls.cat)

    def check_features(self, name, feats):
        typ = self.cat.type_of(name)
        self.assertEqual(set(self.m.feature_map(typ)) - set(feats), set(), name)
        for f, body in feats.items():
            kind, unit, _ = self.cat.spec(name, f)
            p = body["properties"]
            self.assertEqual(set(p), {"value", "unit"})
            self.assertIs(type(p["value"]), KIND[kind], f"{name}.{f}")
            self.assertEqual(p["unit"], unit)
            if kind == "number":
                self.assertTrue(math.isfinite(p["value"]))

    def test_message_shape(self):
        topic, msg = self.pub.build("sag-1", {"power_kw": 26000}, "r1", 480)
        self.assertEqual(topic, "telemetry/kz.aktogay/sag-1")
        self.assertEqual(msg["topic"], "kz.aktogay/sag-1/things/twin/commands/modify")
        self.assertEqual(msg["path"], "/features")
        self.assertEqual(msg["headers"], {"correlation-id": "akt-sim-sag-1", "response-required": False})
        p = msg["value"]
        self.assertEqual(p["power_kw"]["properties"], {"value": 26000.0, "unit": "kW"})
        self.assertEqual(p["idSimulationRun"]["properties"]["value"], "r1")
        self.assertEqual(p["sim_time"]["properties"], {"value": 480.0, "unit": "min"})
        self.assertEqual(p["state"]["properties"]["value"], "")
        self.assertEqual(p["load_pct"]["properties"]["value"], -1.0)
        json.dumps(msg, allow_nan=False)

    def test_merge_header(self):
        pub = publish.Publisher(command="merge", writer="losses", catalog=self.cat)
        _, msg = pub.build("mod-losses", {}, "r1", 480)
        self.assertEqual(msg["topic"], "kz.aktogay/mod-losses/things/twin/commands/merge")
        self.assertEqual(msg["headers"]["content-type"], "application/merge-patch+json")
        self.assertEqual(msg["headers"]["correlation-id"], "akt-losses-mod-losses")

    def test_coercion(self):
        feats = self.cat.features("sag-1", {"power_kw": float("nan"), "feed_tph": None, "speed_pct": True,
                                            "load_pct": 28, "e_kwh_t": float("inf"), "bogus": 1.0}, "r", 1)
        v = {f: b["properties"]["value"] for f, b in feats.items()}
        self.assertEqual((v["power_kw"], v["feed_tph"], v["speed_pct"], v["load_pct"], v["e_kwh_t"]),
                         (-1.0, -1.0, 1.0, 28.0, -1.0))
        self.assertNotIn("bogus", feats)
        self.check_features("sag-1", feats)

    def test_baseline_base_features(self):
        feats = self.cat.features("baseline", {"sag-1_power_kw_base": 25900, "flot-1_state_base": "RUN"}, "r", 1)
        self.assertEqual(feats["sag-1_power_kw_base"]["properties"], {"value": 25900.0, "unit": "kW"})
        self.assertEqual(feats["flot-1_state_base"]["properties"], {"value": "RUN", "unit": ""})

    def test_rate_ramp(self):
        pub = publish.Publisher(catalog=self.cat, max_rate=40.0, ramp_s=60.0)
        t0 = pub._t_conn
        self.assertAlmostEqual(pub.rate(t0), 8.0)
        self.assertAlmostEqual(pub.rate(t0 + 30.0), 24.0)
        self.assertAlmostEqual(pub.rate(t0 + 61.0), 40.0)
        self.assertEqual(publish.Publisher(catalog=self.cat, max_rate=0).rate(), 0.0)

    def test_dynamic_things(self):
        self.assertEqual(self.cat.type_of("batch-0001"), "batch")
        self.assertEqual(self.cat.type_of("issue-3"), "issue")
        self.assertIsNone(self.cat.type_of("nothing-1"))

    def test_sim_features_accepted(self):
        for typ, rules in FEATURE_RULES.items():
            name = next((n for n, t in self.cat.things.items() if t == typ), typ + "-0001")
            for f in rules:
                self.assertIsNotNone(self.cat.spec(name, f), f"{typ}.{f}")

    def test_demo_all_things_typed(self):
        demo = publish.Demo(self.cat, seed=42)
        self.assertEqual(len(demo.names), 140)       # 140 things of things.json without validation-setup
        self.assertNotIn("validation-setup", demo.names)
        for _ in range(3):
            snap = demo.step(5.0)
        for name, values in snap.items():
            for f in values:
                self.assertIsNotNone(self.cat.spec(name, f), f"{name}.{f}")
            _, msg = self.pub.build(name, values, "r", demo.t)
            self.check_features(name, msg["value"])
            json.dumps(msg, allow_nan=False)
        self.assertEqual(snap["site"]["state"], "RUN")
        self.assertGreater(snap["line-1"]["cum_cu_t"], 0.0)


if __name__ == "__main__":
    unittest.main()
