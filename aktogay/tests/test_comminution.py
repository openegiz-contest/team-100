"""Acceptance tests of sim.comminution (design section 4 numbers)."""
import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # aktogay/: packages sim, tests
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sim import comminution as cm
from sim.state import CauseEffects, OreProps, feed_end_wear_mm, initial_state
from tests.support import needs_impl, prm

INF = float("inf")


class TestFormulas(unittest.TestCase):
    def setUp(self):
        self.p = prm()
        self.base = OreProps(0.41, 5.0, 35.0, 19.4)
        self.hard = OreProps(0.41, 5.0, 27.0, 20.9)

    @needs_impl
    def test_dwi_and_energy(self):
        self.assertAlmostEqual(cm.dwi(35, self.p), 7.6, places=6)
        self.assertAlmostEqual(cm.sag_specific_energy(self.base, self.p), 6.748, delta=0.002)
        self.assertAlmostEqual(cm.sag_specific_energy(self.hard, self.p), 8.305, delta=0.005)

    @needs_impl
    def test_pebble_stop_energy(self):
        e = cm.sag_specific_energy(self.base, self.p)
        self.assertAlmostEqual(cm.sag_specific_energy(self.base, self.p, False) / e, 1.06, places=6)
        eh = cm.sag_specific_energy(self.hard, self.p)
        self.assertAlmostEqual(cm.sag_specific_energy(self.hard, self.p, False) / eh, 1.10, places=6)

    @needs_impl
    def test_austin(self):
        j0 = self.p["sag_load0_pct"]
        self.assertEqual(j0, 25.0)                                     # Bradken total load
        self.assertAlmostEqual(cm.austin_power_ratio(j0, 76, self.p), 1.0, places=9)
        self.assertEqual(cm.austin_power_ratio(0, 76, self.p), 0.0)
        self.assertAlmostEqual(cm.load_for_power_ratio(1.0, 76, self.p), j0, places=4)
        j = cm.load_for_power_ratio(0.5, 76, self.p)
        self.assertAlmostEqual(cm.austin_power_ratio(j, 76, self.p), 0.5, places=6)
        self.assertLess(cm.austin_power_ratio(j0, 70, self.p), 1.0)

    @needs_impl
    def test_ball_charge_floor(self):
        """Ore ground out: the 12 % ball charge (Bradken) still draws 65-70 % of P0."""
        p = self.p
        floor = cm.ball_floor_ratio(76, p)
        self.assertTrue(0.65 <= floor <= 0.70, floor)
        self.assertAlmostEqual(floor, p["sag_ball_dens_mult"] * cm.austin_power_ratio(12, 76, p), places=12)
        self.assertEqual(cm.sag_power_ratio(p["sag_ball_load_pct"], 76, p), floor)
        self.assertAlmostEqual(cm.sag_power_ratio(p["sag_load0_pct"], 76, p), 1.0, places=9)
        j_eq = cm.load_for_power_ratio(floor, 76, p)
        self.assertTrue(p["sag_ball_load_pct"] < j_eq < p["sag_load0_pct"])
        self.assertEqual(cm.sag_power_ratio(0.5 * (j_eq + 12), 76, p), floor)   # flat below j_eq
        # slower mill: the ball charge draws less, by the Austin speed term
        self.assertAlmostEqual(cm.ball_floor_ratio(60, p) / floor, cm.austin_power_ratio(25, 60, p), places=9)

    @needs_impl
    def test_speed_for_speed_ratio(self):
        p = self.p
        for r in (0.2, 0.5, 0.735, 0.99):
            s = cm.speed_for_speed_ratio(r, p)
            self.assertAlmostEqual(cm.austin_power_ratio(p["sag_load0_pct"], s, p), r, places=9)
        self.assertEqual(cm.speed_for_speed_ratio(1.0, p), p["sag_speed_pct"])
        self.assertEqual(cm.speed_for_speed_ratio(0.0, p), 0.0)

    @needs_impl
    def test_liner_eta(self):
        p = self.p
        self.assertAlmostEqual(cm.liner_eta(0.0, p), p["liner_eta_new"])
        self.assertAlmostEqual(cm.liner_eta(p["liner_x_ramp"], p), 1.0)
        self.assertAlmostEqual(cm.liner_eta(p["liner_x_peak"], p), p["liner_eta_peak"])
        self.assertAlmostEqual(cm.liner_eta(1.0, p), p["liner_eta_end"])
        self.assertAlmostEqual(cm.liner_eta(p["liner_x0"], p), 1.0)

    @needs_impl
    def test_pebble_fraction(self):
        self.assertAlmostEqual(cm.pebble_fraction(35, self.p), 0.15)
        self.assertAlmostEqual(cm.pebble_fraction(27, self.p), 0.25)
        self.assertGreaterEqual(cm.pebble_fraction(60, self.p), 0.0)

    @needs_impl
    def test_capacity_roundtrip(self):
        e = cm.sag_specific_energy(self.base, self.p)
        self.assertAlmostEqual(cm.sag_capacity_tph(26000, e, 1.0), 3853, delta=1)
        self.assertAlmostEqual(cm.sag_power_for_tph(3853, e, 1.0), 26000, delta=5)
        self.assertAlmostEqual(cm.axb_from_energy(e, self.p), 35.0, places=4)

    @needs_impl
    def test_bond(self):
        p = self.p
        self.assertAlmostEqual(cm.ball_p80_um(3853, 41000, 19.4, p), 178.5, delta=0.5)
        self.assertAlmostEqual(cm.ball_p80_um(1925, 20500, 19.4, p), 178.3, delta=0.5)
        self.assertAlmostEqual(cm.ball_p80_um(2650, 20500, 19.4, p), 279, delta=1)
        self.assertAlmostEqual(cm.ball_p80_um(2960, 41000, 20.9, p), 134.3, delta=0.5)
        self.assertEqual(cm.ball_p80_um(0, 41000, 19.4, p), -1.0)
        self.assertAlmostEqual(cm.ball_q_for_p80(20500, 19.4, 179, p), 1930, delta=5)

    @needs_impl
    def test_line_feed_cap(self):
        st = initial_state(self.p)
        balls = st.line(2).balls
        self.assertEqual(cm.line_feed_cap_tph(balls, 19.4, self.p), INF)
        balls[1].state = "STOP"
        self.assertAlmostEqual(cm.line_feed_cap_tph(balls, 19.4, self.p), 1937, delta=10)


class TestUnits(unittest.TestCase):
    def setUp(self):
        self.p = prm()
        self.st = initial_state(self.p)
        self.ln = self.st.line(1)
        self.base = OreProps(0.41, 5.0, 35.0, 19.4)

    def run_sag(self, ore, minutes=60, avail=1e6, cap=INF, dt=1.0):
        q = 0.0
        for _ in range(int(minutes / dt)):
            q = cm.sag_step(self.ln.sag, self.ln.pebble, avail, ore, cap, CauseEffects(), dt, self.p, 0.0)
        return q

    @needs_impl
    def test_sag_base_steady(self):
        q = self.run_sag(self.base)
        self.assertAlmostEqual(q, 3853, delta=10)
        self.assertAlmostEqual(self.ln.sag.power_kw, 26000, delta=300)
        self.assertAlmostEqual(self.ln.pebble.feed_tph, 578, delta=5)
        self.assertEqual(self.ln.sag.state, "RUN")
        self.assertEqual(self.ln.pebble.state, "RUN")

    @needs_impl
    def test_sag_hard_pebble_limit(self):
        q = self.run_sag(OreProps(0.41, 5.0, 27.0, 20.9))
        self.assertAlmostEqual(q, 2960, delta=15)
        self.assertEqual(self.ln.pebble.state, "LIMIT")

    @needs_impl
    def test_sag_starved(self):
        """No feed: the rock grinds out, the ball charge stays and draws about 69 % of P0."""
        q = self.run_sag(self.base, minutes=30, avail=0.0)
        self.assertEqual(q, 0.0)
        self.assertEqual(self.ln.sag.state, "STARVED")
        self.assertAlmostEqual(self.ln.sag.load_pct, self.p["sag_ball_load_pct"], delta=0.05)
        floor_kw = 26000 * cm.ball_floor_ratio(76, self.p)
        self.assertAlmostEqual(self.ln.sag.power_kw, floor_kw, delta=1.0)
        self.assertTrue(0.65 * 26000 <= self.ln.sag.power_kw <= 0.70 * 26000)
        self.assertEqual(self.ln.sag.speed_pct, self.p["sag_speed_pct"])

    @needs_impl
    def test_sag_grid_cap(self):
        """A cap below the ball-charge draw: the control slows the mill so it draws the cap."""
        e = cm.sag_specific_energy(self.base, self.p)
        q = self.run_sag(self.base, cap=1925 * e)
        self.assertAlmostEqual(q, 1925, delta=10)
        self.assertEqual(self.ln.sag.state, "LIMITED_GRID")
        self.assertAlmostEqual(self.ln.sag.power_kw, 1925 * e, delta=20)
        self.assertLess(self.ln.sag.speed_pct, self.p["sag_speed_pct"] - 15)
        self.assertAlmostEqual(self.ln.sag.load_pct, self.p["sag_ball_load_pct"], delta=0.05)
        # cap lifted: speed back to the setpoint
        self.run_sag(self.base, minutes=1)
        self.assertEqual(self.ln.sag.speed_pct, self.p["sag_speed_pct"])

    @needs_impl
    def test_sag_cap_above_floor_keeps_speed(self):
        e = cm.sag_specific_energy(self.base, self.p)
        floor_kw = 26000 * cm.ball_floor_ratio(self.p["sag_speed_pct"], self.p)
        self.assertGreater(2800 * e, floor_kw)                     # 18.9 MW above the ball draw 18.2 MW
        q = self.run_sag(self.base, cap=2800 * e)
        self.assertAlmostEqual(q, 2800, delta=10)
        self.assertEqual(self.ln.sag.speed_pct, self.p["sag_speed_pct"])
        self.assertAlmostEqual(self.ln.sag.power_kw, 2800 * e, delta=20)
        # 2650 t/h (17.9 MW) sits just below the ball-charge draw with the Austin 1990 load term:
        # the mill is slowed a little and draws the ball charge at that speed
        self.assertLess(2650 * e, floor_kw)
        other = initial_state(self.p).line(1)
        for _ in range(240):
            cm.sag_step(other.sag, other.pebble, 1e6, self.base, 2650 * e, CauseEffects(), 1.0, self.p, 0.0)
        self.assertLess(other.sag.speed_pct, self.p["sag_speed_pct"])
        self.assertGreater(other.sag.speed_pct, 0.95 * self.p["sag_speed_pct"])
        self.assertAlmostEqual(other.sag.power_kw, 26000 * cm.ball_floor_ratio(other.sag.speed_pct, self.p),
                               delta=20)

    @needs_impl
    def test_sag_big_step_stable(self):
        q = self.run_sag(self.base, minutes=600, dt=10.0)
        self.assertAlmostEqual(q, 3853, delta=10)
        self.assertTrue(math.isfinite(self.ln.sag.load_pct))

    @needs_impl
    def test_liner_counter(self):
        w0 = self.ln.sag.liner_wear_mm
        self.run_sag(self.base, minutes=600, dt=10.0)
        mt = 3853 * 10 / 1e6
        self.assertAlmostEqual(self.ln.sag.liner_wear_mm - w0, 20.41 * mt, delta=0.05)

    @needs_impl
    def test_crusher(self):
        cr = self.ln.crusher
        self.assertAlmostEqual(cm.crusher_step(cr, 4000, 1e6, self.p, 0.0), 4000)
        self.assertEqual(cr.state, "RUN")
        self.assertAlmostEqual(cm.crusher_step(cr, 4000, 1000, self.p, 0.0), 1000)
        self.assertEqual(cr.state, "SLOW")
        self.assertAlmostEqual(cm.crusher_step(cr, 9000, 1e6, self.p, 0.0), self.p["crush_cap_tph"])
        cr.lube_bias_kpa = -200
        self.assertEqual(cm.crusher_step(cr, 4000, 1e6, self.p, 0.0), 0.0)
        self.assertEqual((cr.state, cr.fault), ("STOP", "lube_trip"))
        self.assertEqual(cr.power_kw, 0.0)

    @needs_impl
    def test_balls_and_cyclones(self):
        p80 = cm.ball_step(self.ln.balls, 3853, 19.4, self.p)
        self.assertAlmostEqual(p80, 178.5, delta=0.5)
        self.assertAlmostEqual(self.ln.balls[0].power_kw, 20500)
        cy = self.ln.cyclones
        self.assertAlmostEqual(cm.cyclone_step(cy, 3853, p80, self.p), p80, delta=1e-6)
        self.assertAlmostEqual(cy.pressure_kpa, self.p["cyc_pressure_kpa"], delta=0.5)
        cy.clogged = 1
        self.assertAlmostEqual(cm.cyclone_step(cy, 3853, p80, self.p), p80 + 12, delta=1e-6)
        self.assertEqual(cy.open_count, 10)
        self.assertAlmostEqual(cy.pressure_kpa / self.p["cyc_pressure_kpa"], 1.03, delta=0.005)


# ---------------------------------------------------------------------------
# Detailed unit tests (formula shapes, edge cases, scenario chains C2 and C3)
# ---------------------------------------------------------------------------
class TestFormulaDetails(unittest.TestCase):
    def setUp(self):
        self.p = prm()

    def ore(self, axb, bwi=19.4):
        return OreProps(0.41, 5.0, axb, bwi)

    def test_dwi_rejects_bad_axb(self):
        with self.assertRaises(ValueError):
            cm.dwi(0.0, self.p)

    def test_energy_falls_with_softer_ore(self):
        es = [cm.sag_specific_energy(self.ore(a), self.p) for a in (25, 30, 35, 40, 45)]
        self.assertTrue(all(a > b for a, b in zip(es, es[1:])))

    def test_pebble_stop_mult_interpolates(self):
        mid = (self.p["ore_axb_base"] + self.p["ore_axb_hard"]) / 2
        self.assertAlmostEqual(cm.pebble_stop_mult(mid, self.p), 1.08, places=9)
        self.assertEqual(cm.pebble_stop_mult(45, self.p), self.p["peb_stop_e_med"])
        self.assertEqual(cm.pebble_stop_mult(20, self.p), self.p["peb_stop_e_hard"])

    def test_austin_shape(self):
        k = self.p["sag_austin_j"]
        j_top = 100 / (2 * k)
        r_top = cm.austin_power_ratio(j_top, 76, self.p)
        self.assertGreater(r_top, cm.austin_power_ratio(j_top - 5, 76, self.p))
        self.assertGreater(r_top, cm.austin_power_ratio(j_top + 5, 76, self.p))
        self.assertEqual(cm.austin_power_ratio(-3, 76, self.p), 0.0)
        # inverse clamps to the top of the rising branch
        self.assertAlmostEqual(cm.load_for_power_ratio(5.0, 76, self.p), j_top, places=9)
        self.assertEqual(cm.load_for_power_ratio(0.0, 76, self.p), 0.0)
        self.assertEqual(cm.load_for_power_ratio(-1.0, 76, self.p), 0.0)

    def test_austin_inverse_other_speed(self):
        for ratio in (0.05, 0.3, 0.8, 1.1):
            j = cm.load_for_power_ratio(ratio, 72, self.p)
            self.assertAlmostEqual(cm.austin_power_ratio(j, 72, self.p), ratio, places=9)

    def test_liner_eta_profile(self):
        p = self.p
        self.assertEqual(cm.liner_eta(-0.5, p), p["liner_eta_new"])
        self.assertEqual(cm.liner_eta(1.7, p), p["liner_eta_end"])
        x = (p["liner_x_ramp"] + p["liner_x_peak"]) / 2
        self.assertAlmostEqual(cm.liner_eta(x, p), (1.0 + p["liner_eta_peak"]) / 2, places=9)
        # new liner is 3-5 % below the reference, the peak is late in the campaign
        self.assertLess(cm.liner_eta(0.0, p), cm.liner_eta(0.05, p))
        self.assertLess(cm.liner_eta(0.95, p), cm.liner_eta(p["liner_x_peak"], p))

    def test_capacity_edges(self):
        self.assertEqual(cm.sag_capacity_tph(0.0, 6.7, 1.0), 0.0)
        self.assertEqual(cm.sag_power_for_tph(0.0, 6.7, 1.0), 0.0)
        self.assertEqual(cm.sag_power_for_tph(INF, 6.7, 1.0), INF)
        with self.assertRaises(ValueError):
            cm.sag_capacity_tph(26000, 0.0, 1.0)

    def test_soft_sensor_edges(self):
        self.assertEqual(cm.axb_from_energy(0.0, self.p), -1.0)
        self.assertEqual(cm.axb_from_energy(-2.0, self.p), -1.0)
        hard = cm.sag_specific_energy(self.ore(27), self.p)
        self.assertAlmostEqual(cm.axb_from_energy(hard, self.p), 27.0, places=6)

    def test_bond_roundtrip_and_edges(self):
        p = self.p
        for p80 in (120.0, 180.0, 280.0):
            q = cm.ball_q_for_p80(20500, 20.0, p80, p)
            self.assertAlmostEqual(cm.ball_p80_um(q, 20500, 20.0, p), p80, places=6)
        self.assertEqual(cm.ball_q_for_p80(20500, 19.4, p["ball_f80_um"] * 2, p), INF)
        self.assertEqual(cm.ball_q_for_p80(0.0, 19.4, 180, p), 0.0)
        self.assertEqual(cm.ball_p80_um(3853, 0.0, 19.4, p), -1.0)
        # more feed on the same power -> coarser grind
        self.assertLess(cm.ball_p80_um(3000, 41000, 19.4, p), cm.ball_p80_um(4000, 41000, 19.4, p))

    def test_bond_capped_on_small_feed(self):
        """41 MW over a small fresh feed: the cyclones, not Bond, set the overflow."""
        p = self.p
        p_min = p["ball_p80_min_um"]
        for q in (1000.0, 500.0, 10.0):
            self.assertAlmostEqual(cm.ball_p80_um(q, 41000, 19.4, p), p_min, places=6)
        self.assertGreater(cm.ball_p80_um(3000, 41000, 19.4, p), p_min)       # 122 um: Bond still holds
        self.assertAlmostEqual(cm.ball_p80_um(2960, 41000, 20.9, p), 134.3, delta=0.5)   # C3 unchanged
        q_min = cm.ball_q_for_p80(41000, 19.4, p_min, p)
        self.assertAlmostEqual(cm.ball_p80_um(q_min * 0.999, 41000, 19.4, p), p_min, places=6)
        self.assertGreater(cm.ball_p80_um(q_min * 1.01, 41000, 19.4, p), p_min)

    def test_line_feed_cap_none_running(self):
        balls = initial_state(self.p).line(1).balls
        for b in balls:
            b.state = "STOP"
        self.assertEqual(cm.line_feed_cap_tph(balls, 19.4, self.p), 0.0)


class TestUnitDetails(unittest.TestCase):
    def setUp(self):
        self.p = prm()
        self.st = initial_state(self.p)
        self.ln = self.st.line(1)
        self.base = OreProps(0.41, 5.0, 35.0, 19.4)
        self.hard = OreProps(0.41, 5.0, 27.0, 20.9)

    def step(self, ore=None, avail=1e6, cap=INF, dt=1.0, fx=None, z=0.0):
        return cm.sag_step(self.ln.sag, self.ln.pebble, avail, ore or self.base, cap,
                           fx or CauseEffects(), dt, self.p, z)

    def run_sag(self, minutes, **kw):
        dt = kw.get("dt", 1.0)
        q = 0.0
        for _ in range(int(round(minutes / dt))):
            q = self.step(**kw)
        return q

    # -- SAG --
    def test_load_lag_exact_for_any_dt(self):
        e = cm.sag_specific_energy(self.base, self.p)
        cap = 2800 * e                                  # above the ball-charge draw (18.2 MW): speed stays
        self.assertGreater(cap, 26000 * cm.ball_floor_ratio(self.p["sag_speed_pct"], self.p))
        j0 = self.p["sag_load0_pct"]
        other = initial_state(self.p).line(1)
        self.run_sag(10, cap=cap, dt=1.0)
        cm.sag_step(other.sag, other.pebble, 1e6, self.base, cap, CauseEffects(), 10.0, self.p, 0.0)
        self.assertAlmostEqual(self.ln.sag.load_pct, other.sag.load_pct, places=9)
        j_t = cm.load_for_power_ratio(cap / 26000.0, 76, self.p)
        expect = j_t + (j0 - j_t) * math.exp(-10.0 / self.p["sag_tau_min"])
        self.assertAlmostEqual(other.sag.load_pct, expect, places=9)
        # one time constant: 63 % of the way
        third = initial_state(self.p).line(1)
        cm.sag_step(third.sag, third.pebble, 1e6, self.base, cap, CauseEffects(),
                    self.p["sag_tau_min"], self.p, 0.0)
        self.assertAlmostEqual((j0 - third.sag.load_pct) / (j0 - j_t), 1 - math.exp(-1), places=9)

    def test_power_follows_load_not_feed(self):
        e = cm.sag_specific_energy(self.base, self.p)
        q = self.step(cap=2650 * e)
        self.assertAlmostEqual(q, 2650, delta=1)
        # load still high after 1 min, but the drive does not draw above the cap (sim/audit.py found it did, 25.10.2026)
        self.assertLessEqual(self.ln.sag.power_kw, 2650 * e + 1e-6)
        self.assertAlmostEqual(self.ln.sag.power_kw, 2650 * e, delta=20)
        self.run_sag(60, cap=2650 * e)
        self.assertAlmostEqual(self.ln.sag.power_kw, 2650 * e, delta=20)
        # cap below the ball-charge draw (one ball mill): the slowed mill reaches the cap
        self.run_sag(60, cap=1925 * e)
        self.assertAlmostEqual(self.ln.sag.power_kw, 1925 * e, delta=20)

    def test_reline_and_stop(self):
        sag = self.ln.sag
        p = self.p
        j0, jb = p["sag_load0_pct"], p["sag_ball_load_pct"]
        x0, w0 = sag.liner_x, sag.liner_wear_mm
        sag.state = "RELINE"
        q = self.step(dt=p["sag_tau_min"])
        self.assertEqual(q, 0.0)
        self.assertEqual(sag.state, "RELINE")
        self.assertEqual((sag.power_kw, sag.feed_tph), (0.0, 0.0))
        self.assertEqual((sag.e_kwh_t, sag.axb_soft), (-1.0, -1.0))
        # ground out for relining: the rock goes, the ball charge stays
        self.assertAlmostEqual(sag.load_pct, jb + (j0 - jb) * math.exp(-1), places=9)
        self.run_sag(120)
        self.assertAlmostEqual(sag.load_pct, jb, delta=1e-6)
        self.assertEqual((sag.liner_x, sag.liner_wear_mm), (x0, w0))
        self.assertEqual(self.ln.pebble.feed_tph, 0.0)
        sag.state = "RUN"
        self.assertAlmostEqual(self.run_sag(60), 3853, delta=10)
        self.assertAlmostEqual(sag.load_pct, j0, delta=0.01)

    def test_stop_keeps_charge(self):
        """A stopped mill keeps its charge: after a restart the power is back at once."""
        sag = self.ln.sag
        j0 = self.p["sag_load0_pct"]
        sag.state = "STOP"
        for _ in range(240):
            self.assertEqual(self.step(), 0.0)
        self.assertEqual(sag.state, "STOP")
        self.assertEqual(sag.power_kw, 0.0)
        self.assertAlmostEqual(sag.load_pct, j0, places=9)
        sag.state = "RUN"
        self.step()
        self.assertAlmostEqual(sag.power_kw, 26000, delta=300)

    def test_pebble_crusher_stopped(self):
        peb = self.ln.pebble
        peb.state = "STOP"
        q = self.run_sag(60)
        e = cm.sag_specific_energy(self.base, self.p, False)
        self.assertAlmostEqual(q, 26000 / e, delta=1)
        self.assertAlmostEqual(q, 3635, delta=5)
        self.assertEqual((peb.state, peb.feed_tph, peb.load_pct), ("STOP", 0.0, 0.0))
        # hard ore with stopped pebble crusher: no pebble limit, E x 1.10
        q = self.run_sag(60, ore=self.hard)
        self.assertAlmostEqual(q, 26000 / cm.sag_specific_energy(self.hard, self.p, False), delta=1)

    def test_pebble_limit_released(self):
        self.run_sag(60, ore=self.hard)
        self.assertEqual(self.ln.pebble.state, "LIMIT")
        self.assertAlmostEqual(self.ln.pebble.feed_tph, self.p["peb_limit_tph"], delta=1e-6)
        self.assertLess(self.ln.sag.power_kw, 26000 * 0.96)          # pebble limit, not power
        self.assertAlmostEqual(self.run_sag(60), 3853, delta=10)
        self.assertEqual(self.ln.pebble.state, "RUN")

    def test_hard_ore_power_only_without_pebble_limit(self):
        p = prm(peb_limit_tph=792)
        ln = initial_state(p).line(1)
        q = 0.0
        for _ in range(60):
            q = cm.sag_step(ln.sag, ln.pebble, 1e6, self.hard, INF, CauseEffects(), 1.0, p, 0.0)
        # node at the top of its range: power binds (3130 t/h), pebbles 783 t/h in the warning band
        self.assertAlmostEqual(q, 26000 / cm.sag_specific_energy(self.hard, p), delta=1)
        self.assertLess(ln.pebble.feed_tph, 792)
        self.assertEqual(ln.pebble.state, "LIMIT")
        # blend 50/50 with A*b 40 (DWi averaged): pebbles drop below the limit
        axb_blend = 2 / (1 / 27 + 1 / 40)
        q = self.run_sag(60, ore=OreProps(0.41, 5.0, axb_blend, 20.0))
        self.assertLess(self.ln.pebble.feed_tph, self.p["peb_limit_tph"])
        self.assertAlmostEqual(q, 26000 / cm.sag_specific_energy(OreProps(0, 0, axb_blend, 0), self.p), delta=2)

    def test_starved_partial_feed(self):
        q = self.run_sag(60, avail=2000)
        sag = self.ln.sag
        e = cm.sag_specific_energy(self.base, self.p)
        self.assertEqual(q, 2000)
        self.assertEqual(sag.state, "STARVED")
        # 2000 t/h needs less than the ball charge draws: the mill draws the ball-charge power
        floor_kw = 26000 * cm.ball_floor_ratio(76, self.p)
        self.assertGreater(floor_kw, 2000 * e)
        self.assertAlmostEqual(sag.power_kw, floor_kw, delta=30)
        self.assertEqual(sag.speed_pct, self.p["sag_speed_pct"])         # starving does not slow the mill
        self.assertEqual(sag.axb_soft, -1.0)
        self.assertGreater(sag.e_kwh_t, e)
        # 3000 t/h needs more than the ball charge: power follows the feed
        q = self.run_sag(60, avail=3000)
        self.assertEqual(sag.state, "STARVED")
        self.assertAlmostEqual(sag.power_kw, 3000 * e, delta=30)

    def test_grid_cap_states(self):
        sag = self.ln.sag
        self.step(cap=27000)
        self.assertEqual(sag.state, "RUN")
        self.assertEqual(sag.power_limit_kw, 27000)
        self.step()
        self.assertEqual(sag.power_limit_kw, self.p["sag_rated_mw"] * 1000)
        q = self.step(cap=0.0)
        self.assertEqual(q, 0.0)
        self.assertEqual(sag.state, "LIMITED_GRID")

    def test_noise_and_soft_sensor(self):
        self.run_sag(30)
        self.step(z=1.0)
        sag = self.ln.sag
        self.assertAlmostEqual(sag.power_kw, 26000 * (1 + self.p["sag_power_sigma"]), delta=30)
        self.assertLess(sag.axb_soft, 35.0)
        self.step(z=0.0)
        self.assertAlmostEqual(sag.axb_soft, 35.0, delta=0.05)
        self.step(z=1e3)
        self.assertEqual(sag.power_kw, self.p["sag_rated_mw"] * 1000)

    def test_hidden_liner_cause(self):
        fx = CauseEffects(sag_eta_mult=1 - self.p["hc_liner_eta_loss"], liner_wear_mult=self.p["hc_liner_wear_mult"])
        sag = self.ln.sag
        x0, w0 = sag.liner_x, sag.liner_wear_mm
        q = self.run_sag(600, dt=10.0, fx=fx)
        self.assertAlmostEqual(q, 3853 * 0.96, delta=10)
        mt = q * 10 / 1e6
        self.assertAlmostEqual(sag.liner_wear_mm - w0, 20.41 * mt, delta=0.01)
        self.assertAlmostEqual((sag.liner_x - x0) * self.p["liner_life_mt"], 1.5 * mt, delta=1e-3)
        # soft sensor reads the worn liner as harder ore
        self.assertAlmostEqual(sag.axb_soft, 35 * 0.96 ** (1 / 0.8), delta=0.1)
        self.assertAlmostEqual(sag.eta, cm.liner_eta(sag.liner_x, self.p) * 0.96, delta=1e-4)

    def test_missing_ore_keeps_last_blend(self):
        self.run_sag(10, ore=self.hard)
        q = self.step(ore=OreProps())
        self.assertAlmostEqual(q, 2960, delta=15)
        self.assertEqual(self.ln.sag.feed_ore.axb, 27.0)

    def test_deterministic(self):
        from sim.state import normal
        a = initial_state(self.p).line(1)
        b = initial_state(self.p).line(1)
        for k in range(50):
            z = normal(42, k, "sag-power")
            for ln in (a, b):
                cm.sag_step(ln.sag, ln.pebble, 4000 if k % 7 else 500, self.base, INF, CauseEffects(),
                            1.0, self.p, z)
        self.assertEqual(a.sag, b.sag)
        self.assertEqual(a.pebble, b.pebble)

    # -- crusher --
    def test_crusher_faults(self):
        cr = self.ln.crusher
        cr.fault = "scenario"
        self.assertEqual(cm.crusher_step(cr, 4000, 1e6, self.p, 0.0), 0.0)
        self.assertEqual((cr.state, cr.fault, cr.power_kw), ("STOP", "scenario", 0.0))
        self.assertEqual(cr.lube_kpa, self.p["crush_lube_kpa"])
        cr.fault = ""
        self.assertEqual(cm.crusher_step(cr, 4000, 1e6, self.p, 0.0), 4000)
        self.assertEqual(cr.state, "RUN")
        self.assertEqual(cr.power_kw, self.p["crush_power_mw"] * 1000)
        # noise alone trips only far in the tail
        self.assertEqual(cm.crusher_step(cr, 4000, 1e6, self.p, -3.0), 4000)
        self.assertEqual(cm.crusher_step(cr, 4000, 1e6, self.p, -21.0), 0.0)
        self.assertEqual(cr.fault, "lube_trip")

    def test_crusher_empty_pocket_and_full_stock(self):
        cr = self.ln.crusher
        self.assertEqual(cm.crusher_step(cr, -5.0, 1e6, self.p, 0.0), 0.0)
        self.assertEqual(cr.state, "RUN")
        self.assertEqual(cm.crusher_step(cr, 4000, 0.0, self.p, 0.0), 0.0)
        self.assertEqual(cr.state, "SLOW")
        self.assertEqual(cm.crusher_step(cr, 1000, 1000, self.p, 0.0), 1000)
        self.assertEqual(cr.state, "RUN")

    # -- ball mills and cyclones --
    def test_one_ball_mill(self):
        balls = self.ln.balls
        balls[1].state = "STOP"
        p80 = cm.ball_step(balls, 2650, 19.4, self.p)
        self.assertAlmostEqual(p80, 279, delta=1)
        self.assertEqual((balls[1].power_kw, balls[1].e_kwh_t), (0.0, 0.0))
        self.assertAlmostEqual(balls[0].e_kwh_t, 20500 / 2650)
        self.assertEqual(cm.ball_step(balls, 0.0, 19.4, self.p), -1.0)
        self.assertEqual(balls[0].e_kwh_t, -1.0)
        self.assertEqual(balls[0].power_kw, 20500)

    def test_ball_specific_energy_two_mills(self):
        # each mill grinds Q / 2: 20.5 MW x 2 / 3853 t/h = 10.6 kWh/t, the Bond energy of the line
        balls = self.ln.balls
        p80 = cm.ball_step(balls, 3853, 19.4, self.p)
        for b in balls:
            self.assertAlmostEqual(b.e_kwh_t, 2 * 20500 / 3853, places=9)
            self.assertAlmostEqual(b.e_kwh_t, 10.64, delta=0.01)
        bond = 10 * 19.4 * (1 / math.sqrt(p80) - 1 / math.sqrt(self.p["ball_f80_um"]))
        self.assertAlmostEqual(balls[0].e_kwh_t, bond, places=6)
        st = initial_state(self.p)
        self.assertAlmostEqual(st.line(1).balls[0].e_kwh_t, 2 * 20500 / self.p["cal_line_tph"], places=9)

    def test_feed_end_counter_restarts(self):
        sag, peb = self.ln.sag, self.ln.pebble
        cap = self.p["liner_feed_end_mm"]
        self.assertAlmostEqual(cap, 20.41 * 9.96, places=9)
        sag.liner_wear_mm = cap - 0.01
        q = cm.sag_step(sag, peb, 1e6, self.base, INF, CauseEffects(), 60.0, self.p, 0.0)
        worn = 20.41 * q / 1e6                                                          # one hour, mm
        self.assertGreater(worn, 0.01)
        self.assertAlmostEqual(sag.liner_wear_mm, worn - 0.01, places=9)                # feed end changed
        for x in (0.0, 30.0, 48.0):
            self.assertLess(feed_end_wear_mm(20.41 * x, self.p), cap)

    def test_cyclone_edges(self):
        cy = self.ln.cyclones
        p80 = cm.cyclone_step(cy, 3853, 185.0, self.p)
        self.assertEqual(cm.cyclone_step(cy, 0.0, 185.0, self.p), p80)
        self.assertEqual((cy.pressure_kpa, cy.state), (0.0, "NORMAL"))
        self.assertEqual(cm.cyclone_step(cy, 3853, -1.0, self.p), p80)
        # cluster control at half flow keeps pressure: 5 open, no UPSET
        cm.cyclone_step(cy, 1925, 180.0, self.p)
        self.assertEqual(cy.open_count, 5)
        self.assertAlmostEqual(cy.pressure_kpa, self.p["cyc_pressure_kpa"], delta=1.0)
        self.assertEqual(cy.state, "NORMAL")
        # very low flow cannot be balanced
        cm.cyclone_step(cy, 100, 180.0, self.p)
        self.assertEqual((cy.open_count, cy.state), (1, "UPSET"))
        # two clogged units stay hidden: +24 um, +6 % pressure, still NORMAL
        cy.clogged = 2
        self.assertAlmostEqual(cm.cyclone_step(cy, 3853, 180.0, self.p), 204.0, places=9)
        self.assertEqual((cy.open_count, cy.state), (10, "NORMAL"))
        self.assertAlmostEqual(cy.p80_grind_um, 180.0)


class TestScenarioChains(unittest.TestCase):
    """Design section 7: C2 (one ball mill) and C3 (pebble limit) through the unit steps."""

    def setUp(self):
        self.p = prm()
        self.ln = initial_state(self.p).line(2)
        self.base = OreProps(0.41, 5.0, 35.0, 19.4)

    def run_line(self, ore, cap_kw, minutes=60):
        ln = self.ln
        q = 0.0
        for _ in range(minutes):
            q = cm.sag_step(ln.sag, ln.pebble, 1e6, ore, cap_kw, CauseEffects(), 1.0, self.p, 0.0)
        p80 = cm.ball_step(ln.balls, q, ore.bwi, self.p)
        return q, cm.cyclone_step(ln.cyclones, q, p80, self.p)

    def test_c2_line_rule(self):
        self.ln.balls[1].state = "STOP"
        cap_tph = cm.line_feed_cap_tph(self.ln.balls, self.base.bwi, self.p)
        e = cm.sag_specific_energy(self.base, self.p)
        cap_kw = cm.sag_power_for_tph(cap_tph, e, self.ln.sag.eta)
        q, p80 = self.run_line(self.base, cap_kw)
        self.assertAlmostEqual(q, 1925, delta=15)
        self.assertAlmostEqual(p80, self.p["ball_p80_target_um"], delta=0.5)
        self.assertEqual(self.ln.sag.state, "LIMITED_GRID")
        self.assertAlmostEqual(self.ln.sag.power_kw / 1000, 13.0, delta=0.2)
        self.assertEqual(self.ln.cyclones.state, "NORMAL")

    def test_c2_call_gives_tonnes_for_grind(self):
        self.ln.balls[1].state = "STOP"
        e = cm.sag_specific_energy(self.base, self.p)
        extra_kw = self.p["pow_call_use_mw"] * 1000 * self.p["pow_motor_eff"]
        q, p80 = self.run_line(self.base, 1925 * e + extra_kw)
        self.assertAlmostEqual(q, 2650, delta=20)
        self.assertAlmostEqual(p80, 280, delta=4)

    def test_c3_hard_ore(self):
        hard = OreProps(0.41, 5.0, self.p["ore_axb_hard"], self.p["ore_bwi_hard"])
        q, p80 = self.run_line(hard, INF)
        self.assertAlmostEqual(q, 2960, delta=15)
        self.assertAlmostEqual(p80, 134, delta=1)
        self.assertEqual(self.ln.pebble.state, "LIMIT")
        power_only = cm.sag_capacity_tph(26000, cm.sag_specific_energy(hard, self.p), 1.0)
        self.assertAlmostEqual(1 - power_only / 3853, 0.19, delta=0.01)   # "power -19 %"
        self.assertAlmostEqual(1 - q / 3853, 0.23, delta=0.01)            # "-23 %"


class TestNumbersFromParams(unittest.TestCase):
    """Every number of the model comes from the parameter table (contest rule)."""

    def setUp(self):
        import os
        self.path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 "sim", "comminution.py")
        with open(self.path, encoding="utf-8") as f:
            self.src = f.read()

    def test_keys_exist_with_source_and_label(self):
        import re
        from sim import params
        keys = set(re.findall(r'prm\["([a-z0-9_]+)"\]', self.src))
        self.assertGreater(len(keys), 30)
        for k in sorted(keys):
            self.assertIn(k, params.TABLE, k)
            row = params.TABLE[k]
            self.assertIn(row.label, params.LABELS, k)
            self.assertTrue(row.source and row.unit, k)

    def test_no_bare_numbers(self):
        import io
        import re
        import tokenize
        allowed = {0.0, 1.0, 2.0, 4.0, 0.5}
        const_line = re.compile(r"^[A-Z_]+ = ")
        lines = self.src.splitlines()
        for tok in tokenize.generate_tokens(io.StringIO(self.src).readline):
            if tok.type != tokenize.NUMBER:
                continue
            line = lines[tok.start[0] - 1]
            if const_line.match(line):
                continue
            self.assertIn(float(tok.string), allowed, f"line {tok.start[0]}: {line.strip()}")

    def test_lf_line_endings(self):
        with open(self.path, "rb") as f:
            self.assertNotIn(b"\r\n", f.read())


if __name__ == "__main__":
    unittest.main()
