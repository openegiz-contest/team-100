"""One-sided CUSUM with a fast threshold (modules/cusum.py)."""
import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from modules.cusum import STATUS_RU, OneSidedCusum, status_of, z_score  # noqa: E402


class CusumTest(unittest.TestCase):
    def test_no_shift_rarely_alarms(self):
        rng = random.Random(7)
        c = OneSidedCusum(0.5, 6.5, 3.5)
        fired = 0
        was = False
        for _ in range(3000):
            now = c.update(rng.gauss(0.0, 1.0))
            fired += int(now and not was)
            was = now
        # about one fast-threshold alarm per 4300 cycles is expected; a long CUSUM run is rarer
        self.assertLessEqual(fired, 2)

    def test_one_sigma_shift_found_fast(self):
        rng = random.Random(3)
        c = OneSidedCusum(0.5, 6.5, 3.5)
        for i in range(1, 60):
            if c.update(1.0 + rng.gauss(0.0, 1.0)):
                break
        self.assertLess(i, 30)
        self.assertEqual(c.st.fired_by, "cusum")

    def test_shift_without_noise(self):
        c = OneSidedCusum(0.5, 6.5, 3.5)
        n = 0
        while not c.update(1.0):
            n += 1
        self.assertEqual(n, 12)        # 13 updates x 0.5 = 6.5

    def test_fast_threshold(self):
        c = OneSidedCusum(0.5, 6.5, 3.5)
        self.assertFalse(c.update(3.4))
        self.assertTrue(c.update(3.6))
        self.assertEqual(c.st.fired_by, "fast")

    def test_latch_and_clear(self):
        c = OneSidedCusum(0.5, 6.5, 3.5)
        for _ in range(20):
            c.update(2.0)
        self.assertTrue(c.alarm)
        self.assertLessEqual(c.s, 13.0)                # capped at 2 h
        k = 0
        while c.update(0.0):
            k += 1
        self.assertFalse(c.alarm)
        self.assertLessEqual(k, 27)                    # 13 / 0.5 steps at most
        self.assertEqual(c.st.fired_n, -1)

    def test_negative_gaps_ignored(self):
        c = OneSidedCusum()
        for _ in range(50):
            c.update(-3.0)
        self.assertEqual(c.s, 0.0)
        self.assertFalse(c.alarm)

    def test_status_and_z(self):
        self.assertEqual(z_score(1.0, 0.0), 0.0)
        self.assertAlmostEqual(z_score(1.0, 0.5), 2.0)
        self.assertEqual(status_of(0.5, False), "noise")
        self.assertEqual(status_of(2.5, False), "unsure")
        self.assertEqual(status_of(0.1, True), "loss")
        self.assertIn("не уверен", STATUS_RU["unsure"])

    def test_bad_params(self):
        with self.assertRaises(ValueError):
            OneSidedCusum(0.5, 0.0)


if __name__ == "__main__":
    unittest.main()
