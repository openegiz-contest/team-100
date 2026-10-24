"""What-if levers of the model (feed rate of a SAG line, grind P80 target, collector dose): control of the MODEL, not of the
plant. Off by default (a neutral lever leaves the model unchanged), bounded, obeyed by the simulator, reset with the cancel,
commanded through control.lever, advised by the modules (the click is the dispatcher's) and shown by lever.js."""
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from modules import forecast as fc  # noqa: E402
from modules import lever_advice  # noqa: E402
from modules import params as mparams  # noqa: E402
from modules.policy import Trouble  # noqa: E402
from sim import sensors as se  # noqa: E402
from sim.params import TABLE, default  # noqa: E402
from sim.plant import CopySet, Plant  # noqa: E402
from tests.test_service import event, make_runner  # noqa: E402
from web import server  # noqa: E402

STATIC = os.path.join(ROOT, "web", "static")


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def run_plant(levers=None, minutes=240, seed=7):
    pl = Plant(default(), seed, mode="free")
    pl.warmup()
    if levers is not None:
        pl.set_levers(levers)
    for _ in range(minutes // 5):
        pl.step(5.0)
    return pl


def totals(pl):
    ls = pl.state.lines
    tph = sum(ln.tph for ln in ls)
    return {"tph": tph, "cu": sum(ln.cu_tph for ln in ls), "rec": sum(ln.recovery * ln.tph for ln in ls) / tph,
            "kwht": sum(ln.sag.power_kw + sum(b.power_kw for b in ln.balls) for ln in ls) / tph,
            "usd": sum(ln.cum_usd for ln in ls), "conc": sum(ln.cu_tph for ln in ls) * 100.0 / sum(ln.flot.conc_tph for ln in ls)}


class NeutralTest(unittest.TestCase):
    """A neutral lever is no lever: the model is byte-identical (determinism, calibration and the N = 100 trial stay)."""

    def test_neutral_values_are_not_stored_and_change_nothing(self):
        a = run_plant(None, 120)
        b = run_plant({"feed_1": 100, "feed_2": 100, "p80_um": 0, "dose_gt": 0}, 120)
        self.assertEqual(b.state.levers, {})
        fa, fb = se.measured_features(a.state, a.prm), se.measured_features(b.state, b.prm)
        self.assertEqual(fa, fb)
        self.assertEqual(fa["site"]["lever_on"], 0.0)
        self.assertEqual((fa["site"]["lever_feed_1"], fa["site"]["lever_p80_um"], fa["site"]["lever_dose_gt"]), (100.0, -1.0, -1.0))

    def test_default_has_no_levers(self):
        self.assertEqual(Plant(default(), 1, mode="free").state.levers, {})


class ClampTest(unittest.TestCase):
    def setUp(self):
        self.pl = Plant(default(), 3, mode="free")

    def test_bounds_are_the_table_rows(self):
        p = self.pl.prm
        self.assertEqual(self.pl.set_levers({"feed_1": 500, "feed_2": -5}), {"feed_1": p["lev_feed_max_pct"], "feed_2": p["lev_feed_min_pct"]})
        self.assertEqual(self.pl.set_levers({"p80_um": 10}), dict(self.pl.state.levers))
        self.assertEqual(self.pl.state.levers["p80_um"], p["lev_p80_min_um"])
        self.pl.set_levers({"p80_um": 999, "dose_gt": 999})
        self.assertEqual((self.pl.state.levers["p80_um"], self.pl.state.levers["dose_gt"]), (p["lev_p80_max_um"], p["lev_dose_max_gt"]))
        self.pl.set_levers({"dose_gt": 1})
        self.assertEqual(self.pl.state.levers["dose_gt"], p["lev_dose_min_gt"])
        self.assertEqual((p["lev_feed_min_pct"], p["lev_feed_max_pct"]), (80.0, 120.0))
        self.assertEqual((p["lev_p80_min_um"], p["lev_p80_max_um"]), (160.0, 200.0))

    def test_zero_is_off_and_none_clears(self):
        self.pl.set_levers({"feed_1": 110, "p80_um": 170, "dose_gt": 30})
        self.assertEqual(len(self.pl.state.levers), 3)
        self.pl.set_levers({"p80_um": 0})
        self.assertNotIn("p80_um", self.pl.state.levers)
        self.pl.set_levers({"feed_1": 100})
        self.assertNotIn("feed_1", self.pl.state.levers)
        self.assertEqual(self.pl.set_levers(None), {})
        self.assertEqual(self.pl.state.levers, {})

    def test_bad_input_is_refused(self):
        for bad in ({"nonsense": 1}, {"feed_1": float("nan")}, {"dose_gt": "x"}):
            with self.assertRaises((ValueError, TypeError)):
                self.pl.set_levers(bad)
        self.assertEqual(self.pl.state.levers, {})


class FeedLeverTest(unittest.TestCase):
    """Feed rate of a line: -20 % cuts the rate; +20 % raises it only up to the power of the mill, the liner and the pebble circuit."""

    @classmethod
    def setUpClass(cls):
        cls.base = run_plant(None)
        cls.low = run_plant({"feed_1": 80})
        cls.high = run_plant({"feed_1": 120})

    def test_lower_feed_lowers_the_rate_and_the_mill_power(self):
        b, lo = self.base.state.line(1), self.low.state.line(1)
        self.assertLess(lo.tph, b.tph)
        self.assertLess(lo.sag.power_kw, b.sag.power_kw)
        self.assertLess(lo.tph, 0.8 * self.base.prm["cal_line_tph"] + 1.0)         # the lever is a share of the nominal line rate
        self.assertAlmostEqual(self.low.state.line(2).tph, self.base.state.line(2).tph, delta=0.01 * self.base.state.line(2).tph)   # the other line is untouched

    def test_higher_feed_stops_at_the_power_limit(self):
        b, hi, p = self.base.state.line(1), self.high.state.line(1), self.high.prm
        self.assertGreaterEqual(hi.tph, b.tph - 1e-6)
        self.assertLessEqual(hi.sag.power_kw, p["sag_rated_mw"] * 1000.0 * 1.0001)
        self.assertLessEqual(hi.tph, 1.2 * p["cal_line_tph"] + 1e-6)
        self.assertGreater(hi.sag.power_kw, b.sag.power_kw)                         # the mill is pushed

    def test_worn_liner_binds_the_rate(self):
        fresh = Plant(default(), 7, mode="free")
        fresh.warmup()
        worn = Plant(default(), 7, mode="free")
        worn.warmup()
        for pl, x in ((fresh, fresh.prm["liner_x_peak"]), (worn, 1.0)):      # capacity peak against the end of the campaign
            pl.state.line(1).sag.liner_x = x
            pl.set_levers({"feed_1": 120})
            for _ in range(24):
                pl.step(5.0)
        self.assertLess(worn.state.line(1).tph, fresh.state.line(1).tph)

    def test_power_cap_of_the_grid_binds_the_rate(self):
        capped = Plant(default(), 7, mode="free")
        capped.warmup()
        capped.set_levers({"feed_1": 120})
        capped._grid_cap_kw[1] = 0.8 * capped.prm["sag_power_sp_mw"] * 1000.0
        for _ in range(24):
            capped.step(5.0)
        self.assertLess(capped.state.line(1).sag.power_kw, 0.8 * capped.prm["sag_power_sp_mw"] * 1000.0 * 1.05)
        self.assertLess(capped.state.line(1).tph, self.high.state.line(1).tph)


class GrindLeverTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fine = totals(run_plant({"p80_um": 160}))
        cls.coarse = totals(run_plant({"p80_um": 200}))
        cls.base = totals(run_plant(None))

    def test_finer_grind_recovers_more_costs_energy_and_rate(self):
        self.assertGreater(self.fine["rec"], self.coarse["rec"])
        self.assertLess(self.fine["tph"], self.coarse["tph"])
        self.assertGreater(self.fine["kwht"], self.coarse["kwht"])

    def test_recovery_swing_is_inside_the_published_range(self):
        # 40 um of target = 4 x 10 um: laboratory slope 1.2 pp, plant regression 1.95 pp per 10 um (Bozshakol), plus the
        # part of the base model that is taken off; the swing stays between half the lab value and the plant value
        swing = self.fine["rec"] - self.coarse["rec"]
        self.assertGreater(swing, 4 * 1.2 * 0.5)
        self.assertLess(swing, 4 * 1.95 * 1.1)

    def test_target_is_held(self):
        pl = run_plant({"p80_um": 160})
        for ln in pl.state.lines:
            self.assertAlmostEqual(ln.cyclones.p80_um, 160.0, delta=3.0)


class DoseLeverTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = totals(run_plant(None))
        cls.low = totals(run_plant({"dose_gt": 15}))
        cls.opt = totals(run_plant({"dose_gt": 25}))
        cls.high = totals(run_plant({"dose_gt": 40}))

    def test_below_the_optimum_recovery_is_lost(self):
        loss = self.base["rec"] - self.low["rec"]
        self.assertGreater(loss, 2.0)
        self.assertLess(loss, 5.0)                                 # flot_dose_pp 2-4 pp at -40 %
        self.assertLess(self.low["cu"], self.base["cu"])

    def test_at_the_setpoint_nothing_changes_in_the_metal(self):
        self.assertAlmostEqual(self.opt["rec"], self.base["rec"], places=6)

    def test_above_the_optimum_there_is_no_gain_but_cost_and_dilution(self):
        self.assertAlmostEqual(self.high["rec"], self.base["rec"], places=6)
        self.assertLess(self.high["usd"], self.base["usd"])        # the extra reagent is money
        self.assertLess(self.base["usd"] - self.high["usd"], 0.01 * self.base["usd"])    # collector is cheap against copper
        self.assertLess(self.high["conc"], self.base["conc"])      # dilution of the concentrate (qualitative)

    def test_dose_is_what_the_tank_and_the_flowmeter_say(self):
        pl = run_plant({"dose_gt": 35}, 60)
        r = pl.state.line(1).rougher
        self.assertAlmostEqual(r.dose_true_gt, 35.0, places=6)
        self.assertAlmostEqual(r.dose_meas_gt, 35.0, places=6)


class ServiceTest(unittest.TestCase):
    def test_lever_command_cancel_and_repeat(self):
        r, sink, clock = make_runner()
        r.tick()
        self.assertIsNone(r.copies)
        r.handle_event(*event("control", "/features/lever", {"feed_1": 110, "dose_gt": 30}, seq=1))
        self.assertIsNotNone(r.copies)
        self.assertTrue(r.copies.lever_only)
        fact, base = r.copies.copies["fact"], r.copies.copies["base"]
        self.assertEqual(fact.state.levers, {"feed_1": 110.0, "dose_gt": 30.0})
        self.assertEqual(base.state.levers, {})
        snap = sink.last_snapshot
        self.assertEqual(snap["site"]["lever_on"], 1.0)
        self.assertEqual(snap["site"]["lever_feed_1"], 110.0)
        self.assertIn("baseline", snap)                           # base / fact / difference for the interface
        # the same seq again is ignored, a new one changes the lever
        r.handle_event(*event("control", "/features/lever", {"feed_1": 90}, seq=1))
        self.assertEqual(fact.state.levers["feed_1"], 110.0)
        r.handle_event(*event("control", "/features/lever", {"feed_1": 90}, seq=2))
        self.assertEqual(fact.state.levers["feed_1"], 90.0)
        # both copies step together
        t0 = r.t_min
        clock.sleep(10.0)
        r.tick()
        self.assertGreater(base.t_min, t0)
        self.assertEqual(base.t_min, fact.t_min)
        # cancel: the stand is a plain free run again, levers off, no base copy
        r.handle_event(*event("control", "/features/cancel", {}, seq=1))
        self.assertIsNone(r.copies)
        self.assertEqual(r.plant.state.levers, {})
        self.assertEqual(sink.last_snapshot["site"]["lever_on"], 0.0)

    def test_reset_command_and_neutral_values_leave_the_comparison(self):
        r, sink, clock = make_runner()
        r.tick()
        r.handle_event(*event("control", "/features/lever", {"p80_um": 170}, seq=1))
        self.assertIsNotNone(r.copies)
        r.handle_event(*event("control", "/features/lever", {"reset": 1}, seq=2))
        self.assertIsNone(r.copies)
        self.assertEqual(r.plant.state.levers, {})
        r.handle_event(*event("control", "/features/lever", {"feed_2": 100}, seq=3))      # neutral: nothing to compare
        self.assertEqual(r.plant.state.levers, {})
        r.handle_event(*event("control", "/features/lever", {"feed_2": "abc"}, seq=4))    # bad value is dropped
        self.assertEqual(r.plant.state.levers, {})

    def test_scenario_cancel_removes_levers_and_new_run_starts_clean(self):
        r, sink, clock = make_runner()
        r.tick()
        r.handle_event(*event("control", "/features/scenario", {"id": "crusher:1"}, seq=1))
        r.handle_event(*event("control", "/features/lever", {"feed_1": 105}, seq=1))
        self.assertEqual(r.copies.copies["fact"].state.levers, {"feed_1": 105.0})
        self.assertFalse(r.copies.lever_only)
        r.handle_event(*event("control", "/features/cancel", {}, seq=1))
        self.assertEqual(r.plant.state.levers, {})
        r.handle_event(*event("control", "/features/lever", {"dose_gt": 20}, seq=2))
        r.handle_event(*event("control", "/features/reset", {"seed": 5}, seq=1))
        self.assertEqual(r.plant.state.levers, {})
        self.assertIsNone(r.copies)

    def test_calls_reach_both_copies_of_the_lever_comparison(self):
        pl = run_plant(None, 5)
        cs = CopySet.from_plant(pl)
        self.assertTrue(cs.lever_only)
        self.assertEqual(sorted(cs.copies), ["base", "fact"])
        self.assertEqual(cs.copies["base"].state.levers, {})
        self.assertIsNot(cs.copies["base"], cs.copies["fact"])


class ApiTest(unittest.TestCase):
    def test_payload_validation(self):
        self.assertEqual(server.lever_payload({"reset": 1}), {"reset": 1})
        self.assertEqual(server.lever_payload({"feed_1": "110", "p80_um": 0, "dose_gt": 30}), {"feed_1": 110.0, "p80_um": 0.0, "dose_gt": 30.0})
        for bad in ({}, {"feed_1": 130}, {"feed_2": 79}, {"p80_um": 150}, {"p80_um": 201}, {"dose_gt": 10}, {"dose_gt": 41},
                    {"feed_1": "x"}, {"feed_1": float("nan")}, {"dose_gt": float("inf")}, {"feed_1": 0}):
            with self.assertRaises(ValueError, msg=str(bad)):
                server.lever_payload(bad)

    def test_ranges_are_the_table_rows(self):
        rg = server.LEVER_RANGES
        self.assertEqual(rg["feed_1"][:2], (TABLE["lev_feed_min_pct"].value, TABLE["lev_feed_max_pct"].value))
        self.assertEqual(rg["p80_um"][:2], (TABLE["lev_p80_min_um"].value, TABLE["lev_p80_max_um"].value))
        self.assertEqual(rg["dose_gt"][:2], (TABLE["lev_dose_min_gt"].value, TABLE["lev_dose_max_gt"].value))
        js = read("web", "static", "lever.js")
        m = re.search(r"feed: \{ min: (\d+), max: (\d+).*p80: \{ min: (\d+), max: (\d+).*dose: \{ min: (\d+), max: (\d+)", js)
        self.assertEqual([float(x) for x in m.groups()], [rg["feed_1"][0], rg["feed_1"][1], rg["p80_um"][0], rg["p80_um"][1], rg["dose_gt"][0], rg["dose_gt"][1]])

    def test_things_json_declares_the_command_and_the_state(self):
        things = json.loads(read("setup", "things.json"))["types"]
        self.assertEqual(things["control"]["features"]["lever"], "obj")
        for f in ("lever_on", "lever_feed_1", "lever_feed_2", "lever_p80_um", "lever_dose_gt"):
            self.assertIn(f, things["site"]["features"])
        self.assertEqual(things["issue"]["features"]["lever"], "obj")
        self.assertIn("lever", read("models", "control-1.0.0.tm.jsonld"))

    def test_parameter_rows_are_labelled(self):
        for k, p in TABLE.items():
            if k.startswith("lev_"):
                self.assertIn(p.label, ("assumption", "analog"), k)
        self.assertEqual(TABLE["lev_p80_pp_10um"].value, 1.2)                      # lab slope, Bozshakol
        self.assertEqual(TABLE["lev_p80_pp_plant_10um"].value, 1.95)               # plant regression, Bozshakol
        self.assertEqual(TABLE["lev_reagent_usd_t"].label, "assumption")           # the Volza page did not open: not a source


class AdviceTest(unittest.TestCase):
    prm = mparams.default()

    def tr(self, kind, node):
        return Trouble(id=node + ":x", node=node, kind=kind)

    def test_advices_that_change_the_regime_carry_a_lever(self):
        g = lever_advice.suggest(self.tr("grind_coarse", "cyclones-2"), self.prm)
        self.assertEqual((g["name"], g["value"]), ("p80_um", self.prm["p80_ref_um"]))
        s = lever_advice.suggest(self.tr("loss_sag", "sag-1"), self.prm)
        self.assertEqual((s["name"], s["line"], s["value"]), ("feed", 1.0, self.prm["lev_adv_feed_pct"]))
        r = lever_advice.suggest(self.tr("roping", "cyclones-2"), self.prm)
        self.assertEqual((r["name"], r["line"]), ("feed", 2.0))
        for x in (g, s, r):
            self.assertIn("не фабрикой", x["reason"])
            self.assertTrue(x["label"])
        # every suggestion fits the range of the lever
        self.assertTrue(160 <= g["value"] <= 200)
        self.assertTrue(80 <= s["value"] <= 120 and 80 <= r["value"] <= 120)

    def test_other_advices_have_none(self):
        for kind, node in (("crusher_stop", "crusher-1"), ("pit_stop", "pit"), ("reline", "sag-1"), ("conc_low", "flot-1")):
            self.assertEqual(lever_advice.suggest(self.tr(kind, node), self.prm), lever_advice.EMPTY)

    def test_liner_forecast_advice_only_past_the_peak(self):
        p = self.prm
        self.assertEqual(lever_advice.liner_feed(1, 1.0, 1.0, p)["name"], "")
        past = lever_advice.liner_feed(2, 0.9, 1.0, p)
        self.assertEqual((past["name"], past["line"], past["value"]), ("feed", 2.0, p["lev_adv_feed_pct"]))

    def test_issue_and_forecast_features_carry_the_lever(self):
        from tests.test_tier_s import Rig
        rig = Rig("energy:1")
        _f, issues = rig.run(180)
        self.assertTrue(issues, "an overspend is found")
        for feats in issues.values():
            self.assertIn("lever", feats)
            self.assertEqual(set(feats["lever"]), set(lever_advice.EMPTY))
        sag = [v for v in issues.values() if v["kind"] == "loss_sag" and v["status"] != "RESOLVED"]
        if sag:
            self.assertEqual(sag[0]["lever"]["name"], "feed")
        lin = fc.liner(rig.st, rig.pm.prm, rig.pl.t_min)
        self.assertTrue(all("lever" in r for r in lin["lines"].values()))

    def test_module_never_writes_a_lever(self):
        src = read("modules", "lever_advice.py") + read("modules", "priority.py")
        self.assertNotIn("urllib", src)
        self.assertNotIn("write_control", src)
        self.assertNotIn("merge_features", src)


class UiTest(unittest.TestCase):
    def test_button_and_pages(self):
        js = read("web", "static", "lever.js")
        self.assertIn("Применить совет в модели", js)
        self.assertIn("управление моделью, не фабрикой", js)
        self.assertIn("/api/lever", js)
        self.assertIn("AKT.views.levers", js)
        self.assertIn('src="/lever.js"', read("web", "static", "index.html"))
        app = read("web", "static", "app.js")
        self.assertIn('id="tc-lever"', app)
        self.assertIn("AKT.lever.renderCard", app)
        self.assertIn("leverOn", app)
        self.assertIn("lever", read("web", "static", "forecast.js"))
        self.assertIn("view=levers", app)                          # the way in from «Пульт модели»

    def test_ui_reads_only_ditto_and_influx(self):
        js = read("web", "static", "lever.js")
        self.assertNotIn("fetch(", js)                              # only AKT.post to the stand's API; reads via AKT.num / AKT.val
        self.assertEqual(sorted(set(re.findall(r"'/api/[a-z]+'|`/api/[a-z]+`", js))), ["'/api/lever'"])

    def test_p80_range_is_shown_as_a_range(self):
        js = read("web", "static", "lever.js")
        self.assertIn("P80_SLOPE = { lab: 1.2, plant: 1.95 }", js)
        self.assertEqual(TABLE["lev_p80_pp_10um"].value, 1.2)
        self.assertEqual(TABLE["lev_p80_pp_plant_10um"].value, 1.95)


if __name__ == "__main__":
    unittest.main()
