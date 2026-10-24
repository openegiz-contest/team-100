"""The effect of a scenario is the fact minus the base copy at the same model minute (24.10.2026), not «before the scenario → now».
The helpers run in node (when it is installed); the rest are static checks."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "web", "static")

HARNESS = r"""
const vm = require('vm'), fs = require('fs');
const dir = process.argv[2];
const sb = { location: { search: '' }, history: {}, navigator: {}, console, setTimeout, setInterval, clearInterval, URLSearchParams, Date, Math, Intl, isFinite, performance: { now: () => 0 } };
sb.window = sb;
sb.document = { addEventListener() {}, getElementById() { return null; }, querySelector() { return null; }, querySelectorAll() { return []; }, createElement() { return { style: {}, classList: { add() {} } }; }, body: {} };
vm.createContext(sb);
for (const f of ['app.js', 'prop.js']) vm.runInContext(fs.readFileSync(dir + '/' + f, 'utf8').replace(/^'use strict';/, ''), sb, { filename: f });
const A = sb.AKT;
const mk = (type, feats) => ({ attributes: { type }, features: Object.fromEntries(Object.entries(feats).map(([k, v]) => [k, { properties: { value: v } }])) });
function world(scenario, withBase, cu) {
  A.run = 'r1'; A.polled = 1; A.simTime = 600;
  A.things = { site: mk('site', { scenario, cu_tph: 27.0, idSimulationRun: 'r1' }), 'line-1': mk('line', { cu_tph: cu }),
    baseline: mk('baseline', Object.assign({ idSimulationRun: 'r1' }, withBase ? { 'line-1_cu_tph_base': 29.6, 'site_cu_tph_base': 40.0 } : {})) };
}
const out = {};
world('crusher:1', true, 15.8); out.line = A.scenEffect('crusher:1');
world('grid', true, 15.8); out.site = A.scenEffect('grid');
world('crusher:1', false, 15.8); out.nobase = A.scenEffect('crusher:1');
world('dose:1', true, 15.8); out.hidden = A.scenEffect('dose:1');
console.log(JSON.stringify(out));
"""


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class EffectTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "h.js")
            with open(p, "w", encoding="utf-8") as f:
                f.write(HARNESS)
            r = subprocess.run(["node", p, STATIC], capture_output=True, encoding="utf-8", timeout=60)
        if r.returncode != 0:
            raise AssertionError(r.stderr[:1500])
        cls.o = json.loads(r.stdout.strip().splitlines()[-1])

    def test_effect_is_fact_minus_base_of_the_line(self):
        e = self.o["line"]
        self.assertAlmostEqual(e["effect"], 15.8 - 29.6, places=6)
        self.assertIn("Медь линии 1: база 29,6 → факт 15,8 т Cu/ч, эффект −13,8", e["text"].replace(" ", " "))
        self.assertIn("в ту же минуту модели", e["text"])
        self.assertIn("колебание руды вычтено", e["text"])

    def test_site_total_when_the_scenario_names_no_line(self):
        self.assertIn("Медь станции", self.o["site"]["text"])

    def test_no_base_copy_keeps_the_old_pair(self):
        self.assertIsNone(self.o["nobase"])

    def test_hidden_cause_shows_no_comparison(self):
        self.assertIsNone(self.o["hidden"])


class StaticTest(unittest.TestCase):
    def read(self, name):
        with open(os.path.join(STATIC, name), encoding="utf-8") as f:
            return f.read()

    def test_banner_falls_back_with_a_caption(self):
        a = self.read("app.js")
        self.assertIn("AKT.scenEffect(scen)", a)
        self.assertIn("Копии без сценария здесь нет: в разнице есть и колебание руды", a)
        self.assertIn("база в ту же минуту модели → факт сейчас, эффект", a)

    def test_chain_items_carry_the_effect(self):
        p = self.read("prop.js")
        self.assertIn("база ${fnum(b, spec[3])}", p)
        self.assertIn("эффект", p)

    def test_loading_the_expected_result_does_not_call_update_in_a_loop(self):
        """AKT.verify.load calls back at once when the file is there; the banner asks for the file only while it is missing
        (the screenshot of 24.10.2026 caught «Maximum call stack size exceeded»)."""
        a = self.read("app.js")
        self.assertIn("if (!AKT.verify.data) AKT.verify.load(() => Panel.update());", a)
        self.assertNotIn("      AKT.verify.load(() => Panel.update());", a)

    def test_legend_explains_the_arrow(self):
        self.assertIn("Число → число при сценарии", self.read("views.js"))


if __name__ == "__main__":
    unittest.main()


HARNESS2 = r"""
const vm = require('vm'), fs = require('fs');
const dir = process.argv[2];
const sb = { location: { search: '' }, history: {}, navigator: {}, console, setTimeout, setInterval, clearInterval, URLSearchParams, Date, Math, Intl, isFinite, performance: { now: () => 0 } };
sb.window = sb;
sb.document = { addEventListener() {}, getElementById() { return null; }, querySelector() { return null; }, querySelectorAll() { return []; }, createElement() { return { style: {}, classList: { add() {} } }; }, body: {} };
vm.createContext(sb);
for (const f of ['app.js', 'prop.js']) vm.runInContext(fs.readFileSync(dir + '/' + f, 'utf8').replace(/^'use strict';/, ''), sb, { filename: f });
const A = sb.AKT;
A.verify.data = JSON.parse(fs.readFileSync(dir + '/verify.json', 'utf8'));
const mk = (type, feats) => ({ attributes: { type }, features: Object.fromEntries(Object.entries(feats).map(([k, v]) => [k, { properties: { value: v } }])) });
function world(scenario, seed, sim, extra) {
  A.run = 'r1'; A.polled = 1; A.simTime = sim;
  A.things = Object.assign({ site: mk('site', { scenario, seed, idSimulationRun: 'r1' }), 'stockpile-1': mk('stockpile', { state: 'NORMAL' }), 'sag-1': mk('sag', { state: 'RUN' }) }, extra || {});
}
const out = {};
world('crusher:1', 42, 600); out.c1 = A.verify.banner('crusher:1');
world('crusher:1', 7, 600); out.otherSeed = A.verify.banner('crusher:1');
world('conveyor:1', 42, 600); out.conv = A.verify.banner('conveyor:1');
world('conveyor:1', 42, 600 + 400, { 'stockpile-1': mk('stockpile', { state: 'EMPTY' }) }); A.scenStart = () => 480; out.convSeen = A.verify.banner('conveyor:1');
world('fork', 42, 600); out.fork = A.verify.banner('fork');
world('dose:1', 42, 600); out.hidden = A.verify.banner('dose:1');
console.log(JSON.stringify(out));
"""


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class ExpectedResultBannerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "h2.js")
            with open(p, "w", encoding="utf-8") as f:
                f.write(HARNESS2)
            r = subprocess.run(["node", p, STATIC], capture_output=True, encoding="utf-8", timeout=60)
        if r.returncode != 0:
            raise AssertionError(r.stderr[:1500])
        cls.o = json.loads(r.stdout.strip().splitlines()[-1])

    def test_banner_gives_the_expected_result_with_seed_and_label(self):
        t = self.o["c1"].replace(" ", " ")
        self.assertIn("Ожидаемый итог к 20:00", t)
        self.assertIn("посчитано заранее тем же кодом, seed 42, оценка на модели", t)
        self.assertIn("−0,74 т Cu", t)

    def test_another_seed_says_nothing_to_compare(self):
        self.assertIn("сверять нечего", self.o["otherSeed"])

    def test_key_moment_and_its_status(self):
        t = self.o["conv"]
        self.assertIn("склад руды линии 1 кончится", t)
        self.assertIn("10:57", t)
        self.assertIn("ждём", t)
        self.assertIn("подтверждено в", self.o["convSeen"])

    def test_fork_names_the_three_numbers(self):
        t = self.o["fork"].replace(" ", " ")
        self.assertIn("находка", t)
        self.assertIn("порядок вызова", t)

    def test_hidden_cause_has_no_expected_result(self):
        self.assertEqual(self.o["hidden"], "")
