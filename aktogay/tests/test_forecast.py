"""Step 0 (23.10.2026: parameters against the checked facts, HPGR of line 2 wired, the dead excavator / belt states
reachable) and the forecasts of akt-priority (stockpile chain, SAG liner campaign, copper to the end of the shift)."""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests import mod_support as ms  # noqa: E402
from tests.test_mod_priority import T0, modules, real_store  # noqa: E402
from modules import forecast as fc  # noqa: E402
from modules import dispatch, priority  # noqa: E402
from modules.store import Store  # noqa: E402
from sim import comminution as cm  # noqa: E402
from sim import events  # noqa: E402
from sim import sensors as se  # noqa: E402
from sim.params import TABLE, default  # noqa: E402
from sim.plant import Plant  # noqa: E402
from sim.state import NO_VALUE  # noqa: E402

THINGS = os.path.join(ROOT, "setup", "things.json")


def things():
    with open(THINGS, encoding="utf-8") as f:
        return json.load(f)


def passport(name):
    return next(t for t in things()["things"] if t["name"] == name)["passport"]


def scenario_plant(text="", **kw):
    pl = Plant(default(), seed=42, mode="scenario")
    pl.warmup()
    if text:
        pl.apply_scenario(events.parse_scenario(text, pl.t_min, pl.prm, **kw))
    return pl


def store_of(plant, things_only=None):
    prm = ms.default()
    st = Store(ms.NS, prm["hist_min"])
    st.update_from_search(ms.items_from_plant(plant, things=things_only))
    return st, prm


class FactsTest(unittest.TestCase):
    """Passports and parameters carry what the sources say (INVENTORY, FEATURES_22 step 0)."""

    def test_conveyor_sag_pebble_and_dam_passports(self):
        c2 = passport("conveyor-2")
        self.assertEqual((c2["length_km"][0], c2["length_km"][2]), (2.504, "pek18"))
        self.assertNotIn("3,8", json.dumps(c2, ensure_ascii=False))
        c1 = passport("conveyor-1")
        self.assertEqual((c1["length_km"][0], c1["length_km"][2]), (2.5, "pek10"))
        self.assertIn("12,2 × 7,6", passport("sag-1")["size"][0])
        self.assertEqual(passport("sag-1")["size"][2], "pek10")
        self.assertNotIn("40", passport("sag-2")["size"][0].split("(")[0])
        for n in ("pebble-1", "pebble-2"):
            self.assertNotIn("Raptor", json.dumps(passport(n), ensure_ascii=False))
            self.assertNotIn("XL1100", json.dumps(passport(n), ensure_ascii=False))
        w = passport("water")
        self.assertIn("downstream", w["dam_type"][0])
        self.assertEqual(w["dam_height_m"][0], 23)
        self.assertIn("243", w["volume_mm3"][0])
        self.assertIn("Low", w["hazard_class"][0])
        self.assertIn("2022", w["ctd"][0])
        srcs = things()["sources"]
        for k in ("pek10", "pek18", "pek40", "kaz_tailings2020"):
            self.assertIn(k, srcs)
            self.assertTrue(srcs[k]["url"].startswith("https://"))

    def test_parameters_against_the_facts(self):
        p = default()
        self.assertEqual(p["conv_length_km"], 2.504)
        self.assertEqual(TABLE["conv_length_km"].label, "project")
        self.assertAlmostEqual(p["pit_drill_t_hole"], 8 * 9 * 10 * 2.66, places=6)       # bench 10 m, PEK p. 40
        self.assertIn("p. 40", TABLE["pit_drill_t_hole"].source)
        self.assertEqual(p["wx_temp_winter_c"], -10)
        self.assertEqual(TABLE["wx_temp_winter_c"].label, "analog")
        self.assertEqual(TABLE["winter_return_frac"].label, "assumption")
        self.assertEqual(p["winter_return_frac"], 0.03)
        self.assertEqual(p["ball_media_gt"], 800)
        self.assertEqual((TABLE["ball_media_gt"].min, TABLE["ball_media_gt"].max), (600, 1000))
        self.assertEqual(TABLE["ball_media_gt"].label, "analog")
        self.assertEqual(TABLE["econ_payable_frac"].label, "calc")
        self.assertEqual((TABLE["econ_payable_frac"].min, TABLE["econ_payable_frac"].max), (0.95, 0.96))
        m = ms.default()
        self.assertEqual(m["ball_norm_gt"], p["ball_media_gt"])
        self.assertEqual(m["payable_frac"], p["econ_payable_frac"])
        self.assertEqual(m["tariff_zones_on"], 0)
        self.assertEqual(m["conv_travel_min"], round(p["conv_transit_min"], 1))

    def test_winter_changes_the_water_only(self):
        res = {}
        for w in (False, True):
            pl = Plant(default(), seed=42, mode="free")
            pl.base_winter = pl.winter_on = w
            pl.warmup()
            for _ in range(12 * 6):
                pl.step(5.0)
            st = pl.state
            res[w] = ([round(ln.tph, 6) for ln in st.lines], [round(ln.cu_tph, 6) for ln in st.lines],
                      [round(ln.recovery, 6) for ln in st.lines], st.water.recycle_m3h)
        self.assertEqual(res[False][:3], res[True][:3])           # throughput, copper, recovery are the same
        self.assertLess(res[True][3], res[False][3])               # only the water return is lower

    def test_winter_multipliers_are_labelled_assumptions(self):
        m = ms.default()
        for k in ("winter_water_mult", "winter_repair_mult"):
            self.assertGreaterEqual(m[k], 1.0)
        from modules.params import PARAMS
        MT = {x.key: x for x in PARAMS}
        self.assertEqual(MT["winter_water_mult"].label, "assumption")
        self.assertEqual(MT["winter_repair_mult"].label, "assumption")
        self.assertIn("not applied to throughput", MT["winter_water_mult"].note)
        self.assertEqual(MT["tariff_zones_on"].label, "fact")


class HpgrTest(unittest.TestCase):
    def test_line_2_hpgr_is_wired(self):
        pl = scenario_plant()
        for _ in range(12):
            pl.step(5.0)
        pb2, pb1 = pl.state.lines[1].pebble, pl.state.lines[0].pebble
        p = pl.prm
        self.assertEqual(pb2.limit_tph, min(p["peb_limit_tph"], p["peb_hpgr_l2_tph"]))
        self.assertEqual(pb2.hpgr_tph, p["peb_hpgr_l2_tph"])
        self.assertAlmostEqual(pb2.hpgr_load_pct, 100.0 * pb2.feed_tph / 1061.0, places=6)
        self.assertAlmostEqual(pb2.hpgr_kw, 3500.0 * pb2.feed_tph / 1061.0, places=6)
        self.assertEqual((pb1.hpgr_tph, pb1.hpgr_kw), (0.0, 0.0))
        f = se.measured_features(pl.state, p)
        self.assertEqual(f["pebble-1"]["hpgr_tph"], NO_VALUE)                 # line 1: no published rating
        self.assertEqual(f["pebble-2"]["hpgr_tph"], 1061.0)
        self.assertGreater(f["pebble-2"]["hpgr_kw"], 1000.0)
        self.assertLess(f["pebble-2"]["hpgr_kw"], 3500.0)

    def test_hpgr_stands_with_its_circuit(self):
        pl2 = scenario_plant()
        pl2.apply_scenario(events.parse_scenario("hpgr_fire", pl2.t_min, pl2.prm))
        line = int(pl2.prm["scen_fire_line"])
        for _ in range(6):
            pl2.step(5.0)
        pb = pl2.state.lines[line - 1].pebble
        self.assertEqual(pb.state, "STOP")
        if line == 2:
            self.assertEqual((pb.hpgr_kw, pb.hpgr_load_pct), (0.0, 0.0))


class ScenarioTest(unittest.TestCase):
    def test_pit_stop_makes_the_excavator_down_state_reachable(self):
        pl = scenario_plant("pitstop")
        st = pl.state
        self.assertEqual([e.state for e in st.excavators], ["DOWN"] * len(st.excavators))
        pl.step(5.0)
        self.assertEqual(st.pit.state, "STOP")
        self.assertEqual(st.pit.mining_tph, 0.0)
        end = st.excavators[0].down_until_min
        self.assertAlmostEqual(end - 480.0, pl.prm["scen_pitstop_h"] * 60.0, delta=10.0)
        while pl.t_min < end + 20.0:
            pl.step(5.0)
        self.assertTrue(all(e.state != "DOWN" for e in st.excavators))
        self.assertEqual(st.pit.state, "RUN")

    def test_the_stock_carries_the_plant_as_long_as_the_forecast_says(self):
        pl = scenario_plant()
        for _ in range(6):
            pl.step(5.0)
        store, prm = store_of(pl)
        t0 = pl.t_min
        f = fc.stock(store, prm, t0)
        pl.apply_scenario(events.parse_scenario("pitstop", pl.t_min, pl.prm))
        starved = {}
        for _ in range(int(14 * 12)):
            pl.step(5.0)
            for ln in pl.state.lines:
                if ln.n not in starved and ln.sag.state == "STARVED":
                    starved[ln.n] = (pl.t_min - t0) / 60.0
        for n in (1, 2):
            predicted = f["lines"][str(n)]["hours"]
            if predicted < 12.0:
                self.assertIn(n, starved, f"line {n}: SAG never starved, forecast {predicted:.1f} h")
                self.assertAlmostEqual(starved[n], predicted, delta=0.7)
        self.assertLess(f["lines"]["1"]["hours"], f["lines"]["2"]["hours"])      # snapshot: line 1 has less on stock

    def test_belt_trip_stands_the_belt_not_the_crusher(self):
        pl = scenario_plant("conveyor:1")
        for _ in range(3):
            pl.step(5.0)
        ln = pl.state.lines[0]
        self.assertEqual((ln.conveyor.state, ln.conveyor.fault), ("STOP", "scenario"))
        self.assertNotEqual(ln.crusher.state, "STOP")
        self.assertEqual(ln.crusher.tph, 0.0)
        self.assertEqual(pl.state.lines[1].conveyor.state, "RUN")
        f = se.measured_features(pl.state, pl.prm)
        self.assertEqual(f["conveyor-1"]["fault"], 1.0)
        self.assertEqual(f["conveyor-2"]["fault"], 0.0)
        # the module sees a belt trouble with the crusher crew; the stock gives it hours
        store, prm = store_of(pl)
        lm, om, pm = modules(store, prm)
        pm.roles = ms.ROLES
        kinds = {tr.kind: tr for tr in pm.troubles(pl.t_min)}
        self.assertIn("conveyor_stop", kinds)
        self.assertEqual(kinds["conveyor_stop"].crew, "crew-cpd")
        self.assertGreater(kinds["conveyor_stop"].t_conseq_h, 0.5)
        # the crew repairs it: the belt runs again and the fault is gone
        for _ in range(12 * 12):
            pl.step(5.0)
            if not ln.conveyor.fault:
                break
        self.assertEqual(ln.conveyor.fault, "")

    def test_a_belt_that_stands_for_lack_of_ore_is_no_belt_trouble(self):
        pl = scenario_plant("pitstop")
        for _ in range(12 * 5):
            pl.step(5.0)
        store, prm = store_of(pl)
        lm, om, pm = modules(store, prm)
        pm.roles = ms.ROLES
        kinds = [tr.kind for tr in pm.troubles(pl.t_min)]
        self.assertNotIn("conveyor_stop", kinds)
        self.assertIn("pit_stop", kinds)

    def test_pit_stop_trouble_names_the_dispatcher_and_the_hours(self):
        pl = scenario_plant("pitstop")
        for _ in range(6):
            pl.step(5.0)
        store, prm = store_of(pl)
        lm, om, pm = modules(store, prm)
        pm.roles = ms.ROLES
        trs = [tr for tr in pm.troubles(pl.t_min) if tr.kind == "pit_stop"]
        self.assertTrue(trs)
        tr = min(trs, key=lambda x: x.t_conseq_h)
        self.assertEqual((tr.node, tr.crew), ("pit", ""))
        self.assertIn("Горный диспетчер", tr.role)
        self.assertIn("163 кт", tr.text)
        self.assertIn("[проект]", tr.text)
        self.assertIn("[оценка на модели]", tr.text)
        self.assertGreater(tr.rate_cu_tph, 5.0)


class ForecastTest(unittest.TestCase):
    def setUp(self):
        self.prm = ms.default()

    def test_liner_form_equals_the_model(self):
        sp = default()
        for i in range(0, 101, 5):
            x = i / 100.0
            self.assertAlmostEqual(fc.eta(x, self.prm), cm.liner_eta(x, sp), places=9)

    def test_liner_campaign_numbers(self):
        st, prm = real_store(T0, {"sag-1": {"liner_ground_t": 3.0e6, "feed_tph": 3853.0},
                                  "sag-2": {"liner_ground_t": 21.0e6, "feed_tph": 3853.0}})
        f = fc.liner(st, prm, T0)
        a, b = f["lines"]["1"], f["lines"]["2"]
        self.assertAlmostEqual(a["share"], 0.10)
        self.assertAlmostEqual(a["eta_now"], 1.0, places=6)
        self.assertAlmostEqual(a["days_to_end"], 27.0e6 / (3853.0 * 24 * prm["fc_avail"]), places=6)
        self.assertGreater(a["days_to_peak"], 0.0)
        self.assertEqual(b["days_to_peak"], NO_VALUE)                 # already past the peak at 70 %
        self.assertAlmostEqual(b["eta_now"], 1.03, places=6)
        self.assertLess(b["days_to_end"], a["days_to_end"])
        self.assertAlmostEqual(a["drop_from_peak_pct"], 100 * (0.98 / 1.03 - 1), places=6)
        self.assertLess(a["drop_from_peak_pct"], 0.0)
        self.assertAlmostEqual(a["reline_h"], 84)
        self.assertGreater(a["reline_cu_t"], 0.0)
        self.assertEqual(len(f["curve"]), 21)
        txt = fc.liner_text(f, T0)
        self.assertIn("[оценка на модели]", txt)
        self.assertIn("[допущение]", txt)
        self.assertIn("IV кв. 2023", txt)
        self.assertIn("III кв. 2025", txt)

    def test_stock_hours_and_the_pek_reference(self):
        st, prm = real_store(T0, {"stockpile-1": {"level_t": 11600.0, "out_tph": 3853.0},
                                  "stockpile-2": {"level_t": 30000.0, "out_tph": 3853.0},
                                  "crusher-1": {"tph": 3853.0}, "crusher-2": {"tph": 3853.0}})
        f = fc.stock(st, prm, T0)
        r1, r2 = f["lines"]["1"], f["lines"]["2"]
        transit = 3853.0 * (prm["pit_haul_min"] + prm["conv_travel_min"]) / 60.0
        self.assertAlmostEqual(r1["hours"], (11600.0 + transit) / 3853.0, places=6)
        self.assertGreater(r2["hours"], r1["hours"])
        self.assertAlmostEqual(r1["pek_hours"], 48.0)
        self.assertEqual(prm["stock_total_t"], 163000)
        self.assertFalse(f["pit_stopped"])
        txt = fc.stock_text(f, T0)
        self.assertIn("Если карьер встанет сейчас", txt)
        self.assertIn("163 кт", txt)
        self.assertIn("[проект]", txt)

    def test_copper_corridor_and_shift_clock(self):
        hist = []
        for i in range(36):
            hist.append((T0 - 175 + 5 * i, {"site": {"cu_tph": 27.0 + (0.6 if i % 2 else -0.6)}}, None))
        prm = ms.default()
        st = Store(ms.NS, prm["hist_min"])
        for ti, ov, _b in hist:
            st.update_from_search(ms.snapshot(ti, ov))
        st.update_from_search(ms.snapshot(T0, {"site": {"cu_tph": 27.0}}))
        c = fc.copper(st, prm, T0, 1.5)
        self.assertLessEqual(c["rate_lo_tph"], c["rate_tph"])
        self.assertAlmostEqual(c["rate_hi_tph"], c["rate_tph"] + 1.5)
        self.assertGreater(c["sd_tph"], 0.3)
        # T0 is 08:00 + something: the shift clock counts from 08:00 / 20:00
        into = (T0 - 480.0) % 720.0
        self.assertAlmostEqual(c["h_shift"], (720.0 - into) / 60.0)
        self.assertAlmostEqual(c["plan_day_t"], 603.6)
        self.assertAlmostEqual(c["plan_shift_t"], 301.8)
        self.assertIn("[оценка на модели]", fc.copper_text(c, T0))

    def test_copper_forecast_without_history_has_no_spread(self):
        st, prm = real_store(T0, {"site": {"cu_tph": 27.4}})
        c = fc.copper(st, prm, T0, 0.0)
        self.assertEqual(c["sd_tph"], 0.0)
        self.assertEqual(c["rate_lo_tph"], c["rate_tph"])

    def test_the_module_publishes_the_forecast(self):
        st, prm = real_store(T0, {"sag-1": {"liner_ground_t": 3.0e6}})
        lm, om, pm = modules(st, prm)
        pm.roles = ms.ROLES
        lm.compute(T0)
        om.compute(T0)
        feats, _issues = pm.compute(T0, seed=1)
        f = feats["forecast"]
        self.assertEqual(set(f), {"t", "stock", "liner", "copper", "texts"})
        self.assertIn("1", f["stock"]["lines"])
        self.assertIn("1", f["liner"]["lines"])
        self.assertIn("Если карьер встанет сейчас", feats["forecast_text"])
        json.dumps(f)                                                # a plain object: goes to Ditto as it is


class TariffScenarioTest(unittest.TestCase):
    def test_flat_by_default(self):
        prm = ms.default()
        self.assertEqual(dispatch.tariff_info(19 * 60.0, prm)["band"], "flat")
        self.assertEqual(dispatch.tariff_info(19 * 60.0, prm.copy(tariff_zones_on=1))["band"], "peak")


if __name__ == "__main__":
    unittest.main()
