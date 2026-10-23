"""Expectation formulas and parameter table of the modules (modules/expect.py, modules/params.py)."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from modules import expect as ex  # noqa: E402
from modules import params  # noqa: E402


class ParamsTest(unittest.TestCase):
    def test_table_consistent(self):
        self.assertEqual(params.check(), [])
        prm = params.default()
        self.assertAlmostEqual(prm["sag_e_base_kwh_t"], 6.748, places=2)
        self.assertEqual(prm["cusum_h"], 6.5)
        p2 = prm.copy(cusum_h=5.0)
        self.assertEqual(p2["cusum_h"], 5.0)
        self.assertEqual(prm["cusum_h"], 6.5)
        with self.assertRaises(KeyError):
            prm.copy(no_such_key=1)


class ExpectTest(unittest.TestCase):
    def setUp(self):
        self.prm = params.default()

    def test_sag_energy_and_capacity(self):
        prm = self.prm
        self.assertAlmostEqual(ex.sag_energy_kwh_t(35.0, prm), 6.748, places=2)
        self.assertAlmostEqual(ex.sag_capacity_tph(26000.0, 35.0, prm), 3853.0, delta=5.0)
        hard = ex.sag_capacity_tph(26000.0, 27.0, prm)
        self.assertAlmostEqual(hard, 740.0 / 0.25, delta=1.0)           # pebble limit binds
        self.assertGreater(ex.sag_energy_kwh_t(27.0, prm), ex.sag_energy_kwh_t(35.0, prm))
        self.assertAlmostEqual(ex.sag_energy_kwh_t(35.0, prm, pebble_on=False), 6.748 * 1.06, places=2)
        self.assertAlmostEqual(ex.axb_from_energy(6.748, prm), 35.0, delta=0.1)
        self.assertEqual(ex.axb_from_energy(0.0, prm), ex.NO_VALUE)
        with self.assertRaises(ValueError):
            ex.dwi(0.0, prm)

    def test_mix_energy_adds_by_tonnes(self):
        prm = self.prm
        e = ex.sag_mix_energy([(0.5, 35.0), (0.5, 27.0)], prm)
        self.assertAlmostEqual(e, 0.5 * ex.sag_energy_kwh_t(35.0, prm) + 0.5 * ex.sag_energy_kwh_t(27.0, prm))
        self.assertAlmostEqual(ex.sag_mix_capacity_tph(26000.0, [(1.0, 35.0)], prm), 3853.0, delta=5.0)

    def test_bond(self):
        prm = self.prm
        self.assertAlmostEqual(ex.bond_p80_um(3853.0, 41000.0, 19.4, prm), 178.5, delta=1.5)
        self.assertAlmostEqual(ex.bond_p80_um(2650.0, 20500.0, 19.4, prm), 279.0, delta=3.0)
        self.assertEqual(ex.bond_p80_um(0.0, 41000.0, 19.4, prm), ex.NO_VALUE)
        self.assertAlmostEqual(ex.bwi_from_axb(35.0, prm), 19.4)
        self.assertAlmostEqual(ex.bwi_from_axb(27.0, prm), 20.9)
        s = ex.p80_sigma_um(3853.0, 41000.0, 19.4, prm)
        self.assertGreater(s, 8.0)
        self.assertLess(s, 16.0)

    def test_flotation_base_and_dose(self):
        prm = self.prm
        base = ex.total_recovery_pct(3853.0, 0.41, 5.0, 179.0, 1.0, prm)
        self.assertAlmostEqual(base, 87.2, delta=0.1)
        drift = ex.total_recovery_pct(3853.0, 0.41, 5.0, 179.0, 0.6, prm)
        self.assertAlmostEqual(base - drift, 3.5, delta=0.1)
        coarse = ex.total_recovery_pct(3853.0, 0.41, 5.0, 279.0, 1.0, prm)
        self.assertLess(coarse, base)
        rich = ex.total_recovery_pct(3853.0, 0.43, 5.0, 179.0, 1.0, prm)
        self.assertAlmostEqual(rich - base, 0.2, delta=0.05)
        oxide = ex.total_recovery_pct(3853.0, 0.41, 7.0, 179.0, 1.0, prm)
        self.assertAlmostEqual(base - oxide, 2.09, delta=0.05)
        self.assertEqual(ex.total_recovery_pct(0.0, 0.41, 5.0, 179.0, 1.0, prm), ex.NO_VALUE)
        grade = ex.conc_grade_pct(base, prm, 0.41)
        self.assertAlmostEqual(grade, 24.3, delta=0.05)
        self.assertAlmostEqual(ex.tails_cu_pct(0.41, base, grade), 0.053, delta=0.001)

    def test_two_product_and_sigma(self):
        prm = self.prm
        r, y = ex.two_product(0.41, 0.053, 24.3)
        self.assertAlmostEqual(r, 87.2, delta=0.2)
        self.assertAlmostEqual(y, 0.0147, delta=0.0005)
        self.assertEqual(ex.two_product(0.41, 25.0, 24.3), (ex.NO_VALUE, ex.NO_VALUE))
        s = ex.recovery_sigma_pp(0.41, 0.053, 24.3, prm)
        self.assertGreater(s, 0.6)
        self.assertLess(s, 0.9)
        self.assertAlmostEqual(ex.ascu_sigma_pp(prm), 1.043, places=3)

    def test_money_and_classes(self):
        prm = self.prm
        self.assertAlmostEqual(ex.usd_h(1.0, prm), 0.955 * 14539, places=3)
        lo, hi = ex.usd_band(1.0, prm)
        self.assertAlmostEqual(lo, 0.955 * 10000)
        self.assertAlmostEqual(hi, 0.955 * 15000)
        self.assertAlmostEqual(ex.cu_tph(3853.0, 0.41, 87.2), 13.77, places=1)
        self.assertEqual(ex.ore_class(40.0, prm), "М")
        self.assertEqual(ex.ore_class(35.0, prm), "С")
        self.assertEqual(ex.ore_class(27.0, prm), "Т")


if __name__ == "__main__":
    unittest.main()
