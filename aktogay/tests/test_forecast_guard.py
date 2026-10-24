"""The copper forecast chart of the tile draws nothing, not NaN points, while the forecast of a new run has no end time or corridor yet.

Found by the sweep of the stand on 24.10.2026: after every scenario start or cancel the browser console got five
«<polygon> attribute points: Expected number, "NaN,22.0 ..."» errors (the first poll of the new run carried `rate_tph` but not yet
`shift_end_at`, `rate_lo_tph`, `rate_hi_tph`, or the end time of the shift that had just ended: zero width, NaN and Infinity). The test loads web/static/forecast.js with a stub of the page object under node."""
import json
import os
import shutil
import subprocess
import unittest

STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "static")

HARNESS = r"""
const fs = require('fs');
globalThis.window = globalThis;
globalThis.document = { getElementById: () => null, createElement: () => ({}) };
let COPPER = {};
globalThis.AKT = { views: {}, esc: s => String(s), fmt: v => String(v), f1: v => String(v), NB: ' ', simTime: 600, run: 'r',
  val: () => ({ t: 600, copper: COPPER }), st: () => 'RUN', num: () => 5, clock: () => '', clockDay: () => '', history: async () => ({ points: [] }) };
eval(fs.readFileSync(process.argv[1], 'utf8'));
const out = {};
COPPER = { rate_tph: 5, rate_lo_tph: 4, rate_hi_tph: 6, shift_end_at: 1200, plan_shift_t: 300 };
out.full_has_nan = AKT.fc.cuSvg('shift', 120, 26).includes('NaN');
out.full_has_chart = AKT.fc.cuSvg('shift', 120, 26).includes('<polygon');
COPPER = { rate_tph: 5 };
out.partial_cu = AKT.fc.cu('shift');
out.partial_svg = AKT.fc.cuSvg('shift', 120, 26);
COPPER = { rate_tph: 5, rate_lo_tph: 4, rate_hi_tph: 6, shift_end_at: 480, plan_shift_t: 300 };   // the shift that has just ended: zero width
out.zero_span_cu = AKT.fc.cu('shift');
out.zero_span_svg = AKT.fc.cuSvg('shift', 120, 26);
console.log(JSON.stringify(out));
"""


class ForecastGuardTest(unittest.TestCase):
    def test_no_chart_of_nan_for_a_forecast_without_end_time(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        r = subprocess.run([node, "-e", HARNESS, os.path.join(STATIC, "forecast.js")], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertTrue(out["full_has_chart"])
        self.assertFalse(out["full_has_nan"])
        self.assertIsNone(out["partial_cu"])
        self.assertEqual(out["partial_svg"], "")
        self.assertIsNone(out["zero_span_cu"])           # the end time of the previous shift: 0 / 0 and x / 0 gave NaN and Infinity
        self.assertEqual(out["zero_span_svg"], "")


if __name__ == "__main__":
    unittest.main()
