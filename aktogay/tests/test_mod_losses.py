"""akt-losses (modules/losses.py): expectation vs measurement, detector, balances, feature types."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests import mod_support as ms  # noqa: E402
from modules import losses  # noqa: E402
from modules.writer import Catalog  # noqa: E402

T0 = 480.0


def module(store, prm):
    return losses.LossesModule(prm, store, ms.ROLES)


class LossesTest(unittest.TestCase):
    @staticmethod
    def _counters(times, start, feed=56.4, uf=46.4, inv_tph=10.0, inv0=100.0):
        """Thickener and water points with totalizers: thickener filling at inv_tph, pond rising at
        50 m3/h (intake 4350, losses 4300 m3/h); the sampled rates in between do not matter."""
        out = []
        for ti in times:
            h = (ti - start) / 60.0
            out.append((ti, {"thick-1": {"feed_t_total": 1000.0 + feed * h, "underflow_t_total": 900.0 + uf * h,
                                         "inventory_t": inv0 + inv_tph * h, "feed_tph": 0.0},
                             "water": {"intake_m3_total": 5e5 + 4350.0 * h, "loss_m3_total": 4e5 + 4300.0 * h,
                                       "pond_m3": 1.25e6 + 50.0 * h, "intake_m3h": 0.0}}, None))
        return out

    def test_balances_over_a_window(self):
        """Concentrate and water balances take differences of the totalizers over the window: a thickener
        filling at 10 t/h and a pond rising at 50 m3/h close to 0 %, with points 10 or 20 min apart and
        the sampled rates far off (a rate sample cannot stand for the steps between points)."""
        for gap in (10.0, 20.0):
            times = [T0 - 115.0 + gap * i for i in range(int(115 / gap) + 1)]
            st, prm = ms.make_store(T0, hist=self._counters(times, T0 - 115.0))
            feats = module(st, prm).compute(T0)
            self.assertLess(abs(feats["conc_residual_pct"]), 1e-6, gap)
            self.assertLess(abs(feats["water_residual_pct"]), 1e-6, gap)
        # 5 % of the feed lost between the weighers: shown as +5 %
        st, prm = ms.make_store(T0, hist=self._counters([T0 - 110.0, T0 - 70.0, T0 - 20.0], T0 - 110.0, uf=43.58))
        self.assertAlmostEqual(module(st, prm).compute(T0)["conc_residual_pct"], 100.0 * 2.82 / 56.4, places=6)
        # one point only, or counters less than 90 min apart: no balance (NO_VALUE, not a false 0)
        st1, prm1 = ms.make_store(T0)
        f1 = module(st1, prm1).compute(T0)
        self.assertEqual(f1["conc_residual_pct"], -1.0)
        st2, prm2 = ms.make_store(T0, hist=self._counters([T0 - 40.0, T0 - 20.0], T0 - 40.0))
        f2 = module(st2, prm2).compute(T0)
        self.assertEqual(f2["conc_residual_pct"], -1.0)
        self.assertEqual(f2["water_residual_pct"], -1.0)
        # a counter that went down (a restart) cuts the window: what is left is too short
        hist = self._counters([T0 - 115.0, T0 - 90.0], T0 - 115.0) + self._counters([T0 - 60.0, T0 - 10.0], T0 - 500.0, inv0=0.0)
        for _, snap, _ in hist[2:]:
            snap["thick-1"]["feed_t_total"] -= 1000.0
        st3, prm3 = ms.make_store(T0, hist=hist)
        self.assertEqual(module(st3, prm3).compute(T0)["conc_residual_pct"], -1.0)

    def test_copper_balance_at_one_point(self):
        """sag-N and flot-N reach Ditto in separate messages: the copper balance pairs the weighed feed
        and the grades of the same model minute, not the newest of each (2 % weigher noise apart)."""
        st, prm = ms.make_store(T0)
        before = module(st, prm).compute(T0)["cu_residual_pct"]
        st.update_from_search([ms.item("sag-1", dict(ms.BASE["sag"], feed_tph=ms.BASE["sag"]["feed_tph"] * 1.02), T0 + 1.0)])
        after = module(st, prm).compute(T0 + 1.0)["cu_residual_pct"]
        self.assertAlmostEqual(after, before, places=9)

    def test_base_case_inside_noise(self):
        st, prm = ms.make_store(T0, hist=[(T0 - 20.0, {}, None), (T0 - 10.0, {}, None)])
        m = module(st, prm)
        feats = m.compute(T0)
        for node in losses.NODES:
            self.assertEqual(feats[f"{node}_status"], "noise", node)
            self.assertLess(abs(feats[f"{node}_gap_cu_tph"]), 0.3, node)
            self.assertGreater(feats[f"{node}_sigma"], 0.0)
        self.assertEqual(feats["top_node"], "")
        self.assertIn("не найдено", feats["top_text"])
        self.assertEqual(feats["processed_sim_time"], T0)
        self.assertAlmostEqual(feats["power_headroom_mw"], 50.0)
        self.assertIn("мельницы 139,6", feats["power_parts_text"])
        self.assertLess(abs(feats["cu_residual_pct"]), 3.0)
        self.assertEqual(feats["conc_residual_pct"], -1.0)       # no totalizer points an hour apart yet
        self.assertEqual(m.processed, T0)

    def test_dose_drift_found_in_three_cycles(self):
        """Tails 0.053 -> 0.068 % Cu (R -3.5 pp): below the 0.075 alarm, found by the CUSUM on the third reading."""
        st, prm = ms.make_store(T0)
        m = module(st, prm)
        m.compute(T0)
        seen = []
        for i, tail in enumerate((0.0680, 0.0681, 0.0679, 0.0682)):
            t = T0 + 15.0 * (i + 1)
            st.update_from_search(ms.snapshot(t, {"flot-1": {"tail_cu": tail}}))
            feats = m.compute(t)
            seen.append(feats["flot-1_status"])
        self.assertEqual(seen[-1], "loss")
        self.assertIn("loss", seen[:4])                    # z about 2.6 per reading: 3-4 readings at k = 0.5, h = 6.5
        self.assertEqual(seen[0], "unsure")                # one reading is not enough, but it is above 2 sigma
        r = m.results["flot-1"]
        self.assertAlmostEqual(r.gap_cu_tph, 0.55, delta=0.1)
        self.assertGreater(r.z, 2.0)
        self.assertIn("Металлург", r.roles)
        self.assertIn("КИПиА", r.roles)
        self.assertIn("не пересечена", r.cause)
        self.assertNotEqual(r.detected_at, -1.0)
        self.assertEqual(feats["top_node"], "flot-1")
        self.assertIn("оценка на модели", feats["top_text"])
        self.assertEqual(feats["flot-2_status"], "noise")
        # drift ends: the alarm clears after the sum falls back
        for i in range(30):
            t = T0 + 75.0 + 15.0 * (i + 1)
            st.update_from_search(ms.snapshot(t, {"flot-1": {"tail_cu": 0.053 + 0.00001 * i}}))
            feats = m.compute(t)
        self.assertNotEqual(feats["flot-1_status"], "loss")

    def test_held_reading_does_not_feed_the_detector(self):
        st, prm = ms.make_store(T0)
        m = module(st, prm)
        m.compute(T0)
        for i in range(8):                                    # same analyser triple for 40 min
            t = T0 + 5.0 * (i + 1)
            st.update_from_search(ms.snapshot(t, {"flot-1": {"tail_cu": 0.068}}))
            feats = m.compute(t)
        self.assertNotEqual(feats["flot-1_status"], "loss")
        self.assertEqual(m.cusum["flot-1"].st.n, 2)        # base reading, then the one new reading

    def test_oxide_ore_points_to_geologist(self):
        batches = [{"name": "batch-0007", "line": 1, "state": "IN_STOCK", "est_ascu": 8.0, "axb_soft": 35.0}]
        st, prm = ms.make_store(T0, batches=batches)
        m = module(st, prm)
        feats = m.compute(T0)
        self.assertIn("Геолог", feats["flot-1_roles"])
        self.assertNotIn("Геолог", feats["flot-2_roles"])
        # the expectation now sits lower, so the base measurement looks better than expected
        self.assertLess(m.results["flot-1"].gap_cu_tph, 0.0)

    def test_sag_starved_and_stopped(self):
        st, prm = ms.make_store(T0, {"sag-1": {"state": "STARVED", "feed_tph": 2000.0, "power_kw": 19000.0},
                                     "sag-2": {"state": "STOP", "feed_tph": 0.0, "power_kw": 0.0}})
        m = module(st, prm)
        feats = m.compute(T0)
        self.assertEqual(feats["sag-1_status"], "feed")
        self.assertEqual(feats["sag-2_status"], "idle")
        self.assertEqual(feats["sag-1_gap_cu_tph"], 0.0)

    def test_sag_gap_when_tph_below_power(self):
        """Liner wear (-4 % t/h at the same power) is inside the block error: unsure at best, no alarm."""
        st, prm = ms.make_store(T0, {"sag-1": {"feed_tph": 3700.0}})
        m = module(st, prm)
        feats = m.compute(T0)
        self.assertGreater(feats["sag-1_gap_cu_tph"], 0.3)
        self.assertEqual(feats["sag-1_status"], "noise")
        self.assertIn("неразличимы", m.results["sag-1"].cause)

    def test_cyclone_clog(self):
        st, prm = ms.make_store(T0)
        m = module(st, prm)
        m.compute(T0)
        status = ""
        for i in range(6):
            t = T0 + 5.0 * (i + 1)
            st.update_from_search(ms.snapshot(t, {"cyclones-1": {"p80_um": 216.0 + 0.1 * i}}))
            status = m.compute(t)["cyclones-1_status"]
        self.assertEqual(status, "loss")
        r = m.results["cyclones-1"]
        self.assertGreater(r.gap_cu_tph, 0.0)
        self.assertIn("Механик фабрики", r.roles)
        self.assertIn("Металлург смены", r.roles)
        self.assertIn("засор", r.cause)

    def test_alarm_without_copper_cost_is_not_the_main_loss(self):
        """Line 1 at 3000 t/h: P80 178 um against the expected 122 is an alarm, but below the 180 um
        reference it costs no copper; the headline does not call it the main loss."""
        ov = {"sag-1": {"feed_tph": 3000.0, "power_kw": ms.BASE["sag"]["power_kw"] * 3000.0 / 3850.0}}
        st, prm = ms.make_store(T0, ov)
        m = module(st, prm)
        for i in range(6):
            t = T0 + 5.0 * (i + 1)
            st.update_from_search(ms.snapshot(t, ov))
            feats = m.compute(t)
        self.assertEqual(feats["cyclones-1_status"], "loss")
        self.assertLess(m.results["cyclones-1"].gap_cu_tph, losses.MIN_LOSS_CU_TPH)
        self.assertNotIn("звать", feats["top_text"])
        self.assertIn("меди оно не стоит", feats["top_text"])

    def test_feature_types_match_the_model(self):
        st, prm = ms.make_store(T0)
        feats = module(st, prm).compute(T0)
        cat = Catalog()
        typ = cat.type_of("mod-losses")
        out = cat.features(typ, feats, "run", T0)
        self.assertEqual(set(out), set(cat.feature_names(typ)))
        for f, v in out.items():
            kind = cat.spec(typ, f)[0]
            val = v["properties"]["value"]
            self.assertIsInstance(val, {"number": float, "string": str, "object": dict}[kind], f)
        self.assertEqual(out["resend"]["properties"]["value"], -1.0)

    def test_suspect_flowmeter_on_a_dose_loss(self):
        """A recovery loss at the dose the flowmeter shows: the meter itself is the suspect (it reads the
        setpoint while the true dose may have drifted); the oxide case points to the ore, not the meter."""
        st, prm = ms.make_store(T0)
        m = module(st, prm)
        feats = m.compute(T0)
        self.assertEqual(feats["suspect_sensors"], "")
        self.assertIn("не найдено", feats["suspect_text"])
        for i, tail in enumerate((0.0680, 0.0681, 0.0679, 0.0682)):
            t = T0 + 15.0 * (i + 1)
            st.update_from_search(ms.snapshot(t, {"flot-1": {"tail_cu": tail}}))
            feats = m.compute(t)
        self.assertEqual(feats["suspect_sensors"], "flowmeter-1")
        self.assertIn("расходомер собирателя 1", feats["suspect_text"])
        self.assertEqual(feats["flot-1_status_ru"], "потеря")
        self.assertEqual(feats["flot-2_status_ru"], "в пределах шума")

    def test_concentrate_balance_on_the_simulator_within_half_percent(self):
        """The simulator's published points (every 5 model min, rounded as sent) through akt-losses:
        the concentrate residual stays inside 0.5 % over a shift, also with a stop and a grid cut."""
        from sim.plant import CopySet
        for text in ("", "crusher:1+grid"):
            cs = CopySet(None, 42, text)
            fact = cs.copies["fact"]
            st, prm = ms.make_store(fact.t_min)
            m = module(st, prm)
            res = []
            for _ in range(12 * 12):
                for _ in range(5):
                    cs.step()
                st.update_from_search(ms.items_from_plant(fact))
                f = m.compute(fact.t_min)
                if f["conc_residual_pct"] != -1.0:
                    res.append(f["conc_residual_pct"])
            self.assertGreater(len(res), 100, text)
            self.assertLess(max(abs(x) for x in res), 0.5, text)

    def test_reset_clears_state(self):
        st, prm = ms.make_store(T0)
        m = module(st, prm)
        m.compute(T0)
        m.cusum["flot-1"].update(5.0)
        m.reset()
        self.assertEqual(m.processed, -1.0)
        self.assertFalse(m.cusum["flot-1"].alarm)


if __name__ == "__main__":
    unittest.main()
