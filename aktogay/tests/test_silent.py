"""Silent overspends and the shift: SAG energy, collector overdose, water leak by the balance,
the handover sheet at 07:30 / 19:30 and the escalation of a called person who has not arrived."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests import mod_support as ms  # noqa: E402
from modules import losses, ore, priority  # noqa: E402
from modules.store import NO_VALUE  # noqa: E402
from sim import events as ev  # noqa: E402
from sim.params import default as sim_default  # noqa: E402
from sim.plant import CopySet, Plant  # noqa: E402

T0 = 9 * 60 + 20.0


def modules(st, prm):
    lm = losses.LossesModule(prm, st, ms.ROLES)
    om = ore.OreModule(prm, st)
    pm = priority.PriorityModule(prm, st, lm, om, ms.ROLES)
    return lm, om, pm


def run_scenario(text, minutes, every=5):
    """The modules on the simulator's measured snapshot of the fact copy, every `every` model minutes."""
    cs = CopySet(None, 42, text)
    fact = cs.copies["fact"]
    st, prm = ms.make_store(fact.t_min)
    lm, om, pm = modules(st, prm)
    feats = issues = lfeats = None
    for _ in range(int(minutes // every)):
        for _ in range(every):
            cs.step()
        t = fact.t_min
        st.update_from_search(ms.items_from_plant(fact))
        lfeats = lm.compute(t)
        if t % 15 == 0:
            om.compute(t)
        feats, issues = pm.compute(t, seed=1)
    return cs, fact, lm, pm, lfeats, feats, issues


class SilentCausesSimTest(unittest.TestCase):
    """The simulator side: the causes change what they should and nothing else."""

    def test_parse_and_hide(self):
        spec = ev.parse_scenario("energy:1+reagent:2+leak", 480.0, sim_default())
        self.assertEqual({(e.kind, e.line) for e in spec.events}, {("energy", 1), ("reagent", 2), ("leak", 0)})
        self.assertEqual(ev.scenario_label(spec, hidden=False), "")            # silent: not shown before found
        causes = ev.preset_causes(spec, sim_default())
        self.assertEqual({c.kind for c in causes}, {"energy", "reagent", "leak"})

    def test_free_run_draws_do_not_change_the_lab_causes(self):
        prm = sim_default()
        a = ev.draw_hidden_causes(5, 0.0, 7 * 1440.0, prm)
        b = ev.draw_hidden_causes(5, 0.0, 7 * 1440.0, prm.copy(hc_silent_per_shift=1.5))
        self.assertEqual([(c.kind, c.t_start_min) for c in a], [(c.kind, c.t_start_min) for c in b])
        s = ev.draw_hidden_causes(5, 0.0, 7 * 1440.0, prm, silent=True)
        self.assertTrue(s)
        self.assertTrue({c.kind for c in s} <= set(ev.SILENT))
        self.assertTrue(all(c.line == 0 for c in s if c.kind == "leak"))

    def test_effects(self):
        prm = sim_default()
        cs = [ev.preset_causes(ev.parse_scenario(x, 0.0, prm), prm)[0] for x in ("energy:1", "reagent:1", "leak")]
        fx = ev.cause_effects(cs, 1, 600.0, prm)
        self.assertAlmostEqual(fx.sag_e_mult, 1.0 + prm["hc_energy_frac"])
        self.assertAlmostEqual(fx.dose_ratio, 1.0 + prm["hc_reagent_over"])
        self.assertEqual(fx.leak_frac, 0.0)                                   # the leak is site-wide (line 0)
        self.assertAlmostEqual(ev.cause_effects(cs, 0, 600.0, prm).leak_frac, prm["hc_leak_frac"])


class EnergyTest(unittest.TestCase):
    def test_sag_energy_found_with_money_and_metallurgist(self):
        cs, fact, lm, pm, lf, feats, issues = run_scenario("energy:1", 240)
        base = cs.copies["base"].state.line(1).sag
        sag = fact.state.line(1).sag
        self.assertGreater(sag.e_kwh_t, base.e_kwh_t * 1.03)                  # more kWh per t
        self.assertLess(sag.feed_tph, base.feed_tph * 0.97)                    # at the power limit: fewer t/h
        r = lm.results["sag-1"]
        self.assertEqual(r.status, "loss")
        self.assertGreater(lf["sag-1_e_meas_kwh_t"], lf["sag-1_e_exp_kwh_t"])
        self.assertGreater(lf["sag-1_energy_usd_h"], 0.0)
        self.assertIn("[литература]", r.cause)                                 # Sossego only for scale
        self.assertIn("Sossego", r.cause)
        i = next(f for f in issues.values() if f["node"] == "sag-1")
        self.assertEqual(i["kind"], "loss_sag")
        self.assertEqual(i["person"], "person-metallurgist")
        self.assertGreater(i["loss_usd_h"], lf["sag-1_energy_usd_h"])           # energy plus copper at the limit
        self.assertIn("перерасход энергии", lf["silent_text"])
        # the metallurgist's call ends the cause after travel and the decision
        fact.call("sag-1")
        c = next(c for c in fact.state.causes if c.kind == "energy")
        self.assertNotEqual(c.t_end_min, NO_VALUE)
        self.assertEqual(c.found_by, "module")

    def test_energy_only_below_the_power_limit(self):
        st, prm = ms.make_store(T0, {"sag-1": {"power_kw": 20000.0, "feed_tph": 2700.0}})
        lm, _om, _pm = modules(st, prm)
        r = lm.eval_sag(T0, 1, 35.0, 0.41, 87.2)
        self.assertFalse(r.detail["limited"])
        self.assertGreater(r.detail["energy_usd_h"], 0.0)
        self.assertIn("медь не теряется", r.cause)


class ReagentTest(unittest.TestCase):
    def test_overdose_found_by_the_tank_not_the_meter(self):
        cs, fact, lm, pm, lf, feats, issues = run_scenario("reagent:2", 150)
        r2 = fact.state.line(2).rougher
        self.assertAlmostEqual(r2.dose_meas_gt, r2.dose_sp_gt)                  # the meter shows the setpoint
        self.assertGreater(r2.dose_true_gt, r2.dose_sp_gt * 1.3)
        base = cs.copies["base"].state.line(2)
        self.assertLessEqual(fact.state.line(2).recovery, base.recovery + 0.05)  # no recovery gain
        g = lm.reagent[2]
        self.assertEqual(g["status"], "loss")
        self.assertGreater(g["excess"], 0.25)
        self.assertGreater(lf["rougher-2_reagent_usd_h"], 0.0)
        self.assertEqual(lm.reagent[1]["status"], "noise")                       # the other line is clean
        self.assertIn("flowmeter-2", lf["suspect_sensors"])
        self.assertIn("[допущение]", g["text"])                                  # the price is an assumption
        self.assertIn("[аналог]", g["text"])                                     # Sungun is a reference
        i = next(f for f in issues.values() if f["kind"] == "reagent_over")
        self.assertEqual(i["node"], "rougher-2")
        self.assertEqual(i["person"], "person-kip")
        self.assertGreater(i["loss_usd_h"], 0.0)
        job = fact.call("rougher-2")
        self.assertIsNotNone(job)
        self.assertEqual(job.issue, "reagent:2")
        fact.run_until(job.t_done_min + 5)
        self.assertFalse(any(c.kind == "reagent" for c in fact.state.causes))


class LeakTest(unittest.TestCase):
    def test_leak_only_in_the_balance(self):
        cs, fact, lm, pm, lf, feats, issues = run_scenario("leak", 150)
        w = fact.state.water
        self.assertGreater(w.leak_m3h, 0.0)
        snap = fact.snapshot()
        self.assertEqual(snap["water"]["leak_m3h"], -1.0)                        # no meter on a leak
        self.assertNotEqual(w.state, "SHORT")                                    # silent: below the intake cap
        self.assertAlmostEqual(lf["water_leak_m3h"], w.leak_m3h, delta=0.15 * w.leak_m3h)
        self.assertGreater(lf["water_leak_usd_h"], 0.0)
        i = next(f for f in issues.values() if f["kind"] == "water_short")
        self.assertIn("тихая утечка воды", i["text"])
        self.assertIn("невязка водного баланса", i["text"])
        job = fact.call("water")
        self.assertIsNotNone(job)
        self.assertEqual(job.issue, "leak")
        fact.run_until(job.t_done_min + 5)
        self.assertFalse(any(c.kind == "leak" for c in fact.state.causes))
        self.assertEqual(fact.state.water.leak_m3h, 0.0)

    def test_no_leak_without_a_cause(self):
        _cs, _fact, _lm, _pm, lf, _feats, issues = run_scenario("", 120)
        self.assertEqual(lf["water_leak_m3h"], 0.0)
        self.assertFalse(any(f["kind"] == "water_short" for f in issues.values()))


def fork_ov(**extra):
    ov = {"crusher-2": {"state": "STOP", "tph": 0.0, "power_kw": 0.0, "lube_kpa": 150.0},
          "conveyor-2": {"state": "STOP", "tph": 0.0, "power_kw": 0.0},
          "stockpile-2": {"level_t": 30000.0, "in_tph": 0.0, "hours_left": 7.78}}
    ov.update(extra)
    return ov


class EscalationTest(unittest.TestCase):
    def test_not_arrived_then_remind(self):
        st, prm = ms.make_store(T0, fork_ov())
        lm, om, pm = modules(st, prm)
        lm.compute(T0)
        om.compute(T0)
        _f, issues = pm.compute(T0, seed=1)
        name = next(n for n, f in issues.items() if f["node"] == "crusher-2")
        t1 = T0 + 5
        st.update_from_search(ms.snapshot(t1, fork_ov(journal={"last": {"seq": 1, "issue": name, "action": "call"}})))
        lm.compute(t1)
        feats, issues = pm.compute(t1, seed=1)
        self.assertEqual(issues[name]["status"], "CALLED")
        self.assertAlmostEqual(issues[name]["eta"], t1 + prm["q_arrive_hi_min"])
        self.assertEqual(issues[name]["escalation"], "")
        # the crew never left: ETA + 15 min passed
        t2 = t1 + prm["q_arrive_hi_min"] + prm["esc_after_min"] + 5
        st.update_from_search(ms.snapshot(t2, fork_ov(journal={"last": {"seq": 1, "issue": name, "action": "call"}})))
        lm.compute(t2)
        feats, issues = pm.compute(t2, seed=1)
        self.assertIn("не прибыл", issues[name]["escalation"])
        self.assertIn("напомнить или позвать следующего", issues[name]["text"] + issues[name]["escalation"])
        log = feats["escalations"]["log"]
        self.assertEqual([e["action"] for e in log], ["late"])
        # the dispatcher reminds: a new ETA, the escalation is gone, the log keeps both
        t3 = t2 + 5
        st.update_from_search(ms.snapshot(t3, fork_ov(journal={"last": {"seq": 2, "issue": name, "action": "remind"}})))
        lm.compute(t3)
        feats, issues = pm.compute(t3, seed=1)
        self.assertEqual(issues[name]["escalation"], "")
        self.assertAlmostEqual(issues[name]["eta"], t3 + prm["remind_eta_min"])
        self.assertEqual([e["action"] for e in feats["escalations"]["log"]], ["late", "remind"])

    def test_arrived_crew_is_not_escalated(self):
        st, prm = ms.make_store(T0, fork_ov())
        lm, om, pm = modules(st, prm)
        lm.compute(T0)
        om.compute(T0)
        _f, issues = pm.compute(T0, seed=1)
        name = next(n for n, f in issues.items() if f["node"] == "crusher-2")
        t1 = T0 + 5
        st.update_from_search(ms.snapshot(t1, fork_ov(journal={"last": {"seq": 1, "issue": name, "action": "call"}})))
        pm.compute(t1, seed=1)
        t2 = t1 + 70
        st.update_from_search(ms.snapshot(t2, fork_ov(**{"crew-kip": {"state": "WORK", "task": "crusher-2",
                                                                       "free_at": t2 + 120}})))
        _f, issues = pm.compute(t2, seed=1)
        self.assertEqual(issues[name]["status"], "IN_WORK")
        self.assertEqual(issues[name]["escalation"], "")

    def test_plant_late_call_and_reminder(self):
        prm = sim_default().copy(crew_late_p=1.0)
        pl = Plant(prm, 3, mode="free")
        pl.warmup()
        pl.late_calls = True
        pl.apply_scenario(ev.parse_scenario("crusher:1", pl.t_min, prm))
        job = pl.call("crusher-1")
        self.assertGreaterEqual(job.t_arrive_min - pl.t_min, prm["crew_arrive_lo_min"] + prm["crew_late_min"] - 1e-6)
        pl.run_until(pl.t_min + 60)
        moved = pl.remind(node="crusher-1")
        self.assertAlmostEqual(moved.t_arrive_min, pl.t_min + prm["crew_remind_min"])
        self.assertEqual(pl.state.line(1).crusher.fault_until_min, moved.t_done_min)
        pl2 = Plant(prm, 3, mode="free")                                        # an ordinary call is never late
        pl2.warmup()
        pl2.apply_scenario(ev.parse_scenario("crusher:1", pl2.t_min, prm))
        j2 = pl2.call("crusher-1")
        self.assertLessEqual(j2.t_arrive_min - pl2.t_min, prm["crew_arrive_hi_min"] + 1e-6)


class HandoverTest(unittest.TestCase):
    def test_sheet_at_19_30_and_draft_always(self):
        t = 19 * 60.0
        st, prm = ms.make_store(t, fork_ov())
        lm, om, pm = modules(st, prm)
        feats = None
        for k in range(8):                                                   # 19:00 ... 19:35
            tk = t + 5 * k
            st.update_from_search(ms.snapshot(tk, fork_ov()))
            lm.compute(tk)
            if tk % 15 == 0:
                om.compute(tk)
            feats, _issues = pm.compute(tk, seed=1)
            if tk < 19 * 60 + 30:
                self.assertEqual(feats["handover"]["at"], NO_VALUE, tk)
                self.assertEqual(feats["handover_text"], "")
            self.assertIn("Открытые беды", feats["handover_draft_text"])
        ho = feats["handover"]
        self.assertEqual(ho["at"], 19 * 60 + 30)
        for head in ("Сдача смены 19:30", "Открытые беды", "Отложенные", "Приборы под подозрением",
                     "Руда на 12 ч", "Бригады"):
            self.assertIn(head, ho["text"])
        self.assertIn("Дробилка ЦПД-2", ho["text"])
        self.assertTrue(ho["crews"])

    def test_no_sheet_at_the_first_tact_and_one_per_mark(self):
        t = 7 * 60 + 30.0
        st, prm = ms.make_store(t)
        lm, om, pm = modules(st, prm)
        lm.compute(t)
        om.compute(t)
        feats, _ = pm.compute(t, seed=1)
        self.assertEqual(feats["handover"]["at"], NO_VALUE)                    # a run that starts at the mark
        marks = []
        for tk in (7 * 60 + 35.0, 19 * 60 + 25.0, 19 * 60 + 40.0, 19 * 60 + 45.0, 31 * 60 + 35.0):
            st.update_from_search(ms.snapshot(tk))
            lm.compute(tk)
            feats, _ = pm.compute(tk, seed=1)
            marks.append(feats["handover"]["at"])
        self.assertEqual(marks, [NO_VALUE, NO_VALUE, 19 * 60 + 40.0, 19 * 60 + 40.0, 31 * 60 + 35.0])
        self.assertIn("Сдача смены 07:30", feats["handover"]["text"])          # the mark, written at 07:35 next day
        self.assertIn("записан в 07:35", feats["handover"]["text"])


if __name__ == "__main__":
    unittest.main()
