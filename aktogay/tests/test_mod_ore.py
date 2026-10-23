"""akt-ore (modules/ore.py): pile model, arrival windows, 12 h forecast, hindsight check."""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests import mod_support as ms  # noqa: E402
from modules import ore  # noqa: E402
from modules.writer import Catalog  # noqa: E402

T0 = 480.0


class PileTest(unittest.TestCase):
    def test_mass_conservation(self):
        p = ore.PileModel()
        p.add("a", 10000.0, 35.0, 0.41)
        p.sides["r"] = 20000.0
        p.props["r"] = (35.0, 0.41)
        self.assertAlmostEqual(p.total(), 30000.0)
        p.draw(4000.0)
        self.assertAlmostEqual(p.total(), 26000.0)
        self.assertAlmostEqual(p.column_mass(), 6000.0)
        p.exchange(1000.0)
        self.assertAlmostEqual(p.total(), 26000.0)
        self.assertAlmostEqual(p.column_mass(), 6000.0)
        self.assertIn("r", p.column)
        p.spill(5000.0)
        self.assertAlmostEqual(p.column_mass(), 5000.0)
        self.assertAlmostEqual(p.total(), 26000.0)
        p.scale_to(13000.0)
        self.assertAlmostEqual(p.total(), 13000.0)
        shares = p.shares()
        self.assertAlmostEqual(sum(shares.values()), 1.0)

    def test_empty_column_draws_from_sides(self):
        p = ore.PileModel()
        p.sides["r"] = 1000.0
        p.props["r"] = (35.0, 0.41)
        out = p.draw(300.0)
        self.assertAlmostEqual(out["r"], 300.0)
        self.assertAlmostEqual(p.total(), 700.0)

    def test_mix_of_empty_pile_is_base_ore(self):
        p = ore.PileModel()
        mixes, cu = p.mix(ms.default())
        self.assertEqual(mixes, [(1.0, 35.0)])
        self.assertAlmostEqual(cu, 0.41)


class OreModuleTest(unittest.TestCase):
    def test_base_forecast(self):
        st, prm = ms.make_store(T0)
        m = ore.OreModule(prm, st)
        feats = m.compute(T0)
        self.assertEqual(feats["next_hard_eta_h_l1"], -1.0)
        self.assertEqual(feats["next_hard_axb"], -1.0)
        for h in range(1, 13):
            self.assertAlmostEqual(feats[f"fc_tph_h{h}"], 7706.0, delta=250.0, msg=f"h{h}")
        self.assertIn("твёрдой руды в плане на 12 ч нет", feats["fc_text"])
        self.assertIn("оценка на модели", feats["fc_text"])
        self.assertEqual(feats["hit_rate"], -1.0)
        self.assertIn("проверок ещё не было", feats["check_text"])
        self.assertEqual(json.loads(feats["layers_l1"]), [])

    def test_hard_batch_window_and_tph(self):
        # being dug: 12 000 t still in the pit (the first tonnes are already on the way)
        batches = [{"name": "batch-0009", "line": 1, "state": "DIG", "est_axb": 27.0, "tonnes": 15000.0,
                    "block": "B-1207", "pit_t": 12000.0}]
        st, prm = ms.make_store(T0, batches=batches)
        m = ore.OreModule(prm, st)
        feats = m.compute(T0)
        early, exp = feats["next_hard_eta_early_h_l1"], feats["next_hard_eta_h_l1"]
        self.assertGreater(early, 0.1)
        self.assertGreater(exp, early)
        self.assertLess(exp, 6.0)
        self.assertEqual(feats["next_hard_axb"], 27.0)
        self.assertEqual(feats["next_hard_eta_h_l2"], -1.0)
        layers = json.loads(feats["layers_l1"])
        hard = [L for L in layers if L["batch"] == "batch-0009"][0]
        self.assertEqual(hard["cls"], "Т")
        self.assertEqual(hard["block"], "B-1207")
        self.assertIn("–", hard["window"])
        self.assertLess(hard["tph_at"], 3400.0)                 # pebble limit: about 2960 t/h
        self.assertGreater(hard["tph_at"], 2500.0)
        # the hourly total dips when the hard ore dominates line 1
        self.assertLess(min(feats[f"fc_tph_h{h}"] for h in range(1, 13)), 7300.0)
        self.assertIn("B-1207", feats["fc_text"])
        self.assertIn("batch-0009", m.forecasts)
        f = m.forecasts["batch-0009"]
        self.assertAlmostEqual(f.early, T0 + early * 60.0, places=3)

    def test_plan_order_and_window_does_not_slide(self):
        """C3: the scenario block (number 13) is inserted second in the plan of line 1, ahead of 11 and 12.
        The window follows the plan order, and while the batch ahead is dug (pit_t falls) the expected
        arrival stays put instead of moving with the clock."""
        plan = "L1: 0010 S, 0013 T, 0011 S, 0012 M; L2: 0014 S"

        def snap(t, pit10):
            bt = [{"name": "batch-0010", "line": 1, "state": "DIG", "est_axb": 34.0, "pit_t": pit10},
                  {"name": "batch-0011", "line": 1, "state": "PLANNED", "est_axb": 34.0},
                  {"name": "batch-0012", "line": 1, "state": "PLANNED", "est_axb": 40.0},
                  {"name": "batch-0013", "line": 1, "state": "PLANNED", "est_axb": 27.0},
                  {"name": "batch-0014", "line": 2, "state": "PLANNED", "est_axb": 34.0}]
            return ms.snapshot(t, {"pit": {"plan_text": plan}}, bt)

        st, prm = ms.make_store(T0)
        st.update_from_search(snap(T0, 9000.0))
        m = ore.OreModule(prm, st)
        q = [b.name for b in m._queue(1, ore.all_batches(st, prm))]
        self.assertEqual(q, ["batch-0010", "batch-0013", "batch-0011", "batch-0012"])
        f0 = m.compute(T0)
        exp0 = T0 + f0["next_hard_eta_h_l1"] * 60.0
        # one hour later: 3 853 t more dug from batch-0010
        t1 = T0 + 60.0
        st.update_from_search(snap(t1, 9000.0 - 3853.0))
        f1 = m.compute(t1)
        exp1 = t1 + f1["next_hard_eta_h_l1"] * 60.0
        self.assertAlmostEqual(exp1, exp0, delta=20.0)
        self.assertLess(f1["next_hard_eta_h_l1"], f0["next_hard_eta_h_l1"] - 0.6)

    def test_arrived_hard_batch_is_not_coming_again(self):
        batches = [{"name": "batch-0009", "line": 1, "state": "DIG", "est_axb": 27.0, "pit_t": 12000.0}]
        st, prm = ms.make_store(T0, batches=batches)
        m = ore.OreModule(prm, st)
        m.compute(T0)
        self.assertIsNotNone(m.next_hard[1])
        m.arrived.add("batch-0009")
        st.update_from_search(ms.snapshot(T0 + 15.0, {}, batches))
        feats = m.compute(T0 + 15.0)
        self.assertIsNone(m.next_hard[1])
        self.assertEqual(feats["next_hard_eta_h_l1"], -1.0)

    def test_orphan_batch_is_ignored(self):
        """A batch thing whose delete was lost keeps an old sim_time while the others move on: not counted.
        Batches that lag the site together (Ditto busy at x1200) are not orphans."""
        st, prm = ms.make_store(T0)
        live = {"name": "batch-0005", "line": 1, "state": "IN_STOCK"}
        st.update_from_search(ms.snapshot(T0, {}, [{"name": "batch-0003", "line": 1, "state": "DONE"}, live]))
        old = [it for it in ms.snapshot(T0, {}, [{"name": "batch-0003", "line": 1, "state": "DONE"}])
               if it["thingId"].endswith("batch-0003")]
        items = ms.snapshot(T0 + 60.0, {}, [live]) + old
        st.update_from_search(items)
        self.assertEqual([b.name for b in ore.all_batches(st, prm)], ["batch-0005"])
        self.assertTrue(st.is_orphan(st.get("batch-0003")))
        # the site runs 60 min ahead of every batch: none is an orphan
        lag = [it for it in ms.snapshot(T0 + 60.0, {}, [live]) if "batch-" in it["thingId"]]
        items = [it for it in ms.snapshot(T0 + 120.0) if "batch-" not in it["thingId"]] + lag
        st2, _ = ms.make_store(T0)
        st2.update_from_search(items)
        self.assertEqual([b.name for b in ore.all_batches(st2, prm)], ["batch-0005"])

    def test_hindsight_hit(self):
        batches = [{"name": "batch-0009", "line": 1, "state": "BELT", "est_axb": 27.0, "tonnes": 15000.0}]
        st, prm = ms.make_store(T0, batches=batches)
        m = ore.OreModule(prm, st)
        m.compute(T0)
        f = m.forecasts["batch-0009"]
        t_arr = f.expected
        # soft sensor drops to the hard value around the expected time; feed falls to 2960
        hist = []
        t = T0
        while t < t_arr + 60.0:
            t += 15.0
            soft = 27.5 if t >= t_arr - 20.0 else 35.0
            hist.append((t, {"sag-1": {"axb_soft": soft, "feed_tph": 2960.0 if soft < 30 else 3853.0}},
                         [dict(batches[0], state="IN_STOCK", axb_soft=soft)]))
        for ti, ov, bt in hist:
            st.update_from_search(ms.snapshot(ti, ov, bt))
            feats = m.compute(ti)
        self.assertEqual(m.hits + m.misses, 1)
        self.assertEqual(feats["hit_rate"], 100.0)
        self.assertIn("сбылось", feats["check_text"])
        self.assertIn("Прогноз от 08:00", feats["check_text"])

    def test_hindsight_miss(self):
        batches = [{"name": "batch-0009", "line": 1, "state": "BELT", "est_axb": 27.0, "tonnes": 15000.0}]
        st, prm = ms.make_store(T0, batches=batches)
        m = ore.OreModule(prm, st)
        m.compute(T0)
        late = m.forecasts["batch-0009"].late
        t = late + prm["ore_check_miss_h"] * 60.0 + 15.0
        st.update_from_search(ms.snapshot(t, {}, [dict(batches[0], state="IN_STOCK")]))
        feats = m.compute(t)
        self.assertEqual(feats["hit_rate"], 0.0)
        self.assertIn("мимо", feats["check_text"])

    def test_restore_forecasts(self):
        st, prm = ms.make_store(T0)
        m = ore.OreModule(prm, st)
        rows = [{"thingId": "kz.aktogay:mod-ore", "value_sim_time_properties_value": 400.0,
                 "value_layers_l1_properties_value": json.dumps([{"batch": "batch-0003", "cls": "Т", "axb": 27.0,
                                                                  "early": 600.0, "exp": 660.0, "late": 800.0,
                                                                  "tph_at": 2960.0}]),
                 "value_layers_l2_properties_value": "[]"}]
        self.assertEqual(m.restore(rows), 1)
        self.assertEqual(m.forecasts["batch-0003"].made_at, 400.0)
        self.assertEqual(m.restore(rows), 0)

    def test_feature_types(self):
        batches = [{"name": "batch-0009", "line": 1, "state": "DIG", "est_axb": 27.0},
                   {"name": "batch-0010", "line": 2, "state": "PLANNED", "est_axb": 40.0}]
        st, prm = ms.make_store(T0, batches=batches)
        feats = ore.OreModule(prm, st).compute(T0)
        cat = Catalog()
        out = cat.features("mod-ore", feats, "run", T0)
        self.assertEqual(set(out), set(cat.feature_names("mod-ore")))
        for f, v in out.items():
            kind = cat.spec("mod-ore", f)[0]
            self.assertIsInstance(v["properties"]["value"], {"number": float, "string": str, "object": dict}[kind], f)


if __name__ == "__main__":
    unittest.main()
