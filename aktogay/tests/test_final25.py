"""Fixes of 25.10.2026: the fact copy of «Два сразу» follows the calls of the module, the S0 call of the dam alarm works,
the reset button and the texts of the pages (loading state, neutral timing note, no «станции»).

Python side: sim/plant.py (CopySet module mode, fallback, call log, piezometer call), sim/modloop.py, sim/service.py
(policy in baseline.shift_result, module_missing, issue-thing call of the dam alarm). Page side: static checks of the files."""
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sim import modloop, service  # noqa: E402
from sim.plant import MODULE_MISSING_MIN, CopySet  # noqa: E402
from sim.state import NO_VALUE  # noqa: E402
from tests.test_service import event, make_runner  # noqa: E402

STATIC = os.path.join(ROOT, "web", "static")


def read(name):
    with open(os.path.join(STATIC, name), encoding="utf-8") as f:
        return f.read()


def run_to(cs, hhmm):
    h, m = hhmm.split(":")
    while cs.copies["fact"].t_min < int(h) * 60 + int(m) - 1e-6:
        cs.step(1.0)


class ForkModuleModeTest(unittest.TestCase):
    def test_offline_mode_is_the_old_order(self):
        cs = CopySet(None, 42, "", preset="fork", kip=1)
        self.assertEqual(cs.fact_mode, "offline")
        r = cs.run_to_end()
        self.assertAlmostEqual(r["fork"]["detection_cu_t"], 0.847265, places=5)
        self.assertAlmostEqual(r["fork"]["order_cu_t"], 2.175096, places=5)
        self.assertEqual(cs.policy_report()["mode"], "offline")

    def test_module_mode_books_nothing_until_the_module_calls(self):
        cs = CopySet(None, 42, "", preset="fork", kip=1, fact_policy="module")
        fact = cs.copies["fact"]
        self.assertEqual(cs.fact_mode, "module")
        self.assertTrue(fact.follow_module)
        run_to(cs, "10:30")
        # the alarm of the crusher (09:20 + notice) did not call the crew; the laboratory call of 14:00 is the only plan
        self.assertEqual([e for e in fact.call_log], [])
        self.assertIn("trip:2", fact._held_loud)
        self.assertEqual(cs.policy_report()["n_calls"], 0)
        # the other copies keep the alarm
        for name in ("loud", "no_twin"):
            self.assertTrue(any(e["issue"] == "trip:2" and e["src"] in ("alarm", "plan") for e in cs.copies[name].call_log), name)

    def test_a_module_call_is_booked_logged_and_the_loud_copy_follows_the_finding(self):
        cs = CopySet(None, 42, "", preset="fork", kip=1, fact_policy="module")
        run_to(cs, "09:45")
        job = cs.call("flot-1", src="module")
        self.assertIsNotNone(job)
        cs.step(1.0)
        rep = cs.policy_report()
        self.assertEqual((rep["mode"], rep["n_calls"], rep["n_module"], rep["share_module"]), ("module", 1, 1, 1.0))
        self.assertEqual(rep["calls"][0]["node"], "flot-1")
        # the loud copy calls the silent issue when the fact copy found it: after the alarm call of the trip
        loud = cs.copies["loud"]
        run_to(cs, "10:00")
        dose = [e for e in loud.call_log if e["issue"] == "dose:1"]
        self.assertEqual(len(dose), 1)
        self.assertGreaterEqual(dose[0]["t"], 9 * 60 + 45 - 1e-6)
        trip = [e for e in loud.call_log if e["issue"] == "trip:2"][0]
        self.assertLess(trip["t"], dose[0]["t"] + 1e-6)

    def test_fallback_returns_to_the_order_fixed_beforehand(self):
        cs = CopySet(None, 42, "", preset="fork", kip=1, fact_policy="module")
        run_to(cs, "09:50")
        self.assertTrue(cs.fallback_to_offline())
        self.assertFalse(cs.fallback_to_offline())                  # once
        fact = cs.copies["fact"]
        self.assertFalse(fact.follow_module)
        run_to(cs, "10:10")
        rep = cs.policy_report()
        self.assertEqual(rep["mode"], "fallback")
        self.assertEqual(rep["n_module"], 0)
        self.assertEqual({e["issue"] for e in fact.call_log}, {"dose:1", "trip:2"})
        self.assertTrue(all(e["src"] in ("fallback", "plan", "alarm") for e in fact.call_log))
        self.assertEqual(rep["fallback_at"], 9 * 60 + 50)

    def test_no_policy_outside_the_fork(self):
        cs = CopySet(None, 42, "crusher:1", fact_policy="module")
        self.assertEqual(cs.fact_mode, "alarm")
        self.assertFalse(cs.copies["fact"].follow_module)
        self.assertEqual(cs.policy_report(), {})

    def test_auto_off_keeps_the_alarm(self):
        cs = CopySet(None, 42, "", preset="fork", kip=1, auto=False, fact_policy="module")
        self.assertEqual(cs.fact_mode, "alarm")
        run_to(cs, "09:45")
        self.assertTrue(any(e["issue"] == "trip:2" for e in cs.copies["fact"].call_log))


class ModloopTest(unittest.TestCase):
    def test_the_modules_in_the_loop_call_the_flotation_first(self):
        r = modloop.run_fork(kip=1)
        pol = r["policy"]
        self.assertEqual(pol["mode"], "module")
        self.assertEqual((pol["n_calls"], pol["n_module"]), (2, 2))
        self.assertEqual(pol["order"], ["dose:1", "trip:2"])
        self.assertEqual(pol["same_order"], 1.0)
        self.assertLess(pol["calls"][0]["t"], pol["calls"][1]["t"])
        self.assertGreater(r["fork"]["order_cu_t"], 1.0)
        # the numbers stored for the page are these
        with open(os.path.join(STATIC, "verify.json"), encoding="utf-8") as f:
            v = {(x["id"], x["kip"]): x for x in json.load(f)["runs"]}[("fork", 1)]
        self.assertAlmostEqual(v["fork_cu_t"]["order_cu_t"], r["fork"]["order_cu_t"], places=5)
        self.assertEqual(v["fork_policy"]["mode"], "module")
        self.assertEqual(v["fork_policy"]["n_module"], 2)


class ServiceModuleTest(unittest.TestCase):
    def start_fork(self):
        r, sink, clock = make_runner()
        r.tick()
        r.handle_event(*event("control", "/features/scenario", {"preset": "fork", "kip": 1, "auto": 1}, seq=1))
        return r, sink, clock

    def test_default_is_module_and_the_copy_is_followed(self):
        self.assertEqual(service.Config().fact_policy, "module")
        r, sink, clock = self.start_fork()
        self.assertEqual(r.copies.fact_mode, "module")
        pol = sink.last_snapshot["baseline"]["shift_result"]["policy"]
        self.assertEqual(pol["mode"], "module")
        self.assertEqual(pol["n_calls"], 0.0)

    def test_auto_call_event_books_with_source_module(self):
        r, sink, clock = self.start_fork()
        r.handle_event(*event("mod-priority", "/features/issue_map",
                              {"properties": {"value": {"issue-3": {"node": "flot-1", "kind": "loss_flot"}}}}))
        for _ in range(12):
            r.copies.step(1.0)
        r.handle_event(*event("mod-priority", "/features/auto_call", {"issue": "issue-3", "node": "flot-1"}, seq=1))
        log = r.copies.copies["fact"].call_log
        self.assertEqual([(e["issue"], e["src"]) for e in log], [("dose:1", "module")])
        r.publish_point("checkpoint")
        pol = sink.last_snapshot["baseline"]["shift_result"]["policy"]
        self.assertEqual((pol["n_calls"], pol["n_module"], pol["share_module"]), (1.0, 1.0, 1.0))
        self.assertEqual(pol["calls"][0]["src"], "module")

    def test_module_missing_after_the_threshold_only(self):
        r, sink, clock = self.start_fork()
        t0 = r.copies.t0_min
        self.assertFalse(r.module_missing())
        while r.t_min < t0 + MODULE_MISSING_MIN - 2:
            r.copies.step(1.0)
        self.assertFalse(r.module_missing())
        while r.t_min < t0 + MODULE_MISSING_MIN + 2:
            r.copies.step(1.0)
        self.assertTrue(r.module_missing())
        r.processed["mod-priority"] = r.t_min - 10.0                 # the module answers (a few minutes behind)
        self.assertFalse(r.module_missing())
        r.processed["mod-priority"] = r.t_min - MODULE_MISSING_MIN - 5.0
        self.assertTrue(r.module_missing())
        r.check_module()
        self.assertEqual(r.copies.fact_mode, "fallback")
        pol = r.copies.policy_report()
        self.assertEqual(pol["mode"], "fallback")
        self.assertFalse(r.module_missing())                          # once

    def test_a_value_of_an_earlier_run_is_not_an_answer(self):
        r, sink, clock = self.start_fork()
        r.processed["mod-priority"] = 1190.0                          # 19:50 of the shift before
        self.assertFalse(r.module_missing())                          # still inside the start window
        while r.t_min < r.copies.t0_min + MODULE_MISSING_MIN + 2:
            r.copies.step(1.0)
        self.assertTrue(r.module_missing())

    def test_offline_policy_by_setting(self):
        r, sink, clock = make_runner(fact_policy="offline")
        r.tick()
        r.handle_event(*event("control", "/features/scenario", {"preset": "fork", "kip": 1}, seq=1))
        self.assertEqual(r.copies.fact_mode, "offline")
        self.assertFalse(r.module_missing())


class DamAlarmCallTest(unittest.TestCase):
    def test_calling_the_technologist_ends_the_dam_alarm(self):
        cs = CopySet(None, 42, "", kip=1, safety=True)
        fact = cs.copies["fact"]
        for _ in range(20):
            cs.step(1.0)
        st = fact.state
        self.assertTrue(st.flags.get("piezo"))
        self.assertEqual(st.water.state, "ALARM")
        self.assertEqual(st.people["person-water"].state, "FREE")
        cs.call("water")                                              # a node call, as the journal sends it
        cs.step(1.0)
        self.assertEqual(st.people["person-water"].state, "WORK")      # the technologist is on the way and at the dam
        for _ in range(80):
            cs.step(1.0)
        self.assertFalse(st.flags.get("piezo"))
        self.assertNotEqual(st.water.state, "ALARM")
        self.assertEqual(st.people["person-water"].state, "FREE")

    def test_without_a_call_the_alarm_stays(self):
        cs = CopySet(None, 42, "", kip=1, safety=True)
        for _ in range(240):
            cs.step(1.0)
        self.assertTrue(cs.copies["fact"].state.flags.get("piezo"))

    def test_issue_thing_of_the_dam_alarm_is_a_decision_not_a_crew_job(self):
        r, sink, clock = make_runner()
        r.tick()
        r.handle_event(*event("control", "/features/scenario", {"id": "", "preset": "", "safety": 1}, seq=1))
        r.handle_event(*event("mod-priority", "/features/issue_map",
                              {"properties": {"value": {"issue-2": {"node": "water", "kind": "dam_alarm"}}}}))
        self.assertEqual(r.plant_call("issue-2"), ("piezo", "water"))
        for _ in range(15):
            r.copies.step(1.0)
        r.handle_event(*event("journal", "/features/last", {"action": "call", "issue": "issue-2"}, seq=1))
        self.assertEqual(r.stats.calls, 1)
        st = r.plant.state
        r.copies.step(1.0)
        self.assertEqual(st.people["person-water"].state, "WORK")
        for _ in range(80):
            r.copies.step(1.0)
        self.assertFalse(st.flags.get("piezo"))

    def test_cancel_clears_the_alarm_and_the_timer(self):
        cs = CopySet(None, 42, "", kip=1, safety=True)
        for _ in range(20):
            cs.step(1.0)
        cs.call("water")
        cs.copies["fact"].cancel_scenario()
        self.assertFalse(cs.copies["fact"].state.flags.get("piezo"))
        self.assertEqual(cs.copies["fact"]._piezo_until, NO_VALUE)


class PagesTest(unittest.TestCase):
    def test_reset_button_has_one_name_and_a_visible_confirmation(self):
        app = read("app.js")
        self.assertIn(">Сбросить 08:00</button>", app)
        self.assertNotIn("Начать смену заново", app)
        self.assertIn('id="sim-reset-yes"', app)
        self.assertIn("'/api/reset', { seed }", app)
        for name in ("README.md", "SUBMISSION.md"):
            path = os.path.join(os.path.dirname(ROOT), name)
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    text = f.read()
                self.assertNotIn("Сбросить 08:00 (seed 42)", text)
                self.assertNotIn("Начать смену заново", text)

    def test_economics_shows_a_loading_line_before_a_failure(self):
        x = read("exp23.js")
        self.assertIn("failed: false", x)
        self.assertIn("Загружаю итог опыта…", x)
        for name in ("pages.js", "views.js"):
            t = read(name)
            self.assertNotIn("Итог опыта не загружен", t)
            self.assertIn("AKT.exp23.missing()", t)

    def test_calibration_time_is_a_neutral_note(self):
        v = read("views.js")
        self.assertIn("calibration took", v)
        self.assertIn("на числа это не влияет", v)
        self.assertIn("const hard = (r.errors || []).filter", v)

    def test_no_station_copper_and_no_x1200_promise(self):
        a = read("app.js")
        self.assertNotIn("Медь ${m ? 'линии ' + m[1] : 'станции'}", a)
        self.assertIn("'фабрики'}: база", a)
        self.assertNotIn("быстро до 20:00", a)
        self.assertIn("×60–×90", a)

    def test_stock_note_does_not_promise_two_days_for_a_growing_pile(self):
        a = read("app.js")
        self.assertIn("AKT.stockNote", a)
        self.assertNotIn("'запас > 2 суток']", read("line.js"))
        self.assertIn("AKT.stockNote(s).short", read("line.js"))
        self.assertIn("запас не убывает", a)

    def test_modules_page_reports_who_called(self):
        m = read("modview.js")
        self.assertIn("policyHtml", m)
        self.assertIn("Копия «с двойником» шла по вызовам модуля", m)
        self.assertIn("r.policy", m)

    def test_pek_readings_are_stated_together(self):
        pages = read("pages.js")
        self.assertNotIn("(163 кт = 2 суток по ПЭК)'", pages)
        self.assertIn("8.16", pages)
        sc = json.loads(read("scenarios.json"))
        text = json.dumps(sc, ensure_ascii=False)
        self.assertNotIn("(163 кт ≈ 2 суток по ПЭК) держит фабрику", text)
        self.assertIn("8.16", text)


class NoDeadLinksTest(unittest.TestCase):
    """Files of the team's working notes are not part of the repository: no document, page or comment points to them."""
    NAMES = re.compile(r"README_aktogay|facts_round2|facts_pit_line2|facts_savings|facts_2026|SOURCES_(?:thresholds|failures|round\d|sensors)|"
                       r"RUN_LOCAL|FEATURES_22|UI_RULES_28|gaps/")

    def test_no_reference_to_files_outside_the_repository(self):
        base = os.path.dirname(ROOT)
        files = []
        for root_dir in (ROOT, os.path.join(base, "final_docs")):
            for dp, dn, fn in os.walk(root_dir):
                dn[:] = [d for d in dn if d not in ("__pycache__", "data", "vendor", "sat")]
                for f in fn:
                    if f.endswith((".py", ".js", ".md", ".json", ".html", ".yml", ".sh")) and f != "test_final25.py":
                        files.append(os.path.join(dp, f))
        for name in ("README.md", "SUBMISSION.md", "VALIDATION.md", "PARAMETERS.md", "READINESS.md", "DATA_LICENSES.md"):
            p = os.path.join(base, name)
            if os.path.exists(p):
                files.append(p)
        bad = []
        for p in files:
            with open(p, encoding="utf-8") as f:
                for n, line in enumerate(f, 1):
                    if self.NAMES.search(line):
                        bad.append(f"{os.path.relpath(p, base)}:{n}")
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
