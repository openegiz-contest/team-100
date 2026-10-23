"""Tests of sim.calib. The full run with the real plant is slow: set AKT_SLOW=1 to include it.

Most tests swap sim.plant.Plant for FakePlant: the same interface, built
from the unit formulas (comminution, flotation, utilities) at steady state,
with a known bias in SAG specific energy and recovery so the fits have work
to do. This tests calendar, stops, accounting, fits and the week check
without the full plant.
"""
import contextlib
import io
import json
import math
import os
import sys
import tempfile
import unittest
from dataclasses import asdict
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # aktogay/: packages sim, tests
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sim import calib, comminution, flotation, params, state, utilities
from tests.support import SLOW, needs_impl, prm

FAST_DT = 120.0      # model minutes; aligned with month starts, 08:00 relines and quarters


class FakePlant:
    """Plant stand-in: steady unit formulas per step, planned stops and relines honoured."""

    e_bias = 1.03        # SAG specific energy above the Morrell value (sag_k must come down)
    rec_bias = 0.995     # recovery share kept (sag of hidden causes; R0 must go up)

    def __init__(self, prm=None, seed=None, mode="free", t0_min=None, year=2026, origin_doy=0, hooks=None):
        self.prm = prm if prm is not None else params.default()
        self.state = state.initial_state(self.prm, seed, mode, t0_min, year, origin_doy)
        self.hooks = hooks if hooks is not None else state.PlantHooks()
        self.relines = []
        self.down = {1: [], 2: []}
        self.done = set()

    @property
    def t_min(self):
        return self.state.clock.t_min

    def set_relines(self, windows):
        self.relines = list(windows)

    def set_downtime(self, line, windows):
        self.down[line] = list(windows)
        self.state.line(line).down_windows = list(windows)

    def warmup(self):
        end = self.prm["cal_warmup_to_h"] * 60.0
        self.state.site_state = "WARMUP"
        while self.t_min < end - 1e-9:
            self.step(min(5.0, end - self.t_min))
        self.state.site_state = "RUN"
        self.state.shift = state.Counters()

    def balances(self):
        st = self.state
        return {"cu_residual_pct": 0.0, "water_residual_pct": st.water.residual_pct, "conc_residual_pct": 0.0,
                "power_headroom_mw": st.power.headroom_mw, "power_parts_text": utilities.power_parts_text(st.power)}

    def step(self, dt_min=None):
        prm, st = self.prm, self.state
        dt = prm["cal_step_live_min"] if dt_min is None else dt_min
        t = st.clock.t_min
        loads = state.PowerLoads()
        ore_tph = conc_tph = 0.0
        for ln in st.lines:
            n, sag, fl = ln.n, ln.sag, ln.flot
            in_reline = False
            for line, a, b in self.relines:
                if line != n:
                    continue
                if a <= t < b:
                    in_reline = True
                elif t >= b and (line, a) not in self.done:
                    self.done.add((line, a))
                    sag.liner_x = 0.0
            if in_reline or any(a <= t < b for a, b in self.down[n]):
                sag.state = "RELINE" if in_reline else "STOP"
                sag.feed_tph = sag.power_kw = 0.0
                fl.cu_tph, fl.feed_cu = 0.0, state.NO_VALUE
                fl.conc_tph, fl.tail_cu = 0.0, state.NO_VALUE
                ln.tph = ln.cu_tph = 0.0
                for bl in ln.balls:
                    bl.power_kw = 0.0
                continue
            day = int(t // 1440)
            axb = prm["ore_axb_base"] * (0.95 + 0.1 * state.u01(st.seed, day, "fake-axb", n))
            ore = state.OreProps(prm["blk_cu_mean_pct"], prm["blk_ascu_mean_pct"], axb, prm["ore_bwi_base"])
            e = comminution.sag_specific_energy(ore, prm) * self.e_bias
            eta = comminution.liner_eta(sag.liner_x, prm)
            p_kw = prm["sag_power_sp_mw"] * 1000.0
            q = comminution.sag_capacity_tph(p_kw, e, eta)
            sag.state, sag.feed_tph, sag.power_kw = "RUN", q, p_kw
            sag.liner_x += q * dt / 60.0 / 1e6 / prm["liner_life_mt"]
            ball_kw = prm["ball_power_mw"] * 1000.0
            p80 = comminution.ball_p80_um(q, ball_kw * len(ln.balls), ore.bwi, prm)
            res = flotation.flotation_steady(q, ore, p80, 1.0, prm)
            fl.cu_tph, fl.feed_cu = res.cu_tph * self.rec_bias, ore.cu_pct
            fl.conc_tph = res.conc_tph
            fl.tail_cu = (q * ore.cu_pct / 100.0 - fl.cu_tph) / (q - res.conc_tph) * 100.0   # Cu closes
            ln.tph, ln.cu_tph = q, fl.cu_tph
            ore_tph += q
            conc_tph += res.conc_tph
            loads.sag_kw[n] = p_kw
            for bl in ln.balls:
                bl.power_kw = ball_kw
                loads.ball_kw[bl.name] = ball_kw
            loads.crusher_kw[n] = prm["crush_power_mw"] * 1000.0
            loads.conveyor_kw[n] = prm["conv_power_mw"] * 1000.0
        for ln in st.lines:
            ln.stockpile.level_t = prm["stock_live_t"] * (0.5 + 0.2 * math.sin(t / 600.0 + ln.n))
        utilities.power_balance(st.power, loads, prm)
        flows = state.WaterFlows(ore_tph, ore_tph - conc_tph, conc_tph, prm["filt_moist_pct"], 0.0)
        utilities.water_step(st.water, flows, dt, prm, 0.0)
        st.total.ore_t += ore_tph * dt / 60.0
        st.shift.minutes += dt
        before = st.clock.shift_index(prm["cal_shift_start_h"], prm["cal_shift_h"])
        st.clock.t_min = t + dt
        st.clock.step += 1
        after = st.clock.shift_index(prm["cal_shift_start_h"], prm["cal_shift_h"])
        if st.mode == "free" and st.site_state == "RUN" and after != before:
            self.hooks.on_shift_end(st, {})
            st.shift = state.Counters()


class TestCalendar(unittest.TestCase):
    @needs_impl
    def test_calendar_min(self):
        self.assertEqual(calib.calendar_min(2025, 1, 1), 0.0)
        self.assertEqual(calib.calendar_min(2025, 3, 1), 59 * 1440.0)
        self.assertEqual(calib.calendar_min(2024, 3, 1), 60 * 1440.0)
        self.assertEqual(calib.calendar_min(2025, 1, 2, 8.0), 1440.0 + 480.0)
        self.assertEqual(calib.calendar_min(2024, 12, 31), 365 * 1440.0)
        self.assertEqual(calib.year_min(2024), 366 * 1440.0)
        self.assertEqual(calib.year_min(2100), 365 * 1440.0)

    def test_calendar_bad_date(self):
        for args in ((2025, 2, 29), (2025, 13, 1), (2025, 4, 31), (2025, 1, 1, 25.0)):
            with self.assertRaises(ValueError, msg=args):
                calib.calendar_min(*args)

    @needs_impl
    def test_reline_windows(self):
        p = prm()
        dur = p["liner_reline_h"] * 60.0
        w = calib.reline_windows(2025, p)
        self.assertEqual(sorted(x[0] for x in w), [1, 2, 2])
        for _line, a, b in w:
            self.assertAlmostEqual(b - a, dur)
        aug = [x for x in w if x[1] < calib.calendar_min(2025, 9, 1)]
        self.assertEqual(aug, [(2, calib.calendar_min(2025, 8, 15, 8.0), calib.calendar_min(2025, 8, 15, 8.0) + dur)])
        self.assertEqual(sorted(x[0] for x in calib.reline_windows(2024, prm())), [1, 2])
        self.assertEqual(calib.reline_windows(2023, prm()), [])

    @needs_impl
    def test_year_params(self):
        self.assertEqual(calib.year_params(prm(), 2024)["blk_cu_mean_pct"], 0.43)      # report grade
        self.assertEqual(calib.year_params(prm(), 2023)["blk_cu_mean_pct"], 0.50)      # report grade
        feed25 = calib.year_params(prm(), 2025)["blk_cu_mean_pct"]                      # report balance
        self.assertAlmostEqual(feed25, 220.3e3 / (62.1e6 * 0.872) * 100, places=9)
        self.assertEqual(calib.feed_key(2025), "tgt_2025_feed_pct")
        p = prm(blk_cu_mean_pct=0.45)
        self.assertEqual(calib.year_params(p, 2026)["blk_cu_mean_pct"], 0.45)   # no 2026 grade in the table
        calib.year_params(p, 2024)
        self.assertEqual(p["blk_cu_mean_pct"], 0.45)                          # input not changed


class TestStopsAndLiner(unittest.TestCase):
    def test_stopped_share_and_no_overlap(self):
        p = prm()
        t_year = calib.year_min(2025)
        stops = calib.line_stops(2025, p, seed=42, availability=0.90)
        rel = calib.reline_windows(2025, p)
        for line in (1, 2):
            fixed = [(a, b) for n, a, b in rel if n == line]
            total = sum(b - a for a, b in stops[line]) + sum(b - a for a, b in fixed)
            self.assertAlmostEqual(total, 0.10 * t_year, delta=1.0)
            allw = sorted(stops[line] + fixed)
            self.assertGreaterEqual(allw[0][0], 0.0)
            self.assertLessEqual(allw[-1][1], t_year)
            for (a0, b0), (a1, _b1) in zip(allw, allw[1:]):
                self.assertLessEqual(b0, a1 + 1e-6)
            for a, b in stops[line]:
                self.assertLessEqual(b - a, p["cal_stop_h_hi"] * 60.0 + 1e-6)

    def test_quarters_get_calendar_share(self):
        p = prm()
        stops = calib.line_stops(2025, p, seed=42)[2]

        def stopped(m0, m1):
            a0, a1 = calib.calendar_min(2025, m0, 1), calib.calendar_min(2025, m1, 1)
            return sum(max(0.0, min(b, a1) - max(a, a0)) for a, b in stops)

        q2, q3 = stopped(4, 7), stopped(7, 10)
        self.assertAlmostEqual(q3 / q2, 92.0 / 91.0, delta=0.002)   # the reline is not in these stops

    def test_stops_deterministic(self):
        p = prm()
        self.assertEqual(calib.line_stops(2025, p, 42), calib.line_stops(2025, p, 42))
        self.assertNotEqual(calib.line_stops(2025, p, 42)[1], calib.line_stops(2025, p, 43)[1])
        self.assertEqual(calib.line_stops(2025, p, 42, availability=1.0), {1: [], 2: []})

    def test_liner_campaign_from_calendar(self):
        p = prm()
        x1, x2 = calib.liner_x_at(p, 2025, 0.0, 1), calib.liner_x_at(p, 2025, 0.0, 2)

        def expect(year, month, day):
            # hours from the end of that calendar stop to 1 January 2025 at the fitted rate, over the campaign
            end = calib.calendar_min(year, month, day, p["cal_shift_start_h"]) + p["liner_reline_h"] * 60.0
            hours = (calib.year_min(year) - end) / 60.0
            return hours * p["cal_line_tph"] * p["cal_avail"] / 1e6 / p["liner_life_mt"]

        self.assertAlmostEqual(x1, expect(2024, 3, 15), places=9)   # planned stop of line 1, placed in March 2024
        self.assertAlmostEqual(x1, 0.815, delta=0.01)
        self.assertAlmostEqual(x2, expect(2024, 10, 15), places=9)  # SAG maintenance of line 2, October 2024
        self.assertAlmostEqual(x2, 0.205, delta=0.01)
        self.assertIsNone(calib.liner_x_at(p, 2024, 0.0, 1))
        t = calib.calendar_min(2025, 8, 15, 8.0) + (p["liner_reline_h"] + 1.0) * 60.0
        self.assertLess(calib.liner_x_at(p, 2025, t, 2), 0.001)

    def test_secant_step(self):
        f = lambda x: 3.0 * x + 1.0                                   # noqa: E731
        x1 = calib._next_x([1.0], [f(1.0)], 10.0, 1.5, -100, 100, 5.0)    # structural slope too low
        x2 = calib._next_x([1.0, x1], [f(1.0), f(x1)], 10.0, 1.5, -100, 100, 5.0)
        self.assertAlmostEqual(x2, 3.0)
        self.assertEqual(calib._next_x([1.0], [f(1.0)], 1e6, 3.0, -100, 100, 5.0), 100)


class FakeCase(unittest.TestCase):
    def setUp(self):
        calib.clear_cache()
        self._patch = mock.patch.object(calib, "Plant", FakePlant)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        calib.clear_cache()


class TestRuns(FakeCase):
    def test_run_year_accounts(self):
        p = prm()
        yr = calib.run_year(p, 2025, dt_min=FAST_DT)
        self.assertAlmostEqual(sum(q["ore_kt"] for q in yr.quarters.values()) / 1e3, yr.ore_mt, places=6)
        self.assertAlmostEqual(sum(q["cu_kt"] for q in yr.quarters.values()), yr.cu_conc_kt, places=6)
        self.assertAlmostEqual(yr.run_hours, 0.92 * 8760, delta=0.92 * 8760 * 0.01)
        self.assertAlmostEqual(yr.grade_pct, p["tgt_2025_feed_pct"], delta=1e-9)
        self.assertTrue(85.0 < yr.recovery_pct < 89.0, yr.recovery_pct)
        self.assertAlmostEqual(yr.sag_e_kwh_t, p["sag_e_base_kwh_t"] * FakePlant.e_bias, delta=0.25)
        self.assertAlmostEqual(yr.extra["other_gwh"], p["pow_other_mw"] * 8.76, delta=0.5)
        self.assertAlmostEqual(yr.extra["counter_ore_mt"], yr.ore_mt, delta=yr.ore_mt * 1e-6)
        self.assertEqual(yr.extra["reline_h_l2"], 2 * p["liner_reline_h"])     # August and December
        # line part of the other load runs only while the line runs (about the run hours)
        aux_h = yr.extra["line_aux_gwh"] * 1e3 / p["pow_line_aux_mw"]
        self.assertAlmostEqual(aux_h, yr.extra["run_h_l1"] + yr.extra["run_h_l2"], delta=1.0)
        calib.clear_cache()
        self.assertEqual(asdict(calib.run_year(p, 2025, dt_min=FAST_DT)), asdict(yr))

    def test_fit_2025_converges(self):
        p_fit, rows = calib.fit_2025(prm(), dt_min=FAST_DT)
        self.assertEqual([r.group for r in rows], ["fit 2025"] * 4)
        for r in rows:
            self.assertTrue(r.ok, r)
        self.assertLess(p_fit["sag_k"], params.value("sag_k") / 1.02)          # energy bias removed
        self.assertGreater(p_fit["flot_rinf0_pct"], params.value("flot_rinf0_pct"))
        self.assertLessEqual(set(p_fit.overrides()), set(calib.FIT_2025_KEYS))

    def test_fit_2024_converges(self):
        p0 = prm(pow_other_mw=95.0, water_evap_m3h=1500.0)          # start away from the 2024 values
        p_fit, a24, yr24, rows = calib.fit_2024(p0, dt_min=FAST_DT)
        by = {r.name: r for r in rows}
        self.assertEqual({r.group for r in rows}, {"fit 2024"})
        for name in ("electricity", "water intake", "ore processed (input)"):
            self.assertTrue(by[name].ok, by[name])
        self.assertIsNone(by[calib.AVAIL_2024_NAME].ok)
        self.assertEqual(by[calib.AVAIL_2024_NAME].model, a24)
        self.assertLessEqual(set(p_fit.overrides()), set(calib.FIT_2024_KEYS))
        for k in p_fit.as_dict():
            if k not in calib.FIT_2024_KEYS:
                self.assertEqual(p_fit[k], p0[k], k)                    # K, R0, availability untouched
        self.assertEqual(yr24.year, 2024)

    def test_check_2024(self):
        rows = calib.check_2024(prm(), dt_min=FAST_DT)
        by = {r.name: r for r in rows}
        self.assertEqual(set(by), {"ore processed (input)", "feed grade (input)", "recovery", "Cu in concentrate"})
        self.assertAlmostEqual(by["ore processed (input)"].model, 58.3, delta=58.3 * 0.005)
        self.assertEqual(by["recovery"].tol, 0.5)
        self.assertAlmostEqual(by["Cu in concentrate"].tol, 221.0 * 0.02)
        self.assertAlmostEqual(by["feed grade (input)"].model, 0.43, delta=1e-9)
        self.assertIn("0.4313", by["feed grade (input)"].note)        # report balance grade shown
        for r in rows:
            self.assertEqual(r.ok is None, r.tol < 0, r)

    def test_check_2023(self):
        a23, rows = calib.check_2023(prm(), dt_min=FAST_DT)
        by = {r.name: r for r in rows}
        self.assertEqual({r.group for r in rows}, {"check 2023"})
        self.assertIsNone(by["ore processed (input)"].ok)
        self.assertIsNone(by["electricity (input)"].ok)
        self.assertAlmostEqual(by["electricity (input)"].model, 1950.0, delta=1950.0 * 0.01)
        self.assertAlmostEqual(by["feed grade (input)"].model, 0.50, delta=1e-9)
        self.assertEqual(by["recovery"].tol, 0.5)
        self.assertAlmostEqual(by["water intake"].tol, 0.05 * 32.803)
        self.assertTrue(0.0 < a23 <= 1.0)

    def test_reline_and_quarters(self):
        rel = calib.check_reline_quarter(prm(), dt_min=FAST_DT)
        self.assertLess(rel[0].model, -4.0)                     # reline hours plus new-liner ramp
        self.assertGreater(rel[0].model, -9.0)
        q = {r.name: r for r in calib.check_quarters(prm(), dt_min=FAST_DT)}
        at_q = q["Q3 2025 recovery, model at quarter grade"]
        self.assertAlmostEqual(at_q.tol, 1.1, places=6)
        self.assertLess(at_q.model, q["Q3 2025 recovery, model at annual grade"].model)   # 0.40 < 0.41 % Cu
        self.assertIn("0.4000", at_q.note)

    def test_balances_and_2025_site(self):
        rows = calib.check_balances(prm(), 2025, dt_min=FAST_DT)
        by = {r.name: r for r in rows}
        self.assertEqual({r.group for r in rows}, {"balance 2025"})
        for name in ("Cu: feed - concentrate - tails", "water: intake - losses - pond change",
                     "site power highest", "SAG power highest", "ball mill power highest"):
            self.assertTrue(by[name].ok, by[name])
        self.assertIsNone(by["ore: stockpile in - out - level change"].ok)   # FakePlant keeps no stock counters
        for r in rows:
            self.assertTrue(math.isfinite(r.model), r)
        self.assertTrue(by["SAG feed-end wear counter highest"].ok, by["SAG feed-end wear counter highest"])
        site = {r.name: r for r in calib.check_2025_site(prm(), dt_min=FAST_DT)}
        self.assertTrue(site["feed grade (input)"].ok, site["feed grade (input)"])
        self.assertEqual(site["electricity, site"].report, 2033.0)
        self.assertIsNone(site["electricity, site"].ok)                 # 2025 ore differs from 2024
        self.assertIsNone(site["water intake"].ok)
        self.assertAlmostEqual(site["electricity per t ore"].tol, 0.03 * 2033.0 / 58.3)
        self.assertAlmostEqual(site["water intake per t ore"].tol, 0.05 * 34.852 / 58.3)

    def test_week_check(self):
        rows = calib.week_check(prm())
        by = {r.name: r for r in rows}
        self.assertEqual(by["shift counter resets"].model, 14.0)
        for name in ("shift counter resets", "longest shift counter", "pond lowest", "pond highest",
                     "stockpile-1 lowest level", "max |water_residual_pct|", "site power highest",
                     "ACS false alarms"):
            self.assertTrue(by[name].ok, by[name])

    def test_run_all_and_main(self):
        rep = calib.run_all(seed=42, dt_min=FAST_DT, quick=False)
        self.assertEqual(rep["errors"], [])
        self.assertEqual(set(rep["fitted"]), {k for k, p in params.TABLE.items() if p.fit})
        groups = {r["group"] for r in rep["rows"]}
        self.assertTrue({"fit 2025", "fit 2024", "check 2025", "check 2024", "check 2023", "balance 2025",
                         "balance 2024", "reline", "quarters", "week", "fit params"} <= groups, groups)
        for r in rep["rows"]:
            if r["group"] in ("fit 2025", "fit 2024"):
                self.assertTrue(r["ok"] is not False, r)
            self.assertTrue(math.isfinite(r["model"]), r)
        # checks and balances use the final parameters: other load of the 2024 fit in the 2025 run
        by = {(r["group"], r["name"]): r for r in rep["rows"]}
        other = rep["fitted"]["pow_other_mw"]
        self.assertAlmostEqual(rep["years"]["2025"]["extra"]["other_gwh"], other * 8.76, delta=0.5)
        self.assertIn(("balance 2025", "Cu: feed - concentrate - tails"), by)
        self.assertEqual(set(rep["years"]), {"2023", "2024", "2025"})
        self.assertEqual(set(rep["year_avail"]), {"2023", "2024", "2025"})
        json.dumps(rep, allow_nan=False)
        text = calib.format_table([calib.CheckRow(**r) for r in rep["rows"]])
        self.assertIn("deviation", text.splitlines()[0])
        code, rep2, out = _run_main(["--dt", str(FAST_DT), "--quick"])
        self.assertEqual(code, 0)
        self.assertEqual(rep2["errors"], [])
        self.assertNotIn("week", {r["group"] for r in rep2["rows"]})
        self.assertIn("wrote", out)


class TestFormat(unittest.TestCase):
    def test_table(self):
        rows = [calib.CheckRow("check 2024", "recovery", 87.6, 87.9, "%", 0.5, True),
                calib.CheckRow("check 2024", "electricity", 1990.0, 2033.0, "GWh", 60.99, True, "note text"),
                calib.CheckRow("reline", "line 2", -7.0, -4.7, "%", 1.5, False),
                calib.CheckRow("quarters", "constant", 87.2, 86.1, "%", -1.0, None)]
        text = calib.format_table(rows)
        lines = text.splitlines()
        for word in ("model", "report", "deviation", "tolerance", "ok"):
            self.assertIn(word, lines[0])
        self.assertIn("(-2.1 %)", lines[3])
        self.assertIn("| NO", lines[4])
        self.assertIn("note text", lines[3])
        self.assertTrue(lines[-1].startswith("4 rows: 2 ok, 1 not ok, 1 without tolerance"))
        self.assertIn("(no rows)", calib.format_table([]))

    def test_row_ok_rules(self):
        self.assertTrue(calib._row("g", "n", 1.0, 1.2, "-", 0.25).ok)
        self.assertFalse(calib._row("g", "n", 1.0, 1.3, "-", 0.25).ok)
        self.assertIsNone(calib._row("g", "n", 1.0, 1.3, "-").ok)
        bad = calib._row("g", "n", float("nan"), 1.0, "-", 0.1)
        self.assertFalse(bad.ok)
        self.assertEqual(bad.model, -1.0)


def _run_main(args):
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "calib.json")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = calib.main(args + ["--out", out])
        with open(out, encoding="utf-8") as f:
            return code, json.load(f), buf.getvalue()


class TestMain(unittest.TestCase):
    def test_exit_code_zero_on_error(self):
        def broken(**_kw):
            raise RuntimeError("model blew up")

        with mock.patch.object(calib, "run_all", broken):
            code, rep, text = _run_main(["--quick"])
        self.assertEqual(code, 0)
        self.assertIn("model blew up", " ".join(rep["errors"]))
        self.assertIn("error:", text)
        for k in ("seed", "fitted", "rows", "errors"):
            self.assertIn(k, rep)

    def test_stage_errors_reported(self):
        class Broken(FakePlant):
            def step(self, dt_min=None):
                raise NotImplementedError

        calib.clear_cache()
        with mock.patch.object(calib, "Plant", Broken):
            rep = calib.run_all(seed=42, dt_min=FAST_DT, quick=True)
        calib.clear_cache()
        self.assertTrue(rep["errors"])
        self.assertTrue(all("not implemented yet" in e for e in rep["errors"]), rep["errors"])
        self.assertEqual(set(rep["fitted"]), {k for k, p in params.TABLE.items() if p.fit})

    @unittest.skipUnless(SLOW, "set AKT_SLOW=1")
    def test_exit_code_zero_real(self):
        code, rep, _text = _run_main(["--quick"])
        self.assertEqual(code, 0)
        self.assertIn("rows", rep)

    @unittest.skipUnless(SLOW, "set AKT_SLOW=1")
    @needs_impl
    def test_full_quick_run(self):
        rep = calib.run_all(seed=42, quick=True)
        names = {r["name"] for r in rep["rows"]}
        self.assertTrue(any("2024" in r["group"] for r in rep["rows"]), names)
        self.assertEqual(set(rep["fitted"]) >= {"cal_avail", "sag_k", "flot_rinf0_pct"}, True)
        fit = {r["name"]: r for r in rep["rows"] if r["group"] == "fit 2025"}
        for r in fit.values():
            self.assertTrue(r["ok"], r)


if __name__ == "__main__":
    unittest.main()
