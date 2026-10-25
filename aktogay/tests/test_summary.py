"""The text view of the stand, GET /summary and /summary.json (web/summary.py): built from the cached state, no JavaScript."""
import http.client
import json
import os
import sys
import threading
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
STATIC = os.path.join(WEB, "static")
if WEB not in sys.path:
    sys.path.insert(0, WEB)

import server  # noqa: E402
import summary  # noqa: E402


def thing(name, feats, attrs=None):
    return {"thingId": "kz.aktogay:" + name, "attributes": dict({"name_ru": name}, **(attrs or {})),
            "features": {k: {"properties": {"value": v}} for k, v in feats.items()}}


def make_state(run="r1", issues=True, scenario="crusher:1"):
    th = [thing("site", {"sim_time": 725.0, "state_ru": "идёт", "speed": 60.0, "speed_fact": 59.9, "idSimulationRun": run, "seed": 42.0,
                         "scenario": scenario, "cu_tph": 27.0, "tph": 7000.0, "power_mw": 250.0}),
          thing("power", {"grid_limit_mw": 300.0}), thing("line-1", {"recovery": 87.5}), thing("line-2", {"recovery": 88.0}),
          thing("crusher-1", {}, {"name_ru": "Дробилка ЦПД-1"}),
          thing("mod-losses", {"processed_sim_time": 715.0, "top_text": "потерь сверх шума нет", "flot-1_status_ru": "в пределах шума",
                               "flot-1_gap_cu_tph": 0.1, "flot-1_gap_usd_h": 1400.0}),
          thing("mod-ore", {"processed_sim_time": 705.0, "fc_text": "прогноз подачи"}),
          thing("mod-priority", {"processed_sim_time": 720.0, "order_text": "по $: Дробилка ЦПД-1", "queue_text": "1. Дробилка"}),
          thing("validation-calib", {"state": "DONE", "report_json": json.dumps({"rows": [{"ok": True}, {"ok": False}, {"ok": None}]})}),
          thing("baseline", {"shift_result": {"run": run, "kind": "scenario", "t_min": 725.0, "copies": {"base": {"cu_t": 100.0}, "fact": {"cu_t": 98.5}},
                                              "diff": {"fact": {"cu_t": -1.5}}, "fork": {}, "policy": {"mode": "module", "n_calls": 2, "n_module": 2}}})]
    if issues:
        th.append(thing("issue-1", {"idSimulationRun": run, "status": "OPEN", "status_ru": "ждёт решения", "rank": 1.0, "node": "crusher-1",
                                    "kind": "crusher_stop", "loss_usd_h": 153000.0, "delay_cost_usd": 150000.0, "responsible": "Механик ЦПД",
                                    "text": "Дробилка стоит <b>", "choice_text": "потери идут сейчас", "safety_class": ""}))
        th.append(thing("issue-2", {"idSimulationRun": run, "status": "RESOLVED", "rank": 99.0, "node": "crusher-1"}))
    return {"now": time.time(), "count": len(th), "things": th}


class SummaryBuildTest(unittest.TestCase):
    def test_content(self):
        d = summary.build(make_state(), STATIC)
        self.assertEqual(d["now"]["model_time"], "12:05")
        self.assertEqual(d["first_trouble"]["call"], "Механик ЦПД")
        self.assertEqual(d["queue_total"], 1)                     # the resolved one is not listed
        self.assertEqual([m["lag_min"] for m in d["modules"]], [10.0, 20.0, 5.0])
        self.assertEqual(d["scenario"]["base_to_fact"]["diff_cu_t"]["fact"], -1.5)
        c = d["calibration"]
        self.assertEqual((c["rows"], c["in_tolerance"], c["out_of_tolerance"], c["no_tolerance"]), (3, 1, 1, 1))
        self.assertEqual(c["backtest"]["quarters"], 28)
        self.assertEqual(len(d["tiles"]), 6)

    def test_all_scenarios_and_pages_are_listed(self):
        d = summary.build(make_state(), STATIC)
        with open(os.path.join(STATIC, "scenarios.json"), encoding="utf-8") as f:
            ids = [s["id"] for s in json.load(f)["scenarios"]]
        self.assertEqual([s["id"] for s in d["scenarios"]], ids)
        self.assertEqual(len(ids), 30)
        self.assertTrue(all(s["expected_by_20_00"] for s in d["scenarios"] if s["id"] in ("crusher:1", "grid", "fork")))
        fork = [s for s in d["scenarios"] if s["id"] == "fork"][0]
        self.assertIn("twin_minus_no_twin_cu_t", fork["expected_by_20_00"])
        self.assertTrue(all(s["start"].startswith("/?") for s in d["scenarios"]))
        views = {v["url"].split("view=")[1].split("&")[0] for v in d["views"]}
        for v in ("plan", "queue", "modules", "calib", "economics", "scenarios", "howto", "copper", "inside", "replay", "diorama", "site"):
            self.assertIn(v, views)

    def test_no_issues(self):
        d = summary.build(make_state(issues=False), STATIC)
        self.assertIsNone(d["first_trouble"])
        self.assertIn("Открытых бед нет", summary.render_html(d))

    def test_html_is_escaped_text_without_scripts(self):
        h = summary.render_html(summary.build(make_state(), STATIC))
        self.assertNotIn("<script", h.lower())
        self.assertIn("Дробилка стоит &lt;b&gt;", h)
        for needle in ("Беда № 1", "Очередь бед", "Шесть плиток", "Модули", "Где теряется медь", "Все сценарии", "/summary.json", "/api/state",
                       "?scenario=crusher:1&amp;run=1", "?view=modules", "Проверка правдоподобия", "28 кварталов"):
            self.assertIn(needle, h, needle)
        for bad in ("жюри", "судь", "judge", "jury", "llm"):
            self.assertNotIn(bad, h.lower())

    def test_empty_state_does_not_fail(self):
        self.assertTrue(summary.render_html(summary.build({"things": []}, STATIC)))


class SummaryHttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = json.dumps(make_state()).encode("utf-8")
        cls.old = server.state_bytes
        cls.old_t = server.STATE.t
        server.state_bytes = lambda: cls.state
        server.STATE.t = 1.0
        server._summary_cache.update(t=None, json=b"", html=b"")
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        server.state_bytes = cls.old
        server.STATE.t = cls.old_t
        server._summary_cache.update(t=None, json=b"", html=b"")

    def get(self, path):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request("GET", path)
        r = c.getresponse()
        return r.status, r.getheader("Content-Type"), r.read()

    def test_summary_and_json(self):
        st, ct, body = self.get("/summary")
        self.assertEqual(st, 200)
        self.assertIn("text/html", ct)
        self.assertIn("Беда № 1".encode(), body)
        st, ct, body = self.get("/summary.json")
        self.assertEqual(st, 200)
        self.assertEqual(json.loads(body)["now"]["model_time"], "12:05")

    def test_fast_when_cached(self):
        self.get("/summary")
        t = time.perf_counter()
        for _ in range(20):
            self.get("/summary")
        self.assertLess((time.perf_counter() - t) / 20, 0.3)

    def test_index_links_to_the_summary(self):
        with open(os.path.join(STATIC, "index.html"), encoding="utf-8") as f:
            idx = f.read()
        self.assertIn('href="/summary"', idx)
        self.assertRegex(idx, r"(?s)<noscript>.*/summary.*</noscript>")
        with open(os.path.join(ROOT, "web", "docker", "web.Dockerfile"), encoding="utf-8") as f:
            self.assertIn("summary.py", f.read())


if __name__ == "__main__":
    unittest.main()
