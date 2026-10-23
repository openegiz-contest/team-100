"""Site passport twins: people of the shift, pit trucks / faces / roads, instruments, the new
scenarios (water, hpgr_fire, road) and the latched grid call (sim/people.py, sim/pit.py, sim/plant.py)."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sim import events  # noqa: E402
from sim import pit as pt  # noqa: E402
from sim import sensors as se  # noqa: E402
from sim import site_aktogay as site  # noqa: E402
from sim.plant import CopySet, Plant  # noqa: E402
from sim.state import NO_VALUE  # noqa: E402
from tests.support import prm  # noqa: E402


def start(text, **kw):
    pl = Plant(prm(), seed=42, mode="scenario")
    pl.warmup()
    pl.apply_scenario(events.parse_scenario(text, pl.t_min, pl.prm, **kw))
    return pl


class TestSitePassport(unittest.TestCase):
    def test_roster_and_fleet(self):
        roster = site.truck_roster()
        self.assertEqual(len(roster), 37)
        models = [r[1] for r in roster]
        self.assertEqual((models.count("CAT 777"), models.count("CAT 785"), models.count("CAT 793")), (2, 18, 17))
        ore = [r for r in roster if r[3] == "ore"]
        self.assertEqual(len(ore), 23)
        self.assertEqual(sum(1 for r in ore if r[4] == 1), 12)           # 9 CAT 793 + 3 CAT 785 on line 1
        self.assertEqual({r[3] for r in roster if r[1] == "CAT 777"}, {"waste"})
        self.assertEqual(len(site.PEOPLE), 9)
        self.assertEqual(len([e for e in site.EXCAVATORS if e[1] == "ore"]), 3)
        for typ, person in site.TYPE_PERSON.items():
            self.assertIn(person, {p[0] for p in site.PEOPLE}, typ)


class TestPeople(unittest.TestCase):
    def test_crew_job_moves_the_person(self):
        pl = start("crusher:1")
        p = pl.state.people["person-crusher-mech"]
        pl.step()
        self.assertEqual((p.state, p.location), ("FREE", "crusher-1"))     # home node
        job = pl.call("crusher-1")
        pl.step()
        self.assertEqual((p.state, p.task), ("TRAVEL", "crusher-1"))
        self.assertAlmostEqual(p.free_at_min, job.t_done_min)
        pl.run_until(job.t_arrive_min + 2)
        self.assertEqual((p.state, p.location), ("WORK", "crusher-1"))
        pl.run_until(job.t_done_min + 2)
        self.assertEqual((p.state, p.free_at_min), ("FREE", NO_VALUE))
        f = se.measured_features(pl.state, pl.prm)["person-crusher-mech"]
        self.assertEqual((f["state"], f["state_ru"], f["location"]), ("FREE", "свободен", "crusher-1"))

    def test_decision_goes_to_its_person(self):
        pl = start("grid")
        pl.run_until(pl.t_min + 10)
        pl.call("power")
        pl.step()
        p = pl.state.people["person-power"]
        self.assertEqual((p.state, p.location), ("WORK", "power"))
        self.assertAlmostEqual(p.free_at_min - pl.t_min, pl.prm["crew_person_decision_h"] * 60.0 - 1.0, delta=1.0)
        pl.run_until(pl.t_min + 40)
        self.assertEqual(p.state, "FREE")


class TestPit(unittest.TestCase):
    def test_truck_phases_cover_the_cycle(self):
        p = prm()
        seen = [pt.truck_phase(t, 0.0, 30.0, p) for t in range(30)]
        self.assertEqual(seen[:3], ["LOADING"] * 3)
        self.assertEqual(seen.count("HAUL_FULL"), 12)
        self.assertEqual(seen.count("QUEUE"), 2)
        self.assertEqual(seen.count("DUMP"), 1)
        self.assertEqual(seen.count("RETURN"), 12)

    def test_trucks_faces_follow_the_aggregate(self):
        pl = Plant(prm(), seed=42)
        pl.warmup()
        pl.run_until(pl.t_min + 30)
        st = pl.state
        down = [t for t in st.trucks if t.state == "DOWN"]
        self.assertEqual(len(st.trucks) - len(down), st.fleet.trucks_ready)
        states = {t.state for t in st.trucks if t.ready}
        self.assertTrue(states <= set(pt.PHASES))
        self.assertGreater(len(states), 2)                       # trucks spread over the cycle
        e1 = st.excavators[0]
        f1 = st.faces["face-1"]
        self.assertEqual((f1.state, f1.block), ("ACTIVE", e1.block))
        feats = se.measured_features(st, pl.prm)
        b = st.batches[e1.block]
        self.assertAlmostEqual(feats["face-1"]["est_axb"], b.est.axb)       # block-model estimate
        self.assertIn(feats["face-1"]["hardness"], ("твёрдая", "средняя", "мягче базовой"))
        self.assertEqual(feats["face-4"]["hardness"], "вскрыша")
        self.assertGreater(feats["fleet"]["waste_tph"], 0.0)
        on_ramps = sum(r.trucks_on for r in st.roads.values())
        self.assertEqual(on_ramps, sum(1 for t in st.trucks if t.state in ("HAUL_FULL", "RETURN")))

    def test_bort_numbers_drills_and_dozers(self):
        """Bort numbers of the company list of 29.02.2024 where it names a unit; the fleet stays 37 / 5."""
        borts = site.truck_borts()
        self.assertEqual(len(borts), 37)
        facts = sorted(b[0] for b in borts.values() if b[2] == "fact")
        self.assertEqual(facts, ["HT121", "HT136", "HT137", "HT138", "HT141"])
        self.assertEqual({b[1] for b in borts.values() if b[0] == "HT141"}, {"CAT 793D"})
        self.assertEqual(len({b[0] for b in borts.values()}), 37)                  # no number twice
        self.assertEqual(sum(1 for b in borts.values() if b[2] == "номер условный"), 32)
        self.assertEqual({k: v[0] for k, v in site.EXC_BORT.items() if v[2] == "fact"},
                         {"exc-1": "EX01", "exc-4": "EX51", "exc-5": "EX53"})
        self.assertEqual([d[1] for d in site.DRILLS], ["DR01", "DR02", "DR03", "DR04", "DR12", "DR31"])
        self.assertEqual(len(site.DOZERS), 7)
        pl = Plant(prm(), seed=42)
        pl.warmup()
        f0 = pl.state.faces["face-1"].blasted_t
        pl.run_until(pl.t_min + 120)
        st = pl.state
        self.assertTrue({d.state for d in st.drills} <= {"DRILLING", "MOVING", "IDLE", "DOWN"})
        self.assertEqual({z.state for z in st.dozers} - {"WORK", "DOWN"}, set())
        feats = se.measured_features(st, pl.prm)
        d1 = feats["drill-01"]
        self.assertEqual(d1["location"], "face-1")
        self.assertGreater(d1["holes_shift"] + feats["drill-31"]["holes_shift"], 0.0)
        # face-1: two rigs add, one excavator (about 3 000 t/h) takes for 2 h
        f1 = st.faces["face-1"].blasted_t
        p = pl.prm
        drilled = (d1["holes_shift"] + feats["drill-31"]["holes_shift"]) * p["pit_drill_t_hole"]
        self.assertNotEqual(f1, f0)
        self.assertGreater(f1, f0 - 2 * p["pit_exc_max_tph"] - 1.0)
        self.assertLessEqual(f1, f0 + drilled + 1.0)
        self.assertAlmostEqual(feats["face-1"]["blasted_t"], f1)
        self.assertEqual(feats["dozer-21"]["location"], "face-1")
        self.assertIn(feats["drill-12"]["state_ru"], ("бурит", "переезд", "простой", "неисправен"))

    def test_crusher_stop_makes_its_trucks_wait(self):
        pl = start("crusher:1")
        pl.run_until(pl.t_min + 5)
        st = pl.state
        mine = [t for t in st.trucks if t.duty == "ore" and t.line == 1 and t.ready]
        self.assertTrue(mine)
        self.assertEqual({(t.state, t.location) for t in mine}, {("QUEUE", "crusher-1")})
        other = {t.state for t in st.trucks if t.duty == "ore" and t.line == 2 and t.ready}
        self.assertNotEqual(other, {"QUEUE"})

    def test_road_closed_detour(self):
        pl = start("road:2")
        base = start("")
        pl.run_until(pl.t_min + 5)
        base.run_until(base.t_min + 5)
        self.assertEqual(pl.state.roads["ramp-2"].state, "CLOSED")
        self.assertLess(pl.state.fleet.haul_tph, base.state.fleet.haul_tph)
        f = se.measured_features(pl.state, pl.prm)["ramp-2"]
        self.assertEqual((f["state_ru"], f["cycle_mult"]), ("закрыта", pl.prm["pit_road_detour"]))
        pl.run_until(pl.t_min + pl.prm["pit_road_close_h"] * 60.0)
        self.assertEqual(pl.state.roads["ramp-2"].state, "OPEN")


class TestInstruments(unittest.TestCase):
    def test_flowmeter_drift_once_confirmed(self):
        pl = start("dose:1")
        pl.run_until(pl.t_min + 40)
        f = se.measured_features(pl.state, pl.prm)
        self.assertEqual(f["flowmeter-1"]["state"], "OK")                 # not known yet: the meter reads fine
        self.assertAlmostEqual(f["flowmeter-1"]["dose_gt"], pl.prm["flot_dose_sp_gt"], delta=2.0)
        pl.call("flot-1")                                                  # the module finds it: confirmed
        f = se.measured_features(pl.state, pl.prm)
        self.assertEqual((f["flowmeter-1"]["state"], f["flowmeter-1"]["state_ru"]), ("DRIFT", "дрейф"))
        self.assertEqual(f["flowmeter-2"]["state"], "OK")
        truth = se.truth_features(pl.state)
        self.assertLess(truth["flowmeter-1"]["dose_gt"], 0.8 * pl.prm["flot_dose_sp_gt"])

    def test_piezometers_and_safety(self):
        pl = start("", safety=True)
        pl.run_until(pl.t_min + 20)
        f = se.measured_features(pl.state, pl.prm)
        sp = pl.prm["pond_piezo_sp_kpa"]
        self.assertEqual(f["piezo-2"]["alarm"], 1.0)
        self.assertGreaterEqual(f["piezo-2"]["kpa"], sp)
        self.assertEqual(f["piezo-3"]["alarm"], 0.0)                      # lower on the dam
        self.assertAlmostEqual(f["piezo-2"]["level_m"], f["piezo-2"]["kpa"] / 9.81)
        self.assertEqual(f["piezo-2"]["sp_kpa"], sp)

    def test_analyzer_suspect_when_the_line_stands(self):
        pl = start("reline:1")
        pl.run_until(pl.t_min + 60)
        f = se.measured_features(pl.state, pl.prm)
        self.assertEqual(f["analyzer-1"]["state"], "SUSPECT")
        self.assertEqual(f["analyzer-2"]["state"], "OK")
        w0 = f["weigher-2"]["total_t"]
        pl.run_until(pl.t_min + 60)
        w1 = se.measured_features(pl.state, pl.prm)["weigher-2"]["total_t"]
        self.assertAlmostEqual(w1 - w0, pl.state.line(2).conveyor.tph, delta=0.1 * pl.prm["cal_line_tph"])


class TestWaterScenario(unittest.TestCase):
    def test_return_water_shortage(self):
        cs = CopySet(prm(), 42, "water")
        fact, base = cs.copies["fact"], cs.copies["base"]
        for _ in range(30):
            cs.step()
        w = fact.state.water
        cap = fact.prm["water_intake_cap_m3h"]
        self.assertGreater(w.leak_m3h, 0.0)
        self.assertAlmostEqual(w.intake_m3h, cap)                         # fresh water at its supply cap
        self.assertEqual(w.intake_cap_m3h, cap)
        self.assertGreater(w.cut_tph, 0.0)
        self.assertEqual(w.state, "SHORT")
        self.assertLess(abs(w.residual_pct), 1e-6)                        # balance closes with the leak
        self.assertEqual(base.state.water.state, "NORMAL")
        self.assertLess(fact.state.line(1).tph, base.state.line(1).tph)
        # the loud issue is noticed and the tailings and water crew repairs it (not the mill mechanics);
        # then the water and the ore come back
        self.assertIn("water", fact._jobs)
        job = fact._jobs["water"]
        self.assertEqual(job.node, "water")
        self.assertIn(job, fact.state.crews["crew-water"].jobs)
        self.assertEqual(fact.state.people["person-water"].task, "water")
        self.assertEqual(fact.state.people["person-mill-mech"].task, "")
        while fact.t_min < job.t_done_min + 120:
            cs.step()
        self.assertEqual(fact.state.water.leak_m3h, 0.0)
        self.assertEqual(fact._water_scale, 1.0)
        res = cs.shift_result()
        self.assertLess(res["diff"]["fact"]["cu_t"], -0.1)                # copper lost
        self.assertGreater(res["diff"]["fact"]["water_m3"], 1000.0)       # fresh water bought

    def test_parse_tokens(self):
        p = prm()
        spec = events.parse_scenario("water+hpgr_fire+road:1", 480.0, p)
        kinds = {e.kind: e for e in spec.events}
        self.assertEqual(kinds["hpgr_fire"].line, 1)                      # concentrate 1 (fact)
        self.assertEqual(kinds["hpgr_fire"].data["people"], 20)
        self.assertEqual(kinds["water"].data["crew"], "crew-water")
        self.assertEqual(kinds["road"].data["node"], "ramp-1")
        with self.assertRaises(ValueError):
            events.parse_scenario("water:1", 480.0, p)


class TestFireScenario(unittest.TestCase):
    def test_hpgr_fire_of_09_08_2026(self):
        cs = CopySet(prm(), 42, "hpgr_fire")
        fact, base = cs.copies["fact"], cs.copies["base"]
        for _ in range(60):
            cs.step()
        st, p = fact.state, fact.prm
        self.assertEqual(st.flags.get("fire"), 1.0)
        self.assertEqual(st.line(1).pebble.state, "STOP")
        self.assertEqual(st.people["person-mill-mech"].state, "OFF")
        f = se.measured_features(st, p)
        self.assertEqual((f["pebble-1"]["fire"], f["pebble-2"]["fire"]), (1.0, 0.0))
        # consequences on the SAG: no pebble crushing, E_SAG up, t/h down on line 1 only
        self.assertLess(st.line(1).sag.feed_tph, 0.97 * base.state.line(1).sag.feed_tph)
        self.assertAlmostEqual(st.line(2).tph, base.state.line(2).tph, delta=0.02 * base.state.line(2).tph)
        self.assertEqual(st.line(2).pebble.state, base.state.line(2).pebble.state)
        fact.run_until(fact.t_min + p["scen_fire_safety_h"] * 60.0)
        self.assertNotIn("fire", st.flags)                                # S0 over
        self.assertNotEqual(st.people["person-mill-mech"].state, "OFF")
        self.assertEqual(st.line(1).pebble.state, "STOP")                 # circuit still down
        fact.cancel_scenario()
        self.assertEqual(st.line(1).pebble.state, "RUN")


class TestGridLatch(unittest.TestCase):
    def test_call_before_the_shedding_is_applied_when_it_happens(self):
        pl = Plant(prm(), seed=42, mode="scenario")
        pl.warmup()
        spec = events.parse_scenario("grid", pl.t_min, pl.prm)
        for e in spec.events:
            e.t_start_min = pl.t_min + 30.5                              # the cut comes between two tacts
        pl.apply_scenario(spec)
        pl.run_until(pl.t_min + 30)
        self.assertIsNone(pl.call("power"))                              # announced, not yet shed
        self.assertEqual(sum(pl._bonus_kw.values()), 0.0)
        pl.run_until(pl.t_min + 3)
        self.assertEqual(pl.state.power.shed[0], "ball-2b")
        self.assertIsNotNone(pl._c2_latch)                               # waits for the headroom
        pl.run_until(pl.t_min + 15)
        self.assertGreater(pl._bonus_kw[2], 0.0)                         # applied once ball-2b was shed
        pl.run_until(pl.t_min + pl.prm["pow_c2_h"] * 60.0 + 5)
        self.assertIsNone(pl._c2_latch)                                  # spent with the restriction

    def test_call_without_a_restriction_does_nothing(self):
        pl = start("crusher:1")
        pl.call("power")
        self.assertIsNone(pl._c2_latch)


if __name__ == "__main__":
    unittest.main()
