"""Acceptance tests of sim.utilities (power, water, money)."""
import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # aktogay/: packages sim, tests
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sim import utilities as ut
from sim.state import PowerLoads, PowerState, ShedPlan, WaterFlows, WaterState
from tests.support import needs_impl, prm


def base_loads():
    return PowerLoads(sag_kw={1: 26000.0, 2: 26000.0},
                      ball_kw={"ball-1a": 20500.0, "ball-1b": 20500.0, "ball-2a": 20500.0, "ball-2b": 20500.0},
                      crusher_kw={1: 750.0, 2: 750.0}, conveyor_kw={1: 3640.0, 2: 3640.0})


def c2_relief(p):
    """Relief per SAON candidate as the plant computes it (design section 7, C2).

    A shed ball mill frees its grid power; the line rule then halves the
    line feed (one ball mill keeps P80 at half the rate), so SAG power
    falls to E_SAG x Q / 2.
    """
    q = p["cal_line_tph"]
    sag_cut_shaft_mw = p["sag_power_sp_mw"] - p["sag_e_base_kwh_t"] * q / 2.0 / 1000.0
    ball = ut.to_grid_mw(p["ball_power_mw"], p) + ut.to_grid_mw(sag_cut_shaft_mw, p)
    return {"ball-2b": ball, "other_cat2": p["pow_shed_other_mw"], "ball-1b": ball}


def steady_flows(p, grade_pct, rec_pct, lines=2):
    """Water inputs for both lines at the base rate from the flotation numbers."""
    q = lines * p["cal_line_tph"]
    cake = q * grade_pct / 100.0 * rec_pct / 100.0 / p["flot_conc0_pct"]
    fs, us = p["thick_feed_solids_pct"], p["thick_uf_solids_pct"]
    overflow = cake * ((100.0 - fs) / fs - (100.0 - us) / us)
    return WaterFlows(ore_tph=q, tails_tph=q - cake, cake_tph=cake, cake_moist_pct=p["filt_moist_pct"],
                      thick_overflow_m3h=overflow)


class TestPower(unittest.TestCase):
    def setUp(self):
        self.p = prm()

    @needs_impl
    def test_base_balance(self):
        pw = PowerState(grid_limit_mw=300.0)
        ut.power_balance(pw, base_loads(), self.p)
        self.assertAlmostEqual(pw.grinding_shaft_mw, 134.0, delta=0.01)
        self.assertAlmostEqual(pw.grinding_mw, 139.58, delta=0.01)
        self.assertAlmostEqual(pw.cc_mw, 8.78, delta=0.01)
        self.assertAlmostEqual(self.p["pow_other_mw"], 54.56, delta=0.01)     # site part, table value from 2024
        self.assertAlmostEqual(pw.line_aux_mw, 2 * self.p["pow_line_aux_mw"], delta=1e-9)
        self.assertAlmostEqual(pw.other_mw, 54.56 + 57.0, delta=0.01)
        self.assertAlmostEqual(pw.site_mw, 260.0, delta=0.1)
        self.assertAlmostEqual(pw.headroom_mw, 40.0, delta=0.1)
        self.assertEqual(pw.state, "NORMAL")

    @needs_impl
    def test_line_part_stops_with_the_line(self):
        """Flotation, pebble crushing, regrind and pumps stop with their line (SAG draws 0)."""
        p = self.p
        pw = PowerState(grid_limit_mw=300.0)
        loads = base_loads()
        loads.sag_kw[2] = 0.0
        for b in ("ball-2a", "ball-2b"):
            loads.ball_kw[b] = 0.0
        loads.crusher_kw[2] = loads.conveyor_kw[2] = 0.0
        ut.power_balance(pw, loads, p)
        self.assertAlmostEqual(pw.line_aux_mw, p["pow_line_aux_mw"], delta=1e-9)
        self.assertAlmostEqual(pw.other_mw, p["pow_other_mw"] + p["pow_line_aux_mw"], delta=1e-9)
        full = PowerState(grid_limit_mw=300.0)
        ut.power_balance(full, base_loads(), p)
        line_mw = (26.0 + 41.0) / p["pow_motor_eff"] + 0.75 + 3.64 + p["pow_line_aux_mw"]
        self.assertAlmostEqual(full.site_mw - pw.site_mw, line_mw, delta=1e-6)
        # both lines down: only the site part is left
        ut.power_balance(pw, PowerLoads(sag_kw={1: 0.0, 2: 0.0}), p)
        self.assertAlmostEqual(pw.site_mw, p["pow_other_mw"], delta=1e-9)

    @needs_impl
    def test_c2_shed(self):
        relief = {"ball-2b": 21.35 + 13.55, "other_cat2": 15.0, "ball-1b": 21.35 + 13.55}
        plan = ut.shed_plan(260.0, 218.0, relief, self.p)
        self.assertEqual(plan.balls_off, ["ball-2b"])
        self.assertAlmostEqual(plan.other_shed_mw, 15.0)
        self.assertEqual(ut.shed_plan(260.0, 300.0, relief, self.p).balls_off, [])

    @needs_impl
    def test_limited_state(self):
        pw = PowerState(grid_limit_mw=218.0, shed=["ball-2b", "other_cat2"])
        loads = base_loads()
        loads.ball_kw["ball-2b"] = 0.0
        ut.power_balance(pw, loads, self.p)
        self.assertEqual(pw.state, "LIMITED")
        self.assertAlmostEqual(pw.other_mw, self.p["pow_other_mw"] - 15.0 + pw.line_aux_mw, delta=1e-6)
        self.assertGreater(pw.shed_mw, 36.0)

    def test_saon_order(self):
        self.assertEqual(ut.SAON_ORDER, ("ball-2b", "other_cat2", "ball-1b"))

    def test_c2_chain_200_mw(self):
        """260 -> 210 MW, headroom 8 MW, 36 MW shed (design section 7, C2: 250 -> 200 MW at a 210 MW
        limit before the line part of the other load was split out; limit now 218 MW)."""
        p = self.p
        pw = PowerState(grid_limit_mw=p["pow_grid_limit_mw"])
        ut.power_balance(pw, base_loads(), p)
        relief = c2_relief(p)
        self.assertAlmostEqual(relief["ball-2b"], 21.35 + 13.55, delta=0.1)
        plan = ut.shed_plan(pw.site_mw, p["pow_c2_limit_mw"], relief, p)
        self.assertEqual(plan.balls_off, ["ball-2b"])
        self.assertEqual(plan.sag_cap_kw, {})
        self.assertEqual(ut.shed_names(plan), ["ball-2b", "other_cat2"])

        loads = base_loads()
        loads.sag_kw[2] = p["sag_e_base_kwh_t"] * p["cal_line_tph"] / 2.0
        pw.grid_limit_mw = p["pow_c2_limit_mw"]
        pw.shed = ut.shed_names(plan)
        ut.power_balance(pw, loads, p)          # ball-2b still listed at 20.5 MW: ignored
        self.assertAlmostEqual(pw.site_mw, 210.0, delta=0.5)
        self.assertAlmostEqual(pw.headroom_mw, 8.0, delta=0.5)
        self.assertAlmostEqual(pw.shed_mw, 36.35, delta=0.05)
        self.assertEqual(pw.state, "LIMITED")
        self.assertGreaterEqual(pw.headroom_mw, p["pow_call_use_mw"])       # the call still fits
        # After the call (+5 MW to SAG-2) ball-2b cannot come back: 215 + 21.4 > 218.
        after_call = pw.site_mw + p["pow_call_use_mw"]
        self.assertGreater(after_call + ut.to_grid_mw(p["ball_power_mw"], p), p["pow_c2_limit_mw"])
        self.assertIn("= 210.", ut.power_parts_text(pw))

    def test_shed_ball_draws_nothing(self):
        pw = PowerState(grid_limit_mw=300.0, shed=["ball-1b"])
        ut.power_balance(pw, base_loads(), self.p)
        self.assertAlmostEqual(pw.grinding_shaft_mw, 134.0 - 20.5, delta=1e-9)
        self.assertAlmostEqual(pw.shed_mw, 20.5 / 0.96, delta=1e-9)
        self.assertAlmostEqual(pw.other_mw, self.p["pow_other_mw"] + 2 * self.p["pow_line_aux_mw"], delta=1e-9)
        self.assertEqual(pw.state, "LIMITED")

    def test_unset_limit_and_overload(self):
        p = self.p
        pw = PowerState()
        ut.power_balance(pw, base_loads(), p)
        self.assertEqual(pw.grid_limit_mw, p["pow_grid_limit_mw"])
        self.assertEqual(pw.state, "NORMAL")
        # Normal limit, no shedding, but the load is above it: still LIMITED.
        p2 = p.copy(pow_other_mw=115.0, pow_grid_limit_mw=250.0)
        pw2 = PowerState(grid_limit_mw=p2["pow_grid_limit_mw"])
        ut.power_balance(pw2, base_loads(), p2)
        self.assertEqual(pw2.shed, [])
        self.assertLess(pw2.headroom_mw, 0.0)
        self.assertEqual(pw2.state, "LIMITED")

    def test_parts_add_up(self):
        pw = PowerState(grid_limit_mw=300.0)
        loads = base_loads()
        loads.crusher_kw[1] = 0.0
        loads.conveyor_kw[1] = 0.0
        ut.power_balance(pw, loads, self.p)
        self.assertAlmostEqual(pw.site_mw, pw.grinding_mw + pw.cc_mw + pw.other_mw, places=9)
        self.assertAlmostEqual(pw.cc_mw, 4.39, places=9)
        self.assertAlmostEqual(pw.grinding_mw * self.p["pow_motor_eff"], pw.grinding_shaft_mw, places=9)

    def test_unknown_shed_name(self):
        with self.assertRaises(ValueError):
            ut.power_balance(PowerState(grid_limit_mw=300.0, shed=["sag-1"]), base_loads(), self.p)

    def test_shed_plan_depths(self):
        p = self.p
        relief = c2_relief(p)
        site = 250.36
        deep = ut.shed_plan(site, 180.0, relief, p)
        self.assertEqual(deep.balls_off, ["ball-2b", "ball-1b"])
        self.assertAlmostEqual(deep.other_shed_mw, 15.0)
        self.assertEqual(ut.shed_names(deep), ["ball-2b", "other_cat2", "ball-1b"])
        shallow = ut.shed_plan(site, 240.0, relief, p)
        self.assertEqual(shallow.balls_off, ["ball-2b"])
        self.assertEqual(shallow.other_shed_mw, 0.0)
        self.assertEqual(ut.shed_names(shallow), ["ball-2b"])
        exact = ut.shed_plan(site, site, relief, p)
        self.assertEqual((exact.balls_off, exact.other_shed_mw), ([], 0.0))
        # Whole list is not enough: everything shed, no SAG cap from this function.
        worst = ut.shed_plan(site, 100.0, relief, p)
        self.assertEqual(ut.shed_names(worst), list(ut.SAON_ORDER))
        self.assertEqual(worst.sag_cap_kw, {})

    def test_shed_plan_skips(self):
        p = self.p
        relief = c2_relief(p)
        relief.pop("ball-2b")                    # line 2 not on the list
        plan = ut.shed_plan(250.4, 210.0, relief, p)
        self.assertEqual(plan.balls_off, ["ball-1b"])
        self.assertAlmostEqual(plan.other_shed_mw, 15.0)
        relief = c2_relief(p)
        relief["ball-2b"] = 0.0                  # mill already stopped
        plan = ut.shed_plan(250.4, 230.0, relief, p)
        self.assertEqual(plan.balls_off, ["ball-1b"])

    def test_shed_names_extra_ball(self):
        plan = ShedPlan(balls_off=["ball-1b", "ball-2a"], other_shed_mw=0.0)
        self.assertEqual(ut.shed_names(plan), ["ball-1b", "ball-2a"])


class TestWater(unittest.TestCase):
    def setUp(self):
        self.p = prm()

    @needs_impl
    def test_steady_day(self):
        p = self.p
        w = WaterState(pond_m3=p["pond_m3_0"])
        cake = 2 * 56.7
        fl = WaterFlows(ore_tph=7705.7, tails_tph=7705.7 - cake, cake_tph=cake, cake_moist_pct=8.0,
                        thick_overflow_m3h=2 * 132.3)
        for _ in range(144):
            ut.water_step(w, fl, 10.0, p, 0.0)
        self.assertAlmostEqual(w.intake_m3h / 7705.7, 0.567, delta=0.02)
        self.assertAlmostEqual(w.recycle_m3h / 7705.7, 2.7, delta=0.2)
        self.assertLess(abs(w.residual_pct), 0.5)
        self.assertTrue(p["pond_lo_m3"] <= w.pond_m3 <= p["pond_hi_m3"])
        self.assertEqual(w.state, "NORMAL")

    @needs_impl
    def test_piezo(self):
        p = self.p
        w = WaterState(pond_m3=p["pond_m3_0"] + 0.25e6)
        ut.water_step(w, WaterFlows(), 1.0, p, 0.0)
        self.assertAlmostEqual(w.piezo_kpa, 130.0, delta=0.5)

    def test_flows_close(self):
        p = self.p
        fl = steady_flows(p, p["tgt_2025_grade_pct"], p["tgt_2025_rec_pct"])
        w = WaterState(pond_m3=p["pond_m3_0"])
        ut.water_step(w, fl, 1.0, p, 0.0)
        self.assertAlmostEqual(w.proc_m3h, w.intake_m3h + w.recycle_m3h, places=6)
        self.assertAlmostEqual(w.recycle_m3h, w.pond_return_m3h + w.thick_overflow_m3h, places=6)
        self.assertAlmostEqual(w.tails_loss_m3h / fl.tails_tph, 0.3137, delta=1e-4)   # pore water, settled tails
        self.assertAlmostEqual(w.conc_moist_m3h, fl.cake_tph * 8.0 / 92.0, places=9)
        self.assertAlmostEqual(w.evap_m3h, p["water_evap_m3h"], places=9)
        self.assertAlmostEqual(w.residual_pct, 0.0, places=9)

    def test_regulator_time_constant(self):
        p = self.p
        mid = 0.5 * (p["pond_lo_m3"] + p["pond_hi_m3"])
        w = WaterState(pond_m3=mid + 0.2e6)
        fl = steady_flows(p, p["tgt_2025_grade_pct"], p["tgt_2025_rec_pct"])
        steps = int(p["pond_reg_h"] * 6)         # one time constant at 10 min
        for _ in range(steps):
            ut.water_step(w, fl, 10.0, p, 0.0)
        self.assertAlmostEqual((w.pond_m3 - mid) / 0.2e6, math.exp(-1.0), delta=0.01)
        self.assertEqual(w.state, "NORMAL")
        w_lo = WaterState(pond_m3=0.9e6)
        for _ in range(steps * 4):
            ut.water_step(w_lo, fl, 10.0, p, 0.0)
        self.assertTrue(p["pond_lo_m3"] <= w_lo.pond_m3 <= p["pond_hi_m3"])
        self.assertEqual(w_lo.state, "NORMAL")

    def test_water_2024_table_value(self):
        """Year 2024 at the base rate: the table evaporation (calc from 2024) gives the 2024 intake."""
        p = self.p
        fl = steady_flows(p, p["tgt_2024_grade_pct"], p["tgt_2024_rec_pct"])
        hours_run = p["tgt_2024_ore_mt"] * 1e6 / fl.ore_tph
        hours_year = 366 * 24
        frac = hours_run / hours_year
        w = WaterState(pond_m3=p["pond_m3_0"])
        pond0 = w.pond_m3
        intake = out = 0.0
        stop = WaterFlows()
        for k in range(hours_year):
            run = math.floor((k + 1) * frac) > math.floor(k * frac)
            ut.water_step(w, fl if run else stop, 60.0, p, 0.0)
            intake += w.intake_m3h
            out += w.tails_loss_m3h + w.conc_moist_m3h + w.evap_m3h
            self.assertNotEqual(w.state, "ALARM")
        self.assertAlmostEqual(intake, out + (w.pond_m3 - pond0), delta=1e-6 * intake)
        dev = intake / 1e6 / p["tgt_2024_water_mm3"] - 1.0
        self.assertLess(abs(dev), p["tol_water_frac"])

    def test_stop_drains_pond(self):
        p = self.p
        w = WaterState(pond_m3=p["pond_lo_m3"] + 1000.0)
        ut.water_step(w, WaterFlows(), 120.0, p, 0.0)
        self.assertEqual(w.intake_m3h, 0.0)
        self.assertEqual(w.recycle_m3h, 0.0)
        self.assertAlmostEqual(w.pond_m3, p["pond_lo_m3"] + 1000.0 - 2.0 * p["water_evap_m3h"], places=6)
        self.assertEqual(w.state, "LOW")

    def test_pond_never_negative(self):
        p = self.p
        w = WaterState(pond_m3=100.0)
        ut.water_step(w, WaterFlows(), 60.0, p, 0.0)
        self.assertEqual(w.pond_m3, 0.0)
        self.assertAlmostEqual(w.evap_m3h, 100.0, places=9)
        ut.water_step(w, WaterFlows(), 60.0, p, 0.0)
        self.assertEqual((w.pond_m3, w.evap_m3h), (0.0, 0.0))
        # Empty pond and a running plant: fresh water replaces the missing return.
        fl = steady_flows(p, p["tgt_2025_grade_pct"], p["tgt_2025_rec_pct"])
        w = WaterState(pond_m3=0.0)
        ut.water_step(w, fl, 10.0, p, 0.0)
        self.assertGreaterEqual(w.pond_m3, 0.0)
        self.assertAlmostEqual(w.residual_pct, 0.0, places=9)
        self.assertGreater(w.intake_m3h, p["water_tails_m3_t"] * fl.tails_tph)

    def test_overflow_above_process(self):
        p = self.p
        w = WaterState(pond_m3=p["pond_m3_0"])
        ut.water_step(w, WaterFlows(thick_overflow_m3h=200.0), 10.0, p, 0.0)
        self.assertEqual(w.intake_m3h, 0.0)
        self.assertEqual(w.recycle_m3h, 0.0)
        self.assertAlmostEqual(w.pond_in_m3h, 200.0, places=9)

    def test_alarm_and_noise(self):
        p = self.p
        over = (p["pond_piezo_sp_kpa"] - p["pond_piezo_kpa0"]) / p["pond_piezo_kpa_mm3"] * 1e6
        w = WaterState(pond_m3=p["pond_m3_0"] + over + 5e4)
        ut.water_step(w, WaterFlows(), 1.0, p, 0.0)
        self.assertEqual(w.state, "ALARM")
        a = WaterState(pond_m3=p["pond_m3_0"])
        b = WaterState(pond_m3=p["pond_m3_0"])
        ut.water_step(a, WaterFlows(), 1.0, p, 0.0)
        ut.water_step(b, WaterFlows(), 1.0, p, 2.0)
        self.assertAlmostEqual(b.piezo_kpa - a.piezo_kpa, 2.0 * p["pond_piezo_noise_kpa"], places=9)

    def test_bad_inputs(self):
        p = self.p
        with self.assertRaises(ValueError):
            ut.water_step(WaterState(), WaterFlows(cake_tph=1.0, cake_moist_pct=100.0), 1.0, p, 0.0)
        with self.assertRaises(ValueError):
            ut.water_step(WaterState(), WaterFlows(), -1.0, p, 0.0)

    def test_zero_dt(self):
        p = self.p
        fl = steady_flows(p, p["tgt_2025_grade_pct"], p["tgt_2025_rec_pct"])
        w = WaterState(pond_m3=p["pond_m3_0"])
        ut.water_step(w, fl, 0.0, p, 0.0)
        self.assertEqual(w.pond_m3, p["pond_m3_0"])
        self.assertGreater(w.intake_m3h, 0.0)

    def test_regulator_floor_returns_what_the_fresh_water_cap_cannot_supply(self):
        """VALIDATION 9.4: a pond at the bottom of its band (1.0 Mm3 of 1.0-1.5) no longer holds the return water back until the plant
        is short of process water: while the pond has water the return is at least proc - overflow_used - water_intake_cap_m3h."""
        p = self.p
        fl = steady_flows(p, p["tgt_2025_grade_pct"], p["tgt_2025_rec_pct"])
        proc = p["water_proc_m3_t"] * fl.ore_tph
        cap = proc - min(fl.thick_overflow_m3h, proc)
        floor = cap - p["water_intake_cap_m3h"]
        self.assertGreater(floor, 0.0)                              # the cap binds at the base rate: the case the floor is for
        for pond in (1.0e6, 1.02e6, 1.1e6, p["pond_m3_0"]):
            w = WaterState(pond_m3=pond)
            ut.water_step(w, fl, 10.0, p, 0.0)
            self.assertGreaterEqual(w.pond_return_m3h, floor - 1e-9, pond)
            self.assertEqual(w.short_m3h, 0.0, pond)
            self.assertNotEqual(w.state, "SHORT", pond)
        w = WaterState(pond_m3=1.0e6)
        for _ in range(24):
            ut.water_step(w, fl, 10.0, p, 0.0)
        self.assertGreater(w.pond_m3, 1.0e6)                        # the pond rises: net inflow positive at the base rate
        self.assertEqual(w.state, "NORMAL")
        self.assertLess(abs(w.residual_pct), 1e-6)

    def test_the_floor_is_limited_by_the_water_in_the_pond(self):
        p = self.p
        fl = steady_flows(p, p["tgt_2025_grade_pct"], p["tgt_2025_rec_pct"])
        w = WaterState(pond_m3=0.0)                                 # an empty pond has nothing to return: fresh water at its cap, ore cut
        ut.water_step(w, fl, 10.0, p, 0.0)
        self.assertGreater(w.short_m3h, 0.0)
        self.assertEqual(w.state, "SHORT")
        w = WaterState(pond_m3=3000.0)                              # a few thousand m3 last minutes, not hours: no more than the pond holds
        ut.water_step(w, fl, 10.0, p, 0.0)
        self.assertLessEqual(w.pond_return_m3h, w.pond_in_m3h + 3000.0 * 6.0 + 1e-6)
        self.assertGreaterEqual(w.pond_m3, 0.0)

    def test_rounding_is_not_a_deficit(self):
        """A short below 1e-6 m3/h is the rounding of the sums (the floor lands exactly on the cap): never SHORT."""
        p = self.p
        fl = steady_flows(p, p["tgt_2025_grade_pct"], p["tgt_2025_rec_pct"])
        for k in range(60):
            pond = 1.0e6 + 7919.0 * k
            for scale in (1.0, 0.97, 1.0 + 1e-9):
                f = WaterFlows(ore_tph=fl.ore_tph * scale, tails_tph=fl.tails_tph * scale, cake_tph=fl.cake_tph * scale,
                               cake_moist_pct=fl.cake_moist_pct, thick_overflow_m3h=fl.thick_overflow_m3h * scale)
                w = WaterState(pond_m3=pond)
                ut.water_step(w, f, 1.0, p, 0.0)
                self.assertTrue(w.short_m3h == 0.0 or w.short_m3h >= 1e-6, (pond, scale, w.short_m3h))
                self.assertEqual(w.state == "SHORT", w.short_m3h > 0.0)

    def test_scenario_water_results_do_not_move(self):
        """The scenarios of the catalog keep their results (verify.json): winter 0, water -3.47 t Cu, crusher:1 -0.74, reline:1 -145.25 (seed 42, one run; the file is recomputed by test_doc_claims)."""
        import json
        with open(os.path.join(ROOT, "web", "static", "verify.json"), encoding="utf-8") as f:
            runs = {"%s@%d" % (r["id"], r["kip"]): r for r in json.load(f)["runs"]}
        self.assertAlmostEqual(runs["water@1"]["diff"]["fact"]["cu_t"], -3.47, places=2)
        self.assertAlmostEqual(runs["winter@1"]["diff"]["fact"]["cu_t"], 0.0, places=2)
        self.assertAlmostEqual(runs["crusher:1@1"]["diff"]["fact"]["cu_t"], -0.74, places=2)
        self.assertAlmostEqual(runs["reline:1@1"]["diff"]["fact"]["cu_t"], -145.25, places=2)


class TestPondAtThePlantLevel(unittest.TestCase):
    """The plant, not only the water function: 1 Mm3 in the pond (the bottom of the band) must not cut the ore."""

    def test_a_pond_at_the_band_floor_cuts_nothing(self):
        from sim.params import default
        from sim.plant import Plant
        pl = Plant(default().copy(pond_m3_0=1.0e6), 42, mode="scenario")
        pl.warmup()
        t0 = pl.t_min
        pl.run_until(t0 + 120.0)
        w = pl.state.water
        self.assertEqual(w.cut_tph, 0.0)
        self.assertEqual(w.short_m3h, 0.0)
        self.assertNotEqual(w.state, "SHORT")
        self.assertGreater(w.pond_m3, 1.0e6)
        for ln in pl.state.lines:
            self.assertAlmostEqual(ln.sag.feed_tph, 3853.0, delta=1.0)


class TestMoney(unittest.TestCase):
    @needs_impl
    def test_values(self):
        p = prm()
        self.assertAlmostEqual(ut.cu_value_usd(1.0, p), 14539 * 0.955, places=6)
        self.assertAlmostEqual(ut.energy_cost_usd(1.0, p), 32.0, places=6)
        self.assertAlmostEqual(ut.co2_t(10.0, p), 10.0 * p["econ_co2_t_mwh"], places=9)
        self.assertAlmostEqual(ut.co2_t(10.0, p), 6.4, places=9)       # 0.64 t/MWh (KAZ Scope 2 / electricity)
        self.assertAlmostEqual(ut.value_usd(1.0, 1.0, 100.0, p), 14539 * 0.955 - 32.0 - 30.0, places=6)

    def test_overrides_and_scale(self):
        p = prm(econ_cu_price_usd_t=10000.0, econ_kzt_per_usd=450.0, econ_water_usd_m3=1.0)
        self.assertAlmostEqual(ut.cu_value_usd(2.0, p), 2.0 * 0.955 * 10000.0, places=6)
        self.assertAlmostEqual(ut.energy_cost_usd(10.0, p), 10.0 * 1000.0 * 16.0 / 450.0, places=6)
        self.assertAlmostEqual(ut.water_cost_usd(5.0, p), 5.0, places=9)

    def test_line_hour(self):
        """One base line hour: 13.7 t Cu ~ 190 kUSD (design section 7)."""
        p = prm()
        q = p["cal_line_tph"]
        cu = q * p["tgt_2025_grade_pct"] / 100.0 * p["tgt_2025_rec_pct"] / 100.0
        self.assertAlmostEqual(cu, 13.7, delta=0.1)
        self.assertAlmostEqual(ut.cu_value_usd(cu, p) / 1e3, 190.0, delta=3.0)
        mwh = 125.2                              # half of the site for one hour
        self.assertGreater(ut.value_usd(cu, mwh, 2200.0, p), 0.9 * ut.cu_value_usd(cu, p))

    def test_differences_linear(self):
        p = prm()
        fact = ut.value_usd(100.0, 2000.0, 50000.0, p)
        base = ut.value_usd(110.0, 2100.0, 52000.0, p)
        self.assertAlmostEqual(fact - base, ut.value_usd(-10.0, -100.0, -2000.0, p), places=6)
        self.assertAlmostEqual(ut.co2_t(-100.0, p), -100.0 * p["econ_co2_t_mwh"], places=9)


if __name__ == "__main__":
    unittest.main()
