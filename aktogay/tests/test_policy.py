"""Queue policy (modules/policy.py): safety first, money order, bands, robustness, deferral."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from modules import policy  # noqa: E402
from modules.params import default  # noqa: E402

NOW = 9 * 60 + 20.0     # 09:20
USD = 0.955 * 14539     # USD per t Cu


def tr(id, rate_cu, t_h, repair_h, crew, safety="", loud=True, detected=NOW, node="x"):
    return policy.Trouble(id=id, node=node, kind=id, safety=safety, rate_cu_tph=rate_cu, rate_usd_h=rate_cu * USD,
                          t_conseq_h=t_h, repair_h=repair_h, crew=crew, role="role", detected_at=detected, loud=loud)


def fork():
    """'Two at once': crusher-2 stop (stock 7 h 47 min, repair 3 h) and the silent flot-1 loss, one I&C crew."""
    crusher = tr("crusher-2:stop", 13.7, 7.78, 3.0, "crew-kip", detected=NOW)
    flot = tr("flot-1:loss", 0.55, 0.0, 0.5, "crew-kip", loud=False, detected=NOW - 5)
    return [crusher, flot]


class PolicyTest(unittest.TestCase):
    def setUp(self):
        self.prm = default()

    def test_empty(self):
        plan = policy.rank([], NOW, self.prm)
        self.assertEqual(plan.order, [])
        self.assertFalse(plan.order_matters)

    def test_fork_silent_first(self):
        plan = policy.rank(fork(), NOW, self.prm, seed=1)
        ids = [r.id for r in plan.order]
        self.assertEqual(ids[0], "flot-1:loss")
        self.assertTrue(plan.order_matters)
        self.assertGreaterEqual(plan.robust_share, 0.9)
        self.assertEqual(plan.alarm_order[0], "crusher-2:stop")      # loud first "as now"
        self.assertGreater(plan.gain_cu_t, 0.3)                     # ordering by money saves copper
        self.assertLess(plan.gain_cu_t, 3.0)
        flot = plan.order[0]
        crusher = plan.order[1]
        self.assertEqual(flot.level, "now")
        self.assertEqual(flot.band, "<3")
        self.assertEqual(crusher.level, "wait")
        self.assertEqual(crusher.band, ">60")
        self.assertNotEqual(crusher.call_by_min, policy.NO_VALUE)
        # defer until about 11:20: 7.78 h stock minus P90 of arrival + repair (about 0.67 + 5 h)
        self.assertGreater(crusher.call_by_min, NOW + 60)
        self.assertLess(crusher.call_by_min, NOW + 3 * 60)
        # a 1 h delay costs almost nothing while the stock lasts (only the repair tail beyond 6 h pays)
        self.assertLess(crusher.delay_cost_usd, 0.02 * 13.7 * USD)
        self.assertAlmostEqual(flot.delay_cost_usd, 0.55 * USD * (12500 / 14539), delta=0.55 * USD * 0.25)
        self.assertAlmostEqual(flot.exp_loss_cu_t, 0.55 * 12, places=6)

    def test_safety_first_and_not_in_money(self):
        dam = tr("water:alarm", 0.0, 0.0, 0.0, "", safety="S0", detected=NOW + 10)
        s1 = tr("sag-1:s1", 13.7, 0.0, 4.0, "crew-mill", safety="S1", detected=NOW + 5)
        plan = policy.rank(fork() + [dam, s1], NOW, self.prm, seed=2)
        ids = [r.id for r in plan.order]
        self.assertEqual(ids[:2], ["water:alarm", "sag-1:s1"])
        self.assertEqual(plan.order[0].level, "S0")
        self.assertEqual(plan.order[0].exp_loss_usd, 0.0)
        self.assertEqual(plan.order[0].delay_cost_usd, 0.0)
        self.assertEqual(plan.order[1].level, "S1")

    def test_different_crews_order_does_not_matter(self):
        a = tr("crusher-1:stop", 13.7, 0.0, 3.0, "crew-cpd")
        b = tr("flot-1:loss", 0.55, 0.0, 0.5, "crew-kip", loud=False)
        plan = policy.rank([a, b], NOW, self.prm, seed=3)
        self.assertFalse(plan.order_matters)
        self.assertAlmostEqual(plan.gain_usd, 0.0, delta=1.0)
        # fallback: both already losing (<3 band), the bigger loss first
        self.assertEqual(plan.order[0].id, "crusher-1:stop")

    def test_equal_issues_not_robust(self):
        a = tr("a", 5.0, 0.0, 2.0, "crew-mill")
        b = tr("b", 5.0, 0.0, 2.0, "crew-mill")
        plan = policy.rank([a, b], NOW, self.prm, seed=4)
        self.assertLess(plan.robust_share, 0.7)
        self.assertFalse(plan.order_matters)

    def test_crusher_at_19_with_3h_stock_is_not_deferred(self):
        c = tr("crusher-1:stop", 13.7, 3.0, 3.0, "crew-cpd")
        plan = policy.rank([c], 19 * 60.0, self.prm, seed=5)
        r = plan.order[0]
        self.assertEqual(r.level, "now")
        self.assertGreater(r.p_late_now, 0.1)
        self.assertEqual(r.call_by_min, policy.NO_VALUE)
        self.assertAlmostEqual(r.repair_p90_h, 3.0 * 2.7182818 ** (1.2815515655 * 0.4), places=3)

    def test_bands(self):
        prm = self.prm
        self.assertEqual(policy.band_of(0.0, prm), "<3")
        self.assertEqual(policy.band_of(0.1, prm), "3-15")
        self.assertEqual(policy.band_of(0.5, prm), "15-60")
        self.assertEqual(policy.band_of(1.0, prm), "15-60")
        self.assertEqual(policy.band_of(2.0, prm), ">60")

    def test_busy_crew_delays_everything(self):
        a = tr("a", 5.0, 0.0, 2.0, "crew-mill")
        busy = policy.rank([a], NOW, self.prm, {"crew-mill": [NOW + 120]}, seed=6)
        free = policy.rank([a], NOW, self.prm, {"crew-mill": [policy.NO_VALUE]}, seed=6)
        self.assertGreater(busy.loss_value_usd, free.loss_value_usd + 5.0 * USD * 1.5)
        self.assertEqual(busy.order[0].crew_free_at, NOW + 120)
        self.assertEqual(free.order[0].crew_free_at, policy.NO_VALUE)

    def test_many_issues_use_index(self):
        ts = [tr(f"t{i}", 1.0 + i, 0.0, 1.0 + 0.3 * i, "crew-mill") for i in range(7)]
        plan = policy.rank(ts, NOW, self.prm, seed=7)
        self.assertFalse(plan.enumerated)
        self.assertEqual(len(plan.order), 7)
        self.assertEqual([r.rank for r in plan.order], list(range(1, 8)))

    def test_deterministic(self):
        p1 = policy.rank(fork(), NOW, self.prm, seed=11)
        p2 = policy.rank(fork(), NOW, self.prm, seed=11)
        self.assertEqual([(r.id, r.exp_loss_usd, r.delay_cost_usd) for r in p1.order],
                         [(r.id, r.exp_loss_usd, r.delay_cost_usd) for r in p2.order])
        self.assertEqual(p1.loss_value_usd, p2.loss_value_usd)

    def test_hhmm(self):
        self.assertEqual(policy.hhmm(NOW), "09:20")
        self.assertEqual(policy.hhmm(1440 + 5), "00:05")


if __name__ == "__main__":
    unittest.main()
