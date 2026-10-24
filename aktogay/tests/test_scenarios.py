"""Block of 23.10.2026 (scenarios, replay, mechanic screen, price of a trouble, handover button, labels of parameters, module
documentation, light diorama): catalog of scenarios and the constructor of a trouble (token kind[:N][@start][=magnitude]),
the shift with three troubles, replay with the twin and without, the status of the called person, the breakdown of a price,
the button «Сдать смену», the summary of the parameter labels, API.md and the live module table."""
import json
import os
import re
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
WEB = os.path.join(ROOT, "web")
if WEB not in sys.path:
    sys.path.insert(0, WEB)
STATIC = os.path.join(WEB, "static")
FINAL = os.path.dirname(ROOT)

from tests import mod_support as ms  # noqa: E402
from tests.test_mod_priority import T0, fork_ov, fork_store, modules, run_fork  # noqa: E402
from modules import apidoc, priority, readiness, scenarios  # noqa: E402
from modules.params import PARAMS as MPARAMS  # noqa: E402
from modules.policy import Ranked  # noqa: E402
from modules.store import Store  # noqa: E402
from sim import events as ev  # noqa: E402
from sim import paramstat, replay, trial  # noqa: E402
from sim.params import TABLE, default  # noqa: E402
from sim.plant import CopySet  # noqa: E402

import server  # noqa: E402


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


def step(cs, n):
    for _ in range(n):
        cs.step()


# ------------------------------------------------------------------------------------------------ catalog
class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(read(STATIC, "scenarios.json"))

    def test_json_is_written_from_the_module(self):
        self.assertEqual(read(STATIC, "scenarios.json"), scenarios.json_text())

    def test_every_scenario_parses_and_has_its_texts(self):
        prm = default()
        for s in self.data["scenarios"]:
            spec = ev.parse_scenario(s["id"], 480.0, prm)
            self.assertTrue(spec.events or spec.preset, s["id"])
            for k in ("what", "first", "who", "closure", "test"):
                self.assertTrue(str(s[k]).strip(), f"{s['id']}.{k}")
            self.assertGreaterEqual(len(s["steps"]), 2, s["id"])
            self.assertEqual(s["seed"], 42)
            self.assertNotIn("WHO:", json.dumps(s, ensure_ascii=False))

    def test_the_tests_named_exist(self):
        for s in self.data["scenarios"]:
            path, _, name = s["test"].partition("::")
            full = os.path.join(ROOT, path.replace("tests/", "tests" + os.sep, 1))
            self.assertTrue(os.path.isfile(full), s["test"])
            src = read(full)
            for part in name.split("::"):
                self.assertIn(part, src, s["test"])

    def test_every_button_of_the_model_console_is_in_the_catalog(self):
        app = read(STATIC, "app.js")
        block = app[app.index("AKT.SCENARIOS = ["):app.index("];", app.index("AKT.SCENARIOS = ["))]
        ids = set(re.findall(r"\{ id: '([^']+)'", block))
        have = {s["id"] for s in self.data["scenarios"]}
        self.assertTrue(ids <= have, ids - have)

    def test_cards_of_readiness_point_back_to_the_scenario(self):
        for s in self.data["scenarios"]:
            if not s["card"]:
                continue
            card = readiness.by_id(s["card"])
            first = s["id"].split("+")[0]
            self.assertIn(first, card["scenario"], f"{s['id']} / {s['card']}")
            self.assertEqual(s["who"], re.sub(r"\s*\(WHO:[^)]*\)", "", card["who"]))

    def test_groups_cover_every_scenario(self):
        groups = {g["id"] for g in self.data["groups"]}
        for s in self.data["scenarios"]:
            self.assertIn(s["group"], groups)

    def test_same_seed_same_numbers(self):
        a, b, c = (CopySet(None, seed, "crusher:1@10=4") for seed in (42, 42, 43))
        for cs in (a, b, c):
            step(cs, 40)
        sa, sb, sc = (cs.copies["fact"].snapshot() for cs in (a, b, c))
        self.assertEqual(sa, sb)
        self.assertNotEqual(sa, sc)


class ThreeTroublesTest(unittest.TestCase):
    def test_people_then_ecology_then_money(self):
        cs = CopySet(None, 42, "icy+dust+grid")
        fact = cs.copies["fact"]
        prm = ms.default()
        st = Store(ms.NS, prm["hist_min"])
        lm, om, pm = modules(st, prm)
        issues = {}
        for i in range(35):
            cs.step()
            if i % 5 == 4:
                t = fact.state.clock.t_min
                st.update_from_search(ms.items_from_plant(fact))
                lm.compute(t)
                om.compute(t)
                _f, issues = pm.compute(t, seed=3)
        order = sorted(issues.values(), key=lambda x: x["rank"])
        self.assertEqual([x["kind"] for x in order], ["road_winter", "tailings_dust", "grid_limited"])
        self.assertEqual([x["safety_class"] for x in order], ["S0", "S1", ""])
        self.assertEqual(order[0]["loss_usd_h"], -1.0)                 # people: never counted in money
        self.assertGreater(order[2]["loss_usd_h"], 0.0)

    def test_label_of_the_shift_is_one_phrase(self):
        self.assertIn("'icy+dust+grid' ? 'Смена с тремя бедами сразу'", read(STATIC, "app.js"))


# ------------------------------------------------------------------------------------------------ constructor
class ConstructorTest(unittest.TestCase):
    def test_ranges_equal_the_parameter_table(self):
        for key, (v, lo, hi, label) in scenarios.RANGES.items():
            row = TABLE[key]
            self.assertEqual((v, lo, hi, label), (row.value, row.min, row.max, row.label), key)
        con = scenarios.constructor()
        for t in con["troubles"]:
            if t["mag"] is None:
                continue
            row = TABLE[t["mag"]["param"]]
            self.assertEqual(t["mag"]["default"], row.value)
            self.assertEqual(t["mag"]["min"], row.min)
            self.assertAlmostEqual(t["mag"]["max"], row.max, places=2)
            self.assertEqual(t["mag"]["label_src"], scenarios.LABEL_RU[row.label])
            self.assertLess(t["mag"]["min"], t["mag"]["max"])

    def test_every_trouble_of_the_constructor_builds_a_token_the_simulator_takes(self):
        prm = default()
        for t in scenarios.TROUBLES:
            line = t["lines"][0] if t["lines"] else 0
            tok = f"{t['kind']}{':' + str(line) if line else ''}@60"
            ev.parse_scenario(tok, 480.0, prm)
            if t["param"]:
                row = TABLE[t["param"]]
                mid = round((row.min + min(row.max, 1e6)) / 2.0, 3)
                spec = ev.parse_scenario(f"{tok}={mid}", 480.0, prm)
                self.assertAlmostEqual(spec.events[0].t_start_min, 540.0)
                self.assertIn(t["kind"], ev.MAGNITUDE)
            else:
                self.assertNotIn(t["kind"], ev.MAGNITUDE)
                with self.assertRaises(ValueError):
                    ev.parse_scenario(f"{tok}=1", 480.0, prm)

    def test_token_rules(self):
        prm = default()
        self.assertEqual(ev.split_token("crusher:1@90=4.5"), ("crusher:1", 90.0, 4.5))
        self.assertEqual(ev.split_token("grid"), ("grid", None, None))
        self.assertEqual(ev.split_token("bad token"), ("bad token", None, None))
        spec = ev.parse_scenario("crusher:1@90=4.5+dose:2@120=0.3+grid=200", 480.0, prm)
        self.assertEqual(spec.text, "crusher:1+dose:2+grid")               # the label of the run keeps the bare kinds
        by = {e.kind: e for e in spec.events}
        self.assertEqual((by["crusher"].t_start_min, by["crusher"].data["work_h"]), (570.0, 4.5))
        self.assertEqual((by["dose"].t_start_min, by["dose"].data["drop"]), (600.0, 0.3))
        self.assertEqual((by["grid"].t_start_min, by["grid"].data["limit_mw"]), (480.0, 200.0))
        clamp = ev.parse_scenario("crusher:1=99", 480.0, prm).events[0]
        self.assertEqual(clamp.data["work_h"], TABLE["crush_repair_h"].max)       # inside the range of the row
        with self.assertRaises(ValueError):
            ev.parse_scenario("crusher:1@900", 480.0, prm)                         # after 20:00
        with self.assertRaises(ValueError):
            ev.parse_scenario("hpgr:2=3", 480.0, prm)                              # no magnitude for this kind

    def test_a_late_start_reaches_the_plant(self):
        cs = CopySet(None, 42, "crusher:1@90")
        fact = cs.copies["fact"]
        step(cs, 60)
        self.assertNotEqual(fact.state.line(1).crusher.state, "STOP")
        step(cs, 40)
        self.assertEqual(fact.state.line(1).crusher.state, "STOP")

    def test_the_repair_median_follows_the_magnitude(self):
        work = {}
        for tok in ("crusher:1", "crusher:1=6"):
            cs = CopySet(None, 42, tok)
            step(cs, 5)
            job = cs.copies["fact"].call("", issue="crusher:1")
            work[tok] = job.t_done_min - job.t_arrive_min
        self.assertAlmostEqual(work["crusher:1=6"] / work["crusher:1"], 6.0 / TABLE["crush_repair_h"].value, places=3)

    def test_the_token_is_accepted_by_the_server(self):
        for tok in ("crusher:1@90=4.5", "icy@120=8+dust@60+grid=200", "hard:1=26.5", "icy+dust+grid"):
            self.assertIsNotNone(server.RE_SCENARIO.match(tok), tok)
        for bad in ("Crusher:1", "crusher 1", "a;b", "x" * 201):
            self.assertIsNone(server.RE_SCENARIO.match(bad), bad)


# ------------------------------------------------------------------------------------------------ fake Ditto
def merge(cur, patch):
    """RFC 7396: null removes a key, objects merge, anything else replaces."""
    if not isinstance(patch, dict):
        return patch
    out = dict(cur) if isinstance(cur, dict) else {}
    for k, v in patch.items():
        if v is None:
            out.pop(k, None)
        else:
            out[k] = merge(out.get(k), v)
    return out


class FakeDitto:
    def __init__(self, run="run-1", sim_time=500.0):
        self.values = {("site", "idSimulationRun"): run, ("site", "sim_time"): sim_time}
        self.patches = []

    def __call__(self, method, path, body=None, headers=None):
        m = re.match(r"/api/2/things/kz\.aktogay:([a-z0-9-]+)/features(?:/([A-Za-z_]+)/properties/value)?$", path)
        assert m, path
        thing, feature = m.group(1), m.group(2)
        if method == "GET":
            if (thing, feature) in self.values:
                return self.values[(thing, feature)]
            raise server.UpstreamError(404, "Ditto 404")
        assert method == "PATCH" and not feature
        self.patches.append((thing, body))
        for f, obj in body.items():
            v = obj["properties"]["value"]
            self.values[(thing, f)] = merge(self.values.get((thing, f)), v)
        return None


class ServerCase(unittest.TestCase):
    def setUp(self):
        self.fake = FakeDitto()
        self.old = server.ditto
        server.ditto = self.fake
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        server.ditto = self.old

    def post(self, path, body):
        req = urllib.request.Request(self.base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())


class ScenarioRouteTest(ServerCase):
    def test_constructor_token_and_seed_go_to_control_scenario(self):
        code, r = self.post("/api/scenario", {"id": "crusher:1@90=4.5+dose:2@120", "seed": 7})
        self.assertEqual(code, 200)
        v = self.fake.values[("control", "scenario")]
        self.assertEqual((v["id"], v["seed"]), ("crusher:1@90=4.5+dose:2@120", 7.0))
        self.assertEqual(v["run"], "run-1")
        # the next scenario without a seed does not inherit it
        self.post("/api/scenario", {"id": "grid"})
        v = self.fake.values[("control", "scenario")]
        self.assertEqual(v["id"], "grid")
        self.assertNotIn("seed", v)

    def test_bad_token_is_refused(self):
        code, r = self.post("/api/scenario", {"id": "crusher 1"})
        self.assertEqual(code, 400)
        self.assertFalse([p for p in self.fake.patches if p[0] == "control"])


# ------------------------------------------------------------------------------------------------ mechanic
class JournalRouteTest(ServerCase):
    def test_a_call_does_not_inherit_via_of_an_earlier_call(self):
        self.post("/api/call", {"issue": "issue-1", "role": "Механик ЦПД", "text": "x", "via": "head"})
        self.assertEqual(self.fake.values[("journal", "last")]["via"], "head")
        self.post("/api/call", {"issue": "issue-2", "role": "Механик ЦПД", "text": "y"})
        v = self.fake.values[("journal", "last")]
        self.assertNotIn("via", v)
        self.assertEqual((v["issue"], v["action"], v["seq"]), ("issue-2", "call", 2))


class MechanicTest(ServerCase):
    def test_status_is_written_into_the_journal_with_a_log(self):
        code, r = self.post("/api/mech", {"issue": "issue-7", "status": "accepted", "person": "person-crusher-mech"})
        self.assertEqual(code, 200)
        self.fake.values[("site", "sim_time")] = 530.0
        self.post("/api/mech", {"issue": "issue-7", "status": "enroute", "person": "person-crusher-mech"})
        self.fake.values[("site", "sim_time")] = 560.0
        code, r = self.post("/api/mech", {"issue": "issue-7", "status": "help", "person": "person-crusher-mech", "text": "нужен второй"})
        m = self.fake.values[("journal", "mech")]
        self.assertEqual((m["seq"], m["status"], m["issue"]), (3, "help", "issue-7"))
        e = m["items"]["issue-7"]
        self.assertEqual([x["s"] for x in e["log"]], ["accepted", "enroute", "help"])
        self.assertEqual([x["t"] for x in e["log"]], [500.0, 530.0, 560.0])
        self.assertEqual((e["run"], e["person"]), ("run-1", "person-crusher-mech"))

    def test_entries_of_an_earlier_run_are_dropped_and_the_log_restarts(self):
        self.post("/api/mech", {"issue": "issue-7", "status": "accepted"})
        self.post("/api/mech", {"issue": "issue-8", "status": "accepted"})
        self.fake.values[("site", "idSimulationRun")] = "run-2"
        self.post("/api/mech", {"issue": "issue-7", "status": "onsite"})
        items = self.fake.values[("journal", "mech")]["items"]
        self.assertEqual(set(items), {"issue-7"})                       # issue-8 of run-1 is gone
        self.assertEqual([x["s"] for x in items["issue-7"]["log"]], ["onsite"])

    def test_bad_input_is_refused_and_nothing_is_written(self):
        for body in ({"issue": "x", "status": "accepted"}, {"issue": "issue-1", "status": "gone"},
                     {"issue": "issue-1", "status": "done", "person": "PERSON"}):
            code, _ = self.post("/api/mech", body)
            self.assertEqual(code, 400, body)
        self.assertNotIn(("journal", "mech"), self.fake.values)

    def test_the_module_shows_the_status_of_the_called_person_in_the_life_cycle(self):
        st, prm = fork_store()
        lm, om, pm, _feats, issues = run_fork(st, prm)
        name = next(n for n, f in issues.items() if f["kind"] == "lube_trip")
        self.assertEqual([s["key"] for s in issues[name]["lifecycle"]["steps"]], ["new"])
        mech = {"seq": 3, "items": {name: {"status": "help", "person": "person-kip", "run": ms.RUN, "t": T0 + 5,
                                           "log": [{"s": "accepted", "t": T0 + 1}, {"s": "enroute", "t": T0 + 3}, {"s": "help", "t": T0 + 5}]}}}
        ov = dict(fork_ov(), journal={"last": {}, "mech": mech})
        st.update_from_search(ms.snapshot(T0 + 5, ov))
        _f, issues2 = pm.compute(T0 + 5, seed=42)
        lc = issues2[name]["lifecycle"]
        self.assertEqual([s["key"] for s in lc["steps"]], ["new", "accepted", "enroute"])
        self.assertEqual({s["key"]: s["src"] for s in lc["steps"]}["accepted"], "механик")
        self.assertEqual(lc["help"], 1.0)
        self.assertIn("просит помощь", issues2[name]["escalation"])
        self.assertIn("(механик)", lc["text"])
        # an entry of another run does not count
        mech["items"][name]["run"] = "other-run"
        st.update_from_search(ms.snapshot(T0 + 10, dict(fork_ov(), journal={"last": {}, "mech": mech})))
        _f, issues3 = pm.compute(T0 + 10, seed=42)
        self.assertEqual(issues3[name]["lifecycle"]["help"], 0.0)

    def test_the_model_estimate_does_not_precede_the_word_of_the_person(self):
        st, prm = fork_store()
        lm, om, pm, _feats, issues = run_fork(st, prm)
        name = next(n for n, f in issues.items() if f["kind"] == "lube_trip")
        iss = next(i for i in pm.issues.values() if i.name == name)
        iss.enroute_at, iss.onsite_at = T0 + 1.0, T0 + 2.0              # the crew was seen on its way and at work
        _f, out = pm.compute(T0 + 5, seed=42)
        lc = out[name]["lifecycle"]
        self.assertEqual({s["key"]: s["src"] for s in lc["steps"]}, {"new": "модель", "enroute": "модель", "onsite": "модель"})
        mech = {"seq": 1, "items": {name: {"status": "accepted", "person": "person-kip", "run": ms.RUN, "t": T0 + 30,
                                           "log": [{"s": "accepted", "t": T0 + 30}]}}}
        st.update_from_search(ms.snapshot(T0 + 30, dict(fork_ov(), journal={"last": {}, "mech": mech})))
        _f, out = pm.compute(T0 + 30, seed=42)
        keys = [s["key"] for s in out[name]["lifecycle"]["steps"]]
        self.assertEqual(keys, ["new", "accepted"])                      # «на месте» seen earlier than the word of the person is not shown

    def test_the_screen_is_narrow_with_big_targets_and_five_statuses(self):
        js, css = read(STATIC, "mech.js"), read(STATIC, "style.css")
        for k, ru in (("accepted", "Принял"), ("enroute", "В пути"), ("onsite", "На месте"), ("help", "Нужна помощь"), ("done", "Готово")):
            self.assertIn(f"['{k}', '{ru}']", js)
        for sec in ("Мои вызовы", "Работа", "Статус"):
            self.assertIn(f"<h3>{sec}</h3>", js)
        for lab in ("Что", "Где", "Наряд-допуск", "Точки отключения", "Как проверить, что готово"):
            self.assertIn(lab, js)
        self.assertIn("/api/mech", js)
        for sel in (r"\.mh-call", r"\.mh-st", r"\.mh select"):
            m = re.search(sel + r"\s*\{[^}]*min-height:\s*(\d+)px", css)
            self.assertIsNotNone(m, sel)
            self.assertGreaterEqual(int(m.group(1)), 48, sel)
        self.assertRegex(css, r"body\.mech #stage\s*\{[^}]*max-width:\s*560px")
        self.assertRegex(css, r"body\.mech #nav[^{]*#panel[^{]*\{[^}]*display:\s*none")
        self.assertNotIn("['mech'", read(STATIC, "app.js"))                  # a view by role, not an item of the menu

    def test_the_card_shows_the_life_cycle_and_the_server_trusts_only_known_statuses(self):
        app = read(STATIC, "app.js")
        self.assertIn("AKT.life = n =>", app)
        self.assertIn("(механик)", app)
        self.assertIn("'нужна помощь'", app)
        self.assertEqual(server.MECH_STATUS, ("accepted", "enroute", "onsite", "help", "done"))
        # a person on the way to the node keeps his call although the chain already names a deputy for him
        self.assertIn("const onJob = (p, i) =>", read(STATIC, "mech.js"))
        self.assertIn("if (main && onJob(main, i)) return main;", read(STATIC, "mech.js"))


# ------------------------------------------------------------------------------------------------ price of a trouble
class CostTest(unittest.TestCase):
    def pm(self):
        st, prm = ms.make_store(T0, {})
        lm, om, pm = modules(st, prm)
        return pm, prm

    def ranked(self, usd=1000.0):
        return Ranked("x", 1, "now", "<3", usd, 0.0, 0.0, 0.0, -1.0, 0.0, 1.0, -1.0)

    def test_parts_add_up_and_each_part_names_what_it_stands_on(self):
        pm, prm = self.pm()
        for kind, part, label in (("loss_sag", "energy", "допущение"), ("reagent_over", "reagent", "допущение"),
                                  ("conc_low", "penalty", "допущение")):
            tr = pm._tr("n:x", "sag-1", kind, 0.3, 0.0, "rep_decision_h", T0, loud=False, usd_extra_h=2000.0)
            c = pm._cost(tr, self.ranked())
            by = {i["key"]: i for i in c["items"]}
            self.assertAlmostEqual(sum(i["usd_h"] for i in c["items"]), tr.rate_usd_h, places=6)
            self.assertAlmostEqual(by[part]["usd_h"], 2000.0, places=6)
            self.assertGreater(by["cu"]["usd_h"], 0.0)
            self.assertEqual(by[part]["label"], label)
            self.assertTrue(by[part]["supports"] and all(s["what"] and s["label"] for s in by[part]["supports"]))
            self.assertEqual([i["key"] for i in c["items"]][:4], ["cu", "energy", "reagent", "penalty"])
            for other in ("energy", "reagent", "penalty"):
                if other != part:
                    self.assertEqual(by[other]["usd_h"], 0.0)
                    self.assertEqual(by[other]["supports"], [])
        # the labels come from the parameter rows themselves
        rows = {p.key: p for p in MPARAMS}
        self.assertEqual(rows["reagent_usd_kg"].label, "assumption")
        self.assertEqual(rows["cu_price_usd_t"].label, "fact")
        self.assertEqual(rows["payable_frac"].label, "calc")

    def test_copper_alone_stands_on_fact_and_calculation_and_the_horizon_on_assumptions(self):
        pm, prm = self.pm()
        tr = pm._tr("crusher-1:stop", "crusher-1", "crusher_stop", 5.0, 0.0, "rep_crusher_h", T0)
        c = pm._cost(tr, self.ranked(54321.0))
        cu = c["items"][0]
        self.assertEqual((cu["key"], cu["label"]), ("cu", "расчёт"))
        self.assertEqual({s["label"] for s in cu["supports"]}, {"факт", "расчёт"})
        self.assertEqual(c["horizon"]["usd"], 54321.0)
        self.assertEqual(c["horizon"]["label"], "допущение")
        self.assertIn("допущение", {s["label"] for s in c["horizon"]["supports"]})
        self.assertIn("расчёте", c["text"])

    def test_safety_classes_have_no_price(self):
        pm, prm = self.pm()
        tr = pm._tr("w:dust", "water", "tailings_dust", 0.0, 0.0, "", T0, safety="S1")
        c = pm._cost(tr, self.ranked(0.0))
        self.assertEqual((c["items"], c["usd_h"]), ([], -1.0))
        self.assertIn("не считается", c["text"])

    def test_the_issue_carries_the_breakdown_and_the_card_shows_it_inside_the_second_level(self):
        st, prm = fork_store()
        _lm, _om, _pm, _f, issues = run_fork(st, prm)
        for f in issues.values():
            self.assertEqual({"usd_h", "items", "horizon", "weakest", "text"}, set(f["cost"]))
            if f["loss_usd_h"] > 0:
                self.assertAlmostEqual(sum(i["usd_h"] for i in f["cost"]["items"]), f["loss_usd_h"], delta=0.01)
        app = read(STATIC, "app.js")
        more = re.search(r'<details id="tc-more">.*?</details>', app, re.S).group(0)
        self.assertIn('id="tc-cost"', more)                              # second level: no new permanent block
        self.assertIn("Из чего складывается цена", app)
        self.assertRegex(app, r"AKT\.costHtml = n =>")
        self.assertIn("не входит", app)


# ------------------------------------------------------------------------------------------------ handover button
class HandoverButtonTest(unittest.TestCase):
    def test_the_module_shows_the_button_in_the_last_hour_of_a_shift_only(self):
        st, prm = ms.make_store(T0, {})
        _lm, _om, pm = modules(st, prm)
        lead = prm["handover_btn_lead_min"]
        self.assertEqual(lead, 60)
        hh = lambda h, m=0: h * 60.0 + m                         # noqa: E731
        cases = [(hh(8), 0), (hh(12), 0), (hh(18, 59), 0), (hh(19), 1), (hh(19, 30), 1), (hh(19, 59), 1), (hh(20), 0),
                 (hh(23), 0), (hh(30, 59), 0), (hh(31), 1), (hh(31, 59), 1), (hh(32), 0), (hh(32, 1), 0)]
        for t, show in cases:
            b = pm._handover_btn(t)
            self.assertEqual(b["show"], float(show), f"{t / 60:.2f} h")
            self.assertEqual(b["end"] - b["from"], lead)
        self.assertEqual(pm._handover_btn(hh(19))["end"], hh(20))
        self.assertEqual(pm._handover_btn(hh(31))["end"], hh(32))

    def test_it_is_a_feature_of_the_module_and_a_parameter_with_a_label(self):
        row = next(p for p in MPARAMS if p.key == "handover_btn_lead_min")
        self.assertEqual((row.label, row.unit), ("assumption", "min"))
        self.assertIn("UI_RULES_28", row.source)
        st, prm = ms.make_store(T0, {})
        lm, om, pm = modules(st, prm)
        lm.compute(T0)
        om.compute(T0)
        feats, _ = pm.compute(T0)
        self.assertEqual(set(feats["handover_btn"]), {"show", "from", "end", "lead_min"})

    def test_the_page_draws_it_only_when_the_module_says_so(self):
        app = read(STATIC, "app.js")
        body = app[app.index("AKT.updateHandoverBtn = () =>"):]
        body = body[:body.index("\n};") + 3]
        self.assertIn("Number(b.show) === 1", body)
        self.assertIn("el.remove()", body)
        self.assertIn("'WARMUP'", body)
        self.assertIn("AKT.updateHandoverBtn();", app)
        self.assertNotIn('id="ho-btn"', read(STATIC, "index.html"))      # not a permanent element of the screen


# ------------------------------------------------------------------------------------------------ replay
class ReplayTest(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(read(STATIC, "replay.json"))

    def test_file_is_built_from_the_stored_trial_rows(self):
        self.assertEqual(read(STATIC, "replay.json"), replay.json_text())
        self.assertEqual(len(self.data["shifts"]), 100)
        self.assertEqual((self.data["source"]["seed0"], self.data["source"]["seed1"]), (1001, 1100))

    def test_stages_are_in_order_and_the_twin_is_never_worse_on_copper(self):
        for s in self.data["shifts"]:
            self.assertGreaterEqual(s["gain_cu_t"], -0.05, s["seed"])
            for t in s["troubles"]:
                for w in ("with", "without"):
                    c = t[w]
                    seq = [x for x in (t["start"], c["noticed"], c["called"], c["arrived"], c["done"]) if x is not None]
                    self.assertEqual(seq, sorted(seq), (s["seed"], t["issue"], w))
                self.assertEqual(t["without"]["noticed"], t["without"]["called"])      # people call when they see it
                if t["decision"]:
                    self.assertIsNone(t["with"]["arrived"])
                    self.assertEqual(t["with"]["done"], t["with"]["called"])
        mean = sum(s["gain_cu_t"] for s in self.data["shifts"]) / 100.0
        self.assertAlmostEqual(mean, self.data["summary"]["mean_cu_t"], places=1)

    def test_one_seed_repeats_its_times_on_the_current_code(self):
        """The stored times are those of the trial of 22.10; a single seed (not the N = 100) repeats them exactly."""
        stored = json.loads(read(ROOT, "sim", "data", "trial_n100.json"))["shifts"][0]
        row = trial.run_shift((1001, dict(trial.DEFAULTS, no_twin=True)))
        self.assertEqual(row["bookings"]["no_twin"], stored["bookings"]["no_twin"])
        self.assertEqual(row["bookings"]["by_value"], stored["bookings"]["by_value"])
        self.assertAlmostEqual(row["cu_t_2000"]["no_twin"] / stored["cu_t_2000"]["no_twin"], 1.0, delta=0.001)

    def test_the_page_says_it_is_an_estimate_and_draws_two_lines_per_trouble(self):
        js = read(STATIC, "replay.js")
        for w in ("оценка на модели", "С двойником", "Без двойника", "Началась", "Заметили", "Позвали", "Прибыл", "Решено", "т Cu"):
            self.assertIn(w, js)
        self.assertIn("/replay.json", js)


# ------------------------------------------------------------------------------------------------ labels of the parameters
class ParamSummaryTest(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(read(STATIC, "params_summary.json"))

    def test_file_equals_the_tables(self):
        self.assertEqual(read(STATIC, "params_summary.json"), paramstat.json_text())
        d = self.data
        self.assertEqual(d["sim_rows"], len(TABLE))
        self.assertEqual(d["modules_rows"], len(MPARAMS))
        self.assertEqual(d["rows"], len(TABLE) + len(MPARAMS))
        self.assertEqual(sum(x["total"] for x in d["labels"]), d["rows"])
        self.assertEqual([x["key"] for x in d["labels"]], ["fact", "vendor", "analog", "project", "calc", "assumption"])
        a = next(x for x in d["labels"] if x["key"] == "assumption")
        self.assertEqual(a["total"], sum(1 for r in TABLE.values() if r.label == "assumption") + sum(1 for p in MPARAMS if p.label == "assumption"))
        self.assertAlmostEqual(d["assumption_pct"], 100.0 * a["total"] / d["rows"], places=1)
        self.assertGreater(d["assumption_pct"], 50.0)                    # the honest share is not hidden

    def test_the_final_documents_quote_the_same_numbers(self):
        doc = read(FINAL, "VALIDATION.md")
        sec = doc[doc.index("### 12.1 Чего модель не умеет"):doc.index("## 13. Источники отчётных чисел")]
        d = self.data
        lab = {x["key"]: x["total"] for x in d["labels"]}
        self.assertIn(f"{d['rows']} чисел", sec)
        self.assertIn(f"**{lab['assumption']} допущений ({str(d['assumption_pct']).replace('.', ',')} %)**", sec)
        for key, ru in (("fact", "фактов"), ("vendor", "вендор"), ("analog", "аналог"), ("project", "проект"), ("calc", "расчёт")):
            self.assertIn(f"{lab[key]} {ru}", sec)
        self.assertIn("64 — допущения", sec)
        self.assertIn("78 новых строк", sec)
        self.assertRegex(sec, r"не лучше константы")
        self.assertIn("1,73 п.п. против 1,40 п.п.", sec)
        self.assertRegex(sec, r"Реальных журналов смен нет")
        par = read(FINAL, "PARAMETERS.md")
        self.assertIn(f"({lab['assumption']} из {d['rows']})", par)

    def test_the_calibration_page_shows_the_summary_and_the_limits(self):
        js = read(STATIC, "views.js")
        for w in ("params_summary.json", "cb-params", "cb-limits", "Чего модель не умеет", "На чём стоят числа модели"):
            self.assertIn(w, js)
        self.assertEqual(self.data["tier_s"]["assumptions"], 64)
        self.assertTrue(any("не лучше константы" in x for x in self.data["limits"]))


# ------------------------------------------------------------------------------------------------ module documentation
class ApiDocTest(unittest.TestCase):
    def test_files_equal_the_generator(self):
        self.assertEqual(read(WEB, "API.md"), apidoc.md_text())
        self.assertEqual(read(STATIC, "modules.json"), apidoc.modules_json())

    def test_every_module_names_input_output_test_and_live_status(self):
        md = read(WEB, "API.md")
        data = json.loads(read(STATIC, "modules.json"))["modules"]
        self.assertGreaterEqual(len(data), 5)
        for m in data:
            sec = md[md.index(f"### {m['id']} "):]
            sec = sec[:sec.index("\n### ", 4)] if "\n### " in sec[4:] else sec
            for lab in ("**Вход из Ditto:**", "**Вход из InfluxDB:**", "**Выход:**", "**Тест:**", "**Живой статус:**"):
                self.assertIn(lab, sec, m["id"])
            self.assertTrue(m["reads"] and m["writes"] and m["tests"], m["id"])
            for t in m["tests"]:
                self.assertTrue(os.path.isfile(os.path.join(ROOT, t.replace("tests/", "tests" + os.sep, 1))), t)
            self.assertTrue(os.path.isfile(os.path.join(os.path.dirname(ROOT), m["code"].replace("/", os.sep))), m["code"])
        ids = {m["id"] for m in data}
        self.assertTrue({"akt-losses", "akt-ore", "akt-priority", "akt-sim", "akt-calib"} <= ids)

    def test_inputs_are_what_the_code_reads(self):
        from modules import losses, ore
        md = read(WEB, "API.md")
        for name in losses.READS + ore.READS + priority.READS:
            self.assertIn(f"`{name}`", md, name)
        # the modules read Ditto and InfluxDB only
        for m in ("losses", "ore", "priority"):
            src = read(ROOT, "modules", f"{m}.py")
            self.assertNotRegex(src, r"^\s*(from|import)\s+sim\b", m)

    def test_the_page_how_to_check_shows_the_live_status_of_the_modules(self):
        js = read(STATIC, "pages.js")
        for w in ("Модули: живой статус", "ht-mods", "/modules.json", "modStatus", "AKT.modifiedAge"):
            self.assertIn(w, js)
        for ident in ("akt-web", "akt-sim", "akt-calib", "akt-setup"):
            self.assertIn(ident, js)


# ------------------------------------------------------------------------------------------------ screens and diorama
class ScreensTest(unittest.TestCase):
    def test_new_pages_are_loaded_and_in_the_menu_of_four_groups(self):
        html = read(STATIC, "index.html")
        for f in ("scenarios.js", "replay.js", "mech.js"):
            self.assertIn(f'<script src="/{f}"></script>', html)
        app = read(STATIC, "app.js")
        m = re.search(r"const MENU4 = \[(.*?)\n\];", app, re.S).group(1)
        self.assertIn("['scenarios', 'Сценарии']", m)
        self.assertIn("['replay', 'Повтор смены']", m)
        for name, view in (("scenarios.js", "scenarios"), ("replay.js", "replay"), ("mech.js", "mech")):
            self.assertRegex(read(STATIC, name), r"AKT\.views\.%s\s*=" % view)

    def test_catalog_runs_in_one_click_with_seed_and_confirms(self):
        js = read(STATIC, "scenarios.js")
        for w in ("Что должно произойти", "Как проверить", "Номер прогона (seed)", "AKT.panel.scenario(", "seed: this.seed()",
                  "Конструктор беды", "tokenOf", "Запустить сценарий"):
            self.assertIn(w, js)
        app = read(STATIC, "app.js")
        self.assertIn("if (opts && opts.seed != null) body.seed = opts.seed;", app)

    def test_scenario_mode_stays_hatching_and_banner_and_main_screen_has_no_new_block(self):
        css = read(STATIC, "style.css")
        self.assertIn("p-banner", read(STATIC, "app.js"))
        app = read(STATIC, "app.js")
        tiles = re.findall(r'<div class="tile" id="(k-\w+)"', app)
        self.assertEqual(tiles, ["k-loss", "k-cu", "k-ore", "k-rec", "k-mw", "k-usd"])
        # the new second-level pages are views, not blocks of the panel
        panel = app[app.index("  build() {"):app.index("  msg(text) {")]
        for w in ("scenarios", "replay", "mech", "lifecycle", "ho-btn"):
            self.assertNotIn(f'id="{w}', panel)
        self.assertIn("body.training::after", css)

    def test_light_diorama_comes_on_below_20_fps_or_by_a_button_and_keeps_the_look_otherwise(self):
        core = read(STATIC, "diorama", "core.js")
        self.assertIn("const LITE_FPS = 20;", core)
        self.assertIn("fps < LITE_FPS", core)
        self.assertIn("Лёгкий режим", core)
        self.assertIn("localStorage.setItem('dio-lite'", core)
        self.assertIn("AKT.params.get('lite')", core)
        self.assertIn("lite ? FRAME_MS_LITE : FRAME_MS", core)
        self.assertIn("const FRAME_MS = 32;", core)                      # the normal frame rate is as it was
        self.assertIn("state.lite = lite", core)

    def test_no_text_addressed_to_a_reader_outside_the_dispatcher(self):
        bad = re.compile(r"жюри|судь[яеи]|для\s+ИИ|нейросет|языков\w+\s+модел|\bAI\b|\bLLM\b", re.I)
        paths = [os.path.join(STATIC, n) for n in ("scenarios.js", "replay.js", "mech.js", "scenarios.json", "modules.json",
                                                   "params_summary.json")] + [os.path.join(WEB, "API.md")]
        for path in paths:
            for i, line in enumerate(read(path).splitlines(), 1):
                self.assertIsNone(bad.search(line), f"{os.path.basename(path)}:{i}: {line[:80]}")


if __name__ == "__main__":
    unittest.main()
