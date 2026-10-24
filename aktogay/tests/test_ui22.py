"""The interface of the 23.10.2026 block (static checks, no browser): menu of four groups, the new second-level views
(Прогнозы, Путь меди, Участки, Журнал, Отчёт смены, Экономика, Как проверить, Тренировка), training frame and its
guard on calls, forecast marks (dashed, «≈»), scenario ids, JS syntax (when node is installed)."""
import json
import os
import re
import shutil
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "web", "static")
WEB = os.path.join(ROOT, "web")
if WEB not in sys.path:
    sys.path.insert(0, WEB)

import server  # noqa: E402

NEW_JS = ("forecast.js", "flow.js", "pages.js", "backtest.js")


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


class StaticFilesTest(unittest.TestCase):
    def test_index_loads_every_script_that_exists(self):
        html = read(STATIC, "index.html")
        srcs = re.findall(r'<script src="/([^"]+)"', html)
        for s in srcs:
            self.assertTrue(os.path.exists(os.path.join(STATIC, s)), s)
        for s in NEW_JS:
            self.assertIn(s, srcs)
        # app.js first (defines AKT), the views after views.js, the start call last
        self.assertEqual(srcs[0], "app.js")
        self.assertLess(srcs.index("views.js"), srcs.index("forecast.js"))
        self.assertLess(srcs.index("forecast.js"), srcs.index("pages.js"))

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_javascript_parses(self):
        for name in sorted(os.listdir(STATIC)):
            if name.endswith(".js"):
                r = subprocess.run(["node", "--check", os.path.join(STATIC, name)], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, f"{name}: {r.stderr[:300]}")

    def test_no_text_addressed_to_a_reader_outside_the_dispatcher(self):
        bad = re.compile(r"жюри|судь[яеи]|для\s+ИИ|нейросет|языков\w+\s+модел|\bAI\b|\bLLM\b", re.I)
        for name in NEW_JS + ("app.js", "help.js", "views.js", "ru.js"):
            for i, line in enumerate(read(STATIC, name).splitlines(), 1):
                self.assertIsNone(bad.search(line), f"{name}:{i}: {line[:80]}")


class MenuTest(unittest.TestCase):
    def setUp(self):
        self.app = read(STATIC, "app.js")

    def test_four_groups_of_three_to_five_items(self):
        m = re.search(r"const MENU4 = \[(.*?)\n\];", self.app, re.S)
        self.assertIsNotNone(m)
        groups = re.findall(r"\['(\w+)', '([^']+)', \[(.*?)\]\],?\n", m.group(1) + "\n", re.S)
        self.assertEqual([g[1] for g in groups], ["Сейчас", "Смена", "Анализ", "Обучение и справка"])
        for _gid, name, body in groups:
            n = len(re.findall(r"\['(\w+)', '[^']+'\]", body))
            self.assertTrue(3 <= n <= 5, f"{name}: {n} items")
        views = re.findall(r"\['(\w+)', '[^']+'\]", m.group(1))
        for v in ("plan", "queue", "areas", "forecast", "copper", "handover", "report", "journal", "economics", "calib",
                  "howto", "legend", "train", "tour"):
            self.assertIn(v, views)

    def test_every_menu_view_is_registered(self):
        m = re.search(r"const MENU4 = \[(.*?)\n\];", self.app, re.S)
        views = set(re.findall(r"\['(\w+)', '[^']+'\]", m.group(1))) - {"tour"}
        code = "".join(read(STATIC, n) for n in os.listdir(STATIC) if n.endswith(".js"))
        for v in views:
            self.assertRegex(code, r"AKT\.views\.%s\s*=" % v, v)

    def test_old_views_stay_reachable_through_the_hub(self):
        flow = read(STATIC, "flow.js")
        for v in ("line&n=1", "line&n=2", "diorama", "site", "ore", "tree", "text", "copper"):
            self.assertIn("?view=" + v, flow, v)

    def test_main_screen_has_no_new_permanent_block(self):
        # the six tiles stay; the copper forecast sits inside the copper tile; nothing else was added to the panel
        tiles = re.findall(r'<div class="tile" id="(k-\w+)"', self.app)
        self.assertEqual(tiles, ["k-loss", "k-cu", "k-ore", "k-rec", "k-mw", "k-usd"])
        cu = re.search(r'<div class="tile" id="k-cu".*?</div></div>', self.app, re.S).group(0)
        self.assertIn('id="k-cu-f"', cu)


class ForecastMarksTest(unittest.TestCase):
    def test_forecast_is_dashed_with_a_corridor_and_an_approx_sign(self):
        css = read(STATIC, "style.css")
        self.assertRegex(css, r"\.fc-dash\s*\{[^}]*stroke-dasharray")
        self.assertIn(".fc-band", css)
        js = read(STATIC, "forecast.js")
        self.assertIn("≈", js)
        self.assertIn("fc-dash", js)
        self.assertIn("fc-band", js)
        self.assertIn("коридор", js)

    def test_the_copper_tile_gets_the_forecast(self):
        self.assertIn("AKT.fc.tileSvg()", read(STATIC, "app.js"))


class TrainingTest(unittest.TestCase):
    def test_frame_on_every_screen_and_calls_stay_learning(self):
        css = read(STATIC, "style.css")
        self.assertRegex(css, r"body\.training::after\s*\{[^}]*position:\s*fixed[^}]*inset:\s*0")
        app = read(STATIC, "app.js")
        self.assertRegex(app, r"AKT\.train && AKT\.train\.on\(\) && /\^\\/api\\/\(call\|snooze\|remind\|mech\)")
        self.assertIn("учебный вызов", app)
        pages = read(STATIC, "pages.js")
        self.assertIn("не пишутся в журнал", pages)
        # the training log is only in the browser: no POST to the journal from the training page
        train = pages[pages.index("AKT.views.train"):pages.index("// journal") if "// journal" in pages else pages.index("AKT.views.journal")]
        self.assertNotIn("AKT.post", train)
        self.assertNotIn("/api/call", train)


class ScenarioIdsTest(unittest.TestCase):
    def test_new_scenarios_are_offered_and_accepted(self):
        app = read(STATIC, "app.js")
        for sid in ("pitstop", "conveyor:1"):
            self.assertIn(f"id: '{sid}'", app)
            self.assertIsNotNone(server.RE_SCENARIO.match(sid))
        self.assertIn("pit_stop", read(STATIC, "ru.js"))


class JournalCsvTest(unittest.TestCase):
    def test_csv_is_excel_friendly(self):
        js = read(STATIC, "pages.js")
        self.assertIn("\\ufeff", js)               # BOM
        self.assertIn("join(';')", js)
        self.assertIn("text/csv;charset=utf-8", js)
        self.assertIn("replace(/\"/g, '\"\"')", js)


class AskTest(unittest.TestCase):
    def test_new_questions_for_the_new_features(self):
        js = read(STATIC, "help.js")
        for qid in ("pitstop", "liner", "cuend", "econ", "balance"):
            self.assertIn(f"['{qid}', ", js)
            self.assertRegex(js, r"\n    %s\(\) \{" % qid)


class ThingsTest(unittest.TestCase):
    def test_new_features_are_in_the_catalog(self):
        d = json.loads(read(ROOT, "setup", "things.json"))
        t = d["types"]
        self.assertEqual(t["mod-priority"]["features"]["forecast"], "obj")
        self.assertEqual(t["mod-priority"]["features"]["forecast_text"], "text")
        self.assertEqual(t["conveyor"]["features"]["fault"], "flag")
        self.assertEqual(t["sag"]["features"]["liner_ground_t"], "t")
        for k in ("hpgr_tph", "hpgr_load_pct", "hpgr_kw"):
            self.assertIn(k, t["pebble"]["features"])


if __name__ == "__main__":
    unittest.main()
