"""Acceptance tests of sim.plant (integration). They skip until every module is implemented."""
import math
import os
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # aktogay/: packages sim, tests
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sim import comminution as cm
from sim import events
from sim.plant import CopySet, Plant
from sim.state import NO_VALUE, PlannedCall, PlantHooks
from tests.support import SLOW, needs_impl, prm


def warm(mode="free", **kw):
    p = Plant(prm(**kw), seed=42, mode=mode)
    p.warmup()
    return p


def start(text, **kw):
    pl = warm(mode="scenario")
    pl.apply_scenario(events.parse_scenario(text, pl.t_min, pl.prm, **kw))
    return pl


class Counting(PlantHooks):
    def __init__(self):
        self.n = {"step": 0, "checkpoint": 0, "batch": 0, "truth": 0, "shift": 0}
        self.summaries = []

    def on_step(self, st):
        self.n["step"] += 1

    def on_checkpoint(self, st):
        self.n["checkpoint"] += 1

    def on_batch(self, st, batch):
        self.n["batch"] += 1

    def on_truth(self, st, entry):
        self.n["truth"] += 1

    def on_shift_end(self, st, summary):
        self.n["shift"] += 1
        self.summaries.append(summary)


class TestBase(unittest.TestCase):
    @needs_impl
    def test_warmup_reaches_0800_base(self):
        pl = warm()
        st = pl.state
        self.assertAlmostEqual(pl.t_min, 8 * 60)
        self.assertEqual(st.site_state, "RUN")
        tph = sum(ln.tph for ln in st.lines)
        self.assertAlmostEqual(tph, 7706, delta=7706 * 0.03)
        for ln in st.lines:
            self.assertAlmostEqual(ln.recovery, 87.2, delta=0.6)
            self.assertAlmostEqual(ln.cyclones.p80_um, 179, delta=8)
        self.assertAlmostEqual(st.power.site_mw, 260, delta=6)
        self.assertAlmostEqual(st.line(1).stockpile.level_t, 11600, delta=1500)
        self.assertAlmostEqual(st.line(2).stockpile.level_t, 30000, delta=1500)

    @needs_impl
    def test_deterministic_and_clone(self):
        a, b = warm(), warm()
        c = a.clone()
        for _ in range(60):
            a.step()
            b.step()
        self.assertEqual(a.snapshot(), b.snapshot())
        self.assertAlmostEqual(c.t_min, 8 * 60)
        c.step()
        self.assertNotEqual(a.t_min, c.t_min)

    @needs_impl
    def test_balances_close(self):
        pl = warm()
        pl.run_until(12 * 60)
        b = pl.balances()
        for k in ("cu_residual_pct", "water_residual_pct", "conc_residual_pct"):
            self.assertLess(abs(b[k]), 0.5, k)
        self.assertIn("of 300 MW", b["power_parts_text"])

    @needs_impl
    def test_shift_change_free_run(self):
        seen = []

        class H(PlantHooks):
            def on_shift_end(self, st, summary):
                seen.append(summary)

        pl = Plant(prm(), seed=42, mode="free", hooks=H())
        pl.warmup()
        pl.run_until(20 * 60 + 5)
        self.assertEqual(len(seen), 1)
        self.assertGreater(seen[0]["cu_t"], 0)
        self.assertLess(pl.state.shift.minutes, 10)
        self.assertEqual(pl.state.site_state, "RUN")

    @needs_impl
    def test_speed(self):
        pl = Plant(prm(), seed=42, mode="calib", t0_min=0.0, year=2025)
        t = time.perf_counter()
        pl.run_until(7 * 1440.0, dt_min=10.0)
        per_step = (time.perf_counter() - t) / (7 * 144)
        self.assertLess(per_step, 0.002)


class TestScenarios(unittest.TestCase):
    def start(self, text, **kw):
        return start(text, **kw)

    @needs_impl
    def test_c1_crusher(self):
        pl = self.start("crusher:1")
        pl.step()
        ln = pl.state.line(1)
        self.assertEqual(ln.crusher.state, "STOP")
        self.assertEqual(ln.conveyor.tph, 0.0)
        self.assertEqual(ln.conveyor.state, "STOP")
        self.assertAlmostEqual(ln.stockpile.hours_left, 3.0, delta=0.4)
        idle = [e for e in pl.state.excavators if e.line == 1]
        pl.run_until(pl.t_min + 40)
        self.assertTrue(all(e.state in ("IDLE", "MOVE") for e in idle))

    @needs_impl
    def test_c2_grid(self):
        pl = self.start("grid")
        pl.run_until(pl.t_min + 30)
        st = pl.state
        limit = pl.prm["pow_c2_limit_mw"]
        self.assertLessEqual(st.power.site_mw, limit)
        self.assertAlmostEqual(st.power.site_mw, limit - 8, delta=4)
        self.assertEqual(st.line(2).balls[1].state, "STOP")
        self.assertAlmostEqual(st.line(2).sag.feed_tph, 1925, delta=60)
        # one ball mill: the SAG needs less power than its ball charge draws, so it is slowed
        self.assertLess(st.line(2).sag.speed_pct, pl.prm["sag_speed_pct"])
        self.assertEqual(st.power.state, "LIMITED")
        pl.run_until(pl.t_min + 150)
        self.assertEqual(st.power.state, "NORMAL")

    @needs_impl
    def test_c3_hard(self):
        pl = self.start("hard:1")
        self.assertTrue(pl.state.pit.hard_in_plan)
        pl.run_until(pl.t_min + 6 * 60)
        self.assertLess(min(pl.state.line(1).tph, 3853), 3400)

    @needs_impl
    def test_c4_reline(self):
        pl = self.start("reline:1")
        p0 = pl.state.power.site_mw
        pl.run_until(pl.t_min + 10)
        st = pl.state
        self.assertEqual(st.line(1).sag.state, "RELINE")
        self.assertEqual(st.line(1).tph, 0.0)
        # mills (70 MW from the grid) and the line part of the other load stop with the line
        self.assertAlmostEqual(p0 - st.power.site_mw, 70 + pl.prm["pow_line_aux_mw"], delta=4)

    @needs_impl
    def test_copyset_fork(self):
        cs = CopySet(prm(), 42, "", preset="fork", kip=1)
        self.assertEqual(set(cs.copies), set(events.COPIES))
        res = cs.run_to_end()
        self.assertAlmostEqual(cs.copies["fact"].t_min, 20 * 60)
        self.assertEqual(cs.copies["fact"].state.site_state, "PAUSED")
        for name, d in res["diff"].items():
            self.assertTrue(math.isfinite(d["cu_t"]), name)
        self.assertGreaterEqual(res["fork"]["detection_cu_t"], 0.0)
        self.assertGreater(res["fork"]["order_cu_t"], 0.0)          # kip=1: order matters
        # The silent issue is on line 1. Line 2 differs from base also by ore
        # timing (the crusher-2 stop defers the next blocks of its plan, about
        # +-5 t Cu over seeds), so the loss of the fact copy is read on line 1.
        s = {name: c.shift_summary() for name, c in cs.copies.items()}
        self.assertAlmostEqual(s["fact"]["l1_cu_t"] - s["base"]["l1_cu_t"], -1.2, delta=0.5)
        self.assertLess(s["no_twin"]["l1_cu_t"], s["loud"]["l1_cu_t"] + 1e-9)
        self.assertLess(s["loud"]["l1_cu_t"], s["fact"]["l1_cu_t"])
        self.assertLess(res["diff"]["no_twin"]["cu_t"], res["diff"]["fact"]["cu_t"])

    @needs_impl
    def test_copyset_fork_kip2_order_free(self):
        res = CopySet(prm(), 42, "", preset="fork", kip=2).run_to_end()
        self.assertAlmostEqual(res["fork"]["order_cu_t"], 0.0, delta=0.3)

    @needs_impl
    def test_silent_issue_stays_below_setpoint(self):
        pl = self.start("dose:1")
        top = 0.0
        for _ in range(180):
            pl.step()
            top = max(top, pl.state.line(1).flot.tail_cu)
        self.assertGreater(top, 0.062)
        self.assertLess(top, prm()["acs_tail_sp_pct"])
        self.assertFalse(pl.state.line(1).analyzer.alarm)

    @unittest.skipUnless(SLOW, "set AKT_SLOW=1")
    @needs_impl
    def test_week_free_run_stays_bounded(self):
        pl = warm()
        pl.run_until(pl.t_min + 7 * 1440, dt_min=5.0)
        for ln in pl.state.lines:
            frac = ln.stockpile.level_t / pl.prm["stock_live_t"]
            self.assertTrue(0.1 <= frac <= 0.9, frac)
        w = pl.state.water.pond_m3
        self.assertTrue(pl.prm["pond_lo_m3"] * 0.95 <= w <= pl.prm["pond_hi_m3"] * 1.05)


class TestTime(unittest.TestCase):
    @needs_impl
    def test_run_until_never_overshoots(self):
        pl = warm()
        pl.run_until(8 * 60 + 7.5, dt_min=2.0)
        self.assertAlmostEqual(pl.t_min, 8 * 60 + 7.5, places=9)
        self.assertEqual(pl.state.clock.step, 120 + 4)
        with self.assertRaises(ValueError):
            pl.run_until(9 * 60, dt_min=0.0)

    @needs_impl
    def test_auto_pause_at_shift_end(self):
        h = Counting()
        pl = Plant(prm(), seed=42, mode="scenario", hooks=h)
        pl.warmup()
        self.assertEqual(h.n["shift"], 0)                 # warm-up crosses 08:00 silently
        self.assertEqual(pl.state.shift.minutes, 0.0)
        pl.run_until(23 * 60)
        self.assertAlmostEqual(pl.t_min, 20 * 60)
        self.assertEqual(pl.state.site_state, "PAUSED")
        self.assertEqual(h.n["shift"], 1)
        self.assertAlmostEqual(h.summaries[0]["minutes"], 12 * 60)
        k = pl.state.clock.step
        pl.step()
        self.assertEqual(pl.state.clock.step, k)

    @needs_impl
    def test_hooks(self):
        h = Counting()
        pl = Plant(prm(), seed=42, mode="free", hooks=h)
        pl.warmup()
        n0 = dict(h.n)
        pl.run_until(9 * 60)
        self.assertEqual(h.n["step"] - n0["step"], 60)
        self.assertEqual(h.n["checkpoint"] - n0["checkpoint"], 12)
        self.assertGreater(h.n["batch"], 0)                # batches move along the path
        c = pl.clone()
        self.assertIsNot(c.hooks, pl.hooks)
        self.assertIs(type(c.hooks), PlantHooks)

    @needs_impl
    def test_clone_is_independent(self):
        pl = warm()
        c = pl.clone()
        level = pl.state.line(1).stockpile.level_t
        c.apply_scenario(events.parse_scenario("crusher:1", c.t_min, c.prm))
        c.run_until(c.t_min + 30)
        self.assertEqual(pl.t_min, 8 * 60)
        self.assertEqual(pl.state.line(1).stockpile.level_t, level)
        self.assertEqual(pl.state.line(1).crusher.fault, "")
        self.assertIsNone(pl.state.scenario)
        self.assertIs(c.prm, pl.prm)

    @needs_impl
    def test_free_run_random_events(self):
        pl = warm()
        stops = set()
        while pl.t_min < 8 * 60 + 3 * 1440:
            pl.step(5.0)
            stops.update(ln.n for ln in pl.state.lines if ln.pebble.state == "STOP")
        log = pl.state.truth_log
        lab = [e for e in log if e.kind in events.HIDDEN]
        silent = [e for e in log if e.kind in events.SILENT]
        self.assertGreaterEqual(len(lab), 3)                # about one cause per shift
        self.assertTrue(all(e.data["found_by"] == "lab" and not e.data["preset"] for e in lab))
        # silent causes (own stream, free run only): found by the energy report, the tank audit, the patrol
        self.assertTrue(silent)
        self.assertTrue(all(e.data["found_by"] == events.SILENT_FOUND_BY[e.kind] for e in silent))
        for chain in (lab, silent):
            for a, b in zip(chain, chain[1:]):               # one at a time within each chain
                self.assertLessEqual(a.data["t_end_min"], b.data["t_start_min"] + 1e-6)
        self.assertTrue(stops)                               # pebble crusher stops in free run
        self.assertLessEqual(len(pl.state.causes), 4)

    @needs_impl
    def test_no_random_events_in_scenario_mode(self):
        pl = warm(mode="scenario")
        while pl.state.site_state != "PAUSED":
            pl.step(5.0)
            self.assertTrue(all(ln.pebble.state != "STOP" for ln in pl.state.lines))
        self.assertEqual(pl.state.truth_log, [])
        self.assertEqual(pl.state.causes, [])


class TestCalls(unittest.TestCase):
    @needs_impl
    def test_c1_noticed_without_call(self):
        pl = start("crusher:1")
        pl.run_until(pl.t_min + 20)
        jobs = pl.state.crews["crew-cpd"].jobs
        self.assertEqual([j.issue for j in jobs], ["crusher:1"])
        self.assertTrue(8 * 60 + 5 <= jobs[0].t_call_min <= 8 * 60 + 15)
        done = jobs[0].t_done_min
        self.assertEqual(pl.state.line(1).crusher.fault_until_min, done)
        pl.run_until(done + 2)
        cr = pl.state.line(1).crusher
        self.assertEqual(cr.fault, "")
        self.assertIn(cr.state, ("RUN", "SLOW"))
        self.assertEqual(cr.fault_until_min, NO_VALUE)

    @needs_impl
    def test_call_books_once(self):
        pl = start("crusher:1")
        j = pl.call("crusher-1")
        self.assertEqual((j.node, j.t_call_min), ("crusher-1", 8 * 60))
        self.assertTrue(20 <= j.t_arrive_min - j.t_call_min <= 40)
        self.assertIs(pl.call("crusher-1", issue="crusher:1"), j)
        self.assertIsNone(pl.call("crusher-2"))              # nothing to fix there
        self.assertIsNone(pl.call("flot-1", issue="dose:1"))
        pl.run_until(pl.t_min + 30)
        self.assertEqual(len(pl.state.crews["crew-cpd"].jobs), 1)

    @needs_impl
    def test_c2_call_spends_headroom(self):
        pl = start("grid")
        pl.run_until(pl.t_min + 15)
        self.assertIsNone(pl.call("power"))
        pl.run_until(pl.t_min + 30)
        st = pl.state
        self.assertAlmostEqual(st.line(2).tph, 2650, delta=60)
        self.assertGreater(st.line(2).cyclones.p80_um, 250)  # one ball mill: coarse grind
        limit = pl.prm["pow_c2_limit_mw"]
        self.assertLessEqual(st.power.site_mw, limit)
        self.assertGreater(st.power.site_mw, limit - 8)
        # 2650 t/h needs 17.9 MW, just below the ball-charge draw at the setpoint speed (18.2 MW with the
        # Austin 1990 load term): the control lowers the speed a little, never below 95 % of the setpoint
        sag, sp = st.line(2).sag, pl.prm["sag_speed_pct"]
        self.assertLess(sag.power_limit_kw, pl.prm["sag_power_sp_mw"] * 1000.0 * cm.ball_floor_ratio(sp, pl.prm))
        self.assertLess(sag.speed_pct, sp)
        self.assertGreater(sag.speed_pct, 0.9 * sp)
        self.assertLessEqual(sag.power_kw, sag.power_limit_kw * (1.0 + 3 * pl.prm["sag_power_sigma"]))
        pl.run_until(11 * 60)
        self.assertEqual(st.power.shed, [])
        self.assertAlmostEqual(st.line(2).tph, 3853, delta=200)

    @needs_impl
    def test_c3_c4_pit_calls(self):
        pl = start("hard:1")
        self.assertIsNone(pl.call("pit"))
        self.assertTrue(pl.state.pit.blend[1])
        self.assertFalse(pl.state.pit.blend[2])
        pl = start("reline:2")
        pl.run_until(pl.t_min + 5)
        self.assertIsNone(pl.call("pit"))
        self.assertEqual(pl.state.flags.get("people_in_sag"), 2.0)

    @needs_impl
    def test_silent_issue_found_by_lab_then_fixed(self):
        pl = start("dose:1")
        pl.run_until(20 * 60)
        log = pl.state.truth_log
        self.assertEqual([(e.kind, e.line, e.data["found_by"]) for e in log], [("dose", 1, "lab")])
        self.assertAlmostEqual(log[0].data["t_found_min"], 14 * 60)     # 12:00 sample, ready 14:00
        self.assertGreater(log[0].data["t_end_min"], 14 * 60 + 30)       # crew-kip travel and work
        self.assertEqual(pl.state.causes, [])

    @needs_impl
    def test_trip_by_planned_call(self):
        pl = start("trip:2")
        pl.schedule([PlannedCall(8 * 60 + 30, "crusher-2", "crew-kip", "trip:2", 1.0)])
        pl.run_until(8 * 60 + 10)
        cr = pl.state.line(2).crusher
        self.assertEqual((cr.state, cr.fault), ("STOP", "lube_trip"))
        self.assertLess(cr.lube_kpa, pl.prm["crush_lube_trip_kpa"])
        pl.run_until(8 * 60 + 29)
        self.assertEqual(pl.state.crews["crew-kip"].jobs, [])          # planned call suppresses the notice
        pl.run_until(8 * 60 + 31)
        job = pl.state.crews["crew-kip"].jobs[0]
        self.assertAlmostEqual(job.t_done_min - job.t_arrive_min, 60.0)
        pl.run_until(job.t_done_min + 2)
        self.assertEqual((cr.fault, cr.lube_bias_kpa), ("", 0.0))
        self.assertNotEqual(cr.state, "STOP")

    @needs_impl
    def test_safety_flag(self):
        pl = start("", safety=True)
        pl.run_until(8 * 60 + 5)
        self.assertNotIn("piezo", pl.state.flags)
        pl.run_until(8 * 60 + 15)
        w = pl.state.water
        self.assertEqual(pl.state.flags["piezo"], 1.0)
        self.assertGreaterEqual(w.piezo_kpa, pl.prm["pond_piezo_sp_kpa"])
        self.assertEqual(w.state, "ALARM")

    @needs_impl
    def test_cancel_scenario(self):
        pl = start("crusher:1+grid+dose:1")
        pl.run_until(pl.t_min + 10)
        pl.cancel_scenario()
        pl.run_until(pl.t_min + 5)
        st = pl.state
        self.assertIsNone(st.scenario)
        self.assertEqual(st.power.grid_limit_mw, 300.0)
        self.assertEqual(st.power.shed, [])
        self.assertEqual(st.line(1).crusher.fault, "")
        self.assertEqual(st.causes, [])
        self.assertTrue(st.truth_log and "сценарий отменён" in st.truth_log[-1].text)
        self.assertIn("на линии", st.truth_log[-1].text)              # shown in the interface: Russian

    @needs_impl
    def test_snapshot_hides_silent_cause(self):
        pl = start("crusher:1+dose:1")
        pl.step()
        self.assertEqual(pl.snapshot()["site"]["scenario"], "crusher:1")
        self.assertIn("dose:1", pl.snapshot(measured=False)["site"]["scenario"])
        self.assertEqual(pl.scenario_text(), "crusher:1")


class TestCalib(unittest.TestCase):
    @needs_impl
    def test_relines_and_downtime(self):
        pl = Plant(prm(), seed=42, mode="calib", t0_min=0.0, year=2025)
        pl.set_relines([(1, 600.0, 900.0)])
        pl.set_downtime(2, [(300.0, 500.0)])
        pl.run_until(400.0, dt_min=10.0)
        st = pl.state
        l2 = st.line(2)
        self.assertEqual((l2.sag.state, l2.state, l2.flot.state), ("STOP", "STOP", "STOP"))
        self.assertTrue(all(b.state == "STOP" and b.power_kw == 0.0 for b in l2.balls))
        self.assertGreater(l2.stockpile.in_tph, 0.0)          # crusher and belt keep filling
        # line 2 down: its mills (69.8 MW grid) and its line part of the other load are off
        self.assertAlmostEqual(st.power.site_mw, 260.0 - 69.8 - pl.prm["pow_line_aux_mw"], delta=4)
        self.assertAlmostEqual(st.power.line_aux_mw, pl.prm["pow_line_aux_mw"], delta=1e-9)
        pl.run_until(700.0, dt_min=10.0)
        self.assertEqual(l2.sag.state, "RUN")
        self.assertEqual(st.line(1).sag.state, "RELINE")
        self.assertEqual(st.flags.get("people_in_sag"), 1.0)
        pl.run_until(1000.0, dt_min=10.0)
        sag = st.line(1).sag
        self.assertNotEqual(sag.state, "RELINE")
        self.assertLess(sag.liner_x, 0.001)                    # new liner
        self.assertNotIn("people_in_sag", st.flags)
        b = pl.balances()
        self.assertLess(abs(b["cu_residual_pct"]), 0.5)
        self.assertLess(abs(b["conc_residual_pct"]), 0.5)

    @needs_impl
    def test_shift_summary_lines_add_up(self):
        pl = warm()
        pl.run_until(14 * 60)
        s = pl.shift_summary()
        for key in ("ore_t", "cu_t", "energy_mwh", "water_m3", "usd"):
            self.assertAlmostEqual(s["l1_" + key] + s["l2_" + key], s[key], delta=1e-6 * max(1.0, abs(s[key])))
        self.assertAlmostEqual(s["minutes"], 6 * 60)
        self.assertAlmostEqual(s["recovery_pct"], 100 * s["cu_t"] / s["cu_feed_t"])
        self.assertAlmostEqual(pl.state.line(1).cum_cu_t, s["l1_cu_t"])


class TestCopySet(unittest.TestCase):
    @needs_impl
    def test_reline_result_and_cancel(self):
        h = Counting()
        cs = CopySet(prm(), 42, "reline:1", kip=2, hooks=h)
        self.assertEqual(set(cs.copies), {"fact", "base"})
        self.assertIs(cs.copies["fact"].hooks, h)
        self.assertTrue(all(c.state.crews["crew-kip"].count == 2 for c in cs.copies.values()))
        for _ in range(60):
            cs.step()
        res = cs.shift_result()
        self.assertEqual(res["fork"], {})
        self.assertLess(res["diff"]["fact"]["energy_mwh"], -60.0)     # about -70 MW for an hour
        cs.cancel()
        fact, base = cs.copies["fact"], cs.copies["base"]
        self.assertIs(fact.hooks, h)
        self.assertIsNone(fact.state.scenario)
        self.assertEqual(fact.snapshot(), base.snapshot())
        res = cs.run_to_end()
        self.assertEqual(res["diff"]["fact"]["cu_t"], 0.0)
        self.assertEqual(h.n["shift"], 1)                              # auto pause of the fact copy


if __name__ == "__main__":
    unittest.main()
