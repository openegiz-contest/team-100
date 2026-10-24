"""Readiness cards (FEATURES_22.md, «ОПРЕДЕЛЕНИЕ ГОТОВНОСТИ», 23.10.2026): every new trouble and forecast has the nine
points, they agree with the code (WHO table, parameters, scenarios, tests, the page «Как проверить»), the checklist and the
closure reach the issue card, and a closed trouble is written to the journal and the handover sheet."""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests import mod_support as ms  # noqa: E402
from tests.test_mod_priority import T0, modules, real_store  # noqa: E402
from tests.test_forecast import scenario_plant, store_of  # noqa: E402
from modules import params as mparams  # noqa: E402
from modules import priority, readiness  # noqa: E402
from sim.params import TABLE  # noqa: E402


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


class CardsTest(unittest.TestCase):
    def test_all_nine_points_are_filled_for_every_card(self):
        self.assertEqual(readiness.missing(), [])
        ids = [r["id"] for r in readiness.READY]
        self.assertEqual(len(ids), len(set(ids)))
        for need in ("pit_stop", "conveyor_stop", "fc_stock", "fc_liner", "fc_copper", "bal_cu_water"):
            self.assertIn(need, ids)

    def test_who_and_backup_match_the_who_table_and_the_roster(self):
        roles = ms.ROLES
        for r in readiness.READY:
            k = r["who_kind"]
            if not k:
                continue
            crew, keys = priority.WHO[k]
            first = roles[keys[0]]
            self.assertIn(first.split()[0].lower(), r["who"].lower(), r["id"])     # the first role of WHO is named
            self.assertTrue(r["backup"].strip())

    def test_parameters_named_in_the_cards_exist(self):
        have = {p.key for p in mparams.PARAMS} | set(TABLE)
        for r in readiness.READY:
            keys = [w for w in re.findall(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+", r["params"] + " " + r["rule"])]
            self.assertTrue(keys, r["id"])
            for k in keys:
                self.assertIn(k, have, f"{r['id']}: {k}")

    def test_scenario_test_and_howto_row_exist(self):
        app = read(ROOT, "web", "static", "app.js")
        pages = read(ROOT, "web", "static", "pages.js")
        for r in readiness.READY:
            self.assertIn(r["howto"], pages, r["id"])
            sc = r["scenario"].split(" ")[0].strip(",")
            if r["id"] in ("pit_stop", "conveyor_stop", "fc_stock", "fc_liner"):
                self.assertIn(f"id: '{sc}'", app, r["id"])
            path, _, test = r["test"].partition("::")
            path = path.split(" ")[0].split(",")[0]
            self.assertTrue(os.path.exists(os.path.join(ROOT, path)), r["test"])
            if test:
                name = test.split("::")[-1]
                src = read(ROOT, path)
                self.assertTrue(f"def {name}(" in src or f"class {name}(" in src, r["test"])

    def test_checklists_carry_a_source_or_say_so(self):
        for r in readiness.READY:
            c = r["checklist"]
            self.assertTrue(readiness.NOT_FOUND in c or "[факт" in c or "справочный" in c, r["id"])
        self.assertIn("п. 315", readiness.by_id("conveyor_stop")["checklist"])
        self.assertIn("п. 63", readiness.by_id("fc_liner")["checklist"])
        self.assertIn(readiness.NOT_FOUND, readiness.by_id("pit_stop")["checklist"])

    def test_written_copies_equal_the_code(self):
        self.assertEqual(read(ROOT, "web", "static", "readiness.json"), readiness.json_text())
        self.assertEqual(read(os.path.dirname(ROOT), "READINESS.md"), readiness.md_text())

    def test_the_page_shows_the_table(self):
        pages = read(ROOT, "web", "static", "pages.js")
        self.assertIn("Путь внедрения", pages)
        self.assertIn("/readiness.json", pages)


class CardOnTheIssueTest(unittest.TestCase):
    def issues_of(self, plant):
        st, prm = store_of(plant)
        lm, om, pm = modules(st, prm)
        pm.roles = ms.ROLES
        lm.compute(plant.t_min)
        om.compute(plant.t_min)
        feats, issues = pm.compute(plant.t_min, seed=1)
        return pm, feats, issues

    def test_pit_stop_card_has_checklist_and_closure(self):
        pl = scenario_plant("pitstop")
        for _ in range(6):
            pl.step(5.0)
        _pm, _f, issues = self.issues_of(pl)
        pit = [v for v in issues.values() if v["kind"] == "pit_stop"]
        self.assertTrue(pit)
        for v in pit:
            self.assertTrue(v["checklist"].startswith("Что делать:"))
            self.assertIn(readiness.NOT_FOUND, v["checklist"])
            self.assertTrue(v["closure"].startswith("Закроется:"))
            self.assertIn("журнал", v["closure"])

    def test_belt_card_quotes_the_safety_rules(self):
        pl = scenario_plant("conveyor:1")
        for _ in range(3):
            pl.step(5.0)
        _pm, _f, issues = self.issues_of(pl)
        belt = [v for v in issues.values() if v["kind"] == "conveyor_stop"]
        self.assertTrue(belt)
        self.assertIn("Не включать! Работают люди!", belt[0]["checklist"])
        self.assertIn("п. 315", belt[0]["checklist"])

    def test_a_closed_trouble_goes_to_the_journal_and_the_handover_sheet(self):
        pl = scenario_plant("conveyor:1")
        for _ in range(3):
            pl.step(5.0)
        st, prm = store_of(pl)
        lm, om, pm = modules(st, prm)
        pm.roles = ms.ROLES
        t = pl.t_min
        lm.compute(t); om.compute(t)
        _f, issues = pm.compute(t, seed=1)
        self.assertTrue(any(v["kind"] == "conveyor_stop" for v in issues.values()))
        # the belt is repaired: the signal is back to normal
        for _ in range(12 * 12):
            pl.step(5.0)
            if not pl.state.lines[0].conveyor.fault:
                break
        st.update_from_search(ms.items_from_plant(pl))
        t2 = pl.t_min
        lm.compute(t2); om.compute(t2)
        feats, issues2 = pm.compute(t2, seed=1)
        log = [e for e in feats["escalations"]["log"] if e["action"] == "resolved"]
        self.assertTrue(log)
        self.assertIn("устранена", log[0]["text"])
        self.assertIn("Устранено за смену:", feats["handover_draft_text"])
        self.assertTrue(feats["handover"]["done"] if feats["handover"].get("at", -1) >= 0 else True)


if __name__ == "__main__":
    unittest.main()
