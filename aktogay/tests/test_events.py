"""Acceptance tests of sim.events (scenarios, hidden causes, stops, crews)."""
import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # aktogay/: packages sim, tests
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sim import events as ev
from sim.state import NO_VALUE, CrewState, HiddenCause, PlannedCall
from tests.support import needs_impl, prm

T0 = 8 * 60.0   # 08:00 of day 0


class TestScenario(unittest.TestCase):
    def setUp(self):
        self.p = prm()

    @needs_impl
    def test_parse(self):
        s = ev.parse_scenario("crusher:1+grid", T0, self.p)
        self.assertEqual([e.kind for e in s.events], ["crusher", "grid"])
        self.assertEqual(s.events[0].line, 1)
        self.assertEqual(s.events[1].data["limit_mw"], self.p["pow_c2_limit_mw"])
        self.assertFalse(s.auto)
        h = ev.parse_scenario("hard:1", T0, self.p).events[0]
        self.assertEqual((h.data["axb"], h.data["bwi"]), (27.0, 20.9))
        with self.assertRaises(ValueError):
            ev.parse_scenario("meteor:1", T0, self.p)
        with self.assertRaises(ValueError):
            ev.parse_scenario("crusher:3", T0, self.p)

    @needs_impl
    def test_fork_preset(self):
        s = ev.parse_scenario("", T0, self.p, preset="fork", safety=True)
        kinds = {e.kind: e for e in s.events}
        self.assertAlmostEqual(kinds["dose"].t_start_min, 8 * 60)
        self.assertAlmostEqual(kinds["trip"].t_start_min, 9 * 60 + 20)
        self.assertEqual(kinds["trip"].line, 2)
        self.assertAlmostEqual(kinds["safety"].t_start_min, T0 + 10)
        self.assertTrue(s.auto)
        self.assertEqual(s.kip, 1)
        causes = ev.preset_causes(s, self.p)
        self.assertEqual([(c.kind, c.line, c.preset) for c in causes], [("dose", 1, True)])

    def test_fork_token_selects_preset(self):
        # the button "Два сразу" sends {id: "fork", preset: "fork"}; ?scenario=fork sends the token alone
        for text, preset in (("fork", "fork"), ("fork", ""), ("FORK+grid", "")):
            s = ev.parse_scenario(text, T0, self.p, preset=preset)
            self.assertEqual(s.preset, "fork")
            self.assertTrue(s.auto)
            self.assertEqual({e.kind for e in s.events} - {"grid"}, {"dose", "trip"})
            self.assertNotIn("fork", s.text)
        self.assertEqual(ev.scenario_label(ev.parse_scenario("fork", T0, self.p)), "fork")

    @needs_impl
    def test_cause_effects(self):
        p = self.p
        cs = [HiddenCause("dose", 1, T0, 0.4), HiddenCause("liner", 2, T0, 0.04),
              HiddenCause("oxide", 1, T0, 2.0, t_end_min=T0 + 60)]
        fx = ev.cause_effects(cs, 1, T0 + 15, p)
        self.assertAlmostEqual(fx.dose_ratio, 0.8)
        self.assertAlmostEqual(fx.ascu_add_pp, 2.0)
        self.assertEqual(fx.sag_eta_mult, 1.0)
        self.assertAlmostEqual(ev.cause_effects(cs, 1, T0 + 90, p).dose_ratio, 0.6)
        self.assertEqual(ev.cause_effects(cs, 1, T0 + 90, p).ascu_add_pp, 0.0)
        fx2 = ev.cause_effects(cs, 2, T0 + 1, p)
        self.assertAlmostEqual(fx2.sag_eta_mult, 0.96)
        self.assertAlmostEqual(fx2.liner_wear_mult, 1.5)


class TestRandomEvents(unittest.TestCase):
    def setUp(self):
        self.p = prm()

    @needs_impl
    def test_hidden_causes(self):
        days = 30
        cs = ev.draw_hidden_causes(42, 0.0, days * 1440.0, self.p)
        self.assertEqual(cs, ev.draw_hidden_causes(42, 0.0, days * 1440.0, self.p))
        self.assertTrue(30 <= len(cs) <= 2 * days, len(cs))
        for a, b in zip(cs, cs[1:]):
            self.assertLessEqual(a.t_end_min, b.t_start_min)
        for c in cs:
            self.assertIn(c.kind, ev.HIDDEN)
            self.assertTrue(240 <= c.t_found_min - c.t_start_min <= 360)
            self.assertFalse(c.preset)

    @needs_impl
    def test_pebble_stop_share(self):
        year = 365 * 1440.0
        w = ev.draw_pebble_stops(42, 1, 0.0, year, self.p)
        share = sum(b - a for a, b in w) / year
        self.assertAlmostEqual(share, 1 - self.p["peb_kio"], delta=0.02)
        self.assertTrue(all(60 <= b - a <= 240 for a, b in w))

    @needs_impl
    def test_line_downtime(self):
        year = 365 * 1440.0
        fixed = [(200 * 1440.0, 200 * 1440.0 + 126 * 60)]
        w = ev.draw_line_downtime(42, 2, 0.0, year, 0.93, fixed, self.p)
        self.assertIn(fixed[0], w)
        self.assertAlmostEqual(sum(b - a for a, b in w) / year, 0.07, delta=0.002)
        for a, b in zip(w, w[1:]):
            self.assertLessEqual(a[1], b[0])


class TestCrews(unittest.TestCase):
    def setUp(self):
        self.p = prm()

    @needs_impl
    def test_repair_times(self):
        p = self.p
        self.assertAlmostEqual(ev.p90_hours(3.0, p), 5.0, delta=0.02)
        xs = sorted(ev.repair_hours(42, f"k{i}", 3.0, p) for i in range(2001))
        self.assertAlmostEqual(xs[1000], 3.0, delta=0.2)
        a = ev.arrival_min(42, "x", p)
        self.assertTrue(20 <= a <= 40)
        self.assertTrue(5 <= ev.notice_delay_min(42, "x", p) <= 15)
        self.assertEqual(ev.work_median_h("crusher", p), 3.0)
        self.assertEqual(ev.work_median_h("dose", p), 0.5)

    @needs_impl
    def test_single_kip_queue(self):
        crew = CrewState("crew-kip", "kip", count=1, slot_free_min=[NO_VALUE])
        j1 = ev.crew_call(crew, PlannedCall(T0, "flot-1", "crew-kip", "dose:1"), 30.0, 0.5)
        j2 = ev.crew_call(crew, PlannedCall(T0, "crusher-2", "crew-kip", "trip:2"), 30.0, 3.0)
        self.assertAlmostEqual(j1.t_done_min, T0 + 60)
        self.assertAlmostEqual(j2.t_arrive_min, T0 + 90)
        self.assertAlmostEqual(j2.t_done_min, T0 + 270)
        self.assertEqual(ev.crew_step(crew, T0 + 10, 1.0), [])
        self.assertEqual(crew.state, "TRAVEL")
        self.assertEqual(ev.crew_step(crew, T0 + 60, 1.0), [j1])
        ev.crew_step(crew, T0 + 100, 1.0)
        self.assertEqual((crew.state, crew.task), ("WORK", "crusher-2"))

    @needs_impl
    def test_two_kip_parallel(self):
        crew = CrewState("crew-kip", "kip", count=2, slot_free_min=[NO_VALUE, NO_VALUE])
        ev.crew_call(crew, PlannedCall(T0, "flot-1", "crew-kip", "dose:1"), 30.0, 0.5)
        j2 = ev.crew_call(crew, PlannedCall(T0, "crusher-2", "crew-kip", "trip:2"), 30.0, 3.0)
        self.assertAlmostEqual(j2.t_arrive_min, T0 + 30)

    @needs_impl
    def test_fork_policies(self):
        s = ev.parse_scenario("", T0, self.p, preset="fork")
        pol = ev.fork_policies(s, self.p, 42)
        self.assertEqual(set(pol), {"by_value", "loud", "no_twin"})
        loud = [c.issue for c in sorted(pol["loud"], key=lambda c: c.t_min)]
        self.assertEqual(loud[0], "trip:2")
        by_value = [c.issue for c in sorted(pol["by_value"], key=lambda c: c.t_min)]
        self.assertEqual(by_value, ["dose:1", "trip:2"])
        dose_nt = [c for c in pol["no_twin"] if c.issue == "dose:1"][0]
        self.assertAlmostEqual(dose_nt.t_min, 14 * 60)
        self.assertTrue(all(c.crew == "crew-kip" for c in pol["loud"] + pol["no_twin"] + pol["by_value"]))
        self.assertTrue(all(math.isfinite(c.work_h) and c.work_h > 0 for c in pol["loud"]))


# ---------------------------------------------------------------------------
# Detailed checks (events implementation)
# ---------------------------------------------------------------------------
class TestScenarioDetails(unittest.TestCase):
    def setUp(self):
        self.p = prm()

    def test_text_forms_and_dedup(self):
        s = ev.parse_scenario(" Hard:1 GRID,hard:1+crusher:2 ", T0, self.p)
        self.assertEqual(s.text, "hard:1+grid+crusher:2")
        self.assertEqual([(e.kind, e.line) for e in s.events], [("hard", 1), ("grid", 0), ("crusher", 2)])
        self.assertEqual(ev.parse_scenario("", T0, self.p).events, [])

    def test_errors(self):
        p = self.p
        for bad in ("crusher", "crusher:x", "crusher:0", "grid:1", "dose:9"):
            with self.assertRaises(ValueError, msg=bad):
                ev.parse_scenario(bad, T0, p)
        with self.assertRaises(ValueError):
            ev.parse_scenario("", T0, p, preset="meteor")
        with self.assertRaises(ValueError):
            ev.parse_scenario("grid", T0, p, kip=0)

    def test_event_parameters(self):
        p = self.p
        s = ev.parse_scenario("crusher:1+reline:2+dose:2+cyclone:1+liner:2+oxide:1", T0, p, kip=2,
                              safety=True, auto=True)
        k = {(e.kind, e.line): e for e in s.events}
        self.assertEqual(k[("crusher", 1)].duration_h, p["crush_repair_h"])
        self.assertEqual(k[("crusher", 1)].data["crew"], "crew-cpd")
        self.assertEqual(k[("reline", 2)].duration_h, p["liner_reline_h"])
        self.assertEqual(k[("reline", 2)].data["node"], "sag-2")
        self.assertEqual(k[("dose", 2)].data["drop"], p["hc_dose_drop"])
        self.assertEqual(k[("cyclone", 1)].data["n"], p["hc_cyclone_n"])
        self.assertEqual(k[("liner", 2)].data["loss"], p["hc_liner_eta_loss"])
        self.assertEqual(k[("oxide", 1)].data["ascu_pp"], p["hc_oxide_ascu_pp"])
        self.assertEqual(k[("safety", 0)].data["flag"], "piezo")
        self.assertEqual((s.kip, s.safety, s.auto), (2, True, True))
        self.assertEqual([e.t_start_min for e in s.events], sorted(e.t_start_min for e in s.events))

    def test_fork_details(self):
        p = self.p
        s = ev.parse_scenario("dose:1", T0, p, preset="fork", auto=False)
        self.assertFalse(s.auto)
        self.assertEqual(sum(e.kind == "dose" for e in s.events), 1)
        trip = [e for e in s.events if e.kind == "trip"][0]
        self.assertEqual(trip.duration_h, p["crew_trip_fix_h"])
        self.assertEqual(trip.data["crew"], "crew-kip")
        reading = p["crush_lube_kpa"] + trip.data["bias_kpa"]
        self.assertLess(reading + 4 * p["crush_lube_noise_kpa"], p["crush_lube_trip_kpa"])

    def test_label_hides_hidden_causes(self):
        s = ev.parse_scenario("hard:1+dose:2", T0, self.p, preset="fork", safety=True)
        self.assertEqual(ev.scenario_label(s), "fork+hard:1+dose:2+safety")
        self.assertEqual(ev.scenario_label(s, hidden=False), "fork+hard:1+safety")
        self.assertEqual(ev.scenario_label(None), "")

    def test_preset_causes(self):
        s = ev.parse_scenario("cyclone:2+crusher:1+oxide:1", T0, self.p)
        cs = ev.preset_causes(s, self.p)
        self.assertEqual([(c.kind, c.line, c.magnitude) for c in cs],
                         [("cyclone", 2, 1.0), ("oxide", 1, 2.0)])
        self.assertTrue(all(c.preset and c.t_end_min == NO_VALUE for c in cs))


class TestCauseEffectsDetails(unittest.TestCase):
    def setUp(self):
        self.p = prm()

    def test_combined(self):
        p = self.p
        cs = [HiddenCause("cyclone", 1, T0, 1.0), HiddenCause("cyclone", 1, T0, 2.0),
              HiddenCause("liner", 1, T0, 0.04), HiddenCause("liner", 1, T0, 0.02),
              HiddenCause("dose", 1, T0 + 100, 0.4)]
        fx = ev.cause_effects(cs, 1, T0 + 10, p)
        self.assertEqual(fx.clogged, 3)
        self.assertAlmostEqual(fx.sag_eta_mult, 0.96 * 0.98)
        self.assertEqual(fx.dose_ratio, 1.0)             # dose cause not started yet
        many = [HiddenCause("cyclone", 1, T0, 50.0)]
        self.assertEqual(ev.cause_effects(many, 1, T0, p).clogged, int(p["cyc_open"]))
        with self.assertRaises(ValueError):
            ev.cause_effects([HiddenCause("meteor", 1, T0, 1.0)], 1, T0, p)

    def test_ends_at_t_end(self):
        c = [HiddenCause("liner", 1, T0, 0.04, t_end_min=T0 + 30)]
        self.assertAlmostEqual(ev.cause_effects(c, 1, T0 + 29.9, self.p).sag_eta_mult, 0.96)
        self.assertEqual(ev.cause_effects(c, 1, T0 + 30, self.p).sag_eta_mult, 1.0)


class TestRandomDetails(unittest.TestCase):
    def setUp(self):
        self.p = prm()

    def test_hidden_window_independent(self):
        p = self.p
        whole = ev.draw_hidden_causes(42, 0.0, 10 * 1440.0, p)
        parts = []
        for d in range(20):
            parts += ev.draw_hidden_causes(42, d * 720.0, (d + 1) * 720.0, p)
        self.assertEqual(whole, parts)
        self.assertNotEqual(whole, ev.draw_hidden_causes(43, 0.0, 10 * 1440.0, p))

    def test_hidden_rate_lines_kinds(self):
        p = self.p
        days = 120
        cs = ev.draw_hidden_causes(7, 0.0, days * 1440.0, p, lines=(2,))
        per_shift = len(cs) / (2 * days)
        self.assertTrue(0.8 <= per_shift <= 1.0, per_shift)
        self.assertTrue(all(c.line == 2 for c in cs))
        self.assertEqual({c.kind for c in cs}, set(ev.HIDDEN))
        self.assertTrue(all(c.found_by == "lab" and c.t_end_min == c.t_found_min for c in cs))
        half = ev.draw_hidden_causes(7, 0.0, days * 1440.0, prm(hc_per_shift=0.5))
        self.assertTrue(0.35 <= len(half) / (2 * days) <= 0.55, len(half))
        two = ev.draw_hidden_causes(7, 0.0, days * 1440.0, prm(hc_per_shift=2.0))
        for a, b in zip(two, two[1:]):
            self.assertLessEqual(a.t_end_min, b.t_start_min)
        self.assertGreater(len(two), len(cs))

    def test_pebble_windows(self):
        p = self.p
        year = ev.draw_pebble_stops(42, 2, 0.0, 365 * 1440.0, p)
        part = ev.draw_pebble_stops(42, 2, 100 * 1440.0, 101 * 1440.0, p)
        self.assertTrue(all(w in year for w in part))
        self.assertTrue(all(b > 100 * 1440.0 and a < 101 * 1440.0 for a, b in part))
        self.assertNotEqual(year, ev.draw_pebble_stops(42, 1, 0.0, 365 * 1440.0, p))
        self.assertEqual(ev.draw_pebble_stops(42, 1, 0.0, 1440.0, prm(peb_kio=1.0)), [])

    def test_downtime_cases(self):
        p = self.p
        span = 90 * 1440.0
        fixed = [(10 * 1440.0, 10 * 1440.0 + 126 * 60)]
        self.assertEqual(ev.draw_line_downtime(1, 1, 0.0, span, 1.0, fixed, p), fixed)
        self.assertEqual(ev.draw_line_downtime(1, 1, 0.0, span, 0.99, fixed, p), fixed)
        w = ev.draw_line_downtime(1, 1, 0.0, span, 0.85, fixed, p)
        self.assertAlmostEqual(sum(b - a for a, b in w) / span, 0.15, places=6)
        self.assertEqual(w, ev.draw_line_downtime(1, 1, 0.0, span, 0.85, fixed, p))
        for a, b in zip(w, w[1:]):
            self.assertLessEqual(a[1], b[0])
        self.assertTrue(all(0.0 <= a < b <= span for a, b in w))
        extra = [x for x in w if x not in fixed]
        self.assertTrue(all(b - a <= p["cal_stop_h_hi"] * 60 + 1e-6 for a, b in extra))
        self.assertEqual(ev.draw_line_downtime(1, 1, 0.0, 0.0, 0.9, fixed, p), [])


class TestCrewDetails(unittest.TestCase):
    def setUp(self):
        self.p = prm()

    def test_draws(self):
        p = self.p
        self.assertEqual(ev.repair_hours(42, "trip:2", 3.0, p), ev.repair_hours(42, "trip:2", 3.0, p))
        self.assertNotEqual(ev.repair_hours(42, "trip:2", 3.0, p), ev.repair_hours(43, "trip:2", 3.0, p))
        xs = sorted(ev.repair_hours(42, f"k{i}", 3.0, p) for i in range(2001))
        self.assertAlmostEqual(xs[1800], ev.p90_hours(3.0, p), delta=0.35)
        arr = [ev.arrival_min(42, f"a{i}", p) for i in range(500)]
        self.assertAlmostEqual(sum(arr) / len(arr), 30.0, delta=1.0)
        self.assertEqual(ev.work_median_h("crusher:1", p), p["crush_repair_h"])
        self.assertEqual(ev.work_median_h("trip", p), p["crew_trip_fix_h"])
        self.assertEqual(ev.work_median_h("cyclone", p), p["crew_dose_fix_h"])

    def test_states_and_free_at(self):
        crew = CrewState("crew-kip", "kip", count=1, slot_free_min=[NO_VALUE])
        ev.crew_call(crew, PlannedCall(T0, "flot-1", "crew-kip", "dose:1"), 30.0, 0.5)
        self.assertAlmostEqual(crew.free_at_min, T0 + 60)
        ev.crew_step(crew, T0 + 40, 1.0)
        self.assertEqual((crew.state, crew.task), ("WORK", "flot-1"))
        self.assertEqual(len(ev.crew_step(crew, T0 + 61, 1.0)), 1)   # finished job returned once
        self.assertEqual(ev.crew_step(crew, T0 + 62, 1.0), [])
        self.assertEqual((crew.state, crew.task, crew.free_at_min), ("FREE", "", NO_VALUE))
        self.assertEqual(crew.slot_free_min, [NO_VALUE])
        self.assertEqual(crew.jobs, [])

    def test_two_teams_free_at(self):
        crew = CrewState("crew-mill", "plant_mech", count=2, slot_free_min=[])
        ev.crew_call(crew, PlannedCall(T0, "sag-1", "crew-mill", "liner:1"), 20.0, 1.0)
        self.assertEqual(crew.free_at_min, NO_VALUE)        # second team still free
        ev.crew_call(crew, PlannedCall(T0, "cyclones-2", "crew-mill", "cyclone:2"), 20.0, 2.0)
        self.assertAlmostEqual(crew.free_at_min, T0 + 80)
        ev.crew_step(crew, T0 + 30, 1.0)
        self.assertEqual((crew.state, crew.task), ("WORK", "sag-1,cyclones-2"))
        j3 = ev.crew_call(crew, PlannedCall(T0 + 30, "pebble-1", "crew-mill", "pebble:1"), 20.0, 1.0)
        self.assertAlmostEqual(j3.t_arrive_min, T0 + 100)    # waits for the first team

    def test_fork_policies_details(self):
        p = self.p
        s = ev.parse_scenario("", T0, p, preset="fork")
        pol = ev.fork_policies(s, p, 42)
        work = {}
        for calls in pol.values():
            for c in calls:
                work.setdefault(c.issue, set()).add(c.work_h)
        self.assertEqual({k: len(v) for k, v in work.items()}, {"dose:1": 1, "trip:2": 1})
        t_trip = [c.t_min for c in pol["loud"] if c.issue == "trip:2"][0]
        self.assertTrue(9 * 60 + 25 <= t_trip <= 9 * 60 + 35)
        self.assertEqual([c.t_min for c in pol["loud"]], [t_trip, t_trip])
        self.assertAlmostEqual([c.t_min for c in pol["by_value"] if c.issue == "dose:1"][0], 9 * 60 + 15)
        self.assertEqual([c.node for c in pol["no_twin"]], ["crusher-2", "flot-1"])
        self.assertEqual(pol, ev.fork_policies(s, p, 42))

    def test_fork_order_matters_only_with_one_kip(self):
        p = self.p
        s = ev.parse_scenario("", T0, p, preset="fork")
        pol = ev.fork_policies(s, p, 42)

        def dose_done(name, kip):
            crew = CrewState("crew-kip", "kip", count=kip, slot_free_min=[NO_VALUE] * kip)
            done = {}
            for c in pol[name]:
                done[c.issue] = ev.crew_call(crew, c, ev.arrival_min(42, c.issue, p), c.work_h).t_done_min
            return done["dose:1"]

        self.assertLess(dose_done("by_value", 1), dose_done("loud", 1) - 60)
        self.assertLess(dose_done("loud", 1), dose_done("no_twin", 1))
        self.assertAlmostEqual(dose_done("by_value", 2), dose_done("loud", 2), delta=20)


if __name__ == "__main__":
    unittest.main()
