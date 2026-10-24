"""Block of 24.10.2026 (consistency pass): the pages «Экономика» / «Калибровка» / «Спросить двойник» read the result of the
experiment of 24.10.2026 (exp23.json, built from sim/data/experiment_23.json), the old headline +1,26 stays only as history,
the «3D» switch above the map and the WebGL notice, one number of twin types in the documents, the menu in README."""
import json
import os
import re
import shutil
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "web", "static")
DOCS = os.path.dirname(ROOT)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sim import exp23_view  # noqa: E402

WEBGL_NOTE = ("3D требует WebGL (видеокарта или Chrome с флагом --enable-unsafe-swiftshader); "
              "все данные и последствия сценариев показаны на 2D-плане")

NODE_RENDER = r"""global.window={};global.document={};const fs=require('fs');
global.AKT={esc:s=>String(s),fmt:(v,d=0)=>(v==null||!isFinite(v))?'-':new Intl.NumberFormat('ru-RU',{minimumFractionDigits:d,maximumFractionDigits:d}).format(v),money:v=>'$'+Math.round(v)};
global.fetch=()=>Promise.resolve({json:()=>Promise.resolve({})});
const dir=process.argv[1];
eval(fs.readFileSync(dir+'/exp23.js','utf8'));
AKT.exp23.data=JSON.parse(fs.readFileSync(dir+'/exp23.json','utf8'));
console.log(JSON.stringify({s:AKT.exp23.sentence(),t:AKT.exp23.tornado(),m:AKT.exp23.mainTable(),d:AKT.exp23.delay(),tw:AKT.exp23.twin(),
  n:AKT.exp23.novice(),w:AKT.exp23.worse(),c:AKT.exp23.co2(),h:AKT.exp23.delayFor('crusher_stop'),h0:AKT.exp23.delayFor('hard_ore'),hx:AKT.exp23.delayFor('water_short'),
  hs:AKT.exp23.delayFor('roping')}));"""


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


class Exp23DataTest(unittest.TestCase):
    def setUp(self):
        self.d = json.loads(read(STATIC, "exp23.json"))

    def test_file_is_built_from_the_experiment_summary(self):
        self.assertEqual(read(STATIC, "exp23.json"), exp23_view.json_text())

    def test_headline_numbers(self):
        m = self.d["main"]
        self.assertAlmostEqual(m["cu"]["mean"], 1.07, delta=0.005)
        self.assertAlmostEqual(m["cu"]["ci95"][0], 0.89, delta=0.005)
        self.assertAlmostEqual(m["cu"]["ci95"][1], 1.31, delta=0.005)
        self.assertAlmostEqual(m["usd"]["mean"], 14900, delta=60)
        self.assertAlmostEqual(m["down_min"]["mean"], -12.0, delta=0.05)
        self.assertAlmostEqual(m["kwh_per_t_cu"]["mean"], -33.0, delta=0.6)
        self.assertAlmostEqual(m["share_worse"], 0.03, delta=0.001)
        self.assertEqual(self.d["replication"]["seeds"], [2001, 2100])
        self.assertAlmostEqual(self.d["replication"]["cu"]["mean"], 1.01, delta=0.005)

    def test_delay_detection_lab_tornado(self):
        dl = self.d["delay"]
        self.assertAlmostEqual(dl["slope_t_per_h"]["mean"], 5.36, delta=0.005)
        self.assertAlmostEqual(dl["slope_usd_per_h"]["mean"], 74000, delta=1000)
        kinds = {k["kind"]: k["mean"] for k in dl["by_kind_t_per_h"]}
        self.assertAlmostEqual(kinds["trip"], 9.7, delta=0.05)
        self.assertAlmostEqual(kinds["crusher"], 7.7, delta=0.05)
        self.assertAlmostEqual(kinds["grid"], 2.0, delta=0.05)
        self.assertAlmostEqual(kinds["dose"], 0.26, delta=0.005)
        do = self.d["detect_vs_order"]
        self.assertAlmostEqual(do["1"]["order"]["mean"], 0.23, delta=0.005)
        self.assertAlmostEqual(do["2"]["order"]["mean"], 0.06, delta=0.005)
        self.assertGreater(do["2"]["detection"]["mean"], 0.95)
        lab = {x["h"]: x["mean"] for x in self.d["lab"]["levels"]}
        self.assertAlmostEqual(lab[12], lab[24], delta=0.005)          # plateau after 12 h
        tor = {t["label"]: t["mean"] for t in self.d["tornado"]}
        self.assertAlmostEqual(tor["доля выполненных советов 50 %"], 0.76, delta=0.005)
        self.assertAlmostEqual(tor["время находки тихой беды 150 мин (было 75)"], 0.97, delta=0.005)
        base = self.d["tornado"][0]["mean"]
        self.assertAlmostEqual(tor["ошибка оценки модуля ×2 (σ 0,4 вместо 0,2)"], base, delta=0.005)

    def test_novice_from_data_is_reported_as_it_came_out(self):
        """VALIDATION 8.9 (pre-registered) and 8.10: the numbers on the pages are those of the run, null results included."""
        n = self.d["novice"]
        self.assertTrue(n["differs"])
        self.assertAlmostEqual(n["v1_expert_minus_novice_cu"]["mean"], 0.0, delta=0.005)          # the «one at a time» novice of 8.8 stays at zero
        lo, hi = n["v1_expert_minus_novice_cu"]["ci95"]
        self.assertTrue(lo < 0 < hi)
        d = n["data"]
        self.assertEqual((d["n"], d["seeds"]), (100, [1001, 1100]))
        p = d["pairs"]
        self.assertAlmostEqual(p["expert-nov_r"]["cu"]["mean"], 1.08, delta=0.005)
        self.assertAlmostEqual(p["expert-nov_r"]["cu"]["ci95"][0], 0.80, delta=0.005)
        self.assertAlmostEqual(p["expert-nov_r"]["cu"]["ci95"][1], 1.54, delta=0.005)
        self.assertAlmostEqual(p["twin-expert"]["cu"]["mean"], self.d["main"]["cu"]["mean"], delta=1e-3)   # code control: 8.8 is reproduced (rounded in the file)
        self.assertGreater(p["nov_twin-expert"]["cu"]["ci95"][0], 0.05)                                   # a novice with the twin beats the expert without it
        self.assertAlmostEqual(p["nov_twin-nov_r"]["cu"]["mean"], 2.08, delta=0.005)
        self.assertTrue(all(d["expectations"].values()))
        rg = d["ranges"]
        self.assertFalse(rg["lo"]["pairs"]["expert-nov_r"]["effect"])                                     # at the low end of every row there is no effect
        self.assertTrue(rg["lo"]["pairs"]["expert-nov_r"]["cu"]["ci95"][0] < 0.05)
        self.assertAlmostEqual(rg["hi"]["pairs"]["expert-nov_r"]["cu"]["mean"], 3.5, delta=0.05)
        self.assertAlmostEqual(rg["rep"]["pairs"]["expert-nov_r"]["cu"]["mean"], 0.46, delta=0.005)
        self.assertEqual(rg["rep"]["seeds"], [2001, 2100])
        self.assertAlmostEqual(d["parts"]["seeing"]["mean"] + d["parts"]["slips"]["mean"], p["expert-nov_r"]["cu"]["mean"], delta=0.05)
        for name in ("pages.js", "exp23.js", "views.js", "help.js"):
            self.assertNotRegex(read(STATIC, name), r"Новичок и опытный в модели не различаются")

    def test_shifts_where_the_twin_is_worse_are_explained(self):
        w = self.d["worse"]
        m = w["main_full"]
        self.assertEqual((m["n"], m["n_worse"]), (100, 3))
        self.assertEqual([r["seed"] for r in m["rows"]], [1078, 1067, 1005])
        for r in m["rows"]:
            self.assertIn("roping", r["kinds"])                       # the 20 minutes between 55 (people) and 75 (twin) minutes
            self.assertGreater(r["d_cu"], -0.15)
        self.assertEqual(w["rep_full"]["rows"][0]["seed"], 2079)
        self.assertLess(w["rep_full"]["rows"][0]["d_cu"], -17.0)
        self.assertTrue(w["rep_full"]["rows"][0]["shared_crew"])
        self.assertEqual(w["rep_full"]["n_worse"], 5)

    def test_every_issue_kind_with_a_price_of_the_hour_exists_in_the_module(self):
        from modules import priority
        dl = self.d["delay"]
        for issue_kind, exp_kind in dl["issue_kinds"].items():
            self.assertIn(issue_kind, priority.WHO, issue_kind)
            self.assertIn(exp_kind, dl["by_kind"], exp_kind)
        self.assertGreater(dl["by_kind"]["trip"]["t_per_h"], dl["by_kind"]["crusher"]["t_per_h"])
        self.assertTrue(dl["by_kind"]["hard"]["below_threshold"])
        self.assertAlmostEqual(dl["by_kind"]["crusher"]["usd_per_h"], 7.73 * 14539 * 0.955, delta=200)
        for k in ("roping", "phdrift", "hpgr", "mantle"):                 # tier S kinds have their price of the hour as well
            self.assertGreaterEqual(dl["by_kind"][k]["n"], 3)

    def test_energy_and_co2(self):
        e = self.d["energy"]
        from sim.params import default
        self.assertAlmostEqual(e["co2_t_per_mwh"], default()["econ_co2_t_mwh"], places=2)
        self.assertAlmostEqual(e["co2_t_per_mwh"], 2308e3 / (13.06e9 / 3.6e3), places=2)             # group Scope 2 / group electricity
        self.assertAlmostEqual(e["d_kwh_per_t_cu"]["mean"], -33.5, delta=0.1)
        self.assertAlmostEqual(e["d_co2_kg_per_t_cu"]["mean"], e["d_kwh_per_t_cu"]["mean"] * e["co2_t_per_mwh"], delta=0.1)
        self.assertGreater(e["d_mwh"]["mean"], 0.0)                      # the twin shift burns a little more energy, for more copper
        self.assertLess(e["d_co2_t_shift_same_output"]["mean"], -5.0)
        self.assertAlmostEqual(e["co2_t_per_t_cu"]["by_value"], 6.3, delta=0.05)

    def test_alarm_flood_is_below_the_isa_orientation(self):
        a = self.d["alarms"]
        self.assertEqual(a["n"], 100)
        self.assertEqual(a["isa_per_shift"], 75.0)
        self.assertLess(a["no_twin"]["events_mean"], a["isa_per_shift"] / 3)
        self.assertGreater(a["no_twin"]["events_per_trouble"], 2.0)       # one cause drags a chain of nodes
        self.assertAlmostEqual(a["no_twin"]["events_mean"], a["by_value"]["events_mean"], delta=1.0)
        self.assertIn("не воспроизводим", read(STATIC, "pages.js"))


class PageWiringTest(unittest.TestCase):
    def test_script_order_and_loading(self):
        srcs = re.findall(r'<script src="/([^"]+)"', read(STATIC, "index.html"))
        self.assertIn("exp23.js", srcs)
        self.assertLess(srcs.index("exp23.js"), srcs.index("views.js"))
        self.assertLess(srcs.index("exp23.js"), srcs.index("pages.js"))

    def test_economics_and_calibration_read_exp23(self):
        pages, views, helpjs = read(STATIC, "pages.js"), read(STATIC, "views.js"), read(STATIC, "help.js")
        self.assertIn("AKT.exp23.load(", pages)
        self.assertIn("X.tornado()", pages)
        self.assertNotIn("trialOf", pages)
        self.assertIn("AKT.exp23.load(", views)
        self.assertIn("AKT.exp23.tornado()", views)
        self.assertIn("AKT.exp23.sentence()", views)
        self.assertIn("AKT.exp23", helpjs)
        self.assertIn("fetch('/exp23.json'", read(STATIC, "exp23.js"))
        self.assertNotIn("twin_cu_t_2000", helpjs)

    def test_old_headline_only_as_history(self):
        for name in ("pages.js", "views.js", "help.js", "exp23.js", "app.js", "replay.js"):
            for i, line in enumerate(read(STATIC, name).splitlines(), 1):
                if re.search(r"1[.,]26", line):
                    self.assertRegex(line, r"22\.10|историч|Прежн", f"{name}:{i}")
        for name in ("README.md", "SUBMISSION.md"):
            t = read(DOCS, name)
            self.assertIn("+1,07", t, name)
            self.assertIn("+0,89; +1,31", t, name)

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_rendering_with_node(self):
        r = subprocess.run(["node", "-e", NODE_RENDER, STATIC], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        o = json.loads(r.stdout)
        self.assertIn("+1,07", o["s"])
        self.assertIn("[+0,89; +1,31]", o["s"])
        self.assertIn("<svg", o["t"])
        self.assertEqual(o["t"].count("<circle"), len(json.loads(read(STATIC, "exp23.json"))["tornado"]))
        self.assertIn("5,36", o["d"])
        self.assertIn("+1,01 [+0,41; +1,45]", o["m"])
        self.assertAlmostEqual(o["tw"]["mean"], 1.07, delta=0.005)
        self.assertIn("опытный − новичок по данным", o["m"])
        self.assertIn("+1,08 [+0,80; +1,54]", o["m"])
        self.assertIn("новичок с двойником", o["n"])
        self.assertIn("выше опытного без двойника", o["n"])
        self.assertIn("эффект не найден", o["n"])                          # the low end of the rows: no effect
        self.assertIn("канатирование", o["w"])
        self.assertIn("2079", o["w"])
        self.assertIn("21 кг CO₂", o["c"])
        self.assertIn("7,8 т CO₂-экв.", o["c"])
        self.assertIn("7,73 т Cu", o["h"])
        self.assertIn("поломка дробилки", o["h"])
        self.assertIn("эффекта нет", o["h0"])
        self.assertIn("в опыте не считалась", o["hx"])
        self.assertIn("канатирование циклонов", o["hs"])

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_js_syntax(self):
        for name in ("exp23.js", "plan.js", "site.js", "pages.js", "views.js", "help.js", "replay.js"):
            r = subprocess.run(["node", "--check", os.path.join(STATIC, name)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, name + r.stderr)


class Toggle3dTest(unittest.TestCase):
    def test_3d_switch_sits_with_scheme_and_satellite(self):
        plan = read(STATIC, "plan.js")
        m = re.search(r'<span class="grp" role="group" aria-label="Подложка">(.*?)</span>', plan)
        self.assertIsNotNone(m)
        self.assertEqual(re.findall(r'id="(lay-[a-z0-9]+)"', m.group(1)), ["lay-scheme", "lay-sat", "lay-3d"])
        self.assertRegex(m.group(1), r'id="lay-3d"[^>]*>3D</button>')
        i = plan.index("#lay-3d")
        self.assertIn("'?view=diorama'", plan[i:i + 220])

    def test_webgl_notice_text_and_readme(self):
        site = read(STATIC, "site.js")
        self.assertIn(WEBGL_NOTE, site)
        self.assertEqual(site.count("none: WEBGL_NOTE"), 2)
        self.assertNotIn("В этом браузере нет WebGL", site)
        readme = read(DOCS, "README.md")
        req = readme[readme.index("### Требования"):readme.index("### Запуск")]
        self.assertIn("WebGL", req)
        self.assertIn("--enable-unsafe-swiftshader", req)
        self.assertNotIn("Видеокарта не нужна.", req)
        for bad in (r"жюри", r"судь[яеи]", r"для\s+ИИ"):
            self.assertIsNone(re.search(bad, req + site, re.I))


class DocsConsistencyTest(unittest.TestCase):
    def test_one_number_of_types(self):
        n = len(json.loads(read(ROOT, "setup", "things.json"))["types"])
        self.assertEqual(n, 45)
        for name in ("README.md", "SUBMISSION.md"):
            t = read(DOCS, name)
            for m in re.finditer(r"\b(\d+)\s+тип(?:а|ов)\b", t):
                self.assertEqual(int(m.group(1)), n, f"{name}: {m.group(0)}")
        self.assertIn("45 типов", read(DOCS, "README.md"))

    def test_readme_describes_the_live_menu(self):
        readme = read(DOCS, "README.md")
        m = re.search(r"const MENU4 = \[(.*?)\n\];", read(STATIC, "app.js"), re.S)
        groups = re.findall(r"\['(?:now|shift|analysis|learn)', '([^']+)'", m.group(1))
        self.assertEqual(groups, ["Сейчас", "Смена", "Анализ", "Обучение и справка"])
        for g in groups:
            self.assertIn(g, readme)
        for item in re.findall(r"\['[a-z0-9]+', '([^']+)'\]", m.group(1)):
            self.assertIn(item, readme, item)
        self.assertNotIn("Меню: План · Диорама", readme)


if __name__ == "__main__":
    unittest.main()
