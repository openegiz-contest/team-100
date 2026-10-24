"""Разбор машин в диораме (diorama/parts.js, models.js, inspect.js): таблица частей против inside.json, привязка
часть -> узел -> сигналы, логика подсветки (беда, прогноз перефутеровки), разбор модулей в node (чистые функции и
построение моделей без браузера), крючок щелчка в ядре."""
import json
import os
import re
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "web", "static")
DIO = os.path.join(STATIC, "diorama")


def read(*p):
    with open(os.path.join(*p), encoding="utf-8", newline="") as f:
        return f.read()


NODE = shutil.which("node")

PARTS_JS = r"""
import { pathToFileURL } from 'node:url';
import fs from 'node:fs';
const P = await import(pathToFileURL(process.argv[2]).href);
const D = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const sig = (kind, id, part) => P.partSignals(D, kind, id, part).map(s => s.name.slice(0, 200));
const out = {
  kinds: ['truck-21', 'exc-1', 'exc-5', 'exc-2', 'sag-2', 'crusher-1', 'conveyor-2', 'dozer-21', 'ball-1a', 'ball-2b', 'pebble-2', 'flot-1', 'cyclones-2', 'thick-1', 'filter-2', 'pump-1', 'rougher-1', 'ball-1'].map(P.kindOf),
  pn: ['ball-1a', 'pebble-2', 'flot-1', 'cyclones-2', 'thick-1', 'filter-2', 'pump-1'].map(P.nodeOf),
  ps: { ballmotor: sig('ball', 'ball-1a', 'motor'), skew: sig('hpgr', 'pebble-2', 'roll1'), metal: sig('hpgr', 'pebble-2', 'detector'), drv: sig('hpgr', 'pebble-2', 'drives'),
        level: sig('flot', 'flot-1', 'level'), rec: sig('flot', 'flot-1', 'tank'), cyc: sig('cyclones', 'cyclones-1', 'cyclones'), dist: sig('cyclones', 'cyclones-1', 'distributor'),
        tq: sig('thick', 'thick-1', 'drive'), inv: sig('thick', 'thick-1', 'tank'), plates: sig('filter', 'filter-1', 'plates'), cloth: sig('filter', 'filter-1', 'cloth'),
        bear: sig('pump', 'pump-1', 'bearings'), gland: sig('pump', 'pump-1', 'gland'),
        none: [sig('ball', 'ball-1a', 'liner'), sig('flot', 'flot-1', 'rotor'), sig('thick', 'thick-1', 'rake'), sig('filter', 'filter-1', 'ram'), sig('hpgr', 'pebble-2', 'press'), sig('pump', 'pump-1', 'base')] },
  hp: {
    rope: ['cyclones', 'apex', 'distributor', 'overflow'].map(p => P.highlightOf('cyclones', p, new Set(['roping']), null)),
    skewhl: ['roll1', 'roll2', 'drives', 'hopper', 'detector', 'press', 'frame'].map(p => P.highlightOf('hpgr', p, new Set(['hpgr_uneven']), null)),
    filt: ['plates', 'cloth', 'ram', 'frame'].map(p => P.highlightOf('filter', p, new Set(['filter_one']), null)),
    filtstop: ['plates', 'cloth', 'ram'].map(p => P.highlightOf('filter', p, new Set(['filter_stop']), null)),
    thick: ['tank', 'rake'].map(p => P.highlightOf('thick', p, new Set(['thick_full']), null)),
    flot: ['tank', 'launder', 'level'].map(p => P.highlightOf('flot', p, new Set(['loss_flot']), null)),
    whole: [P.wholeAlarm('filter', ['filter_stop']), P.wholeAlarm('hpgr', ['hpgr_fire']), P.wholeAlarm('ball', ['ball_stop']), P.wholeAlarm('cyclones', ['roping'])],
    tg: [P.toggleText('ball', false), P.toggleText('filter', true), P.toggleText('flot', false)],
  },
  nodes: ['truck-21', 'exc-1', 'exc-5', 'exc-2', 'sag-2', 'crusher-1', 'conveyor-2', 'dozer-21'].map(P.nodeOf),
  pumps: sig('exc', 'exc-1', 'pumps'), cylinders: sig('exc', 'exc-1', 'cylinders'), tracks: sig('exc', 'exc-1', 'tracks'),
  liner: sig('sag', 'sag-1', 'liner'), motor: sig('sag', 'sag-1', 'motor'), brakes: sig('truck', 'truck-21', 'brakes'),
  mantle: sig('crusher', 'crusher-1', 'mantle'), drive: sig('conveyor', 'conveyor-1', 'drive'), nosig: sig('truck', 'truck-21', 'chassis'),
  hl_oil: ['pumps', 'cylinders', 'tracks', 'engine'].map(p => P.highlightOf('exc', p, new Set(['oil_contam']), null)),
  hl_none: ['pumps', 'cylinders'].map(p => P.highlightOf('exc', p, new Set(), null)),
  hl_liner_issue: P.highlightOf('sag', 'liner', ['reline'], null),
  hl_liner_days: P.highlightOf('sag', 'liner', [], { share: 0.5, days_to_end: 9 }),
  hl_liner_share: P.highlightOf('sag', 'liner', [], { share: 0.93, days_to_end: 40 }),
  hl_liner_far: P.highlightOf('sag', 'liner', [], { share: 0.5, days_to_end: 120 }),
  hl_liner_other: P.highlightOf('sag', 'motor', [], { share: 0.99, days_to_end: 1 }),
  hl_fatigue: [P.highlightOf('truck', 'cab', ['driver_fatigue'], null), P.highlightOf('truck', 'body', ['driver_fatigue'], null)],
  whole: [P.wholeAlarm('sag', ['sag_stop']), P.wholeAlarm('sag', ['reline']), P.wholeAlarm('exc', new Set(['exc_down']))],
  ev: [P.evidenceRu('machine'), P.evidenceRu('sent'), P.evidenceRu('analog')],
  toggles: [P.toggleText('truck', false), P.toggleText('truck', true), P.toggleText('sag', false), P.toggleText('sag', true)],
  off: P.explodeOffset(P.partById('truck', 'wheels'), 0.5, 10),
  near: [P.linerNear(null), P.linerNear({ days_to_end: 14 }), P.linerNear({ days_to_end: 15, share: 0.1 })],
};
console.log(JSON.stringify(out));
"""

MODELS_JS = r"""
import { pathToFileURL } from 'node:url';
const M = await import(pathToFileURL(process.argv[2]).href);
const P = await import(pathToFileURL(process.argv[3]).href);
const C = { cat: 0xf2b500, tire: 0x222326, steel: 0x8d949c, steelDark: 0x4b525a, steelLight: 0xbfc5cb, white: 0xf2f2ef, hitachi: 0xef7a1a,
  glass: 0x9cc2d8, concrete: 0xcfcbc3, cladding: 0x6f8aa3, roof: 0x9ea7b1, wall: 0xe4e1da, ore: 0x8a7865, oreLight: 0xa48f75, belt: 0x30343a };
const out = {};
for (const [kind, build] of Object.entries(M.BUILDERS)) {
  const m = build(C);
  let tris = 0; const ids = new Set(); let bad = 0;
  for (const g of m.groups) {
    ids.add(g.part);
    for (const p of g.parts) {
      const geo = p.geometry, n = geo.index ? geo.index.count / 3 : geo.attributes.position.count / 3;
      tris += n;
      for (const v of geo.attributes.position.array) if (!Number.isFinite(v)) bad++;
      if (p.matrix) for (const v of p.matrix.elements) if (!Number.isFinite(v)) bad++;
    }
  }
  const table = P.partsOf(kind).map(p => p.id);
  out[kind] = { tris: Math.round(tris), missing: table.filter(x => !ids.has(x)), extra: [...ids].filter(x => !table.includes(x)), bad, size: m.size, scale: m.scale };
}
console.log(JSON.stringify(out));
"""


def run_node(script, *args):
    p = os.path.join(os.environ.get("TEMP", os.environ.get("TMPDIR", "/tmp")), "akt_inspect_check_%d.mjs" % abs(hash(script)))
    with open(p, "w", encoding="utf-8") as f:
        f.write(script)
    r = subprocess.run([NODE, p] + list(args), capture_output=True, encoding="utf-8", timeout=120)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout.strip().splitlines()[-1])


class TableTest(unittest.TestCase):
    """Таблица частей против inside.json и против известных видов бед (без node)."""

    @classmethod
    def setUpClass(cls):
        cls.D = json.loads(read(STATIC, "inside.json"))
        cls.nodes = {nd["id"]: nd for g in cls.D["groups"] for nd in g["nodes"]}
        cls.src = read(DIO, "parts.js")

    def test_every_node_exists_and_troubles_belong_to_node(self):
        for kind, nid in (("truck", "m-cat793"), ("exc", "m-ex3600"), ("sag", "p-sag"), ("crusher", "p-crusher"), ("conveyor", "p-conveyor"),
                          ("ball", "p-grind"), ("hpgr", "p-hpgr"), ("flot", "p-flot"), ("cyclones", "p-grind"), ("thick", "p-thick"),
                          ("filter", "p-filter"), ("pump", "p-pumps")):
            self.assertIn(nid, self.nodes, kind)
        for nid in ("m-ex1200", "m-ex-other"):
            self.assertIn(nid, self.nodes)

    def test_part_troubles_are_known_kinds(self):
        from modules import priority
        known = set(priority.WHO) | set(priority.SHORT_RU)
        kinds = set(re.findall(r"troubles: \[([^\]]*)\]", self.src))
        used = {k.strip().strip("'") for s in kinds for k in s.split(",") if k.strip()}
        used |= set(re.findall(r"whole: \[([^\]]*)\]", self.src) and
                    [k.strip().strip("'") for s in re.findall(r"whole: \[([^\]]*)\]", self.src) for k in s.split(",") if k.strip()])
        self.assertTrue(used)
        for k in used:
            self.assertIn(k, known, k)

    def test_files_are_lf_and_russian_without_addressed_text(self):
        for name in ("parts.js", "models.js", "models_plant.js", "inspect.js"):
            with open(os.path.join(DIO, name), "rb") as fh:
                raw = fh.read()
            self.assertNotIn(b"\r", raw, name)
            low = raw.decode("utf-8").lower()
            for bad in ("жюри", "для судей", "claude", "ии-агент"):
                self.assertNotIn(bad, low, f"{name}: {bad}")

    def test_core_hook_and_module_registered(self):
        core = read(DIO, "core.js")
        self.assertIn("['inspect', 'разбор машин']", core)
        for tok in ("setClickHook", "clickHook(ev)", "rayAt", "pickId: ev => pickId(ev)"):
            self.assertIn(tok, core, tok)

    def test_panel_is_not_permanent(self):
        ins = read(DIO, "inspect.js")
        # карточка создаётся при выборе машины и удаляется при закрытии
        self.assertIn("function ensurePanel", ins)
        self.assertIn("st.panel.remove()", ins)
        self.assertNotIn("ensurePanel();\n  const", ins.split("function open")[0])


@unittest.skipUnless(NODE, "node is not installed")
class NodeTest(unittest.TestCase):
    def test_parts_logic(self):
        o = run_node(PARTS_JS, os.path.join(DIO, "parts.js"), os.path.join(STATIC, "inside.json"))
        self.assertEqual(o["kinds"], ["truck", "exc", "exc", "exc", "sag", "crusher", "conveyor", "", "ball", "ball", "hpgr", "flot", "cyclones",
                                      "thick", "filter", "pump", "", ""])
        self.assertEqual(o["pn"], ["p-grind", "p-hpgr", "p-flot", "p-grind", "p-thick", "p-filter", "p-pumps"])
        self.assertEqual(o["nodes"], ["m-cat793", "m-ex3600", "m-ex1200", "m-ex-other", "p-sag", "p-crusher", "p-conveyor", ""])
        # гидравлика EX01: сигналы загрязнения масла и температуры гидромасла
        self.assertTrue(any("Загрязнение гидромасла" in s for s in o["pumps"]), o["pumps"])
        self.assertTrue(any("Тревога датчика" in s or "Загрязнение" in s for s in o["cylinders"]), o["cylinders"])
        self.assertTrue(any("Натяжение гусениц" in s for s in o["tracks"]), o["tracks"])
        self.assertTrue(any("Тоннаж" in s for s in o["liner"]), o["liner"])
        self.assertTrue(any("ГМД" in s for s in o["motor"]), o["motor"])
        self.assertTrue(any("тормоз" in s.lower() for s in o["brakes"]), o["brakes"])
        self.assertTrue(any("брон" in s.lower() for s in o["mantle"]), o["mantle"])
        self.assertTrue(any("защит" in s.lower() for s in o["drive"]), o["drive"])
        self.assertEqual(o["nosig"], [])

    def test_plant_parts_map_to_sourced_signals_or_say_nothing(self):
        o = run_node(PARTS_JS, os.path.join(DIO, "parts.js"), os.path.join(STATIC, "inside.json"))
        ps = o["ps"]
        has = lambda lst, word: any(word.lower() in x.lower() for x in lst)
        self.assertTrue(has(ps["ballmotor"], "Нагрузка шаровой"), ps["ballmotor"])
        self.assertTrue(has(ps["skew"], "Перекос"), ps["skew"])
        self.assertTrue(has(ps["metal"], "Металлодетектор"), ps["metal"])
        self.assertTrue(has(ps["drv"], "Мощность двух приводов"), ps["drv"])
        self.assertTrue(has(ps["level"], "Уровень ячеек"), ps["level"])
        self.assertTrue(has(ps["rec"], "Извлечение"), ps["rec"])
        self.assertTrue(has(ps["cyc"], "Циркулирующая"), ps["cyc"])
        self.assertTrue(has(ps["dist"], "Давление питания"), ps["dist"])
        self.assertTrue(has(ps["tq"], "Крутящий момент"), ps["tq"])
        self.assertTrue(has(ps["inv"], "Запас"), ps["inv"])
        self.assertTrue(has(ps["plates"], "Прессов"), ps["plates"])
        self.assertTrue(has(ps["cloth"], "Влажность"), ps["cloth"])
        self.assertTrue(has(ps["bear"], "Подшипники"), ps["bear"])
        self.assertTrue(has(ps["gland"], "Подшипники"), ps["gland"])
        # частям без источника сигнал не выдумываем: карточка скажет, что отдельного сигнала нет
        self.assertEqual(ps["none"], [[]] * 6)

    def test_plant_highlights(self):
        h = run_node(PARTS_JS, os.path.join(DIO, "parts.js"), os.path.join(STATIC, "inside.json"))["hp"]
        self.assertEqual(h["rope"], ["issue", "issue", "", ""])
        self.assertEqual(h["skewhl"], ["issue", "issue", "issue", "issue", "issue", "", ""])
        self.assertEqual(h["filt"], ["issue", "issue", "", ""])
        self.assertEqual(h["filtstop"], ["issue", "", "issue"])
        self.assertEqual(h["thick"], ["issue", ""])
        self.assertEqual(h["flot"], ["issue", "", ""])
        self.assertEqual(h["whole"], [True, True, True, False])
        self.assertEqual(h["tg"], ["Разрез", "Собрать", "Разрез"])

    def test_node_to_data_mapping_keeps_feature_names(self):
        D = json.loads(read(STATIC, "inside.json"))
        nd = next(n for g in D["groups"] for n in g["nodes"] if n["id"] == "m-ex3600")
        feats = {s.get("feature") for s in nd["signals"]}
        self.assertTrue({"oil_pct", "oil_alert"} <= feats)
        sg = next(n for g in D["groups"] for n in g["nodes"] if n["id"] == "p-sag")
        self.assertIn("liner_ground_t", {s.get("feature") for s in sg["signals"]})

    def test_highlight_logic(self):
        o = run_node(PARTS_JS, os.path.join(DIO, "parts.js"), os.path.join(STATIC, "inside.json"))
        self.assertEqual(o["hl_oil"], ["issue", "issue", "", ""])
        self.assertEqual(o["hl_none"], ["", ""])
        self.assertEqual(o["hl_liner_issue"], "issue")
        self.assertEqual(o["hl_liner_days"], "warn")
        self.assertEqual(o["hl_liner_share"], "warn")
        self.assertEqual(o["hl_liner_far"], "")
        self.assertEqual(o["hl_liner_other"], "")
        self.assertEqual(o["hl_fatigue"], ["issue", ""])
        self.assertEqual(o["whole"], [True, False, True])
        self.assertEqual(o["ev"], ["на машине", "передаётся, если подключена опция", "аналог другой модели"])
        self.assertEqual(o["toggles"], ["Разобрать", "Собрать", "Разрез", "Убрать разрез"])
        self.assertEqual(o["off"], [0, 0, 5.5])
        self.assertEqual(o["near"], [False, True, False])

    def test_models_build_and_stay_small(self):
        o = run_node(MODELS_JS, os.path.join(DIO, "models.js"), os.path.join(DIO, "parts.js"))
        self.assertEqual(set(o), {"truck", "exc", "sag", "crusher", "conveyor", "ball", "hpgr", "flot", "cyclones", "thick", "filter", "pump"})
        for kind, r in o.items():
            self.assertEqual(r["missing"], [], kind)
            self.assertEqual(r["extra"], [], kind)
            self.assertEqual(r["bad"], 0, kind)
            self.assertGreater(r["tris"], 150, kind)
            self.assertLess(r["tris"], 9000, kind)   # бюджет: одна модель не больше ≈ 10 % сцены (≈ 80 тыс.)
        for kind in ("ball", "hpgr", "flot", "cyclones", "thick", "filter", "pump"):
            self.assertLess(o[kind]["tris"], 3500, kind)   # бюджет аппаратов фабрики: ≈ 3,5 тыс. треугольников на модель
        self.assertLess(sum(r["tris"] for r in o.values()), 45000)

    def test_modules_parse(self):
        for name in ("parts.js", "models.js", "models_plant.js", "inspect.js", "core.js"):
            src = read(DIO, name)
            r = subprocess.run([NODE, "--input-type=module", "--check"], input=src, capture_output=True, encoding="utf-8", timeout=60)
            self.assertEqual(r.returncode, 0, f"{name}: {r.stderr}")


if __name__ == "__main__":
    unittest.main()
