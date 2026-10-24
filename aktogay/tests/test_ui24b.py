"""Interface of 24.10 (second block, static checks, no browser): live effect of the twin, page «Модули», text fixes,
robust WebGL start, README table by the sections of the solution."""
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


def read(*p):
    with open(os.path.join(*p), encoding="utf-8") as f:
        return f.read()


class EffectCounterTest(unittest.TestCase):
    def test_counter_reads_the_copies_from_baseline(self):
        app = read(STATIC, "app.js")
        self.assertIn("AKT.effect = ", app)
        body = app[app.index("AKT.effect = "):app.index("AKT.staleSec = ")]
        for w in ("AKT.shiftResult()", "no_twin", "c.fact.cu_t - c.no_twin.cu_t", "С двойником сейчас", "против копии без двойника",
                  "против копии без сценария"):
            self.assertIn(w, body, w)
        self.assertIn("now-eff", app)

    def test_counter_sits_in_the_context_line(self):
        idx = read(STATIC, "index.html")
        self.assertRegex(idx, r'<span id="now-chip"></span><span id="now-eff"></span>')


class ModulesPageTest(unittest.TestCase):
    def test_menu_and_registration(self):
        app = read(STATIC, "app.js")
        self.assertIn("['modules', 'Модули']", app)
        self.assertRegex(read(STATIC, "modview.js"), r"AKT\.views\.modules\s*=")
        self.assertIn('<script src="/modview.js"></script>', read(STATIC, "index.html"))

    def test_every_module_card_has_the_rubric_fields(self):
        js = read(STATIC, "modview.js")
        for w in ("Что читает", "Какое решение формирует", "Что меняет в работе рудника", "Последнее решение",
                  "Эффект модуля в один клик", "Применить совет", "mod-losses", "mod-ore", "mod-priority", "AKT.moduleLag",
                  "processed_sim_time", "?view=economics", "?view=replay", "AKT.panel.scenario('fork'"):
            self.assertIn(w, js, w)

    def test_page_reads_only_the_twin(self):
        js = read(STATIC, "modview.js")
        self.assertNotRegex(js, r"fetch\(|/api/(scenario|speed|reset)")
        for w in ("жюри", "судья", "Судья", "Жюри"):
            self.assertNotIn(w, js)


class TextFixesTest(unittest.TestCase):
    def test_duration_rounds_before_splitting(self):
        app = read(STATIC, "app.js")
        self.assertIn("const tot = Math.round(min), h = Math.floor(tot / 60), m = tot % 60;", app)
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        m = re.search(r"AKT\.dur = min => \{.*?\n\};", app, re.S).group(0)
        code = "const NBSP='\u00a0';const AKT={};" + m + "console.log([AKT.dur(119.6),AKT.dur(59.7),AKT.dur(120),AKT.dur(90)].join('|'))"
        out = subprocess.run([node, "-e", code], capture_output=True, text=True, encoding="utf-8").stdout.strip()
        self.assertEqual(out.replace(" ", " "), "2 ч 00 мин|1 ч 00 мин|2 ч 00 мин|1 ч 30 мин")

    def test_stock_hours_do_not_lag_a_stop_of_the_crusher(self):
        app = read(STATIC, "app.js")
        self.assertIn("AKT.hoursLeft = sp =>", app)
        self.assertIn("lvl / out + 0.5", app)
        for name in ("plan.js", "line.js", "help.js"):
            self.assertNotIn("'hours_left')", read(STATIC, name).replace("AKT.num(`stockpile-${n}`, 'hours_left') ", ""), name)

    def test_first_minutes_headline_names_whom_to_call(self):
        app = read(STATIC, "app.js")
        self.assertIn("Звать ${AKT.roleAcc(rl)} — цена уточняется", app)
        self.assertNotIn("Двойник оценит их за несколько минут", app)

    def test_one_name_of_the_crusher(self):
        for name in ("plan.js", "site3d.js", "diorama/mining.js"):
            t = read(STATIC, *name.split("/"))
            self.assertNotRegex(t, r"Дробилка [12](?![0-9])", name)
        self.assertIn("return `Дробилка ЦПД-${p.n} · ", read(STATIC, "diorama", "mining.js"))

    def test_panel_and_queue_page_use_one_journal(self):
        app, views = read(STATIC, "app.js"), read(STATIC, "views.js")
        self.assertIn("AKT.shiftJournal = ", app)
        self.assertIn("AKT.shiftJournal().slice(0, 3)", app)
        self.assertIn("AKT.shiftJournal()", views)

    def test_energy_row_explains_annual_against_instant(self):
        views = read(STATIC, "views.js")
        self.assertIn("мгновенное значение, не годовое", views)
        self.assertIn("instKwh", views)

    def test_idle_people_have_no_text_on_the_map(self):
        plan = read(STATIC, "plan.js")
        self.assertIn("const idle = !hl && !info.tr", plan)


class WebGlStartTest(unittest.TestCase):
    def test_one_robust_context_maker(self):
        site = read(STATIC, "site.js")
        for w in ("failIfMajorPerformanceCaveat: false", "async acquire(", "async available(", "attempt < 3", "--enable-unsafe-swiftshader",
                  "Чтобы получить 3D"):
            self.assertIn(w, site, w)

    def test_scenes_take_the_prepared_context(self):
        for name in ("diorama/core.js", "site3d.js"):
            t = read(STATIC, *name.split("/"))
            self.assertIn("await AKT.gl.acquire(", t, name)
            self.assertIn("context: glCtx", t, name)
            self.assertNotIn("pc.getContext(", t, name)             # no private probe context any more


class ReadmeTableTest(unittest.TestCase):
    def test_first_screen_is_the_five_minute_check(self):
        r = read(DOCS, "README_aktogay.md")
        heads = re.findall(r"^#+ .*$", r, re.M)
        self.assertEqual(heads[1], "### Как проверить за 5 минут")
        self.assertIn("python3 -I -m unittest", r)
        self.assertNotRegex(r, r"`python -I -m unittest")

    def test_table_by_sections_of_the_solution(self):
        r = read(DOCS, "README_aktogay.md")
        t = r[r.index("### Разделы решения: где смотреть и что видно"):]
        t = t[:t.index("\n### ", 10)]
        self.assertIn("| Раздел решения | Где посмотреть | Что видно |", t)
        for row in ("Модель рудника", "Визуализация", "Достоверность поведения", "Замысел", "Сценарии «что если»", "Модули"):
            self.assertIn("| " + row + " |", t, row)
        for w in ("жюри", "судья", "Судья", "Жюри", "ИИ"):
            self.assertNotIn(w, t)


if __name__ == "__main__":
    unittest.main()
