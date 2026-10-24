"""Visualisation of the mine (24.10.2026): the spread of a scenario through the plant on the map and in the diorama
(from the base copy in Ditto, «было → стало», hatching), the table «ход без сценария / со сценарием», the haul-road flow,
trucks that go on along the road between readings, the time axis of the trend, the draft «если сдавать сейчас», the
number of things in the documents. The helpers run in node (when it is installed); the rest are static checks."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "web", "static")
DOCS = os.path.join(os.path.dirname(ROOT), "final_docs")
SETUP = os.path.join(ROOT, "setup")
for p in (ROOT, SETUP):
    if p not in sys.path:
        sys.path.insert(0, p)


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


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
let tick = 1;
function world(scenario, now) {
  A.run = 'r1'; A.polled = tick++; A.simTime = 600;
  A.things = {
    site: mk('site', { scenario, tph: now.site, idSimulationRun: 'r1' }),
    baseline: mk('baseline', { idSimulationRun: 'r1', 'site_tph_base': 7500, 'crusher-1_tph_base': 3400, 'crusher-1_state_base': 'RUN', 'exc-1_state_base': 'DIG', 'exc-2_state_base': 'DIG',
      'stockpile-1_level_t_base': 38000, 'sag-1_feed_tph_base': 3300, 'line-1_cu_tph_base': 13.0, 'conc-stock_stock_t_base': 5000, 'pit_mining_tph_base': 7500, 'cum_cu_t_base': 100 }),
    'exc-1': mk('exc', { state: 'DOWN' }), 'exc-2': mk('exc', { state: 'DIG' }),
    pit: mk('pit', { mining_tph: now.pit }), 'crusher-1': mk('crusher', { state: now.crusher, tph: now.ctph }),
    'stockpile-1': mk('stockpile', { level_t: now.stock }), 'sag-1': mk('sag', { feed_tph: now.sag }),
    'line-1': mk('line', { cu_tph: now.cu }), 'conc-stock': mk('conc-stock', { stock_t: 5000 }),
  };
}
const out = {};
world('pitstop', { site: 3000, pit: 0, crusher: 'STOP', ctph: 0, stock: 31000, sag: 3300, cu: 6.0 });
out.cmp = A.cmpOpen(); out.hatch = A.hatchOn();
out.list = A.prop.list().map(c => c.thing);
out.texts = A.prop.list().map(c => c.text);
out.short = A.prop.short('stockpile-1');
out.noChange = A.prop.short('sag-1');
out.chain = [...A.scenarioChain()].sort();
out.banner = A.prop.chainText(3);
out.grouped = A.prop.grouped().map(c => c.text);
world('dose:1', { site: 3000, pit: 0, crusher: 'STOP', ctph: 0, stock: 31000, sag: 3300, cu: 6.0 });
out.hiddenCmp = A.cmpOpen(); out.hiddenList = A.prop.list().length;
world('', { site: 7500, pit: 7500, crusher: 'RUN', ctph: 3400, stock: 38000, sag: 3300, cu: 13.0 });
out.freeCmp = A.cmpOpen(); out.freeList = A.prop.list().length; out.freeShift = A.shiftResult();
const copies = (b, f) => ({ run: 'r1', kind: 'scenario', t_min: 600, copies: { base: b, fact: f, loud: { cu_t: -1 }, no_twin: { cu_t: -1 } } });
const row = (cu) => ({ cu_t: cu, ore_t: 1000, energy_mwh: 50, water_m3: 10, usd: cu * 9000 });
out.tableOk = A.shiftTable(copies(row(100), row(70)));
out.tableEmpty = A.shiftTable(copies({ cu_t: -1 }, { cu_t: -1 }));
out.noCompareFree = A.noCompareText();
out.win = A.lastWindow([{ sim_time: 380 }, { sim_time: 500 }, { sim_time: 560 }, { sim_time: 600 }], 120).map(p => p.sim_time);
out.draftFresh = A.draftTitle(600, 605, v => 'T' + v);
out.draftLate = A.draftTitle(475, 600, v => 'T' + v);
out.along = [A.truckAlong(0.5, 1, 'HAUL_FULL', 1, 10), A.truckAlong(0.95, 1, 'HAUL_FULL', 5, 10), A.truckAlong(0.5, 1, 'RETURN', 1, 10), A.truckAlong(0.5, 1, 'LOADING', 1, 10), A.truckAlong(0.5, -1, 'DUMP', 1, 10)];
console.log(JSON.stringify(out));
"""


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class SpreadHelpersTest(unittest.TestCase):
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

    def test_spread_is_in_the_order_of_the_process_with_before_and_after(self):
        o = self.o
        self.assertTrue(o["cmp"] and o["hatch"])
        order = ["pit", "exc-1", "crusher-1", "stockpile-1", "line-1"]
        self.assertEqual([t for t in o["list"] if t in order], order)
        self.assertNotIn("sag-1", o["list"])                 # SAG has not changed yet: it joins when its numbers move
        self.assertNotIn("exc-2", o["list"])
        self.assertTrue(all("→" in t for t in o["texts"]))
        short = o["short"].replace(" ", " ")
        self.assertIn("38 000", short)
        self.assertIn("31 000", short)
        self.assertEqual(o["noChange"], "")
        self.assertIn("ещё", o["banner"])
        self.assertEqual(sum(1 for t in o["grouped"] if t.startswith("Экскаваторы")), 1)
        self.assertIn("Экскаваторы: стоят 1 из 1", o["grouped"])

    def test_hatching_chain_contains_the_spread(self):
        self.assertTrue({"exc-1", "crusher-1", "stockpile-1", "line-1"} <= set(self.o["chain"]))

    def test_hidden_cause_and_free_run_show_no_comparison(self):
        o = self.o
        self.assertFalse(o["hiddenCmp"])
        self.assertEqual(o["hiddenList"], 0)
        self.assertFalse(o["freeCmp"])
        self.assertEqual(o["freeList"], 0)
        self.assertIsNone(o["freeShift"])

    def test_table_base_scenario_difference(self):
        t = self.o["tableOk"]
        self.assertIn("без сценария (база)", t)
        self.assertIn("со сценарием", t)
        self.assertIn("−30", t)
        self.assertNotIn("<tr><td>", self.o["tableEmpty"])
        self.assertIn("первые минуты", self.o["tableEmpty"])
        self.assertIn("Запустите сценарий", self.o["noCompareFree"])

    def test_trend_window_is_two_hours_of_model_time(self):
        self.assertEqual(self.o["win"], [500, 560, 600])

    def test_draft_title_shows_its_own_time_and_lag(self):
        self.assertEqual(self.o["draftFresh"], "Если сдавать сейчас (T600 модели)")
        self.assertIn("черновик на T475", self.o["draftLate"])
        self.assertIn("сейчас T600", self.o["draftLate"])

    def test_truck_goes_on_in_the_direction_of_its_state_and_waits_at_the_end(self):
        a = self.o["along"]
        self.assertAlmostEqual(a[0]["f"], 0.6)
        self.assertEqual(a[1], {"f": 0.97, "dir": 1})        # does not turn round by itself
        self.assertAlmostEqual(a[2]["f"], 0.4)
        self.assertEqual(a[2]["dir"], -1)
        self.assertEqual(a[3]["f"], 0.03)
        self.assertEqual(a[4], {"f": 0.97, "dir": 1})


class StaticSpreadTest(unittest.TestCase):
    def test_script_is_loaded_and_parses(self):
        html = read(STATIC, "index.html")
        srcs = re.findall(r'<script src="/([^"]+)"', html)
        self.assertIn("prop.js", srcs)
        self.assertLess(srcs.index("app.js"), srcs.index("prop.js"))
        self.assertLess(srcs.index("prop.js"), srcs.index("plan.js"))
        if shutil.which("node"):
            for name in ("prop.js", "plan.js", "app.js", "card.js", "flow.js", "views.js", "pages.js", "help.js", "line.js", "site3d.js"):
                r = subprocess.run(["node", "--check", os.path.join(STATIC, name)], capture_output=True, encoding="utf-8", timeout=60)
                self.assertEqual(r.returncode, 0, f"{name}: {r.stderr[:300]}")

    def test_hatching_does_not_wait_for_the_check_mode(self):
        for name in ("plan.js", "line.js", "site3d.js"):
            self.assertNotRegex(read(STATIC, name), r"AKT\.check\s*&&\s*chain\.has|chain\.has\([^)]*\)\s*&&\s*AKT\.check", name)
        self.assertIn("AKT.hatchOn()", read(STATIC, "plan.js"))

    def test_diorama_labels_and_glow_know_the_spread(self):
        core = read(STATIC, "diorama", "core.js")
        self.assertIn("AKT.prop.short(L.thing)", core)
        self.assertIn("derived.scen.has(id)", core)
        self.assertIn("AKT.prop.affected()", core)

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_diorama_modules_parse_as_es_modules(self):
        d = os.path.join(STATIC, "diorama")
        for name in sorted(os.listdir(d)):
            if name.endswith(".js"):
                with tempfile.TemporaryDirectory() as tmp:
                    p = os.path.join(tmp, name[:-3] + ".mjs")
                    with open(p, "w", encoding="utf-8") as f:
                        f.write(read(d, name))
                    r = subprocess.run(["node", "--check", p], capture_output=True, encoding="utf-8", timeout=60)
                self.assertEqual(r.returncode, 0, f"{name}: {r.stderr[:300]}")

    def test_diorama_truck_is_not_restarted_by_a_reading_of_the_same_phase(self):
        m = read(STATIC, "diorama", "mining.js")
        self.assertIn("dpub", m)
        self.assertIn("if (j === k)", m)

    def test_map_has_flow_on_haul_roads_and_red_where_copper_is_lost(self):
        p = read(STATIC, "plan.js")
        for s in ("haul-flow", "AKT.troubleLoss", "this.hauls", "AKT.truckAlong"):
            self.assertIn(s, p)
        self.assertIn("AKT.troubleLoss = troubleLoss", read(STATIC, "flow.js"))
        css = read(STATIC, "style.css")
        for sel in (".plan .haul-flow", ".plan .belt.loss", ".dl.g-scen"):
            self.assertIn(sel, css)

    def test_banner_has_the_chain_and_no_new_permanent_block(self):
        a = read(STATIC, "app.js")
        self.assertRegex(a, r'<div id="b-chain" class="b-chain" hidden>')     # inside the scenario banner, hidden by default
        self.assertIn("AKT.prop.grouped()", a)
        self.assertLess(a.index('id="p-banner"'), a.index('id="b-chain"'))
        self.assertLess(a.index('id="b-chain"'), a.index('id="b-confirm"'))

    def test_base_copy_carries_the_pit_and_excavators(self):
        from sim import service
        names = dict(service.BASE_FEATURES)
        self.assertIn("mining_tph", names["pit"])
        for n in (1, 2, 3):
            self.assertEqual(names[f"exc-{n}"], ("state", "tph"))

    def test_one_number_of_things_in_all_documents(self):
        import twins
        n = len(twins.Model().things)
        self.assertEqual(n, 136)
        for name in ("README_aktogay.md", "SUBMISSION.md"):
            t = read(DOCS, name)
            for m in re.finditer(r"(\d+)\s+(?:постоянн\w+\s+вещ\w+|постоянных\s+вещей)", t):
                self.assertEqual(int(m.group(1)), n, f"{name}: {m.group(0)}")
            self.assertNotRegex(t, r"\b(?:127|133)\s+постоянн")
        self.assertIn("создаёт 136", read(DOCS, "README_aktogay.md"))

    def test_no_text_for_a_reader_outside_the_dispatcher(self):
        bad = re.compile(r"жюри|судь[яеи]|для\s+ИИ|нейросет|\bLLM\b", re.I)
        self.assertIsNone(bad.search(read(STATIC, "prop.js")))


if __name__ == "__main__":
    unittest.main()
