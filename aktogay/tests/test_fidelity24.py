"""Behaviour fidelity of 24.10.2026: live plausibility check, truck cycle from the map, mine-plan variability of the ore,
the committed results of sim/fidelity.py and sim/influence.py and their page."""
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sim import events, fidelity, haul, ore, plausibility as pl  # noqa: E402
from sim.params import TABLE, default  # noqa: E402
from sim.plant import Plant  # noqa: E402

STATIC = os.path.join(ROOT, "web", "static")
DATA = os.path.join(ROOT, "sim", "data")


def read_json(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return json.load(f)


class PlausibilityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = pl.build()
        cls.plant = Plant(seed=5)
        for _ in range(240):
            cls.plant.step(5.0)
        cls.snap = cls.plant.snapshot()

    def test_list_is_15_to_20_checks_each_with_source_and_label(self):
        ids = [c["id"] for c in self.spec["checks"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(15 <= len(ids) <= 20, len(ids))
        for c in self.spec["checks"]:
            self.assertTrue(c["src"].strip(), c["id"])
            self.assertIn(c["label"], ("fact", "vendor", "project", "analog", "calc", "assumption"), c["id"])
            self.assertIn(c["group"], pl.GROUP_RU)
            self.assertTrue(c["items"], c["id"])
        groups = {c["group"] for c in self.spec["checks"]}
        self.assertEqual(groups, {"balance", "limit", "range"})
        # the balances named in the task: Cu, water, mass, energy; SAG 28 MW; stockpile; truck 236 t
        for need in ("b_cu_line", "b_water", "b_ore", "b_energy", "l_sag", "l_stock", "l_truck"):
            self.assertIn(need, ids)

    def test_committed_json_is_current(self):
        with open(os.path.join(STATIC, "plausibility.json"), encoding="utf-8") as f:
            self.assertEqual(f.read(), pl.json_text())

    def test_running_model_passes_everything_that_has_data(self):
        rows = {r["id"]: r for r in pl.evaluate(self.spec, pl.snapshot_getter(self.snap))}
        self.assertEqual([k for k, r in rows.items() if r["status"] == "bad"], [])
        # the module residuals live in Ditto only: no data here is "na", never a pass
        self.assertEqual(rows["b_cu_mod"]["status"], "na")
        self.assertEqual(rows["b_conc"]["status"], "na")
        self.assertEqual(rows["l_truck"]["status"], "ok")
        self.assertLessEqual(rows["l_truck"]["value"], 236.0)

    def test_scenarios_keep_the_invariants(self):
        for text in ("crusher:1", "grid", "hpgr_fire", "reline:1", "conveyor:1"):
            pl_ = Plant(seed=5)
            for _ in range(30):
                pl_.step(5.0)
            pl_.apply_scenario(events.parse_scenario(text, pl_.t_min, pl_.prm))
            for i in range(120):
                pl_.step(5.0)
                if i % 12 == 11:
                    bad = [r["id"] for r in pl.evaluate(self.spec, pl.snapshot_getter(pl_.snapshot())) if r["status"] == "bad"]
                    self.assertEqual(bad, [], (text, i))

    def test_a_violation_is_caught(self):
        snap = json.loads(json.dumps(self.snap))
        snap["sag-1"]["power_kw"] = 29000.0
        snap["stockpile-2"]["level_t"] = 170000.0
        snap["truck-25"]["load_t"] = 240.0                    # a 793D above its 236 t
        snap["water"]["residual_pct"] = 2.0
        snap["flot-1"]["conc_cu"] = 40.0
        rows = {r["id"]: r for r in pl.evaluate(self.spec, pl.snapshot_getter(snap))}
        for k in ("l_sag", "l_stock", "l_truck", "b_water", "r_conc", "b_cu_line"):
            self.assertEqual(rows[k]["status"], "bad", k)
        self.assertEqual(rows["l_truck"]["name"].split()[0], "truck-25")

    def test_the_limit_of_a_truck_is_its_own_model(self):
        snap = json.loads(json.dumps(self.snap))
        snap["truck-05"]["load_t"] = 150.0                    # a CAT 785 (136 t) carries 150 t: fails although below 236
        rows = {r["id"]: r for r in pl.evaluate(self.spec, pl.snapshot_getter(snap))}
        self.assertEqual(rows["l_truck"]["status"], "bad")
        self.assertEqual(self.plant.state.trucks[4].model, "CAT 785")

    def test_missing_numbers_are_not_a_pass(self):
        rows = pl.evaluate(self.spec, lambda ref: None)
        self.assertEqual({r["status"] for r in rows}, {"na"})

    def test_payload_of_793d_is_the_report_figure(self):
        self.assertEqual(TABLE["fleet_payload_793_t"].value, 236)
        self.assertEqual(TABLE["fleet_payload_793_t"].label, "fact")
        self.assertIn("61", TABLE["fleet_payload_793_t"].source)

    def test_page_wiring(self):
        with open(os.path.join(STATIC, "index.html"), encoding="utf-8") as f:
            idx = f.read()
        self.assertIn('<script src="/plausibility.js"></script>', idx)
        self.assertIn('<script src="/fidelity.js"></script>', idx)
        with open(os.path.join(STATIC, "views.js"), encoding="utf-8") as f:
            v = f.read()
        for w in ("cb-plaus", "Проверка правдоподобия", "AKT.plaus.tick()", "cb-fid", "cb-infl"):
            self.assertIn(w, v)

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_js_gives_the_same_verdicts_as_python(self):
        snap = json.loads(json.dumps(self.snap))
        snap["sag-2"]["power_kw"] = 31000.0
        snap["truck-30"]["load_t"] = 241.0
        want = {r["id"]: r for r in pl.evaluate(self.spec, pl.snapshot_getter(snap))}
        js = (
            "const fs=require('fs');const snap=JSON.parse(fs.readFileSync(process.argv[1],'utf8'));"
            "globalThis.window=globalThis;globalThis.AKT={num:(t,f)=>{const v=(snap[t]||{})[f];return typeof v==='number'?v:null;}};"
            "eval(fs.readFileSync(process.argv[2],'utf8'));"
            "const spec=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));"
            "console.log(JSON.stringify(AKT.plaus.evaluate(spec)));")
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "snap.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(snap, f)
            r = subprocess.run(["node", "-e", js, p, os.path.join(STATIC, "plausibility.js"),
                                os.path.join(STATIC, "plausibility.json")], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        got = {x["id"]: x for x in json.loads(r.stdout)}
        self.assertEqual(set(got), set(want))
        for k, w in want.items():
            self.assertEqual(got[k]["status"], w["status"], k)
            if w["value"] is not None:
                self.assertAlmostEqual(got[k]["value"], w["value"], places=6, msg=k)
        self.assertEqual(got["l_sag"]["status"], "bad")
        self.assertEqual(got["l_truck"]["status"], "bad")

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_availability_rows_of_the_live_check_carry_no_false_verdict(self):
        """The crusher row is a requirement of the reported ore on the equipment and the grinding row is a fit: neither is shown as «не выполнено»;
        only flotation (a check against the design availability) has a verdict. The first build of the page showed two red crosses here."""
        js = (
            "const fs=require('fs');globalThis.window=globalThis;globalThis.AKT={num:()=>null};"
            "eval(fs.readFileSync(process.argv[1]+'/plausibility.js','utf8'));"
            "AKT.plaus.spec=JSON.parse(fs.readFileSync(process.argv[1]+'/plausibility.json','utf8'));"
            "AKT.fidelity={data:JSON.parse(fs.readFileSync(process.argv[1]+'/fidelity.json','utf8'))};"
            "console.log(JSON.stringify(AKT.plaus.render()));")
        r = subprocess.run(["node", "-e", js, STATIC], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        html = json.loads(r.stdout)
        self.assertNotIn("✗ не выполнено", html)
        self.assertIn("требование к оборудованию", html)
        self.assertIn("подгонка, не проверка", html)
        self.assertIn("✓ выполнено</b></td><td>доступность</td><td>Флотация", html)
        self.assertNotIn("паспортной вилк", html)


class HaulTest(unittest.TestCase):
    def setUp(self):
        self.p = default()

    def test_cycle_is_the_sum_of_its_parts(self):
        for line in haul.ROUTES:
            lg = haul.legs(self.p, line)
            self.assertAlmostEqual(lg["total"], lg["load"] + lg["haul"] + lg["queue"] + lg["dump"] + lg["back"])
            self.assertAlmostEqual(haul.cycle_min(self.p, line), lg["total"])
        self.assertAlmostEqual(haul.dump_min(self.p), (20.25 + 17.51) / 60.0 + 0.5, places=6)

    def test_distances_are_the_ones_of_the_map(self):
        plan = read_json(STATIC, "plan.json")
        km = haul.measure_map(plan)
        self.assertAlmostEqual(km[1], self.p["fleet_ramp_km_1"], delta=0.002)
        self.assertAlmostEqual(km[2], self.p["fleet_ramp_km_2"], delta=0.002)
        self.assertAlmostEqual(km[0], self.p["fleet_waste_km"], delta=0.002)
        self.assertEqual(TABLE["fleet_ramp_km_1"].label, "calc")
        self.assertIn("расчёт по карте", TABLE["fleet_ramp_km_1"].source)

    def test_speed_follows_the_power_and_the_grade(self):
        v1, v2 = haul.v_loaded_kmh(self.p, 1), haul.v_loaded_kmh(self.p, 2)
        self.assertTrue(11.8 <= v1 <= 25.0 and 11.8 <= v2 <= 25.0, (v1, v2))      # gear 1 of the Specalog is 11.8 km/h
        self.assertGreater(v2, v1)                                                # line 2 ramp is flatter
        steep = self.p.copy(fleet_rise_m_1=240.0)
        self.assertLess(haul.v_loaded_kmh(steep, 1), v1)
        self.assertLess(haul.v_loaded_kmh(self.p.copy(fleet_power_793_kw=1000.0), 1), v1)
        self.assertGreater(haul.cycle_min(self.p.copy(fleet_speed_eff=0.4), 1), haul.cycle_min(self.p, 1))

    def test_the_one_calibrated_factor_keeps_the_2025_cycle(self):
        self.assertAlmostEqual(haul.mean_ore_cycle_min(self.p), haul.REF_CYCLE_MIN, delta=0.1)
        self.assertAlmostEqual(haul.calibrate(self.p), self.p["fleet_speed_eff"], delta=0.002)
        self.assertEqual(TABLE["fleet_speed_eff"].label, "assumption")
        self.assertAlmostEqual(TABLE["fleet_trip_min"].value, 30.0)

    def test_cycle_is_kept_until_a_value_changes(self):
        p = default()
        a = haul.cycle_min(p, 1)
        self.assertIs(haul.legs(p, 1), haul.legs(p, 1))                # kept, not recomputed every step
        p.set("fleet_speed_eff", 0.9)
        self.assertLess(haul.cycle_min(p, 1), a)                       # a change of a value drops the kept result
        q = p.copy(fleet_load_min=5.0)
        self.assertAlmostEqual(haul.cycle_min(q, 1) - haul.cycle_min(p, 1), 2.0, places=6)
        self.assertAlmostEqual(haul.cycle_min(default(), 1), a, places=9)

    def test_plant_uses_the_route_cycles(self):
        pl_ = Plant(seed=3)
        for _ in range(30):
            pl_.step(5.0)
        st = pl_.state
        want = sum(t.payload_t * 60.0 / haul.cycle_min(pl_.prm, t.line) for t in st.trucks if t.ready and t.duty == "ore")
        self.assertAlmostEqual(st.fleet.haul_tph, want, places=6)
        cycles = {t.line: round(t.cycle_min, 3) for t in st.trucks}
        self.assertNotEqual(cycles[1], cycles[2])                 # two ramps, two cycles
        self.assertAlmostEqual(cycles[1], haul.cycle_min(pl_.prm, 1), places=2)

    def test_phases_follow_the_legs(self):
        from sim import pit
        p = self.p
        cycle = haul.cycle_min(p, 1)
        share = haul.loaded_share(p, 1)
        seen = [pit.truck_phase(t * 0.5, 0.0, cycle, p, share) for t in range(int(cycle * 2))]
        self.assertEqual(seen[0], "LOADING")
        self.assertEqual(set(seen), set(pit.PHASES))
        self.assertGreater(seen.count("HAUL_FULL"), seen.count("RETURN"))      # loaded uphill takes longer than the return
        self.assertEqual(pit.truck_phase(0.0, 0.0, 30.0, p), "LOADING")        # old four-argument call still works


class OrePlanTest(unittest.TestCase):
    def test_off_by_default_and_unchanged(self):
        p = default()
        self.assertEqual(p["blk_plan_on"], 0)
        a = ore.draw_block(1001, 77, p)
        b = ore.draw_block(1001, 77, p.copy(blk_plan_sigma_cu=0.2))      # the sigma does nothing while the switch is off
        self.assertEqual(a, b)

    def test_slow_noise_is_shared_by_neighbours_and_has_unit_variance(self):
        p = default().copy(blk_plan_on=1)
        near = [ore.plan_walk(7, b, p)[0] for b in range(100, 110)]
        self.assertLess(max(near) - min(near), 0.8)
        xs = [ore.plan_walk(s, b, p)[0] for s in range(1, 40) for b in range(0, 5000, 250)]
        m = sum(xs) / len(xs)
        v = sum((x - m) ** 2 for x in xs) / len(xs)
        self.assertAlmostEqual(v, 1.0, delta=0.15)
        self.assertAlmostEqual(m, 0.0, delta=0.1)

    def test_switching_on_moves_the_quarterly_grade_spread_to_the_reported_one(self):
        import statistics as st
        p = default().copy(blk_plan_on=1)
        means = []
        for q in range(12):
            tot = sum(ore.draw_block(11, q * 1000 + b + 1, p)[1].cu_pct for b in range(1000))
            means.append(tot / 1000)
        sd = st.pstdev([math.log(y / x) for x, y in zip(means, means[1:])])
        self.assertTrue(0.02 < sd < 0.09, sd)
        off = default()
        means = [sum(ore.draw_block(11, q * 1000 + b + 1, off)[1].cu_pct for b in range(1000)) / 1000 for q in range(12)]
        self.assertLess(st.pstdev([math.log(y / x) for x, y in zip(means, means[1:])]), 0.012)


class CommittedResultsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = read_json(DATA, "fidelity.json")

    def test_static_copies_equal_the_sources(self):
        for name in ("fidelity.json", "influence.json"):
            with open(os.path.join(DATA, name), encoding="utf-8") as a, open(os.path.join(STATIC, name), encoding="utf-8") as b:
                self.assertEqual(a.read(), b.read(), name)

    def test_fit_is_the_one_of_the_backtest(self):
        bt = read_json(DATA, "backtest_q.json")
        self.assertEqual(self.f["fit"], bt["fit"])

    def test_availability_is_reported_whatever_it_is(self):
        u = self.f["availability"]["units"]
        self.assertEqual(set(u), {"crusher", "grinding", "flotation"})
        # only flotation is a check; the grinding hours follow the availability fitted to the ore of 2025 (a fit); the crusher row is a
        # requirement of the reported ore on the equipment with no tolerance verdict (no crusher nameplate exists)
        self.assertEqual((u["flotation"]["class"], u["grinding"]["class"], u["crusher"]["class"]), ("check", "fit", "requirement"))
        self.assertTrue(u["flotation"]["ok"])
        self.assertIsNone(u["grinding"]["ok"])
        c = u["crusher"]
        self.assertIsNone(c["ok"])
        self.assertIsNone(c["delta_pp"])
        self.assertNotIn("ok_at_lower_cap", c)
        # hour meter (crushed ore / rated rate) on the two ends of the design range of the AREA 4386-5043.9 t/h, and the arithmetic of the
        # requirement: 31.05 Mt per crusher over the rate over 8 760 h; the OVOS design is 285 d x 2 x 10 h = 5 700 h = 65.1 % of the year
        self.assertEqual([round(x) for x in c["required_rates_tph"]], [4386, 4544, 5044])
        for got, want in zip(c["required_hours_pct"], (80.8, 78.0, 70.3)):
            self.assertAlmostEqual(got, want, delta=0.05)
        self.assertAlmostEqual(c["design_hours_pct"], 65.1, delta=0.05)
        self.assertLess(c["run_pct_range"][0], c["run_pct_range"][1])
        self.assertEqual(c["cap_tph_range"], [4386.0, 5043.9])
        self.assertLess(c["state_run_pct"], 100.0)
        self.assertAlmostEqual(sum(c["breakdown_pct"].values()), 100.0, delta=0.05)
        self.assertEqual((c["lit_lo"], c["lit_hi"]), (70.0, 75.0))

    def test_reline_events(self):
        r = self.f["relines"]
        self.assertEqual(r["n"], 5)
        ids = [e["id"] for e in r["events"]]
        self.assertEqual(ids, ["2023Q4-S1", "2023Q4-S2", "2024Q4-S2", "2025Q1-S1", "2025Q3-S2"])
        for e in r["events"]:
            self.assertLess(e["obs_drop_pct"], -3.0)
            self.assertLess(e["pred_drop_pct"], -3.0)
            self.assertTrue(e["url"].startswith("https://www.kazminerals.com"))
        self.assertLess(abs(r["mean_obs_pct"] - r["mean_pred_pct"]), 3.0)
        self.assertEqual(set(r["sensitivity_reline_h"]), {"72", "84"})
        # the quarters of the events differ in length: the reported drop is also given per day (VALIDATION 6.3, C6)
        self.assertAlmostEqual(r["mean_obs_per_day_pct"], -4.63, delta=0.005)
        self.assertEqual(r["n_model_deeper_per_day"], 5)
        self.assertAlmostEqual(r["mean_diff_per_day_pp"], -0.84, delta=0.005)

    def test_forward_2026_uses_the_two_reports(self):
        q = self.f["forward_2026"]["quarters"]
        self.assertEqual([x["q"] for x in q], ["2026Q1", "2026Q2"])
        self.assertEqual((q[0]["ore_rep"], q[1]["ore_rep"]), (15594.0, 16179.0))
        self.assertEqual((q[0]["cu_rep"], q[1]["cu_rep"]), (55.3, 58.4))
        for x in q:
            self.assertLess(abs(x["cu_err_model_pct"]), x["tol_cu_pct"])
        self.assertIn("отчёта ещё нет", self.f["forward_2026"]["note"])

    def test_recovery_refit_and_the_decision(self):
        r = self.f["recovery"]
        self.assertEqual(r["n_test"], 12)
        self.assertEqual(r["verdict"], "refit_worse")
        self.assertEqual(r["kept"], "2025fit")
        for v in r["variants"]:
            self.assertGreater(v["mae_refit"], r["mae_model_2025fit"])
        self.assertAlmostEqual(r["mae_model_all28"], read_json(DATA, "backtest_q.json")["summary"]["all"]["rec_mae_pp"], delta=0.01)

    def test_spread_matches_the_reported_one(self):
        s = self.f["spread"]
        self.assertLess(s["model_off_sd_dln"], 0.2 * s["reported_sd_dln"])
        self.assertAlmostEqual(s["model_on_sd_dln"], s["reported_sd_dln"], delta=0.12 * s["reported_sd_dln"])

    def test_2026_data_file(self):
        import csv
        with open(os.path.join(DATA, "kaz_quarterly_2026.csv"), encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual([r["quarter"] for r in rows], ["2026Q1", "2026Q2"])
        for r in rows:
            self.assertTrue(r["source_url"].startswith("https://www.kazminerals.com/app/uploads/2026/"))

    def test_influence_counts_add_up(self):
        i = read_json(DATA, "influence.json")
        from modules import params as mp
        from sim import params as sp
        self.assertEqual(i["summary"]["total"], len(sp.TABLE) + len(mp.PARAMS))
        s = i["summary"]
        classes = ("matters", "read_small", "read", "read_fixed", "not_read")
        self.assertEqual(sum(s[c] for c in classes), s["total"])
        self.assertEqual(sum(s[k]["n"] for k in ("assumption", "fact", "vendor", "analog", "project", "calc")), s["total"])
        for lab in ("assumption", "fact", "vendor", "analog", "project", "calc"):
            self.assertEqual(sum(s[lab][c] for c in classes), s[lab]["n"], lab)
        self.assertEqual(s["assumptions_total"], s["assumption"]["n"])
        self.assertGreater(s["not_read"], 0)
        self.assertEqual(len(i["rows"]), s["total"])
        # every label of every label is screened (the first screen moved only assumptions): the sourced rows are in the screen too
        self.assertGreater(s["fact"]["matters"] + s["fact"]["read_small"], 0)
        self.assertGreater(s["vendor"]["matters"] + s["vendor"]["read_small"], 0)
        self.assertEqual((i["version"], i["threshold_t_cu"], i["screen_n"]), (2, 0.10, 5))
        self.assertEqual(len(i["screen_seeds"]), i["screen_n"])
        self.assertEqual(s["screened"], s["matters"] + s["read_small"])
        # the file carries the labels of the tables as they are now (a relabel after the run goes through `influence --refresh-labels`)
        lab = {("model", p.key): p.label for p in sp.TABLE.values()}
        lab.update({("modules", p.key): p.label for p in mp.PARAMS})
        for r in i["rows"]:
            self.assertEqual(r["label"], lab[(r["table"], r["key"])], r["key"])
        for key in ("sens_an_tail_sigma", "sens_an_feed_sigma", "sens_an_conc_sigma", "sens_an_cycle_min"):
            self.assertEqual(sp.TABLE[key].label, "vendor", key)
            self.assertIn("vendor", [p.label for p in mp.PARAMS if p.key == key], key)
        # mechanism and refit family of 9.4
        self.assertEqual(i["mechanism"]["set_point_pct"], sp.TABLE["acs_tail_sp_pct"].value)
        self.assertEqual(set(i["recovery_family"]), {"blk_ascu_mean_pct", "flot_ktau0", "clean_r0_pct"})
        for k, v in i["recovery_family"].items():
            self.assertGreaterEqual(v["dev"], i["threshold_t_cu"], k)
            self.assertLess(v["dev_refit"], i["threshold_t_cu"], k)                # once the limit recovery is re-solved the row stops mattering
        self.assertEqual(sorted(s["refit_removes"]), sorted(i["recovery_family"]))
        self.assertEqual(read_json(STATIC, "influence.json"), i)                   # the page reads the copy

    def test_fidelity_page_renders_with_node(self):
        if not shutil.which("node"):
            self.skipTest("node is not installed")
        js = (
            "const fs=require('fs');globalThis.window=globalThis;globalThis.AKT={};"
            "eval(fs.readFileSync(process.argv[1]+'/fidelity.js','utf8'));"
            "AKT.fidelity.data=JSON.parse(fs.readFileSync(process.argv[1]+'/fidelity.json','utf8'));"
            "AKT.fidelity.infl=JSON.parse(fs.readFileSync(process.argv[1]+'/influence.json','utf8'));"
            "const a=AKT.fidelity.renderFidelity(),b=AKT.fidelity.renderInfluence();"
            "console.log(JSON.stringify([a.length,b.length,a.includes('2026Q1'),a.includes('2023Q4-S1'),a.includes('NaN'),b.includes('NaN'),b.includes('undefined'),a.includes('undefined')]));")
        r = subprocess.run(["node", "-e", js, STATIC], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        la, lb, q1, e1, nan1, nan2, und1, und2 = json.loads(r.stdout)
        self.assertTrue(la > 2000 and lb > 500 and q1 and e1)
        self.assertFalse(nan1 or nan2 or und1 or und2)


class FidelityCodeTest(unittest.TestCase):
    def test_least_squares_is_exact_on_a_line(self):
        a, b = fidelity._lsq([-1.0, 0.0, 1.0, 2.0], [0.5, 1.0, 1.5, 2.0])
        self.assertAlmostEqual(a, 1.0)
        self.assertAlmostEqual(b, 0.5)

    def test_2026_reports_load_with_their_page(self):
        rows = fidelity.load_2026()
        self.assertEqual([r["q"] for r in rows], ["2026Q1", "2026Q2"])
        self.assertTrue(all(r["page"].startswith("PDF p.4") for r in rows))
        self.assertEqual((rows[0]["grade_pct"], rows[1]["grade_pct"]), (0.41, 0.41))

    def test_events_name_the_five_reported_relines(self):
        from sim import backtest as bt
        by = {r["q"]: r for r in bt.load_quarters()}
        self.assertEqual(len(fidelity.EVENTS), 5)
        for eid, q, line, ref, month, day, what in fidelity.EVENTS:
            self.assertIn(q, by)
            self.assertIn(ref, by)
            self.assertTrue(by[q]["ore1_kt" if line == 1 else "ore2_kt"] < by[ref]["ore1_kt" if line == 1 else "ore2_kt"], eid)   # the reported drop
            self.assertTrue(1 <= month <= 12 and 1 <= day <= 28)

    def test_the_spread_check_switches_the_plan_on(self):
        s = fidelity.quarterly_spread(default(), n_seeds=2, with_recovery=False)
        self.assertLess(s["model_off_sd_dln"], 0.012)
        self.assertGreater(s["model_on_sd_dln"], 3 * s["model_off_sd_dln"])
        self.assertAlmostEqual(s["reported_n"], 27)


class PassportTest(unittest.TestCase):
    """setup/things.json after gen_site: the haul passports follow the calculation."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "setup", "things.json"), encoding="utf-8") as f:
            cls.things = {t["name"]: t for t in json.load(f)["things"]}
        with open(os.path.join(ROOT, "setup", "things.json"), encoding="utf-8") as f:
            cls.sources = json.load(f)["sources"]

    def test_roads_carry_the_measured_length(self):
        for rid, key in (("ramp-1", "fleet_ramp_km_1"), ("ramp-2", "fleet_ramp_km_2"), ("road-dump", "fleet_waste_km")):
            item = self.things[rid]["passport"]["length"]
            self.assertEqual(item[1], "km")
            self.assertAlmostEqual(item[0], TABLE[key].value, places=3)
            self.assertEqual(item[2], "stand_map")
            self.assertIn("расчёт по карте", item[3])
        self.assertEqual(self.sources["stand_map"]["label"], "calc")

    def test_trucks_carry_the_calculated_cycle_and_the_report_payload(self):
        t793 = next(t for t in self.things.values() if t.get("type") == "truck" and t["passport"]["model"][0] == "CAT 793")
        self.assertEqual(t793["passport"]["payload_t"][0], 236)
        self.assertEqual(t793["passport"]["payload_t"][2], "kaz_ar2020")
        self.assertEqual(self.sources["kaz_ar2020"]["label"], "fact")
        self.assertIn("61", self.sources["kaz_ar2020"]["page"])
        cyc = t793["passport"]["cycle_min"]
        self.assertEqual(cyc[2], "calc")
        self.assertAlmostEqual(cyc[0], haul.cycle_min(default(), 1 if t793["passport"]["duty"][0].endswith("1") else 2), delta=1.1)
        self.assertEqual(self.sources["specalog793d"]["label"], "vendor")


class RelineCheckTest(unittest.TestCase):
    """aktogay/scripts/reline_check.py (VALIDATION 6.3, 6.8): what the reports can say about the cost of a SAG reline."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import reline_check
        cls.rc = reline_check
        cls.r = reline_check.compute()

    def test_the_regression_on_the_named_events_gives_minus_4_22_percent(self):
        x = self.r["c7"]["named_6_events"]
        self.assertAlmostEqual(x["effect_pct"], -4.22, delta=0.005)
        self.assertAlmostEqual(x["t_ci_pct"][0], -7.76, delta=0.005)
        self.assertAlmostEqual(x["t_ci_pct"][1], -0.69, delta=0.005)
        self.assertAlmostEqual(x["bootstrap_ci_pct"][0], -7.24, delta=0.01)
        self.assertAlmostEqual(x["bootstrap_ci_pct"][1], -1.31, delta=0.01)
        self.assertEqual((x["n"], x["df"]), (24, 19))

    def test_the_labelling_of_the_quarters_moves_the_effect_between_minus_3_5_and_minus_6_2(self):
        c = self.r["c7"]
        got = {k: round(v["effect_pct"], 2) for k, v in c.items()}
        self.assertEqual(got, {"named_6_events": -4.22, "docs_5_events": -3.50, "named_plus_dec2025_as_reline": -5.68,
                               "named_plus_other_maintenance": -5.15, "named_plus_other_maintenance_and_dec2025_as_maintenance": -6.22})
        self.assertGreater(c["docs_5_events"]["t_ci_pct"][1], 0.0)                 # the five events of the docs: the interval reaches zero

    def test_per_day_drop_of_the_five_events_and_the_model_against_it(self):
        c = self.r["c6"]
        self.assertAlmostEqual(c["mean_per_day_pct"], -4.63, delta=0.005)
        self.assertAlmostEqual(c["mean_raw_pct"], -4.85, delta=0.005)
        self.assertAlmostEqual(c["mean_model_pct"], -5.47, delta=0.005)
        self.assertEqual(c["model_deeper_in"], 5)
        self.assertAlmostEqual(c["mean_model_minus_report_pp"], -0.84, delta=0.005)
        ev = {e["id"]: e for e in c["events"]}
        self.assertEqual(ev["2025Q1-S1"]["days"], [92, 90])                          # the quarters differ in length: per day, not per quarter

    def test_line_hours_and_noise(self):
        h = self.r["c8"]
        self.assertAlmostEqual(h["named_hours"], 93.0, delta=0.6)
        self.assertAlmostEqual(h["named_hours_ci"][0], 29.0, delta=0.6)
        self.assertAlmostEqual(h["named_hours_ci"][1], 159.0, delta=0.6)
        self.assertAlmostEqual(h["model_hours"], 120.0, delta=0.6)
        self.assertAlmostEqual(h["line_hour_cu_t"], 13.67, delta=0.005)
        n = self.r["c11"]
        self.assertAlmostEqual(n["sd_all_pct"], 5.44, delta=0.005)
        self.assertAlmostEqual(n["sd_clean_pct"], 4.92, delta=0.005)
        self.assertEqual((n["n_all"], n["n_clean"]), (22, 11))

    def test_the_calendar_has_the_first_quarter_2024_reline_as_a_fact(self):
        from sim.params import RELINE_CALENDAR
        ev = next(r for r in RELINE_CALENDAR if (r.line, r.year, r.month) == (1, 2024, 3))
        self.assertEqual((ev.label, ev.kind), ("fact", "reline"))
        self.assertIn("23119", ev.source)                                           # the Q1 2024 production report (A11)
        self.assertTrue(ev.day_assumed)

    def test_the_script_reads_nothing_but_the_stored_files(self):
        r = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "scripts", "reline_check.py")], capture_output=True, text=True,
                           encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("-4.22 % t-CI [-7.76; -0.69]", r.stdout)


class RecoveryBaselinesTest(unittest.TestCase):
    """aktogay/scripts/rec_baselines.py (VALIDATION 6.5, 6.9): every baseline against the model."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import rec_baselines
        cls.rb = rec_baselines
        cls.r = rec_baselines.compute()

    def test_quarters(self):
        c = self.r["c17"]
        q8, q12, q28 = c["quarters_2023_2024"], c["quarters_2023_2025"], c["quarters_2018_2024"]
        for got, want in ((q8["model"], 0.70), (q8["const_87_2_hindsight"], 0.76), (q8["last_report"], 0.91), (q8["mean_last_4_reports"], 0.55),
                           (q8["mean_all_earlier_reports"], 1.11), (q8["period_mean_hindsight"], 0.49),
                           (q12["model"], 0.81), (q12["const_87_2_hindsight"], 0.84), (q12["last_report"], 1.17), (q12["mean_last_4_reports"], 0.80),
                           (q28["model"], 1.75), (q28["const_87_2_hindsight"], 1.40), (q28["last_report"], 1.82), (q28["mean_last_4_reports"], 1.42)):
            self.assertAlmostEqual(got, want, delta=0.006)
        self.assertEqual((q8["n"], q12["n"], q28["n"]), (8, 12, 28))
        self.assertGreater(q28["model"], q28["const_87_2_hindsight"])                 # on 28 quarters the formula loses to the constant

    def test_half_years_and_years_the_model_beats_the_constant_but_not_every_baseline(self):
        c = self.r["c17"]
        h, y = c["half_years_2023_2024"], c["years_2023_2024"]
        self.assertAlmostEqual(h["model"], 0.33, delta=0.006)
        self.assertAlmostEqual(h["const_87_2_hindsight"], 0.61, delta=0.006)
        self.assertLess(h["previous_half"], h["model"])                               # it loses to the previous half-year
        self.assertLess(h["const_2025H1_hindsight"], h["model"])
        self.assertLess(h["period_mean_hindsight"], h["model"])
        self.assertAlmostEqual(y["model"], 0.31, delta=0.006)
        self.assertLess(y["previous_year"], y["model"])
        self.assertLess(y["period_mean_hindsight"], y["model"])
        self.assertEqual((h["n"], y["n"]), (4, 2))

    def test_spread_zigzag_and_2026(self):
        s = self.r["c14"]
        self.assertAlmostEqual(s["two_plants_2023_2025"]["mean"], 87.59, delta=0.005)
        self.assertAlmostEqual(s["two_plants_2023_2025"]["sd"], 0.95, delta=0.005)
        self.assertAlmostEqual(s["check_28_2018_2024"]["sd"], 1.99, delta=0.005)
        self.assertAlmostEqual(s["corr_grade_rec_two_plants"], 0.22, delta=0.005)
        z = self.r["c15"]
        self.assertEqual(z["turns_of"], [10, 10])
        self.assertAlmostEqual(z["all_turns_probability"], 0.0113, delta=0.00005)
        self.assertEqual((z["turns_ore"], z["turns_grade"], z["turns_cu"]), (3, 0, 4))
        self.assertAlmostEqual(z["permutation_p"], 0.075, delta=0.01)
        f = self.r["c20"]
        self.assertAlmostEqual(f["2026Q1"]["implied"], 86.49, delta=0.005)
        self.assertAlmostEqual(f["2026Q2"]["implied"], 88.04, delta=0.005)
        self.assertAlmostEqual(f["H1"]["implied"], 87.28, delta=0.005)
        self.assertAlmostEqual(f["2026Q1"]["band"][1] - f["2026Q1"]["implied"], 1.06, delta=0.02)      # rounding of the printed grade: +-1.06 pp


if __name__ == "__main__":
    unittest.main()
