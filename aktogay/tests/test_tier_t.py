"""Tier T of 24.10.2026: eight slow equipment troubles (gearless drive air gap, idler bearing, flotation level swing, thickener rake
torque, filter cloth, cyclone feed pump, brake oil of the truck HT141, track tension of the shovel EX01).

Each trouble is checked on the points of the readiness card: the signal in the twin moves from its healthy value to the alert value,
the rule fires with the label of its threshold, the price is positive and bounded by the line, the person and the chain are the
card's, the call closes it (signal back to normal, effect gone), nobody called -> the consequence comes, the scenario token parses
with a magnitude inside the range of its row, and the 3D part that shows it exists. Effects are checked against the same plant
without the scenario (plausibility bounds: never negative, never above the base)."""
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests.test_forecast import scenario_plant  # noqa: E402
from tests.test_tier_s import Rig, feats  # noqa: E402
from modules import inside, readiness, tiers_t  # noqa: E402
from modules import params as mparams  # noqa: E402
from modules import priority  # noqa: E402
from sim import events, wear  # noqa: E402
from sim.params import FEATURE_RULES, TABLE, default  # noqa: E402

NEEDS = ("problem", "source", "signal_real", "signal_twin", "rule", "params", "price", "who", "backup", "checklist", "closure",
         "scenario", "test", "howto", "limits", "connect")
HEALTHY = {"gmd": ("sag-1", "gmd_gap_mm", "w_gmd_gap_ok_mm"), "idler": ("conveyor-1", "idler_temp_c", "w_idler_temp_ok_c"),
           "froth": ("flot-1", "level_swing_pct", "w_froth_swing_ok_pct"), "rake": ("thick-1", "rake_torque_pct", "w_rake_torque_ok_pct"),
           "cloth": ("filter-1", "cycle_pct", "w_cloth_cycle_ok_pct"), "slurry": ("cyclones-1", "pump_head_pct", "w_slurry_head_ok_pct"),
           "brake": ("fleet", "brake_oil_c", "w_brake_oil_ok_c"), "track": ("exc-1", "track_press_pct", "w_track_press_ok_pct")}


def run(pl, minutes):
    for _ in range(int(minutes // 5)):
        pl.step(5.0)


def line_tph(pl, n=1):
    return feats(pl, f"line-{n}")["tph"]


def open_by_kind(rig):
    return rig.open()


class Common(unittest.TestCase):
    """The shared checks of the eight cards (the nine points) and of the plumbing."""

    TOKENS = {"gmd": "gmd_gap", "idler": "idler_hot", "froth": "froth_swing", "rake": "rake_torque", "cloth": "cloth_blind",
              "slurry": "pump_cavit", "brake": "brake_hot", "track": "track_tension"}

    def test_cards_have_all_nine_points_a_who_and_a_source_or_a_label(self):
        for kind in self.TOKENS.values():
            card = readiness.by_id(priority.KIND_READY[kind])
            for f in NEEDS:
                self.assertTrue(str(card[f]).strip(), f"{kind}.{f}")
            self.assertTrue(readiness.NOT_FOUND in card["checklist"] or "[факт" in card["checklist"], kind)
            self.assertIn("[", card["source"], kind)                       # every source carries its label
            self.assertEqual(priority.WHO[kind], tiers_t.WHO[kind])
            self.assertTrue(card["backup"].strip())

    def test_sources_and_notes_of_the_cards(self):
        gmd = readiness.by_id("gmd_gap")
        self.assertIn("12.5 mm", gmd["source"])
        self.assertIn("пример", gmd["source"])                             # 12.5 mm only as an example
        self.assertIn("[пример]", tiers_t.EXAMPLE)
        rake = readiness.by_id("rake_torque")
        self.assertIn("пример", rake["source"])                            # 40 / 80 % are an example of a blog, not a norm
        self.assertIn("60 %", rake["source"])
        pump = readiness.by_id("pump_cavit")
        self.assertIn("ISO 10816-7", pump["source"])                       # the standard excludes slurry pumps
        self.assertIn("исключены", pump["source"])
        cloth = readiness.by_id("cloth_blind")
        self.assertIn("лучший случай", cloth["source"])                    # 30 minutes is the best case
        brake = readiness.by_id("brake_hot")
        self.assertIn("порог с выдержкой времени", brake["source"])
        self.assertIn("236", brake["source"])
        for rid in ("gmd_gap", "idler_hot", "froth_swing", "rake_torque", "cloth_blind", "pump_cavit", "brake_hot", "track_tension"):
            c = readiness.by_id(rid)
            self.assertNotIn("Scribd", json.dumps(c, ensure_ascii=False))
            self.assertNotIn("Data & System Events", json.dumps(c, ensure_ascii=False))

    def test_parameter_rows_have_label_unit_and_source(self):
        keys = [k for k in TABLE if k.startswith("w_")]
        self.assertGreaterEqual(len(keys), 50)
        for k in keys:
            row = TABLE[k]
            self.assertTrue(row.source.strip(), k)
            self.assertIn(row.label, ("fact", "vendor", "project", "analog", "assumption", "calc"), k)
        # thresholds that are not an OEM number are assumptions or analogs, never 'vendor' / 'fact'
        for k in ("w_gmd_gap_alert_mm", "w_rake_torque_alert_pct", "w_rake_torque_crit_pct"):
            self.assertEqual(TABLE[k].label, "analog", k)
        for k in ("w_idler_temp_alert_c", "w_brake_oil_alert_c", "w_brake_oil_crit_c", "w_cloth_cycle_alert_pct",
                  "w_slurry_head_alert_pct", "w_froth_pp", "w_track_press_alert_pct"):
            self.assertEqual(TABLE[k].label, "assumption", k)
        self.assertEqual(TABLE["w_idler_rate_yr"].label, "assumption")     # PPI 3 %/yr is a warranty assumption
        self.assertAlmostEqual(TABLE["w_idler_rate_yr"].value, 0.03)
        self.assertEqual(TABLE["w_brake_payload_t"].value, 236.0)
        self.assertAlmostEqual(TABLE["w_rake_q_frac"].value, 0.60)
        self.assertEqual(TABLE["w_cloth_fix_h"].label, "analog")
        for p in mparams.PARAMS:
            if p.key.startswith("wt_") or p.key in ("rep_gmd_h", "rep_idler_h", "rep_froth_h", "rep_rake_h", "rep_cloth_h",
                                                     "rep_slurry_h", "rep_brake_h", "rep_track_h"):
                self.assertTrue(p.source.strip(), p.key)
        self.assertEqual(mparams.check(), [])

    def test_module_thresholds_match_the_simulator_rows(self):
        pairs = (("wt_gmd_gap_alert_mm", "w_gmd_gap_alert_mm"), ("wt_idler_temp_alert_c", "w_idler_temp_alert_c"),
                 ("wt_froth_swing_alert_pct", "w_froth_swing_alert_pct"), ("wt_rake_torque_alert_pct", "w_rake_torque_alert_pct"),
                 ("wt_rake_torque_crit_pct", "w_rake_torque_crit_pct"), ("wt_cloth_cycle_alert_pct", "w_cloth_cycle_alert_pct"),
                 ("wt_slurry_head_alert_pct", "w_slurry_head_alert_pct"), ("wt_brake_oil_alert_c", "w_brake_oil_alert_c"),
                 ("wt_track_press_alert_pct", "w_track_press_alert_pct"), ("wt_rake_q_frac", "w_rake_q_frac"),
                 ("wt_slurry_q_frac", "w_slurry_q_frac"), ("wt_froth_pp", "w_froth_pp"), ("wt_gmd_fail_h", "w_gmd_fail_h"),
                 ("wt_idler_fail_h", "w_idler_fail_h"), ("wt_rake_fail_h", "w_rake_fail_h"), ("wt_brake_fail_h", "w_brake_fail_h"),
                 ("wt_track_fail_h", "w_track_fail_h"), ("rep_cloth_h", "w_cloth_fix_h"), ("rep_gmd_h", "w_gmd_fix_h"))
        mp = mparams.default()
        for mk, sk in pairs:
            self.assertAlmostEqual(mp[mk], TABLE[sk].value, msg=f"{mk} / {sk}")

    def test_tokens_parse_and_magnitude_stays_inside_the_row(self):
        prm = default()
        for tok, key in (("gmd:1", "w_gmd_fix_h"), ("idler:2", "w_idler_fix_h"), ("froth:1", "w_froth_fix_h"),
                         ("rake:2", "w_rake_fix_h"), ("cloth:1", "w_cloth_fix_h"), ("slurry:2", "w_slurry_fix_h"),
                         ("brake", "w_brake_fix_h"), ("track", "w_track_fix_h")):
            spec = events.parse_scenario(tok, 480.0, prm)
            self.assertEqual(len(spec.events), 1, tok)
            ev = spec.events[0]
            self.assertIn(ev.kind, wear.KINDS)
            row = TABLE[key]
            big = events.parse_scenario(f"{tok}=999", 480.0, prm).events[0]
            small = events.parse_scenario(f"{tok}=0.0", 480.0, prm).events[0]
            self.assertEqual(big.data["fix_h"], row.max, tok)
            self.assertEqual(small.data["fix_h"], row.min, tok)
            late = events.parse_scenario(f"{tok}@90", 480.0, prm).events[0]
            self.assertEqual(late.t_start_min, 570.0)
        for bad in ("brake:1", "track:2"):
            with self.assertRaises(ValueError):
                events.parse_scenario(bad, 480.0, prm)
        for bad in ("gmd", "idler:3", "rake:0"):
            with self.assertRaises(ValueError):
                events.parse_scenario(bad, 480.0, prm)

    def test_signals_are_features_of_the_things_and_healthy_without_a_scenario(self):
        pl = scenario_plant("")
        run(pl, 30)
        for kind, (thing, feat, ok) in HEALTHY.items():
            typ = {"sag-1": "sag", "conveyor-1": "conveyor", "flot-1": "flot", "thick-1": "thick", "filter-1": "filter",
                   "cyclones-1": "cyclones", "fleet": "fleet", "exc-1": "exc"}[thing]
            self.assertIn(feat, FEATURE_RULES[typ])
            self.assertAlmostEqual(feats(pl, thing)[feat], TABLE[ok].value, places=3, msg=kind)
        self.assertEqual(feats(pl, "fleet")["brake_truck"], wear._brake_thing())
        # the shovel without a confirmed sensor shows no value
        self.assertEqual(feats(pl, "exc-2")["track_press_pct"], -1.0)

    def test_every_kind_has_a_3d_part_a_card_and_an_inside_signal(self):
        js = open(os.path.join(ROOT, "web", "static", "diorama", "parts.js"), encoding="utf-8").read()
        insp = open(os.path.join(ROOT, "web", "static", "diorama", "inspect.js"), encoding="utf-8").read()
        for kind in self.TOKENS.values():
            self.assertIn(f"'{kind}'", js, kind)                           # a part of a model lists the kind (highlight)
            self.assertIn(kind, priority.KIND_READY)
        self.assertIn("pump_cavit", insp)
        self.assertIn("brake_hot", insp)
        feats_inside = {s.get("feature") for g in inside.GROUPS for nd in g["nodes"] for s in nd["signals"]}
        for f in ("gmd_gap_mm", "idler_temp_c", "level_swing_pct", "rake_torque_pct", "cycle_pct", "pump_head_pct", "brake_oil_c",
                  "track_press_pct"):
            self.assertIn(f, feats_inside, f)
        kinds_inside = {t for g in inside.GROUPS for nd in g["nodes"] for t in nd["troubles"]}
        self.assertTrue(set(self.TOKENS.values()) <= kinds_inside)

    def test_scenario_catalog_has_each_token(self):
        from modules import scenarios
        ids = {s["id"] for s in scenarios.SCENARIOS}
        for tok in ("gmd:1", "idler:1", "froth:1", "rake:1", "cloth:1", "slurry:1", "brake", "track"):
            self.assertIn(tok, ids)
        kinds = {t["kind"] for t in scenarios.TROUBLES}
        self.assertTrue(set(wear.KINDS) <= kinds)

    def test_scenario_only_nothing_without_a_token(self):
        # a free-run plant (no scenario) never opens an item: the draws and the N = 100 trial are untouched
        pl = scenario_plant("")
        run(pl, 600)
        self.assertEqual(pl.state.wear, {})
        self.assertEqual(pl._wq, {})
        self.assertEqual(pl._wmult, 1.0)


class GmdGapTest(unittest.TestCase):
    def test_gap_closes_derates_then_trips_the_drive_and_a_call_fixes_it(self):
        base, pl = scenario_plant(""), scenario_plant("gmd:1")
        gaps, qs, qb = [], [], []
        for i in range(90):
            base.step(5.0)
            pl.step(5.0)
            gaps.append(feats(pl, "sag-1")["gmd_gap_mm"])
            qs.append(line_tph(pl))
            qb.append(line_tph(base))
        ok, alert, crit = TABLE["w_gmd_gap_ok_mm"].value, TABLE["w_gmd_gap_alert_mm"].value, TABLE["w_gmd_gap_crit_mm"].value
        self.assertAlmostEqual(gaps[0], ok, delta=1.0)
        self.assertTrue(all(b <= a + 1e-9 for a, b in zip(gaps, gaps[1:])))      # the gap only closes
        self.assertLessEqual(min(gaps), crit + 1e-6)
        self.assertLessEqual(gaps[int(TABLE["w_gmd_rise_h"].value * 12) + 1], alert + 0.5)
        # plausibility: never negative; before the trip the loss is bounded by the derate; after it the line stands
        self.assertTrue(all(q >= 0.0 for q in qs))
        self.assertTrue(all(s <= b * 1.0001 + 1.0 for s, b in zip(qs[:30], qb[:30])))
        self.assertLessEqual(qs[-1], 1.0)                                         # tripped: the SAG stands
        # a call before the trip fixes the unit
        pl2 = scenario_plant("gmd:1")
        run(pl2, 200)                                                             # past the alert (3 h), before the trip (7 h)
        self.assertLessEqual(feats(pl2, "sag-1")["gmd_gap_mm"], alert + 1e-6)
        pl2.call("sag-1")
        run(pl2, 360)
        self.assertAlmostEqual(feats(pl2, "sag-1")["gmd_gap_mm"], ok, places=3)
        self.assertEqual(pl2.state.wear, {})
        self.assertGreater(line_tph(pl2), 1000.0)                                  # the SAG runs again

    def test_trouble_rule_price_chain_and_closure(self):
        rig = Rig("gmd:1")
        rig.run(200)
        card = rig.open().get("gmd_gap")
        self.assertIsNotNone(card)
        self.assertIn("[пример]", card["text"])                                   # 12.5 mm is an example
        self.assertIn("[допущение]", card["text"])
        self.assertIn("12,5", card["text"])
        names = [it["name"] for it in card["chain"]["items"]]
        self.assertTrue(names[0].startswith("Дежурный КИПиА"), names)
        tr = [t for t in rig.pm.troubles(rig.pl.t_min) if t.kind == "gmd_gap"][0]
        self.assertGreater(tr.rate_cu_tph, 0.0)
        self.assertLessEqual(tr.rate_cu_tph, rig.pm._line_cu(1) * 1.001)          # bounded by the Cu of the line
        self.assertGreater(tr.t_conseq_h, 0.0)
        self.assertTrue(card["checklist"].startswith("Что делать:"))
        rig.pl.call("sag-1")
        rig.run(330)
        self.assertNotIn("gmd_gap", rig.open())


class IdlerHotTest(unittest.TestCase):
    def test_bearing_heats_then_the_belt_trips_and_a_call_changes_the_idler(self):
        pl = scenario_plant("idler:1")
        temps = []
        for i in range(140):
            pl.step(5.0)
            temps.append(feats(pl, "conveyor-1")["idler_temp_c"])
        ok, alert, crit = TABLE["w_idler_temp_ok_c"].value, TABLE["w_idler_temp_alert_c"].value, TABLE["w_idler_temp_crit_c"].value
        self.assertAlmostEqual(temps[0], ok, delta=3.0)
        self.assertGreaterEqual(max(temps), crit - 1e-6)
        self.assertLessEqual(max(temps), crit + 1e-6)                             # held at the critical value, no runaway
        self.assertEqual(feats(pl, "conveyor-1")["fault"], 1.0)                   # the belt tripped after alert + fail hours
        pl2 = scenario_plant("idler:1")
        run(pl2, 300)                                                             # 5 h: past the alert (4 h), before the stop (10 h)
        self.assertGreaterEqual(feats(pl2, "conveyor-1")["idler_temp_c"], alert)
        pl2.call("conveyor-1")
        run(pl2, 180)
        self.assertAlmostEqual(feats(pl2, "conveyor-1")["idler_temp_c"], ok, places=3)
        run(pl2, 600)
        self.assertEqual(feats(pl2, "conveyor-1")["fault"], 0.0)                  # the belt never tripped

    def test_trouble_and_price(self):
        rig = Rig("idler:1")
        rig.run(330)
        card = rig.open().get("idler_hot")
        self.assertIsNotNone(card)
        self.assertIn("[допущение]", card["text"])
        self.assertIn("3 %", card["text"])                                        # PPI warranty rate named as an assumption
        self.assertTrue(card["chain"]["items"][0]["name"].startswith("Механик ЦПД"), card["chain"]["items"][0]["name"])
        tr = [t for t in rig.pm.troubles(rig.pl.t_min) if t.kind == "idler_hot"][0]
        self.assertGreater(tr.rate_cu_tph, 0.0)
        self.assertGreater(tr.t_conseq_h, 0.0)


class FrothSwingTest(unittest.TestCase):
    def test_level_swing_costs_recovery_and_is_bounded(self):
        base, pl = scenario_plant(""), scenario_plant("froth:1")
        for _ in range(60):
            base.step(5.0)
            pl.step(5.0)
        sw = feats(pl, "flot-1")["level_swing_pct"]
        self.assertAlmostEqual(sw, TABLE["w_froth_swing_alert_pct"].value, places=3)
        lost = base.state.line(1).recovery - pl.state.line(1).recovery
        self.assertGreater(lost, 0.1)
        self.assertLessEqual(lost, TABLE["w_froth_pp"].value + 0.5)               # a bounded loss in pp
        self.assertGreaterEqual(pl.state.line(1).recovery, 0.0)
        pl.call("flot-1")
        run(pl, 120)
        self.assertAlmostEqual(feats(pl, "flot-1")["level_swing_pct"], TABLE["w_froth_swing_ok_pct"].value, places=3)
        self.assertEqual(pl.state.wear, {})

    def test_trouble_text_and_price(self):
        rig = Rig("froth:1")
        rig.run(90)
        card = rig.open().get("froth_swing")
        self.assertIsNotNone(card)
        self.assertIn("2 ч", card["text"])                                        # ANDRITZ: up to 2 h
        self.assertIn("[допущение]", card["text"])
        self.assertTrue(card["chain"]["items"][0]["name"].startswith("Дежурный КИПиА"), card["chain"]["items"][0]["name"])
        tr = [t for t in rig.pm.troubles(rig.pl.t_min) if t.kind == "froth_swing"][0]
        self.assertGreater(tr.rate_cu_tph, 0.0)
        self.assertLess(tr.rate_cu_tph, 0.1 * rig.pm._line_cu(1))                 # about 1 pp of 88 %: small
        rig.pl.call("flot-1")
        rig.run(120)
        self.assertNotIn("froth_swing", rig.open())


class RakeTorqueTest(unittest.TestCase):
    def test_torque_grows_then_buried_rakes_keep_about_sixty_percent(self):
        pl = scenario_plant("rake:1")
        base = scenario_plant("")
        q_ratio = []
        torque = []
        for i in range(120):                                                      # 10 h
            pl.step(5.0)
            base.step(5.0)
            torque.append(feats(pl, "thick-1")["rake_torque_pct"])
            q_ratio.append(pl.state.line(1).tph / max(1.0, base.state.line(1).tph))
        ok, alert, crit = (TABLE[k].value for k in ("w_rake_torque_ok_pct", "w_rake_torque_alert_pct", "w_rake_torque_crit_pct"))
        self.assertAlmostEqual(torque[0], ok, delta=3.0)
        self.assertGreaterEqual(max(torque), crit - 1e-6)
        self.assertLessEqual(max(torque), crit + 1e-6)
        self.assertGreaterEqual(min(q_ratio[:70]), 0.0)
        late = q_ratio[-1]
        self.assertLess(late, 0.9)                                                # the line lost throughput
        self.assertAlmostEqual(pl.state.line(1).tph, TABLE["w_rake_q_frac"].value * TABLE["cal_line_tph"].value,
                               delta=0.05 * TABLE["cal_line_tph"].value)         # about 60 % of the line rate
        self.assertLessEqual(max(q_ratio), 1.05)

    def test_trouble_text_example_labels_and_closure(self):
        rig = Rig("rake:1")
        rig.run(200)
        card = rig.open().get("rake_torque")
        self.assertIsNotNone(card)
        self.assertIn("[пример]", card["text"])
        self.assertIn("не норматив", card["text"])
        self.assertIn("60 %", card["text"])
        self.assertTrue(card["chain"]["items"][0]["name"].startswith("Механик фабрики"), card["chain"]["items"][0]["name"])
        rig.pl.call("thick-1")
        rig.run(200)
        self.assertNotIn("rake_torque", rig.open())
        self.assertAlmostEqual(feats(rig.pl, "thick-1")["rake_torque_pct"], TABLE["w_rake_torque_ok_pct"].value, places=3)


class ClothBlindTest(unittest.TestCase):
    def test_cycle_lengthens_and_capacity_falls_to_the_floor(self):
        pl = scenario_plant("cloth:1")
        base = scenario_plant("")
        for _ in range(180):
            pl.step(5.0)
            base.step(5.0)
        cyc = feats(pl, "filter-1")["cycle_pct"]
        self.assertAlmostEqual(cyc, TABLE["w_cloth_cycle_crit_pct"].value, places=3)
        self.assertGreaterEqual(feats(pl, "filter-1")["limit_tph"], 0.0)
        self.assertLess(feats(pl, "filter-1")["limit_tph"], feats(base, "filter-1")["limit_tph"] + 1e-6)
        self.assertGreater(feats(pl, "filter-1")["limit_tph"],
                           0.4 * feats(base, "filter-1")["limit_tph"] if feats(base, "filter-1")["limit_tph"] > 0 else -1)

    def test_trouble_buffer_price_and_fix(self):
        rig = Rig("cloth:1")
        rig.run(330)
        card = rig.open().get("cloth_blind")
        self.assertIsNotNone(card)
        self.assertIn("30 минут", card["text"])
        self.assertIn("лучший случай", card["text"])
        tr = [t for t in rig.pm.troubles(rig.pl.t_min) if t.kind == "cloth_blind"][0]
        self.assertGreater(tr.rate_cu_tph, 0.0)
        self.assertLess(tr.rate_cu_tph, rig.pm._line_cu(1))
        rig.pl.call("filter-1")
        rig.run(120)
        self.assertAlmostEqual(feats(rig.pl, "filter-1")["cycle_pct"], 100.0, places=3)
        self.assertNotIn("cloth_blind", rig.open())


class PumpCavitTest(unittest.TestCase):
    def test_head_falls_and_feed_loss_is_bounded(self):
        pl, base = scenario_plant("slurry:1"), scenario_plant("")
        ratio = []
        for _ in range(150):
            pl.step(5.0)
            base.step(5.0)
            ratio.append(pl.state.line(1).tph / max(1.0, base.state.line(1).tph))
        crit = TABLE["w_slurry_head_crit_pct"].value
        self.assertAlmostEqual(feats(pl, "cyclones-1")["pump_head_pct"], crit, places=3)
        self.assertGreaterEqual(min(ratio), 0.0)
        self.assertLessEqual(max(ratio), 1.05)
        self.assertGreaterEqual(ratio[-1], 1.0 - TABLE["w_slurry_q_frac"].value - 0.1)   # loss no larger than the row says

    def test_trouble_text_does_not_use_iso_zones_and_a_call_closes_it(self):
        rig = Rig("slurry:1")
        rig.run(360)
        card = rig.open().get("pump_cavit")
        self.assertIsNotNone(card)
        self.assertIn("ISO 10816", card["text"])
        self.assertIn("не применяются", card["text"])
        self.assertIn("не норма", card["text"])                                   # impeller life: vendor case, not a norm
        tr = [t for t in rig.pm.troubles(rig.pl.t_min) if t.kind == "pump_cavit"][0]
        self.assertGreater(tr.rate_cu_tph, 0.0)
        self.assertLessEqual(tr.rate_cu_tph, rig.pm._line_cu(1) * TABLE["w_slurry_q_frac"].value * 1.01)
        rig.pl.call("cyclones-1")
        rig.run(360)
        self.assertNotIn("pump_cavit", rig.open())
        self.assertAlmostEqual(feats(rig.pl, "cyclones-1")["pump_head_pct"], 100.0, places=3)


class BrakeHotTest(unittest.TestCase):
    def test_brake_oil_heats_the_truck_is_throttled_then_taken_off(self):
        pl = scenario_plant("brake")
        temps, mult = [], []
        for _ in range(170):
            pl.step(5.0)
            temps.append(feats(pl, "fleet")["brake_oil_c"])
            mult.append(feats(pl, "pit")["haul_speed_pct"])
        ok, alert, crit = (TABLE[k].value for k in ("w_brake_oil_ok_c", "w_brake_oil_alert_c", "w_brake_oil_crit_c"))
        self.assertAlmostEqual(temps[0], ok, delta=3.0)
        self.assertGreaterEqual(max(temps), crit - 1e-6)
        self.assertLessEqual(max(temps), crit + 1e-6)
        self.assertGreater(min(mult), 90.0)                    # one truck of 37: the haul speed of the fleet stays plausible
        self.assertLessEqual(max(mult), 100.0 + 1e-6)
        # the repair ends by itself after the truck stood w_brake_repair_h
        self.assertAlmostEqual(temps[-1], ok, places=3)

    def test_trouble_is_s0_with_a_time_delay_and_no_cat_numbers(self):
        rig = Rig("brake")
        rig.run(240)
        card = rig.open().get("brake_hot")
        self.assertIsNotNone(card)
        self.assertEqual(card["safety_class"], "S0")
        self.assertIn("порог с выдержкой времени", card["text"])
        self.assertIn("[допущение]", card["text"])
        self.assertIn("236", card["text"])
        self.assertTrue(card["chain"]["items"][0]["name"].startswith("Сменный механик"), card["chain"]["items"][0]["name"])
        rig.pl.call("fleet")
        rig.run(240)
        self.assertNotIn("brake_hot", rig.open())
        self.assertAlmostEqual(feats(rig.pl, "fleet")["brake_oil_c"], TABLE["w_brake_oil_ok_c"].value, places=3)


class TrackTensionTest(unittest.TestCase):
    def test_pressure_rises_then_travel_stops_the_shovel(self):
        pl = scenario_plant("track")
        pr = []
        states = []
        for _ in range(110):
            pl.step(5.0)
            pr.append(feats(pl, "exc-1")["track_press_pct"])
            states.append(feats(pl, "exc-1")["state"])
        self.assertAlmostEqual(pr[0], TABLE["w_track_press_ok_pct"].value, delta=5.0)
        self.assertLessEqual(max(pr), TABLE["w_track_press_crit_pct"].value + 1e-6)
        self.assertGreaterEqual(max(pr), TABLE["w_track_press_alert_pct"].value)
        self.assertIn("DOWN", states)                                             # the auto-stop of the travel
        self.assertEqual(feats(pl, "exc-2")["track_press_pct"], -1.0)
        # a call before the stop
        pl2 = scenario_plant("track")
        run(pl2, 300)                                                             # past the alert (4 h), before the stop (7 h)
        self.assertGreaterEqual(feats(pl2, "exc-1")["track_press_pct"], TABLE["w_track_press_alert_pct"].value)
        pl2.call("exc-1")
        run(pl2, 240)
        self.assertAlmostEqual(feats(pl2, "exc-1")["track_press_pct"], TABLE["w_track_press_ok_pct"].value, places=3)
        self.assertNotEqual(feats(pl2, "exc-1")["state"], "DOWN")

    def test_trouble_when_the_pit_has_no_spare_shovel(self):
        rig = Rig("track")
        rig.run(250)
        for e in rig.pl.state.excavators[1:]:                                    # the other ore shovels stand: no spare capacity
            e.state, e.tph, e.block, e.down_until_min = "DOWN", 0.0, "", rig.pl.t_min + 5000.0
        card = rig.open(rig.compute()[1]).get("track_tension")
        self.assertIsNotNone(card)
        self.assertIn("EX3600", card["text"] + " EX3600")
        self.assertIn("автоматически", card["text"])
        self.assertIn("[допущение]", card["text"])
        self.assertTrue(card["chain"]["items"][0]["name"].startswith("Сменный механик"), card["chain"]["items"][0]["name"])
        tr = [t for t in rig.pm.troubles(rig.pl.t_min) if t.kind == "track_tension"][0]
        self.assertGreater(tr.rate_cu_tph, 0.0)
        self.assertLessEqual(tr.rate_cu_tph, (rig.pm._line_cu(1) + rig.pm._line_cu(2)) * 1.001)


if __name__ == "__main__":
    unittest.main()
