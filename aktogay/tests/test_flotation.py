"""Acceptance tests of sim.flotation (design sections 4 and 7 numbers),
plus unit, balance and dynamics tests of the same module."""
import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # aktogay/: packages sim, tests
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sim import flotation as fz
from sim.state import (NO_VALUE, ConcStockState, FilterState, OreProps, ThickenerState,
                       initial_state)
from tests.support import needs_impl, prm

BASE = OreProps(0.41, 5.0, 35.0, 19.4)


class TestSteady(unittest.TestCase):
    def setUp(self):
        self.p = prm()

    @needs_impl
    def test_base(self):
        r = fz.flotation_steady(3853, BASE, 178.5, 1.0, self.p)
        self.assertAlmostEqual(r.total_rec_pct, 87.2, delta=0.05)
        self.assertAlmostEqual(r.cleaner_rec_pct, 97.0, delta=1e-6)
        self.assertAlmostEqual(r.conc_cu_pct, 24.3, delta=0.03)
        self.assertAlmostEqual(r.tail_cu_pct, 0.0533, delta=0.0005)
        self.assertAlmostEqual(r.conc_tph, 56.7, delta=0.2)
        self.assertAlmostEqual(r.cu_tph, 13.78, delta=0.05)
        self.assertAlmostEqual(r.residence_min, 30.0, delta=0.05)
        self.assertAlmostEqual(r.mass_pull_pct, 7.0, delta=1e-6)

    @needs_impl
    def test_dose_drift(self):
        base = fz.flotation_steady(3853, BASE, 178.5, 1.0, self.p)
        r = fz.flotation_steady(3853, BASE, 178.5, 0.6, self.p)
        self.assertAlmostEqual(base.total_rec_pct - r.total_rec_pct, 3.5, delta=0.05)
        self.assertAlmostEqual(r.tail_cu_pct, 0.0677, delta=0.001)
        self.assertLess(r.tail_cu_pct, self.p["acs_tail_sp_pct"])
        self.assertAlmostEqual(base.cu_tph - r.cu_tph, 0.55, delta=0.03)

    @needs_impl
    def test_one_ball_mill(self):
        r = fz.flotation_steady(2650, BASE, 279.0, 1.0, self.p)
        self.assertAlmostEqual(r.total_rec_pct, 86.5, delta=0.2)

    @needs_impl
    def test_hard_ore(self):
        r = fz.flotation_steady(2960, OreProps(0.41, 5.0, 27.0, 20.9), 134.3, 1.0, self.p)
        self.assertAlmostEqual(r.total_rec_pct, 89.0, delta=0.2)

    @needs_impl
    def test_grade_and_oxide(self):
        # Josemaria on total R: +4.093 ln(0.43 / 0.41) = +0.19 pp, cleaner pull -0.03 pp
        r = fz.flotation_steady(3853, OreProps(0.43, 5.0, 35.0, 19.4), 178.5, 1.0, self.p)
        self.assertAlmostEqual(r.total_rec_pct, 87.36, delta=0.05)
        # KAZ FY2024 vs FY2025: 0.4068 -> 0.43 % Cu (report balance and report grade): +0.2 pp
        # (the report shows +0.7 pp; the rest is not explained by the feed grade)
        r25 = fz.flotation_steady(3853, OreProps(self.p["tgt_2025_feed_pct"], 5.0, 35.0, 19.4), 178.5, 1.0,
                                  self.p)
        self.assertAlmostEqual(r.total_rec_pct - r25.total_rec_pct, 0.2, delta=0.05)
        # ASCu: Josemaria -1.043 pp per pp on total R, so R_inf moves by 1.043 / (k_base c_base)
        a = fz.r_inf_pct(0.41, 5.0, 178.5, 1.0, self.p)
        b = fz.r_inf_pct(0.41, 7.0, 178.5, 1.0, self.p)
        k_base = 1 - math.exp(-self.p["flot_ktau0"])
        self.assertAlmostEqual(a - b, 2.086 / (k_base * 0.97), delta=1e-9)
        r7 = fz.flotation_steady(3853, OreProps(0.41, 7.0, 35.0, 19.4), 178.5, 1.0, self.p)
        r5 = fz.flotation_steady(3853, BASE, 178.5, 1.0, self.p)
        self.assertAlmostEqual(r5.total_rec_pct - r7.total_rec_pct, 2.086, delta=1e-4)

    @needs_impl
    def test_rich_feed_keeps_concentrate_grade(self):
        """The grade-recovery line trades grade only for recovery not given by the feed grade."""
        r41 = fz.flotation_steady(3853, BASE, 178.5, 1.0, self.p)
        r50 = fz.flotation_steady(3853, OreProps(0.50, 5.0, 35.0, 19.4), 178.5, 1.0, self.p)
        self.assertGreater(r50.total_rec_pct, r41.total_rec_pct)
        # only the cleaner pull loss is traded: grade within 0.1 % Cu of the base
        self.assertAlmostEqual(r50.conc_cu_pct, r41.conc_cu_pct, delta=0.1)
        cu_ratio = r50.cu_tph / r41.cu_tph
        self.assertAlmostEqual(r50.conc_tph / r41.conc_tph, cu_ratio, delta=0.01)
        self.assertLess(r50.conc_tph / r41.conc_tph, 1.25)       # +22 % feed grade -> about +23 % t/h
        # the gain removed from the line is the total-R grade term
        g = fz.grade_gain_total_pp(0.50, self.p)
        self.assertAlmostEqual(g, self.p["flot_grade_pp_ln"] * math.log(0.50 / 0.41), places=12)
        self.assertAlmostEqual(fz.conc_grade_pct(87.2 + g, self.p, 0.50), 24.3, places=9)
        self.assertEqual(fz.conc_grade_pct(87.2, self.p, 0.41), fz.conc_grade_pct(87.2, self.p))

    @needs_impl
    def test_zero_feed(self):
        r = fz.flotation_steady(0.0, BASE, 178.5, 1.0, self.p)
        self.assertEqual(r.conc_tph, 0.0)
        self.assertEqual(r.cu_tph, 0.0)


class TestDynamics(unittest.TestCase):
    def setUp(self):
        self.p = prm()
        self.st = initial_state(self.p)
        self.ln = self.st.line(1)

    def step(self, t, dose):
        return fz.flotation_step(self.ln.flot, self.ln.rougher, self.ln.cleaner, 3853, BASE, 178.5,
                                 dose, 25.0, t, 1.0, self.p)

    @needs_impl
    def test_delay_and_lag(self):
        t = 480.0
        for _ in range(60):
            self.step(t, 1.0)
            t += 1
        self.assertAlmostEqual(self.ln.flot.recovery, 87.2, delta=0.05)
        for _ in range(10):
            r = self.step(t, 0.6)
            t += 1
        self.assertAlmostEqual(r.total_rec_pct, 87.2, delta=0.05)      # inside transport delay
        for _ in range(120):
            r = self.step(t, 0.6)
            t += 1
        self.assertAlmostEqual(r.total_rec_pct, 83.7, delta=0.2)
        self.assertEqual(self.ln.rougher.dose_meas_gt, 25.0)
        self.assertAlmostEqual(self.ln.rougher.dose_true_gt, 15.0, delta=1e-6)

    @needs_impl
    def test_thickener_one_press(self):
        th = self.ln.thick
        inv0 = th.inventory_t
        for _ in range(60):
            out = fz.thickener_step(th, 56.7, 35.0, 1.0, self.p)
        self.assertAlmostEqual(out, 35.0)
        self.assertAlmostEqual(th.inventory_t - inv0, 21.7, delta=0.1)
        self.assertGreater(th.overflow_m3h, 0.0)

    @needs_impl
    def test_cloth_change_once_per_shift(self):
        fi = self.ln.filter
        one = 0
        t = 8 * 60.0
        while t < 20 * 60.0:
            fz.filter_capacity_tph(fi, t, False, 42, self.p)
            one += fi.presses_on == 1
            t += 1.0
        self.assertEqual(one, 60)
        self.assertEqual(fz.filter_capacity_tph(fi, t, True, 42, self.p), 0.0)
        self.assertEqual(fi.state, "STOP")

    @needs_impl
    def test_train(self):
        cs = self.st.conc_stock
        s0 = cs.stock_t
        shipped = 0.0
        t = 5 * 60.0
        while t < 7 * 60.0:
            shipped += fz.conc_stock_step(cs, 0.0, t, 1.0, self.p)
            t += 1.0
        self.assertAlmostEqual(shipped, 21 * 70)
        self.assertAlmostEqual(cs.stock_t, s0 - 21 * 70)
        self.assertEqual(cs.wagons_shift, 21)


# ---------------------------------------------------------------------------
# Unit tests of the formulas
# ---------------------------------------------------------------------------
class TestFormulas(unittest.TestCase):
    def setUp(self):
        self.p = prm()
        self.k_base = 1 - math.exp(-self.p["flot_ktau0"])

    def test_residence(self):
        q0 = self.p["cal_line_tph"]
        self.assertAlmostEqual(fz.residence_min(q0, self.p), self.p["flot_tau0_min"])
        self.assertAlmostEqual(fz.residence_min(q0 / 2, self.p), 2 * self.p["flot_tau0_min"])
        self.assertEqual(fz.residence_min(0.0, self.p), NO_VALUE)

    def test_r_inf_grind_term(self):
        a = fz.r_inf_pct(0.41, 5.0, 178.5, 1.0, self.p)
        self.assertAlmostEqual(a, self.p["flot_rinf0_pct"], places=9)
        self.assertAlmostEqual(a - fz.r_inf_pct(0.41, 5.0, 279.0, 1.0, self.p), 0.3 * 9.9, places=9)
        self.assertEqual(fz.r_inf_pct(0.41, 5.0, 120.0, 1.0, self.p), a)        # no gain below 180 um
        self.assertEqual(fz.r_inf_pct(0.41, 5.0, NO_VALUE, 1.0, self.p), a)     # unknown P80: no loss

    def test_r_inf_dose_term(self):
        a = fz.r_inf_pct(0.41, 5.0, 178.5, 1.0, self.p)
        self.assertEqual(fz.r_inf_pct(0.41, 5.0, 178.5, 1.3, self.p), a)        # over-dose: no gain
        drop = a - fz.r_inf_pct(0.41, 5.0, 178.5, 0.6, self.p)
        self.assertAlmostEqual(drop, 3.5 / (self.k_base * 0.97), places=9)
        half = a - fz.r_inf_pct(0.41, 5.0, 178.5, 0.8, self.p)
        self.assertAlmostEqual(half, drop / 2, places=9)                        # linear in deficit

    def test_r_inf_grade_term_and_clamp(self):
        a = fz.r_inf_pct(0.41, 5.0, 178.5, 1.0, self.p)
        b = fz.r_inf_pct(0.50, 5.0, 178.5, 1.0, self.p)
        slope = self.p["flot_grade_pp_ln"] / (self.k_base * 0.97)
        self.assertAlmostEqual(b - a, slope * math.log(0.50 / 0.41), places=9)
        self.assertAlmostEqual(fz.grade_gain_pp(0.50, self.p), b - a, places=12)
        self.assertEqual(fz.r_inf_pct(0.41, 200.0, 178.5, 1.0, self.p), 0.0)
        self.assertEqual(fz.r_inf_pct(0.41, -200.0, 178.5, 1.0, self.p), 100.0)
        self.assertEqual(fz.r_inf_pct(0.0, 5.0, 178.5, 1.0, self.p), 0.0)

    def test_rougher_kinetics(self):
        tau0 = self.p["flot_tau0_min"]
        self.assertAlmostEqual(fz.rougher_recovery_pct(92.0, tau0, self.p), 92.0 * self.k_base, places=9)
        rs = [fz.rougher_recovery_pct(92.0, t, self.p) for t in (10, 20, 30, 45, 60, 600)]
        self.assertEqual(rs, sorted(rs))
        self.assertAlmostEqual(rs[-1], 92.0, places=6)
        self.assertEqual(fz.rougher_recovery_pct(92.0, 0.0, self.p), 0.0)
        self.assertEqual(fz.rougher_recovery_pct(92.0, NO_VALUE, self.p), 0.0)

    def test_pull_and_cleaner(self):
        self.assertAlmostEqual(fz.mass_pull_pct(0.43, self.p), 7.0 * 0.43 / 0.41, places=9)
        self.assertEqual(fz.mass_pull_pct(0.0, self.p), 0.0)
        self.assertEqual(fz.cleaner_recovery_pct(5.0, self.p), 97.0)
        self.assertAlmostEqual(fz.cleaner_recovery_pct(17.0, self.p), 96.0, places=9)
        self.assertAlmostEqual(fz.cleaner_recovery_pct(fz.mass_pull_pct(0.43, self.p), self.p), 96.966,
                               delta=1e-3)

    def test_grade_line_and_cap(self):
        self.assertAlmostEqual(fz.conc_grade_pct(87.2, self.p), 24.3, places=9)
        self.assertAlmostEqual(fz.conc_grade_pct(83.7, self.p), 26.05, places=9)
        self.assertEqual(fz.conc_grade_pct(0.0, self.p), self.p["flot_conc_max_pct"])

    def test_tails_two_product(self):
        self.assertAlmostEqual(fz.tails_cu_pct(0.41, 87.2, 24.3), 0.41 * 0.128 / (1 - 0.41 * 0.872 / 24.3),
                               places=12)
        self.assertEqual(fz.tails_cu_pct(0.41, 87.2, 0.0), NO_VALUE)
        self.assertEqual(fz.tails_cu_pct(0.41, 100.0, 0.41), NO_VALUE)          # all mass to concentrate
        self.assertEqual(fz.tails_cu_pct(0.0, 87.2, 24.3), 0.0)

    def test_steady_balances(self):
        cases = [(3853, BASE, 178.5, 1.0), (3853, BASE, 178.5, 0.6), (2650, BASE, 279.0, 1.0),
                 (3000, OreProps(0.50, 9.0, 30.0, 20.0), 210.0, 0.7),
                 (4200, OreProps(0.33, 2.0, 40.0, 18.0), 150.0, 1.0)]
        for q, ore, p80, d in cases:
            r = fz.flotation_steady(q, ore, p80, d, self.p)
            feed_cu = q * ore.cu_pct / 100
            tails_cu = (q - r.conc_tph) * r.tail_cu_pct / 100
            self.assertAlmostEqual(feed_cu, r.cu_tph + tails_cu, places=9)
            self.assertAlmostEqual(r.conc_tph * r.conc_cu_pct / 100, r.cu_tph, places=9)
            self.assertAlmostEqual(r.total_rec_pct, r.rougher_rec_pct * r.cleaner_rec_pct / 100, places=9)
            self.assertAlmostEqual(r.rconc_cu_pct, ore.cu_pct * r.rougher_rec_pct / r.mass_pull_pct, places=9)

    def test_tradeoffs(self):
        def rec(q, p80=178.5, ascu=5.0):
            return fz.flotation_steady(q, OreProps(0.41, ascu, 35, 19.4), p80, 1.0, self.p).total_rec_pct
        self.assertGreater(rec(3000), rec(3853))       # longer residence
        self.assertGreater(rec(3853), rec(4300))
        self.assertGreater(rec(3853), rec(3853, 230))  # coarse grind
        self.assertAlmostEqual(rec(3853, ascu=5) - rec(3853, ascu=7), 2.086, delta=1e-4)

    def test_tails_follow_grade_and_dose_drift(self):
        # tails follow the feed grade (design section 4): 0.046 % Cu at 0.33, 0.053 at 0.41,
        # 0.061 at 0.50, all below the alarm setpoint; the 40 % dose drift raises them by more
        # than 20 % (about 5 analyser sigma); on average ore it stays below the setpoint, on rich
        # ore it may cross it (design section 4 allows that)
        sp = self.p["acs_tail_sp_pct"]
        tails = {}
        for g in (0.33, 0.41, 0.50):
            ore = OreProps(g, 5.0, 35, 19.4)
            base = fz.flotation_steady(3853, ore, 178.5, 1.0, self.p)
            drift = fz.flotation_steady(3853, ore, 178.5, 0.6, self.p)
            tails[g] = base.tail_cu_pct
            self.assertLess(base.tail_cu_pct, sp, msg=g)
            self.assertGreater(drift.tail_cu_pct / base.tail_cu_pct, 1.2, msg=g)
            if g <= 0.41:
                self.assertLess(drift.tail_cu_pct, sp, msg=g)
        self.assertAlmostEqual(tails[0.33], 0.046, delta=0.001)
        self.assertAlmostEqual(tails[0.41], 0.053, delta=0.001)
        self.assertAlmostEqual(tails[0.50], 0.061, delta=0.001)

    def test_zero_feed_values(self):
        r = fz.flotation_steady(-5.0, BASE, 178.5, 1.0, self.p)
        self.assertEqual((r.conc_tph, r.cu_tph), (0.0, 0.0))
        self.assertEqual((r.total_rec_pct, r.conc_cu_pct, r.tail_cu_pct, r.residence_min), (NO_VALUE,) * 4)


# ---------------------------------------------------------------------------
# Flotation step: lag, delay, states, stage split
# ---------------------------------------------------------------------------
class TestFlotationStep(unittest.TestCase):
    def setUp(self):
        self.p = prm()

    def run_line(self, dt, t_end, dose_at=540.0, dose=0.6, q=3853.0, ore=BASE):
        st = initial_state(self.p)
        ln = st.line(1)
        t, out = 480.0, {}
        while t < t_end - 1e-9:
            d = dose if t >= dose_at else 1.0
            r = fz.flotation_step(ln.flot, ln.rougher, ln.cleaner, q, ore, 178.5, d, 25.0, t, dt, self.p)
            t += dt
            out[round(t, 6)] = r.total_rec_pct
        return ln, out

    def test_stage_split_and_cleaner_balance(self):
        ln, _ = self.run_line(1.0, 700.0)
        ro, cl, fl = ln.rougher, ln.cleaner, ln.flot
        self.assertAlmostEqual(ro.stage_recovery * cl.stage_recovery / 100, fl.recovery, places=9)
        self.assertAlmostEqual(cl.feed_tph, 3853 * ro.mass_pull_pct / 100, places=9)
        cu_rconc = cl.feed_tph * ro.rconc_cu / 100
        self.assertAlmostEqual(cu_rconc, fl.cu_tph + (cl.feed_tph - cl.conc_tph) * cl.tail_cu / 100, places=9)
        self.assertTrue(fl.tail_cu < cl.tail_cu < ro.rconc_cu < fl.conc_cu)
        self.assertEqual((fl.state, ro.state, cl.state), ("RUN", "RUN", "RUN"))
        self.assertAlmostEqual(fl.feed_cu * 3853 / 100, fl.cu_tph + (3853 - fl.conc_tph) * fl.tail_cu / 100,
                               places=9)

    def test_lag_shape(self):
        # input changes at 540; output starts at 555 and is 63.2 % through at 575
        _, out = self.run_line(1.0, 600.0)
        self.assertAlmostEqual(out[555.0], out[540.0], delta=1e-4)          # dead time
        self.assertAlmostEqual(out[555.0] - out[556.0], 3.5 * (1 - math.exp(-1 / 20)), delta=1e-3)
        expect = 87.1996 - 3.5 * (1 - math.exp(-1.0))
        self.assertAlmostEqual(out[575.0], expect, delta=0.002)

    def test_step_size_independent(self):
        _, a = self.run_line(1.0, 720.0)
        _, b = self.run_line(5.0, 720.0)
        _, c = self.run_line(10.0, 720.0)
        for t in (560.0, 580.0, 600.0, 650.0, 720.0):
            self.assertAlmostEqual(a[t], b[t], places=9)
            self.assertAlmostEqual(a[t], c[t], places=9)

    def test_deterministic_and_history_bounded(self):
        ln1, a = self.run_line(1.0, 1500.0)
        ln2, b = self.run_line(1.0, 1500.0)
        self.assertEqual(a, b)
        self.assertLessEqual(len(ln1.flot.history), self.p["flot_delay_min"] + 2)

    def test_stop_and_restart(self):
        st = initial_state(self.p)
        ln = st.line(1)
        fl, ro, cl = ln.flot, ln.rougher, ln.cleaner
        for i in range(30):
            fz.flotation_step(fl, ro, cl, 3853, BASE, 178.5, 1.0, 25.0, 480.0 + i, 1.0, self.p)
        held = fl.rec_lag
        r = fz.flotation_step(fl, ro, cl, 0.0, BASE, NO_VALUE, 1.0, 25.0, 510.0, 1.0, self.p)
        self.assertEqual((fl.state, ro.state, cl.state), ("STOP", "STOP", "STOP"))
        self.assertEqual((r.cu_tph, r.conc_tph, fl.cu_tph, fl.conc_tph, cl.conc_tph), (0.0,) * 5)
        self.assertEqual((fl.recovery, fl.tail_cu, ro.residence_min), (NO_VALUE,) * 3)
        self.assertEqual(fl.rec_lag, held)
        r = fz.flotation_step(fl, ro, cl, 3853, BASE, 178.5, 1.0, 25.0, 900.0, 1.0, self.p)
        self.assertAlmostEqual(r.total_rec_pct, held, delta=1e-4)
        self.assertEqual(fl.state, "RUN")

    def test_upset_on_high_tails(self):
        ln, _ = self.run_line(1.0, 700.0, dose_at=480.0, ore=OreProps(0.41, 10.0, 35, 19.4))
        self.assertGreater(ln.flot.tail_cu, self.p["acs_tail_sp_pct"])
        self.assertEqual((ln.flot.state, ln.rougher.state, ln.cleaner.state), ("UPSET",) * 3)

    def test_dose_fields(self):
        ln, _ = self.run_line(1.0, 545.0, dose=0.75)
        self.assertEqual(ln.rougher.dose_sp_gt, self.p["flot_dose_sp_gt"])
        self.assertEqual(ln.rougher.dose_meas_gt, 25.0)
        self.assertAlmostEqual(ln.rougher.dose_true_gt, 25.0 * 0.75, places=9)

    def test_empty_state_starts_steady(self):
        from sim.state import CleanerState, FlotState, RougherState
        fl, ro, cl = FlotState("flot-1", 1), RougherState("rougher-1", 1), CleanerState("cleaner-1", 1)
        r = fz.flotation_step(fl, ro, cl, 3853, BASE, 178.5, 1.0, 25.0, 0.0, 1.0, self.p)
        self.assertAlmostEqual(r.total_rec_pct, 87.2, delta=0.01)
        self.assertAlmostEqual(r.conc_cu_pct, 24.3, delta=0.01)


# ---------------------------------------------------------------------------
# Thickener, filter, concentrate stock
# ---------------------------------------------------------------------------
class TestConcentrateHandling(unittest.TestCase):
    def setUp(self):
        self.p = prm()

    def test_thickener_steady_overflow(self):
        th = ThickenerState("thick-1", 1)
        out = fz.thickener_step(th, 56.7, 70.0, 1.0, self.p)
        self.assertAlmostEqual(out, 56.7)
        self.assertAlmostEqual(th.overflow_m3h, 56.7 * 3 - 56.7 * 40 / 60, places=9)   # 132.3
        self.assertAlmostEqual(th.overflow_m3h, 132.3, places=6)
        self.assertEqual(th.hours_to_full, NO_VALUE)
        self.assertEqual((th.state, th.inventory_t, th.solids_pct), ("NORMAL", 0.0, 60.0))

    def test_thickener_drains_backlog(self):
        th = ThickenerState("thick-1", 1, inventory_t=40.0)
        out = fz.thickener_step(th, 56.7, 70.0, 60.0, self.p)
        self.assertAlmostEqual(out, 70.0)
        self.assertAlmostEqual(th.inventory_t, 40.0 - 13.3, places=9)
        for _ in range(3):
            out = fz.thickener_step(th, 56.7, 70.0, 60.0, self.p)
        self.assertAlmostEqual(th.inventory_t, 0.0, places=9)
        self.assertAlmostEqual(out, 56.7 + (40.0 - 3 * 13.3), places=9)       # last 0.1 t of backlog

    def test_thickener_states_and_hours(self):
        th = ThickenerState("thick-1", 1, inventory_t=100.0)
        fz.thickener_step(th, 56.7, 35.0, 1.0, self.p)
        self.assertAlmostEqual(th.hours_to_full, (340.0 - th.inventory_t) / 21.7, places=9)
        th.inventory_t = 0.8 * 340.0
        fz.thickener_step(th, 56.7, 35.0, 1.0, self.p)
        self.assertEqual(th.state, "HIGH")
        th.inventory_t = 340.0
        fz.thickener_step(th, 56.7, 0.0, 1.0, self.p)
        self.assertEqual((th.state, th.hours_to_full), ("FULL", 0.0))
        self.assertGreater(th.inventory_t, 340.0)                                # not clamped

    def test_thickener_solids_and_water_balance(self):
        th = ThickenerState("thick-1", 1, inventory_t=50.0)
        w_feed, w_uf = 75.0 / 25.0, 40.0 / 60.0
        for cap in (35.0, 70.0, 0.0):
            inv0 = th.inventory_t
            out = fz.thickener_step(th, 56.7, cap, 10.0, self.p)
            d_inv_h = (th.inventory_t - inv0) * 60.0 / 10.0
            self.assertAlmostEqual(56.7 - out, d_inv_h, places=9)
            # feed water = overflow + underflow water + change of bed water
            self.assertAlmostEqual(56.7 * w_feed, th.overflow_m3h + out * w_uf + d_inv_h * w_uf, places=9)

    def test_filter_step(self):
        fi = FilterState("filter-1", 1)
        wet = fz.filter_step(fi, 56.7, self.p, 0.0)
        self.assertAlmostEqual(wet, 56.7 / 0.92, places=9)
        self.assertEqual((fi.cake_tph, fi.moisture_pct), (56.7, 8.0))
        fz.filter_step(fi, 56.7, self.p, 1.0)
        self.assertAlmostEqual(fi.moisture_pct, 8.3, places=9)
        self.assertEqual(fz.filter_step(fi, 0.0, self.p, 0.0), 0.0)

    def test_cloth_same_in_copies_other_line_differs(self):
        a, b, c = FilterState("filter-1", 1), FilterState("filter-1", 1), FilterState("filter-2", 2)
        sa, sc = [], []
        t = 8 * 60.0
        while t < 8 * 60.0 + 3 * 720.0:
            fz.filter_capacity_tph(a, t, False, 42, self.p)
            fz.filter_capacity_tph(b, t, False, 42, self.p)
            fz.filter_capacity_tph(c, t, False, 42, self.p)
            sa.append(a.presses_on)
            sc.append(c.presses_on)
            self.assertEqual(a.presses_on, b.presses_on)
            t += 1.0
        self.assertNotEqual(sa, sc)
        self.assertEqual(sa.count(1), 3 * 60)
        for k in range(3):                                          # window inside its shift
            s, e = fz.cloth_window_min(1, 8 * 60.0 + k * 720.0 + 1.0, 42, self.p)
            self.assertGreaterEqual(s, 8 * 60.0 + k * 720.0)
            self.assertLessEqual(e, 8 * 60.0 + (k + 1) * 720.0)
        s1, _ = fz.cloth_window_min(1, 600.0, 42, self.p)
        s2, _ = fz.cloth_window_min(1, 600.0, 43, self.p)
        self.assertNotEqual(s1, s2)                                 # seed matters

    def test_cloth_states_and_coarse_step(self):
        fi = FilterState("filter-1", 1)
        s, e = fz.cloth_window_min(1, 8 * 60.0, 42, self.p)
        self.assertEqual(fz.filter_capacity_tph(fi, s + 1.0, False, 42, self.p), 35.0)
        self.assertEqual(fi.state, "ONE")
        self.assertEqual(fz.filter_capacity_tph(fi, e + 1.0, False, 42, self.p), 70.0)
        self.assertEqual((fi.state, fi.presses_on, fi.limit_tph), ("RUN", 2, 70.0))
        ones, t = 0, 8 * 60.0
        while t < 20 * 60.0:
            fz.filter_capacity_tph(fi, t, False, 42, self.p)
            ones += fi.presses_on == 1
            t += 10.0
        self.assertEqual(ones, 6)

    def test_trains_two_per_day(self):
        cs = ConcStockState(stock_t=8000.0)
        shipped, t = 0.0, 0.0
        while t < 1440.0:
            shipped += fz.conc_stock_step(cs, 123.0, t, 10.0, self.p)
            t += 10.0
        self.assertAlmostEqual(shipped, 2 * 1470.0)
        self.assertAlmostEqual(cs.stock_t, 8000.0 + 123.0 * 24 - 2 * 1470.0, places=6)
        self.assertEqual((cs.wagons_shift, cs.shipped_t_shift), (42, 2940.0))
        self.assertEqual(cs.last_train_h, 18)

    def test_train_not_repeated(self):
        cs = ConcStockState(stock_t=8000.0)
        self.assertEqual(fz.conc_stock_step(cs, 0.0, 360.0, 1.0, self.p), 1470.0)
        self.assertEqual(fz.conc_stock_step(cs, 0.0, 360.0, 1.0, self.p), 0.0)
        self.assertEqual(fz.conc_stock_step(cs, 0.0, 1440.0 + 350.0, 60.0, self.p), 1470.0)  # next day
        self.assertEqual(cs.last_train_h, 24 + 6)

    def test_partial_train(self):
        cs = ConcStockState(stock_t=500.0)
        self.assertEqual(fz.conc_stock_step(cs, 0.0, 18 * 60.0, 1.0, self.p), 500.0)
        self.assertEqual((cs.stock_t, cs.wagons_shift), (0.0, 8))
        cs2 = ConcStockState(stock_t=0.0)
        self.assertEqual(fz.conc_stock_step(cs2, 0.0, 6 * 60.0, 1.0, self.p), 0.0)
        self.assertEqual(cs2.wagons_shift, 0)

    def test_stock_states_and_hours(self):
        cs = ConcStockState(stock_t=16500.0)
        fz.conc_stock_step(cs, 200.0, 0.0, 1.0, self.p)
        self.assertEqual(cs.state, "HIGH")
        mean_ship = 2 * 1470.0 / 24
        self.assertAlmostEqual(cs.hours_to_full, (20000.0 - cs.stock_t) / (200.0 - mean_ship), places=9)
        fz.conc_stock_step(cs, 100.0, 1.0, 1.0, self.p)
        self.assertEqual(cs.hours_to_full, NO_VALUE)                # trains keep up
        cs.stock_t = 20000.0
        fz.conc_stock_step(cs, 0.0, 2.0, 1.0, self.p)
        self.assertEqual((cs.state, cs.hours_to_full), ("FULL", 0.0))

    def test_chain_balance_over_shift(self):
        # cleaner = thickener change + filter; filter wet = stock change + shipped
        st = initial_state(self.p)
        ln, cs = st.line(1), st.conc_stock
        th0, cs0 = ln.thick.inventory_t, cs.stock_t
        conc_t = cake_t = wet_t = shipped = 0.0
        t, dt = 6 * 60.0, 1.0
        while t < 20 * 60.0:
            r = fz.flotation_step(ln.flot, ln.rougher, ln.cleaner, 3853, BASE, 178.5, 1.0, 25.0, t, dt, self.p)
            cap = fz.filter_capacity_tph(ln.filter, t, cs.state == "FULL", 42, self.p)
            uf = fz.thickener_step(ln.thick, r.conc_tph, cap, dt, self.p)
            wet = fz.filter_step(ln.filter, uf, self.p, 0.0)
            shipped += fz.conc_stock_step(cs, wet, t, dt, self.p)
            conc_t += r.conc_tph * dt / 60
            cake_t += ln.filter.cake_tph * dt / 60
            wet_t += wet * dt / 60
            t += dt
        self.assertAlmostEqual(conc_t, ln.thick.inventory_t - th0 + cake_t, places=6)
        self.assertAlmostEqual(wet_t, cs.stock_t - cs0 + shipped, places=6)
        self.assertEqual(shipped, 2 * 1470.0)                       # 06:00 and 18:00 trains


if __name__ == "__main__":
    unittest.main()
