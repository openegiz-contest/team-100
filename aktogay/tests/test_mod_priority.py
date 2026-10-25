"""akt-priority (modules/priority.py): troubles from states and findings, issues, journal, advice text."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests import mod_support as ms  # noqa: E402
from modules import losses, ore, priority  # noqa: E402
from modules.writer import Catalog  # noqa: E402

T0 = 9 * 60 + 20.0     # 09:20


def modules(st, prm, auto=False):
    lm = losses.LossesModule(prm, st, ms.ROLES)
    om = ore.OreModule(prm, st)
    pm = priority.PriorityModule(prm, st, lm, om, ms.ROLES, auto)
    return lm, om, pm


def fork_ov(tail=0.068, **extra):
    ov = {"crusher-2": {"state": "STOP", "tph": 0.0, "power_kw": 0.0, "lube_kpa": 150.0},
          "conveyor-2": {"state": "STOP", "tph": 0.0, "power_kw": 0.0},
          "stockpile-2": {"level_t": 30000.0, "in_tph": 0.0, "hours_left": 7.78},
          "flot-1": {"tail_cu": tail}}
    ov.update(extra)
    return ov


def fork_store(t=T0):
    """Crusher-2 lube trip (stock 7 h 47 min) and the found flot-1 loss."""
    return ms.make_store(t, fork_ov())


def run_fork(st, prm, auto=False, t=T0):
    lm, om, pm = modules(st, prm, auto)
    # three analyser readings so the loss is on record
    for i, tail in enumerate((0.0680, 0.0681, 0.0682, 0.0679)):
        ti = t - 45.0 + 15.0 * i
        st.update_from_search(ms.snapshot(ti, {"crusher-2": {"state": "STOP", "tph": 0.0, "power_kw": 0.0,
                                                            "lube_kpa": 150.0},
                                               "conveyor-2": {"state": "STOP", "tph": 0.0, "power_kw": 0.0},
                                               "stockpile-2": {"level_t": 30000.0, "in_tph": 0.0, "hours_left": 7.78},
                                               "flot-1": {"tail_cu": tail}}))
        lm.compute(ti)
    om.compute(t)
    feats, issues = pm.compute(t, seed=42)
    return lm, om, pm, feats, issues


class PriorityTest(unittest.TestCase):
    def test_no_troubles(self):
        st, prm = ms.make_store(T0)
        lm, om, pm = modules(st, prm)
        lm.compute(T0)
        om.compute(T0)
        feats, issues = pm.compute(T0)
        self.assertEqual(issues, {})
        self.assertIn("Бед нет", feats["queue_text"])
        self.assertEqual(feats["auto_call"], {})
        self.assertEqual(feats["processed_sim_time"], T0)

    def test_fork_two_issues_one_crew(self):
        st, prm = fork_store()
        lm, om, pm, feats, issues = run_fork(st, prm)
        self.assertEqual(lm.results["flot-1"].status, "loss")
        self.assertEqual(len(issues), 2)
        by_node = {f["node"]: f for f in issues.values()}
        self.assertIn("flot-1", by_node)
        self.assertIn("crusher-2", by_node)
        self.assertEqual(by_node["flot-1"]["rank"], 1.0)
        self.assertEqual(by_node["crusher-2"]["rank"], 2.0)
        self.assertEqual(by_node["crusher-2"]["kind"], "lube_trip")
        self.assertIn("КИПиА", by_node["crusher-2"]["responsible"])
        self.assertGreater(by_node["crusher-2"]["call_by"], T0 + 60)
        self.assertEqual(by_node["flot-1"]["call_by"], -1.0)
        self.assertEqual(by_node["flot-1"]["status"], "OPEN")
        self.assertIn("можно отложить до", by_node["crusher-2"]["text"])
        self.assertIn("позвать сейчас", by_node["flot-1"]["text"])
        self.assertIn("оценка на модели", by_node["flot-1"]["text"])
        self.assertIn("Порядок устойчив", feats["queue_text"])
        self.assertIn("по громкости", feats["alarm_order_text"])
        self.assertIn("Дробилка ЦПД-2 → Флотация 1", feats["alarm_order_text"])
        self.assertIn("Флотация 1 → Дробилка ЦПД-2", feats["order_text"])
        self.assertNotIn(":stop", feats["order_text"] + feats["alarm_order_text"])
        self.assertEqual(feats["auto_call"], {})          # no automatic calls by default

    def test_journal_accept_and_disagree(self):
        st, prm = fork_store()
        lm, om, pm, feats, issues = run_fork(st, prm)
        flot_name = next(n for n, f in issues.items() if f["node"] == "flot-1")
        crusher_name = next(n for n, f in issues.items() if f["node"] == "crusher-2")
        t = T0 + 5.0
        st.update_from_search(ms.snapshot(t, fork_ov(journal={"last": {"seq": 1, "issue": flot_name, "action": "accept",
                                                                       "role": "Дежурный КИПиА", "text": "", "sim_time": t}})))
        feats, issues = pm.compute(t, seed=42)
        self.assertEqual(issues[flot_name]["status"], "CALLED")
        self.assertIn("позвали", issues[flot_name]["text"])
        t += 5.0
        st.update_from_search(ms.snapshot(t, fork_ov(journal={"last": {"seq": 2, "issue": crusher_name, "action": "disagree",
                                                                       "role": "", "text": "зову сразу", "sim_time": t}})))
        feats, issues = pm.compute(t, seed=42)
        self.assertEqual(issues[crusher_name]["status"], "SNOOZED")
        self.assertIn("не согласен", issues[crusher_name]["text"])
        # the same journal entry is not applied twice; an older seq is ignored
        feats, issues = pm.compute(t + 5.0, seed=42)
        self.assertEqual(issues[crusher_name]["status"], "SNOOZED")
        # snooze expires after q_snooze_h
        feats, issues = pm.compute(t + prm["q_snooze_h"] * 60.0 + 5.0, seed=42)
        self.assertEqual(issues[crusher_name]["status"], "OPEN")

    def test_auto_call_when_enabled(self):
        st, prm = fork_store()
        lm, om, pm, feats, issues = run_fork(st, prm, auto=True)
        self.assertEqual(feats["auto_call"]["seq"], 1)
        self.assertEqual(feats["auto_call"]["node"], "flot-1")
        self.assertIn("КИПиА", feats["auto_call"]["role"])
        called = [f for f in issues.values() if f["status"] == "CALLED"]
        self.assertEqual(len(called), 1)
        feats, issues = pm.compute(T0 + 5.0, seed=42)
        self.assertEqual(feats["auto_call"], {})          # one call per issue

    def test_safety_first(self):
        st, prm = fork_store()
        st.update_from_search(ms.snapshot(T0, {"water": {"state": "ALARM", "piezo_kpa": 190.0},
                                               "crusher-2": {"state": "STOP", "tph": 0.0, "lube_kpa": 150.0},
                                               "stockpile-2": {"hours_left": 7.78}}))
        lm, om, pm = modules(st, prm)
        lm.compute(T0)
        om.compute(T0)
        feats, issues = pm.compute(T0, seed=1)
        top = min(issues.values(), key=lambda f: f["rank"])
        self.assertEqual(top["node"], "water")
        self.assertEqual(top["safety_class"], "S0")
        # S0 is not counted in money: no loss rate, no loss over 12 h, no delay price, no loss start
        for k in ("loss_usd_h", "loss_shift_usd", "delay_cost_usd", "loss_from"):
            self.assertEqual(top[k], -1.0, k)
        self.assertIn("впереди всего", top["text"])
        self.assertIn("в деньгах не считается", top["text"])
        self.assertNotIn("$", top["text"])

    def test_reline_is_not_counted_again_downstream(self):
        """C4: SAG-1 relined, so both ball mills of line 1 stand; only the S0 issue of the SAG is raised."""
        st, prm = ms.make_store(T0, {"sag-1": {"state": "RELINE", "feed_tph": 0.0, "power_kw": 0.0},
                                     "ball-1a": {"state": "STOP", "power_kw": 0.0},
                                     "ball-1b": {"state": "STOP", "power_kw": 0.0},
                                     "pebble-1": {"state": "STOP", "feed_tph": 0.0},
                                     "line-1": {"state": "STOP", "tph": 0.0, "cu_tph": 0.0}})
        lm, om, pm = modules(st, prm)
        lm.compute(T0)
        om.compute(T0)
        feats, issues = pm.compute(T0, seed=1)
        nodes = sorted(f["node"] for f in issues.values())
        self.assertEqual(nodes, ["sag-1"])
        self.assertNotIn("Шаровая", feats["queue_text"])
        # a ball mill that stops on its own (SAG running) is still an issue
        st.update_from_search(ms.snapshot(T0 + 5.0, {"ball-1a": {"state": "STOP", "power_kw": 0.0}}))
        feats, issues = pm.compute(T0 + 5.0, seed=1)
        self.assertIn("ball-1a", {f["node"] for f in issues.values() if f["status"] != "RESOLVED"})

    def test_order_note_with_one_issue_besides_safety(self):
        """S0 reline plus one money issue: the note says there is nothing to order, not a false
        "robustness 100 % < 70 %"."""
        st, prm = ms.make_store(T0, {"sag-1": {"state": "RELINE", "feed_tph": 0.0, "power_kw": 0.0},
                                     "ball-1a": {"state": "STOP", "power_kw": 0.0},
                                     "ball-1b": {"state": "STOP", "power_kw": 0.0},
                                     "pebble-1": {"state": "STOP", "feed_tph": 0.0},
                                     "line-1": {"state": "STOP", "tph": 0.0, "cu_tph": 0.0},
                                     "ball-2a": {"state": "STOP", "power_kw": 0.0}})
        lm, om, pm = modules(st, prm)
        lm.compute(T0)
        om.compute(T0)
        feats, issues = pm.compute(T0, seed=1)
        self.assertEqual(sorted(f["node"] for f in issues.values()), ["ball-2a", "sag-1"])
        self.assertIn("остальная беда одна", feats["queue_text"])
        self.assertNotIn("< 70 %", feats["queue_text"])

    def test_loss_start_and_call_by_after_midnight(self):
        """A crusher stop with 10 h of stock at 20:00: losses start tomorrow, the text says so."""
        t = 20 * 60.0
        st, prm = ms.make_store(t, {"crusher-1": {"state": "STOP", "tph": 0.0, "power_kw": 0.0},
                                    "conveyor-1": {"state": "STOP", "tph": 0.0, "power_kw": 0.0},
                                    "stockpile-1": {"level_t": 38530.0, "in_tph": 0.0, "hours_left": 10.0}})
        lm, om, pm = modules(st, prm)
        lm.compute(t)
        om.compute(t)
        feats, issues = pm.compute(t, seed=1)
        cr = next(f for f in issues.values() if f["node"] == "crusher-1")
        self.assertAlmostEqual(cr["loss_from"], t + 600.0)
        self.assertGreater(cr["loss_usd_h"], 0.0)
        self.assertIn("потерь до 06:00 завтра нет", cr["text"])
        self.assertNotIn("$0 ", cr["text"])
        self.assertGreater(cr["call_by"], 24 * 60.0)
        self.assertIn("завтра", cr["text"].split("отложить до")[1][:20])

    def test_filter_one_press_counts_the_short_share(self):
        st, prm = ms.make_store(T0, {"filter-1": {"state": "ONE", "presses_on": 1.0, "limit_tph": 35.0},
                                     "thick-1": {"inventory_t": 200.0, "hours_to_full": 6.7}})
        lm, om, pm = modules(st, prm)
        lm.compute(T0)
        om.compute(T0)
        feats, issues = pm.compute(T0, seed=1)
        fi = next(f for f in issues.values() if f["node"] == "filter-1")
        share = 1.0 - 35.0 / 56.4
        cu = 13.7
        self.assertAlmostEqual(fi["loss_usd_h"], cu * share * prm["payable_frac"] * prm["cu_price_usd_t"], delta=50.0)
        self.assertAlmostEqual(fi["loss_from"], T0 + 6.7 * 60.0)
        self.assertIn("потерь до 16:02 нет", fi["text"])

    def test_state_without_loss_is_no_issue(self):
        """Fleet SHORT against the regulator target while the haul still covers the plant: no $0 issue."""
        st, prm = ms.make_store(T0, {"fleet": {"state": "SHORT", "haul_tph": 8680.0}, "site": {"tph": 7706.0}})
        lm, om, pm = modules(st, prm)
        lm.compute(T0)
        om.compute(T0)
        feats, issues = pm.compute(T0, seed=1)
        self.assertEqual(issues, {})
        st.update_from_search(ms.snapshot(T0 + 5.0, {"fleet": {"state": "SHORT", "haul_tph": 5000.0}, "site": {"tph": 7706.0}}))
        feats, issues = pm.compute(T0 + 5.0, seed=1)
        fl = next(f for f in issues.values() if f["node"] == "fleet")
        self.assertGreater(fl["loss_usd_h"], 0.0)

    def test_issue_without_loss_never_first(self):
        """A hard batch whose forecast t/h is not below today's makes no issue; a $0 issue is never ranked first."""
        from modules.policy import Trouble, rank
        prm = ms.default()
        tr = [Trouble("zero", "pit", "hard_ore", rate_cu_tph=0.0, rate_usd_h=0.0, t_conseq_h=0.0, repair_h=0.5,
                      detected_at=1.0),
              Trouble("crusher-1:stop", "crusher-1", "crusher_stop", rate_cu_tph=13.0, rate_usd_h=180000.0,
                      t_conseq_h=3.0, repair_h=3.0, crew="crew-cpd", detected_at=2.0)]
        plan = rank(tr, T0, prm, {}, seed=1)
        self.assertEqual(plan.order[0].id, "crusher-1:stop")

    def test_resolved_when_state_returns(self):
        st, prm = fork_store()
        lm, om, pm, feats, issues = run_fork(st, prm)
        st.update_from_search(ms.snapshot(T0 + 5.0, {"flot-1": {"tail_cu": 0.0682}}))   # crusher back to RUN
        lm.compute(T0 + 5.0)
        feats, issues = pm.compute(T0 + 5.0, seed=42)
        crusher = next(f for f in issues.values() if f["node"] == "crusher-2")
        self.assertEqual(crusher["status"], "RESOLVED")
        self.assertNotIn("Дробилка", feats["queue_text"])
        self.assertEqual(pm.pruned, [])
        # the resolved issue thing is pruned after q_issue_keep_h
        t2 = T0 + 5.0 + prm["q_issue_keep_h"] * 60.0
        st.update_from_search(ms.snapshot(t2, {"flot-1": {"tail_cu": 0.0683}}))
        lm.compute(t2)
        feats, issues = pm.compute(t2, seed=42)
        self.assertEqual(len(pm.pruned), 1)
        self.assertTrue(pm.pruned[0].startswith("issue-"))
        self.assertNotIn("crusher-2", {f["node"] for f in issues.values()})

    def test_grid_and_hard_ore_without_crews(self):
        batches = [{"name": "batch-0009", "line": 1, "state": "BELT", "est_axb": 27.0, "tonnes": 15000.0}]
        st, prm = ms.make_store(T0, {"power": {"state": "LIMITED", "grid_limit_mw": 210.0, "site_mw": 200.0},
                                     "site": {"cu_tph": 20.0}}, batches=batches)
        lm, om, pm = modules(st, prm)
        lm.compute(T0)
        om.compute(T0)
        feats, issues = pm.compute(T0, seed=3)
        kinds = {f["kind"] for f in issues.values()}
        self.assertIn("grid_limited", kinds)
        self.assertIn("hard_ore", kinds)
        grid = next(f for f in issues.values() if f["kind"] == "grid_limited")
        self.assertIn("Дежурный энергетик", grid["responsible"])
        self.assertIn("допущение", grid["text"])
        hard = next(f for f in issues.values() if f["kind"] == "hard_ore")
        self.assertIn("Геолог", hard["responsible"])
        self.assertIn("Порядок не важен", feats["queue_text"])
        # nothing shed yet: the cheapest load (no copper) goes first
        self.assertIn("что отключать первым", grid["text"])
        self.assertIn("1) фидер прочей нагрузки кат. 2", grid["text"])
        self.assertIn("медь не теряется", grid["text"])
        # the batch is on the belt already: blending in the pit cannot change it, the text does not advise it
        self.assertIn("твёрдая руда — B-0009", hard["text"])
        self.assertIn("партия уже вынута", hard["text"])
        self.assertNotIn("шихтовать 50/50", hard["text"])


class QueueTextTest(unittest.TestCase):
    """The words of the queue do not contradict each other or what the crews are doing."""

    def test_crew_already_on_the_node_is_not_advised_again(self):
        """Crusher-1 stopped and crew-cpd already travels there (the alarm called it): the line says so and
        does not advise to call a crew it shows "busy" with this very job; the queue is not "no troubles"."""
        base = {"crusher-1": {"state": "STOP", "tph": 0.0, "power_kw": 0.0},
                "conveyor-1": {"state": "STOP", "tph": 0.0, "power_kw": 0.0}}
        st, prm = ms.make_store(T0, dict(base, **{"crew-cpd": {"state": "TRAVEL", "task": "crusher-1",
                                                                "free_at": T0 + 240.0}}))
        lm, om, pm = modules(st, prm)
        lm.compute(T0)
        om.compute(T0)
        feats, issues = pm.compute(T0, seed=1)
        cr = next(f for f in issues.values() if f["node"] == "crusher-1")
        self.assertEqual(cr["status"], "CALLED")
        self.assertIn("бригада механиков ЦПД в пути", cr["text"])
        self.assertIn("уже вызвана", cr["text"])
        for w in ("Совет", "занята", "свободна", "отсрочк", "99."):
            self.assertNotIn(w, cr["text"])
        self.assertNotIn("Бед нет", feats["queue_text"])
        self.assertIn("Новых бед нет", feats["queue_text"])
        # at work there
        st.update_from_search(ms.snapshot(T0 + 30.0, dict(base, **{"crew-cpd": {"state": "WORK", "task": "crusher-1",
                                                                                "free_at": T0 + 240.0}})))
        feats, issues = pm.compute(T0 + 30.0, seed=1)
        cr = next(f for f in issues.values() if f["node"] == "crusher-1")
        self.assertEqual(cr["status"], "IN_WORK")
        self.assertIn("бригада механиков ЦПД на месте, освободится в 13:20", cr["text"])
        self.assertNotIn("свободна", cr["text"])
        # the crew left and the crusher still stands: the issue is open again, with advice
        st.update_from_search(ms.snapshot(T0 + 60.0, base))
        feats, issues = pm.compute(T0 + 60.0, seed=1)
        cr = next(f for f in issues.values() if f["node"] == "crusher-1")
        self.assertEqual(cr["status"], "OPEN")
        self.assertIn("Совет", cr["text"])
        self.assertIn("бригада механиков ЦПД свободна", cr["text"])

    def test_crew_busy_elsewhere_is_said_with_its_time(self):
        st, prm = ms.make_store(T0, {"crusher-1": {"state": "STOP", "tph": 0.0, "power_kw": 0.0},
                                     "stockpile-1": {"level_t": 11000.0},
                                     "crew-cpd": {"state": "WORK", "task": "conveyor-2", "free_at": T0 + 150.0}})
        lm, om, pm = modules(st, prm)
        lm.compute(T0)
        om.compute(T0)
        feats, issues = pm.compute(T0, seed=1)
        cr = next(f for f in issues.values() if f["node"] == "crusher-1")
        self.assertEqual(cr["status"], "OPEN")
        self.assertIn("бригада механиков ЦПД занята, освободится в 11:50", cr["text"])

    def test_no_loss_within_the_horizon_gives_no_times(self):
        """SAG-1 relined, crusher-1 stopped: the stock is not drawn, so no losses within 48 h; no "call by"
        two days ahead and no made-up time of losses."""
        st, prm = ms.make_store(T0, {"sag-1": {"state": "RELINE", "feed_tph": 0.0, "power_kw": 0.0},
                                     "crusher-1": {"state": "STOP", "tph": 0.0, "power_kw": 0.0}})
        lm, om, pm = modules(st, prm)
        lm.compute(T0)
        om.compute(T0)
        feats, issues = pm.compute(T0, seed=1)
        cr = next(f for f in issues.values() if f["node"] == "crusher-1")
        self.assertIn("потерь в ближайшие 48 ч не ожидается", cr["text"])
        self.assertIn("срочности нет", cr["text"])
        self.assertNotIn("сут.", cr["text"])
        self.assertNotIn("отложить до", cr["text"])
        self.assertEqual(cr["call_by"], -1.0)
        self.assertEqual(cr["loss_from"], -1.0)

    def test_delay_price_says_why_when_losses_start_later(self):
        """Losses running: a 1 h delay has a price. Losses later: never "$0", and a price is the risk that
        the work ends after the losses start (it never reads as a contradiction of "can defer")."""
        st, prm = ms.make_store(T0, {"sag-2": {"state": "STOP", "feed_tph": 0.0, "power_kw": 0.0},
                                     "crusher-1": {"state": "STOP", "tph": 0.0, "power_kw": 0.0},
                                     "stockpile-1": {"level_t": 11000.0},
                                     "thick-1": {"state": "HIGH", "hours_to_full": 3.0},
                                     "filter-1": {"limit_tph": 40.0}})
        lm, om, pm = modules(st, prm)
        lm.compute(T0)
        om.compute(T0)
        feats, issues = pm.compute(T0, seed=1)
        by = {f["kind"]: f["text"] for f in issues.values()}
        self.assertIn("потери идут", by["sag_stop"])
        self.assertIn("отсрочка вызова на 1 ч стоит ≈ $", by["sag_stop"])
        for kind in ("crusher_stop", "thick_high"):
            text = by[kind]
            self.assertIn("потерь до ", text)
            self.assertNotIn("отсрочка вызова на 1 ч стоит", text)
            self.assertNotIn("$0 ", text)
            if "отсрочки" in text:
                self.assertIn("риск, что ремонт не успеет до", text)

    def test_oxide_cause_names_the_batch_not_its_id(self):
        st, prm = ms.make_store(T0)
        lm, om, pm = modules(st, prm)
        lm.compute(T0)
        r = lm.eval_flot(T0, 2, 9.0, "batch-0013")[0]
        self.assertIn("окисленная руда (партия 13)", r.cause)
        self.assertIn("при среднем", r.cause)
        self.assertNotIn("batch-", r.cause)

    def test_issue_feature_types(self):
        st, prm = fork_store()
        lm, om, pm, feats, issues = run_fork(st, prm)
        cat = Catalog()
        for name, f in issues.items():
            out = cat.features("issue", f, "run", T0)
            self.assertEqual(set(out), set(cat.feature_names("issue")))
            for k, v in out.items():
                kind = cat.spec("issue", k)[0]
                self.assertIsInstance(v["properties"]["value"], {"number": float, "string": str, "object": dict}[kind], k)
            self.assertIn(out["status"]["properties"]["value"], cat.types["issue"]["states"])
        out = cat.features("mod-priority", feats, "run", T0)
        self.assertIsInstance(out["auto_call"]["properties"]["value"], dict)
        body = cat.thing_body("issue-1", "issue", "flot-1", "Беда 1")
        self.assertEqual(body["attributes"]["_parents"], "kz.aktogay:flot-1")
        self.assertTrue(body["definition"].endswith("issue-1.0.0.tm.jsonld"))
        self.assertEqual(set(body["features"]), set(cat.feature_names("issue")))
        for name, f in issues.items():
            self.assertEqual(f["status_ru"], priority.STATUS_RU[f["status"]])
        self.assertEqual({k: v["node"] for k, v in feats["issue_map"].items()},
                         {k: f["node"] for k, f in issues.items() if f["status"] != "RESOLVED"})


class SimDecisionsTest(unittest.TestCase):
    """The queue on the simulator's own measured snapshot (as Ditto would carry it): the decisions."""

    @staticmethod
    def run_scenario(text, minutes, every=5, **kw):
        from sim.plant import CopySet
        cs = CopySet(None, 42, text, **kw)
        fact = cs.copies["fact"]
        st, prm = ms.make_store(fact.t_min)
        lm, om, pm = modules(st, prm)
        feats = issues = None
        for _ in range(int(minutes // every)):
            for _ in range(every):
                cs.step()
            t = fact.t_min
            st.update_from_search(ms.items_from_plant(fact))
            lm.compute(t)
            if t % 15 == 0:
                om.compute(t)
            feats, issues = pm.compute(t, seed=1)
        return fact, pm, feats, issues

    def test_water_shortage_with_cost_in_m3_and_usd(self):
        fact, pm, feats, issues = self.run_scenario("water", 20)
        w = next(f for f in issues.values() if f["kind"] == "water_short")
        self.assertEqual(w["node"], "water")
        self.assertEqual(w["person"], "person-water")
        self.assertIn("м³/ч", w["text"])
        self.assertIn("нехватка оборотной воды", w["text"])
        self.assertGreater(w["loss_usd_h"], fact.state.water.leak_m3h * 0.3)     # copper and water
        self.assertIn("Хвосты и вода", feats["queue_text"])
        # the simulator booked its own crew for the leak (alarm): the queue names that crew, not the mill's,
        # and does not advise to call a crew that is already on its way there
        self.assertEqual(fact.state.crews["crew-water"].task, "water")
        self.assertIn("бригада хвостового хозяйства", w["text"])
        self.assertNotIn("механик", w["text"].lower())
        self.assertIn(w["status"], ("CALLED", "IN_WORK"))
        self.assertNotIn("Совет", w["text"])
        self.assertNotIn("Бед нет", feats["queue_text"])

    def test_fire_is_s0_first(self):
        fact, pm, feats, issues = self.run_scenario("hpgr_fire", 10)
        top = min(issues.values(), key=lambda f: f["rank"])
        self.assertEqual((top["kind"], top["safety_class"], top["node"]), ("hpgr_fire", "S0", "pebble-1"))
        self.assertEqual(top["person"], "person-power")
        self.assertIn("20 человек", top["text"])
        self.assertIn("линия 2 работает", top["text"])
        stop = next(f for f in issues.values() if f["kind"] == "pebble_stop")
        self.assertIn("после разрешения", stop["text"])
        self.assertGreater(stop["loss_usd_h"], 0.0)                               # consequences on the SAG
        self.assertNotIn("Механик фабрики", stop["text"].split("Совет")[-1].split("—")[0])
        # two issues of one node are told apart in the order lines
        self.assertIn("Дробление гали 1 (пожар) → Дробление гали 1 (останов)", feats["order_text"])

    def test_grid_names_what_to_shed_first_with_cost(self):
        fact, pm, feats, issues = self.run_scenario("grid", 15)
        g = next(f for f in issues.values() if f["kind"] == "grid_limited")
        # the automatic shedding acted first: what it shed is said, and not advised again
        self.assertIn("автоматика уже сбросила: шаровая 2B, фидер кат. 2", g["text"])
        self.assertIn("если лимит снизят ещё, отключать дальше", g["text"])
        self.assertNotIn("фидер прочей нагрузки", g["text"])
        self.assertNotIn("шаровая 2B ≈", g["text"])
        self.assertIn("1) шаровая", g["text"])
        self.assertIn("$", g["text"])
        self.assertEqual(g["person"], "person-power")

    def test_reline_and_downstream_not_counted_twice(self):
        """SAG-1 relined, grid cut and crusher-1 stopped: the loss of line 1 is the SAG's (S0, no money);
        the crusher waits for nothing (the SAG draws no ore) and the grid loss is line 2 only."""
        fact, pm, feats, issues = self.run_scenario("reline:1+grid+crusher:1", 15)
        kinds = {f["kind"]: f for f in issues.values()}
        self.assertEqual(kinds["reline"]["safety_class"], "S0")
        self.assertEqual(kinds["crusher_stop"]["loss_from"], -1.0)               # no losses expected
        base_line = pm.prm["line_tph_base"] * pm.prm["flot_grade_ref_pct"] * pm.prm["flot_rec_ref_pct"] / 1e4
        grid_loss_cu = kinds["grid_limited"]["loss_usd_h"] / (pm.prm["cu_price_usd_t"] * pm.prm["payable_frac"])
        self.assertLess(grid_loss_cu, base_line)                                  # not both lines' base
        self.assertNotIn("ball_stop", kinds)
        self.assertNotIn("Шаровая 1", feats["queue_text"])

    def test_hard_ore_is_a_clear_decision(self):
        fact, pm, feats, issues = self.run_scenario("hard:1", 30)
        h = next((f for f in issues.values() if f["kind"] == "hard_ore"), None)
        self.assertIsNotNone(h)
        self.assertIn("прогноз на 12 ч", h["text"])
        self.assertIn("шихтовать 50/50", h["text"])
        self.assertIn("твёрдая руда — партия ", h["text"])
        self.assertNotIn("партия партия", h["text"])
        self.assertEqual(h["person"], "person-geologist")


_MODEL = None


def _model():
    global _MODEL
    if _MODEL is None:
        setup = os.path.join(ROOT, "setup")
        if setup not in sys.path:
            sys.path.insert(0, setup)
        import twins
        _MODEL = twins.Model()
    return _MODEL


def real_snapshot(t, overrides=None, batches=None):
    """Every thing of setup/things.json with its Ditto attributes (people, crews, responsible.person) and
    the base features of mod_support: what akt-priority reads on the stand."""
    m = _model()
    overrides = overrides or {}
    items = []
    for thing in m.things:
        name, typ = thing["name"], thing["type"]
        vals = dict(ms.BASE.get(typ, {}))
        if typ == "person":
            vals = {"state": "FREE", "location": "", "task": "", "free_at": -1.0}
        elif typ == "piezometer":
            vals = {"state": "OK", "kpa": 140.0, "alarm": 0.0}
        vals.update(overrides.get(name, {}))
        attrs = m.attributes(thing)
        attrs["type"] = typ
        items.append(ms.item(name, vals, t, attrs))
    for b in batches or []:
        items.append(ms.batch_item(t, **b))
    return items


def real_store(t, overrides=None, batches=None):
    from modules.store import Store
    prm = ms.default()
    st = Store(ms.NS, prm["hist_min"])
    st.update_from_search(real_snapshot(t, overrides, batches))
    return st, prm


class WhoTest(unittest.TestCase):
    """Crew, person and role of every trouble kind come from one table (priority.WHO) and agree with
    each other, with the crew things and people in Ditto, and with the simulator's crews and callers."""

    # trouble kinds made from states: overrides of one stand snapshot -> kinds expected there
    CASES = [
        ({"crusher-1": {"state": "STOP", "tph": 0.0, "lube_kpa": 250.0}, "stockpile-1": {"hours_left": 7.0},
          "crusher-2": {"state": "STOP", "tph": 0.0, "lube_kpa": 150.0}, "stockpile-2": {"hours_left": 7.0}},
         ("crusher_stop", "lube_trip")),
        ({"conveyor-1": {"state": "STOP", "tph": 0.0}, "stockpile-1": {"hours_left": 7.0},
          "sag-2": {"state": "STOP", "feed_tph": 0.0, "power_kw": 0.0}}, ("conveyor_stop", "sag_stop")),
        ({"sag-1": {"state": "RELINE", "feed_tph": 0.0, "power_kw": 0.0}, "pebble-2": {"state": "STOP"},
          "ball-2a": {"state": "STOP", "power_kw": 0.0}}, ("reline", "pebble_stop", "ball_stop")),
        ({"pebble-1": {"state": "STOP", "fire": 1.0}}, ("hpgr_fire", "pebble_stop")),
        ({"filter-1": {"state": "ONE", "presses_on": 1.0, "limit_tph": 35.0}, "thick-1": {"hours_to_full": 6.7},
          "filter-2": {"state": "STOP", "limit_tph": 0.0}}, ("filter_one", "filter_stop")),
        ({"thick-1": {"state": "HIGH", "hours_to_full": 3.0}, "filter-1": {"limit_tph": 40.0},
          "thick-2": {"state": "FULL", "hours_to_full": 0.0}, "filter-2": {"limit_tph": 40.0}},
         ("thick_high", "thick_full")),
        ({"person-mill-mech": {"state": "WORK", "location": "ball-1a", "task": "ball-1a", "permit": "ball-1a",
                               "free_at": T0 + 120.0},
          "ball-1a": {"state": "STOP", "power_kw": 0.0, "start_cmd": 1.0}}, ("startup_zone", "ball_stop")),
        ({"water": {"wind_ms": 14.0, "beach_dry_pct": 85.0}}, ("tailings_dust",)),
        ({"cyclones-1": {"p80_um": 215.0}}, ("grind_coarse",)),
        ({"flot-1": {"conc_cu": 21.5, "conc_tph": 64.0}}, ("conc_low",)),
        ({"conc-stock": {"state": "HIGH", "hours_to_full": 5.0}}, ("cstock_high",)),
        ({"conc-stock": {"state": "FULL", "hours_to_full": 0.0}}, ("cstock_full",)),
        ({"fleet": {"state": "SHORT", "haul_tph": 5000.0}}, ("fleet_short",)),
        ({"power": {"state": "LIMITED", "grid_limit_mw": 210.0}, "line-2": {"cu_tph": 7.0}}, ("grid_limited",)),
        ({"water": {"state": "ALARM", "piezo_kpa": 190.0}}, ("dam_alarm",)),
        ({"piezo-2": {"state": "ALARM", "kpa": 195.0, "alarm": 1.0}}, ("dam_alarm",)),   # one dam piezometer
        ({"water": {"state": "SHORT", "leak_m3h": 600.0, "cut_tph": 300.0, "short_m3h": 120.0,
                    "intake_cap_m3h": 6126.0}}, ("water_short",)),
        ({"pit": {"state": "STOP", "mining_tph": 0.0}, "exc-1": {"state": "DOWN", "tph": 0.0},
          "exc-2": {"state": "DOWN", "tph": 0.0}, "exc-3": {"state": "DOWN", "tph": 0.0},
          "crusher-1": {"tph": 0.0}, "crusher-2": {"tph": 0.0}}, ("pit_stop",)),
        # tier S of 23.10.2026
        ({"pit": {"visibility_m": 120.0, "road_grip": 0.30, "road_restrict": 0.0}}, ("road_winter",)),
        ({"fleet": {"fatigue": 1.0, "fatigue_truck": "HT141 (CAT 793D)"}}, ("driver_fatigue",)),
        ({"cyclones-1": {"circ_load_pct": 365.0, "p80_um": 215.0}, "ball-1a": {"power_pct": 112.0}}, ("roping",)),
        ({"ph-1": {"ph": 10.8, "sp_ph": 10.8, "lab_ph": 11.5, "age_min": 60.0}}, ("sensor_ph",)),
        ({"pebble-2": {"hpgr_tph": 1061.0, "hpgr_skew_pct": 12.0, "hpgr_kw_diff_pct": 18.0, "limit_tph": 530.0,
                       "metal_alarm": 0.0}}, ("hpgr_uneven",)),
        ({"crusher-1": {"state": "STOP", "tph": 0.0, "lube_kpa": 250.0, "service": 1.0, "service_left_h": 60.0},
          "stockpile-1": {"hours_left": 7.0}}, ("crusher_mantle",)),
        ({"exc-1": {"oil_pct": 120.0, "oil_alert": 1.0}}, ("oil_contam",)),
        ({"exc-2": {"state": "DOWN", "tph": 0.0}}, ("exc_down",)),
        ({"leach-1": {"state": "COLD", "cold_frac": 0.25, "level_tph": 1.6, "irrigation_pct": 75.0, "leach_exp_tph": 1.4}}, ("leach_cold",)),
        ({"ew-1": {"state": "TRIP", "current_ka": 0.0, "current_set_ka": 18.0, "cathode_exp_tph": 1.4, "cathode_tph": 0.0, "electrolyte_cu_t": 18.0},
          "sx-1": {"transfer_cu_tph": 1.4}}, ("ew_rect",)),
        ({"sx-1": {"state": "CRUD", "crud_cm": 4.0, "extraction_pct": 85.0, "raff_cu_gl": 0.2}, "ew-1": {"cathode_exp_tph": 1.4}}, ("sx_crud",)),
        # tier T of 24.10.2026
        ({"sag-1": {"gmd_gap_mm": 11.0}}, ("gmd_gap",)),
        ({"conveyor-1": {"idler_temp_c": 95.0}}, ("idler_hot",)),
        ({"flot-1": {"level_swing_pct": 9.0}}, ("froth_swing",)),
        ({"thick-1": {"rake_torque_pct": 55.0}}, ("rake_torque",)),
        ({"filter-1": {"cycle_pct": 140.0}}, ("cloth_blind",)),
        ({"cyclones-1": {"pump_head_pct": 82.0}}, ("pump_cavit",)),
        ({"fleet": {"brake_oil_c": 125.0}}, ("brake_hot",)),
        ({"exc-1": {"track_press_pct": 95.0}, "exc-2": {"state": "DOWN", "tph": 0.0}, "exc-3": {"state": "DOWN", "tph": 0.0}},
         ("track_tension",)),
    ]
    # the stand's own rule of who goes, for every kind: kind -> (crew, person, words in the role)
    EXPECT = {
        "water_short": ("crew-water", "person-water", ("Технолог хвостов и оборотной воды",)),
        "dam_alarm": ("", "person-water", ("Технолог хвостов",)),               # dam piezometer
        "grid_limited": ("", "person-power", ("Дежурный энергетик",)),
        "hpgr_fire": ("", "person-power", ("Дежурный энергетик", "сменный руководитель ЦУП")),
        "crusher_stop": ("crew-cpd", "person-crusher-mech", ("Механик ЦПД",)),
        "conveyor_stop": ("crew-cpd", "person-crusher-mech", ("Механик ЦПД",)),
        "lube_trip": ("crew-kip", "person-kip", ("Дежурный КИПиА",)),          # protection sensor (КИПиА)
        "loss_flot": ("crew-kip", "person-kip", ("Дежурный КИПиА", "металлург смены")),   # dose, flowmeter
        "loss_flot_oxide": ("", "person-geologist", ("Геолог смены", "металлург смены")),
        "loss_cyclones": ("crew-mill", "person-mill-mech", ("Механик фабрики", "металлург смены")),
        "loss_sag": ("", "person-metallurgist", ("Металлург смены", "механик фабрики")),   # kWh/t above the ore
        "reagent_over": ("crew-kip", "person-kip", ("Дежурный КИПиА", "металлург смены")),  # collector overdose
        "hard_ore": ("", "person-geologist", ("Геолог смены", "горный диспетчер", "металлург смены")),
        "reline": ("", "person-dispatcher", ("Горный диспетчер", "начальник смены фабрики")),
        "sag_stop": ("crew-mill", "person-mill-mech", ("Механик фабрики",)),
        "pebble_stop": ("crew-mill", "person-mill-mech", ("Механик фабрики",)),
        "pebble_stop_fire": ("", "person-mill-mech", ("Механик фабрики",)),
        "ball_stop": ("crew-mill", "person-mill-mech", ("Механик фабрики",)),
        "filter_one": ("crew-mill", "person-mill-mech", ("Механик фабрики", "начальник смены фабрики")),
        "filter_stop": ("crew-mill", "person-mill-mech", ("Механик фабрики", "начальник смены фабрики")),
        "thick_high": ("crew-mill", "person-mill-mech", ("Механик фабрики", "начальник смены фабрики")),
        "thick_full": ("crew-mill", "person-mill-mech", ("Механик фабрики", "начальник смены фабрики")),
        "cstock_high": ("", "person-metallurgist", ("Металлург смены", "начальник смены фабрики")),
        "cstock_full": ("", "person-metallurgist", ("Металлург смены", "начальник смены фабрики")),
        "fleet_short": ("", "person-dispatcher", ("Горный диспетчер",)),
        "pit_stop": ("", "person-dispatcher", ("Горный диспетчер", "геолог смены")),
        "startup_zone": ("", "person-shift-head", ("Начальник смены фабрики", "механик фабрики")),
        "tailings_dust": ("", "person-water", ("Технолог хвостов и оборотной воды",)),
        "grind_coarse": ("", "person-metallurgist", ("Металлург смены", "механик фабрики")),
        "conc_low": ("", "person-metallurgist", ("Металлург смены", "дежурный КИПиА")),
        "road_winter": ("", "person-dispatcher", ("Горный диспетчер", "начальник смены карьера", "дорожная служба карьера")),
        "driver_fatigue": ("", "person-dispatcher", ("Горный диспетчер", "начальник смены карьера")),
        "roping": ("", "person-grind-op", ("Оператор пульта измельчения", "металлург смены")),
        "sensor_ph": ("crew-kip", "person-kip", ("Дежурный КИПиА", "металлург смены")),
        "hpgr_uneven": ("crew-mill", "person-mill-mech", ("Механик фабрики", "оператор пульта измельчения")),
        "crusher_mantle": ("crew-cpd", "person-crusher-mech", ("Механик ЦПД", "начальник смены фабрики")),
        "oil_contam": ("", "person-pit-mech", ("Сменный механик", "горный диспетчер")),
        "exc_down": ("", "person-pit-mech", ("Сменный механик", "горный диспетчер")),
        "leach_cold": ("", "person-metallurgist", ("Металлург смены", "начальник смены фабрики")),
        "ew_rect": ("", "person-power", ("Дежурный энергетик", "металлург смены")),
        "sx_crud": ("", "person-metallurgist", ("Металлург смены", "начальник смены фабрики")),
        "gmd_gap": ("", "person-kip", ("Дежурный КИПиА", "дежурный энергетик")),
        "idler_hot": ("", "person-crusher-mech", ("Механик ЦПД", "механик фабрики")),
        "froth_swing": ("", "person-kip", ("Дежурный КИПиА", "металлург смены")),
        "rake_torque": ("", "person-mill-mech", ("Механик фабрики", "начальник смены фабрики")),
        "cloth_blind": ("", "person-mill-mech", ("Механик фабрики", "начальник смены фабрики")),
        "pump_cavit": ("", "person-mill-mech", ("Механик фабрики", "оператор пульта измельчения")),
        "brake_hot": ("", "person-pit-mech", ("Сменный механик", "горный диспетчер")),
        "track_tension": ("", "person-pit-mech", ("Сменный механик", "горный диспетчер")),
    }

    def collect(self):
        """{WHO key: (Trouble, issue features)} over all cases, the found losses and the hard-ore forecast."""
        m = _model()
        found = {}
        t = T0

        def take(pm, issues, fire=False):
            by_id = {i.key: i for i in pm.issues.values()}
            for tr in pm.troubles(t):
                f = issues[by_id[tr.id].name]
                who = tr.kind
                if tr.kind == "pebble_stop" and fire:
                    who = "pebble_stop_fire"
                if tr.kind == "loss_flot" and tr.crew == "":
                    who = "loss_flot_oxide"
                found[who] = (tr, f)

        for ov, kinds in self.CASES:
            st, prm = real_store(t, ov)
            lm, om, pm = modules(st, prm)
            pm.roles = m.roles
            lm.compute(t)
            om.compute(t)
            feats, issues = pm.compute(t, seed=1)
            got = {tr.kind for tr in pm.troubles(t)}
            for k in kinds:
                self.assertIn(k, got, ov)
            take(pm, issues, fire="fire" in str(ov))
        # losses found by akt-losses (the module's results, as the module leaves them)
        from modules.losses import NodeResult
        st, prm = real_store(t)
        lm, om, pm = modules(st, prm)
        pm.roles = lm.roles = m.roles
        lm.compute(t)
        om.compute(t)
        dose = lm.eval_flot(t, 1, 5.0, "")[0]                       # ordinary ore: the flowmeter, then the metallurgist
        oxide = lm.eval_flot(t, 2, 9.0, "")[0]                      # oxidised ore: the geologist
        cyc = lm.eval_cyclones(t, 1, 35.0, 0.41, 87.0)
        sag = lm.eval_sag(t, 2, 35.0, 0.41, 87.0)
        for r in (dose, oxide, cyc, sag):
            r.status, r.gap_cu_tph, r.detected_at, r.cause = "loss", 0.5, t - 30.0, "находка модуля"
        self.assertEqual(dose.role_keys, priority.WHO["loss_flot"][1])
        self.assertEqual(oxide.role_keys, priority.WHO["loss_flot_oxide"][1])
        self.assertEqual(cyc.role_keys, priority.WHO["loss_cyclones"][1])
        self.assertEqual(sag.role_keys, priority.WHO["loss_sag"][1])
        lm.results = {"flot-1": dose, "flot-2": oxide, "cyclones-1": cyc, "sag-2": sag}
        # collector overdose found by the tank balance of line 1
        lm.reagent = {1: {"status": "loss", "usd_h": 60.0, "excess": 0.4, "text": "реагенты линии 1: +40 %"},
                      2: {"status": "noise", "usd_h": 0.0, "excess": 0.01, "text": ""}}
        feats, issues = pm.compute(t, seed=1)
        take(pm, issues)
        # hard ore ahead of line 1 (akt-ore forecast)
        batches = [{"name": "batch-0009", "line": 1, "state": "BELT", "est_axb": 27.0, "tonnes": 15000.0}]
        st, prm = real_store(t, batches=batches)
        lm, om, pm = modules(st, prm)
        pm.roles = m.roles
        lm.compute(t)
        om.compute(t)
        feats, issues = pm.compute(t, seed=1)
        take(pm, issues)
        return found

    def test_every_kind_one_crew_one_person_one_role(self):
        m = _model()
        found = self.collect()
        self.assertEqual(set(found), set(priority.WHO), "a WHO kind is not covered by the test")
        self.assertEqual(set(self.EXPECT), set(priority.WHO), "a WHO kind has no expected crew and person")
        crew_names = set(priority.CREW_RU.values())
        for who, (tr, f) in sorted(found.items()):
            crew, roles = priority.WHO[who]
            with self.subTest(kind=who):
                self.assertEqual(tr.crew, crew)
                # the person twin is the first role's, and the role text starts with that role
                self.assertIn(tr.person, m.by_name)
                person = m.by_name[tr.person]
                self.assertEqual(person["type"], "person")
                self.assertEqual(person["responsible"]["role"], roles[0])
                self.assertTrue(tr.role.startswith(m.roles[roles[0]]), tr.role)
                for r in roles[1:]:
                    name = m.roles[r]
                    self.assertIn(name[:1].lower() + name[1:], tr.role)
                # the issue thing says the same
                self.assertEqual(f["person"], tr.person)
                self.assertEqual(f["responsible"], tr.role)
                text = f["text"]
                if crew:
                    # the crew is led by that person (crew thing in Ditto, simulator roster) and named in the line
                    self.assertEqual(priority.CREW_LEAD[crew], roles[0])
                    self.assertEqual(m.by_name[crew]["responsible"]["person"], tr.person)
                    self.assertEqual(m.by_name[crew]["responsible"]["role"], roles[0])
                    self.assertIn(priority.CREW_RU[crew], text)
                    for other in crew_names - {priority.CREW_RU[crew]}:
                        self.assertNotIn(other, text)
                else:
                    for name in crew_names:
                        self.assertNotIn(name, text)
                self.assertIn(tr.role, text)
                if who in self.EXPECT:
                    e_crew, e_person, words = self.EXPECT[who]
                    self.assertEqual((tr.crew, tr.person), (e_crew, e_person))
                    for w in words:
                        self.assertIn(w, tr.role)
        # the complaint: water called the tailings technologist but showed the mill mechanics' crew
        w = found["water_short"][1]["text"]
        self.assertIn("бригада хвостового хозяйства свободна", w)
        self.assertNotIn("механик", w.lower())

    def test_simulator_sends_the_same_crew_and_person(self):
        from sim import site_aktogay as site
        from sim.state import CREW_FOR
        role_of = {pid: role for pid, role, _ru, _crew, _home in site.PEOPLE}
        crew_of = {pid: crew for pid, _role, _ru, crew, _home in site.PEOPLE}
        # a crew job in the simulator (issue kind -> crew) is the queue's crew of that trouble
        for sim_kind, who in (("crusher", "crusher_stop"), ("lube_trip", "lube_trip"), ("dose", "loss_flot"),
                              ("cyclone", "loss_cyclones"), ("reagent", "reagent_over"), ("water", "water_short"),
                              ("sag", "sag_stop"), ("ball", "ball_stop"), ("pebble", "pebble_stop"),
                              ("filter", "filter_one"), ("conveyor", "conveyor_stop")):
            with self.subTest(sim_kind=sim_kind):
                self.assertEqual(CREW_FOR[sim_kind], priority.WHO[who][0])
        from sim.params import default as sim_default
        from sim.state import initial_state, topology
        topo = topology()
        crews = initial_state(sim_default(), seed=1).crews
        for crew, person in site.CREW_PERSON.items():
            self.assertEqual(role_of[person], priority.CREW_LEAD[crew], crew)
            self.assertEqual(crew_of[person], crew, crew)
            self.assertEqual(topo[crew].role, priority.CREW_LEAD[crew], crew)      # the crew thing's role
            self.assertEqual(crews[crew].role, priority.CREW_LEAD[crew], crew)     # the crew state of the plant
        self.assertEqual(set(site.CREW_PERSON), set(priority.CREW_RU))
        # a decision called in the simulator goes to the person the queue names first
        for sim_kind, who in (("grid", "grid_limited"), ("hard", "hard_ore"), ("hpgr_fire", "hpgr_fire"),
                              ("reline", "reline"), ("water", "water_short"), ("energy", "loss_sag"),
                              ("liner", "loss_sag")):
            with self.subTest(decision=sim_kind):
                self.assertEqual(role_of[site.DECISION_PERSON[sim_kind]], priority.WHO[who][1][0])


if __name__ == "__main__":
    unittest.main()
