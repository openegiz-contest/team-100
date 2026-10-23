"""Features 1-9, 14, 15 of the list of 22.10.2026: work permit and chain of responsibility, price of a choice,
review of the shift's calls, winter, hourly tariff, coarse grind, concentrate grade, grinding media, people in the
zone at a start, dusting of the tailings beach. Simulator side and the modules on the simulator's own snapshot."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests import mod_support as ms  # noqa: E402
from tests.test_mod_priority import T0, modules, real_store  # noqa: E402
from modules import dispatch, policy, priority  # noqa: E402
from sim import sensors as se  # noqa: E402
from sim import site_aktogay as site  # noqa: E402
from sim import utilities as ut  # noqa: E402
from sim.params import ParamSet  # noqa: E402
from sim.plant import CopySet, Plant  # noqa: E402


def run_cs(text, minutes, step=5):
    cs = CopySet(None, 42, text)
    fact = cs.copies["fact"]
    for _ in range(int(minutes)):
        cs.step()
    return cs, fact


def feats(plant, name):
    return se.measured_features(plant.state, plant.prm)[name]


class SimSideTest(unittest.TestCase):
    def test_season_by_date_and_weather(self):
        p = ParamSet()
        self.assertTrue(ut.is_winter(0.0, p))            # 1 January
        self.assertTrue(ut.is_winter(330.0, p))          # late November
        self.assertFalse(ut.is_winter(295.0, p))         # 23 October
        self.assertFalse(ut.is_winter(180.0, p))
        a = ut.weather(600.0, 7, True, False, p)
        self.assertEqual(a, ut.weather(600.0, 7, True, False, p))     # deterministic
        self.assertLess(a[0], -5.0)                                    # winter: frost, snow-covered beach
        self.assertLess(a[2], 20.0)
        d = ut.weather(600.0, 7, False, True, p)
        self.assertGreaterEqual(d[1], p["scen_dust_wind_ms"])
        self.assertGreaterEqual(d[2], p["scen_dust_dry_pct"])

    def test_winter_scenario_lowers_the_return_and_publishes_the_flag(self):
        _cs0, base = run_cs("", 90)
        _cs, w = run_cs("winter", 90)
        fw, fb = feats(w, "water"), feats(base, "water")
        self.assertEqual(fw["winter"], 1.0)
        self.assertEqual(fb["winter"], 0.0)
        self.assertLess(fw["air_temp_c"], 0.0)
        self.assertGreater(fb["air_temp_c"], 5.0)
        self.assertLess(w.state.water.recycle_m3h, base.state.water.recycle_m3h)
        self.assertEqual(w.prm["winter_return_frac"], 0.03)
        # cancel returns to the base season
        cs, f = run_cs("winter", 10)
        cs.cancel()
        self.assertEqual(cs.copies["fact"].winter_on, False)

    def test_dust_scenario_wind_and_dry_beach_for_a_while(self):
        cs, f = run_cs("dust", 60)
        w = feats(f, "water")
        self.assertGreaterEqual(w["wind_ms"], f.prm["scen_dust_wind_ms"] - 1e-6)
        self.assertGreaterEqual(w["beach_dry_pct"], f.prm["scen_dust_dry_pct"] - 1e-6)
        cs2, f2 = run_cs("dust", int(f.prm["scen_dust_h"] * 60) + 30)
        self.assertLess(feats(f2, "water")["beach_dry_pct"], f.prm["scen_dust_dry_pct"])

    def test_startup_scenario_people_inside_then_start_command(self):
        cs = CopySet(None, 42, "startup:1")
        fact = cs.copies["fact"]
        seen_permit = seen_cmd = False
        both = False
        for _ in range(150):
            cs.step()
            ball = feats(fact, "ball-1a")
            pm = feats(fact, "person-mill-mech")
            if pm["permit"] == "ball-1a":
                seen_permit = True
            if ball["start_cmd"] == 1.0:
                seen_cmd = True
                both = both or (pm["permit"] == "ball-1a" and pm["state"] == "WORK")
        self.assertTrue(seen_permit)
        self.assertTrue(seen_cmd)
        self.assertTrue(both, "the start command must come while the mechanic is inside")
        self.assertEqual(feats(fact, "ball-2a")["start_cmd"], 0.0)

    def test_the_call_to_the_shift_head_cancels_the_start_command(self):
        cs = CopySet(None, 42, "startup:1")
        fact = cs.copies["fact"]
        for _ in range(75):
            cs.step()
        self.assertEqual(feats(fact, "ball-1a")["start_cmd"], 1.0)
        self.assertIsNone(fact.call("ball-1a"))
        self.assertEqual(feats(fact, "ball-1a")["start_cmd"], 0.0)
        cs.step()
        self.assertEqual(fact.state.people["person-shift-head"].state, "WORK")      # the head is busy with it
        for _ in range(60):
            cs.step()
        self.assertEqual(feats(fact, "ball-1a")["start_cmd"], 0.0)

    def test_balls_scenario_raises_consumption_and_conc_scenario_lowers_grade(self):
        _c, base = run_cs("", 180)
        _c, b = run_cs("balls:1", 180)
        gb, g0 = feats(b, "line-1")["balls_gt"], feats(base, "line-1")["balls_gt"]
        self.assertAlmostEqual(g0, b.prm["ball_media_gt"], delta=0.12 * b.prm["ball_media_gt"])
        self.assertGreater(gb, 1.15 * g0)
        self.assertAlmostEqual(feats(b, "line-2")["balls_gt"], g0, delta=0.15 * g0)
        _c, c = run_cs("conc:1", 180)
        d = c.state.lines[0].flot.conc_cu - base.state.lines[0].flot.conc_cu
        self.assertAlmostEqual(d, -c.prm["hc_conc_drop_pp"], delta=0.6)
        # the copper is the same, the mass is bigger
        self.assertAlmostEqual(c.state.lines[0].flot.cu_tph, base.state.lines[0].flot.cu_tph, delta=0.4)
        self.assertGreater(c.state.lines[0].flot.conc_tph, base.state.lines[0].flot.conc_tph)

    def test_free_run_draws_do_not_change(self):
        """The new causes are never drawn in free run: the silent kinds stay the three of before."""
        from sim import events as ev
        self.assertEqual(ev.SILENT, ("energy", "reagent", "leak"))
        self.assertEqual(ev.EXTRA, ("balls", "conc"))

    def test_call_via_deputy_forms_one_more_team(self):
        cs = CopySet(None, 42, "crusher:1")
        fact = cs.copies["fact"]
        for _ in range(3):
            cs.step()
        job1 = fact.call("crusher-1", issue="crusher:1")
        self.assertIsNotNone(job1)
        # the crew-cpd has one team and is busy; a second crusher stop goes to the deputy's team
        fact.state.line(2).crusher.fault = "scenario"
        fact.state.line(2).crusher.state = "STOP"
        job2 = fact.call("crusher-2", issue="crusher:2", via="deputy")
        self.assertIsNotNone(job2)
        self.assertLess(job2.t_arrive_min, job1.t_done_min)
        self.assertEqual(fact.state.crews["crew-cpd"].count, 2)

    def test_site_deputies_match_the_module_table(self):
        self.assertEqual(site.DEPUTY, dispatch.DEPUTY_DEFAULT)
        self.assertIn(site.SHIFT_HEAD, {p[0] for p in site.PEOPLE})
        for k, v in site.DEPUTY.items():
            self.assertIn(k, {p[0] for p in site.PEOPLE})
            self.assertIn(v, {p[0] for p in site.PEOPLE})


class TariffTest(unittest.TestCase):
    def test_daily_mean_is_one_and_bands_order(self):
        prm = ms.default()
        mean = sum(dispatch.tariff_mult(h + 0.5, prm) for h in range(24)) / 24.0
        self.assertAlmostEqual(mean, 1.0, places=6)
        self.assertEqual(dispatch.tariff_band(3.0, prm), "night")
        self.assertEqual(dispatch.tariff_band(12.0, prm), "day")
        self.assertEqual(dispatch.tariff_band(19.0, prm), "peak")
        self.assertLess(dispatch.tariff_mult(3.0, prm), dispatch.tariff_mult(12.0, prm) )
        self.assertLess(dispatch.tariff_mult(12.0, prm), dispatch.tariff_mult(19.0, prm))
        info = dispatch.tariff_info(19.0 * 60, prm)
        self.assertEqual(info["band_ru"], "пик")
        self.assertIn("допущение", info["text"])
        self.assertIn("16 тг/кВт·ч — факт", info["text"])

    def test_energy_overspend_price_follows_the_hour(self):
        from modules.losses import NodeResult
        usd = {}
        for hour in (3, 19):
            t = hour * 60.0
            st, prm = real_store(t)
            lm, om, pm = modules(st, prm)
            lm.compute(t)
            r = lm.eval_sag(t, 1, 35.0, 0.41, 87.0)
            r.status, r.gap_cu_tph, r.detected_at, r.cause = "loss", 0.5, t - 30.0, "перерасход энергии"
            r.detail = dict(r.detail, energy_usd_h=1000.0, limited=False)
            lm.results = {"sag-1": r}
            tr = [x for x in pm.troubles(t) if x.kind == "loss_sag"][0]
            usd[hour] = tr.rate_usd_h
            self.assertIn("тарифу часа", tr.text)
        self.assertLess(usd[3], 1000.0)
        self.assertGreater(usd[19], 1000.0)


class ModulesTest(unittest.TestCase):
    def issues_of(self, ov, t=T0, batches=None):
        st, prm = real_store(t, ov, batches)
        lm, om, pm = modules(st, prm)
        lm.compute(t)
        om.compute(t)
        feats_, issues = pm.compute(t, seed=3)
        return pm, feats_, issues

    def test_startup_with_people_inside_is_s0_first(self):
        ov = {"person-mill-mech": {"state": "WORK", "location": "ball-1a", "task": "ball-1a", "permit": "ball-1a",
                                   "free_at": T0 + 120.0},
              "ball-1a": {"state": "STOP", "power_kw": 0.0, "start_cmd": 1.0},
              "water": {"wind_ms": 3.0}}
        pm, f, issues = self.issues_of(ov)
        top = min(issues.values(), key=lambda x: x["rank"])
        self.assertEqual((top["kind"], top["safety_class"], top["node"]), ("startup_zone", "S0", "ball-1a"))
        self.assertEqual(top["person"], "person-shift-head")
        self.assertIn("Не включать! Работают люди!", top["text"])
        self.assertIn("п. 63", top["text"])
        self.assertEqual(top["loss_usd_h"], -1.0)                      # S0 is never counted in money
        # no start command: no S0
        ov["ball-1a"]["start_cmd"] = 0.0
        _pm, _f, issues = self.issues_of(ov)
        self.assertNotIn("startup_zone", {x["kind"] for x in issues.values()})

    def test_dust_is_ecology_s1_after_people_before_money(self):
        ov = {"water": {"wind_ms": 14.0, "beach_dry_pct": 85.0},
              "person-mill-mech": {"state": "WORK", "location": "ball-1a", "task": "ball-1a", "permit": "ball-1a",
                                   "free_at": T0 + 60.0},
              "ball-1a": {"state": "STOP", "power_kw": 0.0, "start_cmd": 1.0},
              "crusher-2": {"state": "STOP", "tph": 0.0, "lube_kpa": 250.0}, "stockpile-2": {"hours_left": 1.0}}
        pm, f, issues = self.issues_of(ov)
        order = sorted(issues.values(), key=lambda x: x["rank"])
        kinds = [x["kind"] for x in order]
        self.assertEqual(kinds[0], "startup_zone")
        self.assertEqual(kinds[1], "tailings_dust")
        self.assertEqual(order[1]["safety_class"], "S1")
        self.assertIn("crusher_stop", kinds[2:])
        self.assertIn("экология", order[1]["text"])
        # weather back to normal: no dust issue
        ov["water"] = {"wind_ms": 5.0, "beach_dry_pct": 85.0}
        _pm, _f, issues = self.issues_of(ov)
        self.assertNotIn("tailings_dust", {x["kind"] for x in issues.values()})

    def test_coarse_grind_has_a_price_and_the_metallurgist(self):
        pm, f, issues = self.issues_of({"cyclones-1": {"p80_um": 215.0}})
        g = next(x for x in issues.values() if x["kind"] == "grind_coarse")
        self.assertIn("Металлург смены", g["responsible"])
        self.assertIn("извлечение ниже", g["text"])
        self.assertGreater(g["loss_usd_h"], 0.0)
        # inside the norm: nothing
        _pm, _f, issues = self.issues_of({"cyclones-1": {"p80_um": 185.0}})
        self.assertNotIn("grind_coarse", {x["kind"] for x in issues.values()})

    def test_low_concentrate_grade_is_a_priced_trouble(self):
        pm, f, issues = self.issues_of({"flot-1": {"conc_cu": 21.5, "conc_tph": 64.0}})
        c = next(x for x in issues.values() if x["kind"] == "conc_low")
        prm = ms.default()
        self.assertAlmostEqual(c["loss_usd_h"], 64.0 * (prm["conc_norm_pct"] - 21.5) * prm["conc_penalty_usd_dmt_pp"],
                               delta=200.0)
        self.assertIn("допущение", c["text"])
        self.assertIn("96,5 %", c["text"])
        _pm, _f, issues = self.issues_of({"flot-1": {"conc_cu": 24.0}})
        self.assertNotIn("conc_low", {x["kind"] for x in issues.values()})

    def test_balls_overuse_is_a_deviation_not_an_issue(self):
        pm, f, issues = self.issues_of({"line-1": {"balls_gt": 760.0}})
        self.assertEqual(issues, {})
        self.assertEqual(len(f["deviations"]["items"]), 1)
        self.assertIn("Шары, линия 1", f["deviations_text"])
        self.assertIn("в очередь не попадает", f["deviations_text"])
        self.assertIn("Отклонения: Шары, линия 1", f["handover_draft_text"])
        self.assertGreater(f["deviations"]["items"][0]["usd_h"], 0.0)
        _pm, f2, _i = self.issues_of({"line-1": {"balls_gt": 610.0}})
        self.assertEqual(f2["deviations_text"], "")

    def test_winter_makes_water_troubles_dearer_and_urgent(self):
        water = {"state": "SHORT", "leak_m3h": -1.0, "cut_tph": 300.0, "short_m3h": 120.0, "intake_cap_m3h": 6126.0}
        _pm, _f, summer = self.issues_of({"water": water})
        _pm, f, winter = self.issues_of({"water": dict(water, winter=1.0, air_temp_c=-18.0)})
        s = next(x for x in summer.values() if x["kind"] == "water_short")
        w = next(x for x in winter.values() if x["kind"] == "water_short")
        prm = ms.default()
        self.assertAlmostEqual(w["loss_usd_h"] / s["loss_usd_h"], prm["winter_water_mult"], places=2)
        self.assertIn("ЗИМА", w["text"])
        self.assertIn("замерзания труб", w["text"])
        self.assertNotIn("ЗИМА", s["text"])
        self.assertIn("Зима", f["season_text"])
        self.assertIn("Зима: возврат воды", f["handover_draft_text"])

    def test_chain_when_the_main_person_is_busy_on_a_permit(self):
        busy = {"person-crusher-mech": {"state": "WORK", "location": "crusher-1", "task": "crusher-1",
                                         "permit": "crusher-1", "free_at": T0 + 90.0}}
        ov = dict(busy, **{"crusher-2": {"state": "STOP", "tph": 0.0, "lube_kpa": 250.0},
                           "stockpile-2": {"hours_left": 3.0}})
        pm, f, issues = self.issues_of(ov)
        i = next(x for x in issues.values() if x["node"] == "crusher-2")
        self.assertIn("занят по наряду-допуску на Дробилка 1 до", i["chain_text"])
        self.assertIn("п. 12, 63", i["chain_text"])
        self.assertIn("заместитель Механик фабрики", i["chain_text"])
        self.assertEqual(i["chain"]["via"], "deputy")
        self.assertEqual(i["chain"]["pick"], "person-mill-mech")
        self.assertIn("предложить", i["text"])
        self.assertTrue(i["permit_text"])
        # the deputy is busy too: the shift head
        ov2 = dict(ov, **{"person-mill-mech": {"state": "TRAVEL", "location": "line-1", "task": "sag-1",
                                               "free_at": T0 + 30.0}})
        pm, f, issues = self.issues_of(ov2)
        i = next(x for x in issues.values() if x["node"] == "crusher-2")
        self.assertEqual(i["chain"]["via"], "head")
        self.assertEqual(i["chain"]["pick"], "person-shift-head")
        self.assertIn("предложить: Начальник смены фабрики", i["chain_text"])
        # everybody free: nothing to say
        _pm, _f, issues = self.issues_of({"crusher-2": ov["crusher-2"], "stockpile-2": ov["stockpile-2"]})
        i = next(x for x in issues.values() if x["node"] == "crusher-2")
        self.assertEqual(i["chain_text"], "")
        self.assertEqual(i["chain"]["via"], "")

    def test_price_of_choice_one_crew_two_troubles(self):
        ov = {"crusher-1": {"state": "STOP", "tph": 0.0, "lube_kpa": 250.0}, "stockpile-1": {"level_t": 36000.0},
              "crusher-2": {"state": "STOP", "tph": 0.0, "lube_kpa": 250.0}, "stockpile-2": {"level_t": 8000.0}}
        pm, f, issues = self.issues_of(ov)
        a = next(x for x in issues.values() if x["node"] == "crusher-1")
        b = next(x for x in issues.values() if x["node"] == "crusher-2")
        self.assertEqual(a["choice_text"], b["choice_text"])
        txt = a["choice_text"]
        self.assertIn("Бригада одна", txt)
        self.assertIn("на двух линиях", txt)
        self.assertIn("цена неверного выбора", txt)
        self.assertIn("[оценка на модели]", txt)
        # the cheaper first call is the one ranked first (the stock of line 2 ends sooner)
        self.assertLess(b["rank"], a["rank"])
        self.assertIn("Сначала «Дробилка 2»", txt)
        # a trouble that needs another crew has no choice text
        ov2 = dict(ov)
        ov2["crusher-1"] = {"state": "RUN"}
        ov2["stockpile-1"] = {"level_t": 28000.0}
        ov2["crusher-2"] = {"state": "STOP", "tph": 0.0, "lube_kpa": 150.0}
        _pm, _f, issues = self.issues_of(ov2)
        self.assertTrue(all(x["choice_text"] == "" for x in issues.values()))

    def test_first_choice_losses_are_consistent_with_rank(self):
        st, prm = real_store(T0, {"crusher-1": {"state": "STOP", "tph": 0.0, "lube_kpa": 250.0},
                                  "stockpile-1": {"level_t": 36000.0},
                                  "crusher-2": {"state": "STOP", "tph": 0.0, "lube_kpa": 250.0},
                                  "stockpile-2": {"level_t": 8000.0}})
        lm, om, pm = modules(st, prm)
        lm.compute(T0)
        om.compute(T0)
        pm.compute(T0, seed=3)
        trs = [i.trouble for i in pm.issues.values()]
        loss = policy.first_choice_losses(trs, T0, prm, pm._crews(T0), seed=5)
        self.assertEqual(set(loss), {t.id for t in trs})
        best = min(loss, key=lambda k: loss[k][0])
        self.assertEqual(best, "crusher-2:stop")
        self.assertEqual(policy.first_choice_losses(trs[:1], T0, prm), {})

    def test_review_of_the_shift_counts_a_wrong_call_in_cu_and_usd(self):
        ov = {"crusher-1": {"state": "STOP", "tph": 0.0, "lube_kpa": 250.0}, "stockpile-1": {"level_t": 36000.0},
              "crusher-2": {"state": "STOP", "tph": 0.0, "lube_kpa": 250.0}, "stockpile-2": {"level_t": 8000.0}}
        st, prm = real_store(T0, ov)
        lm, om, pm = modules(st, prm)
        lm.compute(T0)
        om.compute(T0)
        feats_, issues = pm.compute(T0, seed=3)
        self.assertIn("Развилок за смену не было", pm.review_text(pm._shift_index(T0)))
        wrong = next(n for n, x in issues.items() if x["node"] == "crusher-1")       # rank 2 called first
        t = T0 + 5.0
        st.update_from_search(real_snapshot_with(t, ov, {"journal": {"last": {
            "seq": 1, "issue": wrong, "action": "call", "role": "Механик ЦПД", "text": "", "sim_time": t}}}))
        feats_, issues = pm.compute(t, seed=3)
        txt = feats_["review_text"]
        self.assertIn("А если бы позвали иначе?", txt)
        self.assertIn("позвали «Дробилка 1» первой, по модели лучше «Дробилка 2»", txt)
        self.assertIn("т Cu", txt)
        self.assertIn("[оценка на модели]", txt)
        self.assertIn("не оценка людей", txt)
        self.assertGreater(feats_["decisions"]["regret_usd"], 0.0)
        self.assertIn("А если бы позвали иначе?", feats_["handover_draft_text"])
        # the right call is no regret
        pm2 = modules(*real_store(T0, ov))[2]
        pm2.store.update_from_search(real_snapshot_with(T0, ov, {}))
        lm2 = pm2.losses
        lm2.compute(T0)
        f0, is0 = pm2.compute(T0, seed=3)
        right = next(n for n, x in is0.items() if x["node"] == "crusher-2")
        pm2.store.update_from_search(real_snapshot_with(T0 + 5.0, ov, {"journal": {"last": {
            "seq": 1, "issue": right, "action": "call", "role": "Механик ЦПД", "text": "", "sim_time": T0 + 5.0}}}))
        f1, _ = pm2.compute(T0 + 5.0, seed=3)
        self.assertIn("потерь от порядка нет", f1["review_text"])

    def test_new_things_json_features_reach_the_publisher_catalog(self):
        from sim.publish import Catalog
        cat = Catalog()
        self.assertIsNotNone(cat.spec("water", "wind_ms"))
        self.assertIsNotNone(cat.spec("person-mill-mech", "permit"))
        self.assertIsNotNone(cat.spec("ball-1a", "start_cmd"))
        self.assertIsNotNone(cat.spec("line-1", "balls_gt"))
        self.assertIsNotNone(cat.spec("issue-3", "chain_text"))
        self.assertIsNotNone(cat.spec("mod-priority", "review_text"))
        self.assertIsNotNone(cat.spec("mod-priority", "deviations"))


def real_snapshot_with(t, ov, extra):
    from tests.test_mod_priority import real_snapshot
    o = dict(ov)
    o.update(extra)
    return real_snapshot(t, o)


if __name__ == "__main__":
    unittest.main()
