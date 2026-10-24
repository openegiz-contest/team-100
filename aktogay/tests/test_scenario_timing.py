"""Time to the first trouble and whom to call, measured for every scenario of the catalog (24.10.2026): web/static/scenario_timing.json is written by
scripts/measure_scenarios.py --model (the three modules on the simulator); the card of each scenario («Когда видно») states the measured time."""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

import measure_scenarios as msn  # noqa: E402
from modules import scenarios  # noqa: E402
from sim import verify  # noqa: E402

STATIC = os.path.join(ROOT, "web", "static")


def timing():
    with open(os.path.join(STATIC, "scenario_timing.json"), encoding="utf-8") as f:
        return json.load(f)


def clock(m):
    t = 480 + int(round(m))
    return "%02d:%02d" % (t // 60 % 24, t % 60)


class TimingFileTest(unittest.TestCase):
    def test_every_catalog_scenario_is_measured_with_the_current_code(self):
        d = timing()
        ids = [s["id"] for s in scenarios.catalog()]
        self.assertEqual([r["id"] for r in d["rows"]], ids)
        self.assertEqual(d["code_hash"], verify.code_hash(), "the model changed: python -I aktogay/scripts/measure_scenarios.py --model --out aktogay/web/static/scenario_timing.json")
        self.assertEqual(d["seed"], 42)

    def test_cards_state_the_measured_time_and_the_person(self):
        d = timing()
        cat = {s["id"]: s for s in scenarios.catalog()}
        for r in d["rows"]:
            when = cat[r["id"]]["when"]
            self.assertNotEqual(when, scenarios.WHEN_DEFAULT, r["id"])
            if r["first_issue_min"] is None:
                self.assertIn("не создаётся" if r["id"] == "sample:1" else "своей беды у сценария нет", when, r["id"])
                continue
            self.assertIn(clock(r["first_issue_min"]), when, r["id"])
            self.assertIn(r["issue"]["who"], when, r["id"])

    def test_slow_scenarios_say_so(self):
        d = {r["id"]: r for r in timing()["rows"]}
        cat = {s["id"]: s for s in scenarios.catalog()}
        slow = [i for i, r in d.items() if r["first_issue_min"] and r["first_issue_min"] > 60]
        self.assertIn("slurry:1", slow)
        self.assertIn("gmd:1", slow)
        for i in slow:
            if i != "fork":
                self.assertIn("доходит до порога", cat[i]["when"], i)

    def test_the_background_of_the_run_without_a_scenario_is_not_the_scenarios(self):
        d = timing()
        bg = {tuple(x) for x in d["background"]}
        self.assertIn(("fleet_short", "fleet"), bg)
        for r in d["rows"]:
            if r["issue"]:
                self.assertNotIn((r["issue"]["kind"], r["issue"]["node"]), bg, r["id"])


class FreshRunTest(unittest.TestCase):
    def test_two_scenarios_repeat_the_stored_minutes(self):
        d = timing()
        bg = {tuple(x) for x in d["background"]}
        rows = {r["id"]: r for r in d["rows"]}
        for sid in ("crusher:1", "hpgr:2"):
            r = msn.model_row(sid, 42, background=bg)
            self.assertEqual(r["first_issue_min"], rows[sid]["first_issue_min"], sid)
            self.assertEqual(r["issue"]["who"], rows[sid]["issue"]["who"], sid)


if __name__ == "__main__":
    unittest.main()
