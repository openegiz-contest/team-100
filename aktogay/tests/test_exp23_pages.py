"""Block of 24.10.2026 (consistency pass): the pages «Экономика» / «Калибровка» / «Спросить двойник» read the result of the
experiment of 24.10.2026 on the symmetric people / twin base (exp23.json, built from sim/data/experiment_24.json and experiment_23.json),
the old headlines +1,26 (22.10) and +1,07 (8.8, asymmetric base) stay only as history,
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
DOCS = os.path.join(os.path.dirname(ROOT), "final_docs")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sim import exp23_view  # noqa: E402

WEBGL_NOTE = '3D не запустился: браузер не дал создать контекст WebGL. Чтобы увидеть 3D: включите аппаратное ускорение в настройках браузера (Chrome: Настройки → Система) и обновите страницу; на компьютере без видеокарты запустите Chrome с флагом --enable-unsafe-swiftshader. Все данные и последствия сценариев показаны на 2D-плане.'

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
        """The headline is R1 of VALIDATION 8.17 (symmetric base); the base of 8.8 is kept next to it as history."""
        m = self.d["main"]
        self.assertAlmostEqual(m["cu"]["mean"], 0.61, delta=0.005)
        self.assertAlmostEqual(m["cu"]["ci95"][0], 0.23, delta=0.005)
        self.assertAlmostEqual(m["cu"]["ci95"][1], 2.18, delta=0.005)
        self.assertAlmostEqual(m["median"], 0.09, delta=0.005)
        self.assertAlmostEqual(m["without_top"]["mean"], 0.26, delta=0.005)
        self.assertEqual(m["top_seed"], 1066)
        self.assertAlmostEqual(m["top_d_cu"], 35.35, delta=0.01)
        self.assertAlmostEqual(m["usd"]["mean"], 8387, delta=60)
        self.assertAlmostEqual(m["down_min"]["mean"], -6.2, delta=0.05)
        self.assertAlmostEqual(m["kwh_per_t_cu"]["mean"], -28.4, delta=0.1)
        self.assertAlmostEqual(m["share_worse"], 0.01, delta=0.001)
        self.assertEqual(self.d["replication"]["seeds"], [2001, 2100])
        self.assertAlmostEqual(self.d["replication"]["cu"]["mean"], 0.31, delta=0.005)
        a = self.d["history"]["asym_8_8"]                                       # the base of 8.8 stays as history
        self.assertAlmostEqual(a["main"]["cu"]["mean"], 1.07, delta=0.005)
        self.assertAlmostEqual(a["main"]["cu"]["ci95"][0], 0.89, delta=0.005)
        self.assertAlmostEqual(a["replication"]["cu"]["mean"], 1.01, delta=0.005)
        self.assertAlmostEqual(a["control_on_the_merged_code"]["cu"]["mean"], 1.09, delta=0.01)
        s = self.d["sym"]                                                       # both edges of the hard-ore assumption, both readings of the stockpile
        self.assertAlmostEqual(s["sag"]["R3"]["cu"]["mean"], 1.19, delta=0.005)
        self.assertAlmostEqual(s["sag"]["R4"]["cu"]["mean"], 0.81, delta=0.005)
        self.assertAlmostEqual(s["stock_b"]["R6"]["cu"]["mean"], 0.59, delta=0.005)
        self.assertAlmostEqual(s["stock_b"]["R7"]["cu"]["mean"], 1.06, delta=0.005)
        self.assertEqual(set(s["ladder"]), {"S1_s1001", "S3_s1001", "S5_s1001", "S1_s2001", "S3_s2001"})
        self.assertAlmostEqual(s["ladder"]["S5_s1001"]["cu"]["mean"], m["cu"]["mean"], delta=1e-3)       # S5 is R1 shift for shift

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
        self.assertAlmostEqual(p["expert-nov_r"]["cu"]["mean"], 1.09, delta=0.005)
        self.assertAlmostEqual(p["expert-nov_r"]["cu"]["ci95"][0], 0.80, delta=0.005)
        self.assertAlmostEqual(p["expert-nov_r"]["cu"]["ci95"][1], 1.57, delta=0.005)
        self.assertAlmostEqual(p["twin-expert"]["cu"]["mean"], self.d["main"]["cu"]["mean"], delta=1e-3)   # code control: the headline is reproduced
        self.assertEqual(p["twin-expert"]["cu"]["ci95"], self.d["main"]["cu"]["ci95"])                    # one interval for one quantity on the pages
        self.assertGreater(p["nov_twin-expert"]["cu"]["ci95"][0], 0.05)                                   # a novice with the twin still beats the expert without it
        self.assertAlmostEqual(p["nov_twin-expert"]["cu"]["mean"], 0.53, delta=0.005)                    # ... by half a tonne, not by a tonne
        self.assertAlmostEqual(p["nov_twin-nov_r"]["cu"]["mean"], 1.62, delta=0.005)
        self.assertTrue(all(v for v in d["expectations"].values() if v is not None))
        rg = d["ranges"]
        self.assertFalse(rg["lo"]["pairs"]["expert-nov_r"]["effect"])                                     # at the low end of every row there is no effect
        self.assertTrue(rg["lo"]["pairs"]["expert-nov_r"]["cu"]["ci95"][0] < 0.05)
        self.assertAlmostEqual(rg["hi"]["pairs"]["expert-nov_r"]["cu"]["mean"], 3.5, delta=0.05)
        self.assertLess(rg["hi"]["pairs"]["nov_twin-expert"]["cu"]["ci95"][0], 0.0)                       # at the upper edge the novice with the twin is not above the expert
        self.assertGreater(rg["hi"]["pairs"]["nov_twin-expert"]["share_worse"], 0.15)
        self.assertAlmostEqual(rg["rep"]["pairs"]["expert-nov_r"]["cu"]["mean"], 0.46, delta=0.005)
        self.assertEqual(rg["rep"]["seeds"], [2001, 2100])
        self.assertAlmostEqual(d["parts"]["seeing"]["mean"] + d["parts"]["slips"]["mean"], p["expert-nov_r"]["cu"]["mean"], delta=0.05)
        for name in ("pages.js", "exp23.js", "views.js", "help.js"):
            self.assertNotRegex(read(STATIC, name), r"Новичок и опытный в модели не различаются")

    def test_shifts_where_the_twin_is_worse_are_explained(self):
        """On the symmetric base the twin is never later than the people, so it is worse than «as now» almost never; it is not a proof of use."""
        w = self.d["worse"]
        m = w["main_full"]
        self.assertEqual((m["n"], m["n_worse"]), (100, 1))
        self.assertEqual([r["seed"] for r in m["rows"]], [1009])
        self.assertGreater(m["rows"][0]["d_cu"], -0.15)
        self.assertEqual((w["rep_full"]["n"], w["rep_full"]["n_worse"]), (100, 0))
        self.assertEqual(w["rep_full"]["rows"], [])

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
        self.assertAlmostEqual(e["d_kwh_per_t_cu"]["mean"], -28.4, delta=0.1)
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
        for name in ("README_aktogay.md", "SUBMISSION.md"):
            t = read(DOCS, name)
            if name == "SUBMISSION.md":                     # the «Concept» section is the participant's text and is checked by check_numbers.py (reported, not edited)
                t = t[:t.index("## Concept")] + t[t.index("## Почему это важно"):]
            self.assertIn("+1,07", t, name)                 # the base of 8.8 stays as history ...
            self.assertIn("+0,89; +1,31", t, name)
            self.assertIn("+0,61", t, name)                 # ... next to the headline of the symmetric base
            self.assertIn("+0,23; +2,18", t, name)
            for i, line in enumerate(t.splitlines(), 1):
                if "+1,07" in line:
                    self.assertRegex(line, r"22\.10|историч|Прежн|прежн|8\.8|none|база|баз", f"{name}:{i}")

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_rendering_with_node(self):
        r = subprocess.run(["node", "-e", NODE_RENDER, STATIC], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        o = json.loads(r.stdout)
        self.assertIn("+0,61 т Cu за смену против «как сейчас»", o["s"])
        self.assertIn("[+0,23; +2,18]", o["s"])
        self.assertIn("медиана +0,09", o["s"])
        self.assertIn("только на SAG — +1,19 [+0,77; +2,81] и +0,81 [+0,58; +1,14]", o["s"])
        self.assertIn("163 кт", o["s"])                                               # both readings of the stockpile are on the page
        self.assertIn("добавка", o["s"])
        self.assertIn("<svg", o["t"])
        self.assertEqual(o["t"].count("<circle"), len(json.loads(read(STATIC, "exp23.json"))["tornado"]))
        self.assertIn("5,36", o["d"])
        self.assertIn("+0,31 [+0,21; +0,47]", o["m"])
        self.assertIn("прежняя база 8.8", o["m"])
        self.assertIn("+1,09 [+0,90; +1,33]", o["m"])                                  # the control run of the base of 8.8 on the merged code
        self.assertAlmostEqual(o["tw"]["mean"], 0.61, delta=0.005)
        self.assertIn("опытный − новичок по данным", o["m"])
        self.assertIn("+1,09 [+0,80; +1,57]", o["m"])
        self.assertIn("новичок с двойником", o["n"])
        self.assertIn("выше опытного без двойника", o["n"])
        self.assertIn("эффект не найден", o["n"])                          # the low end of the rows: no effect
        self.assertIn("1009", o["w"])
        self.assertIn("не доказательство пользы", o["w"])
        self.assertIn("18 кг CO₂", o["c"])
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
        readme = read(DOCS, "README_aktogay.md")
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
        for name in ("README_aktogay.md", "SUBMISSION.md"):
            t = read(DOCS, name)
            for m in re.finditer(r"\b(\d+)\s+тип(?:а|ов)\b", t):
                self.assertEqual(int(m.group(1)), n, f"{name}: {m.group(0)}")
        self.assertIn("45 типов", read(DOCS, "README_aktogay.md"))

    def test_readme_describes_the_live_menu(self):
        readme = read(DOCS, "README_aktogay.md")
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
