"""Acceptance tests of sim.sensors (noise, analyser, lab, measured features)."""
import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # aktogay/: packages sim, tests
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sim import sensors as se
from sim.params import FEATURE_RULES
from sim.state import NO_VALUE, AnalyzerState, LabState, initial_state, topology
from tests.support import needs_impl, prm


class TestNoise(unittest.TestCase):
    @needs_impl
    def test_noisy(self):
        a = se.noisy(100.0, 0.01, 42, 5, "w")
        self.assertEqual(a, se.noisy(100.0, 0.01, 42, 5, "w"))
        self.assertNotEqual(a, 100.0)
        self.assertEqual(se.noisy(NO_VALUE, 0.01, 42, 5, "w"), NO_VALUE)
        self.assertEqual(se.noisy_abs(NO_VALUE, 5.0, 42, 5, "p"), NO_VALUE)


class TestAnalyzerLab(unittest.TestCase):
    def setUp(self):
        self.p = prm()
        self.st = initial_state(self.p)
        self.fl = self.st.line(1).flot

    @needs_impl
    def test_cycle_and_alarm(self):
        an = AnalyzerState()
        n = sum(se.analyzer_step(an, self.fl, 1, 480.0 + m, 42, m, self.p) for m in range(60))
        self.assertEqual(n, 4)
        self.assertFalse(an.alarm)
        self.fl.tail_cu = 0.2
        for m in range(60, 91):
            se.analyzer_step(an, self.fl, 1, 480.0 + m, 42, m, self.p)
        self.assertTrue(an.alarm)
        self.assertGreaterEqual(an.above_count, 2)

    @needs_impl
    def test_lab_delay(self):
        lab = LabState()
        ln = self.st.line(1)
        got = []
        for m in range(0, 9 * 60):
            r = se.lab_step(lab, ln, 5.0, float(m), 42, m, self.p)
            if r is not None:
                got.append(r)
        self.assertEqual([round(r.t_sample_min) for r in got], [0, 240])
        self.assertEqual([round(r.t_ready_min) for r in got], [120, 360])


class TestFeatures(unittest.TestCase):
    @needs_impl
    def test_keys_match_rules(self):
        p = prm()
        st = initial_state(p)
        feats = se.measured_features(st, p)
        topo = topology()
        for tid, info in topo.items():
            self.assertIn(tid, feats)
            want = set(FEATURE_RULES[info.type]) - set(se.SERVICE_FEATURES.get(info.type, ()))
            self.assertEqual(set(feats[tid]), want, tid)
        for bid in st.batches:
            self.assertEqual(set(feats[bid]), set(FEATURE_RULES["batch"]), bid)
        for tid, f in feats.items():
            for k, v in f.items():
                self.assertIsInstance(v, (float, str), (tid, k))
                if isinstance(v, float):
                    self.assertTrue(math.isfinite(v), (tid, k))

    @needs_impl
    def test_truth_same_keys(self):
        p = prm()
        st = initial_state(p)
        m = se.measured_features(st, p)
        t = se.truth_features(st)
        self.assertEqual({k: set(v) for k, v in m.items()}, {k: set(v) for k, v in t.items()})


# ---------------------------------------------------------------------------
# Detailed checks (sensors implementation)
# ---------------------------------------------------------------------------
def _read_analyzers(st, p, t0=480.0, n_cycles=2):
    for n in (1, 2):
        ln = st.line(n)
        for k in range(n_cycles):
            se.analyzer_step(ln.analyzer, ln.flot, n, t0 + 15 * k, st.seed, k, p)


class TestNoiseDetails(unittest.TestCase):
    def test_statistics(self):
        xs = [se.noisy(100.0, 0.02, 42, s, "w") for s in range(4000)]
        mean = sum(xs) / len(xs)
        sd = math.sqrt(sum((x - mean) ** 2 for x in xs) / (len(xs) - 1))
        self.assertAlmostEqual(mean, 100.0, delta=0.15)
        self.assertAlmostEqual(sd, 2.0, delta=0.1)
        ys = [se.noisy_abs(180.0, 5.0, 42, s, "p80") for s in range(4000)]
        self.assertAlmostEqual(sum(ys) / len(ys), 180.0, delta=0.4)
        self.assertNotEqual(se.noisy(100.0, 0.01, 42, 5, "w"), se.noisy(100.0, 0.01, 42, 6, "w"))
        self.assertNotEqual(se.noisy(100.0, 0.01, 42, 5, "w"), se.noisy(100.0, 0.01, 42, 5, "x"))
        self.assertEqual(se.noisy(0.0, 0.01, 42, 5, "w"), 0.0)
        self.assertEqual(se.noisy(float("nan"), 0.01, 42, 5, "w"), NO_VALUE)

    def test_two_product(self):
        p = prm()
        st = initial_state(p)
        fl = st.line(1).flot
        rec, y = se.two_product(fl.feed_cu, fl.tail_cu, fl.conc_cu)
        self.assertAlmostEqual(rec, 87.2, places=6)
        self.assertAlmostEqual(y * st.line(1).tph, fl.conc_tph, places=6)
        self.assertEqual(se.two_product(NO_VALUE, 0.05, 24.0), (NO_VALUE, NO_VALUE))
        self.assertEqual(se.two_product(0.4, 0.05, 0.04), (NO_VALUE, NO_VALUE))


class TestAnalyzerLabDetails(unittest.TestCase):
    def setUp(self):
        self.p = prm()
        self.st = initial_state(self.p)
        self.fl = self.st.line(1).flot

    def test_ten_minute_steps_keep_rate(self):
        an = AnalyzerState()
        n = sum(se.analyzer_step(an, self.fl, 1, 10.0 * k, 42, k, self.p) for k in range(6 * 24))
        self.assertEqual(n, 4 * 24)

    def test_noise_and_alarm_reset(self):
        p = self.p
        an = AnalyzerState()
        se.analyzer_step(an, self.fl, 1, 0.0, 42, 0, p)
        self.assertNotEqual(an.tail_cu, self.fl.tail_cu)
        self.assertAlmostEqual(an.tail_cu, self.fl.tail_cu, delta=5 * p["sens_an_tail_sigma"] * self.fl.tail_cu)
        self.fl.tail_cu = 0.2
        se.analyzer_step(an, self.fl, 1, 15.0, 42, 15, p)
        self.assertEqual((an.above_count, an.alarm), (1, False))
        se.analyzer_step(an, self.fl, 1, 30.0, 42, 30, p)
        self.assertTrue(an.alarm)
        self.fl.tail_cu = NO_VALUE                     # section stopped
        se.analyzer_step(an, self.fl, 1, 45.0, 42, 45, p)
        self.assertEqual((an.tail_cu, an.above_count, an.alarm), (NO_VALUE, 0, False))

    def test_silent_drift_stays_below_setpoint(self):
        # Fork reference: tails 0.068 % with the dose drift; 5 sigma of the analyser
        # is about 0.017, so two cycles in a row above 0.075 are rare.
        p = self.p
        an = AnalyzerState()
        self.fl.tail_cu = 0.068
        alarms = 0
        for k in range(4 * 24 * 7):
            se.analyzer_step(an, self.fl, 1, 15.0 * k, 42, k, p)
            alarms += an.alarm
        self.assertLess(alarms / (4 * 24 * 7), 0.01)

    def test_lab_from_warmup(self):
        p = self.p
        lab = LabState()
        ln = self.st.line(2)
        got = []
        for m in range(360, 24 * 60):
            r = se.lab_step(lab, ln, 7.0, float(m), 42, m, p)
            if r is not None:
                got.append(r)
        self.assertEqual([r.t_sample_min for r in got], [480.0, 720.0, 960.0, 1200.0])
        self.assertIs(lab.last, got[-1])
        r = got[0]
        self.assertAlmostEqual(r.ascu_pct, 7.0, delta=7.0 * 5 * p["sens_lab_sigma"])
        self.assertNotEqual(r.ascu_pct, 7.0)
        self.assertAlmostEqual(r.feed_cu, ln.flot.feed_cu, delta=0.41 * 5 * p["sens_lab_sigma"])
        self.assertEqual(lab.pending, [])               # 20:00 sample was ready at 22:00
        self.assertEqual(lab.next_sample_min, 1440.0)   # next sample at midnight


class TestFeaturesDetails(unittest.TestCase):
    def setUp(self):
        self.p = prm()
        self.st = initial_state(self.p)
        self.st.clock.step = 7

    def test_raw_builders_cover_rules(self):
        c = se._Snap(self.st, self.p, True)
        for tid, info in topology().items():
            obj = c.obj(tid, info.type)
            self.assertIsNotNone(obj, tid)
            raw = se._BUILDERS[info.type](c, tid, obj)
            want = set(FEATURE_RULES[info.type]) - set(se.SERVICE_FEATURES.get(info.type, ()))
            want -= {"state_ru"}                       # filled by conform() from the state code
            self.assertTrue(want <= set(raw), (tid, want - set(raw)))
            self.assertIn("state", raw, tid)
        f = se.measured_features(self.st, self.p)
        self.assertEqual(f["line-1"]["cum_cu_t_total"], self.st.line(1).cum_cu_t_total)
        for tid, vals in f.items():
            if "state_ru" in vals and vals["state"]:
                self.assertEqual(vals["state_ru"], se.STATE_RU[vals["state"]], tid)

    def test_deterministic_by_step(self):
        a = se.measured_features(self.st, self.p)
        self.assertEqual(a, se.measured_features(self.st, self.p))
        self.st.clock.step += 1
        b = se.measured_features(self.st, self.p)
        self.assertNotEqual(a["sag-1"]["feed_tph"], b["sag-1"]["feed_tph"])

    def test_one_instrument_one_value(self):
        f = se.measured_features(self.st, self.p)
        for n in (1, 2):
            self.assertEqual(f[f"line-{n}"]["tph"], f[f"sag-{n}"]["feed_tph"])
            self.assertEqual(f[f"rougher-{n}"]["feed_tph"], f[f"sag-{n}"]["feed_tph"])
            self.assertEqual(f[f"crusher-{n}"]["tph"], f[f"conveyor-{n}"]["tph"])
        self.assertEqual(f["site"]["power_mw"], f["power"]["site_mw"])
        self.assertEqual(f["site"]["water_m3h"], f["water"]["intake_m3h"])
        self.assertEqual(f["pit"]["mining_tph"], f["fleet"]["mining_tph"])
        self.assertAlmostEqual(f["site"]["tph"], f["line-1"]["tph"] + f["line-2"]["tph"])

    def test_noise_size(self):
        p = self.p
        f = se.measured_features(self.st, p)
        t = se.truth_features(self.st)
        q = t["sag-1"]["feed_tph"]
        self.assertNotEqual(f["sag-1"]["feed_tph"], q)
        self.assertAlmostEqual(f["sag-1"]["feed_tph"], q, delta=5 * p["sens_weigher_sigma"] * q)
        pk = t["sag-1"]["power_kw"]
        self.assertAlmostEqual(f["sag-1"]["power_kw"], pk, delta=5 * p["sens_power_sigma"] * pk)
        self.assertAlmostEqual(f["cyclones-1"]["p80_um"], t["cyclones-1"]["p80_um"],
                               delta=5 * p["sens_p80_sigma_um"])
        e = f["sag-1"]["power_kw"] / f["sag-1"]["feed_tph"]
        self.assertAlmostEqual(f["sag-1"]["e_kwh_t"], e)
        self.assertAlmostEqual(f["sag-1"]["axb_soft"], t["sag-1"]["axb_soft"], delta=35 * 0.08)
        for tid in ("rougher-1", "cleaner-1"):
            self.assertTrue(0.0 <= f[tid]["stage_recovery"] <= 100.0)

    def test_flot_from_analyser(self):
        p = self.p
        f0 = se.measured_features(self.st, p)
        self.assertEqual(f0["flot-1"]["recovery"], NO_VALUE)    # no analyser reading yet
        _read_analyzers(self.st, p)
        f = se.measured_features(self.st, p)
        t = se.truth_features(self.st)
        an = self.st.line(1).analyzer
        self.assertEqual((f["flot-1"]["feed_cu"], f["flot-1"]["tail_cu"], f["flot-1"]["conc_cu"]),
                         (an.feed_cu, an.tail_cu, an.conc_cu))
        self.assertEqual(f["cleaner-1"]["conc_cu"], an.conc_cu)
        self.assertAlmostEqual(f["flot-1"]["recovery"], t["flot-1"]["recovery"], delta=4.0)
        self.assertAlmostEqual(f["line-1"]["cu_tph"], t["line-1"]["cu_tph"], delta=1.5)
        self.assertEqual(f["line-1"]["recovery"], f["flot-1"]["recovery"])
        self.assertAlmostEqual(f["site"]["cu_tph"], f["line-1"]["cu_tph"] + f["line-2"]["cu_tph"])

    def test_hidden_truth_not_published(self):
        from sim import events as ev
        p = self.p
        st = self.st
        st.scenario = ev.parse_scenario("crusher:1+dose:2", 480.0, p)
        cy = st.line(2).cyclones
        cy.clogged = 2
        rg = st.line(2).rougher
        rg.dose_true_gt = 15.0                          # meter still reads the setpoint
        cr = st.line(2).crusher
        cr.lube_bias_kpa = -150.0
        cr.lube_kpa = 101.0
        f = se.measured_features(st, p)
        t = se.truth_features(st)
        self.assertEqual(f["site"]["scenario"], "crusher:1")
        self.assertEqual(t["site"]["scenario"], "crusher:1+dose:2")
        self.assertEqual(f["cyclones-2"]["open_count"], float(cy.open_count))
        self.assertEqual(t["cyclones-2"]["open_count"], float(cy.open_count - 2))
        self.assertAlmostEqual(f["rougher-2"]["dose_meas_gt"], 25.0, delta=25.0 * 5 * p["sens_dose_sigma"])
        self.assertEqual(t["rougher-2"]["dose_meas_gt"], 15.0)
        self.assertEqual(f["crusher-2"]["lube_kpa"], 101.0)
        self.assertEqual(t["crusher-2"]["lube_kpa"], 251.0)
        banned = {"eta", "liner_x", "clogged", "dose_true_gt", "column", "sides", "true", "feed_ore"}
        for tid, feats in f.items():
            self.assertFalse(banned & set(feats), tid)

    def test_batches_and_crews(self):
        p = self.p
        st = self.st
        b = next(iter(st.batches.values()))
        b.true.cu_pct = 0.47
        f = se.measured_features(st, p)
        t = se.truth_features(st)
        self.assertEqual(f[b.batch_id]["cu_meas"], NO_VALUE)
        self.assertEqual(t[b.batch_id]["cu_meas"], 0.47)
        self.assertEqual(f[b.batch_id]["state"], b.state)
        st.crews["crew-kip"].free_at_min = 600.0
        st.crews["crew-kip"].state = "WORK"
        f = se.measured_features(st, p)
        self.assertEqual(f["crew-kip"], {"state": "WORK", "task": "", "free_at": 600.0, "state_ru": "работает"})

    def test_missing_units_blank(self):
        st = self.st
        st.lines = st.lines[:1]
        st.crews.pop("crew-mill")
        f = se.measured_features(st, self.p)
        self.assertEqual(f["sag-2"]["feed_tph"], NO_VALUE)
        self.assertEqual(f["sag-2"]["state"], "")
        self.assertEqual(f["crew-mill"]["free_at"], NO_VALUE)
        self.assertEqual(f["site"]["tph"], f["line-1"]["tph"])


if __name__ == "__main__":
    unittest.main()
