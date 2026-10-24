"""Block of 24.10.2026 (P3, P5, P6, P7): grind price from the Bozshakol analog, price of an hour in every card,
the alarm lines on the pages, the example-shift action in the header line, README sections."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "web", "static")
DOCS = os.path.dirname(ROOT)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests.test_mod_priority import T0, modules  # noqa: E402
from tests import mod_support as ms  # noqa: E402
from modules.params import default  # noqa: E402


def read(*p):
    with open(os.path.join(*p), encoding="utf-8") as f:
        return f.read()


class GrindPriceTest(unittest.TestCase):
    def test_rows_come_from_the_bozshakol_tables(self):
        p = default()
        self.assertAlmostEqual(p["grind_pp_10um_hi"], (85.64 - 73.95) / 6.0, delta=0.01)       # regression, table 2
        self.assertAlmostEqual(p["grind_pp_10um_lo"], (71.10 - 66.34) / 6.0, delta=0.01)       # laboratory composite 2
        self.assertAlmostEqual(p["grind_pp_10um"], (85.85 - 78.55) / 6.0, delta=0.02)          # laboratory composite 1
        self.assertGreater(p["grind_pp_10um"], p["flot_p80_pp_10um"])

    def test_card_shows_the_range_and_the_stand_assumption(self):
        st, prm = ms.make_store(T0, {"cyclones-1": {"p80_um": 215.0}})
        lm, om, pm = modules(st, prm)
        lm.compute(T0)
        om.compute(T0)
        _f, issues = pm.compute(T0)
        g = next(x for x in issues.values() if x["kind"] == "grind_coarse")
        self.assertIn("Бозшаколь", g["text"])
        self.assertIn("[аналог]", g["text"])
        self.assertIn("2,8–6,8 п.п.", g["text"])            # 35 um above the norm: 0.79 .. 1.95 pp per 10 um
        self.assertIn("0,3 п.п. на 10 мкм [допущение]", g["text"])


class PagesTest(unittest.TestCase):
    def test_header_example_and_card_hour(self):
        app = read(STATIC, "app.js")
        self.assertIn("Показать пример смены", app)
        self.assertIn("Panel.scenario('fork'", app)
        self.assertIn("out.demo = !AKT.scenario()", app)
        self.assertIn("AKT.delayHourHtml", app)

    def test_alarm_lines(self):
        pages = read(STATIC, "pages.js")
        self.assertIn("alarm_flood_text", pages)
        self.assertIn("Лавина тревог и одна беда", pages)
        self.assertIn("Сверка с фактом KAZ Minerals", read(STATIC, "views.js"))

    def test_readme_sections(self):
        r = read(DOCS, "README.md")
        self.assertLess(r.index("### Как проверить за 5 минут"), r.index("### Требования"))
        self.assertIn("### Что сделано сверх Примера рудника", r)
        self.assertIn("GRAFANA_ADMIN_PASSWORD", r)
        v = read(DOCS, "VALIDATION.md")
        for h in ("### 8.9 ", "### 8.10 ", "### 8.11 ", "### 8.12 ", "### 8.13 ", "### 12.2 ", "## 14. Протокол пилота"):
            self.assertIn(h, v)
        self.assertLess(v.index("### 8.9 "), v.index("### 8.10 "))


if __name__ == "__main__":
    unittest.main()
