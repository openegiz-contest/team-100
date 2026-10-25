"""Oxide chain (ore to the heap -> heap leach pad -> PLS pond -> SX -> EW -> cathode store, 25.10.2026): the reports and the calendar, the back-test on the
cathode of the quarters, Faraday and the copper balance of the chain, the scenarios leachcold / ewtrip / sxcrud and their numbers in the catalog, the
three troubles of the module, the things and the web wiring. The sulphide plant does not move."""
import csv
import json
import math
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "web", "static")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests import mod_support as ms  # noqa: E402
from modules import ore, losses, priority, readiness, scenarios  # noqa: E402
from modules import oxide as mox  # noqa: E402
from sim import oxide  # noqa: E402
from sim import sensors as se  # noqa: E402
from sim.params import FEATURE_RULES, TABLE, default as TABLE_DEFAULT  # noqa: E402
from sim.plant import CopySet, Plant  # noqa: E402

DATE = (2025, 299)        # 27 October: quarter 4 of 2025


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


def snap(plant):
    return se.measured_features(plant.state, plant.prm)


def shift(scn, call=None, hours=12, date=DATE):
    """Fact copy of a scenario for the hours of the shift; call = (node, minute) books the person. Returns (plant, cathode t, hourly snapshots)."""
    cs = CopySet(None, 42, scn)
    f = cs.copies["fact"]
    f.ox_date = date
    rows = []
    for i in range(hours * 60):
        cs.step()
        if call and i == call[1]:
            f.call(call[0])
        if i % 60 == 59:
            rows.append(snap(f))
    return f, f.state.sxew.cathode_t_total, rows


class DataTest(unittest.TestCase):
    def test_34_quarters_are_the_reports(self):
        q = oxide.quarters()
        self.assertEqual(len(q), 34)
        yr = lambda y: sum(q[(y, i)][0] for i in (1, 2, 3, 4))          # noqa: E731
        self.assertEqual(yr(2023), 18694)                                 # Q4 2024 report p. 3
        self.assertEqual(yr(2024), 11349)
        self.assertEqual(yr(2025), 5512)                                  # Q4 2025 report p. 3
        c = oxide.cathode_by_quarter()
        self.assertEqual(len(c), 32)
        self.assertAlmostEqual(sum(c[(2025, i)] for i in (1, 2, 3, 4)), 15.3, places=6)
        for k, (_o, _g, cat) in q.items():
            if k in c:
                self.assertEqual(c[k], cat, k)
        with open(os.path.join(ROOT, "sim", "data", "kaz_oxide_quarterly.csv"), encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 34)
        self.assertTrue(all(r["source_url"].startswith("http") for r in rows))

    def test_level_is_kt_per_hours_of_the_quarter(self):
        self.assertAlmostEqual(oxide.level_tph(2025, 1), 3.4 * 1000 / (90 * 24), places=9)
        self.assertAlmostEqual(oxide.level_tph(2024, 4), 3.6 * 1000 / (92 * 24), places=9)
        self.assertEqual(oxide.quarter_hours(2024, 1), 91 * 24)

    def test_quarter_of_a_date_and_dates_after_2025(self):
        self.assertEqual(oxide.quarter_of(2025, 0), (2025, 1))
        self.assertEqual(oxide.quarter_of(2025, 299), (2025, 4))
        self.assertEqual(oxide.quarter_of(2026, 299), (2025, 4))
        self.assertEqual(oxide.quarter_of(2030, 100), (2025, 2))

    def test_air_temperature_follows_the_era5_months(self):
        import datetime
        self.assertLess(oxide.air_t_c(datetime.date(2025, 1, 15)), -10.0)
        self.assertGreater(oxide.air_t_c(datetime.date(2025, 7, 15)), 25.0)

    def test_reported_quarters_show_the_season(self):
        c = oxide.cathode_by_quarter()
        self.assertAlmostEqual(c[(2024, 4)] / c[(2024, 3)] - 1.0, -0.25, delta=0.001)


class BacktestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bt = oxide.backtest(TABLE_DEFAULT())

    def test_fit_and_forward_errors(self):
        b = self.bt
        self.assertEqual(b["fit"]["n"], 32)
        self.assertLess(b["fit"]["mape_pct"], 12.0)
        self.assertLess(abs(b["fit"]["bias_pct"]), 3.0)
        self.assertEqual(b["forward"]["n"], 2)                           # 2026 Q1, Q2: not in the fit
        self.assertLess(b["forward"]["mape_pct"], 15.0)
        self.assertGreater(b["r_all"], 0.85)
        for y, a in b["annual"].items():
            self.assertLess(abs(a["err_pct"]), 12.0, y)

    def test_model_beats_the_mean_and_sees_the_season(self):
        b = self.bt
        self.assertLess(b["forward"]["mape_pct"], b["baseline_constant_forward"]["mape_pct"] / 3.0)
        rows = {r["quarter"]: r for r in b["rows"]}
        for y in (2021, 2022, 2023):                                     # the model has the winter dip of the quarter 1 below the summer quarter 3
            self.assertLess(rows[f"{y}Q1"]["model_kt"], rows[f"{y}Q3"]["model_kt"], y)
        self.assertLess(rows["2024Q4"]["model_kt"], rows["2024Q3"]["model_kt"])

    def test_stored_file_equals_the_code(self):
        d = json.loads(read(STATIC, "backtest_ox.json"))
        self.assertEqual(d["rows"], self.bt["rows"])
        for k in ("fit", "forward", "annual", "baseline_constant_forward", "baseline_previous_quarter_forward"):
            self.assertEqual(d[k], self.bt[k], k)
        s = d["strict"]                                                  # fit to 2024 only, with the stored parameters
        prm = TABLE_DEFAULT()
        for k, v in s["values"].items():
            prm.set(k, v)
        again = oxide.backtest(prm, last=oxide.STRICT_LAST_QUARTER)
        self.assertEqual(s["forward"], again["forward"])
        self.assertEqual(s["fit"], again["fit"])
        self.assertGreater(s["forward"]["mape_pct"], d["forward"]["mape_pct"])     # the stricter test is honestly worse

    def test_table_values_are_the_optimum_of_the_fit(self):
        prm = TABLE_DEFAULT()
        res = oxide.calibrate(prm, iters=120)
        now = math.sqrt(sum((v / oxide.quarters()[k][2] - 1.0) ** 2 for k, v in oxide.model_quarters(oxide.kinetics(prm)).items()
                            if k <= oxide.FIT_LAST_QUARTER) / 32)
        self.assertLess(abs(res["rel_rmse_fit"] - now), 0.003)           # nothing better near the table values

    def test_kinetics_rows_are_fitted_and_say_so(self):
        for k in ("ox_rmax", "ox_th_d", "ox_ea_app_jmol", "ox_m0_t"):
            r = TABLE[k]
            self.assertEqual(r.label, "calc", k)
            self.assertTrue(r.min <= r.value <= r.max, k)
        self.assertIn("fitted", TABLE["ox_rmax"].note)
        self.assertIn("2020 Q2", TABLE["ox_th_d"].note)


class FaradayTest(unittest.TestCase):
    def test_constants_and_design(self):
        prm = TABLE_DEFAULT()
        self.assertAlmostEqual(prm["ox_ew_gpah"], 63.546 / (2 * 26.8015), places=9)
        k = prm["ox_ew_gpah"] * 1e-6 * prm["ox_ew_cells"] * prm["ox_ew_ce"]
        i_nom = oxide.design_current_ka(prm) * 1000.0
        self.assertAlmostEqual(k * i_nom * 8760.0, prm["ox_ew_design_kty"] * 1000.0, places=6)          # 25 kt a year at the design current
        self.assertTrue(250 <= oxide.design_density_am2(prm) <= 430)       # analogs: Cerro Verde 250, Tenke 430 A/m2

    def test_cathode_is_faraday_of_the_current(self):
        p = Plant(TABLE_DEFAULT(), 42, mode="scenario")
        p.ox_date = DATE
        p.run_until(p.t_min + 120)
        s = snap(p)["ew-1"]
        prm = p.prm
        want = prm["ox_ew_gpah"] * 1e-6 * s["current_ka"] * 1000.0 * prm["ox_ew_cells"] * prm["ox_ew_ce"]
        self.assertAlmostEqual(s["cathode_tph"], want, delta=0.002 * want)
        self.assertAlmostEqual(s["kwh_t"], 1834.0, delta=2.0)               # 2.0 V / (1.1855 g/Ah x 0.92) = 1.83 MWh per tonne
        self.assertAlmostEqual(s["power_mw"], s["current_ka"] * 1000.0 * prm["ox_ew_cells"] * s["voltage_v"] / 1e6, places=6)


class ChainTest(unittest.TestCase):
    def test_normal_shift_states_and_balance(self):
        f, total, rows = shift("")
        s = rows[-1]
        for t in ("oxfeed-1", "leach-1", "pls-1", "sx-1", "ew-1", "catstore-1", "sxew-1"):
            self.assertEqual(s[t]["state"], "NORMAL", t)
        self.assertAlmostEqual(s["ew-1"]["cathode_tph"], s["ew-1"]["cathode_exp_tph"], delta=0.01 * s["ew-1"]["cathode_exp_tph"])
        self.assertEqual((s["sxew-1"]["year"], s["sxew-1"]["quarter"]), (2025.0, 4.0))
        self.assertAlmostEqual(s["leach-1"]["quarter_cathode_kt"], 3.5)
        self.assertAlmostEqual(s["oxfeed-1"]["ore_tph"], 1280 * 1000 / oxide.quarter_hours(2025, 4), places=6)
        self.assertAlmostEqual(s["sx-1"]["extraction_pct"], 95.0, places=3)
        self.assertAlmostEqual(s["pls-1"]["pls_gl"], s["leach-1"]["pls_gl"], delta=0.02)
        # the model against the reported level of the quarter is the back-test error of the day (the state shows it)
        self.assertLess(abs(s["sxew-1"]["model_dev_pct"]), 25.0)

    def test_copper_balance_of_the_chain(self):
        """dissolved - cathode = change of the copper in transit (pad drain, ponds, electrolyte)."""
        cs = CopySet(None, 42, "")
        f = cs.copies["fact"]
        f.ox_date = DATE
        cs.step()
        st = f.state

        def inventory():
            lc, pl, ew = st.leach, st.pls, st.ew
            return lc.hold_cu_t + pl.cu_t + TABLE["ox_raff_v_m3"].value * pl.raff_gl / 1000.0 + ew.electrolyte_cu_t
        start, diss, dep0 = inventory(), 0.0, st.sxew.cathode_t_total
        for _ in range(60 * 10):
            before = st.leach.leach_cu_tph
            cs.step()
            diss += before / 60.0
        dep = st.sxew.cathode_t_total - dep0
        moved = inventory() - start
        self.assertAlmostEqual(diss - dep, moved, delta=0.03 * dep)

    def test_leachcold_cuts_irrigation_then_the_cathode_follows_and_ends(self):
        f, total, rows = shift("leachcold")
        base = shift("")[1]
        self.assertEqual(rows[0]["leach-1"]["state"], "COLD")
        self.assertAlmostEqual(rows[0]["leach-1"]["irrigation_pct"], 75.0, places=6)
        self.assertEqual(rows[0]["leach-1"]["cold_frac"], TABLE["ox_cold_frac"].value)
        self.assertLess(rows[0]["ew-1"]["cathode_tph"], rows[0]["ew-1"]["cathode_exp_tph"])          # the cathode follows with a delay
        self.assertGreater(rows[0]["ew-1"]["cathode_tph"], 0.9 * rows[0]["ew-1"]["cathode_exp_tph"])
        self.assertLess(rows[7]["ew-1"]["cathode_tph"], 0.85 * rows[7]["ew-1"]["cathode_exp_tph"])  # at the end of the spell (8 h)
        self.assertEqual(rows[9]["leach-1"]["state"], "NORMAL")
        self.assertAlmostEqual(rows[9]["leach-1"]["irrigation_pct"], 100.0, places=6)
        self.assertGreater(rows[11]["ew-1"]["cathode_tph"], rows[7]["ew-1"]["cathode_tph"])
        self.assertLess(total, base)

    def test_winter_flag_does_not_cut_the_oxide_twice(self):
        a = Plant(TABLE_DEFAULT(), 42, mode="scenario")
        b = Plant(TABLE_DEFAULT(), 42, mode="scenario")
        b.winter_on = True
        for p in (a, b):
            p.ox_date = (2025, 330)
            p.run_until(p.t_min + 120)
        self.assertEqual(snap(a)["ew-1"]["cathode_tph"], snap(b)["ew-1"]["cathode_tph"])

    def test_the_token_takes_a_duration_inside_the_row(self):
        cs = CopySet(None, 42, "leachcold@60=3")
        ev = [e for e in cs.copies["fact"]._events if e.kind == "leachcold"]
        self.assertEqual(len(ev), 1)
        self.assertAlmostEqual(ev[0].duration_h, 3.0)
        for tok in ("leachcold:1", "ewtrip:1", "sxcrud:2"):
            with self.assertRaises(ValueError):
                CopySet(None, 42, tok)

    def test_the_oxide_chain_changes_nothing_in_the_sulphide_plant(self):
        keys = ("cu_t", "ore_t", "energy_mwh", "water_m3", "usd")
        out = []
        for scn in ("", "leachcold", "ewtrip", "sxcrud"):
            cs = CopySet(None, 42, scn)
            for _ in range(240):
                cs.step()
            out.append({k: cs.copies["fact"].shift_summary()[k] for k in keys})
        for o in out[1:]:
            self.assertEqual(o, out[0])
        # and with the whole oxide step removed
        import sim.plant as plant_mod
        real = plant_mod.oxide.oxide_step
        plant_mod.oxide.oxide_step = lambda *a, **k: None
        try:
            cs = CopySet(None, 42, "")
            for _ in range(240):
                cs.step()
            gone = {k: cs.copies["fact"].shift_summary()[k] for k in keys}
        finally:
            plant_mod.oxide.oxide_step = real
        self.assertEqual(gone, out[0])


class EwTripTest(unittest.TestCase):
    def test_trip_stops_the_current_the_electrolyte_fills_and_sx_stops(self):
        f, total, rows = shift("ewtrip")
        self.assertEqual(rows[0]["ew-1"]["state"], "TRIP")
        self.assertEqual(rows[0]["ew-1"]["current_ka"], 0.0)
        self.assertEqual(rows[0]["ew-1"]["cathode_tph"], 0.0)
        self.assertGreater(rows[0]["ew-1"]["current_set_ka"], 10.0)
        self.assertGreater(rows[2]["ew-1"]["electrolyte_cu_t"], rows[0]["ew-1"]["electrolyte_cu_t"])
        e_max = TABLE["ox_ew_emax_frac"].value * TABLE["ox_ew_el_m3"].value * TABLE["ox_ew_el_gl"].value / 1000.0
        self.assertLessEqual(max(r["ew-1"]["electrolyte_cu_t"] for r in rows), e_max + 0.05)
        self.assertLess(rows[4]["sx-1"]["extraction_pct"], 60.0)           # the strip is blocked: copper goes round the loop
        self.assertLess(rows[4]["sx-1"]["transfer_cu_tph"], 0.5 * rows[0]["sx-1"]["transfer_cu_tph"])
        # restart after ox_rect_auto_h (8 h): the current goes to the limit of the rectifier and catches up
        self.assertEqual(rows[8]["ew-1"]["state"], "LIMIT")
        self.assertGreater(rows[8]["ew-1"]["cathode_tph"], 2.0 * rows[8]["ew-1"]["cathode_exp_tph"])

    def test_call_restores_after_the_arrival_and_the_work(self):
        f, total, rows = shift("ewtrip", call=("ew-1", 10))
        base = shift("")[1]
        self.assertEqual(rows[0]["ew-1"]["state"], "TRIP")                  # arrival 20-40 min + 2 h of work
        self.assertNotEqual(rows[3]["ew-1"]["state"], "TRIP")
        self.assertEqual(f.state.oxf, {})
        self.assertGreater(total, base - 1.0)

    def test_numbers_of_the_catalog(self):
        base, trip, called = shift("")[1], shift("ewtrip")[1], shift("ewtrip", call=("ew-1", 10))[1]
        what = next(s for s in scenarios.catalog() if s["id"] == "ewtrip")["what"]
        for v in (base, trip, called):
            self.assertIn(("%.1f" % v).replace(".", ","), what)


class SxCrudTest(unittest.TestCase):
    def test_crud_grows_extraction_and_flow_fall_the_pond_fills(self):
        f, total, rows = shift("sxcrud")
        self.assertAlmostEqual(rows[0]["sx-1"]["crud_cm"], TABLE["ox_crud_ok_cm"].value + (TABLE["ox_crud_alert_cm"].value - TABLE["ox_crud_ok_cm"].value) / 5.0, delta=0.02)
        self.assertEqual(rows[0]["sx-1"]["state"], "NORMAL")
        self.assertEqual(rows[5]["sx-1"]["state"], "CRUD")                  # above the alert layer after 5 h
        self.assertLess(rows[11]["sx-1"]["extraction_pct"], 60.0)
        self.assertAlmostEqual(rows[11]["sx-1"]["crud_cm"], TABLE["ox_crud_crit_cm"].value, places=2)
        self.assertGreater(rows[11]["sx-1"]["raff_cu_gl"], 3.0 * rows[0]["sx-1"]["raff_cu_gl"])
        self.assertGreater(rows[11]["pls-1"]["level_pct"], rows[0]["pls-1"]["level_pct"])
        self.assertLess(rows[11]["ew-1"]["cathode_tph"], 0.6 * rows[11]["ew-1"]["cathode_exp_tph"])
        self.assertLess(f.state.sxew.cathode_t_total, shift("")[1])

    def test_call_removes_the_crud(self):
        f, total, rows = shift("sxcrud", call=("sx-1", 10))
        self.assertEqual(f.state.oxf, {})
        self.assertAlmostEqual(rows[11]["sx-1"]["extraction_pct"], 95.0, places=3)
        self.assertGreater(total, shift("")[1] - 1.0)

    def test_numbers_of_the_catalog(self):
        base, crud, called = shift("")[1], shift("sxcrud")[1], shift("sxcrud", call=("sx-1", 10))[1]
        what = next(s for s in scenarios.catalog() if s["id"] == "sxcrud")["what"]
        for v in (base, crud, called):
            self.assertIn(("%.1f" % v).replace(".", ","), what)
        cold = next(s for s in scenarios.catalog() if s["id"] == "leachcold")["what"]
        self.assertIn(("%.1f" % shift("leachcold")[1]).replace(".", ","), cold)


class ModuleTest(unittest.TestCase):
    def run_mod(self, scn, minutes, call=None):
        cs = CopySet(None, 42, scn, kip=1)
        fact = cs.copies["fact"]
        for k in [k for k in cs.copies if k != "fact"]:
            cs.copies.pop(k)
        fact.ox_date = DATE
        st, prm = ms.make_store(fact.t_min)
        lm, om = losses.LossesModule(prm, st, ms.ROLES), ore.OreModule(prm, st)
        pm = priority.PriorityModule(prm, st, lm, om, ms.ROLES)
        issues = {}
        for k in range(minutes // 5):
            for _ in range(5):
                fact.step()
            t = fact.t_min
            st.update_from_search(ms.items_from_plant(fact))
            lm.compute(t)
            if t % 15 == 0:
                om.compute(t)
            _f, issues = pm.compute(t, seed=1)
            if call and k * 5 == call[1]:
                fact.call(call[0])
        return {k: v for k, v in issues.items() if v.get("kind") in mox.KINDS}, prm

    def one(self, issues, kind):
        found = [v for v in issues.values() if v["kind"] == kind]
        self.assertEqual(len(found), 1, kind)
        return found[0]

    def test_cold_pad_is_a_priced_money_trouble_for_the_metallurgist(self):
        issues, prm = self.run_mod("leachcold", 60)
        f = self.one(issues, "leach_cold")
        self.assertEqual(f["node"], "leach-1")
        self.assertIn("Металлург смены", f["responsible"])
        self.assertEqual(f.get("safety_class", ""), "")
        self.assertGreater(f["loss_usd_h"], 0.0)
        lexp = 1.41                                                         # t/h of copper at the date
        self.assertAlmostEqual(f["loss_usd_h"], lexp * 0.25 * prm["cu_price_usd_t"], delta=0.12 * lexp * 0.25 * prm["cu_price_usd_t"])
        self.assertIn("допущение", f["text"])
        self.assertIn("орошение кучи 75 %", f["text"])
        self.assertIn(readiness.NOT_FOUND, f["checklist"])
        self.assertIn("Закроется", f["closure"])

    def test_rectifier_trip_is_a_priced_money_trouble_for_the_electrician(self):
        issues, prm = self.run_mod("ewtrip", 60)
        f = self.one(issues, "ew_rect")
        self.assertEqual(f["node"], "ew-1")
        self.assertIn("энергетик", f["responsible"].lower())
        self.assertEqual(f.get("safety_class", ""), "")
        self.assertAlmostEqual(f["loss_usd_h"], 1.41 * prm["cu_price_usd_t"] * prm["cathode_payable_frac"], delta=0.1 * 1.41 * prm["cu_price_usd_t"])
        self.assertIn("кА", f["text"])
        self.assertIn("Фарадею", f["text"])
        self.assertIn(readiness.NOT_FOUND, f["checklist"])

    def test_crud_trouble_opens_at_the_alert_layer_and_closes_after_the_call(self):
        none, _ = self.run_mod("sxcrud", 200)
        self.assertEqual([v for v in none.values() if v["kind"] == "sx_crud"], [])          # 3.3 h: the layer is still below 3 cm
        issues, prm = self.run_mod("sxcrud", 380)
        f = self.one(issues, "sx_crud")
        self.assertEqual(f["node"], "sx-1")
        self.assertIn("Металлург смены", f["responsible"])
        self.assertIn("краб", f["text"])
        self.assertGreater(f["loss_usd_h"], 0.0)
        after, _ = self.run_mod("sxcrud", 640, call=("sx-1", 380))
        left = [v for v in after.values() if v["kind"] == "sx_crud" and v.get("status") not in ("RESOLVED", None)]
        self.assertEqual(left, [])

    def test_the_kinds_have_names_cards_and_who(self):
        for k in mox.KINDS:
            self.assertIn(k, priority.WHO)
            self.assertIn(k, priority.SHORT_RU)
            self.assertEqual(priority.KIND_READY[k], k)
            card = readiness.by_id(k)
            self.assertTrue(card["scenario"])
        self.assertEqual(readiness.missing(), [])
        ru = read(STATIC, "ru.js")
        for k in mox.KINDS:
            self.assertIn(k + ":", ru)
        self.assertIn("катод", readiness.by_id("leach_cold")["price"])
        self.assertIn("1,185", readiness.by_id("ew_rect")["source"])


class ThingsTest(unittest.TestCase):
    TYPES = ("oxfeed", "leach", "plspond", "sx", "ew", "catstore", "sxew")
    THINGS = ("oxfeed-1", "leach-1", "pls-1", "sx-1", "ew-1", "catstore-1", "sxew-1")

    def test_types_things_and_the_chain(self):
        d = json.loads(read(ROOT, "setup", "things.json"))
        self.assertEqual((len(d["types"]), len(d["things"])), (50, 141))
        names = {t["name"]: t for t in d["things"]}
        chain = ["oxfeed-1", "leach-1", "pls-1", "sx-1", "ew-1", "catstore-1"]
        for a, b in zip(chain, chain[1:]):
            self.assertEqual(names[a]["feeds"], [b])
        for n in self.THINGS:
            self.assertTrue(names[n]["passport"], n)
            self.assertEqual(names[n]["parent"], "site")
            for k, v in names[n]["passport"].items():
                if len(v) >= 3:
                    self.assertIn(v[2], d["sources"] | {"assume": 1, "calc": 1}, f"{n}.{k}")
        for typ in self.TYPES:
            self.assertTrue(os.path.isfile(os.path.join(ROOT, "models", f"{typ}-1.0.0.tm.jsonld")), typ)
            self.assertEqual(set(d["types"][typ]["features"]), set(FEATURE_RULES[typ]), typ)
        self.assertEqual(names["ew-1"]["responsible"]["role"], "power_engineer")

    def test_features_published_by_the_simulator_are_the_rules(self):
        p = Plant(TABLE_DEFAULT(), 42, mode="scenario")
        p.ox_date = DATE
        p.run_until(p.t_min + 10)
        s = snap(p)
        for typ, n in zip(self.TYPES, self.THINGS):
            self.assertEqual(set(s[n]), set(FEATURE_RULES[typ]), n)

    def test_parameters_have_source_label_and_range(self):
        keys = [k for k in TABLE if k.startswith("ox_")]
        self.assertGreaterEqual(len(keys), 40)
        for k in keys:
            r = TABLE[k]
            self.assertTrue(r.source and r.label in ("fact", "vendor", "project", "analog", "assumption", "calc") and r.min <= r.value <= r.max, k)
        self.assertEqual(TABLE["ox_cold_frac"].label, "analog")
        self.assertIn("-25 %", TABLE["ox_cold_frac"].source)
        self.assertEqual(TABLE["ox_irr_m3h"].label, "project")
        self.assertEqual(TABLE["ox_ew_ce"].label, "analog")
        self.assertEqual(TABLE["ox_sx_eta"].label, "assumption")      # no verified open source for the extraction


class WebTest(unittest.TestCase):
    def test_catalog_cards_and_pages(self):
        sc = json.loads(read(STATIC, "scenarios.json"))
        ids = {x["id"]: x for x in sc["scenarios"]}
        for i, card in (("leachcold", "leach_cold"), ("ewtrip", "ew_rect"), ("sxcrud", "sx_crud")):
            self.assertEqual(ids[i]["card"], card)
            self.assertTrue(ids[i]["test"].startswith("tests/test_oxide.py"))
        kinds = {t["kind"] for t in sc["constructor"]["troubles"]}
        self.assertTrue({"leachcold", "ewtrip", "sxcrud"} <= kinds)
        rd = json.loads(read(STATIC, "readiness.json"))
        self.assertTrue({"leach_cold", "ew_rect", "sx_crud"} <= {x["id"] for x in rd["items"]})
        flow, plan = read(STATIC, "flow.js"), read(STATIC, "plan.js")
        self.assertIn("cp-oxsvg", flow)
        self.assertIn("не замер", flow)
        for n in ThingsTest.THINGS[:-1]:
            self.assertIn(n, plan)
            self.assertIn(n, flow)
        anchors = json.loads(read(STATIC, "plan.json"))["anchors"]
        for n in ThingsTest.THINGS:
            self.assertTrue(anchors[n]["scheme"], n)
        self.assertIn("CRUD", read(STATIC, "app.js"))
        self.assertIn("/backtest_ox.json", read(STATIC, "oxbacktest.js"))
        self.assertIn("cb-ox", read(STATIC, "views.js"))
        self.assertIn("oxbacktest.js", read(STATIC, "index.html"))

    def test_inside_has_the_oxide_nodes_with_sources(self):
        d = json.loads(read(STATIC, "inside.json"))
        nodes = {n["id"]: n for g in d["groups"] for n in g["nodes"]}
        for nid in ("p-ox-feed", "p-ox-heap", "p-ox-pond", "p-ox-sx", "p-ox-ew", "p-ox-store"):
            self.assertIn(nid, nodes)
            self.assertTrue(nodes[nid]["signals"] and nodes[nid]["what"])
        self.assertEqual(set(nodes["p-ox-ew"]["troubles"]), {"ew_rect"})
        self.assertIn("leach_cold", nodes["p-ox-heap"]["troubles"])
        for s in nodes["p-ox-heap"]["signals"] + nodes["p-ox-ew"]["signals"]:
            self.assertTrue(s["thing"] and s["feature"] and s["label"])

    def test_only_a_deviation_gets_a_label(self):
        plan = read(STATIC, "plan.js")
        m = re.search(r"const oxText = n => (.*)", plan)
        self.assertIn("OX_DEV[n].test", m.group(1))
        self.assertIn(": ''", m.group(1))


if __name__ == "__main__":
    unittest.main()
