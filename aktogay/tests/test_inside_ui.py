"""Tier S in the web interface (23.10.2026): the page «Изнутри» (inside.json, three machine labels), scenario buttons, Russian words for
every new feature and trouble kind, evidence with the age of the data in the issue card, the howto rows, the HPGR on «Путь меди»,
the two fixes of the stand. Static checks over the files of web/static plus the check of web/static/inside.json against
setup/things.json (when the file exists) and, if node is installed, the pure helpers of inside.js run in node."""
import json
import os
import re
import shutil
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

STATIC = os.path.join(ROOT, "web", "static")


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


def js(name):
    return read(STATIC, name)


NEW_KINDS = ("road_winter", "driver_fatigue", "roping", "sensor_ph", "hpgr_uneven", "crusher_mantle", "oil_contam", "exc_down")
NEW_FEATURES = ("visibility_m", "road_grip", "haul_speed_pct", "road_restrict", "oil_pct", "oil_alert", "fatigue", "fatigue_truck",
                "service", "service_left_h", "circ_load_pct", "power_pct", "hpgr_skew_pct", "hpgr_kw_diff_pct", "metal_alarm",
                "ph", "sp_ph", "lab_ph", "evidence", "evidence_text", "notify_text")
NEW_SCENARIOS = ("icy", "fatigue", "roping:1", "phdrift:1", "hpgr:2", "mantle:1", "oil")
HOWTO_TITLES = ("Метель и гололёд: ограничить движение", "Усталость водителя (сценарий, допущение)",
                "Канатирование циклонов и перегрузка шаровой", "Датчик под подозрением и возраст данных",
                "Неравномерное питание ВВД линии 2", "Руда сменилась — режим старый", "Замена брони дробилки",
                "Загрязнение масла экскаватора EX01", "Отказ экскаватора")
MACHINE_WHERE = ("machine", "sent", "analog")


class StaticTest(unittest.TestCase):
    def test_scenario_buttons_and_tokens(self):
        app = js("app.js")
        for sid in NEW_SCENARIOS:
            self.assertIn(f"id: '{sid}'", app, sid)
        for tok in ("icy:", "fatigue:", "oil:", "roping:", "phdrift:", "hpgr:", "mantle:"):
            self.assertIn(tok, app, tok)
        # the hidden causes stay hidden in the banner like dose / oxide
        self.assertRegex(app, r"HIDDEN_KINDS = new Set\(\[[^\]]*'roping'[^\]]*'phdrift'")
        for word in ("допущение", "Метель и гололёд на откатке", "pH-метр врёт", "Канатирование циклонов", "Замена брони дробилки 1"):
            self.assertIn(word, app)
        # the server lets the tokens through
        rx = re.search(r'RE_SCENARIO = re\.compile\(r"([^"]+)"\)', read(ROOT, "web", "server.py")).group(1)
        for sid in NEW_SCENARIOS:
            self.assertRegex(sid, rx)

    def test_russian_words_for_new_kinds_features_roles_types(self):
        ru, app, card = js("ru.js"), js("app.js"), js("card.js")
        for k in NEW_KINDS:
            self.assertRegex(ru, rf"\b{k}:", k)
        for f in NEW_FEATURES:
            self.assertRegex(ru, rf"\b{f}:", f)
        self.assertIn("phmeter:", ru)
        self.assertIn("Начальник смены карьера", read(ROOT, "setup", "things.json"))
        for role in ("mine_shift_head", "road_service"):
            self.assertIn(role, app)
        self.assertIn("начальника смены карьера", app)
        self.assertIn("дорожную службу карьера", app)
        # the excavator card carries the sensor sentence, the pH meter and the people have a "what is it"
        self.assertIn("на машине (видит оператор); в диспетчерскую — если подключена опция Global e-Service", card)
        self.assertIn("oil_pct", card)
        self.assertIn("phmeter:", card)

    def test_header_text_is_said_once(self):
        app = js("app.js")
        self.assertIn("price === 'потерь пока нет' ? ''", app)

    def test_issue_card_shows_evidence_with_age(self):
        app, views, pages = js("app.js"), js("views.js"), js("pages.js")
        self.assertIn("AKT.evidenceHtml", app)
        for word in ("Измерения и возраст данных", "Также сообщить", "под подозрением", "давно", "age_pub_min", "age_meas_min"):
            self.assertIn(word, app, word)
        self.assertIn('id="tc-evid"', app)                      # inside «Подробнее», not a new block of the main screen
        self.assertIn("tc-more", app)
        self.assertIn("Измерения и возраст данных", views)      # the page «Беды»
        self.assertIn("evidenceItems", pages)                   # the shift report marks doubtful data

    def test_howto_rows_and_connect_column(self):
        pages = js("pages.js")
        for t in HOWTO_TITLES:
            self.assertIn(t, pages, t)
        self.assertIn("Что подключить", pages)
        self.assertIn("r.connect", pages)

    def test_copper_path_hpgr_and_pit_box(self):
        flow = js("flow.js")
        self.assertIn("ВВД (POLYCOM)", flow)
        self.assertIn("hpgr_tph", flow)
        self.assertIn("metal_alarm", flow)
        self.assertIn("hpgr_skew_pct", flow)
        self.assertIn("все экскаваторы", flow)                  # the label has its own box width now
        self.assertIn("const bx = [4, 156, 276, 410, 530], bw = [104,", flow)
        self.assertIn("view=inside", flow)                      # a link from «Участки»

    def test_ask_the_twin_and_glossary(self):
        h = js("help.js")
        for q in ("Что сейчас под подозрением из датчиков?", "Где дорога опасна?", "Какие данные устарели?"):
            self.assertIn(q, h)
        for t in ("Канатирование", "Перекос ВВД", "Возраст данных", "Под подозрением", "Наряд-допуск"):
            self.assertIn(t, h)

    def test_inside_page_is_wired(self):
        src, app, idx = js("inside.js"), js("app.js"), js("index.html")
        self.assertIn('/inside.json', src)
        self.assertIn("src=\"/inside.js\"", idx)
        self.assertIn("['inside', 'Изнутри']", app)
        for tab_word in ("where_ru", "depth_ru", "faces", "dam", "people", "machines", "plant", "env"):
            self.assertIn(tab_word, src, tab_word)
        # the three machine labels are drawn from where_ru, not written in the page
        for code in MACHINE_WHERE:
            self.assertIn(code, src)
        for fixed in ("на машине (видит водитель / оператор)", "передаётся, если подключена опция", "аналог другой модели"):
            self.assertNotIn(fixed, src)
        self.assertIn("AKT.insideHref", src)
        self.assertIn("AKT.insideHref", js("card.js"))
        self.assertIn("view=inside", js("flow.js"))
        # menu: 4 groups x 3-5 items
        m = re.search(r"const MENU4 = \[(.*?)\n\];", app, re.S).group(1)
        groups = re.findall(r"\['(\w+)', '[^']+', \[(.*?)\]\],", m)
        self.assertEqual(len(groups), 4)
        for gid, items in groups:
            n = len(re.findall(r"\['\w+', '[^']+'\]", items))
            self.assertTrue(3 <= n <= 5, (gid, n))

    def test_no_new_permanent_block_on_the_main_screen(self):
        idx, app = js("index.html"), js("app.js")
        self.assertNotIn("inside", idx.replace('/inside.js', ''))
        self.assertEqual(app.count('id="tc-evid"'), 1)


class InsideJsonTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(STATIC, "inside.json")
        if not os.path.isfile(self.path):
            self.skipTest("web/static/inside.json is not written yet")
        with open(self.path, encoding="utf-8") as f:
            self.D = json.load(f)
        with open(os.path.join(ROOT, "setup", "things.json"), encoding="utf-8") as f:
            self.tj = json.load(f)
        self.things = {t["name"]: t["type"] for t in self.tj["things"]}
        self.common = set(self.tj.get("common_features", {}))

    def expand(self, spec):
        if spec in (None, ""):
            return []
        parts = spec if isinstance(spec, list) else [x for x in re.split(r"[\s,;]+", str(spec)) if x]
        out = []
        for s in parts:
            if "{n}" in s:
                out += [s.replace("{n}", str(n)) for n in (1, 2, 3) if s.replace("{n}", str(n)) in self.things]
            else:
                out.append(s)
        return out

    def test_schema(self):
        D = self.D
        self.assertEqual(len(D["groups"]), 6)
        self.assertEqual({g["live"] for g in D["groups"]}, {"faces", "dam", "people", "machines", "plant", "env"})
        for code in MACHINE_WHERE:
            self.assertIn(code, D["where_ru"])
        self.assertEqual(set(D["depth_ru"]), {"A", "B", "C"})
        for g in D["groups"]:
            self.assertIn(g["depth"], "ABC")
            self.assertTrue(g["nodes"], g["id"])
            for nd in g["nodes"]:
                self.assertIn(nd["depth"], "ABC", nd["id"])
                for s in nd.get("signals", []):
                    self.assertIn(s["where"], D["where_ru"], f"{nd['id']}: {s['name']}")
                    if s.get("label"):
                        self.assertIn(s["label"], D["labels"], s["name"])
                for f in nd.get("failures", []):
                    if f.get("label"):
                        self.assertIn(f["label"], D["labels"], f["name"])

    def test_every_thing_and_feature_exists(self):
        types = self.tj["types"]
        for g in self.D["groups"]:
            for nd in g["nodes"]:
                for name in self.expand(nd.get("thing")):
                    self.assertIn(name, self.things, f"{nd['id']}: {name}")
                for s in nd.get("signals", []):
                    if not (s.get("thing") and s.get("feature")):
                        continue
                    names = self.expand(s["thing"])
                    self.assertTrue(names, f"{nd['id']}: {s['name']}: no thing for {s['thing']}")
                    for name in names:
                        self.assertIn(name, self.things, f"{nd['id']}: {s['name']}: {name}")
                        feats = set(types[self.things[name]]["features"]) | self.common
                        self.assertIn(s["feature"], feats, f"{nd['id']}: {s['name']}: {name}.{s['feature']}")

    def test_trouble_kinds_are_known(self):
        from modules import priority
        known = set(priority.WHO) | set(priority.SHORT_RU) | {"water_leak"}
        for g in self.D["groups"]:
            for nd in g["nodes"]:
                for k in nd.get("troubles", []) + [f["trouble"] for f in nd.get("failures", []) if f.get("trouble")]:
                    self.assertIn(k, known, f"{nd['id']}: {k}")


NODE_CHECK = r"""
const vm = require('vm'), fs = require('fs');
const things = { 'ph-1': {}, 'ph-2': {}, 'sag-1': {}, 'sag-2': {}, 'water': {}, 'piezo-1': {}, 'piezo-2': {}, 'piezo-3': {}, 'exc-1': {} };
const raw = { 'ph-1': { lab_ph: 11.4, state: 'OK' }, 'ph-2': { lab_ph: -1 }, 'exc-1': { oil_pct: 87.6 }, 'piezo-1': { kpa: 120.4 } };
const types = { 'ph-1': 'phmeter', 'ph-2': 'phmeter', 'sag-1': 'sag', 'sag-2': 'sag', water: 'water', 'piezo-1': 'piezometer', 'exc-1': 'exc' };
const AKT = { things, NB: ' ', params: new URLSearchParams(''), views: {}, esc: s => String(s), fmt: (v, d = 0) => v == null ? '—' : Number(v).toFixed(d), f1: v => Number(v).toFixed(1),
  f2: v => Number(v).toFixed(2), f3: v => Number(v).toFixed(3), num: () => null, raw: (n, f) => (raw[n] || {})[f], TIME_FEATS: new Set(['free_at']),
  valText: (n, f) => String((raw[n] || {})[f]), nameRu: n => n, type: n => types[n] || '', cat: n => ({ 'piezo-1': 'piezo', 'exc-1': 'exc' }[n] || ''), href: h => h };
global.window = {}; global.AKT = AKT;
vm.runInThisContext(fs.readFileSync(process.argv[2], 'utf8'), { filename: 'inside.js' });
const h = AKT.inside.h;
const out = {
  expand_n: h.expand('ph-{n}'), expand_list: h.expand('a, b'), expand_arr: h.expand(['x', 'sag-{n}']), expand_none: h.expand('zz-{n}'),
  text_one: h.liveText('exc-1', 'oil_pct', 0, '%'), text_two: h.liveText('ph-{n}', 'lab_ph', 2, 'pH'), text_missing: h.liveText('nothing', 'x', 0, ''),
  g_piezo: h.groupOfThing('piezo-1'), g_water: h.groupOfThing('water'), g_exc: h.groupOfThing('exc-1'), g_sag: h.groupOfThing('sag-1'), g_ph: h.groupOfThing('ph-1'),
  href: AKT.insideHref('sag-1'),
};
console.log(JSON.stringify(out));
"""


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class NodeHelpersTest(unittest.TestCase):
    def test_pure_helpers_of_inside_js(self):
        tmp = os.path.join(os.environ.get("TEMP", os.environ.get("TMPDIR", "/tmp")), "akt_inside_check.js")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(NODE_CHECK)
        r = subprocess.run(["node", tmp, os.path.join(STATIC, "inside.js")], capture_output=True, encoding="utf-8", timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        o = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(o["expand_n"], ["ph-1", "ph-2"])
        self.assertEqual(o["expand_list"], ["a", "b"])
        self.assertEqual(o["expand_arr"], ["x", "sag-1", "sag-2"])
        self.assertEqual(o["expand_none"], [])
        self.assertEqual(o["text_one"], "88 %")
        self.assertEqual(o["text_two"], "ph-1: 11.40 pH; ph-2: —")
        self.assertEqual(o["text_missing"], "—")
        self.assertEqual((o["g_piezo"], o["g_water"], o["g_exc"], o["g_sag"], o["g_ph"]), ("dam", "dam", "machines", "plant", "env"))
        self.assertEqual(o["href"], "?view=inside&g=plant&t=sag-1")


class NodeSyntaxTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_files_parse(self):
        for name in ("app.js", "ru.js", "card.js", "views.js", "pages.js", "help.js", "flow.js", "inside.js"):
            r = subprocess.run(["node", "--check", os.path.join(STATIC, name)], capture_output=True, encoding="utf-8", errors="replace", timeout=60)
            self.assertEqual(r.returncode, 0, f"{name}: {r.stderr}")


if __name__ == "__main__":
    unittest.main()
