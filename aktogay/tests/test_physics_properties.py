"""Physical properties of the model that hold whatever the numbers: the stored audit of the balances (sim/audit.py), the
same result for the same seed, and the direction of an effect when one number moves (monotonicity). A model check, not a
check against the plant."""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from sim import audit, verify  # noqa: E402
from sim.plant import CopySet  # noqa: E402

STATIC = os.path.join(ROOT, "web", "static")


def loss(sid, **sets):
    """Copper the scenario costs against its base copy by 20:00, t."""
    r = verify.run_one({"id": sid, "text": sid, "preset": "", "kip": 1, "set": sets} if sets else
                       {"id": sid, "text": sid, "preset": "", "kip": 1})
    return -r["diff"]["fact"]["cu_t"], r


class StoredAuditTest(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(STATIC, "audit.json"), encoding="utf-8") as f:
            self.d = json.load(f)

    def test_every_balance_closes_on_every_scenario(self):
        from modules import scenarios
        ids = {r["id"] for r in self.d["runs"]}
        for s in scenarios.catalog():
            if s["id"] != "fork":
                self.assertIn(s["id"], ids)
        self.assertTrue(all(self.d["ok"].values()), self.d["worst_pct"])
        self.assertEqual(self.d["violations"], 0)

    def test_the_file_equals_the_code(self):
        for sid in ("", "pitstop", "grid"):
            now = audit.audit_one(sid)
            stored = next(r for r in self.d["runs"] if r["id"] == now["id"])
            self.assertEqual(now, stored, sid)


class DeterminismTest(unittest.TestCase):
    def test_same_seed_same_shift(self):
        a = verify.run_one({"id": "hard:1", "text": "hard:1", "preset": "", "kip": 1})
        b = verify.run_one({"id": "hard:1", "text": "hard:1", "preset": "", "kip": 1})
        self.assertEqual(a["copies"], b["copies"])


class MonotonicityTest(unittest.TestCase):
    def test_longer_repair_costs_no_less(self):
        short, _ = loss("crusher:1", crush_repair_h=2.0)
        long_, _ = loss("crusher:1", crush_repair_h=6.0)
        self.assertGreaterEqual(long_ + 1e-6, short)

    def test_longer_pit_stop_costs_no_less(self):
        short, _ = loss("pitstop", scen_pitstop_h=4.0)
        long_, _ = loss("pitstop", scen_pitstop_h=12.0)
        self.assertGreater(long_, short)

    def test_bigger_stockpile_empties_later(self):
        _, small = loss("pitstop", stock_live_t=30000.0)
        _, big = loss("pitstop", stock_live_t=60000.0)
        t_small = small["moments"].get("stock_empty_1", {}).get("min")
        t_big = big["moments"].get("stock_empty_1", {}).get("min", 1e9)
        self.assertIsNotNone(t_small)
        self.assertGreater(t_big, t_small)

    def test_longer_detour_hauls_less(self):
        hauls = []
        for detour in (1.2, 1.6, 2.0):
            from sim.params import default
            cs = CopySet(default().copy(pit_road_detour=detour), 42, "road:1", preset="", kip=1)
            f = cs.copies["fact"]
            while f.t_min < cs.copies["fact"].t_min + 30:
                cs.step(cs.prm["cal_step_live_min"])
                if f.state.fleet.haul_tph > 0:
                    break
            hauls.append(f.state.fleet.haul_tph)
        self.assertGreater(hauls[0], hauls[1])
        self.assertGreater(hauls[1], hauls[2])

    def test_grid_cap_holds_the_sag_power(self):
        cs = CopySet(None, 42, "grid", preset="", kip=1)
        f = cs.copies["fact"]
        for _ in range(240):
            cs.step(cs.prm["cal_step_live_min"])
            for ln in f.state.lines:
                if ln.sag.power_limit_kw > 0:
                    self.assertLessEqual(ln.sag.power_kw, ln.sag.power_limit_kw * 1.000001)


if __name__ == "__main__":
    unittest.main()
