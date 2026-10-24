"""Tier S of 23.10.2026 (FEATURES_22.md): winter road and tired driver in the pit, cyclone roping with ball mill overload,
pH sensor under suspicion with the age of every measurement, uneven feed of the line 2 HPGR, ore changed / regime old,
mantle change of the primary crusher, oil contamination and failure of an excavator, the page «Изнутри» and the opt-in trial
library. Each trouble is checked on the nine points of the readiness card: the signal in the twin, the rule, the price, who is
called (and the chain), the closure, the scenario and the limits."""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests import mod_support as ms  # noqa: E402
from tests.test_forecast import scenario_plant  # noqa: E402
from tests.test_mod_priority import modules  # noqa: E402
from modules import dispatch, inside, readiness, tiers  # noqa: E402
from modules import params as mparams  # noqa: E402
from modules import priority  # noqa: E402
from modules.policy import Trouble  # noqa: E402
from modules.store import Store  # noqa: E402
from sim import events  # noqa: E402
from sim import sensors as se  # noqa: E402
from sim import site_aktogay as site  # noqa: E402
from sim import trial  # noqa: E402
from sim.params import TABLE, default  # noqa: E402
from sim.plant import CopySet  # noqa: E402


def feats(plant, name):
    return se.measured_features(plant.state, plant.prm)[name]


class Rig:
    """A scenario plant with the three modules reading its measured snapshot as Ditto would give it."""

    def __init__(self, text="", **kw):
        self.pl = scenario_plant(text, **kw)
        self.st = Store(ms.NS, ms.default()["hist_min"])
        self.st.update_from_search(ms.items_from_plant(self.pl))
        self.lm, self.om, self.pm = modules(self.st, ms.default())
        self.pm.roles = ms.ROLES

    def run(self, minutes, compute_every=10):
        n = int(minutes // 5)
        out = None
        for i in range(n):
            self.pl.step(5.0)
            if (i + 1) % max(1, compute_every // 5) == 0 or i == n - 1:
                out = self.compute()
        return out

    def compute(self):
        self.st.update_from_search(ms.items_from_plant(self.pl))
        t = self.pl.t_min
        self.lm.compute(t)
        self.om.compute(t)
        return self.pm.compute(t, seed=1)

    def open(self, issues=None):
        issues = issues if issues is not None else self.compute()[1]
        return {v["kind"]: v for v in issues.values() if v["status"] != "RESOLVED"}


class WinterRoadTest(unittest.TestCase):
    """T1: ice and snowstorm on the haul roads; the decision is to restrict the traffic (S0)."""

    def test_icy_spell_changes_the_pit_road_state_and_not_the_water_flag(self):
        pl = scenario_plant("icy")
        for _ in range(12):
            pl.step(5.0)
        pit, water = feats(pl, "pit"), feats(pl, "water")
        p = pl.prm
        self.assertEqual(pit["visibility_m"], p["pit_vis_icy_m"])
        self.assertEqual(pit["road_grip"], p["pit_grip_icy"])
        self.assertLess(pit["haul_speed_pct"], 90.0)
        self.assertGreaterEqual(water["wind_ms"], p["scen_icy_wind_ms"])
        self.assertEqual(water["winter"], 0.0)               # the season of the water balance is another thing
        self.assertEqual(pit["road_restrict"], 0.0)
        # the spell ends by itself
        for _ in range(int(p["scen_icy_h"] * 12) + 6):
            pl.step(5.0)
        pit = feats(pl, "pit")
        self.assertEqual(pit["visibility_m"], p["pit_vis_clear_m"])
        self.assertAlmostEqual(pit["haul_speed_pct"], 100.0, places=3)

    def test_winter_season_changes_the_road_state_not_the_throughput(self):
        pl = scenario_plant("winter")
        for _ in range(6):
            pl.step(5.0)
        pit = feats(pl, "pit")
        self.assertEqual(pit["road_grip"], pl.prm["pit_grip_winter"])
        self.assertAlmostEqual(pit["haul_speed_pct"], 100.0, places=3)
        self.assertGreater(pit["road_grip"], pl.prm["pit_grip_min"])    # no hazard from the season alone

    def test_trouble_is_s0_first_with_the_pit_chain_the_price_and_the_closure(self):
        rig = Rig("icy")
        _f, issues = rig.run(40)
        road = rig.open(issues).get("road_winter")
        self.assertIsNotNone(road)
        self.assertEqual(road["safety_class"], "S0")
        self.assertEqual(road["rank"], 1.0)
        self.assertIn("ограничить движение", road["text"])
        self.assertIn("цена решения", road["text"])                       # the price of the safety decision is shown
        self.assertIn("[допущение]", road["text"])                        # thresholds are assumptions
        names = [it["name"] for it in road["chain"]["items"]]
        self.assertEqual(names, ["Горный диспетчер", "Начальник смены карьера", "Дорожная служба карьера"])
        self.assertTrue(road["checklist"].startswith("Что делать:"))
        self.assertIn(readiness.NOT_FOUND, road["checklist"])
        self.assertTrue(road["closure"].startswith("Закроется:"))
        self.assertGreaterEqual(len(road["evidence"]["items"]), 4)
        # the dispatcher restricts the traffic: the S0 trouble is closed, the road is slower, the line goes to the journal
        before = feats(rig.pl, "pit")["haul_speed_pct"]
        rig.pl.call("pit")
        feats_, issues = rig.run(10)
        self.assertNotIn("road_winter", rig.open(issues))
        self.assertEqual(feats(rig.pl, "pit")["road_restrict"], 1.0)
        self.assertLess(feats(rig.pl, "pit")["haul_speed_pct"], before)
        log = [e for e in feats_["escalations"]["log"] if e["action"] == "resolved"]
        self.assertTrue(any("Карьер" in e["text"] and "устранена" in e["text"] for e in log))

    def test_cancel_returns_the_road(self):
        cs = CopySet(None, 42, "icy")
        for _ in range(12):
            cs.step()
        cs.cancel()
        fact = cs.copies["fact"]
        for _ in range(3):
            cs.step()
        self.assertAlmostEqual(feats(fact, "pit")["haul_speed_pct"], 100.0, places=3)

    def test_chain_table_of_the_modules_equals_the_site(self):
        self.assertEqual(dispatch.CHAIN_BY_KIND, {k: v for k, v in site.CHAIN_BY_KIND.items()})
        ids = {p[0] for p in site.PEOPLE}
        for chain in site.CHAIN_BY_KIND.values():
            for pid in chain:
                self.assertIn(pid, ids)


class DriverFatigueTest(unittest.TestCase):
    """T1 (assumption): tired driver / close approach; only a scenario, labelled as such."""

    def test_alert_names_the_truck_and_is_labelled_as_an_assumption(self):
        rig = Rig("fatigue")
        _f, issues = rig.run(20)
        v = rig.open(issues).get("driver_fatigue")
        self.assertIsNotNone(v)
        self.assertEqual(v["safety_class"], "S0")
        self.assertIn("HT141", v["text"])
        self.assertIn("[допущение]", v["text"])
        self.assertIn("не подтверждён", v["text"])
        self.assertEqual([it["name"] for it in v["chain"]["items"]], ["Горный диспетчер", "Начальник смены карьера"])
        fleet = feats(rig.pl, "fleet")
        self.assertEqual(fleet["fatigue"], 1.0)
        self.assertEqual(fleet["fatigue_truck"], "HT141 (CAT 793D)")
        self.assertEqual(site.fatigue_truck(rig.pl.prm)[0], "truck-21")

    def test_the_call_clears_the_alert_and_closes_the_trouble(self):
        rig = Rig("fatigue")
        rig.run(10)
        rig.pl.call("fleet")
        _f, issues = rig.run(45)
        self.assertNotIn("driver_fatigue", rig.open(issues))
        self.assertEqual(feats(rig.pl, "fleet")["fatigue"], 0.0)

    def test_alert_ends_by_itself(self):
        pl = scenario_plant("fatigue")
        for _ in range(int(pl.prm["scen_fatigue_h"] * 12) + 4):
            pl.step(5.0)
        self.assertEqual(feats(pl, "fleet")["fatigue"], 0.0)


class CycloneRopingTest(unittest.TestCase):
    """T2 / M6: cyclone roping and ball mill overload (Kennecott T-F2; Centinela C13)."""

    def test_roping_shows_in_circulating_load_ball_draw_and_p80_of_its_line_only(self):
        pl = scenario_plant("roping:1")
        base = scenario_plant("")
        for _ in range(14):
            pl.step(5.0)
            base.step(5.0)
        c1, c2, b = feats(pl, "cyclones-1"), feats(pl, "cyclones-2"), feats(base, "cyclones-1")
        p = pl.prm
        self.assertGreater(c1["circ_load_pct"], 1.3 * b["circ_load_pct"])
        self.assertGreaterEqual(c1["circ_load_pct"], p["cyc_circ_base_pct"] * (1 + 0.8 * p["cyc_rope_circ_frac"]))
        self.assertGreater(c1["p80_um"], b["p80_um"] + 20.0)
        self.assertGreater(feats(pl, "ball-1a")["power_pct"], 108.0)
        self.assertAlmostEqual(feats(pl, "ball-2a")["power_pct"], 100.0, delta=1.5)
        self.assertAlmostEqual(c2["circ_load_pct"], p["cyc_circ_base_pct"], delta=0.05 * p["cyc_circ_base_pct"])
        # the unit is called through the grinding operator, not a crew: the cause is a decision cause
        self.assertEqual(priority.WHO["roping"][0], "")
        self.assertEqual(priority.WHO["roping"][1][0], "grinding_operator")

    def test_trouble_owns_the_losses_and_escalates_after_the_wait(self):
        rig = Rig("roping:1")
        _f, issues = rig.run(60, 15)
        v = rig.open(issues)
        self.assertIn("roping", v)
        self.assertNotIn("grind_coarse", v)
        self.assertFalse([k for k in v if k in ("loss_cyclones", "loss_flot")])
        self.assertIn("[допущение]", v["roping"]["text"])
        rec1 = rig.pl.state.lines[0].flot.recovery
        _f, issues = rig.run(90, 15)
        v2 = rig.open(issues)["roping"]
        self.assertIn("тяжёлое канатирование", v2["text"])
        self.assertIn("Centinela", v2["text"])
        self.assertLess(rig.pl.state.lines[0].flot.recovery, rec1 - 1.0)                 # the flotation lost more
        self.assertGreater(v2["loss_usd_h"], v["roping"]["loss_usd_h"])
        self.assertIn("Оператор пульта измельчения", v2["responsible"])
        self.assertTrue(v2["checklist"].startswith("Что делать:"))

    def test_the_call_ends_it_before_the_flotation_feels_it(self):
        rig = Rig("roping:1")
        rig.run(20)
        rig.pl.call("cyclones-1")
        _f, issues = rig.run(100)
        self.assertNotIn("roping", rig.open(issues))
        self.assertLess(feats(rig.pl, "cyclones-1")["circ_load_pct"], 300.0)
        self.assertGreater(rig.pl.state.lines[0].flot.recovery, 86.0)

    def test_after_the_call_no_leftover_loss_issue_from_the_lagging_flotation(self):
        rig = Rig("roping:1")
        _f, issues = rig.run(50, 10)
        self.assertIn("roping", rig.open(issues))
        rig.pl.call("cyclones-1")
        seen = set()
        for _ in range(8):
            _f, issues = rig.run(20, 20)
            seen |= set(rig.open(issues))
        self.assertFalse(seen & {"loss_cyclones", "loss_flot", "grind_coarse"}, seen)
        self.assertNotIn("roping", rig.open(issues))

    def test_scenario_token_takes_a_line(self):
        with self.assertRaises(ValueError):
            events.parse_scenario("roping", 0.0, default())
        with self.assertRaises(ValueError):
            events.parse_scenario("roping:3", 0.0, default())
        self.assertIn("roping", events.EXTRA)             # scenario only: never drawn in free run


class SensorSuspectTest(unittest.TestCase):
    """T3: a sensor under suspicion (pH electrode; T-T1) and the age of every measurement in the trouble card."""

    def test_online_reading_stays_on_the_setpoint_the_grab_sample_shows_the_drift(self):
        pl = scenario_plant("phdrift:1")
        for _ in range(14):
            pl.step(5.0)
        ph1, ph2 = feats(pl, "ph-1"), feats(pl, "ph-2")
        p = pl.prm
        self.assertAlmostEqual(ph1["ph"], p["flot_ph_sp"], delta=0.25)
        self.assertGreater(ph1["lab_ph"] - ph1["ph"], 0.4)
        self.assertEqual(ph1["state"], "SUSPECT")                               # the grab sample differs from the reading
        self.assertEqual(ph2["state"], "OK")
        self.assertEqual(ph1["state"], "SUSPECT")                               # the grab sample differs from the reading
        self.assertEqual(ph2["state"], "OK")
        self.assertAlmostEqual(ph2["lab_ph"], p["flot_ph_sp"], delta=0.3)
        truth = se.truth_features(pl.state)["ph-1"]
        self.assertGreater(truth["ph"], p["flot_ph_sp"] + 0.4)                  # the real pH is above the setpoint

    def test_trouble_with_price_and_evidence_marks_the_sensor(self):
        rig = Rig("phdrift:1")
        _f, issues = rig.run(80, 20)
        v = rig.open(issues)
        self.assertIn("sensor_ph", v)
        self.assertNotIn("loss_flot", v)                                         # the pH explains the flotation loss
        s = v["sensor_ph"]
        self.assertIn("pH-метр", s["responsible"] + s["text"] + "pH-метр")
        self.assertIn("Дежурный КИПиА", s["responsible"])
        self.assertGreater(s["loss_usd_h"], 0.0)
        items = {i["feature"]: i for i in s["evidence"]["items"]}
        for f in ("ph", "lab_ph"):
            self.assertTrue(items[f]["suspect"], f)                              # the card marks the pH meter
        self.assertIsNotNone(items["lab_ph"]["age_meas_min"])                    # grab sample: age of the sample itself
        self.assertIsNotNone(items["ph"]["age_pub_min"])
        self.assertGreaterEqual(s["evidence"]["n_suspect"], 2)
        self.assertEqual([it["name"] for it in s["chain"]["items"]][0], "Дежурный КИПиА")
        self.assertIn(priority.KIND_READY["sensor_ph"], [r["id"] for r in readiness.READY])

    def test_the_sheet_names_the_ph_meter_and_not_the_flowmeter(self):
        rig = Rig("phdrift:1")
        rig.run(80, 20)
        self.assertIn("phmeter-1", rig.lm.suspect)
        self.assertNotIn("flowmeter-1", rig.lm.suspect)
        self.assertIn("pH-метр 1", rig.lm.suspect["phmeter-1"])

    def test_clean_electrode_closes_it_after_a_fresh_sample(self):
        rig = Rig("phdrift:1")
        rig.run(80, 20)
        rig.pl.call("ph-1")
        _f, issues = rig.run(240, 20)
        self.assertNotIn("sensor_ph", rig.open(issues))
        ph1 = feats(rig.pl, "ph-1")
        self.assertAlmostEqual(ph1["lab_ph"], rig.pl.prm["flot_ph_sp"], delta=0.3)

    def test_after_the_fix_the_lagging_recovery_is_not_raised_as_a_new_loss(self):
        rig = Rig("phdrift:1")
        rig.run(80, 20)
        rig.pl.call("ph-1")
        seen = set()
        for _ in range(16):
            _f, issues = rig.run(20, 20)
            seen |= set(rig.open(issues))
        self.assertNotIn("loss_flot", seen)                  # settle_min covers the delay and the lag of the flotation
        self.assertNotIn("sensor_ph", rig.open(issues))

    def test_blocked_sample_line_makes_the_analyser_data_old_and_is_a_deviation(self):
        rig = Rig("sample:1")
        feats_, _issues = rig.run(60, 10)
        an1, an2 = feats(rig.pl, "analyzer-1"), feats(rig.pl, "analyzer-2")
        self.assertEqual(an1["state"], "SUSPECT")
        self.assertGreater(an1["age_min"], 2 * rig.pl.prm["sens_an_cycle_min"])
        self.assertEqual(an2["state"], "OK")
        self.assertLess(an2["age_min"], 20.0)
        kinds = {d["kind"] for d in feats_["deviations"]["items"]}
        self.assertIn("analyzer_stale", kinds)
        self.assertIn("Анализатор 1", feats_["deviations_text"])
        self.assertIn("КИПиА", feats_["deviations_text"])
        self.assertIn("analyzer-1", rig.lm.suspect)                            # the sheet «Приборы под подозрением»
        tr = Trouble(id="flot-1:loss", node="flot-1", kind="loss_flot")
        ev = tiers.evidence(rig.pm, tr, rig.pl.t_min, rig.lm.suspect)
        rec = next(i for i in ev["items"] if i["feature"] == "recovery")
        self.assertTrue(rec["suspect"])                                          # grades and recovery are the analyser's readings
        self.assertGreater(rec["age_meas_min"], 2 * rig.pl.prm["sens_an_cycle_min"])
        # the alarm calls the I&C technician, the line is cleaned, the readings come back and the deviation goes
        feats_, _issues = rig.run(150, 15)
        self.assertEqual(feats(rig.pl, "analyzer-1")["state"], "OK")
        self.assertNotIn("analyzer_stale", {d["kind"] for d in feats_["deviations"]["items"]})

    def test_age_of_data_old_publication_is_flagged(self):
        rig = Rig("")
        rig.compute()
        t = rig.pl.t_min
        snap = rig.st.get("analyzer-1")
        snap.sim_time = t - 25.0                                                 # published 25 model minutes ago
        tr = Trouble(id="flot-1:loss", node="flot-1", kind="loss_flot")
        ev = tiers.evidence(rig.pm, tr, t, {"analyzer-1": "анализатор"})
        self.assertTrue(ev["items"])
        tr2 = Trouble(id="ph-1:suspect", node="ph-1", kind="sensor_ph")
        snap_ph = rig.st.get("ph-1")
        snap_ph.sim_time = t - 25.0
        ev2 = tiers.evidence(rig.pm, tr2, t)
        row = next(i for i in ev2["items"] if i["feature"] == "ph")
        self.assertEqual(row["age_pub_min"], 25.0)
        self.assertTrue(row["old"])
        self.assertIn("мин назад", ev2["text"])

    def test_every_issue_card_carries_the_measurements_with_their_age(self):
        rig = Rig("conveyor:1")
        _f, issues = rig.run(20)
        belt = rig.open(issues)["conveyor_stop"]
        self.assertTrue(belt["evidence"]["items"])
        self.assertTrue(all(i["age_pub_min"] is not None for i in belt["evidence"]["items"]))
        self.assertTrue(belt["evidence_text"])


class HpgrUnevenTest(unittest.TestCase):
    """T4 / M4: uneven feed and tramp metal at the line 2 HPGR (the HPGR is wired in the model on line 2 only)."""

    def test_token_is_line_2_only_and_line_1_has_no_hpgr_signals(self):
        with self.assertRaises(ValueError):
            events.parse_scenario("hpgr:1", 0.0, default())
        pl = scenario_plant("hpgr:2")
        for _ in range(8):
            pl.step(5.0)
        p1, p2 = feats(pl, "pebble-1"), feats(pl, "pebble-2")
        self.assertEqual((p1["hpgr_skew_pct"], p1["hpgr_kw_diff_pct"], p1["metal_alarm"]), (-1.0, -1.0, -1.0))
        self.assertAlmostEqual(p2["hpgr_skew_pct"], pl.prm["peb_hpgr_skew_pct"], places=3)
        self.assertAlmostEqual(p2["hpgr_kw_diff_pct"], pl.prm["peb_hpgr_kwdiff_pct"], places=3)
        self.assertLess(p2["limit_tph"], pl.prm["peb_limit_tph"])

    def test_uneven_feed_costs_sag_tph_and_the_trouble_is_priced(self):
        base = scenario_plant("")
        rig = Rig("hpgr:2")
        for _ in range(12):
            base.step(5.0)
        _f, issues = rig.run(60, 15)
        self.assertLess(feats(rig.pl, "sag-2")["feed_tph"], 0.97 * feats(base, "sag-2")["feed_tph"])
        v = rig.open(issues).get("hpgr_uneven")
        self.assertIsNotNone(v)
        self.assertGreater(v["loss_usd_h"], 0.0)
        self.assertIn("Механик фабрики", v["responsible"])
        self.assertIn("Metso", v["text"])
        self.assertIn("[аналог]", v["text"])
        self.assertNotIn("pebble_stop", rig.open(issues))

    def test_tramp_metal_stops_the_hpgr_if_nobody_acts_and_a_repair_clears_it(self):
        rig = Rig("hpgr:2")
        _f, issues = rig.run(int(rig.pl.prm["peb_hpgr_tramp_after_h"] * 60) + 15, 15)
        p2 = feats(rig.pl, "pebble-2")
        self.assertEqual(p2["metal_alarm"], 1.0)
        self.assertEqual(p2["state"], "STOP")
        v = rig.open(issues)["hpgr_uneven"]
        self.assertIn("металлодетектор", v["text"])
        rig.pl.call("pebble-2")
        _f, issues = rig.run(5 * 60, 30)
        self.assertNotIn("hpgr_uneven", rig.open(issues))
        p2 = feats(rig.pl, "pebble-2")
        self.assertEqual((p2["hpgr_skew_pct"], p2["metal_alarm"]), (0.0, 0.0))
        self.assertEqual(p2["state"] in ("RUN", "LIMIT"), True)


class OreRegimeTest(unittest.TestCase):
    """T5: ore changed, the regime is old: hard and oxidised ore name the metallurgist and the Bozshakol example (not as a loss)."""

    def test_who_names_the_metallurgist_for_hard_and_oxidised_ore(self):
        for kind in ("hard_ore", "loss_flot_oxide"):
            roles = priority.WHO[kind][1]
            self.assertEqual(roles[0], "shift_geologist")
            self.assertIn("shift_metallurgist", roles)

    def test_hard_ore_card_says_to_tell_the_metallurgist(self):
        rig = Rig("hard:1")
        _f, issues = rig.run(25, 10)
        hard = rig.open(issues).get("hard_ore")
        self.assertIsNotNone(hard)
        self.assertIn("металлург", hard["responsible"].lower())
        self.assertIn("78,5", hard["notify_text"])
        self.assertIn("73,8", hard["notify_text"])
        self.assertIn("не потеря от задержки", hard["notify_text"])
        self.assertTrue(hard["checklist"].startswith("Что делать:"))
        self.assertEqual(priority.KIND_READY["hard_ore"], "ore_regime")
        self.assertEqual(priority.KIND_READY["loss_flot_oxide"], "ore_regime")

    def test_card_mentions_the_example_as_an_example(self):
        card = readiness.by_id("ore_regime")
        self.assertIn("НЕ потеря от задержки", card["source"])
        self.assertIn("78,5", card["source"])


class CrusherMantleTest(unittest.TestCase):
    """M6 / C11: mantle change of the primary crusher (about 60 h, analog La Caridad)."""

    def test_planned_stop_is_a_mantle_trouble_not_a_plain_stop(self):
        rig = Rig("mantle:1")
        _f, issues = rig.run(30)
        cr = feats(rig.pl, "crusher-1")
        self.assertEqual((cr["state"], cr["service"]), ("STOP", 1.0))
        self.assertGreater(cr["service_left_h"], 0.9 * rig.pl.prm["crush_mantle_h"])
        v = rig.open(issues)
        self.assertIn("crusher_mantle", v)
        self.assertNotIn("crusher_stop", v)
        text = v["crusher_mantle"]["text"]
        self.assertIn("La Caridad", text)
        self.assertIn("75", text)
        self.assertIn("100", text)
        self.assertIn("[аналог]", text)
        self.assertIn("наряд", text)
        self.assertIn("Механик ЦПД", v["crusher_mantle"]["responsible"])
        # the stockpile buys time: no loss at once, then the line loses its copper
        self.assertGreater(v["crusher_mantle"]["loss_usd_h"], 0.0)

    def test_a_plain_crusher_fault_stays_a_plain_stop(self):
        rig = Rig("crusher:1")
        _f, issues = rig.run(20)
        v = rig.open(issues)
        self.assertIn("crusher_stop", v)
        self.assertNotIn("crusher_mantle", v)
        self.assertEqual(feats(rig.pl, "crusher-1")["service"], 0.0)

    def test_the_stockpile_empties_and_the_line_stops_after_it(self):
        pl = scenario_plant("mantle:1")
        for _ in range(48 * 12 // 4):
            pl.step(5.0)
        self.assertEqual(pl.state.line(1).stockpile.state, "EMPTY")
        self.assertEqual(feats(pl, "line-2")["state"] in ("RUN", "LIMITED"), True)       # the other line runs on


class OilContaminationTest(unittest.TestCase):
    """M5 / C9 / S1: oil contamination sensor of the EX3600 (machine; sent only with Global e-Service), then pump failure."""

    def test_sensor_only_on_the_machine_a_source_confirms(self):
        pl = scenario_plant("oil")
        for _ in range(12 * 4):
            pl.step(5.0)
        e1, e2 = feats(pl, "exc-1"), feats(pl, "exc-2")
        self.assertGreaterEqual(e1["oil_pct"], 100.0)
        self.assertEqual(e1["oil_alert"], 1.0)
        self.assertEqual((e2["oil_pct"], e2["oil_alert"]), (-1.0, -1.0))              # no source: no sensor published
        self.assertEqual(site.OIL_SENSOR, ("exc-1",))

    def test_trouble_before_the_failure_with_the_pit_mechanic_and_the_option_label(self):
        rig = Rig("oil")
        _f, issues = rig.run(4 * 60, 30)
        v = rig.open(issues)
        self.assertIn("oil_contam", v)
        o = v["oil_contam"]
        self.assertEqual(o["person"], "person-pit-mech")
        self.assertIn("Global e-Service", o["text"])
        self.assertIn("70 %", o["text"])
        self.assertEqual([it["name"] for it in o["chain"]["items"]],
                         ["Сменный механик карьера", "Горный диспетчер", "Начальник смены карьера"])
        where = {i["feature"]: i["where"] for i in o["evidence"]["items"]}
        self.assertIn("на машине", where["oil_pct"])
        self.assertIn("передаётся, если подключена опция", where["oil_pct"])
        self.assertGreater(o["loss_usd_h"], 0.0)

    def test_service_in_time_prevents_the_failure(self):
        rig = Rig("oil")
        rig.run(4 * 60, 30)
        rig.pl.call("exc-1")
        rig.run(14 * 60, 60)
        e1 = rig.pl.state.excavators[0]
        self.assertNotEqual(e1.state, "DOWN")
        self.assertLess(feats(rig.pl, "exc-1")["oil_pct"], 100.0)

    def test_without_service_the_pump_fails_and_the_excavator_trouble_replaces_it(self):
        rig = Rig("oil")
        p = rig.pl.prm
        _f, issues = rig.run(int((p["pit_oil_rise_h"] + p["pit_oil_fail_h"]) * 60) + 40, 30)
        self.assertEqual(rig.pl.state.excavators[0].state, "DOWN")
        v = rig.open(issues)
        self.assertIn("exc_down", v)
        self.assertNotIn("oil_contam", v)
        self.assertIn("PC3000", v["exc_down"]["text"])
        self.assertEqual([it["name"] for it in v["exc_down"]["chain"]["items"]][0], "Сменный механик карьера")
        self.assertGreater(v["exc_down"]["loss_usd_h"], 0.0)
        self.assertEqual(feats(rig.pl, "fleet")["exc_ready"], 4.0)


class InsideTest(unittest.TestCase):
    """The page «Изнутри»: the table equals the file, the signals exist in the twin, every trouble is a WHO kind."""

    def test_written_file_equals_the_code(self):
        path = os.path.join(ROOT, "web", "static", "inside.json")
        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), inside.json_text())
        self.assertEqual(inside.problems(), [])

    def test_signals_name_real_things_and_features(self):
        with open(os.path.join(ROOT, "setup", "things.json"), encoding="utf-8") as f:
            d = json.load(f)
        names = {t["name"]: t["type"] for t in d["things"]}
        for g in inside.GROUPS:
            for nd in g["nodes"]:
                for s in nd["signals"]:
                    if not s["thing"]:
                        continue
                    things = s["thing"] if isinstance(s["thing"], list) else [s["thing"]]
                    ids = []
                    for t in things:
                        ids += [t.replace("{n}", str(n)) for n in (1, 2)] if "{n}" in t else [t]
                    for tid in ids:
                        if "{n}" in s["thing"] if isinstance(s["thing"], str) else False:
                            if tid not in names:
                                continue                                   # a pattern: only the existing lines count
                        self.assertIn(tid, names, f"{nd['id']}: {tid}")
                        self.assertIn(s["feature"], d["types"][names[tid]]["features"], f"{nd['id']}: {tid}.{s['feature']}")

    def test_troubles_are_who_kinds_and_labels_are_known(self):
        for g in inside.GROUPS:
            for nd in g["nodes"]:
                for k in nd["troubles"] + [f["trouble"] for f in nd["failures"] if f["trouble"]]:
                    self.assertIn(k, priority.WHO, f"{nd['id']}: {k}")
                for s in nd["signals"]:
                    self.assertIn(s["where"], inside.WHERE_RU)
                    self.assertIn(s["label"], inside.LABELS)

    def test_machine_labels_and_depth_follow_the_sensor_check(self):
        nodes = {nd["id"]: nd for g in inside.GROUPS for nd in g["nodes"]}
        ex = {s["feature"] or s["name"]: s for s in nodes["m-ex3600"]["signals"]}
        self.assertEqual(ex["oil_pct"]["where"], "machine")
        self.assertEqual(ex["oil_alert"]["where"], "sent")
        self.assertIn("Global e-Service", ex["oil_alert"]["source"])
        self.assertTrue(any(s["where"] == "sent" for s in nodes["m-ex3600"]["signals"]))
        self.assertEqual(nodes["m-ex3600"]["depth"], "A")
        # the 793F sheet is another model than the 793D of the fleet: marked analog, VIMS is sent
        wheres = {s["where"] for s in nodes["m-cat793"]["signals"]}
        self.assertIn("analog", wheres)
        self.assertIn("sent", wheres)
        self.assertEqual(nodes["m-cat793"]["depth"], "A")
        self.assertIn("не переносить", nodes["m-ex1200"]["limits"])
        self.assertEqual(nodes["m-drills"]["depth"], "C")
        self.assertTrue(any(s["where"] == "analog" for s in nodes["m-drills"]["signals"]))
        self.assertIn("19,2", json.dumps(nodes["m-d10t"]["failures"], ensure_ascii=False))     # C7 Pareto, analog
        self.assertTrue(all(f["label"] == "аналог" for f in nodes["m-d10t"]["failures"]))
        self.assertIn("301", json.dumps(nodes["m-d375"]["failures"], ensure_ascii=False))      # C10
        self.assertIn("60 ч", json.dumps(nodes["p-crusher"]["failures"], ensure_ascii=False))  # C11
        self.assertIn("12 000", json.dumps(nodes["p-hpgr"]["failures"], ensure_ascii=False))   # C19
        self.assertIn("1 600", json.dumps(nodes["p-pumps"]["failures"], ensure_ascii=False))   # C18
        self.assertIn("2 255", json.dumps(nodes["p-filter"]["failures"], ensure_ascii=False))  # C21

    def test_six_groups_in_the_order_of_the_task(self):
        self.assertEqual([g["id"] for g in inside.GROUPS], ["ore", "dam", "people", "machines", "plant", "env"])
        dam = next(g for g in inside.GROUPS if g["id"] == "dam")
        self.assertIn("23 м", dam["intro"])
        self.assertIn("downstream", dam["intro"])
        self.assertIn("CTD", dam["intro"])

    def test_the_truck_of_the_node_is_the_bort_ht141(self):
        borts = site.truck_borts()
        self.assertEqual(borts["truck-21"][0], "HT141")


class ReadinessCardsTest(unittest.TestCase):
    """Every new trouble has all nine points and a 'connect' line (path to a real plant)."""

    NEW = ("winter_road", "driver_fatigue", "cyclone_roping", "sensor_suspect", "hpgr_uneven", "ore_regime", "crusher_mantle",
           "oil_contam", "exc_down")

    def test_new_cards_are_complete(self):
        ids = {r["id"] for r in readiness.READY}
        for cid in self.NEW:
            self.assertIn(cid, ids)
            card = readiness.by_id(cid)
            for f in readiness.FIELDS:
                self.assertTrue(str(card[f]).strip(), f"{cid}.{f}")
        self.assertIn("Global e-Service", readiness.by_id("oil_contam")["connect"])
        self.assertIn("опция", readiness.by_id("oil_contam")["connect"])

    def test_every_who_kind_of_the_tier_has_a_card_or_a_reason(self):
        for kind in ("road_winter", "driver_fatigue", "roping", "sensor_ph", "hpgr_uneven", "crusher_mantle", "oil_contam",
                     "exc_down", "hard_ore", "loss_flot_oxide"):
            self.assertIn(kind, priority.KIND_READY)
            readiness.by_id(priority.KIND_READY[kind])

    def test_parameters_of_tier_s_have_label_and_source(self):
        for key in ("pit_vis_icy_m", "pit_grip_icy", "pit_icy_cycle_mult", "pit_oil_fail_h", "pit_oil_repair_h", "cyc_rope_p80_um",
                    "cyc_rope_flot_h", "flot_ph_sp", "hc_ph_drift", "peb_hpgr_uneven_eff", "peb_hpgr_tramp_after_h",
                    "crush_mantle_h"):
            row = TABLE[key]
            self.assertTrue(row.source.strip(), key)
            self.assertIn(row.label, ("fact", "vendor", "project", "analog", "assumption", "calc"), key)
        self.assertEqual(TABLE["crush_mantle_h"].label, "analog")          # La Caridad, not Aktogay
        self.assertEqual(TABLE["pit_oil_repair_h"].label, "analog")        # PC3000, not EX3600
        self.assertEqual(TABLE["cyc_rope_flot_h"].label, "analog")         # Centinela
        self.assertEqual(TABLE["pit_winter_cycle_mult"].value, 1.0)        # the season alone does not slow the haul
        have = {p.key for p in mparams.PARAMS}
        for key in ("pit_vis_min_m", "pit_grip_min", "rope_circ_alarm_pct", "ph_gap_alarm", "hpgr_skew_alarm_pct", "oil_fail_h",
                    "rep_mantle_h", "age_stale_dcs_min"):
            self.assertIn(key, have)


class TrialLibraryTest(unittest.TestCase):
    """The trial library gets the money kinds of the tier as an opt-in extension; the default draws do not change."""

    def test_default_library_and_draws_are_unchanged(self):
        self.assertEqual([c[0] for c in trial.LIBRARY], ["crusher", "hidden", "hard", "grid", "reline"])
        cfg = dict(trial.DEFAULTS, n=1, jobs=1, boot=200)
        self.assertEqual(trial.draw_shift(1001, cfg).text, "trip:2+hard:1+dose:1")
        kinds = {t.kind for seed in range(1001, 1101) for t in trial.draw_shift(seed, cfg).troubles}
        self.assertFalse(kinds & {"roping", "phdrift", "hpgr", "mantle"})

    def test_tier_s_library_draws_the_new_kinds_and_hpgr_only_on_line_2(self):
        cfg = dict(trial.DEFAULTS, n=1, jobs=1, boot=200, library="tier_s")
        seen = set()
        for seed in range(1001, 1121):
            for t in trial.draw_shift(seed, cfg).troubles:
                seen.add(t.kind)
                if t.kind == "hpgr":
                    self.assertEqual(t.line, 2)
                self.assertEqual(t.hidden, t.kind in trial.HIDDEN + trial.HIDDEN_TIER_S)
        self.assertTrue({"roping", "phdrift", "hpgr", "mantle"} <= seen)

    def test_descriptors_price_the_new_kinds(self):
        pl = scenario_plant("")
        for _ in range(3):
            pl.step(5.0)
        cfg = dict(trial.DEFAULTS, n=1, jobs=1, boot=200, library="tier_s")
        trs = []
        for kind, line in (("roping", 1), ("phdrift", 1), ("hpgr", 2), ("mantle", 1)):
            issue, node, crew = events.issue_for(kind, line)
            trs.append(trial.Trouble(issue, kind, line, node, crew, pl.t_min, kind in trial.HIDDEN_TIER_S))
        out = trial.descriptors(pl, trs, pl.t_min, pl.prm, 1001, cfg["est_sigma"], lambda tr: tr.t_start_min)
        self.assertEqual(len(out), 4)
        for d in out:
            self.assertGreater(d["loss_cu_tph"], 0.0, d["kind"])
        self.assertGreater(out[3]["hours_to_loss"], 0.0)                     # the mantle change: the stockpile buys time


if __name__ == "__main__":
    unittest.main()
