"""Acceptance tests of sim.ore (pit, fleet, haul, belt, stockpile, batches)."""
import math
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # aktogay/: packages sim, tests
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sim import haul, ore
from sim.state import NO_VALUE, OreProps, Parcel, initial_state
from tests.support import needs_impl, prm

HARD = OreProps(0.41, 5.0, 27.0, 20.9)


def drive(st, p, hours, out_tph=3853.0, dt=1.0, on_step=None):
    """Run the ore path alone (crusher = min(pocket, room, cap), SAG draws out_tph).

    out_tph: t/h for both lines or {line: t/h}; on_step(st) runs after each step.
    """
    dug = {1: 0.0, 2: 0.0}
    drawn = {1: 0.0, 2: 0.0}
    for _ in range(int(hours * 60 / dt)):
        ore.plan_step(st, p)
        ore.fleet_step(st, p)
        targets = ore.mining_targets(st, p)
        got = ore.dig_step(st, targets, dt, p)
        for n in (1, 2):
            dug[n] += got.get(n, 0.0) * dt / 60
            avail = ore.pocket_avail_tph(st, n, dt)
            room = ore.stock_room_tph(st, n, dt, p)
            c = min(avail, room, p["crush_cap_tph"])
            st.line(n).crusher.tph = c
            ore.convey_step(st, n, c, dt, p)
            want = out_tph[n] if isinstance(out_tph, dict) else out_tph
            q = min(want, ore.stock_available_tph(st, n, dt))
            st.line(n).sag.feed_tph = q
            ore.reclaim_step(st, n, q, dt, p)
            drawn[n] += q * dt / 60
        ore.batches_step(st, p)
        if on_step is not None:
            on_step(st)
        st.clock.t_min += dt
        st.clock.step += 1
    return dug, drawn


def transit(st, n):
    ln = st.line(n)
    return sum(x.tonnes for x in st.pit.haul[n] + ln.crusher.pocket + ln.conveyor.belt)


def plan_tonnes(st, n):
    return sum(st.batches[b].tonnes - st.batches[b].dug_t for b in st.pit.plan[n])


def set_level(st, n, level_t, p):
    """Put level_t of the initial ore into stockpile n (column first)."""
    sp = st.line(n).stockpile
    bid = next(iter(sp.column))
    col = min(level_t, p["stock_column_frac"] * p["stock_live_t"])
    sp.column = {bid: col}
    sp.sides = {bid: level_t - col} if level_t > col else {}
    sp.level_t = level_t


class TestProps(unittest.TestCase):
    def setUp(self):
        self.p = prm()

    @needs_impl
    def test_bwi_from_axb(self):
        self.assertAlmostEqual(ore.bwi_from_axb(35, self.p), 19.4)
        self.assertAlmostEqual(ore.bwi_from_axb(27, self.p), 20.9)

    @needs_impl
    def test_bwi_linear_and_floor(self):
        self.assertAlmostEqual(ore.bwi_from_axb(45, self.p), 19.4 - 10 * 1.5 / 8)
        self.assertEqual(ore.bwi_from_axb(500, self.p), 0.0)

    @needs_impl
    def test_blend(self):
        b = ore.blend([(1.0, OreProps(0.4, 4.0, 27.0, 20.9)), (1.0, OreProps(0.5, 6.0, 40.0, 18.5))])
        self.assertAlmostEqual(b.axb, 2 / (1 / 27 + 1 / 40), places=6)
        self.assertAlmostEqual(b.cu_pct, 0.45, places=9)
        self.assertAlmostEqual(b.bwi, 19.7, places=9)
        self.assertEqual(ore.blend([]).axb, 0.0)

    @needs_impl
    def test_blend_ascu_by_copper_and_associative(self):
        a = OreProps(0.2, 10.0, 30.0, 20.0)
        b = OreProps(0.6, 2.0, 40.0, 18.0)
        c = OreProps(0.4, 5.0, 35.0, 19.4)
        self.assertAlmostEqual(ore.blend([(1.0, a), (1.0, b)]).ascu_pct, (0.2 * 10 + 0.6 * 2) / 0.8)
        whole = ore.blend([(3.0, a), (1.0, b), (2.0, c)])
        step = ore.blend([(4.0, ore.blend([(3.0, a), (1.0, b)])), (2.0, c)])
        for f in ("cu_pct", "ascu_pct", "axb", "bwi"):
            self.assertAlmostEqual(getattr(whole, f), getattr(step, f), places=12)
        self.assertEqual(ore.blend([(0.0, a)]), OreProps())

    @needs_impl
    def test_block_model_error(self):
        p = self.p
        est, true = zip(*(ore.draw_block(42, k, p) for k in range(1, 2001)))
        self.assertEqual(ore.draw_block(42, 7, p), ore.draw_block(42, 7, p))
        logs = [math.log(t.axb / e.axb) for e, t in zip(est, true)]
        m = sum(logs) / len(logs)
        sd = math.sqrt(sum((x - m) ** 2 for x in logs) / len(logs))
        self.assertAlmostEqual(sd, p["blk_err_axb_sigma"], delta=0.01)
        self.assertTrue(all(p["blk_axb_lo"] <= e.axb <= p["blk_axb_hi"] for e in est))
        lo, hi = p["blk_cu_mean_pct"] * p["blk_cu_lo_frac"], p["blk_cu_mean_pct"] * p["blk_cu_hi_frac"]
        self.assertAlmostEqual(lo, 0.33, places=9)
        self.assertAlmostEqual(hi, 0.50, places=9)
        self.assertTrue(all(lo - 1e-12 <= e.cu_pct <= hi + 1e-12 for e in est))
        self.assertAlmostEqual(sum(e.cu_pct for e in est) / len(est), 0.41, delta=0.01)

    @needs_impl
    def test_block_draws_mean_preserving(self):
        # lognormal factors have mean 1: the feed mean is the table mean (clamps shift it < 0.1 %)
        p = self.p
        n = 20000
        est, true = zip(*(ore.draw_block(7, k, p) for k in range(1, n + 1)))
        for vals, mean, rel_se in (([t.cu_pct for t in true], p["blk_cu_mean_pct"], 0.112),
                                   ([e.cu_pct for e in est], p["blk_cu_mean_pct"], 0.10),
                                   ([e.axb for e in est], p["blk_axb_mean"], 0.10)):
            m = sum(vals) / n
            self.assertAlmostEqual(m / mean, 1.0, delta=3 * rel_se / math.sqrt(n) + 0.001)
        ratio = sum(t.axb / e.axb for e, t in zip(est, true)) / n
        self.assertAlmostEqual(ratio, 1.0, delta=3 * 0.12 / math.sqrt(n))
        # the clamp band follows the year grade: 2023 at 0.50 % Cu is not cut at 0.50
        p50 = prm(blk_cu_mean_pct=0.50)
        cu50 = [ore.draw_block(7, k, p50)[1].cu_pct for k in range(1, 5001)]
        self.assertAlmostEqual(sum(cu50) / len(cu50) / 0.50, 1.0, delta=0.005)

    @needs_impl
    def test_block_streams_separate(self):
        e1, t1 = ore.draw_block(42, 5, self.p)
        e2, t2 = ore.draw_block(42, 5, prm(blk_err_axb_sigma=0.15))
        self.assertEqual(e1, e2)                       # estimate does not depend on the error
        self.assertNotEqual(t1.axb, t2.axb)
        self.assertNotEqual(ore.draw_block(43, 5, self.p)[0], e1)
        self.assertAlmostEqual(e1.bwi, ore.bwi_from_axb(e1.axb, self.p))
        self.assertAlmostEqual(t1.bwi, ore.bwi_from_axb(t1.axb, self.p))


class TestPit(unittest.TestCase):
    def setUp(self):
        self.p = prm()
        self.st = initial_state(self.p)

    @needs_impl
    def test_plan_keeps_horizon(self):
        st, p = self.st, self.p
        new = ore.plan_step(st, p)
        need = p["pit_plan_h"] * p["cal_line_tph"]
        for n in (1, 2):
            self.assertGreaterEqual(plan_tonnes(st, n), need)
            self.assertLess(plan_tonnes(st, n), need + p["pit_block_t"])
            face = st.batches[st.pit.plan[n][0]]       # face dug at the snapshot: base ore
            self.assertEqual((face.tag, face.block_no), ("initial", 0))
            self.assertEqual(face.est, face.true)
            self.assertEqual(face.est.axb, p["ore_axb_base"])
        drawn = [b for b in new if b.tag != "initial"]
        self.assertEqual(len(new) - len(drawn), 2)
        self.assertEqual([b.block_no for b in drawn], list(range(1, len(drawn) + 1)))
        self.assertTrue(all(b.state == "PLANNED" and b.location == "pit" and b.tonnes_left == b.tonnes
                            for b in new))
        self.assertEqual(ore.plan_step(st, p), [])
        self.assertRegex(st.pit.plan_text, r"^L1: \d{4} [MST](, \d{4} [MST])*; L2: \d{4} [MST](, \d{4} [MST])*$")
        self.assertEqual(st.pit.hard_in_plan, any(b.est.axb < p["ui_axb_hard"] for b in new))

    @needs_impl
    def test_inject_block_lead(self):
        st, p = self.st, self.p
        ore.plan_step(st, p)
        ore.mining_targets(st, p)
        cut_id = st.pit.plan[1][0]
        next_block = st.pit.next_block_no
        hb = ore.inject_block(st, 1, HARD, HARD, 2.0, p)
        self.assertTrue(st.pit.hard_in_plan)
        self.assertEqual((hb.tag, hb.block_no, hb.state), ("hard", 0, "PLANNED"))
        self.assertEqual(st.pit.next_block_no, next_block)      # random block sequence untouched
        plan = st.pit.plan[1]
        i = plan.index(hb.batch_id)
        ahead = sum(st.batches[b].tonnes - st.batches[b].dug_t for b in plan[:i])
        self.assertAlmostEqual(ahead, 2.0 * p["cal_line_tph"], delta=1e-6)
        cont = st.batches[plan[i + 1]]
        cut = st.batches[cut_id]
        self.assertEqual((cont.block_no, cont.est), (cut.block_no, cut.est))
        self.assertAlmostEqual(cut.tonnes + cont.tonnes, p["pit_block_t"])
        self.assertIn(hb.batch_id.split("-")[1] + " T", st.pit.plan_text)

    @needs_impl
    def test_fleet_short_and_shift_mean(self):
        st, p = self.st, self.p
        st.pit.target_tph = {1: 6000.0, 2: 6000.0}
        seen = {}
        for h in range(6, 22):
            st.clock.t_min = h * 60.0
            ore.fleet_step(st, p)
            self.assertEqual(st.fleet.state, "SHORT")
            seen[h] = (st.fleet.kio_n, st.fleet.trucks_ready, st.fleet.truck_kio_shift)
        self.assertEqual(seen[8][0], 1)            # new shift at 08:00
        self.assertEqual(seen[19][0], 12)
        self.assertEqual(seen[20][0], 1)
        mean = sum(seen[h][1] for h in range(8, 20)) / 12 / len(st.trucks)
        self.assertAlmostEqual(seen[19][2], mean)
        st.pit.target_tph = {1: 3853.0, 2: 3853.0}
        ore.fleet_step(st, p)
        self.assertEqual(st.fleet.exc_ready, 5)            # 3 on ore + 2 stripping (5 Hitachi, fact)
        self.assertEqual(st.fleet.state, "SHORT" if st.fleet.haul_tph < 7706 else "NORMAL")

    @needs_impl
    def test_regulator_bands(self):
        st, p = self.st, self.p
        live, base = p["stock_live_t"], p["cal_line_tph"]
        set_level(st, 1, 0.10 * live, p)
        set_level(st, 2, 0.50 * live, p)
        t = ore.mining_targets(st, p)
        self.assertAlmostEqual(t[1], max(base, 3 * p["pit_exc_max_tph"] / 2))
        self.assertAlmostEqual(t[2], base)
        self.assertEqual(st.pit.target_tph, t)
        hi, full = p["stock_reg_high_frac"], p["stock_full_frac"]
        set_level(st, 1, 0.5 * (hi + full) * live, p)
        set_level(st, 2, full * live, p)
        t = ore.mining_targets(st, p)
        self.assertAlmostEqual(t[1], 0.5 * base)
        self.assertEqual(t[2], 0.0)
        set_level(st, 2, 0.5 * live, p)
        st.line(2).crusher.fault = "scenario"
        self.assertEqual(ore.mining_targets(st, p)[2], 0.0)
        st.line(2).crusher.fault = ""
        st.line(2).crusher.state = "STOP"
        self.assertEqual(ore.mining_targets(st, p)[2], 0.0)

    @needs_impl
    def test_dig_allocation(self):
        st, p = self.st, self.p
        ore.plan_step(st, p)
        e1, e2, e3 = st.excavators
        got = ore.dig_step(st, {1: 3853.0, 2: 3853.0}, 1.0, p)
        self.assertAlmostEqual(got[1], 3853.0)
        self.assertAlmostEqual(got[2], 3853.0)
        self.assertEqual((e1.tph, e2.tph), (3000.0, 3000.0))
        self.assertAlmostEqual(e3.tph, 2 * 853.0)
        self.assertEqual({e.state for e in st.excavators}, {"DIG"})
        self.assertAlmostEqual(st.fleet.mining_tph, 7706.0)
        self.assertEqual(e1.block, st.pit.plan[1][0])

        ore.dig_step(st, {1: 0.0, 2: 3853.0}, 1.0, p)        # crusher-1 stopped
        self.assertEqual((e1.state, e1.block, e1.tph), ("IDLE", "", 0.0))
        self.assertEqual(e3.line, 2)
        self.assertAlmostEqual(e3.tph, 853.0)

        e2.state = "DOWN"
        got = ore.dig_step(st, {1: 3853.0, 2: 3853.0}, 1.0, p)
        self.assertEqual((e2.state, e2.tph), ("DOWN", 0.0))
        self.assertAlmostEqual(e3.tph, p["pit_exc_max_tph"])
        self.assertAlmostEqual(got[1], 3000.0 + 853.0 * 3000.0 / 4706.0)
        self.assertAlmostEqual(got[2], 3853.0 * 3000.0 / 4706.0)
        e2.down_until_min = st.clock.t_min
        ore.dig_step(st, {1: 3853.0, 2: 3853.0}, 1.0, p)
        self.assertEqual(e2.state, "DIG")

        st.fleet.haul_tph = 4000.0
        got = ore.dig_step(st, {1: 3853.0, 2: 3853.0}, 1.0, p)
        self.assertAlmostEqual(got[1], 2000.0)
        self.assertAlmostEqual(got[2], 2000.0)
        self.assertEqual(st.fleet.state, "SHORT")

    @needs_impl
    def test_dig_mass_and_batch_states(self):
        st, p = self.st, self.p
        ore.plan_step(st, p)
        first = st.batches[st.pit.plan[1][0]]
        haul0 = sum(x.tonnes for x in st.pit.haul[1])
        got = ore.dig_step(st, {1: 3853.0, 2: 0.0}, 1.0, p)
        self.assertAlmostEqual(sum(x.tonnes for x in st.pit.haul[1]) - haul0, got[1] / 60)
        self.assertEqual((first.state, first.t_dig_min), ("DIG", st.clock.t_min))
        self.assertEqual(st.pit.haul[1][-1].t_ready_min, st.clock.t_min + p["pit_haul_min"])
        for _ in range(240):
            st.clock.t_min += 1
            ore.dig_step(st, {1: 3853.0, 2: 0.0}, 1.0, p)
        self.assertNotIn(first.batch_id, st.pit.plan[1])
        self.assertAlmostEqual(first.dug_t, first.tonnes)
        self.assertEqual(st.batches[st.pit.plan[1][0]].state, "DIG")

    @needs_impl
    def test_blend_partner(self):
        st, p = self.st, self.p
        ore.plan_step(st, p)
        hb = ore.inject_block(st, 1, HARD, HARD, 0.0, p)
        self.assertEqual(st.pit.plan[1][0], hb.batch_id)
        st.pit.blend[1] = True
        ore.dig_step(st, {1: 3853.0, 2: 0.0}, 1.0, p)
        mate = st.batches[st.pit.plan[1][1]]
        self.assertEqual(mate.tag, "blend")
        self.assertEqual(mate.est.axb, p["ore_axb_blend"])
        self.assertEqual(mate.true.axb, p["ore_axb_blend"])
        self.assertAlmostEqual(mate.est.bwi, ore.bwi_from_axb(p["ore_axb_blend"], p))
        self.assertAlmostEqual(hb.dug_t, 3853.0 / 60 * p["ore_blend_frac"])
        self.assertAlmostEqual(mate.dug_t, 3853.0 / 60 * (1 - p["ore_blend_frac"]))
        for _ in range(480):
            st.clock.t_min += 1
            ore.dig_step(st, {1: 3853.0, 2: 0.0}, 1.0, p)
        self.assertNotIn(hb.batch_id, st.pit.plan[1])
        self.assertNotIn(mate.batch_id, st.pit.plan[1])
        self.assertAlmostEqual(hb.dug_t, p["pit_block_t"])
        self.assertAlmostEqual(mate.dug_t, p["pit_block_t"] * (1 - p["ore_blend_frac"]) / p["ore_blend_frac"])
        self.assertEqual(sum(1 for b in st.batches.values() if b.tag == "blend"), 1)


class TestPath(unittest.TestCase):
    def setUp(self):
        self.p = prm()
        self.st = initial_state(self.p)

    @needs_impl
    def test_mass_conservation(self):
        st = self.st
        start = {n: st.line(n).stockpile.level_t + transit(st, n) for n in (1, 2)}
        dug, drawn = drive(st, self.p, 6)
        for n in (1, 2):
            ln = st.line(n)
            self.assertAlmostEqual(start[n] + dug[n], ln.stockpile.level_t + drawn[n] + transit(st, n), delta=1.0)
            sp = ln.stockpile
            self.assertAlmostEqual(sum(sp.column.values()) + sum(sp.sides.values()), sp.level_t, delta=1.0)
            self.assertAlmostEqual(sp.cum_in_t - sp.cum_out_t, sp.level_t, delta=1.0)
        states = {b.state for b in st.batches.values()}
        self.assertTrue({"PLANNED", "IN_STOCK"} <= states, states)

    @needs_impl
    def test_regulator_keeps_stock(self):
        st = self.st
        drive(st, self.p, 24, dt=5.0)
        for n in (1, 2):
            frac = st.line(n).stockpile.level_t / self.p["stock_live_t"]
            self.assertTrue(0.1 < frac < 0.9, (n, frac))

    @needs_impl
    def test_not_fifo(self):
        st, p = self.st, self.p
        soft = OreProps(0.41, 5.0, 45.0, 17.5)
        b = ore.new_batch(st, 1, soft, soft, p)
        b.state = "BELT"
        st.line(1).conveyor.belt.append(Parcel(b.batch_id, 3000.0, st.clock.t_min))
        c = ore.pocket_avail_tph(st, 1, 1.0)            # first haul parcel reaches the pocket
        ore.convey_step(st, 1, c, 1.0, p)               # belt runs: the soft parcel lands on the column
        for _ in range(10):
            ore.reclaim_step(st, 1, 3853.0, 1.0, p)
            st.clock.t_min += 1
        self.assertGreater(ore.feed_props(st, 1).axb, 36.0)   # FIFO would still feed the old ore

    @needs_impl
    def test_hours_left_c1(self):
        st, p = self.st, self.p
        sp = st.line(1).stockpile
        belt0 = sum(x.tonnes for x in st.line(1).conveyor.belt)
        ore.convey_step(st, 1, 0.0, 1.0, p)           # crusher-1 stopped: belt stands still
        self.assertEqual(sp.in_tph, 0.0)
        self.assertAlmostEqual(sum(x.tonnes for x in st.line(1).conveyor.belt), belt0)
        ore.reclaim_step(st, 1, 3853.0, 1.0, p)
        self.assertAlmostEqual(sp.hours_left, 3.0, delta=0.05)
        self.assertEqual(st.line(1).conveyor.state, "STOP")
        self.assertEqual(st.line(1).conveyor.power_kw, 0.0)

    @needs_impl
    def test_fleet(self):
        st, p = self.st, self.p
        ready = []
        self.assertEqual(len(st.trucks), 37)                # 2 CAT 777 + 18 CAT 785 + 17 CAT 793 (fact)
        self.assertEqual(sum(1 for t in st.trucks if t.duty == "ore"), 23)
        # ore trucks carry 17 x 236 + 6 x 136 t per cycle (793D payload 236 t, annual report 2020 p. 61)
        self.assertAlmostEqual(sum(t.payload_t for t in st.trucks if t.duty == "ore"), 17 * 236.0 + 6 * 136.0)
        for h in range(500):
            st.clock.t_min = h * 60.0
            ore.fleet_step(st, p)
            ready.append(st.fleet.trucks_ready)
            self.assertEqual(st.fleet.trucks_ready, sum(1 for t in st.trucks if t.ready))
            # ready ore trucks x their payload x trips per hour (waste trucks haul no ore)
            want = sum(t.payload_t * 60.0 / haul.cycle_min(p, t.line) for t in st.trucks if t.ready and t.duty == "ore")
            self.assertAlmostEqual(st.fleet.haul_tph, want)
        self.assertAlmostEqual(sum(ready) / len(ready), 37 * 0.85, delta=0.6)
        # a closed ramp of line 1 makes its ore trucks take the detour
        st.roads["ramp-1"].state = "CLOSED"
        ore.fleet_step(st, p)
        want = sum(t.payload_t * 60.0 / (haul.cycle_min(p, t.line) * (p["pit_road_detour"] if t.line == 1 else 1.0))
                   for t in st.trucks if t.ready and t.duty == "ore")
        self.assertAlmostEqual(st.fleet.haul_tph, want)

    @needs_impl
    def test_belt_transit_and_batch_path(self):
        st, p = self.st, self.p
        pipe = next(b for b in st.batches.values() if b.state == "BELT" and b.line == 1)
        pipe_t = pipe.tonnes
        drive(st, p, 1.0)
        first = st.batches["batch-0005"]          # first planned block of line 1 (the face)
        self.assertEqual(first.line, 1)
        self.assertEqual(first.t_dig_min, 360.0)
        self.assertEqual(first.t_belt_min - first.t_dig_min, p["pit_haul_min"])
        self.assertEqual(first.t_stock_min - first.t_belt_min, math.ceil(p["conv_transit_min"]))
        # its first tonnes lie on the stockpile, but the excavator still digs it: the state follows
        # the last tonne (DIG in the pit), the published pit_t tells what is still to dig
        self.assertEqual((first.state, first.location), ("DIG", "pit"))
        self.assertGreater(first.dug_t, 0.0)
        self.assertLess(first.dug_t, first.tonnes)
        self.assertAlmostEqual(first.stock_mark_t, p["stock1_t0"] + pipe_t + p["pit_block_t"], delta=1e-6)
        self.assertEqual(st.line(1).conveyor.state, "RUN")
        self.assertEqual(st.line(1).conveyor.power_kw, p["conv_power_mw"] * 1000.0)
        # all dug: BELT while its tail is on the road or belt, IN_STOCK once the last tonne landed
        seen = []
        drive(st, p, 6.0, on_step=lambda s: seen.append((s.batches["batch-0005"].state,
                                                          s.batches["batch-0005"].dug_t >= s.batches["batch-0005"].tonnes - 1e-6))
              if "batch-0005" in s.batches else None)
        order = [x[0] for i, x in enumerate(seen) if i == 0 or x[0] != seen[i - 1][0]]
        self.assertEqual(order[:3], ["DIG", "BELT", "IN_STOCK"], order)
        self.assertTrue(all(done for st_, done in seen if st_ in ("BELT", "IN_STOCK")))

    @needs_impl
    def test_column_spill_and_exchange(self):
        st, p = self.st, self.p
        sp = st.line(2).stockpile
        size = p["stock_column_frac"] * p["stock_live_t"]
        soft = OreProps(0.41, 5.0, 45.0, 17.5)
        b = ore.new_batch(st, 2, soft, soft, p)
        st.line(2).conveyor.belt.append(Parcel(b.batch_id, 6000.0, st.clock.t_min))
        level0 = sp.level_t
        got = ore.convey_step(st, 2, 1.0, 1.0, p)      # empty pocket, belt runs
        self.assertGreater(got, 6000.0 * 60)
        self.assertAlmostEqual(sum(sp.column.values()), size, delta=1e-6)
        self.assertAlmostEqual(sp.level_t, level0 + got / 60, delta=1e-6)

        def share(d):
            return d.get(b.batch_id, 0.0) / sum(d.values())

        d0 = share(sp.column) - share(sp.sides)
        self.assertGreater(d0, 0.2)
        for _ in range(24):
            ore.reclaim_step(st, 2, 0.0, 60.0, p)      # no draw: exchange only
        self.assertAlmostEqual((share(sp.column) - share(sp.sides)) / d0, math.exp(-1.0), places=6)
        self.assertAlmostEqual(sp.column[b.batch_id] + sp.sides[b.batch_id], 6000.0, delta=1e-6)
        self.assertAlmostEqual(sp.level_t, level0 + got / 60, delta=1e-6)

    @needs_impl
    def test_weigher_done_and_delete(self):
        st, p = self.st, self.p
        init_id = next(iter(st.line(1).stockpile.column))
        seen = {}

        def watch(s):
            b = s.batches.get(init_id)
            if b is not None:
                seen["done"] = b.t_done_min
                seen["loc"] = b.location
            else:
                seen.setdefault("gone", s.clock.t_min)

        drive(st, p, 6.0, on_step=watch)
        t_done = seen["done"] - 360.0
        self.assertAlmostEqual(t_done, p["stock1_t0"] / 3853.0 * 60, delta=2.0)
        self.assertEqual(seen["loc"], "line-1")
        self.assertAlmostEqual(seen["gone"] - seen["done"], p["cal_batch_keep_h"] * 60, delta=1.0)
        sp = st.line(1).stockpile
        rest = [k for k in list(sp.column) + list(sp.sides) if k.startswith(ore.REST_PREFIX)]
        self.assertTrue(rest)                           # its ore is still mixed in the pile
        self.assertAlmostEqual(sum(sp.column.values()) + sum(sp.sides.values()), sp.level_t, delta=1e-6)
        self.assertGreater(ore.feed_props(st, 1).axb, 0.0)
        for b in st.batches.values():
            self.assertTrue(0.0 <= b.tonnes_left <= b.tonnes + 1e-9, b.batch_id)
            if b.state == "IN_STOCK":
                self.assertNotEqual(b.stock_mark_t, NO_VALUE)
            if b.state in ("IN_STOCK", "DONE") and b.batch_id in sp.column:
                self.assertNotEqual(b.t_sag_min, NO_VALUE)

    @needs_impl
    def test_stockpile_label(self):
        st, p = self.st, self.p
        sp = st.line(1).stockpile
        for level, label in ((100, "EMPTY"), (5000, "LOW"), (6000, "NORMAL"), (20000, "NORMAL"),
                             (39600, "FULL")):
            sp.level_t = level
            self.assertEqual(ore.stockpile_label(sp, p), label, level)

    @needs_impl
    def test_c4_stock_fills(self):
        st, p = self.st, self.p
        start = st.line(1).stockpile.level_t + transit(st, 1)
        log = []
        dug, drawn = drive(st, p, 12.0, out_tph={1: 0.0, 2: 3853.0},
                           on_step=lambda s: log.append((s.clock.t_min, s.line(1).stockpile.level_t,
                                                         s.line(1).stockpile.state)))
        full = [t for t, _, state in log if state == "FULL"]
        self.assertTrue(full)
        self.assertTrue(7.0 <= (full[0] - 360.0) / 60 <= 10.0, (full[0] - 360.0) / 60)
        self.assertLessEqual(max(level for _, level, _ in log), p["stock_live_t"] + 1e-6)
        self.assertEqual(st.pit.target_tph[1], 0.0)
        self.assertEqual(st.excavators[0].state, "IDLE")
        self.assertEqual(drawn[1], 0.0)
        self.assertAlmostEqual(start + dug[1], st.line(1).stockpile.level_t + transit(st, 1), delta=1.0)

    @needs_impl
    def test_c3_hard_block_and_blend(self):
        p = self.p
        result = {}
        for blend_on in (False, True):
            st = initial_state(p)
            ore.plan_step(st, p)
            ore.mining_targets(st, p)
            hb = ore.inject_block(st, 1, HARD, HARD, p["scen_hard_lead_h"], p)
            st.pit.blend[1] = blend_on
            axb = []
            drive(st, p, 9.0, on_step=lambda s: axb.append(ore.feed_props(s, 1).axb))
            self.assertAlmostEqual(hb.t_dig_min - 360.0, p["scen_hard_lead_h"] * 60, delta=15.0)
            self.assertEqual(hb.t_sag_min - hb.t_dig_min, p["pit_haul_min"] + math.ceil(p["conv_transit_min"]))
            result[blend_on] = min(axb)
            if blend_on:
                self.assertEqual(sum(1 for b in st.batches.values() if b.tag == "blend"), 1)
        self.assertLess(result[False], 30.0)
        self.assertGreater(result[True] - result[False], 2.0)

    @needs_impl
    def test_snapshot_feed_is_base_ore(self):
        st, p = self.st, self.p
        drive(st, p, 2.0)                          # warm-up 06:00 -> 08:00
        for n in (1, 2):
            self.assertAlmostEqual(ore.feed_props(st, n).axb, p["ore_axb_base"], places=9)
            self.assertAlmostEqual(st.line(n).stockpile.level_t, p[f"stock{n}_t0"], delta=1500)

    @needs_impl
    def test_deterministic(self):
        p = self.p
        a, b = initial_state(p), initial_state(p)
        drive(a, p, 3.0, dt=5.0)
        drive(b, p, 3.0, dt=5.0)
        self.assertEqual(a.pit.plan_text, b.pit.plan_text)
        self.assertEqual(a.batches, b.batches)
        for n in (1, 2):
            self.assertEqual(a.line(n).stockpile, b.line(n).stockpile)
        self.assertEqual(a.fleet, b.fleet)
        self.assertIsNotNone(re.match(r"^L1: ", a.pit.plan_text))


if __name__ == "__main__":
    unittest.main()
